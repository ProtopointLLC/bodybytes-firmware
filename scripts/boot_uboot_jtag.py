#!/usr/bin/env python3
"""
Initialise MT7628 DRAM via JTAG and boot U-Boot from RAM.

Run this once to bring the board up from a cold/blank state.
Afterwards U-Boot is running at the => prompt and flash_nor_images.py can be used.

Prerequisites:
  OpenOCD running and connected to the MT7628 JTAG port.

Usage:
  boot_uboot_jtag.py
  boot_uboot_jtag.py --openocd-host localhost --openocd-port 4444
"""

import time

from lib.openocd import OpenOCD
from lib.log import log, err, oc as _oc
from lib.config import (
    OPENOCD_HOST, OPENOCD_PORT,
    UBOOT_RAM_BIN, UBOOT_RAM_ADDR,
    CHIP_ID_ADDR, CHIP_ID_MAGIC, DRAM_SIZE_MB, STAGING_ADDR,
)


def _mdw(openocd: OpenOCD, addr: int) -> int:
    out = _oc(openocd, f"mdw {addr:#x}", timeout=5)
    try:
        return int(out.split(":")[-1].strip(), 16)
    except (IndexError, ValueError):
        err(f"mdw {addr:#x}: unexpected response: {out!r}")


def jtag_ram_boot(openocd: OpenOCD) -> None:
    _oc(openocd, "halt", timeout=10)

    out = _oc(openocd, "reg pc", timeout=5)
    try:
        pc = int(out.split(":")[-1].strip(), 16)
    except (IndexError, ValueError):
        err(f"reg pc: unexpected response: {out!r}")
    if pc != 0x9c000000:
        log(f"warning: PC = {pc:#010x} (expected 0x9c000000 at reset vector)")
    else:
        log(f"PC = {pc:#010x} (reset vector ok)")

    chip_id = _mdw(openocd, CHIP_ID_ADDR)
    if chip_id != CHIP_ID_MAGIC:
        err(f"chip ID {chip_id:#010x} != {CHIP_ID_MAGIC:#010x} (not MT7628?)")
    log(f"chip ID = {chip_id:#010x} (MT7628 ok)")

    _oc(openocd, "cpu_pll_init", timeout=10)
    _oc(openocd, "adapter speed 1000", timeout=5)

    _oc(openocd, f"dram_init {DRAM_SIZE_MB}", timeout=60)
    _oc(openocd,
        "mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0",
        timeout=5)

    _oc(openocd, f"mww {STAGING_ADDR:#x} 0xdeadbeef", timeout=5)
    got = _mdw(openocd, STAGING_ADDR)
    if got != 0xdeadbeef:
        err(f"DRAM test failed: wrote 0xdeadbeef, read back {got:#010x}")
    log(f"DRAM test passed: {got:#010x}")

    if not UBOOT_RAM_BIN.exists():
        err(f"not found: {UBOOT_RAM_BIN} (build U-Boot first)")
    out = _oc(openocd, f"load_image {UBOOT_RAM_BIN} {UBOOT_RAM_ADDR:#x} bin")
    if "bytes written" not in out:
        err(f"load_image failed:\n{out}")

    _oc(openocd, f"reg pc {UBOOT_RAM_ADDR:#x}", timeout=5)
    _oc(openocd, "resume", timeout=5)
    log(f"Resumed at {UBOOT_RAM_ADDR:#010x}, waiting 5 s for U-Boot prompt")
    time.sleep(5)


def main():
    log(f"Connecting to OpenOCD {OPENOCD_HOST}:{OPENOCD_PORT}")
    try:
        openocd = OpenOCD(OPENOCD_HOST, OPENOCD_PORT)
    except (ConnectionRefusedError, OSError) as e:
        err(f"Cannot connect to OpenOCD: {e}")
    log("OpenOCD connected")

    try:
        jtag_ram_boot(openocd)
    finally:
        openocd.close()

    log("U-Boot is running — you can now run flash_nor_images.py")


if __name__ == "__main__":
    main()
