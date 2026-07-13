#!/usr/bin/env python3
"""
Assemble a complete NOR image for bodybytes (64 MB W25Q512JV) or VoCore2 (32 MB W25Q256).

Partition layout (matches bodybytes,bodybytes.dts + bodybytes_defconfig):
  0x000000  256 KB   u-boot       u-boot-with-spl.bin; remainder 0xFF
  0x040000   64 KB   u-boot-env   built from board/bodybytes/bodybytes/bodybytes.env
  0x050000   64 KB   factory      1 KB EEPROM (chip ID + MAC); remainder 0xFF
  0x060000  rest     recovery     OpenWrt initramfs-kernel.bin; remainder 0xFF
                                  63.625 MB on bodybytes, 31.625 MB on VoCore2

Factory EEPROM layout (first 1 KB of factory partition):
  0x00  2 B  Chip ID  0x7628 little-endian
  0x04  6 B  MAC      from --mac argument
  rest  0x00 RF cal fields; merged from on-chip eFuse at boot
             (mediatek,eeprom-merge-otp in DTS)

Use --nor-size 32 to produce a 32 MB image for VoCore2 recovery testing.
"""

import argparse
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO         = Path(__file__).resolve().parent.parent
UBOOT_MAX    = 0x0004_0000  # 256 KB partition
ENV_OFF      = 0x0004_0000
ENV_SIZE     = 0x0000_1000  # CONFIG_ENV_SIZE
FACTORY_OFF  = 0x0005_0000
RECOVERY_OFF = 0x0006_0000
EEPROM_SIZE  = 0x400        # MT7603_EEPROM_SIZE

MKENVIMAGE = REPO / "u-boot/tools/mkenvimage"
ENV_TXT    = REPO / "u-boot/board/bodybytes/bodybytes/bodybytes.env"
UBOOT_BIN  = REPO / "u-boot/u-boot-with-spl.bin"
RECOVERY_BIN = (REPO / "openwrt/bin/targets/ramips/mt76x8"
                / "openwrt-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin")


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
    p.add_argument("mac", type=parse_mac, metavar="MAC",
                   help="WiFi MAC address (XX:XX:XX:XX:XX:XX)")
    p.add_argument("--nor-size", type=int, default=64, metavar="MB",
                   help="NOR flash size in MB (default: 64 for bodybytes W25Q512JV; use 32 for VoCore2 W25Q256)")
    p.add_argument("--out", type=Path, metavar="FILE",
                   help="output image (default: assets/bodybytes_nor_image.bin)")
    args = p.parse_args()

    nor_size = args.nor_size * 1024 * 1024
    if args.out is None:
        args.out = REPO / "assets/bodybytes_nor_image.bin"

    uboot    = UBOOT_BIN.read_bytes()
    env_bin  = build_env()
    recovery = RECOVERY_BIN.read_bytes()

    if len(uboot) > UBOOT_MAX:
        p.error(f"u-boot ({len(uboot)} B) exceeds partition ({UBOOT_MAX} B)")
    if len(recovery) > nor_size - RECOVERY_OFF:
        p.error(f"recovery image ({len(recovery)} B) exceeds recovery partition ({nor_size - RECOVERY_OFF:#x} B)")

    img = bytearray(b"\xff" * nor_size)
    img[0:len(uboot)] = uboot
    img[ENV_OFF:ENV_OFF + ENV_SIZE] = env_bin

    eeprom = bytearray(EEPROM_SIZE)
    struct.pack_into("<H", eeprom, 0x00, 0x7628)
    eeprom[0x04:0x0a] = args.mac
    img[FACTORY_OFF:FACTORY_OFF + EEPROM_SIZE] = eeprom

    img[RECOVERY_OFF:RECOVERY_OFF + len(recovery)] = recovery

    args.out.write_bytes(img)

    print(f"Written: {args.out}  ({len(img)} bytes)\n")
    print("Program via U-Boot (after loading the image to 0x80000000 via JTAG):\n")
    print(f"  sf probe")
    print(f"  sf erase 0 {nor_size:#x}")
    print(f"  sf write 0x80000000 0 {nor_size:#x}")
    print()
    print("Or write directly with a SPI flash programmer (e.g. flashrom).")


if __name__ == "__main__":
    main()
