from __future__ import annotations

import threading
from queue import Empty, Queue
from typing import Iterable, Optional, Sequence, Union

import serial
import structlog


class SerialWorker:
    """Manage a background serial reader/writer with auto-reconnect."""

    RETRY_DELAY_SECONDS = 5
    SEND_DELAY_SECONDS = 0.1
    READ_CHUNK_SIZE = 4096
    _STOP_SENTINEL = object()

    def __init__(self, port: str, baud: int, message_queue: Queue):
        self.port = port
        self.baud = baud
        self.message_queue = message_queue

        self._logger = structlog.get_logger().bind(component="SerialWorker")
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._serial: Optional[serial.Serial] = None
        self._serial_lock = threading.Lock()
        self._write_queue: Queue = Queue()
        self._shutdown_notified = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="SerialWorker", daemon=True
        )
        self._thread.start()

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            self._await_thread()
            return

        self._logger.info("Shutting down serial worker")
        self._stop_event.set()
        # Wake any pending write operations and unblock the reader.
        self._write_queue.put(self._STOP_SENTINEL)
        self._close_serial()
        self._await_thread()
        self._notify_shutdown()

    def reconfigure(self, port: str, baud: int) -> None:
        if port == self.port and baud == self.baud:
            return

        self._logger.info("Reconfiguring serial connection", port=port, baud=baud)
        self.port = port
        self.baud = baud
        self._queue_message(f"Reconfiguring serial connection to {port} at {baud} baud")
        self._close_serial()

    def send(self, command: Union[Sequence[str], str]) -> None:
        if self._stop_event.is_set():
            self._queue_message("Cannot send: serial worker is shutting down")
            return

        commands: Iterable[str]
        if isinstance(command, str):
            if not command.strip():
                return
            commands = [command]
        elif isinstance(command, Sequence):
            commands = [str(cmd) for cmd in command if str(cmd).strip()]
            if not commands:
                return
        else:
            self._logger.warning("Unsupported command type", command_type=type(command))
            return

        for index, cmd in enumerate(commands):
            delay = self.SEND_DELAY_SECONDS if index else 0.0
            self._write_queue.put((cmd, delay))

    def _run(self) -> None:
        self._logger.info("Serial worker thread started")
        while not self._stop_event.is_set():
            if not self._ensure_connection():
                break
            self._read_loop()
        self._logger.info("Serial worker thread exiting")

    def _ensure_connection(self) -> bool:
        while not self._stop_event.is_set() and not self._serial:
            try:
                serial_conn = serial.Serial(self.port, self.baud, timeout=1)
                with self._serial_lock:
                    self._serial = serial_conn
                serial_conn.flush()
                self._logger.info(
                    "Connected to serial port", port=self.port, baud=self.baud
                )
                self._queue_message(f"Connected to {self.port} at {self.baud} baud")
                return True
            except serial.SerialException as exc:
                self._logger.warning(
                    "Failed to open serial port",
                    port=self.port,
                    baud=self.baud,
                    error=str(exc),
                )
                self._queue_message(
                    f"Serial open failed for {self.port} at {self.baud} baud: {exc}. "
                    f"Retrying in {self.RETRY_DELAY_SECONDS}s"
                )
                if self._stop_event.wait(self.RETRY_DELAY_SECONDS):
                    break
            except OSError as exc:
                self._logger.warning(
                    "OS error opening serial port",
                    port=self.port,
                    baud=self.baud,
                    error=str(exc),
                )
                self._queue_message(
                    f"OS error opening {self.port}: {exc}. Retrying in {self.RETRY_DELAY_SECONDS}s"
                )
                if self._stop_event.wait(self.RETRY_DELAY_SECONDS):
                    break
        return bool(self._serial)

    def _read_loop(self) -> None:
        while not self._stop_event.is_set() and self._serial:
            self._drain_write_queue()

            if not self._serial or not self._serial.is_open:
                return

            try:
                line = self._serial.readline(self.READ_CHUNK_SIZE)
            except (serial.SerialException, OSError, TypeError) as exc:
                self._handle_disconnect(exc)
                return

            if not line:
                continue

            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                self._queue_message(f"Received: {decoded}")

    def _drain_write_queue(self) -> None:
        while True:
            try:
                item = self._write_queue.get_nowait()
            except Empty:
                return

            if item is self._STOP_SENTINEL:
                return

            command, delay = item
            if not isinstance(command, str):
                continue

            if not self._serial or not self._serial.is_open:
                # Put the command back so it can be retried after reconnection.
                self._write_queue.put((command, delay))
                self._queue_message(
                    "Serial port not connected; command will retry after reconnect"
                )
                return

            try:
                with self._serial_lock:
                    self._serial.write((command + "\n").encode("utf-8"))
                self._queue_message(f"Sent: {command}")
            except (serial.SerialException, OSError) as exc:
                self._handle_disconnect(exc)
                return

            if delay > 0 and self._stop_event.wait(delay):
                return

    def _handle_disconnect(self, exc: Exception) -> None:
        self._logger.warning(
            "Serial connection lost", port=self.port, baud=self.baud, error=str(exc)
        )
        self._queue_message(
            f"Serial error: {exc}. Reconnecting in {self.RETRY_DELAY_SECONDS}s"
        )
        self._close_serial()
        self._stop_event.wait(self.RETRY_DELAY_SECONDS)

    def _close_serial(self) -> None:
        with self._serial_lock:
            if self._serial:
                try:
                    if self._serial.is_open:
                        self._serial.close()
                except serial.SerialException as exc:
                    self._logger.warning("Error closing serial port", error=str(exc))
                finally:
                    self._serial = None

    def _await_thread(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _notify_shutdown(self) -> None:
        if self._shutdown_notified:
            return
        self._shutdown_notified = True
        self._queue_message("Serial worker stopped")
        self.message_queue.put(None)

    def _queue_message(self, message: str) -> None:
        if message is None:
            return
        try:
            self.message_queue.put_nowait(message)
        except Exception:
            self._logger.warning("Failed to enqueue message", message=message)
