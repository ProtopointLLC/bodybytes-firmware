# DTS Comparison: vocore2 / mt7628ram / bodybytes

Three compiled DTBs decompiled for reference analysis.

| File | Source | Status |
|------|--------|--------|
| `docs/dts/vocore2.dts` | Stock VoCore2 OpenWrt Linux DTS | Runs correctly (Linux) |
| `docs/dts/mt7628ram.dts` | `openocd/u-boot-mt7628-ram.bin` (U-Boot 2021.04-rc1, `mt7628_rfb_defconfig`) | Boots on VoCore2 via JTAG |
| `docs/dts/bodybytes.dts` | Compiled bodybytes U-Boot DTB (`bodybytes_defconfig`, v2026.04) | Fixed: `ephy_iot_mode` added to `uart2` pinctrl; outputs on P2TP/P2TN on VoCore2 breakout |

---

## 1 — DTS framework / target OS

`vocore2.dts` is a **Linux DTS**: no U-Boot pre-relocation properties, uses older OpenWrt-era compatible strings, has Linux-specific peripheral nodes (WiFi WMAC, audio, LEDs, PCIe), and sets the console via kernel `bootargs`.

`mt7628ram.dts` and `bodybytes.dts` are **U-Boot DTBs**: they carry DM pre-reloc markers so U-Boot can initialize drivers before relocation, use the current MediaTek U-Boot compatible strings, and set the console via `chosen.stdout-path`.

The two U-Boot DTBs differ in which pre-reloc marker they use — a version difference, not a bug:

| Property | `mt7628ram.dts` (2021.04) | `bodybytes.dts` (2026.04) |
|----------|--------------------------|--------------------------|
| Pre-reloc marker | `u-boot,dm-pre-reloc` | `bootph-all` |

Both mark the `palmbus`, clock controller, reset controller, pinctrl, and the active UART for early DM initialization. The semantics are identical; `bootph-all` is the modern replacement.

---

## 2 — Compatible strings

`compatible` strings identify the board and SoC to both the kernel/bootloader and the DT match machinery.

| Node | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|------|--------------|----------------|----------------|
| Root | `vocore,vocore2`, `mediatek,mt7628an-soc` | `mediatek,mt7628-rfb`, `ralink,mt7628a-soc` | `bodybytes,bodybytes`, `mediatek,mt7628an-soc` |
| INTC | `mti,cpu-interrupt-controller` | `mti,cpu-interrupt-controller` | `mti,cpu-interrupt-controller` |
| SYSC | `ralink,mt7620a-sysc`, `syscon` | `ralink,mt7620a-sysc`, `syscon` | `ralink,mt7620a-sysc`, `syscon` |
| INTC2 | `ralink,mt7628an-intc`, `ralink,rt2880-intc` | `ralink,rt2880-intc` | `ralink,rt2880-intc` |
| ETH | `ralink,rt5350-eth` | `mediatek,mt7628-eth` | `mediatek,mt7628-eth` |
| GPIO | `mediatek,mt7621-gpio` | `mtk,mt7628-gpio`, `mtk,mt7621-gpio` | `mtk,mt7628-gpio`, `mtk,mt7621-gpio` |
| Pinctrl | `ralink,rt2880-pinmux` | `mediatek,mt7628-pinctrl` | `mediatek,mt7628-pinctrl` |
| UART | `ns16550a` | `mediatek,hsuart`, `ns16550a` | `mediatek,hsuart`, `ns16550a` |
| CLK | `ralink,rt2880-clock` | `mediatek,mt7628-clk` | `mediatek,mt7628-clk` |

The `vocore2.dts` uses older OpenWrt drivers (`ralink,rt5350-eth`, `ralink,rt2880-pinmux`, flat `mediatek,mt7621-gpio`). These are Linux drivers that were never upstreamed to U-Boot. The U-Boot DTBs use the MediaTek-upstreamed driver names.

---

## 3 — Clock framework

| Aspect | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|--------|--------------|----------------|----------------|
| Clock provider | `ralink,rt2880-clock` (flat, no reg) | `mediatek,mt7628-clk` at `0x2c/0x10` | same |
| Fixed clock | none | `clk48m` fixed-clock @ 48 MHz | same |
| Fixed clock use | — | MMC source clock | MMC source clock |

`vocore2.dts` uses the legacy OpenWrt clock driver with no register base; the clock state is left to the bootloader. The U-Boot DTBs use the upstream `mediatek,mt7628-clk` driver which manages PLL-derived clocks from the CLKCFG registers at offset `0x2c`.

---

## 4 — Pinctrl framework

`vocore2.dts` uses `ralink,rt2880-pinmux` — the old Linux pinmux driver that lives in the `pinctrl` node at the root level (not inside `palmbus`). It defines simple pin-group/function pairs.

`mt7628ram.dts` and `bodybytes.dts` use `mediatek,mt7628-pinctrl` with two register ranges:
- `0x3c/0x2c`: AGPIO_CFG + GPIO_MODE registers (function mux)
- `0x1300/0x100`: PAD configuration registers (drive strength, slew rate)

The U-Boot pinctrl driver manages three register groups:
- **AGPIO_CFG** (`0xb000003c`): EPHY pad analog/digital mode (`EPHY_GPIO_AIO_EN`, bits [20:17]) and EPHY0 enable
- **GPIO_MODE1** (`0xb0000060`): UART mode bits (UART0_MODE, UART1_MODE, UART2_MODE, SPIS_MODE)
- **PADCONF** (`0xb0001300`): pad drive strength

The board-level default `pinctrl-0` state is applied at pinctrl driver probe (very early, `bootph-all`):

| | `mt7628ram.dts` board default | `bodybytes.dts` board default |
|--|------------------------------|------------------------------|
| `pin_state` content | `pleds`: p0led–p4led as LED | empty |

`mt7628ram.dts` configures the EPHY LED pins (GPIO39–43) as LEDs at startup. This is the function they serve in router mode. `bodybytes.dts` leaves the board default state empty — JTAG is expected on those pins (strapped via TXD1 low) and no further mux configuration is needed at the board level.

---

## 5 — GPIO controller

`vocore2.dts` uses a **flat** single-bank GPIO controller:
```dts
gpio@600 {
    compatible = "mediatek,mt7621-gpio";
    gpio-controller;
    #gpio-cells = <2>;
};
```
GPIO references are `<&gpio N flags>`.

`mt7628ram.dts` and `bodybytes.dts` use a **multi-bank** structure:
```dts
gpio@600 {
    compatible = "mtk,mt7628-gpio", "mtk,mt7621-gpio";
    bank@0 { compatible = "mtk,mt7621-gpio-bank"; gpio-controller; #gpio-cells = <2>; };
    bank@1 { ... };
    bank@2 { ... };
};
```
GPIO references use the specific bank: `<&gpio0 15 GPIO_ACTIVE_LOW>` for GPIO#15 in bank 0.

The multi-bank structure is required in U-Boot for the `mmc-pwrseq-emmc` node in `bodybytes.dts` to correctly reference GPIO#15 (MDI_TN_P1, SoC pin 42) as the eMMC hardware reset output. The flat structure in `vocore2.dts` is the Linux driver's model and is incompatible with the U-Boot `mmc-pwrseq` driver.

---

## 6 — UART nodes and console selection

### 6a — Console path

| | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|--|--------------|----------------|----------------|
| Console mechanism | kernel `bootargs = "console=ttyS2,115200"` | `chosen.stdout-path = uartlite@c00` | `chosen.stdout-path = uart2@e00` |
| Physical UART | UART2 (Linux ttyS2) | UART0 | UART2 |
| Alias | `serial0 = uartlite@c00` | `serial0 = uartlite@c00` | `serial2 = uart2@e00` |
| Clock source | `clock-frequency = <40000000>` (hardcoded) | `clocks = <&clkctrl CLK_UART*>` (DM) | `clocks = <&clkctrl CLK_UART2>` (DM, from dtsi) |

VoCore2's Linux DTS hardcodes the UART clock frequency at 40 MHz — the Linux ns16550 driver reads this directly. U-Boot DTS uses the DM clock controller (`mediatek,mt7628-clk`) instead; the clock value is read at runtime. Both result in a 40 MHz UART clock and 115200 baud at divisor 22. The SPL bypasses both mechanisms and uses `CFG_SYS_NS16550_CLK = 40000000` from `mt7628.h`.

VoCore2's Linux DTS has `serial0 = uart0` as an alias but selects UART2 as the console via the kernel command line. U-Boot uses `stdout-path` to select the console directly at driver probe time.

### 6b — UART2 physical pin routing

All three DTS files enable UART2 with `groups = "uart2"; function = "uart2"`. In the U-Boot pinctrl driver, this sets `UART2_MODE[1:0] = 0` in `GPIO_MODE1[27:26]`, which routes UART2 to the **MDI P2 pads**:

| Signal   | SoC pin | MDI pad   | GPIO_MODE1 UART2_MODE value |
|----------|---------|-----------|----------------------------|
| UART2 TX | 47      | MDI_TP_P2 | 0 (MDI P2 path) |
| UART2 RX | 48      | MDI_TN_P2 | 0 (MDI P2 path) |

Bodybytes uses `UART2_MODE=0` (MDI P2 path). VoCore2 stock firmware routes UART2 to a different mux path (P1RP/P1RN, labelled TXD2/RXD2 on the breakout). Both call it UART2/ttyS2 but emerge on different physical pins — see [vocore2.md](vocore2.md) for the connector pin table.

### 6c — Critical difference: EPHY_GPIO_AIO_EN

The MDI P2 pads have two operating modes controlled by `AGPIO_CFG[20:17]` (`EPHY_GPIO_AIO_EN` bits):

| `EPHY_GPIO_AIO_EN` P2 bit | MDI P2 pad function |
|--------------------------|---------------------|
| 0 (default after reset) | Analog EPHY mode — pad driven by Ethernet PHY analog circuitry |
| 1 | Digital GPIO/UART mode — pad usable as digital signal |

**UART2 on MDI P2 pads only produces a signal when `EPHY_GPIO_AIO_EN` for P2 is set.**

How each DTS handles this:

**`vocore2.dts` (Linux):** Does not set `EPHY_GPIO_AIO_EN` in any DT node. Works because VoCore2's stock U-Boot runs before Linux and calls `mtmips_spl_serial_init()` which sets `EPHY_GPIO_AIO_EN_M`. Linux inherits the register state from the bootloader.

**`mt7628ram.dts` (U-Boot, UART0):** Does not need `EPHY_GPIO_AIO_EN`. UART0 is on GPIO12/GPIO13 (regular GPIO pads), independent of EPHY pad state.

**`bodybytes.dts` (U-Boot, UART2):** The DM pinctrl for `uart2` applies only `uart2_pins` (`UART2_MODE=0`). `EPHY_GPIO_AIO_EN` is **not set** by this pinctrl state. When the binary is loaded directly via JTAG (bypassing the SPL), `EPHY_GPIO_AIO_EN` remains 0 after PORST_N reset, leaving MDI P2 pads in analog mode. **UART2 output is present but absorbed by the analog EPHY circuitry — nothing reaches the pad output.**

This is the root cause of the bodybytes binary producing no output on VoCore2 when loaded via JTAG.

When booting from NOR flash: the SPL runs first and calls:
```c
setbits_32(base + SYSCTL_AGPIO_CFG_REG, EPHY_GPIO_AIO_EN_M);  // sets AGPIO_CFG[20:17] = 0xf
```
Then U-Boot proper inherits the register state and UART2 works. But JTAG skips the SPL.

---

## 7 — EPHY pad groups and the fix

The MT7628 pinctrl driver exposes AGPIO_CFG control through the `ephy4_1_pad` group:

| Function | AGPIO_CFG bits [20:17] | Effect |
|----------|------------------------|--------|
| `"digital"` | 0xf (all set) | MDI P1–P4 pads in digital GPIO/UART/SDXC mode |
| `"analog"` | 0 (all clear) | MDI P1–P4 pads in analog EPHY mode |

The available pinctrl states that reference this group:

| State | Sets `ephy4_1_pad` | Also sets |
|-------|-------------------|-----------|
| `ephy_iot_mode` | `digital` (0xf) | `ephy0` = enable |
| `ephy_router_mode` | `analog` (0) | `ephy0` = enable |
| `sd_iot_mode` | `digital` (0xf) | `sdmode` = sdxc, `sd router` = iot |

In `bodybytes.dts`, `sd_iot_mode` is the pinctrl for the MMC node. It does set `EPHY_GPIO_AIO_EN`. However, MMC is probed **after** UART2 is initialized (UART2 is the `stdout-path` console, so it is probed first, pre-relocation). By the time `sd_iot_mode` runs, UART2 has already tried and failed to output.

**The fix:** Add `ephy_iot_mode` to `uart2`'s `pinctrl-0` in the bodybytes board DTS. DM will then set both `UART2_MODE=0` and `EPHY_GPIO_AIO_EN=0xf` at uart2 probe time, before any UART output is attempted.

Changed in `u-boot/arch/mips/dts/bodybytes,bodybytes.dts`:

```dts
&uart2 {
    status = "okay";
    pinctrl-names = "default";
    pinctrl-0 = <&uart2_pins &ephy_iot_mode>;
};
```

`uart2_pins` is the original DTSI pinctrl (sets `UART2_MODE=0`). `ephy_iot_mode` is the new addition (sets `AGPIO_CFG[20:17] = 0xf`). Both are applied when uart2 is probed. This makes the JTAG-direct path identical to the SPL path in terms of UART2 pad state, and makes bodybytes u-boot.bin boot with UART2 output both on real bodybytes hardware and on VoCore2.

---

## 8 — SPI / NOR flash

| Aspect | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|--------|--------------|----------------|----------------|
| SPI controller reg size | `0x100` | `0x40` | `0x40` |
| `spi-max-frequency` | `0x989680` (10 MHz) | `0x17d7840` (25 MHz) | `0x17d7840` (25 MHz) |
| NOR partition table | yes (u-boot, env, factory, firmware) | no | yes (u-boot, env, factory) |
| Factory partition | read-only, `nvmem-cells` (MAC addr) | — | read-only |
| `num-cs` | not set | `2` | `2` |

The SPI register range difference (0x100 vs 0x40) is a Linux vs U-Boot driver difference — both drivers access the same hardware.

VoCore2 runs NOR at 10 MHz (conservative for the old 1.1.3 bootloader); bodybytes runs at 25 MHz per `CONFIG_SF_DEFAULT_SPEED`. The bodybytes NOR partition table matches the actual flash layout: u-boot at `0x000000`, env at `0x040000`, factory at `0x050000`, recovery at `0x060000`. The VoCore2 DTS omits the recovery/OpenWrt partition (labelled `firmware` starting at `0x050000`) — U-Boot doesn't need it.

---

## 9 — MMC / SDXC

| Aspect | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|--------|--------------|----------------|----------------|
| Driver | `ralink,mt7620-sdhci` | `mediatek,mt7620-mmc` | `mediatek,mt7620-mmc` |
| Status | disabled | okay | okay |
| Pinctrl | `sdxc` (sdmode pins) | `sd_router_mode` | `sd_iot_mode` + `mdi_p1_gpio` |
| Mode | — | SD card (removable) | eMMC (non-removable) |
| Capability | — | `cap-sd-highspeed` | `cap-mmc-highspeed` |
| Card detect | — | `builtin-cd = 1` | `builtin-cd = 1` (from DTSI) |
| Sample delay | — | `r_smpl = 1` | `r_smpl = 1` (from DTSI) |
| PWR seq | — | none | `mmc-pwrseq-emmc` (GPIO#15 reset) |

`sd_router_mode` (mt7628ram) remaps GPIO0, I2S, sdmode, I2C, and uart1 pins as GPIO for the router chip's SD card interface. This changes many pin functions at once and would conflict with bodybytes peripherals (I2S, I2C, UART1 are used).

`sd_iot_mode` (bodybytes) puts EPHY P1–P4 pads in digital mode and enables SDXC on the EPHY P3/P4 pads (SD_CLK, SD_CMD, SD_D0–D3). UART2 uses P2, eMMC reset uses P1. All MDI P1–P4 pads are consumed within the bodybytes board. `bus-width = <4>` is set explicitly in `bodybytes.dts`; the dtsi base does not set it.

`builtin-cd = <1>` and `r_smpl = <1>` are inherited silently from `mt7628a.dtsi`. With `non-removable`, the built-in card-detect is ignored. `r_smpl = <1>` sets rising-edge sampling on the SDXC controller.

**8-bit eMMC mode is not possible on bodybytes.** The dtsi defines `emmc_iot_8bit_mode` which would add D4/D5 by remapping `groups = "uart2"` to `function = "sdxc d5 d4"`. This conflicts with UART2 being the system console. 4-bit mode with `sd_iot_mode` is the only option.

On VoCore2, `sd_iot_mode` puts MDI pads in digital mode (harmless — VoCore2 uses the internal switch, not external EPHY) and enables SDXC, but there is no eMMC device. With `non-removable`, the MMC driver will attempt to probe and time out (~1–2 seconds) before continuing. This produces MMC error messages on VoCore2 but does not hang boot.

`mdi_p1_gpio` sets `SPIS_MODE = GPIO` to make GPIO#15 (MDI_TN_P1 = SoC pin 42) available as the eMMC hardware reset output. On VoCore2, toggling GPIO#15 drives the MDI_TN_P1 pad; harmless.

---

## 10 — Ethernet

| Aspect | `vocore2.dts` | `mt7628ram.dts` | `bodybytes.dts` |
|--------|--------------|----------------|----------------|
| ETH driver | `ralink,rt5350-eth` + `mediatek,mt7628-esw` | `mediatek,mt7628-eth` | `mediatek,mt7628-eth` |
| EPHY pinctrl | none (uses internal switch) | `ephy_router_mode` (analog) | none |
| WAN port | internal switch | `mediatek,wan-port = 0` | — |

`vocore2.dts` uses the full internal Ethernet switch (ESW) with `mediatek,portdisable = 0x3a` to configure port routing. The MDI pads are not used for external Ethernet.

`mt7628ram.dts` uses `ephy_router_mode` which sets EPHY pads to **analog** (Ethernet PHY mode). This is for a board that uses the 5 internal EPHY ports as a router switch with external magnetics. Applying `ephy_router_mode` keeps the MDI pads as analog Ethernet connections.

`bodybytes.dts` has no ETH pinctrl. The EPHY pads go to **digital** mode via `sd_iot_mode` (applied when MMC is probed), because all MDI pads are used for SDXC, UART2, and GPIO on bodybytes. The internal Ethernet switch is not used; VoCore2 uses internal switch and bodybytes uses cellular/WiFi connectivity.

---

## 11 — USB

`vocore2.dts` has EHCI + OHCI (both Linux-compatible). `mt7628ram.dts` and `bodybytes.dts` have only EHCI (U-Boot doesn't use OHCI). All three use the same USB PHY at `0x10120000`. The USB node differences are Linux vs U-Boot driver scope, not a hardware difference.

---

## 12 — VoCore2-specific peripherals (vocore2.dts only)

These nodes are absent from U-Boot DTBs as U-Boot does not need them:

| Node | Purpose |
|------|---------|
| `wmac@10300000` | 802.11n WiFi MAC with EEPROM from NOR factory partition |
| `esw@10110000` | Embedded switch (5-port LAN/WAN) with `mediatek,portmap` |
| `i2c@900` + ES8388 | I2C audio codec |
| `i2s@a00` | I2S audio interface |
| `gdma@2800` | General-purpose DMA (for I2S) |
| `leds` | GPIO LED (fuchsia:status on GPIO44) |
| `sound` | ASoC soundcard node |
| `pcie@10140000` | PCIe (disabled on VoCore2) |
| `pwm@5000` | PWM with pins on PWM0/PWM1 |

---

## 13 — Root cause summary

Before the §7 fix, bodybytes `u-boot.bin` loaded via JTAG (bypassing the SPL) produced no serial output because:

1. After `reset halt`, all SoC registers are in reset state: `AGPIO_CFG = 0` → MDI P2 pads in **analog EPHY mode**.
2. The JTAG load goes directly to `u-boot.bin` at `0x80200000`. The SPL (`u-boot-spl.bin`) does not run.
3. The SPL is the only component that calls `setbits_32(SYSCTL_AGPIO_CFG_REG, EPHY_GPIO_AIO_EN_M)` to switch MDI P2 pads to digital mode. With no SPL, this never happens.
4. DM probes `uart2` early (it is the `stdout-path` console; modern U-Boot propagates pre-reloc requirement via the stdout-path dependency chain — no explicit `bootph-all` on the uart node is needed). DM applies `uart2_pins` pinctrl which sets `UART2_MODE=0` (MDI P2 route) but leaves `AGPIO_CFG` untouched.
5. UART2 sends characters toward the MDI P2 pads, but the pads are in analog mode. No digital signal is produced. The MDI P2 pads on VoCore2 route to the same physical pins used for UART2 — but the digital signal never reaches them.

VoCore2's stock Linux works because the stock VoCore2 U-Boot runs the SPL before Linux and sets `EPHY_GPIO_AIO_EN`. Linux inherits the register state. Our JTAG-direct load does not have this warm-start advantage.

---

## 14 — VoCore2 compatibility

The fix is idempotent: when booting from NOR flash, the SPL sets `AGPIO_CFG[20:17] = 0xf` before U-Boot proper starts; DM re-applies the same bits via `ephy_iot_mode` at uart2 probe. No conflict.

**eMMC on VoCore2:** With `non-removable` and no eMMC connected, the MMC driver times out on probe (≈1–2 s), emits an error, and U-Boot continues normally. The bodybytes MMC pinctrl (`sd_iot_mode`, `mdi_p1_gpio`) and `mmc-pwrseq` are harmless on VoCore2 hardware.
