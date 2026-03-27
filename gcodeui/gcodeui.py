import argparse
import os
import shutil
import sys
from functools import partial
from pathlib import Path
from queue import Empty, Queue

import structlog
import yaml
from tkinter import END, Button, Entry, Frame, Label, Scrollbar, Text, Tk

from gcodeui.serial_worker import SerialWorker


logger = structlog.get_logger()


class GCodeApp:
    NUM_COLS = 4
    JOG_STEPS = [-10, -1, -0.1, 0, 0.1, 1, 10]
    FG = "#ffffff"

    def __init__(self, master, args):
        cfg = self.load_config(args)
        port, baud = self.get_port(args, cfg)
        self.background_color = cfg.get("background_color", "#f5f7fa")

        self.message_queue = Queue()
        self._queue_active = True
        self._queue_job = None
        self._closing = False

        self.master = master
        self.master.title("G-code Sender")
        self.master.configure(bg=self.background_color)
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.schedule_queue_flush()

        self.label = Label(master, text="Enter G-code:")
        self.label.grid(row=0, column=0, sticky="nw")

        self.entry = Entry(master)
        self.entry.grid(row=0, column=1, columnspan=2, sticky="new")
        self.entry.bind("<Return>", lambda event: self.send_gcode())

        self.send_button = Button(master, text="Send", command=self.send_gcode)
        self.send_button.grid(row=0, column=4)

        row = 1
        col = 0
        self.buttons = []
        for cmd in cfg.get("commands", []):
            button = Button(
                master,
                text=cmd["title"],
                bg=self.get_color(cmd),
                fg=GCodeApp.FG,
                command=partial(self.send_specific_gcode, cmd["command"]),
            )
            grid = button.grid(row=row, column=col, sticky="nw")
            col += 1
            if col >= GCodeApp.NUM_COLS:
                col = 0
                row += 1
            self.buttons.append(button)
            self.buttons.append(grid)

        command_rows = self._command_row_count(row, col)
        self.build_jog_panel(master, command_rows)

        master.grid_rowconfigure(row + 1, weight=1)
        master.grid_columnconfigure(row, weight=1)

        self.textbox = Text(master, wrap="word", width=40, height=30)
        self.textbox.grid(
            row=row + 1,
            column=0,
            rowspan=2,
            columnspan=GCodeApp.NUM_COLS,
            sticky="nsew",
        )

        self.scrollbar = Scrollbar(master, command=self.textbox.yview)
        self.scrollbar.grid(row=row + 1, column=GCodeApp.NUM_COLS, sticky="nse")
        self.textbox.config(yscrollcommand=self.scrollbar.set)

        self.close_button = Button(master, text="Close", command=self.on_close)
        self.close_button.grid(row=row + 3, column=GCodeApp.NUM_COLS)
        master.bind("<Escape>", lambda event=None: self.on_close())

        logger.info("Starting serial worker", port=port, baud=baud)
        self.serial_worker = SerialWorker(port, baud, self.message_queue)
        self.serial_worker.start()

    def schedule_queue_flush(self):
        if not self._queue_active:
            return
        if self._queue_job is not None:
            return
        self._queue_job = self.master.after(50, self.flush_queue)

    def flush_queue(self):
        self._queue_job = None
        try:
            while True:
                message = self.message_queue.get_nowait()
                if message is None:
                    self._queue_active = False
                    return
                self.textbox.insert(END, message + "\n")
                self.textbox.see(END)
                # print(message)
        except Empty:
            pass
        finally:
            if self._queue_active:
                self.schedule_queue_flush()

    def send_gcode(self):
        command = self.entry.get().strip()
        if not command:
            return
        self.send_specific_gcode(command)

    def send_specific_gcode(self, command):
        if not hasattr(self, "serial_worker"):
            logger.warning("Serial worker not initialized; cannot send command")
            return
        self.serial_worker.send(command)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        self._queue_active = False
        if self._queue_job is not None:
            try:
                self.master.after_cancel(self._queue_job)
            except ValueError:
                pass
            self._queue_job = None
        if hasattr(self, "serial_worker"):
            self.serial_worker.shutdown()
        self.master.destroy()

    def get_port(self, args, cfg):
        if args.port is not None:
            port = args.port
        else:
            port = cfg.get("port", "/dev/ttyUSB0")

        if args.baud is not None:
            baud = args.baud
        else:
            baud = cfg.get("baud", 115200)

        return port, baud

    def load_config(self, args):
        attempts = []
        for path in self.config_candidates(args):
            attempts.append(str(path))
            if path and path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    cfg = yaml.safe_load(fh) or {}
                logger.info("Loaded config file", path=str(path))
                return dict(cfg)

        logger.warning("Config file not found, using defaults", attempts=attempts)
        return dict()

    def config_candidates(self, args):
        if getattr(args, "cfg", None):
            yield Path(args.cfg).expanduser()
        yield Path.cwd() / "config.yaml"
        #        yield Path(__file__).with_name("config.yaml")
        yield default_config_path()

    def get_color(self, cmd: dict):
        color = cmd.get("color", "#c0c0c0")
        return color

    def build_jog_panel(self, master, command_rows):
        jog_frame = Frame(
            master,
            padx=6,
            pady=6,
            relief="groove",
            borderwidth=2,
            bg=self.background_color,
        )
        jog_frame.grid(
            row=1,
            column=GCodeApp.NUM_COLS + 1,
            rowspan=max(1, command_rows),
            sticky="n",
            padx=(6, 0),
            pady=(0, 6),
        )

        labels = ["10mm", "1mm", "0.1mm", " ", "0.1mm", "1mm", "10mm"]
        frame = Frame(jog_frame)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for label in labels:
            # TODO: add the label
            pass

        for i, axis in enumerate(["X", "Y", "Z"]):
            frame = Frame(jog_frame)
            frame.grid(row=i + 1, column=0, sticky="ew", pady=(0, 6))
            self._build_horizontal_axis(
                frame,
                axis_label=axis,
                negative_factory=lambda step: partial(
                    self.send_relative_move, moves={axis: -step}
                ),
                positive_factory=lambda step: partial(
                    self.send_relative_move, moves={axis: step}
                ),
            )

    def _build_horizontal_axis(
        self, parent, axis_label, negative_factory, positive_factory
    ):
        # Label(parent, text=f"{axis_label} axis").grid(
        #     row=0, column=0, columnspan=7, pady=(0, 2)
        # )
        left_chars = ["⋘", "≪", "＜", "label", "＞", "≫", "⋙"]
        down_chars = ["⤋", "⇓", "↓", "label", "↑", "⇑", "⤊"]

        left_char_list = down_chars if axis_label == "Z" else left_chars

        levels = list(enumerate(GCodeApp.JOG_STEPS, start=1))
        button_row = 1
        for idx, (level, step) in enumerate(reversed(levels)):
            if left_char_list[idx] == "label":
                Label(parent, text=axis_label).grid(row=button_row, column=idx, padx=4)
            else:
                Button(
                    parent,
                    text=left_char_list[idx],
                    width=1,
                    command=negative_factory(step),
                    bg="#e2e8f0",
                ).grid(row=button_row, column=idx, padx=1, pady=1)

    def send_relative_move(self, moves):
        if not moves:
            return

        coords = " ".join(
            f"{axis}{self.format_distance(distance)}"
            for axis, distance in moves.items()
        )
        self.send_specific_gcode(["M120", "G91", f"G0 {coords}", "M121"])

    def format_distance(self, value):
        formatted = f"{value:.3f}".rstrip("0").rstrip(".")
        return formatted if formatted not in {"-0", "-0."} else "0"

    def _command_row_count(self, row, col):
        if not self.buttons:
            return 1
        if col == 0:
            return max(1, row - 1)
        return row


def default_config_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return base / "gcodeui"


def default_config_path():
    return default_config_dir() / "config.yaml"


def init_config(target: Path):
    template = Path(__file__).with_name("config.yaml")
    if not template.exists():
        raise FileNotFoundError(f"Bundled template not found at {template}")

    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, target)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Launch gcodeui: an app for sending G-code over a serial connection."
    )
    parser.add_argument("-c", "--cfg", type=str, default=None)
    parser.add_argument("-p", "--port", type=str, default=None)
    parser.add_argument("-b", "--baud", type=int, default=None)
    parser.add_argument(
        "--init",
        action="store_true",
        help="Copy the bundled config.yaml into the user configuration directory and exit.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.init:
        target = Path(args.cfg).expanduser() if args.cfg else default_config_path()
        init_config(target)
        print(f"Default configuration written to {target}")
        return

    root = Tk()
    app = GCodeApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
