# VoCore2 — Development Proxy for Bodybytes

The VoCore2 module uses the same MT7628AN SoC as bodybytes and can stand in as a lower-risk development board during U-Boot and OpenWrt bring-up. The bodybytes U-Boot binary runs on VoCore2 without modification; most peripherals behave identically, with the differences noted below.

Breakout board: <https://github.com/stargate01/vocore2-breakout>

---

## Hardware Differences

| Parameter | VoCore2 | Bodybytes |
|-----------|---------|-----------|
| RAM | 128 MB DDR2 | 256 MB DDR2 |
| NOR flash | 32 MB W25Q256 | 64 MB W25Q512JV |
| PORST\_N on JTAG connector | Yes (J6 pin 10) | Not connected |
| eMMC | 32 GB Hardkernel H2 via reader board + Adafruit 4682 breakout | 128 GB Kingston EMMC128-IY29-5B111 |
| Recovery trigger | Push button to GND on MDI\_TP\_P1 | TI DRV5032FCDBZT hall-effect sensor on MDI\_TP\_P1 |
| UART2 TX — bodybytes U-Boot | P2TP (breakout connector) | TP20 (test point) |
| UART2 RX — bodybytes U-Boot | P2TN (breakout connector) | TP19 (test point) |
| UART2 TX — stock VoCore2 firmware | TXD2 / P1RP (breakout connector) | N/A |
| UART2 RX — stock VoCore2 firmware | RXD2 / P1RN (breakout connector) | N/A |

### eMMC on VoCore2

The Hardkernel H2 eMMC module connects via the reader board → Adafruit 4682 microSD breakout → jumper wires to the breakout connector. See §eMMC / SD Card below for the full wiring table and setup notes.

### Recovery trigger on VoCore2

On bodybytes, MDI\_TP\_P1 (SoC pin 40, GPIO#14) connects to a TI DRV5032FCDBZT hall-effect sensor. On VoCore2, replace this with a **push button to GND** on the same pin.

MDI\_TP\_P1 is the **PWM0** pad on the VoCore2 module. It is not broken out on the main connector row — it appears as a pad contact on the **second row** of the VoCore2 module footprint and requires a pin header to be soldered to access it. Once accessible, connect a normally-open button between this pad and GND. The board DTS configures a pull-up via `mdi_p1_gpio`; pressing the button pulls GPIO#14 low and triggers recovery boot.

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

This pipes [`scripts/openocd_run_uboot_vocore2.scr`](../scripts/openocd_run_uboot_vocore2.scr) (PLL init, `dram_init 128`, load [`u-boot/u-boot.bin`](../u-boot/u-boot.bin) to `0x80200000`, resume) to the OpenOCD telnet port. OpenOCD processes each command and keeps running after the connection closes. U-Boot output appears on the serial adapter connected to P2TP/P2TN.

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

## eMMC / SD Card

### Bus wiring

The SDXC data bus is identically wired between bodybytes and VoCore2 — the same MDI pad → SD signal mapping on both boards:

| SD signal | MDI pad | Net |
|-----------|---------|-----|
| SD\_D1 | MDI\_RP\_P3 | SD\_D1 |
| SD\_D0 | MDI\_RN\_P3 | SD\_D0 |
| SD\_CLK | MDI\_RP\_P4 | SD\_CLK |
| SD\_CMD | MDI\_RN\_P4 | SD\_CMD |
| SD\_D3 | MDI\_TP\_P4 | SD\_D3 |
| SD\_D2 | MDI\_TN\_P4 | SD\_D2 |
| RST\_n | MDI\_TN\_P1 | EMMC\_RST (bodybytes only) |

Both use the legacy 4-bit data interface (SD\_D0–D3). 8-bit eMMC mode is not used.

### Storage devices

| | VoCore2 (development) | Bodybytes (production) |
|-|-----------------------|------------------------|
| Device | Hardkernel 32 GB eMMC module (H2) | Kingston EMMC128-IY29-5B111 (128 GB) |
| Connection | eMMC module → Hardkernel eMMC Module Reader Board → Adafruit 4682 microSD breakout → jumper wires to breakout connector | Soldered directly on board |
| RST\_n | Reader board R1 tap → MDI\_TN\_P1 (GPIO#15) | Wired to MDI\_TN\_P1 (GPIO#15) |

The microSD breakout must expose all four data lines (D0–D3), CMD, and CLK — a **4-bit SDIO-capable** breakout is required. SPI-only breakouts (which expose only D0/MISO, CLK, CMD/MOSI, CS) will not work. The Adafruit 4682 exposes the full SDIO bus and is the tested choice.

The Hardkernel reader board has a small pull-up resistor **R1** on RST\_n. RST\_n is tapped from the R1 pads with a bridge wire and connected to MDI\_TN\_P1 (GPIO#15) on the breakout, giving full pin parity with the bodybytes hardware setup. See [openwrt.md](openwrt.md) for the DTS `emmc_pwrseq` node discussion.

### eMMC manufacturing from PC

On VoCore2, the Hardkernel eMMC module can be removed from the reader board and plugged directly into a PC for partitioning and flashing — no JTAG or U-Boot needed. The reader board appears as a USB mass storage device. Replace `/dev/sdX` with the actual device:

```sh
# Create GPT with 4 partitions
sgdisk --zap-all /dev/sdX
sgdisk \
  -n 1:2048:+32M    -t 1:8300  -c 1:"kernel"      \
  -n 2:0:+512M      -t 2:8300  -c 2:"rootfs"       \
  -n 3:0:+4096M     -t 3:8300  -c 3:"rootfs_data"  \
  -n 4:0:0          -t 4:8300  -c 4:"data"          \
  /dev/sdX

# Extract kernel and squashfs rootfs from sysupgrade.bin and write to eMMC
SYSUPGRADE=openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
tar xf "$SYSUPGRADE" -O 'sysupgrade-bodybytes,bodybytes/kernel' | dd of=/dev/sdX1 bs=4M conv=fsync
tar xf "$SYSUPGRADE" -O 'sysupgrade-bodybytes,bodybytes/root'   | dd of=/dev/sdX2 bs=4M conv=fsync

# Format overlay and data partitions as ext4
mkfs.ext4 -L rootfs_data /dev/sdX3
mkfs.ext4 -L data        /dev/sdX4
```

Partition 1 holds the raw kernel binary; partition 2 holds the squashfs rootfs (both extracted from `sysupgrade.bin`). Partition 3 (`rootfs_data`) is the ext4 overlay — libfstools mounts it over the squashfs at boot by GPT label. Partition 4 (`data`) is auto-mounted at `/mnt/data` by `block-mount` via `auto_mount 1`. See [flashing.md §5](flashing.md#5--emmc) for the full layout.

---

## NOR Flash

VoCore2 uses a 32 MB W25Q256. The partition offsets (u-boot at `0x0`, u-boot-env at `0x40000`, factory at `0x50000`, recovery at `0x60000`) are identical to bodybytes; only the total NOR size and the recovery partition end differ. `generate_nor_image.py --nor-size 32` produces a 32 MB image with the recovery partition capped at `0x1FA0000` (31.625 MB) instead of 63.625 MB. The actual recovery kernel is far smaller than either limit.

The recovery boot path (`altbootcmd=run bootcmd_recovery`, `bootcmd_recovery=bootm 0xBC060000`) reads the kernel directly from the NOR memory-mapped window — it does not use `sf read` and does not care about the DTS partition size.

**OpenWRT MTD note:** The OpenWRT DTS defines the `recovery` partition with size `0x3FA0000` (63.625 MB), which extends to the 64 MB boundary. On VoCore2 the kernel spi-nor driver detects the W25Q256 as 32 MB, so the MTD layer rejects or truncates the `recovery` partition with a warning. The `u-boot`, `u-boot-env`, and `factory` partitions (all within the first 384 KB) register correctly. The truncated `recovery` MTD is harmless in practice: OpenWRT never writes to it (it is `read-only` in the DTS and is only ever written by U-Boot via `sf`), and `fw_setenv`/`fw_printenv` use `u-boot-env` which is unaffected.

### Recovery testing on VoCore2

**Before making any changes, dump the stock NOR** (see §Dumping the stock NOR image below) so you can restore VoCore2 to its original state afterwards.

**1 — Build the NOR image:**

```sh
python3 scripts/generate_nor_image.py --nor-size 32 XX:XX:XX:XX:XX:XX
```

Output: [`assets/vocore2_nor_image.bin`](../assets/vocore2_nor_image.bin) (32 MB).

**2 — Load the image into RAM via JTAG/OpenOCD:**

```tcl
# OpenOCD telnet (bodybytes U-Boot already RAM-booted via openocd_run_uboot_vocore2.scr)
halt
load_image assets/vocore2_nor_image.bin 0x80000000 bin
resume
```

**3 — Write to NOR from the U-Boot prompt:**

```
sf probe
sf erase 0 0x2000000
sf write 0x80000000 0 0x2000000
```

**4 — Test recovery:**

Trigger recovery by simulating a bootcount overflow (or hold the recovery button during reset):

```
fw_setenv upgrade_available 1
fw_setenv bootcount 4
fw_setenv bootlimit 3
reset
```

U-Boot will run `altbootcmd` → `bootm 0xBC060000` and boot the recovery initramfs from NOR.

**5 — Restore stock NOR** when done (see §Restoring the stock NOR image below).

For JTAG RAM-boot development that does not exercise the recovery path, NOR is not involved — `u-boot.bin` is loaded directly to RAM.

### Dumping the stock NOR image

A reference dump of the stock VoCore2 NOR is already committed at [`assets/vocore2_nor_backup.bin`](../assets/vocore2_nor_backup.bin). The procedure below is for reference or for re-dumping from different hardware. The NOR is memory-mapped at `0xBC000000` (KSEG1 uncached), so it is directly readable via JTAG without any flash driver.

**1 — Start OpenOCD and RAM-boot bodybytes U-Boot** (for `sf` command access and fast SPI reads):

```sh
openocd -f interface/jlink.cfg \
    -c "transport select jtag" \
    -c "adapter speed 100" \
    -c "reset_config trst_and_srst separate srst_nogate connect_assert_srst" \
    -f mt7628.cfg \
    -c "init" \
    -c "reset halt" \
    -c "wait_halt 10000"

nc -N localhost 4444 < scripts/openocd_run_uboot_vocore2.scr
```

**2 — Read NOR into RAM via U-Boot** (fast — uses SPI burst reads):

```
sf probe
sf read 0x81000000 0 0x2000000
```

Wait for `SF: 33554432 bytes @ 0x0 Read: OK`.

**3 — Halt and dump via OpenOCD**:

```tcl
halt
dump_image assets/vocore2_nor_backup.bin 0xa1000000 0x2000000
```

`0x81000000` (U-Boot KSEG0) = physical `0x01000000` = KSEG1 uncached `0xa1000000`.

At ~4 MHz adapter speed this takes several hours. Use `adapter speed 8000` or higher before the dump to speed it up if the EJTAG link stays stable.

### Restoring the stock NOR image

RAM-boot bodybytes U-Boot via JTAG as above, then load the backup into RAM:

```tcl
# OpenOCD telnet
halt
load_image assets/vocore2_nor_backup.bin 0x80000000 bin
resume
```

At the U-Boot prompt:

```
sf probe
sf erase 0 0x2000000
sf write 0x80000000 0 0x2000000
```

Power-cycle to boot the restored stock firmware.

---

## References

- <https://vocore.io/v2.html> — VoCore2 pinout and hardware documentation
- <https://github.com/stargate01/vocore2-breakout> — breakout board KiCad files and documentation
- <https://www.hardkernel.com/shop/32gb-emmc-module-h2/> — Hardkernel 32 GB eMMC module (H2)
- <https://www.hardkernel.com/shop/emmc-module-reader-board-for-os-upgrade/> — Hardkernel eMMC Module Reader Board (microSD adapter)
- <https://www.adafruit.com/product/4682> — Adafruit 4682 SDIO microSD breakout
- [jtag.md](jtag.md) — bodybytes JTAG procedure (use `dram_init 128` and VoCore2 reset\_config when adapting for VoCore2)
- [uboot.md](uboot.md) — U-Boot DTS details including UART2 pin routing and EPHY pad mode; [openwrt.md](openwrt.md) — OpenWrt DTS details
