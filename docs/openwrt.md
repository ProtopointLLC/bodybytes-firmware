# OpenWRT - MT7628AN

Target: `ramips` / subtarget `mt76x8` - see [building.md](building.md) for build steps.

---

## 1 - Board files

[`bodybytes.config`](../bodybytes.config) (at the repo root) seeds the target/board selection and board-specific Kconfig options. `CONFIG_EMMC_SUPPORT=y` ensures `emmc.sh` is included in the base-files package without affecting other mt76x8 boards. `CONFIG_SAMBA4_SERVER_AVAHI=y` builds samba4 with avahi client support so smbd registers and deregisters `_smb._tcp` with avahi-daemon dynamically via D-Bus rather than requiring a static service file. `CONFIG_IMAGEOPT=y` and `CONFIG_VERSIONOPT=y` are required to activate the `VERSION_MANUFACTURER`, `VERSION_PRODUCT`, and `VERSION_MANUFACTURER_URL` symbols - without them those symbols live inside an `if VERSIONOPT` block and are silently dropped by Kconfig regardless of their values.

`CONFIG_TARGET_MULTI_PROFILE=y` is required to build both device profiles in one `make` run. Without it, the device symbols (`CONFIG_TARGET_ramips_mt76x8_DEVICE_*`) live in a Kconfig `choice` block - only the last one set wins and the first is silently dropped. With `MULTI_PROFILE`, the build system switches to independent `CONFIG_TARGET_DEVICE_ramips_mt76x8_DEVICE_*` bool symbols (note the leading `DEVICE_` before the subtarget name) that can both be set simultaneously. See `include/image.mk:585` (`DEVICE_CHECK_PROFILE`) for the conditional expansion.

All files below live in the `openwrt/` submodule; the submodule is pinned to a commit that includes these changes.

| File | Purpose |
|------|---------|
| [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi) | Device tree (shared by both profiles) - thin `.dts` wrappers [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts) and [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts) include it |
| [`openwrt/target/linux/ramips/image/mt76x8.mk`](../openwrt/target/linux/ramips/image/mt76x8.mk) | Board profile: `DEVICE_DTS`, `KERNEL` (FIT image pipeline), `DEVICE_PACKAGES` (includes `parted` for first-install partitioning from recovery), `IMAGE_SIZE`, `IMAGES`, `sysupgrade.bin` and `recovery.bin` build rules, `SUPPORTED_DEVICES` |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults) | First-boot board defaults: hostname; WiFi SSID, country, WPA3-mixed encryption (`sae-mixed`, key `bodybytes`); fstab mount for `data` partition at `/mnt/data`; Samba description and `/mnt/data` share (guarded on `/etc/config/samba4`); collectd disk/tcpconns/processes enables and RRD path `/srv/collectd/rrd` (guarded on `/etc/config/luci_statistics`) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network) | Network board detection; bodybytes entry sets `label_mac` from the factory NOR partition (offset 0x4) - exposes the WiFi MAC as the device label MAC in LuCI. No wired interface config (Ethernet disabled in DTS) |
| [`openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips`](../openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips) | U-Boot env tool config; the `bodybytes,bodybytes` case calls `ubootenv_add_mtd "u-boot-env" "0x0" "0x1000" "0x10000"`, which resolves the `u-boot-env` MTD partition by name at runtime and writes the resulting `/dev/mtdN` path into `/etc/fw_env.config` |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount) | Resets the SYSCTL MEMO2 bootcount register to zero (`devmem 0x1000006c 32 0xB0010000`) on every successful boot (START=99) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) | Sysupgrade dispatch; `platform_check_image` rejects non-sysupgrade-tar images (no `CONTROL` entry) and fails if the `kernel` or `rootfs` GPT partitions are not yet present on the eMMC; bodybytes case sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, resets the SYSCTL MEMO2 bootcount register to zero via `devmem` (no NOR write), then calls `emmc_do_upgrade` to write the kernel to p1 and the squashfs rootfs to p2; `platform_copy_config` dispatches to `emmc_copy_config` to save the sysupgrade config backup into the `rootfs_data` partition |

### What the DTS sets

#### Board identity

Sets `compatible = "bodybytes,bodybytes", "mediatek,mt7628an-soc"` and `model = "Bodybytes"`. The first compatible string is the board-specific identifier OpenWRT uses for board detection; the second is the fallback SoC match.

#### Console

`chosen.bootargs` is set to `"console=ttyS0,115200"`. UART2 becomes ttyS0 because `&uartlite` (UART0) is disabled in the DTS, so UART2 is the only registered serial device and gets ttyS0. UART2 is routed to EPHY MDI_P2 pads (MDI_TP_P2 / MDI_TN_P2, SoC pins 47/48): `uart2_pins` sets `UART2_MODE=0`; `ephy-digital` (see below) sets `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1]=0xf` at pinctrl probe time, switching those pads from analog to digital mode.

#### SPI NOR flash - `&spi0`

W25Q512JV, 64 MB, CS0, 25 MHz. The OS lives on eMMC; NOR holds only the bootloader and the WiFi calibration EEPROM.

| Partition | Offset | Size | Notes |
|-----------|--------|------|-------|
| `u-boot` | `0x000000` | 256 KB | read-only |
| `u-boot-env` | `0x040000` | 64 KB | read-only; contains `bootlimit=3`, `altbootcmd`, and other boot variables; never written by OpenWrt |
| `factory` | `0x050000` | 64 KB | read-only; 1 KB WiFi EEPROM at offset 0 |
| `recovery` | `0x060000` | 63.625 MB | read-only; OpenWrt initramfs kernel |

The `factory` partition exposes a 1 KB nvmem cell (`eeprom@0`) consumed by `&wmac`. If the partition is erased (all 0xFF) the driver falls back to the on-chip eFuse automatically. [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) generates the factory blob on the fly; pass `--mac XX:XX:XX:XX:XX:XX` to override the default MAC from `config.ini`.

The kernel MTD spi-nor driver handles BAR (Bank Address Register) addressing for the W25Q512JV's four 16 MB regions automatically - no special DTS flag is needed.

**All four NOR partitions carry `read-only;` in the DTS.** This is intentional: the boot scripts (`u-boot`, `u-boot-env`, `altbootcmd`, `bootcmd`, `boot_sf`, …) and the WiFi calibration EEPROM (`factory`) live entirely on NOR. Mounting the env partition read-write from Linux exposes every script that runs as root to accidentally corrupting the bootloader environment - a mistake that bricks the device with no software recovery path. Making all NOR partitions read-only at the kernel MTD layer prevents any process (including a shell running as root) from overwriting them without a deliberate, multi-step workaround.

The bootcount mechanism does not write to NOR at all - it uses the SYSCTL MEMO2 register (see [Sysupgrade](#2--sysupgrade)), so the read-only constraint does not affect sysupgrade or the failed-boot watchdog.

**Escape hatch - writing to NOR from a running OpenWrt system**

The normal path for updating NOR is via JTAG with [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py). If NOR must be updated from a live system (e.g. to reflash the recovery partition or update the WiFi EEPROM over SSH), install `kmod-mtd-rw` from the `packages` feed (`feeds/packages/kernel/mtd-rw`) and load it with `insmod mtd-rw i_want_a_brick=1`. The `i_want_a_brick=1` parameter is a mandatory acknowledgement; the module refuses to load without it. Once loaded, it clears the `MTD_WRITEABLE` restriction kernel-side, making all NOR partitions writable by normal MTD tools (`mtd`, `dd`, `fw_setenv`). Remove with `rmmod mtd-rw` to restore read-only protection; a reboot also removes it.

`kmod-mtd-rw` is not included in `BODYBYTES_PACKAGES` - it must be installed explicitly when needed and should be removed afterwards.

#### Pin control - `&pinctrl`

**`ephy-digital`** - a property on the pinctrl node consumed by OpenWRT patch `809-pinctrl-mtmips-allow-mux-SDXC-pins-for-mt76x8`. It sets `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1] = 0xf`, switching all four MDI pad groups (P1–P4) from analog Ethernet PHY mode to digital signal mode. Required by all three EPHY-routed functions below.

**`sdxc_iot_mode`** - two sub-groups:

| Sub-group | Register field | Value | Effect |
|-----------|---------------|-------|--------|
| `esd` → `iot` | `AGPIO_CFG ESD` bit | `iot` | Routes SDXC signals to EPHY pads |
| `sdmode` → `sdxc` | `GPIO_MODE SDMODE` | `sdxc` | Enables SDXC controller on those pads |

Together these mirror what `sd_iot_mode` does in `bodybytes_uboot.dtsi`, routing the SDXC data/cmd/clk lines to EPHY P3/P4 MDI pads (SoC pins 51–57).

**`mdi_p1_gpio`** - sets `GPIO_MODE SPIS = gpio`, switching MDI P1 pads to GPIO function. Makes MDI_TN_P1 (GPIO#15) driveable as the eMMC hardware reset output. Without this, the `emmc_pwrseq` GPIO write has no effect.

#### eMMC power sequencer

A `mmc-pwrseq-emmc` node wired to `reset-gpios = <&gpio 15 GPIO_ACTIVE_LOW>`. MDI_TN_P1 (SoC pin 42, GPIO#15) is pulsed low at power-up by the `mmc-pwrseq-emmc` driver to clear fault conditions. The eMMC RST_n function is disabled by default (EXT_CSD[162] = 0x00) so pulsing is a safe no-op; if the OS later enables RST_n the pulse will perform a real reset on subsequent power-ups.

#### eMMC - `&sdhci`

Kingston EMMC128-IY29-5B111, 128 GB eMMC 5.1, on EPHY P3/P4 MDI pads (SoC pins 51–57).

| Property | Value | Reason |
|----------|-------|--------|
| `pinctrl-0` | `sdxc_iot_mode mdi_p1_gpio` | Overrides base `sdxc_pins`; applies EPHY routing and SPIS GPIO mode |
| `vmmc-supply` | `reg_3v3` | Explicit 3.3 V supply for eMMC VCC; without this the mtk-msdc driver cannot negotiate voltage and fails with `no support for card's volts` |
| `vqmmc-supply` | `reg_3v3` | Explicit 3.3 V supply for eMMC VCCQ (I/O signalling) |
| `no-1-8-v` | - | Prevents voltage-switch negotiation to 1.8 V; MT7628 SDXC runs at 3.3 V only |
| `mediatek,cd-poll` | - | Software card-detect polling; used instead of `non-removable` for compatibility with the removable Hardkernel eMMC module on VoCore2 |
| `mmc-pwrseq` | `emmc_pwrseq` | Links hardware reset GPIO (GPIO#15, MDI_TN_P1) |

`cap-mmc-highspeed` and `bus-width = <4>` are inherited from `mt7628an.dtsi`. High Speed SDR mode (≤52 MHz, ≤52 MB/s) is the fastest mode the MT7628 SDXC controller supports at 3.3 V VCCQ; HS200/HS400 require 1.8 V and are unreachable regardless.

8-bit bus width (`bus-width = <8>`) is not possible: the four additional data lines (SD_D4–SD_D7) would require `groups = "uart2"; function = "sdxc d5 d4"` (as defined in `emmc_iot_8bit_mode` in the dtsi), which conflicts with UART2 as the system console.

#### Boot mode selector - `keys`

A `gpio-keys` node exposes a `boot-mode` button on `gpios = <&gpio 14 GPIO_ACTIVE_LOW>` with `linux,code = <BTN_0>`. MDI_TP_P1 (SoC pin 43, GPIO#14) is driven by a TI DRV5032FCDBZT hall-effect sensor — magnet present = low = pressed. U-Boot reads this GPIO at boot to choose normal vs. recovery boot; the `gpio-keys` node exposes the physical state to Linux via the input subsystem so userspace can observe it without polling.

The `button-hotplug` module maps `BTN_0` → `BUTTON=BTN_0`. Hotplug scripts in `/etc/hotplug.d/button/` match on `[ "$BUTTON" = "BTN_0" ]`. The DTS `label` is used only as the GPIO consumer description in `/sys/kernel/debug/gpio`; it does not affect `BUTTON=`.

GPIO#14 is on the same MDI P1 pad group as GPIO#15 (eMMC reset), so `mdi_p1_gpio` pinctrl state (which sets `SPIS_MODE=gpio`) is required for both. The `gpio-keys` driver claims GPIO#14 at probe time, preventing accidental userspace re-export.

#### Ethernet - `&ethernet` / `&esw`

Both disabled. Bodybytes has no physical Ethernet ports; the MT7628 internal switch is unused.

#### UART0 - `&uartlite`

UART0 is disabled (`status = "disabled"`). `mt7628an.dtsi` leaves `uartlite` enabled by default; bodybytes has no UART0 connection on the board. Disabling it ensures UART2 registers as ttyS0 (Linux assigns ttyS numbers in probe order - with only UART2 active, it becomes the first and only serial device).

#### 3.3 V regulator - `reg_3v3`

A `regulator-fixed` node providing a permanent 3.3 V rail (`regulator-always-on`), referenced by `vmmc-supply` and `vqmmc-supply` on `&sdhci`. The MT7628 SDXC controller is hard-wired to 3.3 V; declaring the regulator explicitly prevents the mtk-msdc driver from attempting voltage negotiation and failing with `no support for card's volts`.

#### UART2 - `&uart2`

Enabled (`status = "okay"`). Becomes ttyS0 since UART0 is disabled. `uart2_pins` (from `mt7628an.dtsi`) sets `UART2_MODE=0`; `ephy-digital` sets `AGPIO_CFG` to make the MDI P2 pads digital. Both are applied at pinctrl probe.

#### WiFi - `&wmac`

Three key properties: `nvmem-cells = <&eeprom_factory_0>` and `nvmem-cell-names = "eeprom"` wire the WiFi calibration EEPROM to the 1 KB cell from the `factory` NOR partition; `mediatek,eeprom-merge-otp` overlays only RF calibration fields from the on-chip eFuse onto the external EEPROM data while preserving the MAC address from the factory partition.

**Driver stack:** The MT7628AN's integrated 2.4 GHz radio (`wmac@10300000`, compatible `"mediatek,mt7628-wmac"`) is driven by `mt7603e.ko` from the mt76 package. The driver binds via the DTS platform device path — not PCI. `kmod-mt7603` is in the mt76x8 subtarget's `DEFAULT_PACKAGES` and is automatically included in every build; no explicit package entry is needed in `BODYBYTES_PACKAGES`.

**Firmware blobs:** MT7628 WiFi requires two firmware files at `/lib/firmware/mt7628_e1.bin` and `/lib/firmware/mt7628_e2.bin` (ECO revision 1 and 2 respectively). These are **bundled in the mt76 package** — the `kmod-mt7603` install rule detects `CONFIG_TARGET_ramips_mt76x8` at build time and copies the `mt7628_*` variants instead of the MT7603-card variants. No external blob source is needed; the files are built from the mt76 source tree.

**EEPROM load path:** `mt76_eeprom_init()` calls `mt76_get_of_eeprom()`, which tries three sources in order: embedded DT data → MTD partition → nvmem cell. For bodybytes, the nvmem path succeeds: `of_nvmem_cell_get(np, "eeprom")` resolves `nvmem-cell-names = "eeprom"` to the `eeprom_factory_0` cell (`factory` partition offset 0, size 0x400). `MT7603_EEPROM_SIZE = 1024 = 0x400` matches exactly.

**`mediatek,eeprom-merge-otp`:** After loading the external EEPROM, `mt7603_eeprom_init()` reads the on-chip eFuse OTP. If the external EEPROM passes the validity check, it overlays only the RF calibration fields (TX power, RSSI offsets, crystal trim) from the eFuse onto the EEPROM data — the MAC address and chip ID stay from the external EEPROM. If the factory partition is entirely erased (all 0xFF), the driver copies the eFuse wholesale, including whatever MAC MediaTek burned into the chip (often `0xFF:FF:FF:FF:FF:FF` on engineering samples). Always write a valid factory blob with your own MAC.

See [docs/wifi.md](wifi.md) for the EEPROM register map, field documentation, and `config.ini` key reference.

### Board profiles

Two device profiles are defined, enabled by `CONFIG_TARGET_PER_DEVICE_ROOTFS=y`. Each starts from the full `.config` package set and applies per-device package additions.

`BODYBYTES_PACKAGES` is a shared Make variable holding the packages common to both profiles - the same pattern used by `USB2_PACKAGES` in `bcm47xx`. The **main profile** (`bodybytes_bodybytes`) produces `sysupgrade.bin` via `sysupgrade-tar | append-metadata | check-size` with `IMAGE_SIZE := 544m` (32 MiB kernel + 512 MiB rootfs partitions). The **recovery profile** (`bodybytes_bodybytes_recovery`) produces `recovery.bin` via `append-image-stage initramfs-kernel.bin | check-size` with `IMAGE_SIZE := 65152k`, matching the NOR `recovery` partition exactly (63.625 MB). `DEVICE_VARIANT := Recovery` distinguishes the recovery profile without modifying `DEVICE_MODEL`.

The kernel pipeline `kernel-bin | lzma | fit lzma <dtb>` produces a FIT image (`.itb`) containing an LZMA-compressed kernel image node and a flat DTB node. U-Boot's `bootm ${kernel_addr_r}` verifies and extracts both, applies standard fixups (writes detected memory into `/memory`, merges `bootargs` into `/chosen/bootargs`), then jumps to the kernel entry point. No separate DTB file is needed on the eMMC kernel partition.

GPT partition 1 (`kernel`) holds the raw FIT image blob with no filesystem. `emmc_do_upgrade` performs a raw `dd` write directly to `/dev/mmcblkNpN` — any filesystem would be overwritten and destroyed on every sysupgrade. The raw partition approach is consistent with all other ramips/MT7628 boards in OpenWrt.

`IMAGE/recovery.bin` copies the already-built initramfs FIT image into an explicit build output. U-Boot boots it via `sf read` from NOR offset `0x60000` into RAM, then `bootm`. This file is written to the NOR `recovery` partition at `0x060000` by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py), which also reads its size to set `recovery_size` in the env partition.

**`BODYBYTES_PACKAGES`** (both profiles):
- `openssh-sftp-server` + `rsync` - needed in recovery to transfer a sysupgrade image into the device before flashing.
- `avahi-daemon` - advertises `bodybytes.local` via mDNS; useful in recovery where the user has no easy way to find the device IP.
- `e2fsprogs` - `e2fsck`/`resize2fs`/`tune2fs` for ext4 maintenance on the data partition and for `mkfs.ext4` after `parted` creates partitions in recovery.
- `lsblk` - inspects block device layout, partition labels, and mount points.
- `-wpad-basic-mbedtls wpad-openssl` - swaps the subtarget default for the full WPA supplicant/hostapd build with OpenSSL; required for WPA3 (SAE) and 802.11r. The MT7628AN mt76 driver sets `IEEE80211_HW_MFP_CAPABLE` via the shared mt76 framework (`mac80211.c:476`), confirming hardware 802.11w support.
- `-swconfig` - removes the `swconfig` Ethernet switch configuration tool from the image. `swconfig` is in the mt76x8 subtarget `DEFAULT_PACKAGES` for the many mt76x8 boards that have an internal switch, but bodybytes disables both `&ethernet` and `&esw` in the DTS. The kernel driver never probes, so `swconfig` would find no switch to configure — it is dead weight.
- `luci-ssl-openssl` - LuCI collection package that pulls in `luci-light`, `libustream-openssl`, and `openssl-util`. Enables HTTPS for the LuCI web interface; uhttpd listens on both port 80 (HTTP, redirects to HTTPS) and port 443. OpenSSL is already in the image from `wpad-openssl` so this adds only the ustream TLS glue and the `openssl` tool used for certificate generation. Replaces `libustream-mbedtls` as the ustream TLS backend.

**Main profile only:**
- `samba4-server` + `luci-app-samba4` - SMB file sharing; compatible with Windows, macOS, iOS, and Android.
- `luci-app-statistics` + `collectd-mod-{cpu,load,memory,disk,interface,iwinfo,tcpconns,processes}` - system, storage, WiFi, and TCP connection metrics in LuCI. `collectd-mod-ping` is excluded - the device has no upstream internet connection and is a local-only AP.
- `iperf3` - network throughput benchmarking; run `iperf3 -s` on device, `iperf3 -c bodybytes.local` from a client to measure WiFi throughput under load.
- `luci-app-ttyd` - web terminal in LuCI; provides browser-based shell access without SSH, critical once the device is implanted and serial is inaccessible.
- `luci-app-nlbwmon` - per-client bandwidth tracking in LuCI.

**Recovery profile only:**
- `parted` - partitions a fresh eMMC before the first sysupgrade (see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)).

**`90_defaults` UCI configuration** (first boot, board-gated):
- System: `hostname=bodybytes`
- WiFi: `ssid=Bodybytes`, `country=US`, `encryption=sae-mixed`, `key=bodybytes` (change via LuCI before use)
- Network: fixed ULA prefix `fd13:37be:ef00::/48` ("1337beef") overriding OpenWrt's `ula_prefix=auto`. A fixed prefix is safe because bodybytes is an isolated AP - no other device will ever share this ULA space. `ip6assign=64` tells netifd to assign the first /64 of that prefix to `br-lan`; the router's address is always `fd13:37be:ef00::1`.
- DHCP/IPv6: `dhcpv6=server`, `ra=server`, `ra_slaac=1` on the LAN - odhcpd provides DHCPv6 and Router Advertisements with SLAAC so clients auto-configure their IPv6 addresses without explicit assignment.
- TLS certificate: EC P-256 self-signed cert generated via `openssl req` on first boot, valid 10 years. SANs: `DNS:bodybytes.local`, `DNS:bodybytes`, `IP:192.168.1.1`, `IP:fd13:37be:ef00::1`. Covers all access paths (mDNS hostname over IPv4 and IPv6, IPv4 gateway, ULA router address). uhttpd (START=80) generates a generic cert before this script runs (START=95); the script overwrites it and restarts uhttpd to pick up the custom cert.
- fstab: explicit mount entry for the `data` partition at `/mnt/data` (`label=data`, `fstype=ext4`, `options=noatime`, `enabled=1`)
- Samba (guarded on `/etc/config/samba4`): sets description to `Bodybytes`; adds a read-write guest share for `/mnt/data`. mDNS/Bonjour advertisement of `_smb._tcp` is handled by smbd itself via the avahi client library (`CONFIG_SAMBA4_SERVER_AVAHI=y`) - smbd registers with avahi-daemon over D-Bus when it starts and deregisters when it stops; no static service file is needed.
- collectd (guarded on `/etc/config/luci_statistics`): enables `collectd_disk` (monitoring `mmcblk0`), `collectd_tcpconns` (ports 22 and 445, `AllPortsSummary=1`), `collectd_processes` (smbd, nmbd, dnsmasq, dropbear, uhttpd, avahi-daemon, collectd); sets RRD `DataDir` to `/srv/collectd/rrd` - persisted on `rootfs_data` via overlayfs, outside the Samba share. collectd creates the directory on first write.

The `data` partition is mounted at `/mnt/data` via an explicit fstab entry written by `90_defaults` on first boot (`uci add fstab mount` with `label=data`, `target=/mnt/data`, `fstype=ext4`, `options=noatime`, `enabled=1`). The `block` daemon creates `/mnt/data` automatically at mount time. The `rootfs_data` overlay partition is handled by libfstools (matched by GPT label) independently.

---

## 2 - Sysupgrade

[`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) dispatches `sysupgrade` per board name with three functions for the `bodybytes,bodybytes` case:

**`platform_check_image`** runs two checks before anything is written. First, it greps the tar listing for a `sysupgrade-*/CONTROL` entry — the canonical marker that distinguishes a sysupgrade-tar from a raw image or FIT blob. Second, for each partition that will be written (`kernel`, `rootfs`), `find_mmc_part` searches `/sys/block/mmcblk*/uevent` by GPT label and returns empty if the partition is absent — catching the case where the GPT has not yet been laid down (first install before `parted` has run). Without the readiness check, `emmc_upgrade_tar` would silently write to nothing but the devmem reset would already have cleared the bootcount. Return code 1 marks the image as invalid but still forceable with `sysupgrade -F`.

`validate_firmware_image` (called by `sysupgrade` before touching anything) calls `platform_check_image`. Because `REQUIRE_IMAGE_METADATA=1` is set, `fwtool_check_image` already verifies board-name compatibility from the appended metadata before `platform_check_image` adds its further checks.

**`platform_copy_config`** dispatches to `emmc_copy_config`, which writes `/etc/sysupgrade.tgz` to the block offset immediately following the rootfs in the `rootfs_data` partition. Without this entry, the generic sysupgrade framework skips the config-save step and the "keep settings" option silently does nothing.

**`platform_do_upgrade`** sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, resets the bootcount register with `devmem 0x1000006c 32 0xB0010000`, then calls `emmc_do_upgrade`. `0x1000006c` is the physical address of the MT7628 SYSCTL MEMO2 register; `0xB0010000` packs the magic sentinel `0xB001` in bits [31:16] and count `0` in bits [15:0] — the encoding U-Boot's `BOOTCOUNT_GENERIC`/`SINGLEWORD` backend expects. No NOR write occurs; the NOR env partition is fully read-only from Linux. `bootlimit=3` is permanently fixed in the compiled-in env and the NOR env partition.

`emmc_do_upgrade` detects the sysupgrade-tar format and dispatches to `emmc_upgrade_tar`, which raw-writes each tar member via `dd`:
- `sysupgrade-*/kernel` (the FIT image) → GPT partition labelled `kernel` (`CI_KERNPART`) - raw binary, no filesystem
- `sysupgrade-*/root` (the squashfs) → GPT partition labelled `rootfs` (`CI_ROOTPART`) - raw binary, no filesystem

It also zeros 8 sectors past each written member to prevent stale content from being misread. `CI_DATAPART="rootfs_data"` tells `emmc_copy_config` where to store the sysupgrade config backup.

The `init.d/bootcount` script (START=99) runs near the end of every successful OpenWrt boot and writes `0xB0010000` to MEMO2 via `devmem`, resetting the bootcount to zero. U-Boot increments the count from 0 to 1 on the next boot, and `init.d/bootcount` resets it again on success - so the count only accumulates across consecutive failed boots.

The default fallback (`default_do_upgrade`) writes to an MTD partition named `firmware`, which does not exist on bodybytes. Without the bodybytes case, sysupgrade would fail at runtime.

**`devmem` availability:** `CONFIG_KERNEL_DEVMEM=y` enables `/dev/mem` in the kernel; `CONFIG_BUSYBOX_CUSTOM=y` + `CONFIG_BUSYBOX_CONFIG_DEVMEM=y` in [`bodybytes.config`](../bodybytes.config) enable the busybox `devmem` applet. `devmem` is included in `RAMFS_COPY_BIN` in `platform.sh` so it is available during the sysupgrade ramfs stage.

See [uboot.md - Boot counter](uboot.md#boot-counter-failed-boot-recovery) for the U-Boot side of this mechanism.
