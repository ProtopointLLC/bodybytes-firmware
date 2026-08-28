import socket
import time
from typing import Callable


class OpenOCD:
    PROMPT = b"> "

    def __init__(self, host: str = "localhost", port: int = 4444):
        self._sock = socket.create_connection((host, port), timeout=10)
        self._buf = b""
        self._drain(timeout=10)

    def cmd(self, command: str, timeout: float = 300,
            on_line: Callable[[str], None] | None = None) -> str:
        self._sock.sendall(command.encode() + b"\n")
        return self._drain(timeout=timeout, on_line=on_line)

    def _drain(self, timeout: float,
               on_line: Callable[[str], None] | None = None) -> str:
        deadline = time.monotonic() + timeout
        emitted = 0
        while not self._buf.endswith(self.PROMPT):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("OpenOCD: timed out waiting for prompt")
            self._sock.settimeout(min(remaining, 2.0))
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("OpenOCD: connection closed")
            self._buf += chunk

            # Long commands (PRACC writes run for minutes) must report as they
            # go, not in one burst once the prompt returns.
            while on_line:
                nl = self._buf.find(b"\n", emitted)
                if nl < 0:
                    break
                on_line(self._buf[emitted:nl].decode(errors="replace"))
                emitted = nl + 1

        result, self._buf = self._buf[: -len(self.PROMPT)], b""

        # The last line often arrives with no trailing newline, directly
        # followed by the prompt; emit whatever the loop above left behind.
        if on_line and emitted < len(result):
            tail = result[emitted:].decode(errors="replace")
            if tail.strip():
                on_line(tail)

        return result.decode(errors="replace").strip()

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass
