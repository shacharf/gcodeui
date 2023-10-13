import os
import serial
from tkinter import Tk, Label, Button, Entry, Text, Scrollbar, END
from addict import Dict
import argparse
from functools import partial
import structlog
import threading
import time
import yaml


logger = structlog.get_logger()


class GCodeApp:
    NUM_COLS = 4

    def __init__(self, master, args):
        cfg = self.load_config(args)
        port, baud = self.get_port(args, cfg)

        self.master = master
        master.title("G-code Sender")

        self.label = Label(master, text="Enter G-code:")
        self.label.grid(row=0, column=0, sticky="nw")

        self.entry = Entry(master)
        self.entry.grid(row=0, column=1, columnspan=2, sticky='new')
        self.entry.bind("<Return>", lambda event: self.send_gcode())

        self.send_button = Button(master, text="Send", command=self.send_gcode)
        self.send_button.grid(row=0, column=4)

        row = 1
        col = 0
        self.buttons = []
        for cmd in cfg.commands:
            button = Button(
                master,
                text=cmd["title"],
                bg=self.get_color(cmd),
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

        self.textbox = Text(master, wrap='word', width=40, height=30)
        # self.textbox.grid(row=row + 1, column=0, sticky='nsew')
        self.textbox.grid(row=row + 1, column=0, rowspan=2, columnspan=GCodeApp.NUM_COLS, sticky='nsew')

        self.scrollbar = Scrollbar(master, command=self.textbox.yview)
        self.scrollbar.grid(row=row + 1, column=GCodeApp.NUM_COLS, sticky='nse')
        self.textbox.config(yscrollcommand=self.scrollbar.set)

        self.close_button = Button(master, text="Close", command=master.quit)
        self.close_button.grid(row=row + 3, column=GCodeApp.NUM_COLS )
        master.bind("<Escape>", lambda event=None: root.quit())

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
                self.print(f"Sent: {cmd_i}")
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
        elif cfg.port is not None:
            port = cfg.port

        if args.baud is not None:
            baud = args.baud
        if cfg.baud is not None:
            baud = cfg.baud

        return port, baud

    def load_config(self, args):
        if os.path.exists(args.cfg):
            cfg = yaml.safe_load(open(args.cfg))
            return Dict(cfg)
        else:
            return Dict()
        
    def get_color(self, cmd: dict):
        color = cmd.get("color", "#c0c0c0")
        return color


parser = argparse.ArgumentParser()
parser.add_argument("-c", "--cfg", type=str, default="config.yaml")
parser.add_argument("-p", "--port", type=str, default=None)
parser.add_argument("-b", "--baud", type=int, default=None)
args = parser.parse_args()


root = Tk()
app = GCodeApp(root, args)
root.mainloop()
