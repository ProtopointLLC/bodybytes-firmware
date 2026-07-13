# Building

Prerequisites: `u-boot` and `openwrt` are git submodules — run `git submodule update --init --recursive` if either directory is empty.

---

## U-Boot

See [uboot.md](uboot.md) for defconfig rationale and board file documentation.

### Dev shell

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

Sets `CROSS_COMPILE=mipsel-unknown-linux-gnu-` and `ARCH=mips` automatically.

### Configure

```sh
cd u-boot
make bodybytes_defconfig
```

`bodybytes_defconfig` is a complete standalone defconfig. To change a Kconfig option, edit it directly and re-run `make bodybytes_defconfig`. Run `make menuconfig` to explore options interactively.

### Build

```sh
make -j$(nproc)
```

### Output

| File | Use |
|------|-----|
| `u-boot.bin` | U-Boot proper, linked at `0x80200000`. JTAG RAM boot. |
| `spl/u-boot-spl.bin` | SPL; runs from NOR flash, initialises PLL+DRAM, then loads and jumps to U-Boot proper. |
| `u-boot-with-spl.bin` | Combined NOR image: SPL immediately followed by LZMA-compressed U-Boot. Write to NOR offset 0. |

`CONFIG_SKIP_LOWLEVEL_INIT=y` is set, so `u-boot.bin` expects PLL and DRAM already initialised — exactly what the JTAG OpenOCD scripts provide for RAM boot.

→ See [flashing.md §4](flashing.md#4--program-spi-nor) for NOR programming.

---

## OpenWrt

See [openwrt.md](openwrt.md) for board file documentation and sysupgrade internals.

OpenWrt builds its own MIPS cross-compiler from source. Do **not** use the U-Boot `nix develop .#uboot` shell — it sets `CROSS_COMPILE` and `ARCH`, which would interfere.

### Dev shell

```sh
cd /path/to/bodybytes
nix develop .#openwrt
```

Drops into a `buildFHSEnv` shell with all required host tools, without setting any cross-compilation variables. Also sets `AR=gcc-ar` (LTO-aware archiver for host builds) and `FAKEROOTDONTTRYCHOWN=1` (works around a fakeroot/bwrap user-namespace limitation that would otherwise produce ownership warnings during image assembly).

### Feeds

```sh
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

### Configure

```sh
cp ../bodybytes.config .config
make defconfig
```

`bodybytes.config` seeds the target/board selection and board-specific Kconfig options (`CONFIG_EMMC_SUPPORT=y` ensures `emmc.sh` is included in the base-files package). `CONFIG_TARGET_MULTI_PROFILE=y` enables building both device profiles (`bodybytes_bodybytes` and `bodybytes_bodybytes_recovery`) in one pass — without it the device symbols are in a Kconfig `choice` and only the last one set is built. `make defconfig` expands the seed into a full `.config`. To add or change packages, run `make menuconfig` afterwards.

### Build

```sh
make download
make V=s world -j$(nproc)
```

The first build downloads the MIPS cross-toolchain and all package sources; subsequent builds are incremental.

### Output

All images land in `openwrt/bin/targets/ramips/mt76x8/`. Two profiles are built:

```
openwrt-ramips-mt76x8-bodybytes_bodybytes-sysupgrade.bin
openwrt-ramips-mt76x8-bodybytes_bodybytes_recovery-initramfs-kernel.bin
openwrt-ramips-mt76x8-bodybytes_bodybytes_recovery-recovery.bin
```

| Image | Profile | Purpose |
|-------|---------|---------|
| `bodybytes_bodybytes-sysupgrade.bin` | `bodybytes_bodybytes` | Sysupgrade tar (regular kernel + squashfs rootfs). Used for initial eMMC install and all OTA updates. |
| `bodybytes_bodybytes_recovery-recovery.bin` | `bodybytes_bodybytes_recovery` | Initramfs kernel written to NOR `recovery` partition at `0x060000`; referenced by `scripts/generate_nor_image.py`. |
| `bodybytes_bodybytes_recovery-initramfs-kernel.bin` | `bodybytes_bodybytes_recovery` | Same content as `recovery.bin`; intermediate artifact. |

→ See [flashing.md §3](flashing.md#3--assemble-nor-image) to assemble the NOR image and [flashing.md §4](flashing.md#4--program-spi-nor) to program NOR. See [flashing.md §5](flashing.md#5--emmc) for initial eMMC install.
