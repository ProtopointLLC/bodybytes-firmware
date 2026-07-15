#!/usr/bin/env python3
"""
Generate synthesized NOR partition blobs for bodybytes.

Outputs (written to build/):
  bodybytes_nor_uboot_env.bin     4 KB mkenvimage blob for the u-boot-env partition
  bodybytes_nor_wifi_factory.bin  1 KB WiFi EEPROM blob (chip ID 0x7628 + MAC)

Run this once per device MAC address. Both blobs are consumed by:
  scripts/flash_nor_images.py  — incremental JTAG flashing
  scripts/pack_nor_image.py    — full NOR image for flashrom / CH341A
"""

import argparse
import re
import struct
import subprocess

from lib.config import WIFI_CHIP_ID, WIFI_MAC, MKENVIMAGE, UBOOT_ENV_TXT, UBOOT_ENV_BIN, FACTORY_BIN, UBOOT_DEFCONFIG
from lib.dts import parse_wifi_cal_size
from lib.log import log, err

def _read_env_size() -> int:
    if not UBOOT_DEFCONFIG.exists():
        err(f"not found: {UBOOT_DEFCONFIG}  (build U-Boot first)")
    for line in UBOOT_DEFCONFIG.read_text().splitlines():
        if line.startswith("CONFIG_ENV_SIZE="):
            return int(line.split("=", 1)[1], 0)
    err(f"CONFIG_ENV_SIZE not found in {UBOOT_DEFCONFIG}")


def build_env() -> None:
    if not MKENVIMAGE.exists():
        err(f"mkenvimage not found at {MKENVIMAGE}  (build U-Boot first)")
    env_size = _read_env_size()
    UBOOT_ENV_BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(MKENVIMAGE), "-s", str(env_size), "-o", str(UBOOT_ENV_BIN), str(UBOOT_ENV_TXT)],
        check=True,
    )
    size = UBOOT_ENV_BIN.stat().st_size
    if size != env_size:
        err(f"mkenvimage produced {size} B, expected {env_size}")


def parse_mac(s: str) -> bytes:
    if not re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", s):
        raise argparse.ArgumentTypeError(f"expected XX:XX:XX:XX:XX:XX, got {s!r}")
    mac = bytes(int(x, 16) for x in s.split(":"))
    if mac == b"\x00" * 6:
        raise argparse.ArgumentTypeError("MAC must not be all zeros")
    if mac == b"\xff" * 6:
        raise argparse.ArgumentTypeError("MAC must not be broadcast")
    return mac


def build_factory(mac: bytes) -> bytes:
    cal_size = parse_wifi_cal_size()
    eeprom = bytearray(cal_size)
    struct.pack_into("<H", eeprom, 0x00, WIFI_CHIP_ID)
    eeprom[0x04:0x0a] = mac
    return bytes(eeprom)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mac", type=parse_mac, metavar="MAC", nargs="?", default=None,
                   help=f"WiFi MAC address (XX:XX:XX:XX:XX:XX); default from config: {WIFI_MAC.hex(':')}")
    args = p.parse_args()
    mac = args.mac if args.mac is not None else WIFI_MAC

    build_env()
    factory_bin = build_factory(mac)

    FACTORY_BIN.parent.mkdir(parents=True, exist_ok=True)
    FACTORY_BIN.write_bytes(factory_bin)

    log(f"Written: {UBOOT_ENV_BIN}  ({UBOOT_ENV_BIN.stat().st_size} bytes)")
    log(f"Written: {FACTORY_BIN}  ({len(factory_bin)} bytes)")


if __name__ == "__main__":
    main()
