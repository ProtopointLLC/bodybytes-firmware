import sys
import time

import serial as _serial

from lib.openocd import OpenOCD
from lib.uboot import UBoot
from lib.config import SERIAL_TIMEOUT


def ts() -> str:
    t = time.time()
    ms = int((t % 1) * 1000)
    return time.strftime(f"[%H:%M:%S.{ms:03d}]")

def _printable(line: str) -> str:
    return "".join(c for c in line if c.isprintable()).strip()

def log(msg: str) -> None:
    print(f"{ts()} [Info] {msg}")

def err(msg: str) -> None:
    for line in msg.splitlines():
        clean = _printable(line)
        if clean:
            print(f"{ts()} [Error] {clean}")
    sys.exit(1)

def _lines(out: str, cmd: str):
    for line in out.splitlines():
        clean = _printable(line)
        if clean and clean != cmd:
            yield clean

def oc(openocd: OpenOCD, cmd: str, timeout: float = 300) -> str:
    print(f"{ts()} [OpenOCD] > {cmd}")
    try:
        out = openocd.cmd(cmd, timeout=timeout)
    except (TimeoutError, ConnectionError, OSError) as e:
        err(f"OpenOCD: {e}")
    for line in _lines(out, cmd):
        print(f"{ts()} [OpenOCD] < {line}")
    return out

def ub(uboot: UBoot, cmd: str, timeout: float = SERIAL_TIMEOUT) -> str:
    print(f"{ts()} [U-Boot] > {cmd}", flush=True)
    def on_line(line: str) -> None:
        clean = _printable(line)
        if clean and clean != cmd:
            print(f"{ts()} [U-Boot] < {clean}", flush=True)
    try:
        return uboot.cmd(cmd, timeout=timeout, on_line=on_line)
    except (TimeoutError, _serial.SerialException) as e:
        err(f"U-Boot: {e}")

