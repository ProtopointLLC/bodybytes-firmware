#!/usr/bin/env python3
"""
Flash NOR partitions to bodybytes.

Three strategies (select with --jtag / --flashrom / --file):
  --jtag      Load via JTAG into RAM, write via U-Boot sf commands (default)
  --flashrom  Write directly via CH341A SPI programmer (faster; power off board first)
  --file      Assemble full NOR image and write to build/ (implies --all)

Prerequisites (JTAG):
  1. U-Boot running at the => prompt (use boot_uboot_jtag.py to bring up a blank board)
  2. build/ blobs generated: scripts/generate_nor_env_wifi_images.py

Prerequisites (flashrom):
  1. Board powered off and disconnected from JTAG
  2. CH341A connected to SPI header
  3. flashrom installed

Usage:
  flash_nor_images.py --all --full-erase          # JTAG: full chip erase then all partitions
  flash_nor_images.py --all                        # JTAG: incremental
  flash_nor_images.py --flashrom --all             # flashrom: selected regions only
  flash_nor_images.py --flashrom --all --full-erase  # flashrom: write entire chip image
  flash_nor_images.py --file                       # assemble full image to build/

Connection settings are read from scripts/config.ini.
"""

import argparse
import tempfile
from pathlib import Path

import serial

from lib.openocd import OpenOCD
from lib.uboot import UBoot
from lib.log import log, err, oc as _oc, ub as _ub, subproc
from lib.config import (
    OPENOCD_HOST, OPENOCD_PORT,
    SERIAL_PORT, SERIAL_BAUD,
    STAGING_ADDR, NOR_SIZE, NOR_SECTOR_SIZE,
    NOR_CHIP_NAME, NOR_FLASHROM_PROG,
    UBOOT_BIN, UBOOT_ENV_BIN, FACTORY_BIN, RECOVERY_BIN, NOR_IMAGE,
)
from lib.dts import parse_nor_partitions


def _sector_ceil(n: int) -> int:
    return (n + NOR_SECTOR_SIZE - 1) & ~(NOR_SECTOR_SIZE - 1)


# --- JTAG strategy ---

def _flash_jtag(openocd: OpenOCD, uboot: UBoot,
                label: str, binary: Path, flash_offset: int) -> None:
    data = binary.read_bytes()
    erase_size = min(_sector_ceil(len(data)), NOR_SIZE - flash_offset)

    log(f"Flashing '{label}': {binary.name} ({len(data):#x} bytes, NOR offset {flash_offset:#x})")

    _oc(openocd, "halt", timeout=10)
    out = _oc(openocd, f"load_image {binary} {STAGING_ADDR:#x} bin")
    if "bytes written" not in out:
        err(f"load_image failed for {label}")
    _oc(openocd, "resume", timeout=10)

    uboot.sync(timeout=5)

    out = _ub(uboot, "sf probe", timeout=10)
    if "Detected" not in out:
        err(f"sf probe failed:\n{out}")

    out = _ub(uboot, f"sf erase {flash_offset:#x} {erase_size:#x}")
    if "OK" not in out:
        err(f"sf erase failed:\n{out}")

    out = _ub(uboot, f"sf write {STAGING_ADDR:#x} {flash_offset:#x} {len(data):#x}")
    if "OK" not in out:
        err(f"sf write failed:\n{out}")


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
    log(f"Program with: flashrom -p {NOR_FLASHROM_PROG} -c {NOR_CHIP_NAME} --progress -w {NOR_IMAGE}")


# --- flashrom strategy ---

def _flash_flashrom(selected: list[str], partitions: dict, full_erase: bool) -> None:
    img = bytearray(b"\xff" * NOR_SIZE)
    sizes = {}
    for name in selected:
        data = partitions[name]["binary"].read_bytes()
        offset = partitions[name]["offset"]
        img[offset:offset + len(data)] = data
        sizes[name] = len(data)

    base = ["flashrom", "-p", NOR_FLASHROM_PROG, "-c", NOR_CHIP_NAME, "--force"]

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(bytes(img))
        img_path = Path(f.name)

    try:
        if full_erase:
            log(f"flashrom: writing full {NOR_SIZE // (1024 * 1024)} MB image")
            subproc(base + ["-w", str(img_path)], "Flashrom")
        else:
            layout_lines = []
            for name in selected:
                offset = partitions[name]["offset"]
                end = min(offset + _sector_ceil(sizes[name]), NOR_SIZE) - 1
                layout_lines.append(f"{offset:08x}:{end:08x} {name}")

            with tempfile.NamedTemporaryFile(suffix=".layout", mode="w", delete=False) as lf:
                lf.write("\n".join(layout_lines) + "\n")
                layout_path = Path(lf.name)

            try:
                image_flags = [flag for name in selected for flag in ("-i", name)]
                log(f"flashrom: writing regions: {', '.join(selected)}")
                subproc(base + ["-l", str(layout_path)] + image_flags + ["-w", str(img_path)], "Flashrom")
            finally:
                layout_path.unlink(missing_ok=True)
    finally:
        img_path.unlink(missing_ok=True)


# --- main ---

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--jtag",     dest="strategy", action="store_const", const="jtag",
                   help="use JTAG + U-Boot sf (default)")
    p.add_argument("--flashrom", dest="strategy", action="store_const", const="flashrom",
                   help="use flashrom via CH341A SPI programmer")
    p.add_argument("--file",     dest="strategy", action="store_const", const="file",
                   help=f"assemble full NOR image to {NOR_IMAGE} (implies --all)")
    p.set_defaults(strategy="jtag")

    sel = p.add_argument_group("partition selection (at least one required)")
    sel.add_argument("--all",         action="store_true", help="flash all partitions")
    sel.add_argument("--u-boot",      action="store_true", help="flash u-boot-with-spl.bin")
    sel.add_argument("--u-boot-env",  action="store_true", help="flash U-Boot env partition")
    sel.add_argument("--factory",     action="store_true", help="flash WiFi EEPROM factory blob")
    sel.add_argument("--recovery",    action="store_true", help="flash OpenWrt recovery kernel")
    sel.add_argument("--full-erase",  action="store_true",
                     help=f"erase entire chip before flashing ({NOR_SIZE // (1024 * 1024)} MB, "
                          f"set via nor->total_size_mb in config.ini)")
    args = p.parse_args()

    if args.strategy == "file" or args.all:
        args.u_boot = args.u_boot_env = args.factory = args.recovery = True

    partition_binaries = {
        "u-boot":     UBOOT_BIN,
        "u-boot-env": UBOOT_ENV_BIN,
        "factory":    FACTORY_BIN,
        "recovery":   RECOVERY_BIN,
    }

    selected = [k for k in partition_binaries if getattr(args, k.replace("-", "_"))]
    if not selected:
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

    if args.strategy == "flashrom":
        _flash_flashrom(selected, partitions, args.full_erase)
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

    if not uboot.sync(timeout=5):
        openocd.close()
        uboot.close()
        err("No U-Boot prompt on serial port — is U-Boot running at the => prompt?")
    log("U-Boot prompt confirmed")

    try:
        if args.full_erase:
            log(f"Full chip erase ({NOR_SIZE:#x} bytes)")
            uboot.sync(timeout=5)
            out = _ub(uboot, "sf probe", timeout=10)
            if "Detected" not in out:
                err("sf probe failed")
            out = _ub(uboot, f"sf erase 0 {NOR_SIZE:#x}", timeout=600)
            if "OK" not in out:
                err("sf erase failed")

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
