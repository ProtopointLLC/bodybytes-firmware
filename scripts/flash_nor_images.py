#!/usr/bin/env python3
"""
Flash NOR partitions to bodybytes.

Two strategies (select with --jtag / --file):
  --jtag   Load via JTAG into RAM, write via U-Boot sf commands (default)
  --file   Assemble full NOR image and write to build/ (implies --all)
           Then program manually: flashrom -p <prog> -c <chip> -w build/bodybytes_nor_image.bin

Prerequisites (JTAG):
  1. U-Boot running at the => prompt (use boot_uboot_jtag.py to bring up a blank board)
  2. build/ blobs generated: scripts/generate_nor_env_wifi_images.py

Usage:
  flash_nor_images.py --full-erase         # JTAG: erase entire chip only
  flash_nor_images.py --all                # JTAG: flash all partitions (incremental)
  flash_nor_images.py --file               # assemble full image to build/

Connection settings are read from scripts/config.ini.
"""

import argparse
import zlib
from pathlib import Path

import serial

from lib.openocd import OpenOCD
from lib.uboot import UBoot
from lib.log import log, err, oc as _oc, ub as _ub
from lib.config import (
    OPENOCD_HOST, OPENOCD_PORT,
    SERIAL_PORT, SERIAL_BAUD,
    STAGING_ADDR, NOR_SIZE, NOR_SECTOR_SIZE,
    NOR_CHIP_NAME, NOR_FLASHROM_PROG,
    UBOOT_BIN, UBOOT_ENV_BIN, FACTORY_BIN, RECOVERY_BIN, NOR_IMAGE,
)
from lib.dts import parse_nor_partitions


# --- JTAG strategy ---

def _flash_jtag(openocd: OpenOCD, uboot: UBoot,
                label: str, binary: Path, flash_offset: int) -> None:
    total = binary.stat().st_size

    log(f"Flashing '{label}': {binary.name} ({total:#x} bytes, NOR offset {flash_offset:#x})")

    uboot.sync(timeout=5)
    out = _ub(uboot, "sf probe", timeout=10)
    if "Detected" not in out:
        err(f"sf probe failed:\n{out}")

    load_timeout = max(60, total // (70 * 1024) * 3)
    _oc(openocd, "halt", timeout=10)
    out = _oc(openocd, f"load_image {binary} {STAGING_ADDR:#x} bin", timeout=load_timeout)
    if "bytes written" not in out:
        err(f"load_image failed:\n{out}")
    _oc(openocd, "resume", timeout=10)

    sectors = (total + NOR_SECTOR_SIZE - 1) // NOR_SECTOR_SIZE
    pages   = (total + 255) // 256
    update_timeout = max(300, sectors * 200 // 1000 + pages * 5 // 1000 + 60)
    expected_crc = zlib.crc32(binary.read_bytes()) & 0xFFFFFFFF
    uboot.sync(timeout=30)

    out = _ub(uboot, f"crc32 {STAGING_ADDR:#x} {total:#x}", timeout=60)
    try:
        staging_crc = int(out.split("==>")[-1].strip().split()[0], 16)
    except (IndexError, ValueError):
        err(f"crc32 (staging) output unparseable:\n{out}")
    if staging_crc != expected_crc:
        err(f"DRAM staging CRC mismatch: got {staging_crc:#010x}, expected {expected_crc:#010x}"
            f" — load_image corrupted data")
    log(f"DRAM staging CRC verified: {staging_crc:#010x}")

    out = _ub(uboot, f"sf update {STAGING_ADDR:#x} {flash_offset:#x} {total:#x}",
              timeout=update_timeout)
    if "bytes written" not in out:
        err(f"sf update failed:\n{out}")

    verify_addr = STAGING_ADDR + ((total + 0xFFFFF) & ~0xFFFFF)
    out = _ub(uboot, f"sf read {verify_addr:#x} {flash_offset:#x} {total:#x}", timeout=60)
    if "Read: OK" not in out:
        err(f"sf read (verify) failed:\n{out}")
    out = _ub(uboot, f"crc32 {verify_addr:#x} {total:#x}", timeout=60)
    try:
        actual_crc = int(out.split("==>")[-1].strip().split()[0], 16)
    except (IndexError, ValueError):
        err(f"crc32 output unparseable:\n{out}")
    if actual_crc != expected_crc:
        err(f"CRC32 mismatch for '{label}': NOR={actual_crc:#010x}  disk={expected_crc:#010x}")
    log(f"CRC32 verified: {actual_crc:#010x}")


# --- file strategy ---

def _flash_file(selected: list[str], partitions: dict) -> None:
    img = bytearray(b"\xff" * NOR_SIZE)
    for name in selected:
        data = partitions[name]["binary"].read_bytes()
        offset = partitions[name]["offset"]
        part_size = partitions[name]["size"]
        if len(data) > part_size:
            err(f"'{name}' binary ({len(data):#x} B) exceeds partition ({part_size:#x} B)")
        img[offset:offset + len(data)] = data
    NOR_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    NOR_IMAGE.write_bytes(img)
    log(f"Written: {NOR_IMAGE}  ({len(img) // (1024 * 1024)} MB)")
    log(f"Program with: flashrom -p {NOR_FLASHROM_PROG} -c {NOR_CHIP_NAME} --force -w {NOR_IMAGE}")


# --- main ---

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--jtag", dest="strategy", action="store_const", const="jtag",
                   help="use JTAG + U-Boot sf (default)")
    p.add_argument("--file", dest="strategy", action="store_const", const="file",
                   help=f"assemble full NOR image to {NOR_IMAGE} (implies --all)")
    p.set_defaults(strategy="jtag")

    p.add_argument("--full-erase", action="store_true",
                   help=f"JTAG: erase entire chip ({NOR_SIZE // (1024 * 1024)} MB); "
                        f"mutually exclusive with partition flags")

    sel = p.add_argument_group("partition selection (at least one required, except with --full-erase)")
    sel.add_argument("--all",        action="store_true", help="flash all partitions")
    sel.add_argument("--u-boot",     action="store_true", help="flash u-boot-with-spl.bin")
    sel.add_argument("--u-boot-env", action="store_true", help="flash U-Boot env partition")
    sel.add_argument("--factory",    action="store_true", help="flash WiFi EEPROM factory blob")
    sel.add_argument("--recovery",   action="store_true", help="flash OpenWrt recovery kernel")
    args = p.parse_args()

    partition_flags = (args.all or args.u_boot or args.u_boot_env or args.factory or args.recovery)
    if args.full_erase and partition_flags:
        p.error("--full-erase is mutually exclusive with partition selection flags")
    if args.full_erase and args.strategy == "file":
        p.error("--full-erase requires JTAG, not --file")

    if args.strategy == "file" or args.all:
        args.u_boot = args.u_boot_env = args.factory = args.recovery = True

    partition_binaries = {
        "u-boot":     UBOOT_BIN,
        "u-boot-env": UBOOT_ENV_BIN,
        "factory":    FACTORY_BIN,
        "recovery":   RECOVERY_BIN,
    }

    selected = [k for k in partition_binaries if getattr(args, k.replace("-", "_"))]
    if not args.full_erase and not selected:
        p.error("select at least one partition: --u-boot / --u-boot-env / --factory / --recovery / --all")

    dts = parse_nor_partitions()
    partitions = {}
    for label, binary in partition_binaries.items():
        if label not in dts:
            err(f"Partition '{label}' not found in DTB")
        offset, size = dts[label]
        partitions[label] = {"binary": binary, "offset": offset, "size": size}

    for name in selected:
        if not partitions[name]["binary"].exists():
            err(f"file not found: {partitions[name]['binary']}")

    if args.strategy == "file":
        _flash_file(selected, partitions)
        log("Done")
        return

    # JTAG strategy
    log(f"Connecting to OpenOCD {OPENOCD_HOST}:{OPENOCD_PORT}")
    try:
        openocd = OpenOCD(OPENOCD_HOST, OPENOCD_PORT)
    except (ConnectionRefusedError, OSError) as e:
        err(f"Cannot connect to OpenOCD: {e}")
    log("OpenOCD connected")

    log(f"Opening serial {SERIAL_PORT} @ {SERIAL_BAUD} baud")
    try:
        uboot = UBoot(SERIAL_PORT, SERIAL_BAUD)
    except serial.SerialException as e:
        openocd.close()
        err(f"Cannot open serial port: {e}")

    try:
        prompt_found = uboot.sync(timeout=5)
    except serial.SerialException as e:
        openocd.close()
        uboot.close()
        err(f"Serial error waiting for U-Boot prompt: {e}")
    if not prompt_found:
        openocd.close()
        uboot.close()
        err("No U-Boot prompt on serial port — is U-Boot running at the => prompt?")
    log("U-Boot prompt confirmed")

    try:
        if args.full_erase:
            log(f"Erasing entire chip ({NOR_SIZE:#x} bytes)")
            out = _ub(uboot, "sf probe", timeout=10)
            if "Detected" not in out:
                err("sf probe failed")
            out = _ub(uboot, f"sf erase 0 {NOR_SIZE:#x}", timeout=600)
            if "OK" not in out:
                err("sf erase failed")
        else:
            for name in selected:
                _flash_jtag(
                    openocd, uboot,
                    label=name,
                    binary=partitions[name]["binary"],
                    flash_offset=partitions[name]["offset"],
                )
    finally:
        openocd.close()
        uboot.close()

    log("Done")


if __name__ == "__main__":
    main()
