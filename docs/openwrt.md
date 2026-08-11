# OpenWRT - MT7628AN

Target: `ramips` / subtarget `mt76x8` - see [building.md](building.md) for build steps.

---

## 1 - Board files

[`bodybytes.config`](../bodybytes.config) seeds the target/board selection and Kconfig options. Key items:

- The `mt76x8` subtarget's `emmc` target feature (`target.mk`) `select`s the prompt-less `EMMC_SUPPORT` symbol so base-files keeps `/lib/upgrade/emmc.sh` — the `emmc_do_upgrade`/`emmc_copy_config` helpers [`platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) calls for eMMC sysupgrade. (`CONFIG_EMMC_SUPPORT=y` in the seed config is silently dropped by `make defconfig` — it can only be reached via `select`; base-files is one package per subtarget so `emmc.sh` ships on all mt76x8 images, inert on boards whose `platform.sh` never calls it.)
- `CONFIG_SAMBA4_SERVER_AVAHI=y` builds samba4 with avahi client support so smbd registers `_smb._tcp` via D-Bus rather than requiring a static service file.
- `CONFIG_IMAGEOPT=y` and `CONFIG_VERSIONOPT=y` activate the `VERSION_*` symbols — without them they live inside an `if VERSIONOPT` block and are silently dropped.

`CONFIG_TARGET_MULTI_PROFILE=y` is required to build both device profiles in one `make` run. Without it, device symbols live in a Kconfig `choice` block — only the last one set wins. With `MULTI_PROFILE`, they become independent bool symbols that can both be set simultaneously.

All files below live in the `openwrt/` submodule; the submodule is pinned to a commit that includes these changes.

| File | Purpose |
|------|---------|
| [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi) | Device tree (shared by both profiles); thin `.dts` wrappers [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts) and [`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts`](../openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes_recovery.dts) include it. The main `.dts` overrides `chosen.bootargs` to add `root=/dev/mmcblk0p2 rootwait=10 panic=3` (eMMC root device; the bounded root wait plus reboot-on-panic feed the failed-boot watchdog — see [Console](#console)); the recovery `.dts` uses the DTSI bootargs as-is. |
| [`openwrt/target/linux/ramips/image/mt76x8.mk`](../openwrt/target/linux/ramips/image/mt76x8.mk) | Board profile: `DEVICE_DTS`, `KERNEL` (FIT image pipeline), `DEVICE_PACKAGES` (includes `parted` for first-install partitioning from recovery), `IMAGE_SIZE`, `IMAGES`, `sysupgrade.bin` and `recovery.bin` build rules, `SUPPORTED_DEVICES` |
| [`openwrt/target/linux/ramips/modules.mk`](../openwrt/target/linux/ramips/modules.mk) | Adds `CONFIG_PWRSEQ_EMMC` to `kmod-mmc-mtk`'s `KCONFIG` and `pwrseq_emmc.ko` to its `FILES`, so `mmc-pwrseq-emmc` (the eMMC RST_n pulse at probe) is packaged on the *module* build of this shared kmod (the `mt7620`/`mt7621` ramips subtargets). On mt76x8/bodybytes the whole stack is built in via `config-6.12` instead, so the package is an empty built-in stub |
| [`openwrt/target/linux/ramips/mt76x8/target.mk`](../openwrt/target/linux/ramips/mt76x8/target.mk) | mt76x8 subtarget definition; adds `emmc` to `FEATURES` so `EMMC_SUPPORT` is selected and base-files keeps `/lib/upgrade/emmc.sh` (the `emmc_do_upgrade`/`emmc_copy_config` sysupgrade helpers) — required for eMMC sysupgrade to work |
| [`openwrt/target/linux/ramips/mt76x8/config-6.12`](../openwrt/target/linux/ramips/mt76x8/config-6.12) | mt76x8 subtarget kernel config; the bodybytes change builds the MMC stack into the kernel (`CONFIG_MMC`, `CONFIG_MMC_BLOCK`, `CONFIG_MMC_MTK`, `CONFIG_MMC_HSQ`, `CONFIG_MMC_CQHCI`, `CONFIG_PWRSEQ_EMMC` all `=y`) so the eMMC rootfs can be mounted at boot — a driver packaged as a module on that rootfs can't load itself (see [SD/eMMC driver & kernel patches](#sdemmc-driver--kernel-patches)) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/uci-defaults/90_defaults) | First-boot board defaults: root password (`bodybytes`); hostname; syslog to `/dev/console`; WiFi SSID, country, WPA3-mixed encryption (`sae-mixed`, key `bodybytes`); full LAN setup (br-lan bridge, 192.168.1.1/24, ip6assign=64, ULA prefix); DHCPv6+RA; avahi mDNS hostname pin; two-cert TLS PKI for uhttpd and ttyd (with IPv6 enabled); fstab mount for `data` partition at `/mnt/data`; Samba description, `/mnt/data` share, and `bodybytes` system user (guarded on `/etc/config/samba4`); collectd disk/tcpconns/processes enables and RRD path `/srv/collectd/rrd` (guarded on `/etc/config/luci_statistics`) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/board.d/02_network) | Network board detection. `ramips_setup_interfaces`: bodybytes case calls `ucidef_set_interface "lan" protocol "static"`, writing `network.lan = { protocol: "static" }` (no `device` field) to `/etc/board.json`. This suppresses the `99-default_network` fallback that would otherwise write `eth0` as the LAN device; it also prevents LuCI's port-status widget from showing a phantom eth0 entry (the widget reads `board.json`'s `device` field, which is absent). Because `board.json` has no `device` field for lan, `config_generate` skips LAN bridge creation; `90_defaults` builds it from scratch. `ramips_setup_macs`: bodybytes case reads the WiFi MAC from the factory NOR partition (offset 0x4) and sets it as `label_mac`, exposed as the device label MAC in LuCI. |
| [`openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips`](../openwrt/package/boot/uboot-tools/uboot-envtools/files/ramips) | U-Boot env tool config; the `bodybytes,bodybytes` case calls `ubootenv_add_mtd "u-boot-env" "0x0" "0x1000" "0x10000"`, which resolves the `u-boot-env` MTD partition by name at runtime and writes the resulting `/dev/mtdN` path into `/etc/fw_env.config` |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount) | Resets the SYSCTL MEMO2 bootcount register to zero (`devmem 0x1000006c 32 0xB0010000`) on every successful boot (START=99) |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/avahi-reprobe`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/avahi-reprobe) | Boot fallback for avahi mDNS (START=99): waits for the `br-lan` global IPv6 (ULA) to appear, then restarts avahi once so it publishes both A and AAAA records under its hostname instead of renaming to `<host>-2.local` (avahi claims the name on IPv4 before the ULA is assigned and mistakes the late IPv6 for a conflict). Board-gated via `case $(board_name)`; auto-enabled at build like all base-files init scripts. |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/hotplug.d/iface/99-avahi-mdns`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/hotplug.d/iface/99-avahi-mdns) | Restarts avahi on `lan` `ifup`/`ifupdate` so it re-probes with both address families after any address change — the ongoing self-heal counterpart to `avahi-reprobe` (which covers the boot race). Board-gated via `case $(board_name)`. |
| [`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) | Sysupgrade dispatch; `platform_check_image` rejects non-sysupgrade-tar images (no `CONTROL` entry) and fails if the `kernel` or `rootfs` GPT partitions are not yet present on the eMMC; bodybytes case sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, resets the SYSCTL MEMO2 bootcount register to zero via `devmem` (no NOR write), then calls `emmc_do_upgrade` to write the kernel to p1 and the squashfs rootfs to p2; `platform_copy_config` dispatches to `emmc_copy_config` to save the sysupgrade config backup into the `rootfs_data` partition |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/banner`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/banner) | Custom ASCII art banner shown at login: Bodybytes slant ASCII art, then `%D` (distro name, "OpenWrt"), `%V` (version), and `%C` (revision code). |
| [`openwrt/target/linux/ramips/mt76x8/base-files/etc/profile.d/apk-cheatsheet.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/profile.d/apk-cheatsheet.sh) | Login profile script: prints a one-line APK package manager hint if `apk` is available |

### What the DTS sets

#### Board identity

Sets `compatible = "bodybytes,bodybytes", "mediatek,mt7628an-soc"` and `model = "Bodybytes"`. The first compatible string is the board-specific identifier OpenWRT uses for board detection; the second is the fallback SoC match.

#### Console

The DTSI sets `chosen.bootargs = "console=ttyS0,115200"`. UART2 gets ttyS0 because: `mt7628an.dtsi` defines `serial0 = &uartlite` but uartlite is disabled, so slot 0 in the 8250 port array is never claimed. UART2 has no serial alias, so the 8250 driver auto-assigns it to the first free slot (ttyS0). Both profiles use `console=ttyS0`.

The main profile's `mt7628an_bodybytes_bodybytes.dts` wrapper overrides `chosen.bootargs` to `"console=ttyS0,115200 root=/dev/mmcblk0p2 rootwait=10 panic=3"`, adding the eMMC root device. The recovery profile uses the DTSI bootargs verbatim (no root= needed — rootfs is in the initramfs).

`rootwait=10 panic=3` wires eMMC into the failed-boot watchdog: `rootwait=10` caps the wait for `/dev/mmcblk0p2` at 10 s (normal eMMC enumeration takes well under a second); if root mount fails, `panic=3` reboots after 3 s. Since the panic fires before userspace, [`init.d/bootcount`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount) never resets the counter — each failed boot increments the U-Boot bootcount until `bootlimit=3` runs `altbootcmd` into NOR recovery. See [Sysupgrade](#2--sysupgrade) and [uboot.md — Boot counter](uboot.md#boot-counter-failed-boot-recovery).

UART2 is routed to EPHY MDI_P2 pads (MDI_TP_P2 / MDI_TN_P2, SoC pins 47/48): `uart2_pins` sets `UART2_MODE=0`; `ephy-digital` (see below) sets `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1]=0xf` at pinctrl probe time, switching those pads from analog to digital mode.

#### SPI NOR flash - `&spi0`

W25Q512JV, 64 MB, CS0, 25 MHz. The OS lives on eMMC; NOR holds only the bootloader and the WiFi calibration EEPROM. See [flashing.md §1a](flashing.md#1a--partition-map) and [§1b](flashing.md#1b--partition-details) for the full partition map and per-partition details.

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

**`state_default`** - the system-wide default pinctrl state, populated by the bodybytes DTSI. Sets `GPIO_MODE SPIS = gpio`, switching MDI P1 pads to GPIO#14–17, applied at pinctrl init before `gpio-button-hotplug` claims GPIO#14 at probe. GPIO#15 (MDI_TN_P1, eMMC RST\_n) is also made driveable. The `esd` and `sdmode` groups are intentionally **not** hogged here: the pinctrl core's exclusive ownership model would prevent `10130000.mmc` from later claiming those groups via its own `pinctrl-0 = <&sdxc_iot_mode>`, causing -EINVAL at sdhci probe. Those groups are owned and applied by sdhci.

#### eMMC / microSD - `&sdhci`

Kingston EMMC128-IY29-5B111, 128 GB eMMC 5.1 (or microSD), on EPHY P3/P4 MDI pads (SoC pins 51–57). The controller probes SD protocol first (ACMD41); if that times out it falls through to MMC (CMD1), so either medium works with no DTS change. Both are treated as always-inserted (`non-removable`).

| Property | Value | Reason |
|----------|-------|--------|
| `pinctrl-0` | `sdxc_iot_mode` | Overrides base `sdxc_pins`; applies EPHY routing. SPIS→GPIO mux is handled by `state_default` at pinctrl init. |
| `pinctrl-1` | `sdxc_iot_mode` | Overrides base `sdxc_pins` (state_uhs for 1.8 V switching). UHS never activates (no UHS caps, fixed 3.3 V), but prevents the non-IoT pinctrl being applied if state_uhs is ever requested. |
| `mmc-pwrseq` | `emmc_pwrseq` | Pulses GPIO#15 (eMMC RST\_n, MDI\_TN\_P1) low at probe via `mmc-pwrseq-emmc`, clearing any eMMC fault state before the init sequence. |
| `vmmc-supply` | `reg_3v3` | Overrides the base DTSi `reg_vmmc` supply; explicit 3.3 V rail for eMMC VCC |
| `vqmmc-supply` | `reg_3v3` | Overrides the base DTSi `reg_vqmmc` supply; explicit 3.3 V rail for eMMC VCCQ |
| `no-1-8-v` | - | Prevents voltage-switch negotiation to 1.8 V; MT7628 SDXC runs at 3.3 V only |
| `non-removable` | - | Card is always present; no CD polling needed |
| `no-sdio` | - | Prevents SDIO (CMD5) probe; without this the MSDC driver sets `SDC_CFG_SDIO` in hardware and CMD5 causes "no support for card's volts" + CMD1 busy-poll timeout |

**Clock** - the board DTSI sets `max-frequency = <48000000>`; `cap-sd-highspeed`, `cap-mmc-highspeed`, and `bus-width = <4>` are inherited from `mt7628an.dtsi`. SD/MMC High-Speed (50 MHz class) is the fastest the MT7628 SDXC does at 3.3 V VCCQ — HS200/HS400 need 1.8 V and are unreachable. The bodybytes PCB (short soldered traces) runs cleanly at 48 MHz. On dev-rig wiring, `max-frequency` may need to be reduced — see [vocore2.md §Bus speed depends on your wiring](vocore2.md#bus-speed-depends-on-your-wiring).

8-bit bus width (`bus-width = <8>`) is not possible: the four additional data lines (SD_D4–SD_D7) would require `groups = "uart2"; function = "sdxc d5 d4"` (as defined in `emmc_iot_8bit_mode` in the dtsi), which conflicts with UART2 as the system console.

**JTAG must be off.** SD/eMMC on the EPHY pads only works with `DBG_JTAG_MODE` disabled (`UART_TXD1` strapped high / GPIO mode); enabling CPU JTAG breaks the bus. They are mutually exclusive — see [jtag.md](jtag.md#jtag-and-sdemmc-are-mutually-exclusive).

#### SD/eMMC driver & kernel patches

The board uses the upstream MSDC driver (`CONFIG_MMC_MTK`, compatible `mediatek,mt7620-mmc`, `drivers/mmc/host/mtk-sd.c`), **built into the kernel** rather than shipped as the `kmod-mmc-mtk` module: the MMC stack (`CONFIG_MMC`, `CONFIG_MMC_BLOCK`, `CONFIG_MMC_MTK`, `CONFIG_MMC_HSQ`, `CONFIG_MMC_CQHCI`, `CONFIG_PWRSEQ_EMMC`) is set `=y` in [`config-6.12`](../openwrt/target/linux/ramips/mt76x8/config-6.12). This is mandatory for the normal (eMMC) boot: the squashfs rootfs is on `/dev/mmcblk0p2`, so the block driver has to be in the kernel *before* it can mount root — a driver packaged as a module lives on that very rootfs and can never load itself. Recovery is exempt because its rootfs is the initramfs in RAM, so the MMC modules load normally after boot.

MT7628 support comes from three ramips patches to `mtk-sd.c` (mirrored by the U-Boot driver fix):

| Patch | Effect |
|-------|--------|
| `831-01` | adds the `mips_mt762x` flag: hardcodes the vendor pad drive/`PAD_TUNE`/read-delay values, and enables high-speed response/data sampling above 25 MHz (what makes 48 MHz work) |
| `831-02` | `support_cmd23 = false` — CMD23 is unreliable on this controller IP and causes I/O errors |
| `831-03` | skips the `MSDC_PATCH_BIT`/`PATCH_BIT1` writes for `mips_mt762x` — those MT8173/MT7622 values corrupt the MT7628 controller; keep the reset defaults |

Plus patch `809` adds the `esd`/`sdmode` groups and the `ephy-digital` property handler (§`&pinctrl`).

**eMMC power sequencer.** `mmc-pwrseq-emmc` pulses RST_n at MMC probe (see [eMMC / microSD](#emmc--microsd---sdhci)). `CONFIG_PWRSEQ_EMMC=y` is built in alongside the rest of the MMC stack in `config-6.12`, so the sequencer is registered before the (also built-in) host controller probes — a built-in host with an `mmc-pwrseq` phandle but no loaded provider would otherwise `EPROBE_DEFER` indefinitely before root is mounted. `modules.mk` also adds `pwrseq_emmc.ko` to `kmod-mmc-mtk`'s `FILES`; that only affects the *module* build of the shared kmod on the `mt7620`/`mt7621` ramips subtargets — on mt76x8 the package is an empty built-in stub.

#### Boot mode selector - `keys`

A `gpio-keys` node exposes a `boot-mode` button on `gpios = <&gpio 14 GPIO_ACTIVE_LOW>` with `linux,code = <BTN_0>`. MDI_TP_P1 (SoC pin 40, GPIO#14) is driven by a TI DRV5032FCDBZT hall-effect sensor — magnet present = low = pressed. U-Boot reads this GPIO at boot to choose normal vs. recovery boot.

**`CONFIG_INPUT` is not set** in the bodybytes kernel config. There is no Linux input subsystem, no `/dev/input/`, and the standard `gpio-keys` input driver is not compiled. Instead, `kmod-gpio-button-hotplug` (from the mt76x8 `DEFAULT_PACKAGES`) registers a platform driver under the name `gpio-keys`, claiming the DTS node at module load time from `/etc/modules-boot.d/`. It fires uevent hotplug calls directly rather than creating input events. Hotplug scripts in `/etc/hotplug.d/button/` match on `[ "$BUTTON" = "BTN_0" ]` and `[ "$ACTION" = "pressed" ]` / `released`.

The DTS `label = "boot-mode"` is used only as the GPIO consumer description visible in `/sys/kernel/debug/gpio`; it does not affect `BUTTON=`. To observe the current sensor state from a running system: `grep boot-mode /sys/kernel/debug/gpio` — the field reads `hi` (no magnet) or `lo` (magnet present, ACTIVE_LOW).

GPIO#14 is on the same MDI P1 pad group as GPIO#15 (eMMC RST_n). The `state_default` pinctrl state (sets `SPIS_MODE=gpio`) covers both; it fires at pinctrl init time, before `gpio-button-hotplug` probes. `gpio-button-hotplug` claims GPIO#14 at probe time, preventing accidental userspace re-export.

#### Ethernet - `&ethernet` / `&esw`

Both left **enabled** (their `mt7628an.dtsi` default) even though bodybytes has no physical Ethernet ports. The switch/PHY block is kept solely for a side effect that SD/eMMC depends on: SD runs on the EPHY P3/P4 MDI pads in IoT mode, and `ephy-digital` only routes the SDXC signals onto those pads — it does **not** initialise the EPHY analog front-end. Probing `&ethernet`/`&esw` runs the ramips switch/PHY driver's EPHY bring-up (reset pulse + the *"fix EPHY idle state"* MDIO sequence), which the SD pads require to idle correctly. Disabling them would leave the SD pads in an abnormal idle state and the card would not enumerate. The unused switch just registers netdevs that are left unconfigured. (U-Boot solves the identical dependency by enabling its eth driver — see [uboot.md](uboot.md).)

#### USB - `&usbphy` / `&ehci` / `&ohci`

All three disabled. `mt7628an.dtsi` leaves the USB 2.0 host (EHCI/OHCI) and its PHY enabled by default, but bodybytes has no USB connector. Disabling `&usbphy`, `&ehci`, and `&ohci` stops the kernel initialising an unusable controller and keeps the boot lean. (The U-Boot build has no USB support compiled in at all, so its equivalent DTS node is inert.)

#### UART0 - `&uartlite`

UART0 is disabled (`status = "disabled"`). `mt7628an.dtsi` leaves `uartlite` enabled by default; bodybytes has no UART0 connection on the board. Disabling it ensures UART2 registers as ttyS0 (Linux assigns ttyS numbers in probe order - with only UART2 active, it becomes the first and only serial device).

#### 3.3 V regulator - `reg_3v3`

A `regulator-fixed` node providing a permanent 3.3 V rail (`regulator-always-on`), overriding the base DTSi `reg_vmmc`/`reg_vqmmc` supplies for `vmmc-supply` and `vqmmc-supply` on `&sdhci`. The MT7628 SDXC controller is hard-wired to 3.3 V; the explicit regulator ensures the OCR mask is correct for voltage negotiation.

#### UART2 - `&uart2`

Enabled (`status = "okay"`). Becomes ttyS0 since UART0 is disabled. `uart2_pins` (from `mt7628an.dtsi`) sets `UART2_MODE=0`; `ephy-digital` sets `AGPIO_CFG` to make the MDI P2 pads digital. Both are applied at pinctrl probe.

#### WiFi - `&wmac`

Three key properties: `nvmem-cells = <&eeprom_factory_0>` and `nvmem-cell-names = "eeprom"` wire the WiFi calibration EEPROM to the 1 KB cell from the `factory` NOR partition; `mediatek,eeprom-merge-otp` overlays only RF calibration fields from the on-chip eFuse onto the external EEPROM data while preserving the MAC address from the factory partition.

**Driver stack:** The MT7628AN's integrated 2.4 GHz radio (`wmac@10300000`, compatible `"mediatek,mt7628-wmac"`) is driven by `mt7603e.ko` from the mt76 package. The driver binds via the DTS platform device path — not PCI. `kmod-mt7603` is in the mt76x8 subtarget's `DEFAULT_PACKAGES` and is automatically included in every build; no explicit package entry is needed in `BODYBYTES_PACKAGES`.

**Firmware blobs:** MT7628 WiFi requires two firmware files at `/lib/firmware/mt7628_e1.bin` and `/lib/firmware/mt7628_e2.bin` (ECO revision 1 and 2 respectively). These are **bundled in the mt76 package** — the `kmod-mt7603` install rule detects `CONFIG_TARGET_ramips_mt76x8` at build time and copies the `mt7628_*` variants instead of the MT7603-card variants. No external blob source is needed; the files are built from the mt76 source tree.

**EEPROM load path:** `mt76_eeprom_init()` calls `mt76_get_of_eeprom()`, which tries three sources in order: embedded DT data → MTD partition → nvmem cell. For bodybytes, the nvmem path succeeds: `of_nvmem_cell_get(np, "eeprom")` resolves `nvmem-cell-names = "eeprom"` to the `eeprom_factory_0` cell (`factory` partition offset 0, size 0x400). `MT7603_EEPROM_SIZE = 1024 = 0x400` matches exactly.

**`mediatek,eeprom-merge-otp`:** After loading the external EEPROM, `mt7603_eeprom_init()` reads the on-chip eFuse OTP. If the external EEPROM passes the validity check, it overlays only the RF calibration fields (TX power, RSSI offsets, crystal trim) from the eFuse onto the EEPROM data — the MAC address and chip ID stay from the external EEPROM. If the factory partition is entirely erased (all 0xFF), the driver copies the eFuse wholesale, including whatever MAC MediaTek burned into the chip (often `0xFF:FF:FF:FF:FF:FF` on engineering samples). Always write a valid factory blob with your own MAC.

**LED suppression:** `mt76_led_init()` (`mac80211.c:196`) checks for a `led` child node in the DTS before registering a kernel LED class device. If the node is present and `of_device_is_available()` returns false (i.e. `status = "disabled"`), the function returns early without calling `led_classdev_register()`. Without this, the driver registers `mt76-phy0` in `/sys/class/leds/`, which causes LuCI's LED configuration page to show a configurable LED despite bodybytes having no physical LED wired to the WiFi chip. The `led { status = "disabled"; }` subnode in `&wmac` suppresses this registration.

See [docs/wifi.md](wifi.md) for the EEPROM register map, field documentation, and [`config.ini`](../scripts/config.ini) key reference.

### Board profiles

Two device profiles are defined, enabled by `CONFIG_TARGET_PER_DEVICE_ROOTFS=y`. Each starts from the full `.config` package set and applies per-device package additions.

`BODYBYTES_PACKAGES` is a shared Make variable holding the packages common to both profiles - the same pattern used by `USB2_PACKAGES` in `bcm47xx`. The **main profile** (`bodybytes_bodybytes`) produces `sysupgrade.bin` via `sysupgrade-tar | append-metadata | check-size` with `IMAGE_SIZE := 544m` (32 MiB kernel + 512 MiB rootfs partitions). The **recovery profile** (`bodybytes_bodybytes_recovery`) produces `recovery.bin` via `append-image-stage initramfs-kernel.bin | check-size` with `IMAGE_SIZE := 65152k`, matching the NOR `recovery` partition exactly (63.625 MB). `DEVICE_VARIANT := Recovery` distinguishes the recovery profile without modifying `DEVICE_MODEL`.

The kernel pipeline `kernel-bin | gzip | fit gzip <dtb>` produces a FIT image (`.itb`) containing a gzip-compressed kernel image node and a flat DTB node. U-Boot's `bootm ${kernel_addr_r}` verifies and extracts both, applies standard fixups (writes detected memory into `/memory`, merges `bootargs` into `/chosen/bootargs`), then jumps to the kernel entry point. No separate DTB file is needed on the eMMC kernel partition.

**gzip, not LZMA, for the FIT kernel node.** LZMA decompression on the MT7628's 24KEc is very slow (single-digit MB/s) — the dominant cost of the U-Boot boot stage. gzip is ~10× faster for a slightly larger image. lz4 would be marginally faster still but requires `CONFIG_LZ4=y` and a non-standard `Build/lz4`; gzip uses the existing `CONFIG_GZIP=y` mainline path. (The recovery initramfs cpio is LZ4-compressed separately via `CONFIG_TARGET_INITRAMFS_COMPRESSION_LZ4` — decompressed by the kernel, not U-Boot.)

GPT partition 1 (`kernel`) holds the raw FIT image blob with no filesystem. `emmc_do_upgrade` performs a raw `dd` write directly to `/dev/mmcblkNpN` — any filesystem would be overwritten and destroyed on every sysupgrade. The raw partition approach is consistent with all other ramips/MT7628 boards in OpenWrt.

`IMAGE/recovery.bin` copies the already-built initramfs FIT image into an explicit build output. U-Boot boots it via `sf read` from NOR offset `0x60000` into RAM, then `bootm`. This file is written to the NOR `recovery` partition at `0x060000` by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py), which also reads its size to set `recovery_size` in the env partition.

**`BODYBYTES_PACKAGES`** (both profiles):

- `block-mount` + `kmod-fs-ext4` - block device automount daemon and ext4 support for the `data` partition (`rootfs_data` is F2FS — see next bullet). The MMC host driver itself is **built into the kernel** (via `config-6.12`), not a package — see [SD/eMMC driver & kernel patches](#sdemmc-driver--kernel-patches).
- `kmod-fs-f2fs` + `mkf2fs` + `f2fsck` - F2FS support for the `rootfs_data` **overlay**. F2FS (Flash-Friendly File System) is a log-structured filesystem designed for the raw NAND behind eMMC/SD: it does wear-aware allocation and turns the overlay's many small random writes (package installs, config, logs) into sequential appends, cutting write amplification and flash wear versus ext4's in-place journaling — so it is genuinely better suited to this partition, not just the path of least resistance. `mount_root` formats a blank/reset overlay partition as F2FS by default (it only mounts an existing ext4 overlay, never creates one), so `mkfs.f2fs` must be present — otherwise a fresh `rootfs_data`, a `sysupgrade -n`, or a factory reset leaves `mount_root` unable to create the overlay and it silently falls back to a **non-persistent tmpfs** (`overlay filesystem … has not been formatted yet` → `mkfs.f2fs: not found`). `f2fsck` repairs the overlay after the abrupt power-offs this on-demand device sees. `kmod-fs-f2fs` is a module `mount_root` loads at preinit (same as the ext4 module).
- `uboot-envtools` - provides `fw_printenv`/`fw_setenv`; `ubootenv_add_mtd` in `02_network` configures `/etc/fw_env.config` at runtime. `fw_printenv` is copied into the sysupgrade ramfs via `RAMFS_COPY_BIN`.
- `openssh-sftp-server` + `rsync` - needed in recovery to transfer a sysupgrade image into the device before flashing.
- `avahi-daemon` - advertises `bodybytes.local` via mDNS; useful in recovery where the user has no easy way to find the device IP.
- `e2fsprogs` - `e2fsck`/`resize2fs`/`tune2fs` for ext4 maintenance on the data partition and for `mkfs.ext4` after `parted` creates partitions in recovery.
- `lsblk` - inspects block device layout, partition labels, and mount points.
- `mmc-utils` - `mmc` tool for eMMC identification and maintenance (`mmc cid read` / `mmc extcsd read`: vendor/product, boot-partition config, life-time/health).
- `blkdiscard` - issues TRIM/erase to a whole device or range (`blkdiscard -f /dev/mmcblk0`); the flash-correct way to reset the eMMC/SD - near-instant and wear-levelling, unlike `dd` zeroing.
- `fstrim` - TRIMs a mounted filesystem (`fstrim /mnt/data`, `/overlay`); OpenWrt runs no periodic TRIM by default, so this maintains write performance and reduces wear on the eMMC/SD.
- `dtc` - device tree compiler; included for on-device DTS/DTB debugging.
- `iperf3` - network throughput benchmarking; run `iperf3 -s` on device, `iperf3 -c bodybytes.local` from a client to measure WiFi throughput under load.
- `fio` - flexible storage benchmarking (IOPS/throughput/latency) for characterising the eMMC/SD. Upload [`scripts/emmc-bench.fio`](../scripts/emmc-bench.fio) to the device and run `fio emmc-bench.fio` to benchmark `/mnt/data` and verify bus stability. The job file uses libaio with `iodepth=1` for sequential and `iodepth=8` for random tests. Reference numbers for Kingston EMMC128-IY29-5B111, 4-bit bus @ 48 MHz on EPHY pads:

  | Test | Throughput | IOPS |
  |---|---|---|
  | Sequential write (1M) | 20.7 MB/s | — |
  | Sequential read (1M) | 21.4 MB/s | — |
  | Random write 4K | 7.4 MB/s | 1902 |
  | Random read 4K | 9.1 MB/s | 2321 |

  Sequential throughput (~21 MB/s) is ~88% of the 24 MB/s theoretical bus ceiling. These numbers are a rough orientation — they will vary with the eMMC part, bus wiring quality, and clock speed.
- `-wpad-basic-mbedtls wpad-openssl` - swaps the subtarget default for the full WPA supplicant/hostapd build with OpenSSL; required for WPA3 (SAE) and 802.11r. The MT7628AN mt76 driver sets `IEEE80211_HW_MFP_CAPABLE` via the shared mt76 framework (`mac80211.c:476`), confirming hardware 802.11w support.
- `-swconfig` - removes the `swconfig` Ethernet switch configuration tool from the image. `swconfig` is in the mt76x8 subtarget `DEFAULT_PACKAGES` for the many mt76x8 boards that have an internal switch. Bodybytes keeps `&ethernet`/`&esw` enabled (for the EPHY bring-up the SD pads depend on — see [Ethernet](#ethernet---ethernet--esw)), so the switch driver does probe, but the board exposes no Ethernet ports and there is nothing to configure — `swconfig` is dead weight either way.
- `luci-ssl-openssl` - LuCI collection package that pulls in `luci-light`, `libustream-openssl`, and `openssl-util`. Enables HTTPS for the LuCI web interface; uhttpd listens on both port 80 (HTTP, redirects to HTTPS) and port 443. OpenSSL is already in the image from `wpad-openssl` so this adds only the ustream TLS glue and the `openssl` tool used for certificate generation. Replaces `libustream-mbedtls` as the ustream TLS backend.
- `luci-app-ttyd` - web terminal in LuCI; provides browser-based shell access without SSH, critical once the device is implanted and serial is inaccessible. Included in both profiles so recovery also has a web terminal.

**Main profile only:**

- `travelmate` + `luci-app-travelmate` - WiFi roaming/uplink manager; allows the device to connect to an upstream WiFi network while simultaneously hosting its own AP.
- `samba4-server` + `luci-app-samba4` - SMB file sharing; compatible with Windows, macOS, iOS, and Android.
- `luci-app-statistics` + `collectd-mod-{cpu,load,memory,disk,interface,iwinfo,tcpconns,processes}` - system, storage, WiFi, and TCP connection metrics in LuCI. `collectd-mod-ping` is excluded - upstream connectivity is not guaranteed (travelmate manages it opportunistically), so ping round-trip metrics would be meaningless or missing during periods without an upstream WiFi connection.

**Recovery profile only:**

- `parted` - partitions a fresh eMMC before the first sysupgrade (see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)).

**`90_defaults` UCI configuration** (first boot, board-gated):

- Root password: set to `bodybytes` via `passwd` (change before deployment).
- System: `hostname=bodybytes`; `log_file=/dev/console` - routes syslog output to the UART serial port (ttyS0), making kernel and daemon log messages visible on the UART console during debugging.
- WiFi: `ssid=Bodybytes`, `country=US`, `encryption=sae-mixed`, `key=bodybytes` (change via LuCI before use)
- Network: `90_defaults` owns the entire LAN setup because `config_generate` skips it. `02_network` writes only `network.lan = { protocol: "static" }` to `board.json` (no `device` field) — this suppresses the `99-default_network` eth0 fallback and hides the phantom eth0 entry from LuCI's port-status widget. `90_defaults` builds the full LAN from scratch: `br-lan` bridge (no wired ports; WiFi attaches at runtime), `lan` at `192.168.1.1/24`, `ip6assign=64`, fixed ULA prefix `fd13:37be:ef00::/48` ("1337beef"). Fixed prefix is safe on an isolated AP; router always at `fd13:37be:ef00::1`.
- DHCP/IPv6: `dhcpv6=server`, `ra=server`, `ra_slaac=1` on the LAN - odhcpd provides DHCPv6 and Router Advertisements with SLAAC so clients auto-configure their IPv6 addresses without explicit assignment.
- mDNS (avahi): pins `host-name=bodybytes` and enables `avahi-reprobe`. Together with `99-avahi-mdns`, keeps `bodybytes.local` resolving to both `192.168.1.1` and `fd13:37be:ef00::1`. The fix is needed because avahi claims the hostname on IPv4 before the ULA is assigned; the late IPv6 churn makes avahi self-conflict and rename to `bodybytes-2.local`. `avahi-reprobe` waits for the ULA at boot and restarts avahi once; the hotplug script re-covers later address changes (see [avahi #340](https://github.com/avahi/avahi/issues/340)).
- Travelmate (main profile only): `90_defaults` only **enables the init** (`/etc/init.d/travelmate enable`, guarded on `[ -x … ]`) — the build's auto-enable is unreliable here, so this is explicit. No travelmate settings are pre-seeded. Its one-time Interface Wizard (LuCI, or `/etc/init.d/travelmate setup`) owns `trm_iface`, the `trm_wwan` DHCP interface and its `wan`-zone assignment; travelmate's `setup()` is a no-op once `trm_iface` is already set, so configuring those over uci would block the wizard. Behaviour tuning is left to the user too (`trm_captive` on by default; `trm_proactive`/`trm_netcheck` off by default). The user runs the wizard once and adds the uplink station (SSID/password unknown until on-site) via the Wireless Stations tab.
- TLS PKI: two-cert setup generated on first boot. A CA cert (`/etc/bodybytes-ca.crt`, `basicConstraints: CA:TRUE, pathlen:0`) signs a separate server cert (`/etc/uhttpd.crt`, `CA:FALSE`, SANs, `serverAuth`). Both are EC P-256, valid 50 years (18250 days). A clock guard (`[ "$(date +%Y)" -lt 2025 ] && date -s "2026-01-01 00:00:00"`) forces the clock forward on freshly-flashed devices with no valid RTC so the cert's `notBefore` field is sane. A single self-signed cert cannot work: Chrome/Firefox require the trust anchor to have `CA:TRUE` and the server cert to have `CA:FALSE` — they reject a cert that tries to be both. Users download the CA cert at `https://bodybytes.local/bodybytes-ca.crt` and install it once as a trusted CA; after that, all HTTPS connections to the device are trusted without warnings. The script restarts uhttpd to load the CA-signed cert. SANs: `DNS:bodybytes.local`, `DNS:bodybytes`, `IP:192.168.1.1`, `IP:fd13:37be:ef00::1`.
- fstab: explicitly sets `delay_root=5` s; adds an explicit mount entry for the `data` partition at `/mnt/data` (`label=data`, `fstype=ext4`, `options=noatime`, `enabled=1`)
- Samba (guarded on `/etc/config/samba4`): sets description to `Bodybytes`. **`/etc/init.d/samba4 start` must precede `smbpasswd`**: `90_defaults` runs before the samba4 service generates `/etc/samba/smb.conf`; without it `smbpasswd` uses the `tdbsam` default and writes into tmpfs `/var/lib/samba` — lost on reboot, leaving `/etc/samba/smbpasswd` empty and every login rejected. Starting the service first writes `passdb backend = smbpasswd`, so passwords land in the persistent file. Adds an authenticated R/W share for `/mnt/data` (uci `users=bodybytes` → `valid users` — **not** `valid_users`, which the samba4 init silently ignores; `browseable=yes`, `create_mask=0666`, `dir_mask=0777`) and injects `host msdfs = no` so the `bodybytes.local` mDNS name isn't rejected by smbd's DFS parser. The `data` root is owned uid 8000 (`mkfs -E root_owner=8000:8000` — see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)) so `bodybytes` can create files without `force user`. `_smb._tcp` is advertised by smbd via avahi over D-Bus (`CONFIG_SAMBA4_SERVER_AVAHI=y`); no static service file needed.
- ttyd: enables TLS (`ssl=1`), IPv6 (`ipv6=1`), and points ttyd at the uhttpd cert/key (`/etc/uhttpd.crt`, `/etc/uhttpd.key`). TLS is required because LuCI is served over HTTPS and browsers block mixed-content WebSocket connections (`ws://` from an `https://` page); ttyd must use `wss://` with the same certificate. IPv6 enables ttyd to accept connections on both IPv4 and IPv6.
- collectd (guarded on `/etc/config/luci_statistics`): enables `collectd_disk` (monitoring `mmcblk0`), `collectd_tcpconns` (ports 22 and 445, `AllPortsSummary=1`), `collectd_processes` (smbd, nmbd, dnsmasq, dropbear, uhttpd, avahi-daemon, collectd); sets RRD `DataDir` to `/srv/collectd/rrd` - persisted on `rootfs_data` via overlayfs, outside the Samba share. collectd creates the directory on first write.

The `data` partition is mounted at `/mnt/data` via an explicit fstab entry written by `90_defaults` on first boot (`uci add fstab mount` with `label=data`, `target=/mnt/data`, `fstype=ext4`, `options=noatime`, `enabled=1`). It is deliberately **ext4**, not F2FS like the `rootfs_data` overlay: `data` holds irreplaceable user files, so ext4's journaling and mature `e2fsck` recovery tooling to salvage it after an abrupt power cut outweigh the overlay's flash-write optimization. The `block` daemon creates `/mnt/data` automatically at mount time. The `rootfs_data` overlay partition is handled by libfstools (matched by GPT label) independently.

---

## 2 - Sysupgrade

[`openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) dispatches `sysupgrade` per board name with three functions for the `bodybytes,bodybytes` case:

**`platform_check_image`** runs two checks before anything is written. First, it greps the tar listing for a `sysupgrade-*/CONTROL` entry — the canonical marker that distinguishes a sysupgrade-tar from a raw image or FIT blob. Second, for each partition that will be written (`kernel`, `rootfs`), `find_mmc_part` searches `/sys/block/mmcblk*/uevent` by GPT label and returns empty if the partition is absent — catching the case where the GPT has not yet been laid down (first install before `parted` has run). Without the readiness check, `emmc_upgrade_tar` would silently write to nothing but the devmem reset would already have cleared the bootcount. Return code 1 marks the image as invalid but still forceable with `sysupgrade -F`.

`validate_firmware_image` (called by `sysupgrade` before touching anything) calls `platform_check_image`. Because `REQUIRE_IMAGE_METADATA=1` is set, `fwtool_check_image` already verifies board-name compatibility from the appended metadata before `platform_check_image` adds its further checks.

**`platform_copy_config`** dispatches to `emmc_copy_config`, which writes `/etc/sysupgrade.tgz` to the block offset immediately following the rootfs in the `rootfs_data` partition. Without this entry, the generic sysupgrade framework skips the config-save step and the "keep settings" option silently does nothing.

**`platform_do_upgrade`** sets `CI_KERNPART="kernel"`, `CI_ROOTPART="rootfs"`, `CI_DATAPART="rootfs_data"`, resets the bootcount register (`devmem 0x1000006c 32 0xB0010000`), calls `emmc_do_upgrade`, then issues an explicit **`sync`**. The `sync` is required: `emmc_upgrade_tar` flushes after the rootfs write but not after the kernel (written last), so without it the kernel FIT can remain in the write cache and be lost on reboot — leaving p1 partially written and U-Boot unable to read the image. `0x1000006c` is the physical address of SYSCTL MEMO2; `0xB0010000` encodes magic `0xB001` in bits [31:16] and count 0 in bits [15:0]. No NOR write occurs; the NOR env partition is read-only from Linux.

`emmc_do_upgrade` detects the sysupgrade-tar format and dispatches to `emmc_upgrade_tar`, which raw-writes each tar member via `dd`:

- `sysupgrade-*/kernel` (the FIT image) → GPT partition labelled `kernel` (`CI_KERNPART`) - raw binary, no filesystem
- `sysupgrade-*/root` (the squashfs) → GPT partition labelled `rootfs` (`CI_ROOTPART`) - raw binary, no filesystem

It also zeros 8 sectors past each written member to prevent stale content from being misread. `CI_DATAPART="rootfs_data"` tells `emmc_copy_config` where to store the sysupgrade config backup.

The [`init.d/bootcount`](../openwrt/target/linux/ramips/mt76x8/base-files/etc/init.d/bootcount) script (START=99) runs near the end of every successful OpenWrt boot and writes `0xB0010000` to MEMO2 via `devmem`, resetting the bootcount to zero. U-Boot increments the count from 0 to 1 on the next boot, and `init.d/bootcount` resets it again on success - so the count only accumulates across consecutive failed boots.

The default fallback (`default_do_upgrade`) writes to an MTD partition named `firmware`, which does not exist on bodybytes. Without the bodybytes case, sysupgrade would fail at runtime.

**`devmem` availability:** `CONFIG_KERNEL_DEVMEM=y` enables `/dev/mem` in the kernel; `CONFIG_BUSYBOX_CUSTOM=y` + `CONFIG_BUSYBOX_CONFIG_DEVMEM=y` in [`bodybytes.config`](../bodybytes.config) enable the busybox `devmem` applet. `devmem` is included in `RAMFS_COPY_BIN` in [`platform.sh`](../openwrt/target/linux/ramips/mt76x8/base-files/lib/upgrade/platform.sh) so it is available during the sysupgrade ramfs stage.

---

## 3 - TLS and browser trust

Both LuCI (port 443) and ttyd (port 7681) are served over HTTPS using a CA-signed certificate generated on first boot. The CA cert is available for download at `https://bodybytes.local/bodybytes-ca.crt` (or `https://192.168.1.1/bodybytes-ca.crt`).

**Recommended: install the CA cert once**

Download `bodybytes-ca.crt` and import it as a trusted CA. After that, all HTTPS connections to the device — both LuCI and ttyd — are trusted without warnings on that browser/OS.

- **Firefox:** `about:preferences#privacy` → Certificates → View Certificates → Authorities → Import → check "Trust this CA to identify websites"
- **Windows:** double-click the `.crt` file → Install Certificate → Trusted Root Certification Authorities. Enable `security.enterprise_roots.enabled` in Firefox `about:config` to pick up the Windows store.
- **macOS:** double-click → Keychain Access → System keychain → mark as Always Trust. Same `security.enterprise_roots.enabled` flag for Firefox.
- **Android:** Settings → Security → Install a certificate → CA certificate
- **iOS:** download the file → Settings → General → VPN & Device Management → install → Settings → General → About → Certificate Trust Settings → enable

**Alternative: per-host browser exceptions**

If you skip CA cert installation, you must add a separate browser exception for each port you access. LuCI (port 443) and ttyd (port 7681) are different origins — accepting the warning for one does not cover the other. Navigate to `https://bodybytes.local:7681/` (or the IP equivalent) and accept the exception there before the LuCI terminal tab will connect.

See [uboot.md - Boot counter](uboot.md#boot-counter-failed-boot-recovery) for the U-Boot side of this mechanism.
