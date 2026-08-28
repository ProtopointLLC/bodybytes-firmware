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
            on_line: Callable[[str], None] | None = None,
            idle_timeout: float | None = None) -> str:
        """
        Run `command` and return its output.

        `timeout` bounds the whole command. `idle_timeout`, when given, bounds
        the gap between output instead, and is the right control for anything
        long: a PRACC write of a few hundred KiB takes 3.5 minutes on a native
        adapter and the better part of an hour through a VM's USB passthrough,
        but reports progress every couple of seconds either way. Bounding
        silence rather than duration tolerates any transfer rate while still
        failing on a wedged target.
        """
        self._sock.sendall(command.encode() + b"\n")
        return self._drain(timeout=timeout, on_line=on_line,
                           idle_timeout=idle_timeout)

    def _drain(self, timeout: float,
               on_line: Callable[[str], None] | None = None,
               idle_timeout: float | None = None) -> str:
        hard_deadline = time.monotonic() + timeout
        idle_deadline = (time.monotonic() + idle_timeout
                         if idle_timeout is not None else None)
        emitted = 0
        while not self._buf.endswith(self.PROMPT):
            now = time.monotonic()
            remaining = hard_deadline - now
            if remaining <= 0:
                raise TimeoutError(
                    f"OpenOCD: no prompt after {timeout:.0f}s")
            if idle_deadline is not None:
                idle_left = idle_deadline - now
                if idle_left <= 0:
                    raise TimeoutError(
                        f"OpenOCD: silent for {idle_timeout:.0f}s "
                        f"waiting for prompt")
                remaining = min(remaining, idle_left)
            self._sock.settimeout(min(remaining, 2.0))
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("OpenOCD: connection closed")
            self._buf += chunk
            if idle_timeout is not None:
                idle_deadline = time.monotonic() + idle_timeout

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
