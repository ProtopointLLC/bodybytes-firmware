# OpenWRT — MT7628AN

Target: `ramips` / subtarget `mt76x8`

---

## 1 — Prerequisites

### Build environment

OpenWRT **builds its own MIPS cross-compiler** from source. Do not use the
U-Boot `nix develop .#uboot` shell — it sets `CROSS_COMPILE` and `ARCH` which would
interfere.

```sh
cd /path/to/bodybytes
nix develop .#openwrt
```

This provides all required host tools (gcc, perl, rsync, wget, …) without
setting any cross-compilation variables.

### Update feeds

```sh
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

---

## 2 — Board target files

Both board files live inside the `openwrt/` submodule. The submodule is
pinned to a commit that includes these changes.

| File | Purpose |
|------|---------|
| `openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dts` | Device tree |
| `openwrt/target/linux/ramips/image/mt76x8.mk` | Board profile |

### What the DTS sets

#### Board identity

```dts
compatible = "bodybytes,bodybytes", "mediatek,mt7628an-soc";
model = "Bodybytes";
```

The first compatible string is the board-specific identifier OpenWRT uses for
board detection. The second is the fallback SoC match.

#### Console

```dts
chosen { bootargs = "console=ttyS2,115200"; }
```

UART2 = ttyS2. UART2 is wired to EPHY MDI_P2 pads (MDI_TP_P2 / MDI_TN_P2,
SoC pins 47/48) via the AGPIO_CFG UART2_MODE=0 path set by the SPL. The
kernel does not touch that register, so the routing persists from boot.
`ephy-digital` (see below) re-asserts the EPHY pad digital-mode bit on every
kernel init.

#### SPI NOR flash — `&spi0`

W25Q512JV, 64 MB, CS0, 25 MHz. The OS lives on eMMC; NOR holds only the
bootloader and the WiFi calibration EEPROM.

| Partition | Offset | Size | Notes |
|-----------|--------|------|-------|
| `u-boot` | `0x000000` | 192 KB | read-only |
| `u-boot-env` | `0x030000` | 64 KB | writable |
| `factory` | `0x040000` | 64 KB | read-only; contains WiFi EEPROM at offset 0 |

The `factory` partition exposes a 1 KB nvmem cell (`eeprom@0`) consumed by
`&wmac` for WiFi calibration data. Without this partition the wireless
interface will not initialize.

The kernel MTD spi-nor driver handles BAR (Bank Address Register) addressing
for the upper 48 MB automatically — no special DTS flag is needed.

#### Pin control — `&pinctrl`

**`ephy-digital`** — a property on the pinctrl node consumed by OpenWRT patch
`809-pinctrl-mtmips-allow-mux-SDXC-pins-for-mt76x8`. It sets
`AGPIO_CFG EPHY_APGIO_AIO_EN[4:1] = 0xf`, switching all four MDI pad groups
(P1–P4) from analog Ethernet PHY mode to digital signal mode. Required by all
three EPHY-routed functions below.

**`sdxc_iot_mode`** — two sub-groups:

| Sub-group | Register field | Value | Effect |
|-----------|---------------|-------|--------|
| `esd` → `iot` | `AGPIO_CFG ESD` bit | `iot` | Routes SDXC signals to EPHY pads |
| `sdmode` → `sdxc` | `GPIO_MODE SDMODE` | `sdxc` | Enables SDXC controller on those pads |

Together these mirror what `sd_iot_mode` does in `bodybytes_uboot.dtsi`,
routing the SDXC data/cmd/clk lines to EPHY P3/P4 MDI pads (SoC pins 51–57).

**`mdi_p1_gpio`** — sets `GPIO_MODE SPIS = gpio`, switching MDI P1 pads to
GPIO function. Makes MDI_TN_P1 (GPIO#15) driveable as the eMMC hardware reset
output. Without this, the `emmc_pwrseq` GPIO write has no effect.

#### eMMC power sequencer

```dts
emmc_pwrseq: emmc_pwrseq {
    compatible = "mmc-pwrseq-emmc";
    reset-gpios = <&gpio 15 GPIO_ACTIVE_LOW>;
};
```

MDI_TN_P1 (SoC pin 42, GPIO#15, active-low). Pulsed low at power-up by the
`mmc-pwrseq-emmc` driver to clear fault conditions. The eMMC RST_n function
is disabled by default (EXT_CSD[162] = 0x00) so pulsing is a safe no-op; if
the OS later enables RST_n the pulse will perform a real reset on subsequent
power-ups.

#### eMMC — `&sdhci`

Kingston EMMC128-IY29-5B111, 128 GB eMMC 5.1, on EPHY P3/P4 MDI pads
(SoC pins 51–57).

| Property | Value | Reason |
|----------|-------|--------|
| `pinctrl-0/1` | `sdxc_iot_mode mdi_p1_gpio` | Overrides base `sdxc_pins`; applies EPHY routing and SPIS GPIO mode |
| `non-removable` | — | Soldered eMMC; skips card-detect polling |
| `/delete-property/ cap-sd-highspeed` | — | Removes removable-SD capability from base dtsi |
| `mmc-pwrseq` | `emmc_pwrseq` | Links hardware reset GPIO |

`cap-mmc-highspeed`, `bus-width = <4>`, and `no-1-8-v` are inherited from
`mt7628an.dtsi`. High Speed SDR mode (≤52 MHz, ≤52 MB/s) is the fastest mode
the MT7628 SDXC controller supports at 3.3 V VCCQ; HS200/HS400 require 1.8 V
and are unreachable regardless.

#### UART2 — `&uart2`

```dts
&uart2 { status = "okay"; };
```

Enables the UART2 peripheral (ttyS2). Pin routing to EPHY MDI_P2 is handled
at the register level by the SPL and `ephy-digital`; the standard `uart2_pins`
pinctrl only touches `GPIO_MODE` and does not override the AGPIO_CFG routing.

#### WiFi — `&wmac`

```dts
&wmac {
    nvmem-cells = <&eeprom_factory_0>;
    nvmem-cell-names = "eeprom";
};
```

Points the MT7628 integrated 2.4 GHz radio at the 1 KB calibration EEPROM in
the NOR `factory` partition. Without this the driver loads with a zeroed
EEPROM and RF performance is undefined.

### Board profile

```makefile
define Device/bodybytes_bodybytes
  DEVICE_VENDOR := Bodybytes
  DEVICE_MODEL := Bodybytes
  IMAGE_SIZE := 120m
  DEVICE_PACKAGES := kmod-mmc-mtk
  SUPPORTED_DEVICES := bodybytes,bodybytes
endef
TARGET_DEVICES += bodybytes_bodybytes
```

`IMAGE_SIZE := 120m` is the maximum size of the kernel+rootfs image written
to eMMC. The remaining eMMC space is available to the OS as data storage.

---

## 3 — Configure

```sh
cd openwrt
make menuconfig
```

Set:

| Option | Value |
|--------|-------|
| Target System | `MediaTek Ralink MIPS` |
| Subtarget | `MT76x8 based boards` |
| Target Profile | `Bodybytes` |

Enable additional packages as needed (e.g. `kmod-usb2`, `kmod-usb-ohci`).

---

## 4 — Build

```sh
make -j$(nproc)
```

First build downloads the MIPS cross-toolchain and all package sources —
this takes a while. Subsequent builds are incremental.

### Output

```
bin/targets/ramips/mt76x8/
  openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
```

This is a raw image: uImage (lzma-compressed kernel + DTB) followed by a
squashfs rootfs. Write it directly to eMMC sector 0.

---

## 5 — Write to eMMC

See [uboot.md §3f](uboot.md#3f--write-openwrt-to-emmc) for the full
procedure. In brief, from the U-Boot console after loading the image into RAM:

```
mmc dev 0
mmc write 0x82000000 0 <block_count_hex>
```

Pre-calculate block count on the host (512 bytes/block):

```sh
img=openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
blkcount=$(( ($(stat -c%s "$img") + 511) / 512 ))
printf "block count: 0x%x\n" $blkcount
```

---

## 6 — Boot configuration

U-Boot reads the kernel from eMMC. A FIT-based `bootcmd` (set once via
U-Boot console):

```
setenv bootcmd 'mmc dev 0; mmc read 0x82000000 0 0x10000; bootm 0x82000000'
saveenv
boot
```

The kernel command line (rootfs location, overlayfs) depends on the exact
OpenWRT image layout and will be refined once a first boot is achieved.
The `bootargs` in the DTS (`console=ttyS2,115200`) is a baseline; U-Boot
can extend it via `setenv bootargs`.
