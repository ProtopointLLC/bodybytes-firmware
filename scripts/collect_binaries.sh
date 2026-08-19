#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p build

cp "$(ls openwrt/bin/targets/ramips/mt76x8/openwrt-*-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin)" build/openwrt-sysupgrade.bin
cp u-boot/u-boot.bin build/u-boot-ram.bin

./scripts/flash_nor_images.py --bodybytes --file --minimal --mac AA:BB:CC:DD:EE:01
mv build/bodybytes_nor_image.bin build/firmware-minimal-bodybytes.bin

./scripts/flash_nor_images.py --vocore2 --file --minimal --mac AA:BB:CC:DD:EE:01
mv build/bodybytes_nor_image.bin build/firmware-minimal-vocore2.bin
