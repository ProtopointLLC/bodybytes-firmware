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
for f in packages luci routing telephony video; do ./scripts/feeds install -a -p $f; done
./scripts/feeds install -p immortalwrt_luci luci-app-dufs
```

`feeds.conf.default` pins a second feed, `immortalwrt_luci`, used only to cherry-pick `luci-app-dufs` (not in the primary `luci` feed). **`./scripts/feeds install -a` alone is not scoped to "the feeds that existed before" — it walks every feed listed in `feeds.conf.default`, full stop.** Running it plain here would install all ~190 other `luci-app-*`/`luci-theme-*`/`luci-proto-*` packages from `immortalwrt_luci` too (confirmed: several of those have broken Kconfig, e.g. recursive-dependency errors on `luci-app-passwall`/`luci-app-homeproxy`/`luci-app-ipsec-vpnd`, since that feed normally pairs with ImmortalWrt's own `packages` fork, not upstream's). The `for` loop above scopes `-a` to just the five feeds this project actually wants everything from (`-a -p <feedname>` = "install all, but only from this feed"); `immortalwrt_luci` is deliberately left out of it and only ever touched by the final targeted single-package install. Neither `travelmate` nor `luci-app-travelmate` need any special-casing here — both come straight from their (forked) feeds like any other package now (see below).

**Never hand-edit files inside `openwrt/feeds/`.** `./scripts/feeds update <name>` does a git checkout to the pinned commit and will silently discard local edits there (or refuse on a dirty tree); `package/feeds/<name>/<pkg>` is just a symlink into the same checkout, not a separate copy, so it doesn't help either. This project's convention for a board-specific change to a feed package is to **fork the feed itself**: `feeds.conf.default`'s `packages` and `luci` lines point at [`StarGate01/bodybytes-packages`](https://github.com/StarGate01/bodybytes-packages) and [`StarGate01/bodybytes-luci`](https://github.com/StarGate01/bodybytes-luci) (both branch `bodybytes`, each pinned to a specific commit like every other feed here) instead of upstream, carrying the `travelmate`/`luci-app-travelmate` patches as real, minimal commits in each fork's git history. That survives `feeds update` the same way any other pinned-feed change does, reads as an ordinary diff (`git diff <old-pin>..<new-pin>` in the fork), and is trivially upstreamable later if desired. Worth it even though `packages`/`luci` are large monorepos covering hundreds of unrelated packages: the actual patch in each is tiny (one package, a handful of commits), so the maintenance burden is small regardless of how big the fork itself is — what matters is how much you're actually patching, not how big the repo you're patching happens to be. See the Travelmate bullet in `docs/openwrt.md` for what each patch does.

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
| _**OpenWrt: Remote Build**_ | Configure + [`scripts/remote-openwrt-build.sh`](../scripts/remote-openwrt-build.sh) `V=s world -j$(nproc)` (see below) |

All tasks enter `nix develop .#openwrt` (or `nix run .#openwrt`) automatically - no manual shell entry required, except for the remote-build step itself, which runs directly on the host since it needs `ssh`/`rsync`.

### Remote build

[`scripts/remote-openwrt-build.sh`](../scripts/remote-openwrt-build.sh) offloads `make world` to a faster machine over SSH (default host: `redbox-server`), then rsyncs `build_dir`/`staging_dir`/`bin`/`dl` back so this machine can keep building incrementally once the remote is offline. Requires the repo checked out at the *same absolute path* on both machines and Nix (with flakes) installed remotely - OpenWrt's self-built toolchain embeds absolute paths, and incremental rebuilds rely on rsync preserving file mtimes.

```sh
scripts/remote-openwrt-build.sh V=s world -j'$(nproc)'   # quoted: nproc evaluates on the remote, not here
scripts/remote-openwrt-build.sh download
```

→ See [flashing.md §3](flashing.md#3--assemble-nor-image) to assemble the NOR image and [flashing.md §4](flashing.md#4--program-spi-nor) to program NOR. See [flashing.md §5](flashing.md#5--emmc) for initial eMMC install.
