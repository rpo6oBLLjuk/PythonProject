# utils/logger.py
import time
import traceback
from datetime import datetime

class Logger:
    def __init__(self, console=False):
        self.console = console
        self.start_time = time.time()
        self.messages = []

    def _format(self, level, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message}"
        self.messages.append(line)
        if self.console:
            print(line)
        return line

    def info(self, message):
        return self._format("INFO", message)

    def warning(self, message):
        return self._format("WARNING", message)

    def error(self, message, exc=None):
        line = self._format("ERROR", message)
        if exc:
            tb = traceback.format_exc()
            self.messages.append(tb)
            if self.console:
                print(tb)
        return line

    def success(self, message):
        return self._format("SUCCESS", message)

    def elapsed(self):
        return f"{time.time() - self.start_time:.2f} сек"

    def get_logs(self):
        return "\n".join(self.messages)
