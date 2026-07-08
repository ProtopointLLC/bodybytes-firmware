#!/usr/bin/env python3
"""
Assemble a complete 64 MB NOR image for the W25Q512JV.

Partition layout (matches bodybytes,bodybytes.dts + bodybytes_defconfig):
  0x000000  256 KB   u-boot       u-boot-with-spl.bin; remainder 0xFF
  0x040000   64 KB   u-boot-env   0xFF; U-Boot writes on first saveenv
  0x050000   64 KB   factory      1 KB EEPROM (chip ID + MAC); remainder 0xFF
  0x060000  63.6 MB  recovery     OpenWrt sysupgrade image; remainder 0xFF

Factory EEPROM layout (first 1 KB of factory partition):
  0x00  2 B  Chip ID  0x7628 little-endian
  0x04  6 B  MAC      from --mac argument
  rest  0x00 RF cal fields; merged from on-chip eFuse at boot
             (mediatek,eeprom-merge-otp in DTS)
"""

import argparse
import re
import struct
import sys
from pathlib import Path

REPO        = Path(__file__).resolve().parent.parent
NOR_SIZE    = 0x0400_0000   # 64 MB
UBOOT_MAX   = 0x0004_0000   # 256 KB partition
FACTORY_OFF = 0x0005_0000
RECOVERY_OFF= 0x0006_0000
EEPROM_SIZE = 0x400         # MT7603_EEPROM_SIZE

DEFAULT_UBOOT   = REPO / "u-boot/u-boot-with-spl.bin"
DEFAULT_OPENWRT = (REPO / "openwrt/bin/targets/ramips/mt76x8"
                   / "openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin")
DEFAULT_OUT     = REPO / "assets/bodybytes_nor_image.bin"


def parse_mac(s):
    if not re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", s):
        raise argparse.ArgumentTypeError(f"expected XX:XX:XX:XX:XX:XX, got {s!r}")
    mac = bytes(int(x, 16) for x in s.split(":"))
    if mac == b"\x00" * 6:
        raise argparse.ArgumentTypeError("MAC must not be all zeros")
    if mac == b"\xff" * 6:
        raise argparse.ArgumentTypeError("MAC must not be broadcast")
    return mac


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mac",      type=parse_mac,   metavar="MAC",
                   help="WiFi MAC address (XX:XX:XX:XX:XX:XX)")
    p.add_argument("--uboot",  type=Path, default=DEFAULT_UBOOT,
                   metavar="FILE", help="u-boot-with-spl.bin (default: %(default)s)")
    p.add_argument("--openwrt",type=Path, default=DEFAULT_OPENWRT,
                   metavar="FILE", help="squashfs-sysupgrade.bin (default: %(default)s)")
    p.add_argument("--out",    type=Path, default=DEFAULT_OUT,
                   metavar="FILE", help="output image (default: %(default)s)")
    args = p.parse_args()

    uboot   = args.uboot.read_bytes()
    openwrt = args.openwrt.read_bytes()

    if len(uboot) > UBOOT_MAX:
        p.error(f"u-boot ({len(uboot)} B) exceeds partition ({UBOOT_MAX} B)")
    if len(openwrt) > NOR_SIZE - RECOVERY_OFF:
        p.error(f"OpenWrt image ({len(openwrt)} B) exceeds recovery partition")

    # Blank image (0xFF = erased flash)
    img = bytearray(b"\xff" * NOR_SIZE)

    # U-Boot at offset 0
    img[0:len(uboot)] = uboot

    # Factory EEPROM: chip ID + MAC; RF cal fields left zero for eFuse merge
    eeprom = bytearray(EEPROM_SIZE)
    struct.pack_into("<H", eeprom, 0x00, 0x7628)
    eeprom[0x04:0x0a] = args.mac
    img[FACTORY_OFF:FACTORY_OFF + EEPROM_SIZE] = eeprom

    # OpenWrt recovery image
    img[RECOVERY_OFF:RECOVERY_OFF + len(openwrt)] = openwrt

    args.out.write_bytes(img)

    recovery_erase = (len(openwrt) + 0xffff) & ~0xffff
    print(f"Written: {args.out}  ({len(img)} bytes)\n")
    print("Program via U-Boot (after loading nor_image.bin to 0x80000000, e.g. via TFTP):\n")
    print(f"  sf probe")
    print(f"  sf erase 0 0x50000")
    print(f"  sf write 0x80000000 0 {len(uboot):#x}")
    print(f"  sf erase 0x50000 0x10000")
    print(f"  sf write 0x80050000 0x50000 0x400")
    print(f"  sf erase 0x60000 {recovery_erase:#x}")
    print(f"  sf write 0x80060000 0x60000 {len(openwrt):#x}")
    print()
    print("Or write nor_image.bin directly with a SPI flash programmer (e.g. flashrom).")


if __name__ == "__main__":
    main()
