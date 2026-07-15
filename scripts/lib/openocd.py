import socket
import time


class OpenOCD:
    PROMPT = b"> "

    def __init__(self, host: str = "localhost", port: int = 4444):
        self._sock = socket.create_connection((host, port), timeout=10)
        self._buf = b""
        self._drain(timeout=10)

    def cmd(self, command: str, timeout: float = 300) -> str:
        self._sock.sendall(command.encode() + b"\n")
        return self._drain(timeout=timeout)

    def _drain(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
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
        result, self._buf = self._buf[: -len(self.PROMPT)], b""
        return result.decode(errors="replace").strip()

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass
