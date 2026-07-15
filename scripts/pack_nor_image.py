#!/usr/bin/env python3
"""
Assemble a complete NOR image for bodybytes (64 MB W25Q512JV) or VoCore2 (32 MB W25Q256FV).

Use this to produce a single binary for programming via a SPI flash programmer
(flashrom + CH341A). For incremental JTAG-based flashing use flash_nor_images.py.

Prerequisites — run first:
  scripts/generate_nor_image.py <MAC>

Partition layout (matches bodybytes,bodybytes.dts + bodybytes_defconfig):
  0x000000  256 KB   u-boot       u-boot/u-boot-with-spl.bin; remainder 0xFF
  0x040000   64 KB   u-boot-env   build/bodybytes_nor_uboot_env.bin
  0x050000   64 KB   factory      build/bodybytes_nor_wifi_factory.bin
  0x060000  rest     recovery     openwrt/.../squashfs-recovery.bin; remainder 0xFF

Use --nor-size 32 for a 32 MB image (VoCore2 W25Q256FV).
"""

import argparse
import sys
from pathlib import Path

REPO         = Path(__file__).resolve().parent.parent
BUILD        = REPO / "build"
UBOOT_MAX    = 0x0004_0000
ENV_OFF      = 0x0004_0000
ENV_SIZE     = 0x0000_1000
FACTORY_OFF  = 0x0005_0000
RECOVERY_OFF = 0x0006_0000

UBOOT_BIN    = REPO / "u-boot/u-boot-with-spl.bin"
ENV_BIN      = BUILD / "bodybytes_nor_uboot_env.bin"
FACTORY_BIN  = BUILD / "bodybytes_nor_wifi_factory.bin"
RECOVERY_BIN = (REPO / "openwrt/bin/targets/ramips/mt76x8"
                / "openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin")

CHIP = {64: "W25Q512JV", 32: "W25Q256FV"}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nor-size", type=int, default=64, metavar="MB",
                   choices=[32, 64],
                   help="NOR flash size in MB (default: 64 for bodybytes; 32 for VoCore2)")
    p.add_argument("--out", type=Path, metavar="FILE",
                   help="output image path (default: build/bodybytes_nor_image.bin)")
    args = p.parse_args()

    nor_size = args.nor_size * 1024 * 1024
    if args.out is None:
        args.out = BUILD / "bodybytes_nor_image.bin"

    missing = [
        (UBOOT_BIN,    "u-boot/u-boot-with-spl.bin — build U-Boot first"),
        (ENV_BIN,      "build/bodybytes_nor_uboot_env.bin — run generate_nor_image.py first"),
        (FACTORY_BIN,  "build/bodybytes_nor_wifi_factory.bin — run generate_nor_image.py first"),
        (RECOVERY_BIN, "OpenWrt recovery binary — build OpenWrt first"),
    ]
    for path, hint in missing:
        if not path.exists():
            sys.exit(f"Missing: {path}\n  → {hint}")

    uboot    = UBOOT_BIN.read_bytes()
    env_bin  = ENV_BIN.read_bytes()
    factory  = FACTORY_BIN.read_bytes()
    recovery = RECOVERY_BIN.read_bytes()

    if len(uboot) > UBOOT_MAX:
        p.error(f"u-boot ({len(uboot)} B) exceeds partition ({UBOOT_MAX:#x} B)")
    if len(recovery) > nor_size - RECOVERY_OFF:
        p.error(f"recovery ({len(recovery)} B) exceeds partition ({nor_size - RECOVERY_OFF:#x} B)")

    img = bytearray(b"\xff" * nor_size)
    img[0:len(uboot)]                              = uboot
    img[ENV_OFF:ENV_OFF + len(env_bin)]            = env_bin
    img[FACTORY_OFF:FACTORY_OFF + len(factory)]    = factory
    img[RECOVERY_OFF:RECOVERY_OFF + len(recovery)] = recovery

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(img)

    chip = CHIP.get(args.nor_size, "")
    print(f"Written: {args.out}  ({len(img) // (1024*1024)} MB)\n")
    print("Program with flashrom (CH341A):")
    print(f"  flashrom -p ch341a_spi -c {chip} --progress -w {args.out}")


if __name__ == "__main__":
    main()
