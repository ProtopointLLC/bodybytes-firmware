# Building

Prerequisites: `u-boot` and `openwrt` are git submodules - run `git submodule update --init --recursive` if either directory is empty.

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
| [`u-boot/u-boot.bin`](../u-boot/u-boot.bin) | U-Boot proper, linked at `0x80200000`. JTAG RAM boot. |
| [`u-boot/spl/u-boot-spl.bin`](../u-boot/spl/u-boot-spl.bin) | SPL; runs from NOR flash, initialises PLL+DRAM, then loads and jumps to U-Boot proper. |
| [`u-boot/u-boot-with-spl.bin`](../u-boot/u-boot-with-spl.bin) | Combined NOR image: SPL immediately followed by LZMA-compressed U-Boot. Write to NOR offset 0. |

`u-boot.bin` expects PLL and DRAM already initialised (`CONFIG_SKIP_LOWLEVEL_INIT=y`) — the JTAG scripts provide this for RAM boot.

### VS Code tasks

| Task | What it runs | When to use |
|------|-------------|-------------|
| _**U-Boot: Build**_ (`Ctrl+Shift+B`) | `make bodybytes_defconfig && make -j$(nproc)` | Default — incremental; always re-applies defconfig and picks up DTS changes |
| _**U-Boot: Clean Build**_ | `make mrproper && make bodybytes_defconfig && make -j$(nproc)` | Full wipe when the build is stuck or after major restructuring |

Both tasks run inside `nix develop .#uboot` automatically — no manual shell entry required.

→ See [flashing.md §4](flashing.md#4--program-spi-nor) for NOR programming.

---

## OpenWrt

See [openwrt.md](openwrt.md) for board file documentation and sysupgrade internals.

OpenWrt builds its own MIPS cross-compiler from source. Do **not** use the U-Boot `nix develop .#uboot` shell - it sets `CROSS_COMPILE` and `ARCH`, which would interfere.

### Dev shell

```sh
cd /path/to/bodybytes
nix develop .#openwrt
```

Enters a `buildFHSEnv` shell with all required host tools (no cross-compilation variables set). Sets `AR=gcc-ar` (LTO-aware archiver) and `FAKEROOTDONTTRYCHOWN=1` (suppresses fakeroot ownership warnings during image assembly).

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

[`bodybytes.config`](../bodybytes.config) seeds the target/board selection and board-specific Kconfig options; `make defconfig` expands it to a full `.config`. `CONFIG_TARGET_MULTI_PROFILE=y` is required — without it only one of the two device profiles is built. Run `make menuconfig` to add or change packages. See [openwrt.md §1](openwrt.md#1---board-files) for config symbol rationale.

### Build

```sh
make download
make V=s world -j$(nproc)
```

The first build downloads the MIPS cross-toolchain and all package sources; subsequent builds are incremental.

### Output

All images land in `openwrt/bin/targets/ramips/mt76x8/`. Two profiles are built:

```
openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-initramfs-kernel.bin
openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin
openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-initramfs-kernel.bin
```

| Image | Profile | Purpose |
|-------|---------|---------|
| [`openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin) | `bodybytes_bodybytes` | Sysupgrade tar (regular kernel + squashfs rootfs). Used for initial eMMC install and all OTA updates. |
| [`openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-initramfs-kernel.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-initramfs-kernel.bin) | `bodybytes_bodybytes` | Initramfs kernel for the main profile; useful for RAM-boot testing without eMMC. |
| [`openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin) | `bodybytes_bodybytes_recovery` | Initramfs kernel written to NOR `recovery` partition at `0x060000` by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py). |
| [`openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-initramfs-kernel.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-initramfs-kernel.bin) | `bodybytes_bodybytes_recovery` | Same content as `squashfs-recovery.bin`; intermediate build artifact. |

### VS Code tasks

| Task | What it runs |
|------|-------------|
| _**OpenWrt: Setup**_ | Feeds update + install, configure, download - use on first checkout |
| _**OpenWrt: Download Packages**_ | Configure + download only (skip feeds re-update on incremental builds) |
| _**OpenWrt: Build**_ | Configure + `make V=s world -j$(nproc)` |

All three tasks enter `nix develop .#openwrt` automatically - no manual shell entry required.

→ See [flashing.md §3](flashing.md#3--assemble-nor-image) to assemble the NOR image and [flashing.md §4](flashing.md#4--program-spi-nor) to program NOR. See [flashing.md §5](flashing.md#5--emmc) for initial eMMC install.
