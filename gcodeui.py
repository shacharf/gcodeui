import argparse
import threading
import time
from functools import partial
from pathlib import Path

import serial
import structlog
import yaml
from addict import Dict
from tkinter import END, Button, Entry, Label, Scrollbar, Text, Tk


logger = structlog.get_logger()


class GCodeApp:
    NUM_COLS = 4
    FG = "#ffffff"

    def __init__(self, master, args):
        cfg = self.load_config(args)
        port, baud = self.get_port(args, cfg)

        self.master = master
        master.title("G-code Sender")

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

        master.grid_rowconfigure(row + 1, weight=1)
        master.grid_columnconfigure(row, weight=1)

        self.textbox = Text(master, wrap="word", width=40, height=30)
        # self.textbox.grid(row=row + 1, column=0, sticky='nsew')
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

        self.close_button = Button(master, text="Close", command=master.quit)
        self.close_button.grid(row=row + 3, column=GCodeApp.NUM_COLS)
        master.bind("<Escape>", lambda event=None: master.quit())

        logger.info(f"Initializing serial port {port} : {baud}")
        self.ser = serial.Serial(port, baud, timeout=1)
        self.ser.flush()

        self.read_thread = threading.Thread(target=self.read_from_serial)
        self.read_thread.daemon = True  # Daemon threads exit when the program exits
        self.read_thread.start()

    def send_gcode(self):
        command = self.entry.get()
        self.send_specific_gcode(command)

    def lprint(self, line):
        self.textbox.insert(END, line + "\n")
        self.textbox.see(END)
        print(line)

    def send_specific_gcode(self, command):
        if isinstance(command, str):
            self.ser.write((command + "\n").encode())
            self.lprint(f"Sent: {command}")
        elif isinstance(command, list):
            for cmd_i in command:
                self.ser.write((cmd_i + "\n").encode())
                self.lprint(f"Sent: {cmd_i}")
                time.sleep(0.1)  # Not sure it is required

    def read_from_serial(self):
        while True:
            if self.ser.in_waiting > 0:
                response = self.ser.readline().decode().strip()
                if response:
                    self.lprint(f"Received: {response}")

    def get_port(self, args, cfg):
        port = "/dev/ttyUSB0"
        baud = 115200
        if args.port is not None:
            port = args.port
        else:
            cfg_port = cfg.get("port")
            if cfg_port is not None:
                port = cfg_port

        if args.baud is not None:
            baud = args.baud
        else:
            cfg_baud = cfg.get("baud")
            if cfg_baud is not None:
                baud = cfg_baud

        return port, baud

    def load_config(self, args):
        attempts = []
        for path in self.config_candidates(args):
            attempts.append(str(path))
            if path and path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    cfg = yaml.safe_load(fh) or {}
                logger.info("Loaded config file", path=str(path))
                return Dict(cfg)

        logger.warning("Config file not found, using defaults", attempts=attempts)
        return Dict()

    def config_candidates(self, args):
        if getattr(args, "cfg", None):
            yield Path(args.cfg).expanduser()
        yield Path.cwd() / "config.yaml"
        yield Path(__file__).with_name("config.yaml")
        yield Path.home() / ".config" / "gcodeui" / "config.yaml"

    def get_color(self, cmd: dict):
        color = cmd.get("color", "#c0c0c0")
        return color


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cfg", type=str, default=None)
    parser.add_argument("-p", "--port", type=str, default=None)
    parser.add_argument("-b", "--baud", type=int, default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Tk()
    app = GCodeApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
