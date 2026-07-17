#!/usr/bin/env python3
"""
Flash NOR partitions to bodybytes.

Generates the u-boot-env and factory partitions on the fly; no pre-build
step is required.  The u-boot-env partition is generated from bodybytes.env
with the recovery_size variable patched to the exact size of the recovery
binary, rounded up to NOR sector alignment.

Two strategies (select with --jtag / --file):
  --jtag   Load via JTAG into RAM, write via U-Boot sf commands (default)
  --file   Assemble full NOR image and write to build/ (implies --all)
           Then program manually: flashrom -p <prog> -c <chip> -w build/bodybytes_nor_image.bin

Prerequisites (JTAG):
  1. U-Boot running at the => prompt (use boot_uboot_jtag.py to bring up a blank board)
  2. Compiled U-Boot: u-boot/u-boot-with-spl.bin
  3. OpenWrt recovery image at the path in scripts/config.ini [paths]->recovery_bin

Usage:
  flash_nor_images.py --bodybytes --full-erase
  flash_nor_images.py --bodybytes --all --mac XX:XX:XX:XX:XX:XX
  flash_nor_images.py --vocore2   --all --mac XX:XX:XX:XX:XX:XX
  flash_nor_images.py --bodybytes --file --mac XX:XX:XX:XX:XX:XX

Connection settings are read from scripts/config.ini.
"""

import argparse
import os
import re
import subprocess
import tempfile
import zlib
from pathlib import Path

import serial

from lib.openocd import OpenOCD
from lib.uboot import UBoot
from lib.log import log, err, oc as _oc, ub as _ub
from lib.config import (
    OPENOCD_HOST, OPENOCD_PORT,
    SERIAL_PORT, SERIAL_BAUD,
    STAGING_ADDR, NOR_SECTOR_SIZE, NOR_FLASHROM_PROG,
    UBOOT_BIN, UBOOT_ENV_TXT, UBOOT_DEFCONFIG, MKENVIMAGE,
    RECOVERY_BIN, NOR_IMAGE,
    BOARD_NAMES, load_board, BoardConfig,
)
from lib.dts import parse_nor_partitions, parse_wifi_cal_size
from lib.wifi import build_factory as _wifi_build_factory


# --- blob generation ---

def _read_env_size() -> int:
    if not UBOOT_DEFCONFIG.exists():
        err(f"not found: {UBOOT_DEFCONFIG}  (build U-Boot first)")
    for line in UBOOT_DEFCONFIG.read_text().splitlines():
        if line.startswith("CONFIG_ENV_SIZE="):
            return int(line.split("=", 1)[1], 0)
    err(f"CONFIG_ENV_SIZE not found in {UBOOT_DEFCONFIG}")


def _build_env_bin() -> bytes:
    if not MKENVIMAGE.exists():
        err(f"mkenvimage not found: {MKENVIMAGE}  (build U-Boot first)")
    if not UBOOT_ENV_TXT.exists():
        err(f"not found: {UBOOT_ENV_TXT}")
    env_size = _read_env_size()
    tmp_fd, tmp_out = tempfile.mkstemp(suffix='.bin')
    os.close(tmp_fd)
    try:
        subprocess.run(
            [str(MKENVIMAGE), '-s', str(env_size), '-o', tmp_out, str(UBOOT_ENV_TXT)],
            check=True,
        )
        data = Path(tmp_out).read_bytes()
    finally:
        Path(tmp_out).unlink(missing_ok=True)
    if len(data) != env_size:
        err(f"mkenvimage produced {len(data)} B, expected {env_size}")
    return data


def _build_factory(mac: bytes, board: BoardConfig) -> bytes:
    return _wifi_build_factory(mac, board.wifi, parse_wifi_cal_size())


def parse_mac(s: str) -> bytes:
    if not re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", s):
        raise argparse.ArgumentTypeError(f"expected XX:XX:XX:XX:XX:XX, got {s!r}")
    mac = bytes(int(x, 16) for x in s.split(":"))
    if mac == b"\x00" * 6:
        raise argparse.ArgumentTypeError("MAC must not be all zeros")
    if mac[0] & 0x01:
        raise argparse.ArgumentTypeError("MAC must not be multicast (LSB of first octet must be 0)")
    return mac


def _prepare_blobs(selected: list[str], mac: bytes, board: BoardConfig) -> dict[str, bytes]:
    blobs: dict[str, bytes] = {}

    if "u-boot" in selected:
        if not UBOOT_BIN.exists():
            err(f"not found: {UBOOT_BIN}  (build U-Boot first)")
        blobs["u-boot"] = UBOOT_BIN.read_bytes()

    if "recovery" in selected:
        matches = sorted(RECOVERY_BIN.parent.glob(RECOVERY_BIN.name))
        if not matches:
            err(f"no file matching {RECOVERY_BIN}  (build OpenWrt first)")
        if len(matches) > 1:
            err(f"ambiguous recovery glob matched {len(matches)} files: {[m.name for m in matches]}")
        log(f"recovery image: {matches[0].name}")
        blobs["recovery"] = matches[0].read_bytes()

    if "u-boot-env" in selected:
        blobs["u-boot-env"] = _build_env_bin()

    if "factory" in selected:
        blobs["factory"] = _build_factory(mac, board)

    return blobs


# --- JTAG strategy ---

def _flash_jtag(openocd: OpenOCD, uboot: UBoot,
                label: str, data: bytes, flash_offset: int) -> None:
    total = len(data)
    log(f"Flashing '{label}': {total:#x} bytes at NOR offset {flash_offset:#x}")

    load_timeout = max(60, total // (70 * 1024) * 3)
    _oc(openocd, "halt", timeout=10)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{label}.bin")
    try:
        os.write(tmp_fd, data)
        os.close(tmp_fd)
        out = _oc(openocd, f"load_image {tmp_path} {STAGING_ADDR:#x} bin", timeout=load_timeout)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if "bytes written" not in out:
        err(f"load_image failed:\n{out}")
    _oc(openocd, "resume", timeout=10)

    sectors = (total + NOR_SECTOR_SIZE - 1) // NOR_SECTOR_SIZE
    pages   = (total + 255) // 256
    update_timeout = max(300, sectors * 200 // 1000 + pages * 5 // 1000 + 60)
    expected_crc = zlib.crc32(data) & 0xFFFFFFFF
    uboot.sync(timeout=30)

    out = _ub(uboot, f"crc32 {STAGING_ADDR:#x} {total:#x}", timeout=60)
    try:
        staging_crc = int(out.split("==>")[-1].strip().split()[0], 16)
    except (IndexError, ValueError):
        err(f"crc32 (staging) output unparseable:\n{out}")
    if staging_crc != expected_crc:
        err(f"DRAM staging CRC mismatch: got {staging_crc:#010x}, expected {expected_crc:#010x}"
            f" - load_image corrupted data")
    log(f"DRAM staging CRC verified: {staging_crc:#010x}")

    out = _ub(uboot, "sf probe", timeout=10)
    if "Detected" not in out:
        err(f"sf probe (pre-update) failed:\n{out}")

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


def _probe_nor(uboot: UBoot, board: BoardConfig) -> None:
    out = _ub(uboot, "sf probe", timeout=10)
    if "Detected" not in out:
        err(f"sf probe failed:\n{out}")
    detected_line = next((l for l in out.splitlines() if "Detected" in l), out.strip())
    log(f"sf probe: {detected_line.strip()}")
    m = re.search(r'total\s+(\d+)\s+(MiB|KiB|Bytes?)', out)
    if not m:
        err(f"sf probe: cannot parse chip size from:\n{out}")
    val, unit = int(m.group(1)), m.group(2)
    detected = val * (1024 * 1024 if unit == "MiB" else 1024 if unit == "KiB" else 1)
    if detected != board.nor_size:
        err(f"NOR size mismatch: chip reports {detected // (1024 * 1024)} MiB, "
            f"board profile '{board.name}' expects {board.nor_size // (1024 * 1024)} MiB")


# --- file strategy ---

def _flash_file(selected: list[str], partitions: dict, board: BoardConfig) -> None:
    img = bytearray(b"\xff" * board.nor_size)
    for name in selected:
        data = partitions[name]["data"]
        offset = partitions[name]["offset"]
        part_size = partitions[name]["size"]
        if len(data) > part_size:
            err(f"'{name}' binary ({len(data):#x} B) exceeds partition ({part_size:#x} B)")
        img[offset:offset + len(data)] = data
    NOR_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    NOR_IMAGE.write_bytes(img)
    log(f"Written: {NOR_IMAGE}  ({len(img) // (1024 * 1024)} MB)")
    log(f"Program with: flashrom -p {NOR_FLASHROM_PROG} -c {board.nor_chip_name} --force -w {NOR_IMAGE}")


# --- main ---

def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    board_grp = p.add_mutually_exclusive_group(required=True)
    for name in BOARD_NAMES:
        board_grp.add_argument(f"--{name}", dest="board", action="store_const", const=name,
                               help=f"target board: {name}")

    p.add_argument("--jtag", dest="strategy", action="store_const", const="jtag",
                   help="use JTAG + U-Boot sf (default)")
    p.add_argument("--file", dest="strategy", action="store_const", const="file",
                   help=f"assemble full NOR image to {NOR_IMAGE} (implies --all)")
    p.set_defaults(strategy="jtag")

    p.add_argument("--full-erase", action="store_true",
                   help="JTAG: erase entire chip; mutually exclusive with partition flags")
    p.add_argument("--mac", type=parse_mac, default=None,
                   metavar="XX:XX:XX:XX:XX:XX",
                   help="WiFi MAC address (required when flashing the factory partition)")

    sel = p.add_argument_group("partition selection (at least one required, except with --full-erase)")
    sel.add_argument("--all",        action="store_true", help="flash all partitions")
    sel.add_argument("--u-boot",     action="store_true", help="flash u-boot-with-spl.bin")
    sel.add_argument("--u-boot-env", action="store_true", help="flash U-Boot env (recovery_size patched in)")
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

    if args.factory and args.mac is None:
        p.error("--mac XX:XX:XX:XX:XX:XX is required when flashing the factory (WiFi EEPROM) partition")

    mac = args.mac

    selected = [k for k in ["u-boot", "u-boot-env", "factory", "recovery"]
                if getattr(args, k.replace("-", "_"))]
    if not args.full_erase and not selected:
        p.error("select at least one partition: --u-boot / --u-boot-env / --factory / --recovery / --all")

    board = load_board(args.board)
    log(f"Board: {board.name}  NOR: {board.nor_size // (1024 * 1024)} MB ({board.nor_chip_name})"
        f"  DRAM: {board.dram_size_mb} MB")

    if not args.full_erase:
        blobs = _prepare_blobs(selected, mac, board)
        dts = parse_nor_partitions()
        partitions = {}
        for label in ["u-boot", "u-boot-env", "factory", "recovery"]:
            if label not in dts:
                err(f"Partition '{label}' not found in DTB")
            offset, size = dts[label]
            partitions[label] = {"data": blobs.get(label, b""), "offset": offset, "size": size}

    if args.strategy == "file":
        _flash_file(selected, partitions, board)
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
        err("No U-Boot prompt on serial port - is U-Boot running at the => prompt?")
    log("U-Boot prompt confirmed")

    try:
        uboot.sync(timeout=5)
        _probe_nor(uboot, board)

        if args.full_erase:
            log(f"Erasing entire chip ({board.nor_size:#x} bytes)")
            out = _ub(uboot, f"sf erase 0 {board.nor_size:#x}", timeout=600)
            if "OK" not in out:
                err("sf erase failed")
        else:
            for name in selected:
                data = partitions[name]["data"]
                part_size = partitions[name]["size"]
                if len(data) > part_size:
                    err(f"'{name}' binary ({len(data):#x} B) exceeds partition ({part_size:#x} B)")
                _flash_jtag(
                    openocd, uboot,
                    label=name,
                    data=data,
                    flash_offset=partitions[name]["offset"],
                )
    finally:
        openocd.close()
        uboot.close()

    log("Done")


if __name__ == "__main__":
    main()
