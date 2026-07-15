#!/usr/bin/env python3
"""
Flash NOR partitions to bodybytes via OpenOCD + U-Boot serial console.

Prerequisites:
  1. OpenOCD running with bodybytes U-Boot active at the => prompt
     (see docs/flashing.md §4a for JTAG RAM-boot procedure)
  2. build/ blobs generated: scripts/generate_nor_image.py <MAC>
  3. pyserial installed: pip install pyserial

Usage:
  flash_nor_images.py --all --port /dev/ttyUSB0
  flash_nor_images.py --u-boot --recovery --port /dev/ttyUSB0
  flash_nor_images.py --u-boot-env --factory --port /dev/ttyUSB0

The W25Q512JV uses native 4-byte addressing (entered via 0xB7 on sf probe);
no BAR (Bank Address Register) handling is needed.
"""

import argparse
import re
import socket
import sys
import tempfile
import time
from pathlib import Path

import fdt
import serial

REPO = Path(__file__).resolve().parent.parent

SECT_SIZE = 0x1_0000    # 64 KB erase sector (W25Q512JV block size)
RAM_ADDR  = 0x8000_0000  # DRAM staging address

DTS_FILE = REPO / "u-boot/arch/mips/dts/bodybytes,bodybytes.dts"

# DTS partition label → (binary path, erase full partition?)
# erase_full=True  → erase the entire DTS partition size before writing
# erase_full=False → erase only as much as the binary needs (rounded up to sector)
_PARTITION_CONFIG = {
    "u-boot":     (REPO / "u-boot/u-boot-with-spl.bin",                                                                                        True),
    "u-boot-env": (REPO / "build/bodybytes_nor_uboot_env.bin",                                                                                True),
    "factory":    (REPO / "build/bodybytes_nor_wifi_factory.bin",                                                                              True),
    "recovery":   (REPO / "openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin", False),
}

ORDERED = list(_PARTITION_CONFIG)


def _build_partitions() -> dict[str, dict]:
    if not DTS_FILE.exists():
        sys.exit(f"DTS not found: {DTS_FILE}")
    text = re.sub(r'^\s*#.*$', '', DTS_FILE.read_text(), flags=re.MULTILINE)
    dts = {
        node.get_property('label').value: tuple(node.get_property('reg').value[:2])
        for _, node in fdt.parse_dts(text)
        if node.get_property('label') is not None and node.get_property('reg') is not None
    }
    def resolve(label, binary, erase_full):
        if label not in dts:
            sys.exit(f"Partition '{label}' not found in {DTS_FILE}")
        offset, size = dts[label]
        return {"binary": binary, "offset": offset, "erase": size if erase_full else None}
    return {label: resolve(label, binary, erase_full)
            for label, (binary, erase_full) in _PARTITION_CONFIG.items()}


PARTITIONS = _build_partitions()


# ── OpenOCD telnet client ────────────────────────────────────────────────────

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


# ── U-Boot serial console client ─────────────────────────────────────────────

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


# ── flash logic ───────────────────────────────────────────────────────────────

def flash_partition(openocd: OpenOCD, uboot: UBoot,
                    label: str, binary: Path,
                    flash_offset: int, erase_size: int | None) -> None:
    data = binary.read_bytes()

    if erase_size is None:
        erase_size = (len(data) + SECT_SIZE - 1) & ~(SECT_SIZE - 1)

    if len(data) > erase_size:
        sys.exit(f"[{label}] binary ({len(data):#x} B) exceeds erase region ({erase_size:#x} B)")

    print(f"\n── {label} ──")
    print(f"   binary : {binary.name}  ({len(data):#x} bytes)")
    print(f"   NOR    : offset {flash_offset:#x}, erase {erase_size:#x}")

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
    try:
        print(f"   load → DRAM {RAM_ADDR:#010x} ... ", end="", flush=True)
        openocd.cmd("halt", timeout=10)
        openocd.cmd(f"load_image {tmp} {RAM_ADDR:#x} bin", timeout=180)
        openocd.cmd("resume", timeout=10)
        print("ok")
    finally:
        tmp.unlink(missing_ok=True)

    uboot.sync(timeout=5)

    print(f"   sf probe ... ", end="", flush=True)
    out = uboot.cmd("sf probe", timeout=10)
    if "Detected" not in out:
        sys.exit(f"\nsf probe failed:\n{out}")
    for line in out.splitlines():
        if "Detected" in line or "SF:" in line:
            print(line.strip())
            break

    print(f"   sf erase {flash_offset:#x} {erase_size:#x} ... ", end="", flush=True)
    out = uboot.cmd(f"sf erase {flash_offset:#x} {erase_size:#x}", timeout=120)
    if "OK" not in out:
        sys.exit(f"\nsf erase failed:\n{out}")
    print("ok")

    print(f"   sf write {RAM_ADDR:#x} {flash_offset:#x} {len(data):#x} ... ",
          end="", flush=True)
    out = uboot.cmd(f"sf write {RAM_ADDR:#x} {flash_offset:#x} {len(data):#x}",
                    timeout=180)
    if "OK" not in out:
        sys.exit(f"\nsf write failed:\n{out}")
    print("ok")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", required=True, metavar="DEV",
                   help="U-Boot serial port (e.g. /dev/ttyUSB0)")
    p.add_argument("--baud", type=int, default=115200,
                   help="serial baud rate (default: 115200)")
    p.add_argument("--openocd-host", default="localhost", metavar="HOST")
    p.add_argument("--openocd-port", type=int, default=4444, metavar="PORT")

    sel = p.add_argument_group("partition selection (at least one required)")
    sel.add_argument("--all",         action="store_true", help="flash all partitions")
    sel.add_argument("--u-boot",      action="store_true", help="flash u-boot-with-spl.bin")
    sel.add_argument("--u-boot-env",  action="store_true", help="flash U-Boot env partition")
    sel.add_argument("--factory",     action="store_true", help="flash WiFi EEPROM factory blob")
    sel.add_argument("--recovery",    action="store_true", help="flash OpenWrt recovery kernel")
    args = p.parse_args()

    if args.all:
        args.u_boot = args.u_boot_env = args.factory = args.recovery = True

    selected = [k for k in ORDERED if getattr(args, k.replace("-", "_"))]
    if not selected:
        p.error("select at least one partition: --u-boot / --u-boot-env / --factory / --recovery / --all")

    for name in selected:
        part = PARTITIONS[name]
        if not part["binary"].exists():
            sys.exit(f"file not found: {part['binary']}")

    print(f"Connecting to OpenOCD {args.openocd_host}:{args.openocd_port} ...")
    try:
        openocd = OpenOCD(args.openocd_host, args.openocd_port)
    except (ConnectionRefusedError, OSError) as e:
        sys.exit(f"Cannot connect to OpenOCD: {e}")
    print("Connected.")

    print(f"Opening serial {args.port} @ {args.baud} baud ...")
    try:
        uboot = UBoot(args.port, args.baud)
    except serial.SerialException as e:
        openocd.close()
        sys.exit(f"Cannot open serial port: {e}")

    if not uboot.sync(timeout=5):
        openocd.close()
        uboot.close()
        sys.exit("No U-Boot prompt on serial port — is U-Boot running at the => prompt?")
    print("U-Boot prompt confirmed.\n")

    try:
        for name in selected:
            part = PARTITIONS[name]
            flash_partition(
                openocd, uboot,
                label=name,
                binary=part["binary"],
                flash_offset=part["offset"],
                erase_size=part["erase"],
            )
    finally:
        openocd.close()
        uboot.close()

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
