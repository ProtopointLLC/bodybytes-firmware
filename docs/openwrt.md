# OpenWRT — MT7628AN

Target: `ramips` / subtarget `mt76x8` — see [building.md](building.md) for build steps.

---

## 1 — Board files

[`bodybytes.config`](../bodybytes.config) (at the repo root) seeds the target/board selection and board-specific Kconfig options. `CONFIG_EMMC_SUPPORT=y` ensures `emmc.sh` is included in the base-files package without affecting other mt76x8 boards. `CONFIG_SAMBA4_SERVER_AVAHI=y` builds samba4 with avahi client support so smbd registers and deregisters `_smb._tcp` with avahi-daemon dynamically via D-Bus rather than requiring a static service file. `CONFIG_IMAGEOPT=y` and `CONFIG_VERSIONOPT=y` are required to activate the `VERSION_MANUFACTURER`, `VERSION_PRODUCT`, and `VERSION_MANUFACTURER_URL` symbols — without them those symbols live inside an `if VERSIONOPT` block and are silently dropped by Kconfig regardless of their values.

`CONFIG_TARGET_MULTI_PROFILE=y` is required to build both device profiles in one `make` run. Without it, the device symbols (`CONFIG_TARGET_ramips_mt76x8_DEVICE_*`) live in a Kconfig `choice` block — only the last one set wins and the first is silently dropped. With `MULTI_PROFILE`, the build system switches to independent `CONFIG_TARGET_DEVICE_ramips_mt76x8_DEVICE_*` bool symbols (note the leading `DEVICE_` before the subtarget name) that can both be set simultaneously. See `include/image.mk:585` (`DEVICE_CHECK_PROFILE`) for the conditional expansion.

All files below live in the `openwrt/` submodule; the submodule is pinned to a commit that includes these changes.

| File | Purpose |
|------|---------|
| [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi) | Device tree (shared by both profiles) — thin `.dts` wrappers [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts) and [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts) include it |
| [`openwrt/target/linux/ramips/image/mt76x8.mk`](../openwrt/target/linux/ramips/image/mt76x8.mk) | Board profile: `DEVICE_PACKAGES` (includes `parted` for first-install partitioning from recovery), `IMAGE_SIZE`, `IMAGES`, `sysupgrade.bin` and `recovery.bin` build rules, `SUPPORTED_DEVICES` |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults) | First-boot board defaults: hostname; WiFi SSID, country, WPA3-mixed encryption (`sae-mixed`, key `bodybytes`); fstab mount for `data` partition at `/mnt/data`; Samba description and `/mnt/data` share (guarded on `/etc/config/samba4`); collectd disk/tcpconns/processes enables and RRD path `/srv/collectd/rrd` (guarded on `/etc/config/luci_statistics`) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network) | Network board detection; bodybytes entry sets `label_mac` from the factory NOR partition (offset 0x4) — exposes the WiFi MAC as the device label MAC in LuCI. No wired interface config (Ethernet disabled in DTS) |
| [`openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips`](../openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips) | U-Boot env tool config; the `bodybytes,bodybytes` case calls `ubootenv_add_mtd "u-boot-env" "0x0" "0x1000" "0x10000"`, which resolves the `u-boot-env` MTD partition by name at runtime and writes the resulting `/dev/mtdN` path into `/etc/fw_env.config` |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount) | Clears `upgrade_available=0` and `bootcount=0` unconditionally on every successful boot (START=99) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) | Sysupgrade dispatch; bodybytes case sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, arms the U-Boot bootcount (`upgrade_available=1 bootcount=0 bootlimit=3`), then calls `emmc_do_upgrade` to write the kernel to p1 and the squashfs rootfs to p2 |

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

The `factory` partition exposes a 1 KB nvmem cell (`eeprom@0`) consumed by `&wmac`. If the partition is erased (all 0xFF) the driver falls back to the on-chip eFuse automatically. See [`scripts/generate_nor_image.py`](../scripts/generate_nor_image.py) for how to build a factory blob with a custom MAC.

The kernel MTD spi-nor driver handles BAR (Bank Address Register) addressing for the W25Q512JV's four 16 MB regions automatically — no special DTS flag is needed.

#### Pin control — `&pinctrl`

**`ephy-digital`** — a property on the pinctrl node consumed by OpenWRT patch `809-pinctrl-mtmips-allow-mux-SDXC-pins-for-mt76x8`. It sets `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1] = 0xf`, switching all four MDI pad groups (P1–P4) from analog Ethernet PHY mode to digital signal mode. Required by all three EPHY-routed functions below.

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

8-bit bus width (`bus-width = <8>`) is not possible: the four additional data lines (SD_D4–SD_D7) would require `groups = "uart2"; function = "sdxc d5 d4"` (as defined in `emmc_iot_8bit_mode` in the dtsi), which conflicts with UART2 as the system console.

#### Boot mode selector — `keys`

```dts
keys {
    compatible = "gpio-keys";

    boot-mode {
        label = "boot-mode";
        linux,code = <BTN_0>;
        gpios = <&gpio 14 GPIO_ACTIVE_LOW>;
    };
};
```

MDI_TP_P1 (SoC pin 43, GPIO#14) — TI DRV5032FCDBZT hall-effect sensor, active-low (magnet present = low = pressed). U-Boot reads this GPIO at boot to choose normal vs. recovery boot; the `gpio-keys` node exposes the physical state to Linux via the input subsystem so userspace can observe it without polling.

The `button-hotplug` module maps `BTN_0` → `BUTTON=BTN_0`. Hotplug scripts in `/etc/hotplug.d/button/` match on `[ "$BUTTON" = "BTN_0" ]`. The DTS `label` is used only as the GPIO consumer description in `/sys/kernel/debug/gpio`; it does not affect `BUTTON=`.

GPIO#14 is on the same MDI P1 pad group as GPIO#15 (eMMC reset), so `mdi_p1_gpio` pinctrl state (which sets `SPIS_MODE=gpio`) is required for both. The `gpio-keys` driver claims GPIO#14 at probe time, preventing accidental userspace re-export.

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

### Board profiles

Two device profiles are defined, enabled by `CONFIG_TARGET_PER_DEVICE_ROOTFS=y`. Each starts from the full `.config` package set and applies per-device package additions.

```makefile
BODYBYTES_PACKAGES := kmod-mmc-mtk block-mount kmod-fs-ext4 uboot-envtools \
  openssh-sftp-server rsync e2fsprogs avahi-daemon lsblk \
  -wpad-basic-mbedtls wpad-openssl \
  luci-ssl-openssl

define Device/bodybytes_bodybytes
  DEVICE_VENDOR := Bodybytes
  DEVICE_MODEL := Bodybytes
  IMAGE_SIZE := 544m
  IMAGES := sysupgrade.bin
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata | check-size
  DEVICE_PACKAGES := $(BODYBYTES_PACKAGES) \
    samba4-server luci-app-samba4 \
    luci-app-statistics \
    collectd-mod-cpu collectd-mod-load collectd-mod-memory \
    collectd-mod-disk collectd-mod-interface collectd-mod-iwinfo \
    collectd-mod-tcpconns collectd-mod-processes \
    iperf3 luci-app-ttyd luci-app-nlbwmon
  SUPPORTED_DEVICES := bodybytes,bodybytes
endef
TARGET_DEVICES += bodybytes_bodybytes

define Device/bodybytes_bodybytes_recovery
  DEVICE_VENDOR := Bodybytes
  DEVICE_MODEL := Bodybytes
  DEVICE_VARIANT := Recovery
  IMAGE_SIZE := 65152k
  IMAGES := recovery.bin
  IMAGE/recovery.bin := append-image-stage initramfs-kernel.bin | check-size
  DEVICE_PACKAGES := $(BODYBYTES_PACKAGES) parted
  SUPPORTED_DEVICES := bodybytes,bodybytes
endef
TARGET_DEVICES += bodybytes_bodybytes_recovery
```

`BODYBYTES_PACKAGES` is a shared Make variable holding the packages common to both profiles — the same pattern used by `USB2_PACKAGES` in `bcm47xx`.

`IMAGE_SIZE := 544m` for the sysupgrade profile reflects the actual eMMC GPT layout: 32 MiB kernel partition + 512 MiB rootfs partition. `check-size` enforces this at build time.

`IMAGE_SIZE := 65152k` for the recovery profile matches the NOR `recovery` partition exactly (63.625 MB = `0x3FA0000` bytes). `check-size` rejects an initramfs that would overflow the NOR partition.

`DEVICE_VARIANT := Recovery` distinguishes the recovery profile in the build system without modifying `DEVICE_MODEL`. The primary sysupgrade profile has no variant.

`IMAGE/sysupgrade.bin` uses `sysupgrade-tar | append-metadata | check-size` — the canonical form for all eMMC boards. `sysupgrade-tar` packages the regular kernel and squashfs rootfs as separate tar members (`sysupgrade-*/kernel` and `sysupgrade-*/root`). `emmc_do_upgrade` in `platform.sh` unpacks the tar and writes each member to its respective partition.

#### Raw kernel partition vs. FAT/distro boot

GPT partition 1 (`kernel`) holds a raw uImage blob with no filesystem. U-Boot locates it with `part start`/`part size` and loads it with `mmc read` — no filesystem driver required. The alternative, a FAT boot partition with extlinux.conf (U-Boot distro boot / `bootflow scan`), is not used because `emmc_do_upgrade` performs a raw `dd` write directly to `/dev/mmcblkNpN`: it would overwrite and destroy a FAT filesystem on every sysupgrade. Supporting distro boot would require a filesystem-aware kernel update in `platform.sh`, `kmod-fs-vfat` in the recovery image, and extlinux.conf management — added complexity with no benefit for a single-OS device with a fixed GPT layout. The raw partition approach is consistent with all other ramips/MT7628 boards in OpenWrt.

`IMAGE/recovery.bin` copies the already-built initramfs kernel (`initramfs-kernel.bin`) into an explicit build output via `append-image-stage`. This file is written to the NOR `recovery` partition at `0x060000` and is used by [`scripts/generate_nor_image.py`](../scripts/generate_nor_image.py).

`block-mount` provides the `block` binary and preinit scripts. `kmod-fs-ext4` provides the ext4 kernel module for the overlay and data partitions. `uboot-envtools` provides `fw_printenv` and `fw_setenv`; it is also copied into the sysupgrade ramfs by `platform.sh` (`RAMFS_COPY_BIN`). The `uboot-envtools/files/ramips` script populates `/etc/fw_env.config` at first boot by resolving the `u-boot-env` MTD partition by name, so no hardcoded device path is needed.

**`BODYBYTES_PACKAGES`** (both profiles):
- `openssh-sftp-server` + `rsync` — needed in recovery to transfer a sysupgrade image into the device before flashing.
- `avahi-daemon` — advertises `bodybytes.local` via mDNS; useful in recovery where the user has no easy way to find the device IP.
- `e2fsprogs` — `e2fsck`/`resize2fs`/`tune2fs` for ext4 maintenance on the data partition and for `mkfs.ext4` after `parted` creates partitions in recovery.
- `lsblk` — inspects block device layout, partition labels, and mount points.
- `-wpad-basic-mbedtls wpad-openssl` — swaps the subtarget default for the full WPA supplicant/hostapd build with OpenSSL; required for WPA3 (SAE) and 802.11r. The MT7628AN mt76 driver sets `IEEE80211_HW_MFP_CAPABLE` via the shared mt76 framework (`mac80211.c:476`), confirming hardware 802.11w support.
- `luci-ssl-openssl` — LuCI collection package that pulls in `luci-light`, `libustream-openssl`, and `openssl-util`. Enables HTTPS for the LuCI web interface; uhttpd listens on both port 80 (HTTP, redirects to HTTPS) and port 443. OpenSSL is already in the image from `wpad-openssl` so this adds only the ustream TLS glue and the `openssl` tool used for certificate generation. Replaces `libustream-mbedtls` as the ustream TLS backend.

**Main profile only:**
- `samba4-server` + `luci-app-samba4` — SMB file sharing; compatible with Windows, macOS, iOS, and Android.
- `luci-app-statistics` + `collectd-mod-{cpu,load,memory,disk,interface,iwinfo,tcpconns,processes}` — system, storage, WiFi, and TCP connection metrics in LuCI. `collectd-mod-ping` is excluded — the device has no upstream internet connection and is a local-only AP.
- `iperf3` — network throughput benchmarking; run `iperf3 -s` on device, `iperf3 -c bodybytes.local` from a client to measure WiFi throughput under load.
- `luci-app-ttyd` — web terminal in LuCI; provides browser-based shell access without SSH, critical once the device is implanted and serial is inaccessible.
- `luci-app-nlbwmon` — per-client bandwidth tracking in LuCI.

**Recovery profile only:**
- `parted` — partitions a fresh eMMC before the first sysupgrade (see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)).

**`90_defaults` UCI configuration** (first boot, board-gated):
- System: `hostname=bodybytes`
- WiFi: `ssid=Bodybytes`, `country=US`, `encryption=sae-mixed`, `key=bodybytes` (change via LuCI before use)
- Network: fixed ULA prefix `fd13:37be:ef00::/48` ("1337beef") overriding OpenWrt's `ula_prefix=auto`. A fixed prefix is safe because bodybytes is an isolated AP — no other device will ever share this ULA space. `ip6assign=64` tells netifd to assign the first /64 of that prefix to `br-lan`; the router's address is always `fd13:37be:ef00::1`.
- DHCP/IPv6: `dhcpv6=server`, `ra=server`, `ra_slaac=1` on the LAN — odhcpd provides DHCPv6 and Router Advertisements with SLAAC so clients auto-configure their IPv6 addresses without explicit assignment.
- TLS certificate: EC P-256 self-signed cert generated via `openssl req` on first boot, valid 10 years. SANs: `DNS:bodybytes.local`, `DNS:bodybytes`, `IP:192.168.1.1`, `IP:fd13:37be:ef00::1`. Covers all access paths (mDNS hostname over IPv4 and IPv6, IPv4 gateway, ULA router address). uhttpd (START=80) generates a generic cert before this script runs (START=95); the script overwrites it and restarts uhttpd to pick up the custom cert.
- fstab: explicit mount entry for the `data` partition at `/mnt/data` (`label=data`, `fstype=ext4`, `options=noatime`, `enabled=1`)
- Samba (guarded on `/etc/config/samba4`): sets description to `Bodybytes`; adds a read-write guest share for `/mnt/data`. mDNS/Bonjour advertisement of `_smb._tcp` is handled by smbd itself via the avahi client library (`CONFIG_SAMBA4_SERVER_AVAHI=y`) — smbd registers with avahi-daemon over D-Bus when it starts and deregisters when it stops; no static service file is needed.
- collectd (guarded on `/etc/config/luci_statistics`): enables `collectd_disk` (monitoring `mmcblk0`), `collectd_tcpconns` (ports 22 and 445, `AllPortsSummary=1`), `collectd_processes` (smbd, nmbd, dnsmasq, dropbear, uhttpd, avahi-daemon, collectd); sets RRD `DataDir` to `/srv/collectd/rrd` — persisted on `rootfs_data` via overlayfs, outside the Samba share. collectd creates the directory on first write.

The `data` partition is mounted at `/mnt/data` via an explicit fstab entry written by `90_defaults` on first boot (`uci add fstab mount` with `label=data`, `target=/mnt/data`, `fstype=ext4`, `options=noatime`, `enabled=1`). The `block` daemon creates `/mnt/data` automatically at mount time. The `rootfs_data` overlay partition is handled by libfstools (matched by GPT label) independently.

---

## 2 — Sysupgrade

[`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) dispatches `sysupgrade` per board name. The bodybytes case:

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

The env partition is pre-programmed with `bootcmd`, `altbootcmd`, and all other boot variables by [`scripts/generate_nor_image.py`](../scripts/generate_nor_image.py) at NOR image build time. `fw_setenv` read-modify-writes the partition and preserves all other variables, so [`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) only needs to write the three bootcount variables.

The `init.d/bootcount` script (START=99) runs near the end of every successful OpenWrt boot and unconditionally resets `upgrade_available=0` and `bootcount=0` via `fw_setenv`. All other env variables are preserved by `fw_setenv`'s read-modify-write behaviour.

The default fallback (`default_do_upgrade`) writes to an MTD partition named `firmware`, which does not exist on bodybytes. Without the bodybytes case, sysupgrade would fail at runtime.

See [uboot.md — Boot counter](uboot.md#boot-counter-failed-boot-recovery) for the U-Boot side of this mechanism.
