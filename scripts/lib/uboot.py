import time

import serial


class UBoot:
    PROMPT = b"=> "

    def __init__(self, port: str, baud: int = 115200):
        self._ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(0.2)
        self._ser.reset_input_buffer()

    def sync(self, timeout: float = 5.0) -> bool:
        """Send a blank line and confirm the => prompt appears."""
        self._ser.write(b"\n")
        try:
            self._read_until_prompt(timeout=timeout)
            return True
        except TimeoutError:
            return False

    def cmd(self, command: str, timeout: float = 120.0) -> str:
        self._ser.write(command.encode() + b"\n")
        return self._read_until_prompt(timeout=timeout)

    def _read_until_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if buf.endswith(self.PROMPT):
                    return buf[: -len(self.PROMPT)].decode(errors="replace").strip()
        raise TimeoutError(f"U-Boot: no prompt after {timeout:.0f}s")

    def close(self):
        try:
            self._ser.close()
        except Exception:
            pass
