import re
import time
from typing import Callable

import serial


class UBoot:
    PROMPT = b"=> "

    def __init__(self, port: str, baud: int):
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
        seen = buf.decode("utf-8", "replace").strip() if buf else "(nothing received)"
        raise TimeoutError(
            f"U-Boot: autoboot interrupt timed out after {timeout:.0f}s; "
            f"UART said: {seen!r}")

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

    def set_baud(self, baud: int, timeout: float = 5.0) -> None:
        """
        Switch U-Boot's console baud rate live via `setenv baudrate`, then
        follow it on this end. Typed at a live `=> ` prompt, this always
        takes the *interactive* path in drivers/serial/serial.c - U-Boot
        can't tell this script apart from a human - which prints "press
        ENTER ..." and then genuinely blocks in `getchar() == '\\r'` at the
        new rate before it prints "=> " again. So after reprogramming our
        own end, send a bare CR (not sync()'s '\\n') to satisfy that wait.
        """
        if self._ser.baudrate == baud:
            return
        self._ser.write(f"setenv baudrate {baud}\n".encode())
        self._ser.flush()  # tcdrain(): block until sent at the OLD baud
        time.sleep(0.1)    # let U-Boot's env callback (udelay(50000)) land
        self._ser.baudrate = baud
        self._ser.reset_input_buffer()
        self._ser.write(b"\r")  # satisfy the "press ENTER" wait at the NEW baud
        self._ser.flush()
        if not self.sync(timeout=timeout):
            raise TimeoutError(f"U-Boot: no prompt at {baud} baud after switching")

    def loady(self, addr: int, data: bytes, name: str = "image.bin",
              progress: Callable[[int, int], None] | None = None,
              timeout: float = 30.0) -> str:
        """
        Load `data` into DRAM at `addr` over YMODEM, using U-Boot's `loady`.

        Needs nothing but a live => prompt - no JTAG. Returns the command
        output after the transfer, which carries the "## Total Size" line.
        """
        from . import ymodem

        self._ser.reset_input_buffer()
        self._ser.write(f"loady {addr:#x}\n".encode())

        # Wait for the receiver to start offering 'C'. Reading it here would
        # steal it from the sender, so only look for the banner and let
        # ymodem.send() consume the 'C' itself.
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b"Ready for binary" in buf:
                    break
        else:
            raise TimeoutError(
                f"U-Boot: no loady banner after {timeout:.0f}s "
                f"(is CONFIG_CMD_LOADB enabled?)")

        ymodem.send(self._ser, data, name=name, progress=progress)

        # loady prints "## Total Size = ..." and returns to the prompt.
        return self._read_until_prompt(timeout=timeout)

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
