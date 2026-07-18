import re
import time
from typing import Callable

import serial


class UBoot:
    PROMPT = b"=> "

    def __init__(self, port: str, baud: int = 115200):
        self._ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(0.2)
        self._ser.reset_input_buffer()

    def interrupt_autoboot(self, timeout: float = 10.0) -> None:
        """Send ESC repeatedly to exit the autoboot menu and land at the => prompt."""
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            self._ser.write(b"\x1b")
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if self.PROMPT in buf:
                    return
            time.sleep(0.05)
        raise TimeoutError(f"U-Boot: autoboot interrupt timed out after {timeout:.0f}s")

    def sync(self, timeout: float = 5.0) -> bool:
        """Send a blank line and confirm the => prompt appears."""
        self._ser.write(b"\n")
        try:
            self._read_until_prompt(timeout=timeout)
            return True
        except TimeoutError:
            return False

    def cmd(self, command: str, timeout: float = 120.0,
            on_line: Callable[[str], None] | None = None) -> str:
        self._ser.write(command.encode() + b"\n")
        return self._read_until_prompt(timeout=timeout, on_line=on_line)

    def _read_until_prompt(self, timeout: float,
                           on_line: Callable[[str], None] | None = None) -> str:
        deadline = time.monotonic() + timeout
        buf = b""
        pending = b""
        while time.monotonic() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if on_line:
                    pending += chunk
                    parts = re.split(rb'\r\n|\r|\n', pending)
                    pending = parts[-1]
                    for line in parts[:-1]:
                        text = line.decode(errors="replace").strip()
                        if text:
                            on_line(text)
                if buf.endswith(self.PROMPT):
                    return buf[: -len(self.PROMPT)].decode(errors="replace").strip()
        raise TimeoutError(f"U-Boot: no prompt after {timeout:.0f}s")

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass
