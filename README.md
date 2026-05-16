# bodybytes-firmware

Development environment for the bodybytes implantable WiFi router — MT7628AN
SoC, 256 MB DDR2, 64 MB SPI NOR, 128 GB eMMC.

## Repositories

This repo uses two submodules:

| Path | Contents |
|------|----------|
| `openocd-scripts/` | MT7628 OpenOCD target scripts (`mt7628.cfg`, `mmio.tcl`, `memc.tcl`) |
| `u-boot/` | U-Boot source, pinned to tag `v2026.04` |

Clone with submodules:

```sh
git clone --recurse-submodules <url>
```

## Dev shell

A single Nix dev shell covers both OpenOCD and U-Boot work:

```sh
nix develop
```

This sets:
- `OPENOCD_SCRIPTS` — points to `openocd-scripts/mt7628/` so OpenOCD finds target scripts by name
- `CROSS_COMPILE`, `ARCH` — MIPS cross-compilation environment for U-Boot
- `KCPPFLAGS` — injects `CFG_SYS_NS16550_COM3` for the UART2 SPL console

## Documentation

- [docs/jtag.md](docs/jtag.md) — wiring, JTAG connectivity check, PLL/DRAM bootstrap
- [docs/uboot.md](docs/uboot.md) — U-Boot configure, build, and full install sequence
