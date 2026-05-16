# bodybytes-firmware

Development environment for the bodybytes implantable WiFi router — MT7628AN
SoC, 256 MB DDR2, 64 MB SPI NOR, 128 GB eMMC.

## Submodules

| Path | Contents |
|------|----------|
| `openocd-scripts/` | MT7628 OpenOCD target scripts (`mt7628.cfg`, `mmio.tcl`, `memc.tcl`) |
| `u-boot/` | U-Boot source, pinned to tag `v2026.04` |
| `openwrt/` | OpenWRT source tree with bodybytes board files |

Clone with submodules:

```sh
git clone --recurse-submodules <url>
```

## Dev shells

| Shell | Purpose |
|-------|---------|
| `nix develop .#uboot` | U-Boot build + OpenOCD/JTAG. Sets `CROSS_COMPILE`, `ARCH`, `OPENOCD_SCRIPTS`. |
| `nix develop .#openwrt` | OpenWRT host build. FHS environment; sets `AR`, `NM`, `RANLIB`, `FAKEROOTDONTTRYCHOWN`. |

## Documentation

- [docs/jtag.md](docs/jtag.md) — JTAG wiring, connectivity check, PLL/DRAM bootstrap
- [docs/uboot.md](docs/uboot.md) — U-Boot configure, build, and full install sequence
- [docs/openwrt.md](docs/openwrt.md) — OpenWRT build, board files reference, and eMMC flash
