#!/usr/bin/env python3
"""
Hardware validation - DRAM, NOR flash, and eMMC functional test.

Expects U-Boot already running at the => prompt (use boot_uboot_jtag.py first).
Connects via serial, issues diagnostic U-Boot commands, and verifies measured
values against the selected board profile in scripts/config.ini.

The NOR test is split into a non-destructive probe (always runs) and a
full erase/write/verify cycle (--destructive only).  The destructive test
erases the entire NOR chip; reprogram with flash_nor_images.py afterwards.

Usage:
  test_hardware.py --bodybytes --all
  test_hardware.py --bodybytes --dram --mmc
  test_hardware.py --bodybytes --sf --destructive
  test_hardware.py --vocore2 --all
"""

import argparse
import re

import serial

from lib.uboot import UBoot
from lib.log import log, err, ub as _ub
from lib.config import (
    SERIAL_PORT, SERIAL_BAUD,
    BOARD_NAMES, load_board, BoardConfig,
)


def _test_dram(uboot: UBoot, board: BoardConfig) -> None:
    out = _ub(uboot, "meminfo", timeout=10)
    m = re.search(r'DRAM:\s+(\d+)\s+MiB', out)
    if not m:
        err(f"meminfo: cannot parse DRAM size:\n{out}")
    detected_mb = int(m.group(1))
    if detected_mb != board.dram_size_mb:
        err(f"DRAM size mismatch: detected {detected_mb} MiB, expected {board.dram_size_mb} MiB")
    log(f"DRAM size: {detected_mb} MiB - ok")

    out = _ub(uboot, "meminfo map", timeout=10)
    m = re.search(r'^\s*free\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)',
                  out, re.MULTILINE | re.IGNORECASE)
    if not m:
        err(f"meminfo map: cannot find free region:\n{out}")
    free_base = int(m.group(1), 16)
    free_end  = int(m.group(2), 16)
    if free_end <= free_base:
        err(f"meminfo map: free region is empty ({free_base:#x}–{free_end:#x})")
    free_mib = (free_end - free_base) // (1024 * 1024)
    log(f"Free region: {free_base:#010x}–{free_end:#010x} ({free_mib} MiB)")

    out = _ub(uboot, f"mtest {free_base:#x} {free_end:#x} 0 1", timeout=120)
    if "FAILURE" in out.upper():
        err(f"mtest: DRAM failure detected:\n{out}")
    if not out.strip():
        err("mtest: no output received")
    log("mtest: passed")


def _test_nor(uboot: UBoot, board: BoardConfig, destructive: bool) -> None:
    out = _ub(uboot, "sf probe", timeout=15)
    if "Detected" not in out:
        err(f"sf probe: no chip detected:\n{out}")

    detected_line = next((l for l in out.splitlines() if "Detected" in l), "").strip()
    log(f"sf probe: {detected_line}")

    if board.nor_chip_name.lower() not in out.lower():
        err(f"NOR chip mismatch: expected {board.nor_chip_name}, got: {detected_line}")

    m = re.search(r'total\s+(\d+)\s+(MiB|KiB)', out)
    if not m:
        err(f"sf probe: cannot parse total size:\n{out}")
    val, unit = int(m.group(1)), m.group(2)
    detected_size = val * (1024 * 1024 if unit == "MiB" else 1024)
    if detected_size != board.nor_size:
        err(f"NOR size mismatch: detected {detected_size // (1024 * 1024)} MiB, "
            f"expected {board.nor_size // (1024 * 1024)} MiB")
    log(f"NOR: {board.nor_chip_name} {board.nor_size // (1024 * 1024)} MiB - ok")

    if not destructive:
        log("Skipping sf test (--destructive not set)")
        return

    nor_mb = board.nor_size // (1024 * 1024)
    log(f"sf test: erase/write/verify entire chip ({nor_mb} MiB) - takes several minutes")
    out = _ub(uboot, f"sf test 0x0 {board.nor_size:#x}", timeout=600)
    for phase in ("Erase: OK", "Check Erase: OK", "Fill: OK", "Verify: OK"):
        if phase not in out:
            err(f"sf test: phase '{phase}' not found in output:\n{out}")
    log("sf test: all phases passed")


def _test_emmc(uboot: UBoot, board: BoardConfig) -> None:
    out = _ub(uboot, "mmc dev 0", timeout=10)
    if "is current device" not in out:
        err(f"mmc dev 0: device not found:\n{out}")
    log("mmc dev 0: ok")

    _ub(uboot, "mmc rescan", timeout=15)

    out = _ub(uboot, "mmc info", timeout=10)
    if "Capacity" not in out:
        err(f"mmc info: unexpected output:\n{out}")

    m = re.search(r'Capacity:\s+([\d.]+)\s+(GiB|MiB)', out)
    if not m:
        err(f"mmc info: cannot parse capacity:\n{out}")
    cap_val  = float(m.group(1))
    cap_unit = m.group(2)
    cap_gib  = cap_val if cap_unit == "GiB" else cap_val / 1024.0

    # Convert nominal SI GB to GiB for comparison against mmc info output.
    # 10% tolerance covers the SI→binary gap (~7%) and eMMC over-provisioning.
    expected_gib = board.emmc_capacity_gb * 1e9 / (1024 ** 3)
    tolerance    = expected_gib * 0.10
    if abs(cap_gib - expected_gib) > tolerance:
        err(f"eMMC capacity mismatch: detected {cap_gib:.1f} GiB, "
            f"expected ~{expected_gib:.1f} GiB (nominal {board.emmc_capacity_gb} GB ±10%)")
    log(f"eMMC capacity: {cap_gib:.1f} GiB (nominal {board.emmc_capacity_gb} GB) - ok")

    m = re.search(r'Bus Speed:\s+(\d+)', out)
    if m:
        log(f"eMMC bus speed: {int(m.group(1)) // 1_000_000} MHz")

    m = re.search(r'Mode:\s+(.+)', out)
    if m:
        log(f"eMMC mode: {m.group(1).strip()}")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    board_grp = p.add_mutually_exclusive_group(required=True)
    for name in BOARD_NAMES:
        board_grp.add_argument(f"--{name}", dest="board", action="store_const", const=name,
                               help=f"target board: {name}")

    sel = p.add_argument_group("test selection (at least one required)")
    sel.add_argument("--all",  action="store_true", help="run all tests")
    sel.add_argument("--dram", action="store_true", help="DRAM size + mtest")
    sel.add_argument("--sf",   action="store_true", help="NOR flash probe (and erase/write/verify with --destructive)")
    sel.add_argument("--mmc",  action="store_true", help="eMMC detect + capacity check")

    p.add_argument(
        "--destructive", action="store_true",
        help="with --sf: full erase/write/verify of entire NOR chip (reflash required afterwards)",
    )
    args = p.parse_args()

    if args.all:
        args.dram = args.sf = args.mmc = True

    if not (args.dram or args.sf or args.mmc):
        p.error("select at least one test: --dram / --sf / --mmc / --all")

    if args.destructive and not args.sf:
        p.error("--destructive requires --sf")

    board = load_board(args.board)
    log(f"Board: {board.name}  DRAM: {board.dram_size_mb} MiB  "
        f"NOR: {board.nor_size // (1024 * 1024)} MiB ({board.nor_chip_name})  "
        f"eMMC: {board.emmc_capacity_gb} GB")
    if args.destructive:
        log("WARNING: --destructive enabled - NOR will be fully erased")

    log(f"Connecting to U-Boot via {SERIAL_PORT} at {SERIAL_BAUD} baud")
    try:
        uboot = UBoot(SERIAL_PORT, SERIAL_BAUD)
    except serial.SerialException as e:
        err(f"Cannot open serial port: {e}")

    if not uboot.sync(timeout=5):
        err("No U-Boot prompt - run boot_uboot_jtag.py first")
    log("U-Boot prompt confirmed")

    try:
        if args.dram:
            log("--- DRAM ---")
            _test_dram(uboot, board)

        if args.sf:
            log("--- NOR ---")
            _test_nor(uboot, board, args.destructive)

        if args.mmc:
            log("--- eMMC ---")
            _test_emmc(uboot, board)
    finally:
        uboot.close()

    log("All selected tests passed")


if __name__ == "__main__":
    main()
