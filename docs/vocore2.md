# VoCore2 - Development Proxy for Bodybytes

The VoCore2 module uses the same MT7628AN SoC as bodybytes and can stand in as a lower-risk development board during U-Boot and OpenWrt bring-up. The bodybytes U-Boot binary runs on VoCore2 without modification; most peripherals behave identically, with the differences noted below.

Breakout board: <https://github.com/stargate01/vocore2-breakout>

---

## Hardware Differences

| Parameter | VoCore2 | Bodybytes |
|-----------|---------|-----------|
| RAM | 128 MB DDR2 | 256 MB DDR2 |
| NOR flash | 32 MB W25Q256FV | 64 MB W25Q512JV |
| PORST\_N on JTAG connector | Yes (J6 pin 10) | Not connected |
| eMMC | 32 GB Hardkernel H2 via reader board + Adafruit 4682 breakout | 128 GB Kingston EMMC128-IY29-5B111 |
| Recovery trigger | Push button to GND on MDI\_TP\_P1 | TI DRV5032FCDBZT hall-effect sensor on MDI\_TP\_P1 |
| UART2 TX - bodybytes U-Boot | P2TP (breakout connector) | TP20 (test point) |
| UART2 RX - bodybytes U-Boot | P2TN (breakout connector) | TP19 (test point) |
| UART2 TX - stock VoCore2 firmware | TXD2 / P1RP (breakout connector) | N/A |
| UART2 RX - stock VoCore2 firmware | RXD2 / P1RN (breakout connector) | N/A |

### eMMC on VoCore2

The Hardkernel H2 eMMC module connects via the reader board → Adafruit 4682 microSD breakout → jumper wires to the breakout connector. See §eMMC / SD Card below for the full wiring table and setup notes.

### Recovery trigger on VoCore2

On bodybytes, MDI\_TP\_P1 (SoC pin 40, GPIO#14) connects to a TI DRV5032FCDBZT hall-effect sensor. On VoCore2, replace this with a **push button to GND** on the same pin.

MDI\_TP\_P1 is the **PWM0** pad on the VoCore2 module. It is not broken out on the main connector row - it appears as a pad contact on the **second row** of the VoCore2 module footprint and requires a pin header to be soldered to access it. Once accessible, connect a normally-open button between this pad and GND. The board DTS configures a pull-up via `mdi_p1_gpio`; pressing the button pulls GPIO#14 low and triggers recovery boot.

---

## Breakout Board Setup

### Module modification (required for JTAG)

The stock VoCore2 module has **R9** (4.7 kΩ pull-up to 3V3) on TXD1 (GPIO13), which holds the JTAG mode strap high and disables JTAG. To enable JTAG:

1. Remove R9 from the VoCore2 module (eliminates the internal pull-up).
2. Set JP1 on the breakout to position **2-3** (pulls TXD1 low via R2, enabling JTAG).

Leaving R9 populated and setting JP1 to 2-3 creates a voltage divider (≈1.65 V, undefined logic level) - the module modification is required.

### Pull-up resistors

All five JTAG signals (TMS, TCK, TDI, TDO, TRST) need pull-ups to 3V3. The breakout provides these. RESET (PORST\_N) does not need an external pull-up.

### Fabrication notes

- Bake the VoCore2 module at 120 °C for at least 12 hours before reflow to drive out moisture.
- Reflow the module with hot air only; do not use a soldering iron. DDR2 is ESD-sensitive and iron leakage current can cause permanent damage.
- Reflow temperature must not exceed 260 °C for more than 10 seconds.
- The JTAG header J6 is 1.27 mm pitch - inspect solder joints under magnification.

---

## JTAG Wiring

J6 on the breakout is a 2×5 1.27 mm header wired to the ARM 9-pin Cortex debug connector spec used by the J-Link EDU Mini V2. Plug J-Link directly into J6 - it is a 1:1 connector.

| J6 pin | Signal | MT7628 pad | J-Link pin |
|--------|--------|------------|------------|
| 1 | +3V3 | VTref (sense only - do not power board from here) | 1 |
| 2 | JTAG\_TMS | GPIO41 / EPHY\_LED2\_N\_JTMS | 2 |
| 3 | GND | - | 3 |
| 4 | JTAG\_CLK | GPIO40 / EPHY\_LED3\_N\_JTCLK | 4 |
| 5 | GND | - | 5 |
| 6 | JTAG\_TDO | GPIO43 / EPHY\_LED0\_N\_JTDO | 6 |
| 7 | NC | key position - no pin on J-Link EDU Mini | 7 |
| 8 | JTAG\_TDI | GPIO42 / EPHY\_LED1\_N\_JTDI | 8 |
| 9 | JTAG\_TRST | GPIO39 / EPHY\_LED4\_N\_JTRST\_N | 9 |
| 10 | RESET | MT7628 pin 138 / PORST\_N (system reset, active-low) | 10 |

---

## OpenOCD

### Key difference from bodybytes

VoCore2 has PORST\_N wired to J6 pin 10. Use `trst_and_srst` with `connect_assert_srst` so OpenOCD holds the SoC in reset during TAP init and halts cleanly at the SPI NOR entry point:

```sh
scripts/start_openocd_jlink.py --vocore2
```

This uses `reset_config trst_and_srst separate srst_nogate connect_assert_srst`, issues `reset halt` after `init`, and waits up to 5 s. Ctrl-C terminates OpenOCD directly.

Bodybytes has no PORST\_N on its JTAG connector and uses a different reset\_config - see [jtag.md](jtag.md) (run without `--vocore2`).

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
scripts/boot_uboot_jtag.py
```

This automates PLL init, `dram_init` (size from `[jtag]->dram_size_mb` in `scripts/config.ini`, default 128 MB - correct for VoCore2), DRAM test, and loading [`u-boot/u-boot.bin`](../u-boot/u-boot.bin) to `0x80200000` via JTAG. U-Boot output appears on the serial adapter connected to P2TP/P2TN.

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

Stock VoCore2 firmware routes its UART2 console to **TXD2/RXD2** on the breakout connector (also called P1RP/P1RN in MDI pad naming). These are a completely different pair of SoC pads from P2TP/P2TN. Both use UART2 hardware but appear at different ttyS numbers and on different pins:

| Firmware | ttyS | UART2 TX | UART2 RX |
|----------|------|----------|----------|
| bodybytes firmware (`UART2_MODE=0`, UART0 disabled) | ttyS0 | P2TP | P2TN |
| Stock VoCore2 firmware (UART0 + UART2 both active) | ttyS2 | TXD2 (P1RP) | RXD2 (P1RN) |

Move your USB-serial adapter wires when switching between stock VoCore2 firmware and bodybytes U-Boot on the same hardware.

---

## eMMC / SD Card

### Bus wiring

The SDXC data bus is identically wired between bodybytes and VoCore2 - the same MDI pad → SD signal mapping on both boards:

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

The microSD breakout must expose all four data lines (D0–D3), CMD, and CLK - a **4-bit SDIO-capable** breakout is required. SPI-only breakouts (which expose only D0/MISO, CLK, CMD/MOSI, CS) will not work. The Adafruit 4682 exposes the full SDIO bus and is the tested choice.

The Hardkernel reader board has a small pull-up resistor **R1** on RST\_n. RST\_n is tapped from the R1 pads with a bridge wire and connected to MDI\_TN\_P1 (GPIO#15) on the breakout, giving full pin parity with the bodybytes hardware setup. See [openwrt.md](openwrt.md) for the DTS `emmc_pwrseq` node discussion.

### eMMC manufacturing from PC

On VoCore2, the Hardkernel eMMC module can be removed from the reader board and plugged directly into a PC for partitioning and flashing - no JTAG or U-Boot needed. The reader board appears as a USB mass storage device. Replace `/dev/sdX` with the actual device:

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
SYSUPGRADE=openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
tar xf "$SYSUPGRADE" -O 'sysupgrade-bodybytes,bodybytes/kernel' | dd of=/dev/sdX1 bs=4M conv=fsync
tar xf "$SYSUPGRADE" -O 'sysupgrade-bodybytes,bodybytes/root'   | dd of=/dev/sdX2 bs=4M conv=fsync

# Format overlay and data partitions as ext4
mkfs.ext4 -L rootfs_data /dev/sdX3
mkfs.ext4 -L data        /dev/sdX4
```

Partition 1 holds the raw kernel binary; partition 2 holds the squashfs rootfs (both extracted from `sysupgrade.bin`). Partition 3 (`rootfs_data`) is the ext4 overlay - libfstools mounts it over the squashfs at boot by GPT label. Partition 4 (`data`) is auto-mounted at `/mnt/data` by `block-mount` via `auto_mount 1`. See [flashing.md §5](flashing.md#5--emmc) for the full layout.

---

## NOR Flash

VoCore2 uses a Winbond W25Q256FV: 32 MB total, 256-byte page size, 64 KB erase block size. The 64 KB block size matches `CONFIG_ENV_SECT_SIZE=0x10000` exactly - U-Boot's `saveenv` erases one block, and `fw_setenv` issues an erase ioctl for `secsize=0x10000`; both are correct for this chip. The partition offsets (u-boot at `0x0`, u-boot-env at `0x40000`, factory at `0x50000`, recovery at `0x60000`) are identical to bodybytes; only the total NOR size and the recovery partition end differ. Set `total_size_mb = 32` and `chip_name = W25Q256FV` in `scripts/config.ini` before using any NOR scripts on VoCore2 - `flash_nor_images.py --file` then produces a 32 MB image with the recovery partition capped at `0x1FA0000` (31.625 MB) instead of 63.625 MB. The actual recovery kernel is far smaller than either limit.

The recovery boot path (`altbootcmd=run bootcmd_recovery`) copies the kernel to RAM via `sf read` before booting - see §SPI Addressing Mode below for why direct XIP boot (`bootm 0xBC060000`) is unreliable and is not used.

### SPI Addressing Mode - CHIP_MODE Strapping

The MT7628AN latches `CHIP_MODE[2:0]` from `{SPI_CS1, SPI_CLK, SPI_MOSI}` at reset. These bits select the SPI XIP (auto-read) addressing mode: **3-byte** (16 MB window) or **4-byte** (full flash access). This only affects the memory-mapped NOR window at KSEG1 `0xBC000000` / physical `0x1C000000`. `sf read`, `sf write`, and `sf update` use the SPI driver and are unaffected - the driver switches the chip to 4-byte mode on `sf probe` regardless of strapping.

**VoCore2 strapping** selects 3-byte mode. VoCore2 shipped historically with a 16 MB W25Q128FV; later production runs changed to the W25Q256FV (32 MB) without updating the strapping resistors. The recovery partition starts at offset `0x60000`, leaving ~15.6 MB of usable XIP-readable space before the 16 MB address wrap at `0xFFFFFF`. Recovery images that fit within that range boot correctly via `bootm 0xBC060000`; images larger than ~15.6 MB return corrupt data from XIP.

**Bodybytes strapping**: `SPI_CS1` = high, `SPI_CLK` = high, `SPI_MOSI` = floating. MOSI is wired directly to the W25Q512JV SI pin, which is high-impedance when CS is deasserted, so `CHIP_MODE[0]` at reset is determined only by PCB pull resistors. In practice the effective mode is also 3-byte, giving the same 16 MB XIP window - but the bodybytes chip is a W25Q512JV (64 MB), so any recovery image larger than ~15.6 MB would read garbage via XIP. The floating strapping is a hardware design issue; a future board revision should add an explicit pull resistor to lock `CHIP_MODE[0]` to a known state.

**The fix**: never boot from the XIP window directly. `bootcmd_recovery` copies to RAM first:

```
sf probe && sf read ${kernel_addr_r} 0x60000 ${recovery_size} && bootm ${kernel_addr_r}
```

`sf probe` triggers EN4B (command `0xB7`) on the W25Q512JV, switching it to 4-byte mode. `sf read` then uses the SPI driver - not the XIP window - and can access the full 64 MB correctly.

**OpenWRT MTD note:** The OpenWRT DTS defines the `recovery` partition with size `0x3FA0000` (63.625 MB), which extends to the 64 MB boundary. On VoCore2 the kernel spi-nor driver detects the W25Q256 as 32 MB, so the MTD layer rejects or truncates the `recovery` partition with a warning. The `u-boot`, `u-boot-env`, and `factory` partitions (all within the first 384 KB) register correctly. The truncated `recovery` MTD is harmless in practice: OpenWRT never writes to it (it is `read-only` in the DTS and is only ever written by U-Boot via `sf`), and `fw_setenv`/`fw_printenv` use `u-boot-env` which is unaffected.

### Recovery testing on VoCore2

**Before making any changes, dump the stock NOR** (see §Dumping the stock NOR image below) so you can restore VoCore2 to its original state afterwards.

**1 - Set config for VoCore2** (if not already done):

In `scripts/config.ini` set `total_size_mb = 32` and `chip_name = W25Q256FV` in `[nor]`.

**2 - Build the NOR image:**

```sh
scripts/flash_nor_images.py --file --mac XX:XX:XX:XX:XX:XX
```

Output: `build/bodybytes_nor_image.bin` (32 MB). The u-boot-env and factory blobs are generated on the fly.

**3 - Flash to NOR:**

Via JTAG (U-Boot already RAM-booted, serial port connected):

```sh
scripts/flash_nor_images.py --full-erase   # erase entire chip first
scripts/flash_nor_images.py --all          # then write all partitions
```

Or via CH341A SPI programmer (board powered off):

```sh
flashrom -p ch341a_spi -c W25Q256FV --force -w build/bodybytes_nor_image.bin
```

**4 - Test recovery:**

Trigger recovery by simulating a bootcount overflow (or hold the recovery button during reset):

```
fw_setenv upgrade_available 1
fw_setenv bootcount 4
fw_setenv bootlimit 3
reset
```

U-Boot will run `altbootcmd` → `sf probe && sf read ${kernel_addr_r} 0x60000 ${recovery_size} && bootm ${kernel_addr_r}` and boot the recovery initramfs from NOR.

**5 - Restore stock NOR** when done (see §Restoring the stock NOR image below).

For JTAG RAM-boot development that does not exercise the recovery path, NOR is not involved - `u-boot.bin` is loaded directly to RAM.

### Dumping the stock NOR image

The procedure below dumps the stock VoCore2 NOR to `build/vocore2_nor_backup.bin` (`build/` is not tracked; keep the file safe yourself).

> The CH341A method (see §CH341A USB programmer above) is simpler: plug in the programmer, run `flashrom`, done - no JTAG setup or U-Boot required. The JTAG `sf read` method works equally well since U-Boot uses native 4-byte addressing (command 0xB7, entered on `sf probe`) and has no addressing limitations on the W25Q256FV.

**1 - Start OpenOCD and RAM-boot bodybytes U-Boot** (for `sf` command access and fast SPI reads):

```sh
scripts/start_openocd_jlink.py --vocore2
scripts/boot_uboot_jtag.py
```

**2 - Read full NOR into RAM:**

```
sf probe
sf read 0x81000000 0 0x2000000
```

Wait for `SF: 33554432 bytes @ 0x0 Read: OK`, then halt and dump:

```tcl
halt
dump_image build/vocore2_nor_backup.bin 0xa1000000 0x2000000
```

`0x81000000` (U-Boot KSEG0) = physical `0x01000000` = KSEG1 uncached `0xa1000000`.

At ~4 MHz adapter speed a full 32 MB dump takes several hours. Use `adapter speed 8000` or higher if the EJTAG link stays stable.

### Restoring the stock NOR image

RAM-boot bodybytes U-Boot via JTAG as above, then:

```tcl
# OpenOCD telnet
halt
load_image build/vocore2_nor_backup.bin 0x80000000 bin
resume
```

```
sf probe
sf erase 0 0x2000000
sf write 0x80000000 0 0x2000000
```

Power-cycle to boot the restored stock firmware.

### CH341A USB programmer (alternative to JTAG)

The W25Q256FV is a standard SPI NOR. A CH341A USB flash programmer can read and write it directly via the SPI pins on the breakout connector - no JTAG, no U-Boot required. The CH341A supplies 3.3 V to the board; do not connect any other power source. A jumper from RST to GND holds the MT7628 in reset so its SPI controller cannot contend on the bus.

Connect the CH341A to the VoCore2 breakout connector SPI pins, and fit a jumper from RST to GND to hold the MT7628 in reset so it does not drive the SPI bus while the programmer is attached:

| CH341A | VoCore2 breakout |
|--------|-----------------|
| CLK | SPI CLK |
| CS | SPI CS0 |
| MOSI | SPI MOSI |
| MISO | SPI MISO |
| GND | GND |
| 3.3V | 3.3VO |
| - | RST → GND (jumper) |

Use `flashrom` with the `ch341a_spi` programmer:

```sh
# Read entire 32 MB chip to file
flashrom -p ch341a_spi -c W25Q256FV --progress -r build/vocore2_nor_backup.bin

# Write image to chip (verifies after write)
flashrom -p ch341a_spi -c W25Q256FV --progress -w build/bodybytes_nor_image.bin
```

The write command erases each 64 KB block before programming and verifies the result; a full 32 MB write takes a few minutes.

---

## References

- <https://vocore.io/v2.html> - VoCore2 pinout and hardware documentation
- <https://github.com/stargate01/vocore2-breakout> - breakout board KiCad files and documentation
- <https://www.hardkernel.com/shop/32gb-emmc-module-h2/> - Hardkernel 32 GB eMMC module (H2)
- <https://www.hardkernel.com/shop/emmc-module-reader-board-for-os-upgrade/> - Hardkernel eMMC Module Reader Board (microSD adapter)
- <https://www.adafruit.com/product/4682> - Adafruit 4682 SDIO microSD breakout
- [jtag.md](jtag.md) - bodybytes JTAG procedure (use `dram_init 128` and VoCore2 reset\_config when adapting for VoCore2)
- [uboot.md](uboot.md) - U-Boot DTS details including UART2 pin routing and EPHY pad mode; [openwrt.md](openwrt.md) - OpenWrt DTS details
