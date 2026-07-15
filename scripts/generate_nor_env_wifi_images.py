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
import sys
import tempfile
from pathlib import Path

REPO        = Path(__file__).resolve().parent.parent
BUILD       = REPO / "build"
ENV_SIZE    = 0x0000_1000   # CONFIG_ENV_SIZE
EEPROM_SIZE = 0x400         # MT7603_EEPROM_SIZE

MKENVIMAGE  = REPO / "u-boot/tools/mkenvimage"
ENV_TXT     = REPO / "u-boot/board/bodybytes/bodybytes/bodybytes.env"
ENV_OUT     = BUILD / "bodybytes_nor_uboot_env.bin"
FACTORY_OUT = BUILD / "bodybytes_nor_wifi_factory.bin"


def build_env() -> bytes:
    if not MKENVIMAGE.exists():
        sys.exit(
            f"mkenvimage not found at {MKENVIMAGE}\n"
            "Build U-Boot first: cd u-boot && make bodybytes_defconfig && make -j$(nproc)"
        )
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        tmp = Path(f.name)
    try:
        subprocess.run(
            [str(MKENVIMAGE), "-s", str(ENV_SIZE), "-o", str(tmp), str(ENV_TXT)],
            check=True,
        )
        data = tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)
    if len(data) != ENV_SIZE:
        sys.exit(f"mkenvimage produced {len(data)} B, expected {ENV_SIZE}")
    return data


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
    eeprom = bytearray(EEPROM_SIZE)
    struct.pack_into("<H", eeprom, 0x00, 0x7628)
    eeprom[0x04:0x0a] = mac
    return bytes(eeprom)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mac", type=parse_mac, metavar="MAC",
                   help="WiFi MAC address (XX:XX:XX:XX:XX:XX)")
    args = p.parse_args()

    env_bin     = build_env()
    factory_bin = build_factory(args.mac)

    ENV_OUT.parent.mkdir(parents=True, exist_ok=True)
    ENV_OUT.write_bytes(env_bin)
    FACTORY_OUT.write_bytes(factory_bin)

    print(f"Written: {ENV_OUT}  ({len(env_bin)} bytes)")
    print(f"Written: {FACTORY_OUT}  ({len(factory_bin)} bytes)")


if __name__ == "__main__":
    main()
