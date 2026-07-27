# eMMC / microSD Bring-up

## Status

**In progress** — DTS fixes applied; oscilloscope verification pending.

| Fix | File | Status |
|-----|------|--------|
| Add `non-removable` to U-Boot `&mmc` | `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | ✓ done |
| Add `no-1-8-v` to U-Boot `&mmc` | `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | ✓ done |
| Add `mmc-pwrseq-emmc` node + wire to `&mmc` | `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | ✓ done |
| Remove `.use_internal_cd = true` from `mt7620_compat`; add pwrseq call | `u-boot/drivers/mmc/mtk-sd.c` | ✓ done |
| Add `mmc-pwrseq-emmc` node + wire to `&sdhci` | `openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi` | ✓ done |
| Override `max-frequency = <1000000>` in `&sdhci` | `openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi` | ✓ done |
| `CONFIG_PWRSEQ_EMMC` in `kmod-mmc-mtk` | `openwrt/target/linux/ramips/modules.mk` | ✓ done |
| Add `bias-pull-up` for CMD+DAT pads | `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | ✓ done |
| Switch back to `kmod-mmc-mtk` (upstream driver, calls `mmc_of_parse`) | `mt7628an_bodybytes_bodybytes.dtsi`, `mt76x8.mk` | ✓ done |
| Add `esd=iot` explicitly to both U-Boot and OpenWrt (IoT routing is HW reset default; explicit for clarity) | `bodybytes,bodybytes.dts`, `mt7628an_bodybytes_bodybytes.dtsi` | ✓ done |
| Add `ephy-digital-mask = <0xf>` (all digital; P4 analog disconnects MSDC from CLK/CMD entirely) | `mt7628an_bodybytes_bodybytes.dtsi`, patch 809 | ✓ done |

Testing target: **VoCore2 only** (Hardkernel H2 eMMC module → reader board → SB Components MicroSD breakout → jumper wires to VoCore2 breakout connector). CLK pull-up removed from the SB Components board before use.

---

## Core issue

The MT7628AN SDXC controller drives SD/eMMC signals through the EPHY (Ethernet PHY) MDI pads, which are in analog mode at reset. Two things must happen before any bus activity can occur:

1. **MDI P1–P4 pads** must be switched from analog EPHY to digital mode (`AGPIO_CFG EPHY_GPIO_AIO_EN[4:1] = 0xf`).
2. **SDXC controller** must be muxed onto those pads (`GPIO_MODE SDMODE → sdxc`). The MT7628AN supports two routing modes:
   - *IoT mode* (`GPIO_MODE1[15]=0` + `sdmode → sdxc`): routes SDXC to the MDI/EPHY pad group. This is the hardware reset default and the mode in use. The root cause of the CMD/CLK loading was not IoT routing but EPHY P4 digital mode (AGPIO\_CFG\[20\]) — see §EPHY P4 RX pad bias.
   - *Router mode* (`GPIO_MODE1[15]=1`): routes SDXC to I2S/I2C/GPIO0/UART1 pads. Not used on this board; the VoCore2 vendor firmware used standard SDXC mode (see §Standard SDXC mode experiment for the full analysis).

If either step is missing or mis-ordered, the CLK/CMD/DAT lines are electrically dead and the card never responds.

Additionally, the eMMC RST\_n line (GPIO\#15 / MDI\_TN\_P1 / breakout P1TN) is currently not driven by software — no `mmc-pwrseq` node exists in either the U-Boot or OpenWrt DTS. If the eMMC entered a fault state (e.g. from a power glitch), it will not self-recover without a RST\_n pulse.

---

## Signal path

```
MT7628AN SoC                     VoCore2 breakout         Adafruit 4682 / Hardkernel reader
─────────────────────────────    ────────────────          ─────────────────────────────────
SDXC controller ──► MDI_RP_P3 ──► P3RP  (pin 51) ──────► D1
                ──► MDI_RN_P3 ──► P3RN  (pin 52) ──────► D0
                ──► MDI_RP_P4 ──► P4RP  (pin 54) ──────► CLK
                ──► MDI_RN_P4 ──► P4RN  (pin 55) ──────► CMD
                ──► MDI_TP_P4 ──► P4TP  (pin 56) ──────► D3
                ──► MDI_TN_P4 ──► P4TN  (pin 57) ──────► D2
GPIO#15         ──► MDI_TN_P1 ──► P1TN  (pin 42) ──────► RST_n (via reader board R1 tap)
```

---

## Pin map

| Signal | SoC function | MDI pad | SoC pin | VoCore2 breakout | GPIO# (if SD_MODE=GPIO) |
|--------|-------------|---------|---------|-----------------|------------------------|
| SD\_CLK | SDXC CLK | MDI\_RP\_P4 | 54 | **P4RP** | 26 |
| SD\_CMD | SDXC CMD | MDI\_RN\_P4 | 55 | **P4RN** | 27 |
| SD\_D0 | SDXC DAT0 | MDI\_RN\_P3 | 52 | **P3RN** | 25 |
| SD\_D1 | SDXC DAT1 | MDI\_RP\_P3 | 51 | **P3RP** | 24 |
| SD\_D2 | SDXC DAT2 | MDI\_TN\_P4 | 57 | **P4TN** | 29 |
| SD\_D3 | SDXC DAT3 | MDI\_TP\_P4 | 56 | **P4TP** | 28 |
| eMMC RST\_n | GPIO#15 | MDI\_TN\_P1 | 42 | **P1TN** | 15 |

MDI pads use an RX/TX naming convention inherited from Ethernet PHY: RP/RN = receive pair, TP/TN = transmit pair. In SD IoT mode these are re-purposed as general-purpose digital lines — the names are physical pad identifiers, not signal direction.

---

## DTS analysis

### U-Boot (`u-boot/arch/mips/dts/bodybytes,bodybytes.dts`)

Current `&mmc` node (all fixes applied):

```dts
&mmc {
    status = "okay";
    bus-width = <4>;
    max-frequency = <1000000>;
    non-removable;
    no-1-8-v;
    builtin-cd = <0>;
    mmc-pwrseq = <&emmc_pwrseq>;

    pinctrl-names = "default";
    pinctrl-0 = <&sd_sdxc_mode &sd_bias>;
};
```

`sd_sdxc_mode` is defined in `bodybytes,bodybytes.dts` (replaces `sd_iot_mode` from `mt7628a.dtsi`) and sets:
- `sdmode → sdxc` (SDXC controller enabled on MDI pads)
- `sd router → iot` (ESD mux routes SDXC to MDI/EPHY pads; HW reset default but set explicitly)
- `sd_clk` drive strength = 8 mA
- **No** `ephy4_1_pad → digital` (digital mode is set separately by `ephy_iot_mode` for UART2)

`sd_bias` is defined in `bodybytes,bodybytes.dts` and sets:
- `bias-pull-up` on `sd_cmd`, `sd_d0`, `sd_d1`, `sd_d2`, `sd_d3` (PAD\_PU\_G0 bits 25–29)

Both states are applied together: `pinctrl-0 = <&sd_sdxc_mode &sd_bias>`. See
§EPHY P4 RX pad bias for the pull-up rationale.

**Complete property audit:**

Properties parsed by `mmc_of_parse` (standard MMC layer) and `msdc_of_to_plat` (driver):

| Property | Source | Assessment |
|----------|--------|------------|
| `bus-width = <4>` | Board DTS | ✅ Only DAT0–3 wired; 8-bit needs PWM0 (GPIO\#14 = boot sensor) |
| `max-frequency = <1000000>` | Board DTS | ✅ 1 MHz for jumper-wire bring-up (~300 KB/s data rate). Raise once enumeration is confirmed — see **Speed progression** note below |
| `non-removable` | Board DTS | ✅ Sets `MMC_CAP_NONREMOVABLE`; bypasses `mmc_getcd` check entirely in `mmc_start_init` |
| `no-1-8-v` | Board DTS | ✅ Supply is 3.3 V; strips `UHS_CAPS` (SDR12/25/50/104/DDR50) + HS200 + HS400 + HS400-ES. Does **not** strip `MMC_DDR_52` — see below |
| `builtin-cd = <0>` | Board DTS | ✅ Must explicitly override `builtin-cd = <1>` from `mt7628a.dtsi` |
| `mmc-pwrseq = <&emmc_pwrseq>` | Board DTS | ✅ Wires `mmc-pwrseq-emmc` driver to RST\_n (GPIO\#15) |
| `pinctrl-names = "default"` | Board DTS | ✅ Single state; no UHS voltage-switch state needed |
| `pinctrl-0 = <&sd_sdxc_mode &sd_bias>` | Board DTS | ✅ `sd_sdxc_mode`: sdxc routing + ESD IoT mux; `sd_bias`: padconf pull-ups on CMD+DAT |
| `r_smpl = <1>` | Inherited from dtsi | ✅ Rising-edge CMD sample, standard for SD/eMMC at 3.3 V |
| `cap-sd-highspeed` | Not set | ✅ Not needed at 1 MHz (cap is the binding limit). Add alongside `max-frequency = <48000000>` for HS production speed — enables CMD6 SD HS switch (25 → 50 MHz, 3.3 V) |
| `cap-mmc-highspeed` | Not set | ✅ Same — add for HS production speed — enables CMD6 EXT\_CSD[185] eMMC HS switch (26 → 52 MHz, 3.3 V) |
| `sd-uhs-sdr12/25/50/104`, `sd-uhs-ddr50` | Not set | ✅ Require 1.8 V signalling; `no-1-8-v` also strips them defensively |
| `mmc-ddr-1_8v`, `mmc-ddr-1_2v` | Not set | ✅ Would set `MMC_CAP(MMC_DDR_52)`; not set so DDR52 is never advertised. Note: `no-1-8-v` does **not** strip `MMC_DDR_52` — safety here comes only from not setting these properties. `mt7620_compat` also lacks `async_fifo`/`data_tune` so DDR52 would fail in hardware regardless |
| `mmc-hs200-1_8v`, `mmc-hs200-1_2v` | Not set | ✅ `mt7620_compat` has no `data_tune`/`async_fifo`; HS200 not achievable. `no-1-8-v` strips `MMC_MODE_HS200` defensively |
| `mmc-hs400-1_8v`, `mmc-hs400-1_2v`, `mmc-hs400-enhanced-strobe` | Not set | ✅ HS400/HS400-ES not achievable on this IP. `no-1-8-v` strips `MMC_MODE_HS400`/`MMC_MODE_HS400_ES` defensively |
| `no-mmc-hs400` | Not set | ✅ Not needed; HS400 caps never set so there is nothing to strip |
| `cd-inverted` | Not set | ✅ Only parsed in the `else` branch of `non-removable` — with `non-removable` present this property is never even read |
| `broken-cd` | Not set | ✅ Same — only parsed when not `non-removable`; irrelevant in our config |
| `cd-active-high` | Not set | ✅ Driver reads this but only uses it inside `msdc_ops_get_cd` when `builtin_cd = 1`; with `builtin-cd = <0>` it is never consulted |
| `wp-gpios`, `cd-gpios` | Not set | ✅ No WP/CD pins wired |
| `hs400-ds-delay`, `mediatek,hs200-cmd-int-delay`, `mediatek,latch-ck`, `write_int_delay`, `mediatek,hs400-cmd-resp-sel-rising` | Not set | ✅ All only affect tuning paths gated on `data_tune = true` in `mt7620_compat`, which is false |
| `vmmc-supply`, `vqmmc-supply` | Not set | ✅ Linux-only; not parsed by U-Boot `mmc_of_parse` |
| `no-sdio` | Not set | ✅ Not parsed by U-Boot `mmc_of_parse`; SDIO not attempted in U-Boot |

**Fixed gaps (were missing before):**

| Gap | Impact | Fix |
|-----|--------|-----|
| ~~No `non-removable`~~ | `mmc_of_parse()` does not set `MMC_CAP_NONREMOVABLE`; MMC core may treat slot as empty when no CD mechanism is present. | ✓ Added `non-removable;` |
| ~~No `no-1-8-v`~~ | Without it, if a UHS cap is ever set, the core could attempt a 1.8 V switch command against a rail incapable of switching. | ✓ Added `no-1-8-v;` |
| ~~No `mmc-pwrseq` node~~ | RST\_n (GPIO\#15) never pulsed; a faulted eMMC will not reset. | ✓ Added `emmc-pwrseq` node + `mmc-pwrseq` ref |
| ~~`use_internal_cd = true` in `mt7620_compat`~~ | Driver probe overwrites the `builtin-cd = <0>` read from DTS, silently ignoring it. | ✓ Removed from compat struct (see §mtk-sd.c patch) |
| No `no-sdio` | Minor: U-Boot does not probe SDIO (no CMD5 path), so harmless but inconsistent with the OpenWrt DTS. | Not fixed (harmless) |

### OpenWrt (`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi`)

Current `&sdhci` node (all fixes applied):

```dts
&sdhci {
    status = "okay";

    /* Suppress state_uhs from base DTSI; UHS disabled by no-1-8-v. */
    pinctrl-names = "default";
    pinctrl-0 = <&sdxc_mode>;

    vmmc-supply = <&reg_3v3>;
    vqmmc-supply = <&reg_3v3>;
    no-1-8-v;
    max-frequency = <1000000>;
    no-sdio;
    non-removable;
    mmc-pwrseq = <&emmc_pwrseq>;
};
```

The base `mt7628an.dtsi` provides `compatible = "mediatek,mt7620-mmc"` which binds the
upstream `drivers/mmc/host/mtk-sd.c` driver. This driver calls `mmc_of_parse()`; all DTS
properties above are parsed at runtime. The package is `kmod-mmc-mtk`. The driver hardcodes
`f_max = 48 MHz`. The kernel package is `kmod-sdhci-mt7620` (`CONFLICTS:=kmod-mmc-mtk`).

`pinctrl-names = "default"` overrides the base DTSI's two-entry `"default", "state_uhs"` list,
dropping `state_uhs` entirely. This prevents the base DTSI's `pinctrl-1 = <&sdxc_pins>` from
ever being applied. The device core (`pinctrl_bind_pins()` in `really_probe()`) still applies
`pinctrl-0` automatically before the driver probes.

`sdxc_mode` is defined inline in `&pinctrl`:

```dts
sdxc_mode: sdxc_mode {
    esd {
        groups = "esd";
        function = "iot";
    };
    sdxc {
        groups = "sdmode";
        function = "sdxc";
    };
};
```

`esd=iot` sets GPIO\_MODE1\[15\]=0, routing SDXC to the MDI/EPHY pad group. This is the
hardware reset default but is set explicitly here for clarity.

The `ephy-digital-mask = <0x7>` property on the `&pinctrl` node sets `AGPIO_CFG EPHY_GPIO_AIO_EN[3:1] = 0x7`
(MDI P1/P2/P3 digital; P4 stays analog). P1/P2/P3 digital is required for UART2. P4 kept analog to avoid the EPHY P4 RX input buffer loading CMD and CLK below VIH=2.0 V.

> **Note on the property audit below:** The following table was written for the upstream
> `mediatek,mt7620-mmc` driver, which calls `mmc_of_parse()`. With `ralink,mt7620-sdhci`,
> most properties are ignored at runtime. They are kept in the DTS for reference and to ease
> a future driver switch back to the upstream driver.

**Complete property audit:**

Properties parsed by `mmc_of_parse` (Linux kernel `drivers/mmc/core/host.c`) and
`msdc_of_property_parse` (`drivers/mmc/host/mtk-sd.c`):

| Property | Source | Assessment |
|----------|--------|------------|
| `bus-width = <4>` | Upstream dtsi | ✅ Inherited; `MMC_CAP_4_BIT_DATA` |
| `max-frequency = <1000000>` | Board DTS | ✅ Overrides upstream dtsi's 48 MHz. 1 MHz for bring-up. Raise to 25 MHz (SD default-speed) or 48 MHz (HS, base dtsi caps apply) once enumeration is confirmed |
| `non-removable` | Board DTS | ✅ Required. Sets `MMC_CAP_NONREMOVABLE`. Also prevents `internal_cd = true` — see use\_internal\_cd trap below |
| `no-1-8-v` | Upstream dtsi + board DTS | ⚠️ **Silently ignored by `mtk-sd.c`** — this is an SDHCI-only quirk (`SDHCI_QUIRK2_NO_1_8_V`). `mtk-sd.c` never parses it. Present in both the upstream dtsi and our overlay, but it is a no-op for this driver. Protection against 1.8 V switching comes from: (a) no UHS/HS200/HS400 caps set; (b) `vqmmc-supply` = fixed 3.3 V → `msdc_ops_switch_volt` returns an error if 1.8 V is somehow requested |
| `disable-wp` | Upstream dtsi | ✅ Inherited; `MMC_CAP2_NO_WRITE_PROTECT` — no WP pin wired |
| `cap-sd-highspeed` | Upstream dtsi | ✅ Inherited; `MMC_CAP_SD_HIGHSPEED`. Valid at 3.3 V (SD HS stays on 3.3 V supply). The `mips_mt762x` code path in `msdc_set_mclk` sets `MSDC_IOCON_RSPL/DSPL/W_DSPL` when `actual_clock > 25 MHz` — tested and working at 48 MHz on VoCore2 |
| `cap-mmc-highspeed` | Upstream dtsi | ✅ Inherited; `MMC_CAP_MMC_HIGHSPEED`. Valid at 3.3 V (MMC HS uses 3.3 V supply). Same `mips_mt762x` tuning applies |
| `vmmc-supply = <&reg_3v3>` | Board DTS | ✅ Overrides dtsi's `&reg_vmmc`; functionally identical (both are fixed 3.3 V). Required for `mmc_power_up` → `mmc_regulator_set_ocr()` |
| `vqmmc-supply = <&reg_3v3>` | Board DTS | ✅ Required. Fixed 3.3 V regulator — `msdc_ops_switch_volt` calls `mmc_regulator_set_vqmmc()`; a fixed 3.3 V regulator returns error for any 1.8 V request, providing a last-resort barrier against voltage switching |
| `non-removable` → `cd-inverted`, `cd-debounce-delay-ms`, `broken-cd`, `cd-gpios` | — | ✅ Skipped; all inside `else` branch of `non-removable` check in `mmc_of_parse` |
| `wp-inverted`, `wp-gpios` | — | ✅ N/A; `disable-wp` covers WP; no WP pin |
| `sd-uhs-sdr12/25/50/104/ddr50` | Not set | ✅ No UHS caps; all require 1.8 V signalling |
| `cap-power-off-card` | Not set | ✅ N/A |
| `cap-mmc-hw-reset` | Not set | ✅ Not needed. `mmc_hw_reset_for_init()` (called during every `mmc_rescan_try_freq`) calls `mmc_pwrseq_reset()` unconditionally, regardless of this flag — RST\_n is pulsed at init via the pwrseq. `MMC_CAP_HW_RESET` is only needed to additionally call `host->ops->card_hw_reset`, which `mtk-sd.c` does not implement anyway |
| `cap-sdio-irq` | Not set | ✅ N/A; no SDIO device |
| `full-pwr-cycle`, `full-pwr-cycle-in-suspend`, `keep-power-in-suspend`, `wakeup-source` | Not set | ✅ N/A |
| `mmc-ddr-3_3v` | Not set | ✅ DDR52 at 3.3 V not supported: `mt7620_compat` has `async_fifo = false` |
| `mmc-ddr-1_8v`, `mmc-ddr-1_2v` | Not set | ✅ DDR52 at 1.8/1.2 V — requires voltage switching |
| `mmc-hs200-1_8v`, `mmc-hs200-1_2v` | Not set | ✅ HS200 not achievable; `data_tune = false` in `mt7620_compat` |
| `mmc-hs400-1_8v`, `mmc-hs400-1_2v`, `mmc-hs400-enhanced-strobe` | Not set | ✅ HS400/HS400-ES not achievable |
| `no-mmc-hs400` | Not set | ✅ N/A; HS400 caps never set |
| `no-sdio` | Board DTS | ✅ Required. Sets `MMC_CAP2_NO_SDIO`. In `msdc_init_hw`, when this cap is present, the driver explicitly clears `SDC_CFG_SDIO` register bit. Without it, `SDC_CFG_SDIO` stays set and CMD5 causes "no support for card's volts" error during SD/eMMC probe |
| `no-sd` | Not set | ✅ Not set; SD (ACMD41) probe intentionally left enabled for microSD cards. Falls through to CMD1 automatically when ACMD41 times out for eMMC |
| `no-mmc` | Not set | ✅ Not set; CMD1 (MMC) probe needed for eMMC |
| `fixed-emmc-driver-type`, `dsr`, `post-power-on-delay-ms` | Not set | ✅ N/A |
| `mmc-pwrseq = <&emmc_pwrseq>` | Board DTS | ✅ Required. Wires `mmc-pwrseq-emmc` driver to RST\_n (GPIO\#15). RST\_n pulse happens in `mmc_hw_reset_for_init()` → `mmc_pwrseq_reset()` → `.reset` op — called at every card init attempt before CMD0 |
| `pinctrl-names = "default", "state_uhs"` | Board DTS | ✅ **Required for probe to succeed.** `mtk-sd.c` lines 2885-2888: `pinctrl_lookup_state(..., "state_uhs")` failing causes `dev_err` + `return PTR_ERR(...)` — probe aborts before `mmc_add_host()`. UHS is never activated (fixed 3.3 V supply), so both states point to `sdxc_mode`. |
| `pinctrl-0 = <&sdxc_mode>`, `pinctrl-1 = <&sdxc_mode>` | Board DTS | ✅ Both default and state_uhs point to `sdxc_mode` (esd=iot + sdxc routing). Applied by device core at probe and potentially at voltage-switch time (which never occurs). |
| `mediatek,latch-ck`, `hs400-ds-delay`, `mediatek,hs400-ds-dly3`, `mediatek,hs200-cmd-int-delay`, `mediatek,hs400-cmd-int-delay`, `mediatek,hs400-cmd-resp-sel-rising` | Not set | ✅ All affect HS200/HS400 tuning paths that are not reachable on MT7628 |
| `mediatek,tuning-step` | Not set | ✅ Defaults to `PAD_DELAY_HALF`; irrelevant — `mips_mt762x` path hardcodes all tuning parameters in `msdc_init_hw` regardless |
| `supports-cqe` | Not set | ✅ CQE not available on MT7628 (`support_cmd23 = false`) |

**Fixed gaps (were missing before):**

| Gap | Impact | Fix |
|-----|--------|-----|
| ~~No `mmc-pwrseq` node~~ | RST\_n (GPIO\#15) never pulsed; a faulted eMMC will not reset. | ✓ Added `emmc-pwrseq` node + `mmc-pwrseq` ref |
| ~~`pinctrl-1 = <&sdxc_pins>`~~ (inherited from upstream dtsi) | `state_uhs` would apply non-IoT pinctrl if somehow activated. | ✓ `pinctrl-names = "default"` override drops `state_uhs` entirely |
| `esd=iot` in `sdxc_mode` pinctrl | IoT routing (GPIO\_MODE1\[15\]=0) is the HW reset default; re-added explicitly for clarity. Root cause was EPHY P4 digital mode (AGPIO\_CFG\[20\]), not ESD routing. | ✓ Re-added explicitly |
| `ephy-digital-mask = <0x7>` | EPHY P4 digital input buffer loaded CMD/CLK below VIH=2.0V. Mask 0x7 keeps P1/P2/P3 digital (UART2), P4 analog. | ✓ Applied |

---

## Applied DTS fixes

All fixes below are committed to the DTS files. See git log for the exact diff.

### 1 — U-Boot DTS (`non-removable`, `no-1-8-v`, `mmc-pwrseq`) ✓

`u-boot/arch/mips/dts/bodybytes,bodybytes.dts` — added `emmc-pwrseq` node under `/` and applied all
capability properties to `&mmc`:

```dts
/ {
    emmc_pwrseq: emmc-pwrseq {
        compatible = "mmc-pwrseq-emmc";
        reset-gpios = <&gpio0 15 GPIO_ACTIVE_LOW>;
    };
};

&mmc {
    status = "okay";
    bus-width = <4>;
    max-frequency = <1000000>;
    non-removable;
    no-1-8-v;
    builtin-cd = <0>;
    mmc-pwrseq = <&emmc_pwrseq>;

    pinctrl-names = "default";
    pinctrl-0 = <&sd_sdxc_mode &sd_bias>;
};
```

`gpio0` is the U-Boot label for bank 0 (GPIO\#0–31) in `mt7628a.dtsi`. GPIO\#15 is offset 15 within
that bank. The `mdi_p1_gpio` pinctrl state (applied at `&pinctrl` init, before MMC probe) sets
SPIS\_MODE=gpio so GPIO\#15 is already available as a digital output when the pwrseq driver drives it.

The patched `u-boot/drivers/mmc/mtk-sd.c` calls `mmc_pwrseq_get_power()` / `pwrseq_set_power()` at
probe time (see §mtk-sd.c patch analysis below); `CONFIG_PWRSEQ=y` and `CONFIG_MMC_PWRSEQ=y` are
already set in `bodybytes_defconfig`.

### 2 — `mmc-pwrseq`, driver, and pinctrl in OpenWrt DTS ✓

`openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi` — added `emmc-pwrseq` node,
upstream `kmod-mmc-mtk` driver (via base DTSI `compatible`), explicit IoT routing, and EPHY mask:

```dts
/ {
    emmc_pwrseq: emmc-pwrseq {
        compatible = "mmc-pwrseq-emmc";
        reset-gpios = <&gpio 15 GPIO_ACTIVE_LOW>;
    };
};

&pinctrl {
    ephy-digital-mask = <0x7>;   /* P1/P2/P3 digital, P4 analog */

    sdxc_mode: sdxc_mode {
        esd { groups = "esd"; function = "iot"; };   /* GPIO_MODE1[15]=0; HW reset default, set explicitly */
        sdxc { groups = "sdmode"; function = "sdxc"; };
    };
};

&sdhci {
    status = "okay";
    /* compatible from base DTSI: mediatek,mt7620-mmc (kmod-mmc-mtk) */
    pinctrl-names = "default";
    pinctrl-0 = <&sdxc_mode>;
    mmc-pwrseq = <&emmc_pwrseq>;
    ...
};
```

`gpio` is the OpenWrt label for the flat GPIO controller (`gpio@600`) in `mt7628an.dtsi`; GPIO numbers are flat (GPIO\#15 = offset 15).

`CONFIG_PWRSEQ_EMMC` is in the generic kernel config as `=y`, but because `CONFIG_MMC=m` (pulled in as a module by `kmod-mmc-mtk`), Kconfig downgrades it to `=m` at build time. This makes `pwrseq_emmc.ko` a separate module — it gets compiled but was not packaged anywhere. Fixed by adding `CONFIG_PWRSEQ_EMMC` to the `kmod-mmc-mtk` KCONFIG and `pwrseq_emmc.ko` to its FILES in `openwrt/target/linux/ramips/modules.mk`.

---

## Driver and packaging verification

### U-Boot — `mtk-sd.c` patch analysis

Three changes were made to `u-boot/drivers/mmc/mtk-sd.c` relative to upstream commit
`88dc2788777babfd6322fa655df549a019aa1e69`:

#### Change 1 — `#include <pwrseq.h>`

`pwrseq_set_power()` (the uclass dispatcher that calls the driver op) is declared in
`<pwrseq.h>`. Without this include the compiler has no declaration for the call in change 2.
`mmc_pwrseq_get_power()` is in `<mmc.h>`, which was already included.

#### Change 2 — pwrseq call block in `msdc_drv_probe`

```c
#if CONFIG_IS_ENABLED(MMC_PWRSEQ)
{
    int pwrseq_ret = mmc_pwrseq_get_power(dev, cfg);
    if (!pwrseq_ret)
        pwrseq_set_power(cfg->pwr_dev, true);
}
#endif
```

**Guard correctness:** `cfg->pwr_dev` and `mmc_pwrseq_get_power()` are both inside
`#if CONFIG_IS_ENABLED(MMC_PWRSEQ)` in `mmc.h`. The guard in `mtk-sd.c` matches exactly.

**Absent `mmc-pwrseq` in DTS:** `mmc_pwrseq_get_power()` calls
`uclass_get_device_by_phandle()`. If the DTS has no `mmc-pwrseq` phandle, it returns a
non-zero error and `pwrseq_set_power` is never called — safe for boards without a pwrseq node.

**Placement:** the block sits after `msdc_ungate_clock()` (clocks must be running before GPIO
operations) and before `msdc_init_hw()` (RST\_n must be deasserted before the controller is
initialised). Card enumeration only happens later when `mmc dev 0` / `mmc rescan` is issued
at the U-Boot prompt — a gap of several seconds — so the 200 µs JEDEC tRSTH window is met
with large margin.

**Return value:** `pwrseq_set_power()` return value is not checked. If the GPIO request
fails silently (e.g. a pinmux race), probe continues and the eMMC may not respond to CMD1.
This matches U-Boot error-handling conventions and is acceptable for bring-up.

#### Change 3 — Remove `.use_internal_cd = true` from `mt7620_compat`

This removes a subtle property that was silently overwriting the DTS value.

The driver model calls `of_to_plat` **before** `probe`. In `of_to_plat`:

```c
host->builtin_cd = dev_read_u32_default(dev, "builtin-cd", 0);   // reads DTS → 0
```

Then in `probe` (with the old code):

```c
if (host->dev_comp->use_internal_cd)   // mt7620_compat had this true
    host->builtin_cd = 1;              // overwrites the DTS value!
```

Our board DTS has `builtin-cd = <0>`, but probe was resetting it to 1. With `use_internal_cd`
removed, the DTS value survives and `builtin-cd = <0>` correctly takes effect.

**What `builtin_cd = 1` would do wrong:**

`msdc_init_hw` gates on `builtin_cd` to decide whether to enable the MSDC controller's
hardware card-detect circuit:

```c
if (host->builtin_cd)
    clrsetbits_le32(&host->base->msdc_ps, MSDC_PS_CDDBCE,
        FIELD_PREP(MSDC_PS_CDDBCE, DEFAULT_CD_DEBOUNCE) | MSDC_PS_CDEN);
else
    clrbits_le32(&host->base->msdc_ps, MSDC_PS_CDEN);
```

With `builtin_cd = 1`, `MSDC_PS_CDEN` is set and `msdc_ops_get_cd` reads `MSDC_PS_CDSTS`
(the MSDC controller's native hardware CD input pin). In IoT mode the SD signals are routed
through MDI pads P3/P4; the MSDC controller's native CD input belongs to its non-IoT
(router-mode) wiring and is not connected to anything meaningful in our setup — it is
floating or held by an internal pull.

**Why it does not hard-fail today with `non-removable`:**

`non-removable` in the DTS causes `mmc_of_parse` to set `MMC_CAP_NONREMOVABLE`.
U-Boot's `mmc_start_init` guards the card-detect check:

```c
if (!(mmc->cfg->host_caps & MMC_CAP_NONREMOVABLE)) {
    if (!mmc_getcd(mmc))          // calls msdc_ops_get_cd
        return -ENOMEDIUM;
}
```

With `non-removable` set, `mmc_getcd` is never called, so the bad `MSDC_PS_CDSTS` read
never happens and enumeration proceeds. The failure is masked.

**When it would fail:**

Remove `non-removable` (for example, to test with a genuinely removable microSD card):

- `mmc_getcd` → `msdc_ops_get_cd` is called
- Reads `MSDC_PS_CDSTS` — the floating/undefined MSDC native CD pin
- A floating-high CD pin decodes as "not present": `msdc_ops_get_cd` returns 0
- `mmc_start_init` returns `-ENOMEDIUM`
- U-Boot prints **"MMC: no card present"** and aborts
- No CMD is ever sent to the bus, even with a card physically connected

The DTS property `builtin-cd = <0>` exists precisely to prevent this — it selects the
`#else` branch which disables `MSDC_PS_CDEN` and makes `msdc_ops_get_cd` fall through to
the GPIO-CD or always-present path. `use_internal_cd = true` made that property a no-op.

**No regression for other boards:** every other board using `mt7620_compat` inherits
`builtin-cd = <1>` from either `mt7628a.dtsi` or `mt7620.dtsi`. They receive `builtin_cd = 1`
via DTS rather than the compat flag — identical runtime behaviour.

---

### U-Boot — static link, no packaging concern

In U-Boot, `CONFIG_PWRSEQ` and `CONFIG_MMC_PWRSEQ` are **boolean** Kconfig symbols, not
tristates. Everything compiles directly into the `u-boot` binary; there are no modules.

Verified against the built `u-boot/u-boot` binary and object files:

| Check | Evidence |
|-------|----------|
| `CONFIG_PWRSEQ=y` | `bodybytes_defconfig` line 80 |
| `CONFIG_MMC_PWRSEQ=y` | `bodybytes_defconfig` line 83 |
| `CONFIG_DM_GPIO=y` (required by `MMC_PWRSEQ`) | `.config` |
| `drivers/misc/pwrseq-uclass.o` compiled | file present in build tree |
| `drivers/mmc/mmc-pwrseq.o` compiled | file present in build tree |
| `mmc_pwrseq_get_power` linked in | `nm u-boot \| grep mmc_pwrseq_get_power` ✓ |
| `mmc_pwrseq_set_power` linked in | `nm u-boot \| grep mmc_pwrseq_set_power` ✓ |
| `pwrseq_set_power` linked in | `nm u-boot \| grep pwrseq_set_power` ✓ |
| Driver registered for `mmc-pwrseq-emmc` | `_u_boot_list_2_driver_2_mmc_pwrseq_drv` in binary |
| Uclass registered | `_u_boot_list_2_uclass_driver_2_pwrseq` in binary |

`CONFIG_IS_ENABLED(MMC_PWRSEQ)` in `mtk-sd.c` resolves to `CONFIG_MMC_PWRSEQ` in a
non-SPL build. Since that is `=y`, the `mmc_pwrseq_get_power()` / `pwrseq_set_power()`
call block in `msdc_probe()` is compiled in and will fire at MMC probe time.

**Pulse behaviour** (`u-boot/drivers/mmc/mmc-pwrseq.c`):

```c
dm_gpio_set_value(&reset, 1);   // assert RST_n (GPIO_ACTIVE_LOW → physical LOW)
udelay(1);                       // hold ≥ 1 µs (JEDEC tRSTW minimum)
dm_gpio_set_value(&reset, 0);   // deassert RST_n (physical HIGH)
udelay(200);                     // wait ≥ 200 µs before CMD0 (JEDEC tRSTH)
```

### OpenWRT — `mmc-pwrseq-emmc` vs `mmc-pwrseq-simple`

Linux has two power-sequencer drivers. Choosing the wrong one would mean the RST\_n pulse
never happens during eMMC initialisation.

| Driver | compatible | Kconfig | Ops implemented | When called |
|--------|-----------|---------|----------------|-------------|
| `pwrseq_emmc.ko` | `mmc-pwrseq-emmc` | `CONFIG_PWRSEQ_EMMC` | `.reset` | `mmc_pwrseq_reset()` → `_mmc_hw_reset()` — during card init and error recovery |
| `pwrseq_simple.ko` | `mmc-pwrseq-simple` | `CONFIG_PWRSEQ_SIMPLE` | `.pre_power_on` / `.post_power_on` / `.power_off` | Host power-on / power-off cycle |

`mmc-pwrseq-emmc` is definitively correct for eMMC RST\_n:

- Its `.reset` op is invoked by `mmc_pwrseq_reset()` inside `_mmc_hw_reset()` during
  `mmc_init_card()`, which is exactly when the spec requires RST\_n to be pulsed before
  the CMD0 / CMD1 exchange.
- It also registers a **reboot notifier** that pulses RST\_n on system reboot or shutdown,
  ensuring the eMMC reaches a clean state before power is removed.
- `mmc-pwrseq-simple` has **no `.reset` op** at all. On this board the 3.3 V rail is
  always-on and the card is `non-removable`, so the host power-on/off cycle never fires.
  Using `mmc-pwrseq-simple` would make the `mmc-pwrseq` node a no-op.

### OpenWRT — `use_internal_cd` trap in Linux kernel

The Linux kernel `mt7620_compat` struct still carries `use_internal_cd = true`. In
`msdc_drv_probe`, the condition is:

```c
if (!(mmc->caps & MMC_CAP_NONREMOVABLE) &&
    !mmc_can_gpio_cd(mmc) &&
    host->dev_comp->use_internal_cd) {
    host->internal_cd = true;
}
```

Unlike U-Boot (where the compat flag was silently overwriting the DTS value regardless
of the `non-removable` cap), the Linux kernel probe explicitly checks `MMC_CAP_NONREMOVABLE`
before setting `internal_cd`. With `non-removable` in the DTS, `MMC_CAP_NONREMOVABLE` is
set by `mmc_of_parse` before this check runs, so `internal_cd` stays false.

**No kernel driver patching is needed** — `non-removable` in the DTS is sufficient.

Without `non-removable`, `internal_cd = true` would follow, and `msdc_init_hw` would
enable `MSDC_PS_CDEN` (hardware CD detection on the controller's native CD pin). In IoT
mode that pin is from the non-IoT router-mode wiring — floating/undefined, exactly the
same failure as U-Boot's `MSDC_PS_CDSTS` trap.

### OpenWRT — kernel patches for MT7628 (`mtk-sd.c` 831-01/02/03)

Three OpenWRT-specific patches to `drivers/mmc/host/mtk-sd.c` add MT7628 support:

#### Patch 831-01 — `mips_mt762x` flag

Adds `mips_mt762x = true` to `mt7620_compat` and three code paths that fire when this
flag is set:

1. **`msdc_set_mclk`** (clock change handler): when `actual_clock > 25 MHz`, sets
   `MSDC_IOCON_RSPL | MSDC_IOCON_DSPL | MSDC_IOCON_W_DSPL` (response/data/write latch
   on falling edge). This is the tuning configuration that makes SD/MMC High Speed work
   at 25–48 MHz on MT7628 without the standard pad-delay tuning algorithm.

2. **`msdc_init_hw`** (hardware init): hardcodes pad drive strength and read-delay
   registers:
   ```
   MSDC_PAD_CTRL0 = 0x000d0044   (CLK pad: 12 mA drive)
   MSDC_PAD_CTRL1 = 0x000e0044   (CMD pad: 14 mA drive)
   MSDC_PAD_CTRL2 = 0x000e0044   (DAT pads: 14 mA drive)
   MSDC_PAD_TUNE  = 0x84101010   (CMD/CLK/DAT rising-edge sample delays)
   MSDC_DAT_RDDLY0/1 = 0x10101010
   ```
   These values come from the MediaTek vendor SDK and are not DTS-configurable on MT7628.

#### Patch 831-02 — `support_cmd23 = false`

Sets `support_cmd23 = false` in `mt7620_compat`, which prevents `MMC_CAP_CMD23` from
being set in `msdc_drv_probe`. CMD23 (SET\_BLOCK\_COUNT, auto-issued before CMD18/25) is
not reliably supported by the MT7628 MSDC controller version.

Without this patch, enabling CMD23 causes I/O errors empirically observed on
MT7621+eMMC (same controller IP family):
```
mtk-msdc 1e130000.mmc: msdc_track_cmd_data: cmd=6 arg=03B30101; host->error=0x00000002
I/O error, dev mmcblk0boot0, sector 0 op 0x0:(READ) flags 0x80700
```

This is a correctness fix, not just a performance trade-off.

#### Patch 831-03 — skip `MSDC_PATCH_BIT/BIT1` for MT762x

Wraps the `MSDC_PATCH_BIT` and `MSDC_PATCH_BIT1` initialization in `msdc_init_hw`
with `if (!host->dev_comp->mips_mt762x)`. MT7628's register layout for these fields
differs from later SoCs; writing the values intended for MT8173/MT7622 corrupts the
controller state. Using the hardware reset defaults is correct for MT7628.

### OpenWRT — `kmod-sdhci-mt7620` vs `kmod-mmc-mtk`

Two competing kernel packages implement the MT7628 SDXC controller:

| Package | Kconfig | compatible string | Driver | `mmc_of_parse` |
|---------|---------|------------------|--------|----------------|
| `kmod-mmc-mtk` | `CONFIG_MMC_MTK` | `mediatek,mt7620-mmc` | `drivers/mmc/host/mtk-sd.c` (upstream) | Yes — reads all DTS props |
| `kmod-sdhci-mt7620` | `CONFIG_MTK_MMC` | `ralink,mt7620-sdhci` | `target/linux/ramips/files/drivers/mmc/host/mtk-mmc/sd.c` (out-of-tree) | No — hardcodes f_max=48 MHz |

The two packages declare `CONFLICTS:=kmod-mmc-mtk` / `CONFLICTS:=kmod-sdhci-mt7620` — only
one can be installed. The board package list in `mt76x8.mk` is set to **`kmod-mmc-mtk`**
(upstream). The out-of-tree `kmod-sdhci-mt7620` was trialled temporarily but did not call
`mmc_of_parse()`, so `mmc-pwrseq` (RST\_n pulse) and most DTS properties were silently
ignored. Reverted to `kmod-mmc-mtk`.

### OpenWRT — `pwrseq_emmc.ko` packaging root cause

The generic kernel config (`target/linux/generic/config-6.12`) sets both
`CONFIG_PWRSEQ_EMMC=y` and `CONFIG_PWRSEQ_SIMPLE=y`. However, `CONFIG_PWRSEQ_EMMC` has
`depends on MMC`. Because `CONFIG_MMC` is pulled in as a **module** (`=m`) by the MMC
packages, Kconfig's dependency resolution downgrades both to `=m` at build time:

```
generic/config-6.12:  CONFIG_PWRSEQ_EMMC=y   (intent)
actual kernel .config: CONFIG_PWRSEQ_EMMC=m   (after oldconfig, MMC=m forces this)
```

Both `pwrseq_emmc.ko` and `pwrseq_simple.ko` get compiled and land in the build directory,
but neither appeared in any package's `FILES` list. This board is the first in the OpenWRT
tree to use `mmc-pwrseq-emmc`; there is no prior art to follow.

**Fix** (`openwrt/target/linux/ramips/modules.mk`): `CONFIG_PWRSEQ_EMMC` was added to
`kmod-mmc-mtk`'s `KCONFIG` with `pwrseq_emmc.ko` in `FILES`. Now that the board is back on
`kmod-mmc-mtk`, this fix is active and `pwrseq_emmc.ko` will be installed alongside the
driver, enabling RST\_n pulses via `mmc-pwrseq-emmc`.

---

## Wiring checklist (VoCore2 + Adafruit 4682)

Before applying DTS changes, verify the physical connections:

| VoCore2 breakout pad | Signal | Adafruit 4682 / reader board |
|---------------------|--------|------------------------------|
| P4RP | SD\_CLK | CLK |
| P4RN | SD\_CMD | CMD |
| P3RN | SD\_D0 | D0 |
| P3RP | SD\_D1 | D1 |
| P4TN | SD\_D2 | D2 |
| P4TP | SD\_D3 | D3 |
| P1TN | RST\_n | RST\_n tap on reader board R1 |
| GND | GND | GND |
| 3.3VO | 3V3 | 3V3 |

Notes:
- The Adafruit 4682 CD (card-detect) pin should be left unconnected (or pulled high); the DTS uses `non-removable`.
- The RST\_n tap on the Hardkernel reader board is a bridge wire across R1 pads. R1 is a pull-up, so RST\_n sits at 3.3 V when undriven — this is correct (RST\_n deasserted = eMMC operating).
- The P1TN pad on VoCore2 is **not** on the main connector row. It is on the second row (MDI pad side) of the VoCore2 module footprint and requires a soldered pin header or a direct wire to the SMD pad.

---

## DTS verification against VoCore2 pinout

Verified against https://vocore.io/v2.html. All SD card signals are on MDI ports 3 and 4 (IoT mode).

| Signal | GPIO | MDI pad | VoCore2 pin | DTS setting responsible |
|--------|------|---------|-------------|------------------------|
| CLK | 26 | P4RXP | 54 | `sdmode=sdxc` + `esd=iot` |
| CMD | 27 | P4RXN | 55 | `sdmode=sdxc` + `esd=iot` |
| DAT0 | 25 | P3RXN | 52 | `sdmode=sdxc` + `esd=iot` |
| DAT1 | 24 | P3RXP | 51 | `sdmode=sdxc` + `esd=iot` |
| DAT2 | 29 | P4TXN | 57 | `sdmode=sdxc` + `esd=iot` |
| DAT3 | 28 | P4TXP | 56 | `sdmode=sdxc` + `esd=iot` |
| RST\_n | 15 | P1TXN | 42 | `spis=gpio` + `emmc_pwrseq` |
| Hall sensor | 14 | P1TXP | 40 | `spis=gpio` |

### Why each register setting is needed

**`esd=iot` (GPIO\_MODE1\[15\]=0):** Routes the SDXC controller's CLK/CMD/DAT signals to the MDI/EPHY pad group instead of the alternative I2S/I2C/UART1 pad group. Hardware reset default is already 0 (iot); set explicitly for clarity. Controlled via U-Boot group `"sd router"` and kernel group `"esd"` — both target GPIO\_MODE1 bit 15.

**`sdmode=sdxc` (GPIO\_MODE1\[11:10\]=01):** Enables the SDXC controller on the MDI pads. Without this the pads stay in GPIO/JTAG mode and the SDXC controller never drives them.

**`ephy-digital-mask = <0x7>` / `p123_digital` (AGPIO\_CFG\[19:17\]=0x7, bit\[20\]=0):** Sets MDI ports P1/P2/P3 to digital mode (decouples from EPHY analog circuitry), leaves P4 analog. P4 analog is critical: AGPIO\_CFG\[20\]=1 (P4 digital) enables the EPHY P4 RX input buffer on P4RXP (CLK) and P4RXN (CMD), which presents enough resistive loading to pull both below VIH=2.0V. The P4 TX pair (P4TXP=DAT3, P4TXN=DAT2) is driven by the TX buffer only and is **not affected** by bit 20 — DAT2/DAT3 work correctly with P4 in analog mode.

**`spis=gpio` (GPIO\_MODE1\[3:2\]=01):** Releases MDI P1 pads (P1TXP, P1TXN, P1RXP, P1RXN = GPIO14–17) from SPI-slave mux to GPIO mode, making GPIO14 (hall sensor, pin 44) and GPIO15 (RST\_n, pin 43) driveable.

**Pull-ups on CMD+DAT (U-Boot only):** U-Boot's `sd_bias` writes PAD\_PU\_G0 bits 25–29 (CMD, D0–D3). The Linux kernel does not reset PAD\_PU registers between stages, so these pull-ups persist from U-Boot into OpenWrt. The OpenWrt DTSI has no pull-up configuration and relies on this persistence — acceptable because U-Boot always runs before Linux on this board.

**EPHY mode timing in U-Boot:** `ephy_iot_mode` (which sets AGPIO\_CFG\[19:17\]=0x7 and clears bit 20) is referenced by `&uart2`'s pinctrl, not `&mmc`. Since `uart2` is `stdout-path` it is the first device initialized in U-Boot. AGPIO\_CFG is written before MMC probes; the hardware register holds the value until the next hardware reset.

---

## Oscilloscope test procedures (VoCore2)

Attach the oscilloscope probe ground to any GND pad on the VoCore2 breakout.
Set trigger to edge-rising. All signals are 3.3 V CMOS.

### Test 1 — CLK line activity (most fundamental)

**Probe:** P4RP (SD\_CLK, SoC pin 54)

**Expected when working:**
- U-Boot: 1 MHz square wave (~50% duty cycle) during `mmc rescan` or `mmc dev 0`.
  CLK is only present during bus transactions; it stops between commands.
- OpenWrt: up to 48 MHz bursts during enumeration and data transfer.

**If no CLK is seen:**
- The SDXC controller is not running, or the MDI pads are still in analog EPHY mode.
- Check that `sd_sdxc_mode` / `sdxc_mode` pinctrl states are being applied.
- Verify `AGPIO_CFG EPHY_GPIO_AIO_EN[4:1]` = `0xf` via U-Boot memory read:
  `md.l 0xb000003c 1` — bits [20:17] should all be 1.  (AGPIO_CFG is at SYSC offset 0x3c; 0x14 is SYSCFG1, a different register)

### Test 2 — CMD line framing

**Probe:** P4RN (SD\_CMD, SoC pin 55)

**Expected when working:**
- CMD is idle-high. Transactions begin with a start bit (0), then 6-bit command index, 32-bit argument, 7-bit CRC, end bit (1).
- During SD init: see CMD0 (GO\_IDLE, arg=0), then CMD8 (SEND\_IF\_COND), then CMD55 + ACMD41 (repeated until card ready) or CMD1 (eMMC OCR).
- Response frames follow each command (different lengths: R1=48 bit, R3/R7=48 bit, R2=136 bit).
- Trigger on the falling start bit to capture a complete command frame.

**If CLK is present but CMD stays high:**
- Pinctrl applied but driver not sending; or card is being detected as absent (missing `non-removable`).

### Test 3 — DAT0 busy / 1-bit response

**Probe:** P3RN (SD\_D0, SoC pin 52)

**Expected during card init:**
- DAT0 is pulled high by pull-up resistor when idle.
- During ACMD41 (SD) or CMD1 (eMMC) the card pulls DAT0 low ("busy") until the card completes internal initialization. This busy period can last tens of milliseconds for cold-start.
- After init, DAT0 goes high (card ready).

**Note:** If RST\_n was not pulsed (no `mmc-pwrseq`) and the eMMC is in a fault state,
DAT0 may stay low indefinitely. Adding `mmc-pwrseq` and observing a RST\_n pulse (Test 4)
clears this condition.

### Test 4 — RST\_n pulse (after adding `mmc-pwrseq`)

**Probe:** P1TN (eMMC RST\_n, SoC pin 42)

**Expected when `mmc-pwrseq-emmc` is active:**
- Line is high (3.3 V) at all times except during `mmc_pwrseq_power_on()`.
- At MMC probe time, a brief low pulse appears (typically ≥1 µs as specified by JEDEC JESD84).
- The `mmc-pwrseq-emmc` driver asserts RST\_n (drives GPIO\#15 low), waits the post-reset delay, then deasserts (drives GPIO\#15 high).
- Trigger on falling edge; expect a clean low pulse followed by the line returning to 3.3 V.

**Before `mmc-pwrseq` is added:**
- P1TN should read a static 3.3 V (reader board R1 pull-up holds RST\_n high).
- If P1TN reads 0 V, something is pulling RST\_n low — check for a GPIO direction conflict.

### Test 5 — EPHY digital mode sanity check (no SD card needed)

**Purpose:** Confirm MDI pads are in digital mode before connecting the eMMC adapter.

**Procedure:**
1. RAM-boot U-Boot via JTAG (no eMMC attached).
2. At U-Boot prompt, apply the pinctrl manually by probing the MMC:
   ```
   mmc dev 0
   ```
3. Probe P4RP (CLK) with the oscilloscope. You should see the 1 MHz clock for the
   duration of the initial card-detect sweep, then it stops.
4. Alternatively confirm with memory reads:
   ```
   # AGPIO_CFG register (contains EPHY_GPIO_AIO_EN[4:1] in bits [20:17])
   # NOTE: AGPIO_CFG is at SYSC offset 0x3c (physical 0x1000003c / KSEG1 0xb000003c).
   # Offset 0x14 is SYSCFG1, not AGPIO_CFG.
   md.l 0xb000003c 1
   ```
   Expected value: bits [20:17] = `0xf` (0001 1110 0000 0000 0000 0000 = 0x001e0000 masked).
   Full AGPIO_CFG bits [20:17] = 1 means all four MDI pad groups are in digital mode.

### Test 6 — GPIO mode check for P1TP and P1TN

**Purpose:** Confirm `state_default` correctly switches MDI P1 pads to GPIO before any user
of GPIO\#14 (hall sensor) or GPIO\#15 (RST\_n) probes.

**Procedure:**
1. At U-Boot prompt, after boot:
   ```
   gpio status 14
   gpio status 15
   ```
   Both should show as `input` or `output`, not `unknown` / `not requested`. If `gpio status`
   returns an error, the `mdi_p1_gpio` pinctrl state was not applied.

2. On oscilloscope: probe P1TN. Drive GPIO\#15 from U-Boot:
   ```
   gpio set 15        # assert (drive high)
   gpio clear 15      # deassert (drive low)
   ```
   You should see the pad transition between 3.3 V and 0 V cleanly. If the pad stays at
   an intermediate voltage or doesn't respond, the pad is still in EPHY analog mode.

---

## Debug sequence (recommended order)

All DTS fixes and the `kmod-mmc-mtk` packaging fix are already applied. Rebuild U-Boot
and OpenWrt before testing.

1. **Wiring check** — verify all jumper connections against the wiring table above.
   Use a multimeter in continuity mode before applying power.

2. **Test 5** — confirm MDI pads are in digital mode (no eMMC needed; JTAG only).

3. **Test 6** — confirm GPIO\#15 is driveable from U-Boot.

4. **RAM-boot U-Boot, run `mmc dev 0; mmc rescan`**. Watch P4RP for CLK activity
   (Test 1) and P1TN for the RST\_n pulse at probe time (Test 4).

5. **If CLK appears**: proceed to Test 2 (CMD framing) and Test 3 (DAT0 busy release).

6. **If U-Boot enumerates the eMMC**: rebuild OpenWrt with the DTSI and `modules.mk`
   changes, flash, and confirm `mmcblk0` appears in the kernel boot log.

---

## EPHY P4 RX pad bias — root cause and fix

### Observation

After all pinctrl fixes are applied and the MSDC controller initialises successfully
(MSDC\_CFG = 0x00007899, CKSTB=1), reading GPIO\_DATA (0x10000620) on a fresh boot
shows GPIO#26 (CLK = MDI\_RP\_P4) and GPIO#27 (CMD = MDI\_RN\_P4) as **LOW**, while
GPIO#24 (D1 = MDI\_RP\_P3), GPIO#25 (D0 = MDI\_RN\_P3), GPIO#28 (D3 = MDI\_TP\_P4) and
GPIO#29 (D2 = MDI\_TN\_P4) all read HIGH.

The asymmetry is specific to the **P4 RX pair** (MDI\_RP\_P4 / MDI\_RN\_P4). P3 RX pair
and P4 TX pair are unaffected. CMD idle-high is an SD/MMC protocol requirement; with CMD
stuck at ~0 V or below VIH=2.0 V the MSDC receives every CMD1 response with CARD\_BUSY=0
(all 1-bits read as 0), causing the "Card stuck being busy!" timeout loop.

MSDC\_PS (0x10130008) confirms: bit 24 = CMD pad value = 0 after failed init (reset default
is 1; it goes low when the pad voltage is below VIH).

### Pull-up architecture

There are **two separate** pull-up mechanisms in the MT7628AN MSDC subsystem:

#### 1 — MSDC PAD\_CTRL registers (0x101300E0–E8)

These control the output buffer for the **dedicated SDXC pads** (the pads used in
router/standard SDXC mode). In IoT mode the SDXC signals are routed internally to the
EPHY MDI pads; the MSDC PAD\_CTRL pull-ups do **not** affect the physical MDI pin voltage.

The MT7628 OpenWrt kernel driver (`drivers/mmc/host/mtk-sd.c`, mips\_mt762x path) writes:

| Register | Address | Value | Decoded fields |
|----------|---------|-------|---------------|
| PAD\_CTRL0 / CLK | 0x101300E0 | `0x000d0044` | DRVN=4 DRVP=4 **CLKPD=1** CLKPU=0 SMT=1 IES=1 |
| PAD\_CTRL1 / CMD | 0x101300E4 | `0x000e0044` | DRVN=4 DRVP=4 CLKPD=0 **CMDPU=1** SMT=1 IES=1 |
| PAD\_CTRL2 / DAT | 0x101300E8 | `0x000e0044` | DRVN=4 DRVP=4 CLKPD=0 **DATPU=1** SMT=1 IES=1 |

Bit layout (from `drivers/mmc/host/mtk-mmc/mt6575_sd.h`):

```
bits [ 2: 0] = DRVN   (N-driver strength 0–7)
bits [ 6: 4] = DRVP   (P-driver strength 0–7)
bit  [    8] = SR     (slew rate)
bit  [   16] = PD     (pull-down enable)
bit  [   17] = PU     (pull-up enable)
bit  [   18] = SMT    (Schmitt trigger)
bit  [   19] = IES    (input enable)
bits [23:20] = TDSEL  (TX delay)
bits [31:24] = RDSEL  (RX delay)
```

CMDPU=1 (bit 17 of 0x000e0044) is already set by the driver — but it is **ineffective** in
IoT mode because it drives the dedicated SDXC pad, not the MDI physical pad.

CLKPD=1 (bit 16 of 0x000d0044) is correct: CLK is a driven output; a pull-down keeps it
low when the controller is idle. This has no bearing on CMD.

#### 2 — Physical pad padconf registers (SYSC + 0x1300 = 0x10001300)

The SYSC padconf block provides per-pad pull-up, pull-down, Schmitt trigger, and drive
strength control for every physical GPIO/pad. These are the controls that actually affect
the MDI pin voltage. The register layout (from U-Boot `drivers/pinctrl/mtmips/pinctrl-mt7628.c`):

| Register | Physical address | Controls | Bit for GPIO#N |
|----------|-----------------|----------|---------------|
| PAD\_PU\_G0 | `0x10001300` | pull-up, GPIO#0–31 | bit N |
| PAD\_PD\_G0 | `0x10001310` | pull-down, GPIO#0–31 | bit N |
| PAD\_SR\_G0 | `0x10001320` | slew rate, GPIO#0–31 | bit N |
| PAD\_SMT\_G0 | `0x10001330` | Schmitt trigger, GPIO#0–31 | bit N |
| PAD\_E2\_G0 | `0x10001340` | 2 mA drive enable, GPIO#0–31 | bit N |
| PAD\_E4\_G0 | `0x10001350` | 4 mA drive enable, GPIO#0–31 | bit N |
| PAD\_E8\_G0 | `0x10001360` | 8 mA drive enable, GPIO#0–31 | bit N |

All SD IoT pads (GPIO#24–29) are in the G0 registers. All MDI P3/P4 pads use the
same bit index as the GPIO number (bit 26 = GPIO#26 = CLK, bit 27 = GPIO#27 = CMD, etc.).

Drive strength for sd\_clk is set to 8 mA by U-Boot's `sd_sdxc_mode`
(`drive-strength-4g = <8>` → E4=1, E8=0, PAD\_E4\_G0 bit 26 set at 0x10001350).
**No pull-up was previously set** for CMD, D0–D3 or CLK in the original `sd_iot_mode` — the padconf
pull state after reset was unknown and uncontrolled.

### Root cause

The EPHY P4 RX pair (MDI\_RP\_P4 / MDI\_RN\_P4) has a persistent analog loading that
pulls these pads below VIH=2.0 V (3.3 V domain) even after AGPIO\_CFG[20:17]=0xF sets
the pads to digital mode. This loading is absent on P3 RX pair and P4 TX pair.

The following software approaches all failed to remove the loading:
- AGPIO\_CFG[20:17] = 0xF (digital mode) — applied correctly, verified, insufficient
- EPHY\_RST (RSTCTRL bit 24) assert/deassert
- MDIO BMCR\_PDOWN to PHY 0–4 in pages 0x0 and 0x8000
- Full MT7628AN EPHY init sequence (pages 0x2000, 0x8000, 0xa000)

**Datasheet coverage:** The MT7628 datasheet (confirmed by full-text search) documents
MDI pads as type "A" (Analog) with no I/O voltage spec, no input impedance, no threshold
voltages, and no description of what happens to the EPHY's internal RX circuitry when
AGPIO\_CFG switches the pad to digital mode. AGPIO\_CFG simply "selects digital PAD" without
specifying whether EPHY analog circuits are powered down or remain connected. There is no
documented 100 Ω differential termination, center-tap voltage, or equivalent circuit for
the MDI pins in digital mode. The internal mechanism causing the P4 RX loading is unknown
from the public datasheet.

The P3 RX pair (MDI\_RP\_P3 / MDI\_RN\_P3) works with 47 kΩ external pull-ups, confirming
that when the loading is absent the pads reach VIH. The P4 RX pair has something specific
to that port — possibly different EPHY port power state, a different internal RX front-end
design for P4, or undocumented EPHY P4 bias circuitry that AGPIO\_CFG digital-mode
switching does not disconnect.

### Applied fix — U-Boot board DTS (`bodybytes,bodybytes.dts`)

A board-specific pinctrl state `sd_bias` is added to `&pinctrl`, and wired into
`&mmc` alongside `sd_sdxc_mode`:

```dts
&pinctrl {
    sd_bias: sd_bias {
        pins = "sd_cmd", "sd_d0", "sd_d1", "sd_d2", "sd_d3";
        bias-pull-up;
    };
};

&mmc {
    pinctrl-0 = <&sd_sdxc_mode &sd_bias>;
};
```

This sets PAD\_PU\_G0 bits 25–29 at 0x10001300, enabling the SoC's internal pull-up
resistors on the physical MDI pad lines for CMD and all four data pins. CLK (GPIO#26,
bit 26) is excluded: it is a driven output and already has an internal pull-down via
MSDC PAD\_CTRL0 (CLKPD=1); adding an opposing pull-up is unnecessary.

The fix is board-specific (`bodybytes,bodybytes.dts`) rather than in the shared
`mt7628a.dtsi` because the pull-up need is specific to this board's EPHY P4 RX bias
issue and should not affect other boards.

### Why U-Boot must apply this and Linux cannot

The Linux kernel's MT7628 pinctrl driver (`drivers/pinctrl/mediatek/pinctrl-mt76x8.c`)
only registers `pmxops` (mux switching via GPIO\_MODE). It does not register `confops`
(`pinconf_ops`), so the kernel pinctrl core has no handler for `bias-pull-up`,
`drive-strength`, or any other pad configuration property on this SoC. Any such
properties in the Linux DTS are silently ignored — the pinctrl DT parser never calls
into the driver for them.

The U-Boot driver (`drivers/pinctrl/mtmips/pinctrl-mt7628.c`) does implement
`mt7628_pinconf_set` and registers it as `.set_state`. It reads `bias-pull-up` from the
DTS and writes PAD\_PU\_G0 via the padconf MMIO block at SYSC+0x1300.

### Why the configuration persists into Linux

The padconf registers (0x10001300–0x10001360) are in the SYSC block and have no reset
triggered by the kernel. Nothing in the Linux boot sequence touches them:

- The kernel MT7628 pinctrl driver only writes to GPIO\_MODE (0x10000060/64) for mux
  switching. It never accesses the padconf range at 0x10001300.
- The MSDC driver writes PAD\_CTRL0/1/2 at 0x101300E0–E8 (MSDC-internal registers),
  not the SYSC padconf block.
- No other kernel driver claims or resets the SYSC+0x1300 range.

So the PAD\_PU\_G0 bits set by U-Boot at MMC probe time remain set for the entire Linux
session. Linux's `sdhci` / `mtk-sd` driver benefits from the pull-ups without being
aware they were configured by U-Boot.

### SSH diagnosis results

Two diagnostic sessions were performed over SSH. Session 1 used the SB Components board
(10 kΩ CMD pull-up, CLK pull-up removed). Session 2 used no card (all signals floating).

#### Session 1 register snapshot (SB Components board attached)

| Register | Address | Value | Interpretation |
|----------|---------|-------|---------------|
| GPIO\_MODE1 | `0x10000060` | `0x50050404` | SDMODE=01 (SDXC) ✓ — correct on this boot |
| AGPIO\_CFG | `0x1000003c` | `0x00FE00FF` | ESD=iot (was ✓ under old config; now ESD bit removed — see §Standard SDXC mode experiment), EPHY\_GPIO\_AIO\_EN=0xF ✓ |
| PAD\_PU\_G0 | `0x10001300` | `0x3B000400` | CMD+D0-D3 pull-ups set ✓, CLK excluded ✓ |
| PAD\_PD\_G0 | `0x10001310` | `0x00000000` | No pull-downs ✓ |
| GPIO\_DATA | `0x10000620` | `0xF36CFC70` | CMD=0 (LOW), CLK=0 (LOW), D0–D3=1 (HIGH) |
| MSDC\_PS | `0x10130008` | `0x00000000` | All MSDC pad inputs read zero (expected, see below) |
| PAD\_CTRL0/1/2 | `0x101300E0–E8` | `0x00000000` | All zero — writes do not stick (see below) |

**SDMODE=00 on some cold boots:** On the first cold-boot snapshot SDMODE read as 00;
on the second boot (session 1 above) it was 01. The variation is a sampling artefact:
SDMODE=00 is read *after* probe failure cleanup reverted the mux via `devm_pinctrl_put()`.
Rebooting again reproduced SDMODE=01 during the active probe window.

**PAD\_CTRL registers do not retain writes:** Writing 0x000e0044 to PAD\_CTRL1
(0x101300E4) reads back immediately as 0x00000000. These registers appear to be
non-writable at this address on MT7628AN in the current MSDC configuration (possibly
cleared by the `hrst` that fires at every bind, or unimplemented in this SoC variant).
In any case, MSDC PAD\_CTRL PU=1 has no effect on CMD voltage.

**MSDC\_PS=0 is expected in IoT mode:** MSDC\_PS reflects the dedicated SDXC pad input
path. In IoT mode the active signal path goes through the MDI pads; the dedicated SDXC
pad inputs are floating and always read zero. GPIO\_DATA is the correct register for
actual MDI pad voltages.

#### Session 2: no card, GPIO drive test

With the card disconnected and signals floating, CMD and CLK were driven directly as
GPIO outputs from the CPU to measure whether the EPHY P4 RX loading can be overcome.

Baseline (no card, SDMODE=01, internal padconf pull-up only):
- GPIO\_DATA = 0xF36CF470 → CMD=LOW, CLK=LOW, D0–D3=HIGH

Driving GPIO#27 (CMD) HIGH via GPIO\_CTRL/GPIO\_DATA:
- GPIO\_DATA → 0xFB6CF470 → CMD bit = 1 (**CMD went HIGH ✓**)

Driving GPIO#26 (CLK) HIGH additionally:
- GPIO\_DATA → 0xFF6CFC70 → CLK bit = 1 (**CLK went HIGH ✓**)

Restoring to inputs:
- GPIO\_DATA → 0xF36CFC70 → CMD=LOW, CLK=LOW immediately

**Key conclusion:** The SoC's own GPIO digital driver (low output impedance, ~50–100 Ω)
CAN bring CMD above VIH=2.0 V. The EPHY P4 RX loading is not an absolute clamp — it can
be overcome by an active driver. But the internal padconf pull-up (~100–200 kΩ equivalent)
and a 10 kΩ external pull-up both cannot hold CMD above VIH; the loading source impedance
is well below 10 kΩ.

#### Session 2: no-card rebind confirms CMD response is the failure

After rebind with no card, the MSDC produced "Card stuck being busy!" — identical to the
card-attached case. This is definitive:

- With no card, CMD1 should produce a **response timeout** (no pull of CMD at all)
- Instead, the MSDC sees **a response with OCR[31]=0** (busy bit = card not ready)
- This only happens if the MSDC IS receiving a response — specifically, CMD reading as all
  zeros during every response bit, including OCR[31]
- CMD below VIH = logic 0 = "card busy" for every bit of every response frame

The MSDC IS successfully sending the CMD1 command frame (push-pull drive overcomes the
EPHY loading). But during the response window the MSDC releases CMD and only the padconf
pull-up remains — CMD falls below VIH and the MSDC reads all zeros.

Summary of failure modes by phase:

| Phase | CMD level | Driver | Result |
|-------|-----------|--------|--------|
| MSDC sends CMD1 frame | HIGH ✓ | MSDC push-pull (~1–5 Ω output Z) | Overcomes EPHY loading |
| Response window: card/no-card releases CMD | LOW ✗ | Padconf PU ~100 kΩ (+ ext. 10 kΩ) | Below VIH — all bits read as 0 |
| MSDC reads OCR[31] | 0 (not ready) | — | "Card stuck being busy" retry |

### Next experiment — low-resistance CMD pull-up (hardware fallback)

If the standard SDXC mode experiment (§Standard SDXC mode experiment) does not resolve the
CMD loading, the GPIO drive test bounds the EPHY loading: between "stronger than 10 kΩ" and
"weaker than a GPIO driver". Try a resistor in the 100–500 Ω range between CMD (P4RN breakout
pad) and 3.3 V. A 100 Ω pull-up draws ~12–18 mA on CMD HIGH — too high for production but
sufficient to confirm whether the loading source can be overcome with a lower-value resistor.

If CMD enumerates with a ≤500 Ω pull-up: the bodybytes PCB's 10 kΩ CMD pull-up is
insufficient and must be reduced on the next board revision, or CMD must be routed to a
non-P4-RX pad. The MSDC CMD mapping to MDI\_RN\_P4 is fixed in SoC hardware.

---

## Standard SDXC mode experiment (esd=iot removal)

### Background: VoCore2 vendor firmware analysis

The VoCore2 uses the same MT7628AN SoC and identical MDI pad routing. To understand how
the vendor solved the same hardware bring-up, the stock firmware
(`vocore2_stock_firmware_20240316.23062.bin`) was reverse-engineered:

1. The binary is a uImage (64-byte header + LZMA payload).
2. `binwalk` extracted the LZMA payload; `xz -d --suffix .lzma` decompressed a 7.4 MB kernel.
3. The FDT magic (`\xd0\x0d\xfe\xed`) was located at offset 0x756c80 in the decompressed
   kernel image; `dtc -I dtb -O dts` produced the full DTS from the 9168-byte DTB.

Key findings from the extracted DTS (Linux 5.15.137, built 2023-11-14):

```dts
sdhci@10130000 {
    compatible = "ralink,mt7620-sdhci";
    status = "disabled";   /* SD not used in stock firmware */
    pinctrl-0 = <&sdxc_pinctrl>;
    ...
};

sdxc_pinctrl: sdxc_pinctrl {
    groups = "sdmode";
    function = "sdxc";
    /* NO esd group, NO ephy-digital */
};
```

**The vendor never used `esd=iot` for SDXC.** There is no `ephy-digital` property either.
The SDXC pinctrl in the stock firmware is a single `sdmode=sdxc` group with nothing else.
The `esd=iot` used by the OpenWrt VoCore2 DTSI and the original bodybytes DTSI was a
community addition not derived from vendor practice.

The U-Boot binary (`vocore2_stock_uboot128m.20190625.bin`) contained no embedded DTB — it
uses old U-Boot with hardcoded board configuration. No DTS was recoverable from the
U-Boot binary.

### Root cause — confirmed

The loading is caused by **`ephy-digital` (AGPIO\_CFG bit 20) enabling the EPHY P4 digital
input buffer**, which presents a resistive load strong enough to hold CMD (MDI\_RN\_P4) and
CLK (MDI\_RP\_P4) below VIH=2.0 V, overwhelming the padconf pull-up (~100–200 kΩ) and
any external pull-up ≥10 kΩ.

Confirmed via `devmem` on a running system (SSH):

| Action | AGPIO\_CFG | GPIO\_DATA CMD (bit 27) |
|--------|-----------|------------------------|
| Baseline (ephy-digital set, ESD=iot) | `0x00FE00FF` | **0 (LOW)** |
| Clear ESD bit only (bit 1=0) | `0x00FE00FD` | **0 (LOW)** — ESD not the cause |
| Clear P4 digital mode (bit 20=0) | `0x00EE00FD` | **1 (HIGH)** ✓ |

Clearing bit 20 (P4 EPHY digital mode) immediately unloaded CMD and CLK.

The ESD/IoT routing bit (`esd=iot`) was **not** the cause — AGPIO\_CFG's reset default
already has ESD=1, and clearing it did not affect CMD. The IoT routing is required to route
SDXC to the MDI pads and must remain.

The loading is absent on P3 and P4 TX pairs (DAT0/DAT1 and DAT2/DAT3 are all HIGH) because
only the EPHY P4 RX pair pads have this specific input buffer behaviour. This may be
related to P4 being a special EPHY port (CPU/uplink) with different internal circuitry.

### Changes applied

**OpenWrt (`mt7628an_bodybytes_bodybytes.dtsi` + `mt76x8.mk` + patch 809):**
- ~~`compatible = "ralink,mt7620-sdhci"`~~ — **subsequently reverted**; back to `kmod-mmc-mtk` (upstream `mediatek,mt7620-mmc`) which calls `mmc_of_parse()` and supports `mmc-pwrseq`
- ~~`kmod-sdhci-mt7620` replaces `kmod-mmc-mtk`~~ — **reverted**; board package list uses `kmod-mmc-mtk` again
- `sdxc_mode` now has both `esd=iot` + `sdmode=sdxc` (esd re-added for explicit clarity; it was always the default)
- `pinctrl-names = "default"` drops `state_uhs` ✓ (kept)
- `ephy-digital-mask = <0x7>` replaces `ephy-digital` — sets P1/P2/P3 digital, P4 stays analog ✓ (kept)
- Kernel patch 809 extended: added `ephy-digital-mask` u32 property (writes `(mask & 0xf) << 17` to AGPIO\_CFG) ✓ (kept); `else` → `else if (of_property_present(...))` guard ✓

**U-Boot (`bodybytes,bodybytes.dts` + `pinctrl-mt7628.c`):**
- `ephy_iot_mode` overridden in board DTS: child renamed to `ephy4_1_dis` (matches base DTSI name for proper DTC merge); uses `function = "p123_digital"` ✓
- `FUNC("p123_digital", 0x7)` added to `ephy4_1_pad_grp` in U-Boot pinctrl driver ✓
- `sd_sdxc_mode` adds explicit `esd_iot { groups = "sd router"; function = "iot"; }` sub-node ✓
- `sd_bias` unchanged ✓

**Net effect:** AGPIO\_CFG bits [20:17] = 0xf at both U-Boot and Linux init. All four EPHY groups in digital mode — MSDC has full access to CLK and CMD pads. P4 analog mode was found to disconnect the MSDC digital path entirely (MSDC cannot drive or sample CLK/CMD), which is worse than the EPHY input buffer loading. The EPHY P4 input buffer loading pulls CMD/CLK LOW in idle, but push-pull communication still works: MSDC (~50 Ω output) and the card (~50 Ω output) both overcome the ~500 Ω EPHY load during command and response phases.

### Outcomes

| State | CMD idle | MSDC access to CLK/CMD | Result |
|-------|----------|------------------------|--------|
| `ephy-digital` (0xF) — all digital | LOW (EPHY P4 input buffer loads idle) | **Yes** — push-pull comms work | To be validated |
| `ephy-digital-mask = <0x7>` (P4 analog) | HIGH (no loading) | **No** — MSDC digital path disconnected from pads | "Card stuck being busy!" (MSDC CMD input floats at 0, all-zeros = busy) |

---

## External pull-up recommendations

### Per-signal summary

| Signal | SoC pad | GPIO# | Direction | SD/eMMC spec | Target HW (bodybytes PCB) | Dev board (SB Components) | Dev board (Adafruit 4682) |
|--------|---------|-------|-----------|-------------|--------------------------|--------------------------|--------------------------|
| CLK | MDI\_RP\_P4 | 26 | SoC→card output | No pull-up; idle-low | None ✓ | 10 kΩ — **remove before use** | 47 kΩ (present but weak) |
| CMD | MDI\_RN\_P4 | 27 | Bidirectional open-drain init | Pull-up required | **10 kΩ** ✓ | 10 kΩ ✓ | None (missing on Adafruit) |
| DAT0 | MDI\_RN\_P3 | 25 | Bidirectional (open-drain busy) | Pull-up required | **50 kΩ** ✓ | 10 kΩ ✓ | 47 kΩ ✓ |
| DAT1 | MDI\_RP\_P3 | 24 | Bidirectional | Pull-up after 4-bit mode | **50 kΩ** ✓ | 10 kΩ ✓ | 47 kΩ ✓ |
| DAT2 | MDI\_TN\_P4 | 29 | Bidirectional | Pull-up after 4-bit mode | **50 kΩ** ✓ | 10 kΩ ✓ | 47 kΩ ✓ |
| DAT3 | MDI\_TP\_P4 | 28 | Bidirectional | Pull-up after 4-bit mode | **50 kΩ** ✓ | 10 kΩ ✓ | 47 kΩ ✓ |
| RST\_n | MDI\_TN\_P1 | 15 | SoC→card output | Pulled to VMMC when idle | **50 kΩ** ✓ | via reader board R1 | via reader board R1 |

### Target hardware evaluation (bodybytes PCB)

**CLK — no pull-up ✓**
Correct. The SD spec explicitly prohibits a pull-up on CLK ("CLK should be driven to low"). MSDC PAD\_CTRL0 CLKPD=1 holds it low between bus transactions via the internal MSDC mechanism. Nothing to add.

**CMD — 10 kΩ ✓ (spec) / ⚠️ may be insufficient (EPHY loading)**
CMD is the most critical line: it is open-drain during the entire init phase (CMD0, CMD1/ACMD41 OCR negotiation) and only switches to push-pull for fast data-phase commands. A 10 kΩ pull-up gives a fast rise time (~50–100 ns with typical PCB trace capacitance of 5–10 pF), well within timing margins at both 1 MHz bring-up and 25 MHz production speed.

However, CMD (GPIO#27, MDI\_RN\_P4) is on the EPHY P4 RX pair, which has an undocumented
analog loading that pulls CMD below VIH=2.0 V. SSH diagnosis with the SB Components board
(10 kΩ CMD pull-up) confirmed CMD reads LOW despite padconf pull-up enabled (then named `sd_iot_bias`, now `sd_bias`) and D0–D3
reading HIGH. The EPHY P4 RX loading impedance is below 10 kΩ; the bodybytes PCB's 10 kΩ
pull-up does not bring CMD to VIH. A hardware experiment with a ≤100 Ω pull-up is needed
to characterise the loading source impedance (see §SSH diagnosis results). If the impedance
proves to require ≤130 Ω, the CMD pad assignment to MDI\_RN\_P4 is a fundamental limitation
and a future PCB revision must avoid P4 RX for CMD.

**DAT0–3 — 50 kΩ ✓**
Acceptable and within the JEDEC JESD84 recommended range (10 kΩ–100 kΩ). Analysis per sub-signal:

- **DAT0** (MDI\_RN\_P3, GPIO#25, P3 RX pair — no EPHY bias): used for open-drain busy signalling during write operations. With 50 kΩ and 5–10 pF PCB trace capacitance, τ ≈ 250–500 ns. At 1 MHz (bring-up) this is fine: the controller clocks DAT0 and the 50 kΩ brings it high well within the next clock cycle. At 25 MHz the controller samples DAT0 over multiple clock cycles until it sees HIGH, so the slower rise time adds only a few extra cycles of polling, not a protocol violation. Once the card exits busy, DAT0 is push-pull and the pull-up value is irrelevant.
- **DAT1–3** (P3 RP, P4 TN, P4 TP — no EPHY bias): after the initial 1-bit mode phase the eMMC device disconnects its internal pull-ups on these lines. They become idle between transfers and need the host pull-up to hold them high. 50 kΩ is sufficient; there is no open-drain use of DAT1–3.

**RST\_n — 50 kΩ ✓**
RST\_n is a static signal — driven low briefly at MMC probe time by `mmc-pwrseq-emmc`, then released and held high by the pull-up for the rest of operation. 50 kΩ is perfectly adequate for a static rail; there are no rise/fall time concerns. Current draw while driving low: 3.3 V / 50 kΩ = 66 µA, for the duration of the reset pulse only (microseconds).

**Design rationale**
The bodybytes PCB pull-up assignment reflects a correct priority ordering:
1. CMD gets the smallest resistor (10 kΩ) because it is open-drain during init, has the tightest timing requirement, and is on the EPHY-affected P4 RX pad.
2. DAT0–3 get 50 kΩ: lighter pull-ups reduce static power, are sufficient for the limited open-drain use (DAT0 busy only), and avoid unnecessary loading during push-pull data transfer.
3. RST\_n gets 50 kΩ: adequate for a static rail, consistent with DAT value.
4. CLK has no pull-up: correct per spec.

No changes required to the target hardware pull-up network.

### What the specs say

**SD Physical Layer Simplified Spec v9.10:**
- CLK: "CLK (without pull-up resistor) should be driven to low" — explicitly prohibits a CLK pull-up.
- DAT3 at power-up: the card has a **50 kΩ internal pull-up** for card-detect and SPI/SD mode selection. This is the card's own pull-up, not a host requirement. Disabled by ACMD42 for normal data transfer. eMMC has no equivalent.
- Host-side external resistor values are not in the simplified spec; they come from the full spec and reference designs.

**Kingston eMMC datasheet (EMMC128-IY29-5B111):**
- DAT1–DAT7: internal pull-ups present in 1-bit mode; "Immediately after entering the 4-bit mode, the device disconnects the internal pull-ups of lines DAT1, DAT2, and DAT3." Host must supply pull-ups in 4-bit mode.
- CMD: open-drain during init, push-pull for fast command transfer. Host pull-up required.
- RST\_n: JEDEC JESD84 requires it pulled to VMMC when not driven if RST\_n is in use.

**VoCore2 SD schematic (same MT7628AN SoC):**
- R2, R3, R7, R8 = **10 kΩ** on all SD data and command lines.
- Used as the reference for the recommended 10 kΩ CMD value; the bodybytes PCB follows this for CMD and uses lighter 50 kΩ on DAT.

### Dev board notes

**SB Components MicroSD Card Breakout (current test board):**
- 10 kΩ on D0, D1, D2, D3, CMD, CLK.
- CMD and DAT0–3 at 10 kΩ: correct per SD/JEDEC spec.
- **CLK pull-up removed** before use. A pull-up fighting MSDC CLKPD=1 wastes static current.
- **Tested result:** Even with CLK pull-up removed and all DTS fixes applied, CMD (MDI\_RN\_P4)
  remains LOW. 10 kΩ is insufficient to overcome the EPHY P4 RX loading on this pad.
  D0–D3 (P3 RX and P4 TX pairs) correctly read HIGH. Card stuck in "busy" loop — see §SSH diagnosis results.

**Adafruit 4682 microSD breakout:**
- 47 kΩ on card-detect, D0, D1, SCLK (CLK), CS (DAT3), DAT1, DAT2. No pull-up on CMD.
- Missing CMD pull-up is a problem: CMD floats during init on this board.
- CLK pull-up present but 47 kΩ is weak enough that the MSDC driver can still drive it; not ideal but functional.
- 47 kΩ on P3 pads (DAT0/DAT1) pulls those correctly because P3 has no EPHY bias. The P4 RX pair (CMD/CLK) cannot be pulled above VIH with 47 kΩ — this board is not suitable for reliable CMD bring-up on this SoC's EPHY-affected pads.

---

## Register reference

### GPIO mux / pad mode registers (SYSC = 0x10000000, U-Boot KSEG1 = 0xb0000000)

| Register | U-Boot address | Field | Bit(s) | Value for standard SDXC mode |
|----------|---------------|-------|--------|------------------------------|
| AGPIO\_CFG | `0xb000003c` | EPHY\_GPIO\_AIO\_EN[4:1] | [20:17] | `0x7` (P1/P2/P3 digital via `ephy-digital-mask`; P4 analog to avoid CMD/CLK loading) |
| GPIO\_MODE1 | `0xb0000060` | ESD mux | [15] | `0` = iot (routes SDXC to MDI/EPHY pads; HW reset default; set by `esd=iot` pinctrl entry) |
| GPIO\_MODE1 | `0xb0000060` | SDMODE | [11:10] | `01` = sdxc |
| GPIO\_MODE1 | `0xb0000060` | SPIS\_MODE | [2] | `0` = gpio (for GPIO#14/15) |

**Note on ESD mux bit:** AGPIO\_CFG\[1\] was previously believed to be the ESD routing bit. A devmem experiment (clearing bit 1: `0x00FE00FF → 0x00FE00FD`) had zero effect on CMD pad voltage, proving it controls `I2S_SDO_AIO_EN` (confirmed by MT7628 datasheet page 116), not ESD routing. The actual SDXC routing mux is **GPIO\_MODE1\[15\]**, which the `esd=iot` pinctrl entry writes to 0 (= iot). Both U-Boot (`GRP("sd router", ..., ESD_SHIFT=15)`) and the kernel patch 809 (`GRP("esd", ..., MT76X8_GPIO_MODE_ESD=15)`) target this bit.

**GPIO\_MODE1\[15\] is not labeled in the MT7628 programming guide** (pages 117–118 show bits 14:0 named but bit 15 has no entry in the bit-field description table). The bit is undocumented in the MediaTek register spec. Its existence and function as the ESD/router routing mux are confirmed only by driver source (`ESD_SHIFT = 15` in U-Boot `pinctrl-mt7628.c`, `MT76X8_GPIO_MODE_ESD = 15` in kernel patch 809). Its reset value is confirmed as **0** (= iot) from the GPIO1\_MODE register reset value `0x54050404` (bits [15:8] = `0x04` = `0000 0100`; bit 15 = 0).

Read all at once from U-Boot:
```
md.l 0xb000003c 1    # AGPIO_CFG  (SYSC offset 0x3c, NOT 0x14 which is SYSCFG1)
md.l 0xb0000060 1    # GPIO_MODE1
```

### Physical pad control registers (padconf = SYSC + 0x1300 = 0x10001300)

Bit N in each G0 register corresponds to GPIO#N. All SD IoT signals are GPIO#24–29
(all in G0 = pins 0–31).

**Drive strength encoding:** The MT7628 pinctrl driver (`drivers/pinctrl/mtmips/pinctrl-mt7628.c`)
exposes two custom DT properties for drive strength, selecting different pad families and
register pairs:

| DT property | Registers | Valid values | Encoding |
|-------------|-----------|-------------|---------|
| `drive-strength-28` | PAD\_E2\_G0, PAD\_E4\_G0 | 2, 4, 6, 8 mA | index in `{2,4,6,8}` → 2 bits across E2/E4 |
| `drive-strength-4g` | PAD\_E4\_G0, PAD\_E8\_G0 | 4, 8, 12, 16 mA | index in `{4,8,12,16}` → 2 bits across E4/E8 |

`sd_clk` uses `drive-strength-4g = <8>`: value 8 is index 1 in `{4,8,12,16}`,
so `PAD_E4_G0 bit 26 = (1 & 1) = 1` and `PAD_E8_G0 bit 26 = (1 >> 1) & 1 = 0` → 8 mA.

| Register | Physical address | Bit 29 | Bit 28 | Bit 27 | Bit 26 | Bit 25 | Bit 24 |
|----------|-----------------|--------|--------|--------|--------|--------|--------|
| PAD\_PU\_G0 | `0x10001300` | D2 PU | D3 PU | CMD PU | CLK PU | D0 PU | D1 PU |
| PAD\_PD\_G0 | `0x10001310` | D2 PD | D3 PD | CMD PD | CLK PD | D0 PD | D1 PD |
| PAD\_SR\_G0 | `0x10001320` | D2 SR | D3 SR | CMD SR | CLK SR | D0 SR | D1 SR |
| PAD\_SMT\_G0 | `0x10001330` | D2 SMT | D3 SMT | CMD SMT | CLK SMT | D0 SMT | D1 SMT |
| PAD\_E4\_G0 | `0x10001350` | D2 E4 | D3 E4 | CMD E4 | CLK E4 | D0 E4 | D1 E4 |
| PAD\_E8\_G0 | `0x10001360` | D2 E8 | D3 E8 | CMD E8 | CLK E8 | D0 E8 | D1 E8 |

Expected state after `sd_bias` padconf fix applies (at U-Boot MMC probe):
- `PAD_PU_G0` bits [29:25] = 1 (pull-up on CMD, D0–D3), bit 26 = 0 (no pull-up on CLK)
- `PAD_PD_G0` bits [29:24] = 0 (no pull-down on any SD signal)
- `PAD_E4_G0` bit 26 = 1 (8 mA drive on CLK from `sd_sdxc_mode` drive-strength-4g setting)

Read from Linux via devmem (all physical addresses):
```sh
devmem 0x10001300   # PAD_PU_G0
devmem 0x10001310   # PAD_PD_G0
devmem 0x10000620   # GPIO_DATA — actual pad voltage (bits 29:24 = D2,D3,CMD,CLK,D0,D1)
```

### MSDC PAD\_CTRL registers (MSDC base = 0x10130000, Linux only)

These control the output buffer for the **dedicated SDXC pads** (not the MDI physical pads).
In IoT mode these registers do not affect the actual pin voltage and are documented here
for completeness only.

| Register | Address | Value (mips\_mt762x) | Fields |
|----------|---------|---------------------|--------|
| PAD\_CTRL0 / CLK | `0x101300E0` | `0x000d0044` | DRVN=4 DRVP=4 **PD=1** PU=0 SMT=1 IES=1 |
| PAD\_CTRL1 / CMD | `0x101300E4` | `0x000e0044` | DRVN=4 DRVP=4 PD=0 **PU=1** SMT=1 IES=1 |
| PAD\_CTRL2 / DAT | `0x101300E8` | `0x000e0044` | DRVN=4 DRVP=4 PD=0 **PU=1** SMT=1 IES=1 |

Bit layout: [2:0]=DRVN, [6:4]=DRVP, [8]=SR, [16]=PD, [17]=PU, [18]=SMT, [19]=IES, [23:20]=TDSEL, [31:24]=RDSEL.

### MSDC status / diagnostics (Linux devmem)

| Register | Address | Key bits |
|----------|---------|---------|
| MSDC\_CFG | `0x10130000` | bit 7=CKSTB (1=clock stable), bit 3=PIO, bit 4=CKDRVEN, bit 0=MSDC mode |
| MSDC\_PS | `0x10130008` | bit 24=CMD pad value, bits [23:16]=DAT[7:0] pad values |
| GPIO\_DATA | `0x10000620` | GPIO bank 0 actual pad voltages |

---

## References

- [vocore2.md §eMMC / SD Card](vocore2.md#emmc--sd-card) — wiring table and VoCore2 hardware details
- [uboot.md §eMMC DTS](uboot.md#emmc-dts) — DTS property rationale and GPIO number derivation
- [openwrt.md §Pin control](openwrt.md#pin-control---pinctrl) — `ephy-digital`, `sdxc_iot_mode`, `state_default` details
- [flashing.md §5](flashing.md#5--emmc) — eMMC GPT layout and first-install procedure
- `u-boot/drivers/mmc/mtk-sd.c` — patched MSDC driver with `mmc-pwrseq` support
- `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` — U-Boot board DTS
- `openwrt/target/linux/ramips/dts/mt7628an_bodybytes_bodybytes.dtsi` — OpenWrt board DTSI
