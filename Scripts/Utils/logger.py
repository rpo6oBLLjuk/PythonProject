# utils/logger.py
import os
import time
import traceback
from datetime import datetime


class Logger:
    def __init__(self, logs_dir, console=False):
        self.logs_dir = logs_dir
        self.console = console
        self.start_time = time.time()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(logs_dir, f"pdf_processing_{timestamp}.log")

    def _write(self, level, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message}"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        if self.console:
            print(line)

    def info(self, message):
        self._write("INFO", message)

    def warning(self, message):
        self._write("WARNING", message)

    def error(self, message, exc=None):
        self._write("ERROR", message)
        if exc:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")

    def success(self, message):
        self._write("SUCCESS", message)

    def elapsed(self):
        return f"{time.time() - self.start_time:.2f} сек"
