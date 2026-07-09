# OpenWRT — MT7628AN

Target: `ramips` / subtarget `mt76x8` — see [building.md](building.md) for build steps.

---

## 1 — Board files

`bodybytes.config` (at the repo root) seeds the target/board selection and board-specific Kconfig options. `CONFIG_EMMC_SUPPORT=y` ensures `emmc.sh` is included in the base-files package without affecting other mt76x8 boards.

All files below live in the `openwrt/` submodule; the submodule is pinned to a commit that includes these changes.

| File | Purpose |
|------|---------|
| `openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts` | Device tree |
| `openwrt/target/linux/ramips/image/mt76x8.mk` | Board profile: `DEVICE_PACKAGES` (includes `parted` for first-install partitioning from recovery), `IMAGE_SIZE`, `IMAGES`, `sysupgrade.bin` and `recovery.bin` build rules, `SUPPORTED_DEVICES` |
| `openwrt/target/linux/ramips/mt76x8/base-files/etc/config/fstab` | Global fstab config with `auto_mount 1`; `block-mount` uses this to auto-mount any labeled block device to `/mnt/<label>` at boot — the `data` partition mounts at `/mnt/data` without any board-specific config |
| `openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network` | Network board detection; bodybytes entry sets `label_mac` from the factory NOR partition (offset 0x4) — exposes the WiFi MAC as the device label MAC in LuCI. No wired interface config (Ethernet disabled in DTS) |
| `openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips` | U-Boot env tool config; the `bodybytes,bodybytes` case calls `ubootenv_add_mtd "u-boot-env" "0x0" "0x1000" "0x10000"`, which resolves the `u-boot-env` MTD partition by name at runtime and writes the resulting `/dev/mtdN` path into `/etc/fw_env.config` |
| `openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount` | Clears `upgrade_available=0` and `bootcount=0` unconditionally on every successful boot (START=99) |
| `openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh` | Sysupgrade dispatch; bodybytes case sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, arms the U-Boot bootcount (`upgrade_available=1 bootcount=0 bootlimit=3`), then calls `emmc_do_upgrade` to write the kernel to p1 and the squashfs rootfs to p2 |

### What the DTS sets

#### Board identity

```dts
compatible = "bodybytes,bodybytes", "mediatek,mt7628an-soc";
model = "Bodybytes";
```

The first compatible string is the board-specific identifier OpenWRT uses for board detection. The second is the fallback SoC match.

#### Console

```dts
chosen { bootargs = "console=ttyS2,115200"; }
```

UART2 = ttyS2. UART2 is routed to EPHY MDI_P2 pads (MDI_TP_P2 / MDI_TN_P2, SoC pins 47/48): `uart2_pins` sets `UART2_MODE=0`; `ephy-digital` (see below) sets `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1]=0xf` at pinctrl probe time, switching those pads from analog to digital mode.

#### SPI NOR flash — `&spi0`

W25Q512JV, 64 MB, CS0, 25 MHz. The OS lives on eMMC; NOR holds only the bootloader and the WiFi calibration EEPROM.

| Partition | Offset | Size | Notes |
|-----------|--------|------|-------|
| `u-boot` | `0x000000` | 256 KB | read-only |
| `u-boot-env` | `0x040000` | 64 KB | writable; `fw_setenv` from OpenWrt can update boot variables |
| `factory` | `0x050000` | 64 KB | read-only; 1 KB WiFi EEPROM at offset 0 |
| `recovery` | `0x060000` | 63.625 MB | read-only; OpenWrt initramfs kernel |

The `factory` partition exposes a 1 KB nvmem cell (`eeprom@0`) consumed by `&wmac`. If the partition is erased (all 0xFF) the driver falls back to the on-chip eFuse automatically. See `scripts/generate_nor_image.py` for how to build a factory blob with a custom MAC.

The kernel MTD spi-nor driver handles BAR (Bank Address Register) addressing for the W25Q512JV's four 16 MB regions automatically — no special DTS flag is needed.

#### Pin control — `&pinctrl`

**`ephy-digital`** — a property on the pinctrl node consumed by OpenWRT patch `809-pinctrl-mtmips-allow-mux-SDXC-pins-for-mt76x8`. It sets `AGPIO_CFG EPHY_APGIO_AIO_EN[4:1] = 0xf`, switching all four MDI pad groups (P1–P4) from analog Ethernet PHY mode to digital signal mode. Required by all three EPHY-routed functions below.

**`sdxc_iot_mode`** — two sub-groups:

| Sub-group | Register field | Value | Effect |
|-----------|---------------|-------|--------|
| `esd` → `iot` | `AGPIO_CFG ESD` bit | `iot` | Routes SDXC signals to EPHY pads |
| `sdmode` → `sdxc` | `GPIO_MODE SDMODE` | `sdxc` | Enables SDXC controller on those pads |

Together these mirror what `sd_iot_mode` does in `bodybytes_uboot.dtsi`, routing the SDXC data/cmd/clk lines to EPHY P3/P4 MDI pads (SoC pins 51–57).

**`mdi_p1_gpio`** — sets `GPIO_MODE SPIS = gpio`, switching MDI P1 pads to GPIO function. Makes MDI_TN_P1 (GPIO#15) driveable as the eMMC hardware reset output. Without this, the `emmc_pwrseq` GPIO write has no effect.

#### eMMC power sequencer

```dts
emmc_pwrseq: emmc_pwrseq {
    compatible = "mmc-pwrseq-emmc";
    reset-gpios = <&gpio 15 GPIO_ACTIVE_LOW>;
};
```

MDI_TN_P1 (SoC pin 42, GPIO#15, active-low). Pulsed low at power-up by the `mmc-pwrseq-emmc` driver to clear fault conditions. The eMMC RST_n function is disabled by default (EXT_CSD[162] = 0x00) so pulsing is a safe no-op; if the OS later enables RST_n the pulse will perform a real reset on subsequent power-ups.

#### eMMC — `&sdhci`

Kingston EMMC128-IY29-5B111, 128 GB eMMC 5.1, on EPHY P3/P4 MDI pads (SoC pins 51–57).

| Property | Value | Reason |
|----------|-------|--------|
| `pinctrl-0/1` | `sdxc_iot_mode mdi_p1_gpio` | Overrides base `sdxc_pins`; applies EPHY routing and SPIS GPIO mode |
| `non-removable` | — | Soldered eMMC; skips card-detect polling |
| `/delete-property/ cap-sd-highspeed` | — | Removes removable-SD capability from base dtsi |
| `mmc-pwrseq` | `emmc_pwrseq` | Links hardware reset GPIO |

`cap-mmc-highspeed`, `bus-width = <4>`, and `no-1-8-v` are inherited from `mt7628an.dtsi`. High Speed SDR mode (≤52 MHz, ≤52 MB/s) is the fastest mode the MT7628 SDXC controller supports at 3.3 V VCCQ; HS200/HS400 require 1.8 V and are unreachable regardless.

#### Ethernet — `&ethernet` / `&esw`

Both disabled. Bodybytes has no physical Ethernet ports; the MT7628 internal switch is unused.

#### UART2 — `&uart2`

```dts
&uart2 { status = "okay"; };
```

Enables the UART2 peripheral (ttyS2). `uart2_pins` (from `mt7628an.dtsi`) sets `UART2_MODE=0`; `ephy-digital` sets `AGPIO_CFG` to make the MDI P2 pads digital. Both are applied at pinctrl probe.

#### WiFi — `&wmac`

```dts
&wmac {
    nvmem-cells = <&eeprom_factory_0>;
    nvmem-cell-names = "eeprom";
    mediatek,eeprom-merge-otp;
};
```

Points the MT7628 integrated 2.4 GHz radio at the 1 KB EEPROM in the `factory` partition. `mediatek,eeprom-merge-otp` tells the mt7603 driver to overlay RF calibration fields (TX power, RSSI offsets, crystal trim) from the on-chip eFuse over the external EEPROM. This means only the chip ID and MAC address need to be present in the factory partition; all RF fields can be zero and the eFuse values fill them in.

If the factory partition is entirely erased (all 0xFF) the driver discards the external EEPROM and copies the eFuse wholesale, including whatever MAC MediaTek burned into the chip (often `0xFF:FF:FF:FF:FF:FF` on engineering samples). Always write a valid factory blob with your own MAC.

### Board profile

```makefile
define Device/bodybytes_bodybytes
  DEVICE_VENDOR := Bodybytes
  DEVICE_MODEL := Bodybytes
  IMAGE_SIZE := 120m
  IMAGES := sysupgrade.bin recovery.bin
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  IMAGE/recovery.bin := append-image-stage initramfs-kernel.bin | check-size
  DEVICE_PACKAGES := kmod-mmc-mtk block-mount kmod-fs-ext4 uboot-envtools parted
  SUPPORTED_DEVICES := bodybytes,bodybytes
endef
TARGET_DEVICES += bodybytes_bodybytes
```

`IMAGE_SIZE := 120m` bounds the `recovery.bin` (initramfs kernel) size against the NOR recovery partition (63.625 MB).

`IMAGE/sysupgrade.bin` uses `sysupgrade-tar | append-metadata` — the canonical form for all eMMC boards. `sysupgrade-tar` packages the regular kernel and squashfs rootfs as separate tar members (`sysupgrade-*/kernel` and `sysupgrade-*/root`). `emmc_do_upgrade` in `platform.sh` unpacks the tar and writes each member to its respective partition.

`IMAGE/recovery.bin` copies the already-built initramfs kernel (`initramfs-kernel.bin`) into an explicit build output via `append-image-stage`. This file is written to the NOR `recovery` partition at `0x060000` and is used by `scripts/generate_nor_image.py`.

`block-mount` provides the `block` binary and preinit scripts. `kmod-fs-ext4` provides the ext4 kernel module for the overlay and data partitions. `uboot-envtools` provides `fw_printenv` and `fw_setenv`; it is also copied into the sysupgrade ramfs by `platform.sh` (`RAMFS_COPY_BIN`). The `uboot-envtools/files/ramips` script populates `/etc/fw_env.config` at first boot by resolving the `u-boot-env` MTD partition by name, so no hardcoded device path is needed. `parted` is included so the recovery initramfs can partition a fresh eMMC before the first sysupgrade (see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)).

`block-mount` with `auto_mount 1` (set in the subtarget fstab) auto-mounts the `data` partition at `/mnt/data` via `blkid` label scanning — no board-specific config required. The `rootfs_data` overlay partition is handled by libfstools (by GPT label) independently. See [flashing.md §5c](flashing.md#5c--openwrt-storage-mounts) for details.

---

## 2 — Sysupgrade

`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh` dispatches `sysupgrade` per board name. The bodybytes case:

```sh
bodybytes,bodybytes)
    CI_KERNPART="kernel"
    CI_ROOTPART="rootfs"
    CI_DATAPART="rootfs_data"
    fw_setenv upgrade_available 1
    fw_setenv bootcount 0
    fw_setenv bootlimit 3
    emmc_do_upgrade "$1"
    ;;
```

`sysupgrade` calls `platform_do_upgrade` with the new image path. Before writing the image, the bodybytes case arms the U-Boot bootcount mechanism via three `fw_setenv` calls:

| Variable | Value | Purpose |
|----------|-------|---------|
| `upgrade_available` | `1` | Arms U-Boot bootcount; counting starts on next boot |
| `bootcount` | `0` | Resets the counter for the new firmware |
| `bootlimit` | `3` | Recovery triggers when `bootcount > 3` (i.e., on the 4th failed boot) |

`emmc_do_upgrade` (from `/lib/upgrade/emmc.sh`, sourced via `include /lib/upgrade` in `do_stage2`) unpacks the sysupgrade tar and writes:
- `sysupgrade-*/kernel` → GPT partition labelled `kernel` (`CI_KERNPART`, found via `/sys/block/mmcblk*/uevent`, not a hardcoded device path)
- `sysupgrade-*/root` → GPT partition labelled `rootfs` (`CI_ROOTPART`)

It also zeros 8 sectors past each written member to prevent stale content from being misread. `CI_DATAPART="rootfs_data"` tells `emmc_copy_config` where to store the sysupgrade config backup — it is written to the `rootfs_data` partition at the block offset recorded in `$EMMC_ROOTFS_BLOCKS`.

The env partition is pre-programmed with `bootcmd`, `altbootcmd`, and all other boot variables by `scripts/generate_nor_image.py` at NOR image build time. `fw_setenv` read-modify-writes the partition and preserves all other variables, so `platform.sh` only needs to write the three bootcount variables.

The `init.d/bootcount` script (START=99) runs near the end of every successful OpenWrt boot and unconditionally resets `upgrade_available=0` and `bootcount=0` via `fw_setenv`. All other env variables are preserved by `fw_setenv`'s read-modify-write behaviour.

The default fallback (`default_do_upgrade`) writes to an MTD partition named `firmware`, which does not exist on bodybytes. Without the bodybytes case, sysupgrade would fail at runtime.

See [uboot.md — Boot counter](uboot.md#boot-counter-failed-boot-recovery) for the U-Boot side of this mechanism.
