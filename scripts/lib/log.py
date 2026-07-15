import subprocess
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
    print(f"{ts()} [U-Boot] > {cmd}")
    try:
        out = uboot.cmd(cmd, timeout=timeout)
    except (TimeoutError, _serial.SerialException) as e:
        err(f"U-Boot: {e}")
    for line in _lines(out, cmd):
        print(f"{ts()} [U-Boot] < {line}")
    return out

def subproc(cmd: list[str], label: str) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        clean = _printable(line)
        if clean:
            print(f"{ts()} [{label}] {clean}")
    proc.wait()
    if proc.returncode != 0:
        err(f"{label} exited with code {proc.returncode}")
