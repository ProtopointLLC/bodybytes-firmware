# bodybytes-firmware

Development environment for the bodybytes implantable WiFi router - MT7628AN SoC, 256 MB DDR2, 64 MB SPI NOR, 128 GB eMMC.

## Submodules

| Path | Contents |
|------|----------|
| `u-boot/` | U-Boot `v2026.04`, branch `bodybytes` - board support for MT7628AN |
| `openwrt/` | OpenWRT `v25.12.4`, branch `bodybytes` - board target and DTS for bodybytes |

The MT7628 OpenOCD target scripts (`mt7628.cfg`, `mmio.tcl`, `memc.tcl`) in `openocd/` are vendored from [mtk-openwrt/openocd-scripts](https://github.com/mtk-openwrt/openocd-scripts) and patched to comply with recent OpenOCD versions.

Clone with submodules:

```sh
git clone --recurse-submodules https://github.com/ProtopointLLC/bodybytes-firmware.git
```

## Dev shells

Requires Linux and [Nix](https://nixos.org/download/) with flakes enabled.

| Shell | Purpose |
|-------|---------|
| `nix develop .#uboot` | U-Boot build + OpenOCD/JTAG. Sets `CROSS_COMPILE`, `ARCH`, `OPENOCD_SCRIPTS`. |
| `nix develop .#openwrt` | OpenWRT host build. FHS environment; sets `AR`, `NM`, `RANLIB`, `FAKEROOTDONTTRYCHOWN`. |

## Firmware

The firmware runs OpenWrt as a standalone WiFi AP with no wired uplink. All services are local-only.

**Network**

| | Address |
|-|---------|
| Hostname | `bodybytes.local` (mDNS via avahi) |
| Gateway | `192.168.1.1` , `fd13:37be:ef00::1` |
| WiFi | WPA3/WPA2-mixed (SAE), 2.4 GHz 802.11n |

**HTTPS admin (LuCI)**

Reachable at `https://bodybytes.local`, `https://192.168.1.1`, or `https://fd13:37be:ef00::1`. EC P-256 self-signed certificate generated on first boot; all three access paths are covered by SANs so the browser only needs to accept the cert once.

**File sharing (Samba)**

`/mnt/data` (128 GB eMMC `data` partition) is shared read-write as a share named `data`.

## Development with VoCore2

The [VoCore2](https://vocore.io/v2.html) module uses the same MT7628AN SoC and can stand in as a lower-risk development board during U-Boot and OpenWrt bring-up. The bodybytes U-Boot and OpenWrt builds run on VoCore2 without modification; differences (128 MB RAM, 32 MB NOR, eMMC via adapter board, push-button recovery trigger) are handled by the `[board:vocore2]` profile in `scripts/config.ini`. See [docs/vocore2.md](docs/vocore2.md) for hardware differences, JTAG wiring, and WiFi calibration notes.

## Documentation

- [docs/building.md](docs/building.md) - build U-Boot and OpenWrt from source
- [docs/jtag.md](docs/jtag.md) - JTAG wiring, connectivity check, PLL/DRAM bootstrap
- [docs/uboot.md](docs/uboot.md) - U-Boot board files, NOR image, and env layout
- [docs/flashing.md](docs/flashing.md) - full first-install and sysupgrade procedures
- [docs/openwrt.md](docs/openwrt.md) - OpenWrt board files, DTS, and package reference
- [docs/wifi.md](docs/wifi.md) - WiFi EEPROM register map and calibration profile
- [docs/vocore2.md](docs/vocore2.md) - VoCore2 as development proxy: hardware differences, JTAG, NOR/eMMC, WiFi EEPROM calibration
