# OpenWRT — MT7628AN

Target: `ramips` / subtarget `mt76x8`

---

## 1 — Prerequisites

### Build environment

OpenWRT **builds its own MIPS cross-compiler** from source. Do not use the U-Boot `nix develop .#uboot` shell — it sets `CROSS_COMPILE` and `ARCH` which would interfere.

```sh
cd /path/to/bodybytes
nix develop .#openwrt
```

This drops into a `buildFHSEnv` shell that provides all required host tools without setting any cross-compilation variables. It also sets `AR=gcc-ar` (LTO-aware archiver for host builds) and `FAKEROOTDONTTRYCHOWN=1` (works around a fakeroot/bwrap user-namespace limitation that would otherwise produce ownership warnings and a non-zero exit during image assembly).

### Update feeds

```sh
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

---

## 2 — Configure

```sh
cd openwrt
cp ../bodybytes.config .config
make defconfig
```

`bodybytes.config` seeds the target; `make defconfig` expands it into a full `.config` with all defaults filled in. To add or change packages, run `make menuconfig` afterwards.

### Board files

Both live in the `openwrt/` submodule; the submodule is pinned to a commit that includes these changes.

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
| `u-boot-env` | `0x040000` | 64 KB | writable |
| `factory` | `0x050000` | 64 KB | read-only; 1 KB WiFi EEPROM at offset 0 |
| `recovery` | `0x060000` | 63.625 MB | read-only; OpenWrt sysupgrade image |

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

If the factory partition is entirely erased (all 0xFF) the driver discards the external EEPROM and copies the eFuse wholesale, including whatever MAC MediaTek burned into the chip. The `eeprom-merge-otp` property has no effect in that case.

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

`IMAGE_SIZE := 120m` is the maximum size of the kernel+rootfs image written to eMMC. The remaining eMMC space is available to the OS as data storage.

---

## 3 — Build

All commands run from inside `openwrt/`.

```sh
make download
make world -j$(nproc)
```

The first build downloads the MIPS cross-toolchain and all package sources and takes a while; subsequent builds are incremental. `make world` also performs smaller downloads on each run.

### Output

```
bin/targets/ramips/mt76x8/
  openwrt-ramips-mt76x8-bodybytes_bodybytes-initramfs-kernel.bin
  openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
```

The sysupgrade image is a raw image: uImage (lzma-compressed kernel + DTB) followed by a squashfs rootfs. Write it directly to eMMC sector 0.

---

## 4 — Flash

See [flashing.md](flashing.md) for NOR image assembly, factory EEPROM generation, SPI NOR programming, eMMC write, and boot configuration.
