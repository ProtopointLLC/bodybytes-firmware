# VoCore2 — Development Proxy for Bodybytes

The VoCore2 module uses the same MT7628AN SoC as bodybytes and can stand in as a lower-risk development board during U-Boot and OpenWrt bring-up. The bodybytes U-Boot binary runs on VoCore2 without modification; most peripherals behave identically, with the differences noted below.

Breakout board: <https://github.com/stargate01/vocore2-breakout>

---

## Hardware Differences

| Parameter | VoCore2 | Bodybytes |
|-----------|---------|-----------|
| RAM | 128 MB DDR2 | 256 MB DDR2 |
| NOR flash | 16 MB | 64 MB W25Q512JV |
| PORST\_N on JTAG connector | Yes (J6 pin 10) | Not connected |
| eMMC | None | 128 GB Kingston EMMC128-IY29-5B111 |
| UART2 TX — bodybytes U-Boot | P2TP (breakout connector) | TP20 (test point) |
| UART2 RX — bodybytes U-Boot | P2TN (breakout connector) | TP19 (test point) |
| UART2 TX — stock VoCore2 firmware | TXD2 / P1RP (breakout connector) | N/A |
| UART2 RX — stock VoCore2 firmware | RXD2 / P1RN (breakout connector) | N/A |

### eMMC on VoCore2

bodybytes U-Boot has the eMMC node enabled with `non-removable`. Without an eMMC connected, the MMC driver probes, times out (≈1–2 s), emits an error, and continues. This is harmless for development.

---

## Breakout Board Setup

### Module modification (required for JTAG)

The stock VoCore2 module has **R9** (4.7 kΩ pull-up to 3V3) on TXD1 (GPIO13), which holds the JTAG mode strap high and disables JTAG. To enable JTAG:

1. Remove R9 from the VoCore2 module (eliminates the internal pull-up).
2. Set JP1 on the breakout to position **2-3** (pulls TXD1 low via R2, enabling JTAG).

Leaving R9 populated and setting JP1 to 2-3 creates a voltage divider (≈1.65 V, undefined logic level) — the module modification is required.

### Pull-up resistors

All five JTAG signals (TMS, TCK, TDI, TDO, TRST) need pull-ups to 3V3. The breakout provides these. RESET (PORST\_N) does not need an external pull-up.

### Fabrication notes

- Bake the VoCore2 module at 120 °C for at least 12 hours before reflow to drive out moisture.
- Reflow the module with hot air only; do not use a soldering iron. DDR2 is ESD-sensitive and iron leakage current can cause permanent damage.
- Reflow temperature must not exceed 260 °C for more than 10 seconds.
- The JTAG header J6 is 1.27 mm pitch — inspect solder joints under magnification.

---

## JTAG Wiring

J6 on the breakout is a 2×5 1.27 mm header wired to the ARM 9-pin Cortex debug connector spec used by the J-Link EDU Mini V2. Plug J-Link directly into J6 — it is a 1:1 connector.

| J6 pin | Signal | MT7628 pad | J-Link pin |
|--------|--------|------------|------------|
| 1 | +3V3 | VTref (sense only — do not power board from here) | 1 |
| 2 | JTAG\_TMS | GPIO41 / EPHY\_LED2\_N\_JTMS | 2 |
| 3 | GND | — | 3 |
| 4 | JTAG\_CLK | GPIO40 / EPHY\_LED3\_N\_JTCLK | 4 |
| 5 | GND | — | 5 |
| 6 | JTAG\_TDO | GPIO43 / EPHY\_LED0\_N\_JTDO | 6 |
| 7 | NC | key position — no pin on J-Link EDU Mini | 7 |
| 8 | JTAG\_TDI | GPIO42 / EPHY\_LED1\_N\_JTDI | 8 |
| 9 | JTAG\_TRST | GPIO39 / EPHY\_LED4\_N\_JTRST\_N | 9 |
| 10 | RESET | MT7628 pin 138 / PORST\_N (system reset, active-low) | 10 |

---

## OpenOCD

### Key difference from bodybytes

VoCore2 has PORST\_N wired to J6 pin 10. Use `trst_and_srst` with `connect_assert_srst` so OpenOCD holds the SoC in reset during TAP init and halts cleanly at the SPI NOR entry point:

```sh
openocd -f interface/jlink.cfg \
    -c "transport select jtag" \
    -c "adapter speed 100" \
    -c "reset_config trst_and_srst separate srst_nogate connect_assert_srst" \
    -f mt7628.cfg \
    -c "init" \
    -c "reset halt" \
    -c "wait_halt 10000"
```

Bodybytes has no PORST\_N on its JTAG connector and uses a different reset\_config — see [jtag.md](jtag.md).

### Bootstrap DRAM

VoCore2 has 128 MB DDR2. Use `dram_init 128` (not 256):

```tcl
cpu_pll_init
adapter speed 1000
dram_init 128
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
```

All other steps (PLL init, work area, verify) are identical to [jtag.md §2](jtag.md#step-2--bootstrap-pll-and-dram).

### Quick boot shortcut

Once OpenOCD is running and listening on port 4444, run the full init + U-Boot load sequence in one shot:

```sh
nc -N localhost 4444 < scripts/openocd_run_uboot_vocore2.scr
```

This pipes `scripts/openocd_run_uboot_vocore2.scr` (PLL init, `dram_init 128`, load `u-boot.bin` to `0x80200000`, resume) to the OpenOCD telnet port. OpenOCD processes each command and keeps running after the connection closes. U-Boot output appears on the serial adapter connected to P2TP/P2TN.

---

## UART2 Console

### Correct pins

When running bodybytes U-Boot (`CONFIG_CONS_INDEX=3`, `UART2_MODE=0`, `ephy_iot_mode`), UART2 output is on MDI\_TP\_P2 and MDI\_TN\_P2. On the VoCore2 breakout connector these pads are labeled **P2TP** and **P2TN**.

| Function | Breakout label | Connect to adapter |
|----------|---------------|-------------------|
| UART2 TX | P2TP | adapter RX |
| UART2 RX | P2TN | adapter TX |

115200 8N1.

### Stock VoCore2 UART2 is on different pins

Stock VoCore2 firmware routes its UART2 console to **TXD2/RXD2** on the breakout connector (also called P1RP/P1RN in MDI pad naming). These are a completely different pair of SoC pads from P2TP/P2TN. Both firmwares call it "UART2" / `ttyS2` but use different pin mux paths:

| Firmware | UART2 TX | UART2 RX |
|----------|----------|----------|
| bodybytes U-Boot (`UART2_MODE=0`) | P2TP | P2TN |
| Stock VoCore2 firmware | TXD2 (P1RP) | RXD2 (P1RN) |

Move your USB-serial adapter wires when switching between stock VoCore2 firmware and bodybytes U-Boot on the same hardware.

---

## NOR Flash

VoCore2 uses a 16 MB NOR with a different partition layout than bodybytes. When testing bodybytes U-Boot on VoCore2, the SPI NOR commands will work but the partition offsets differ from the VoCore2 stock layout. The bodybytes `generate_nor_image.py` output cannot be written verbatim to a stock VoCore2 NOR without replacing the entire flash contents.

For JTAG RAM-boot development, this is not relevant — `u-boot.bin` is loaded directly to RAM and never touches NOR.

---

## References

- <https://github.com/stargate01/vocore2-breakout> — breakout board KiCad files and documentation
- [jtag.md](jtag.md) — bodybytes JTAG procedure (use `dram_init 128` and VoCore2 reset\_config when adapting for VoCore2)
- [dts.md](dts.md) — DTS comparison: vocore2 / mt7628\_rfb / bodybytes; explains UART2 pin routing and EPHY pad mode fix
