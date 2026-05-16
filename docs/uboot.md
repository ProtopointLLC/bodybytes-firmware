# U-Boot — MT7628AN

Source tree: `u-boot/` submodule (tag `v2026.04`)

### Board files

All board-specific files live inside the `u-boot/` submodule and are tracked
via the submodule commit pointer.

| File | Purpose |
|------|---------|
| `u-boot/configs/bodybytes_defconfig` | Complete standalone defconfig |
| `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | Full board device tree |
| `u-boot/include/configs/bodybytes.h` | Board config header (`CFG_SYS_NS16550_COM3`) |
| `u-boot/board/bodybytes/bodybytes/Kconfig` | Board vendor/name declarations |
| `u-boot/board/bodybytes/bodybytes/MAINTAINERS` | File ownership record |

---

## 1 — Configure

### Enter the dev shell

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

This sets `CROSS_COMPILE` and `ARCH` automatically.

### Load the board defconfig

```sh
cd u-boot
make bodybytes_defconfig
```

This loads `u-boot/configs/bodybytes_defconfig` — a complete, standalone
defconfig that already incorporates all board-specific settings. The individual
settings and why they are needed are documented below.

To change a Kconfig option, edit `u-boot/configs/bodybytes_defconfig` directly
and re-run `make bodybytes_defconfig`.

### What the defconfig sets

#### UART2 console

The default config uses UART0. One setting needs to change.

**`CONFIG_CONS_INDEX=3`** — selects UART2 as console and triggers the SPL pin
mux setup in `arch/mips/mach-mtmips/mt7628/serial.c`.

The SPL serial driver also requires `CFG_SYS_NS16550_COM3` (UART2's MMIO
address, `0xb0000e00`) to be defined. There is no Kconfig symbol for this; it
is defined in `u-boot/include/configs/bodybytes.h` under the
`XPL_BUILD && SPL_SERIAL` guard alongside the other NS16550 constants.

`CONS_INDEX` is 1-based while the hardware names are 0-based, so UARTLITE**2**
= index **3**:

| `CONS_INDEX` | Hardware  |
|--------------|-----------|
| 1 (default)  | UARTLITE0 |
| 2            | UARTLITE1 |
| 3            | UARTLITE2 |

`SPL_UART2_SPIS_PINMUX` must stay **unset** (default). On this board UART2 is
on the EPHY/MDI pins — the no-`SPL_UART2_SPIS_PINMUX` path in the SPL sets
`EPHY_GPIO_AIO_EN` and clears `UART2_MODE`, which routes to:

| Signal   | SoC pin | Net       | Test point |
|----------|---------|-----------|------------|
| UART2 TX | 47      | MDI_TP_P2 | TP20       |
| UART2 RX | 48      | MDI_TN_P2 | TP19       |

#### eMMC support

The board's 128 GB eMMC is the main OS storage, but the Kconfig options are
entirely absent from the MT7628 RFB defconfig — U-Boot cannot access it without
them. `bodybytes_defconfig` enables `CONFIG_MMC`, `CONFIG_MMC_WRITE`,
`CONFIG_CMD_MMC`, and `CONFIG_MMC_MTK`. The DTS has the MMC controller node
enabled.

#### SPI NOR flash

**`CONFIG_SPI_FLASH_BAR=y`** — critical. The W25Q512JV is 64 MB but carries no
`SPI_NOR_4B_OPCODES` flag, so it uses a Bank Address Register (BAR) to reach
addresses above 16 MB. Without this option U-Boot can only see the first 16 MB
of flash.

**Speed** — the MT7628 RFB defconfig leaves `CONFIG_SF_DEFAULT_SPEED` and
`CONFIG_ENV_SPI_MAX_HZ` at 1 MHz. `CONFIG_ENV_SPI_MAX_HZ` controls env
save/restore independently and is not overridden by the DTS
`spi-max-frequency`; both are set to 25 MHz in `bodybytes_defconfig`.

Note: the MT7621 SPI controller is half-duplex and does not support quad or
dual I/O. `CONFIG_SPI_FLASH_SMART_HWCAPS=y` already ensures the driver will
not attempt modes the controller cannot handle.

#### eMMC DTS: SD vs eMMC profile

The MT7628 RFB DTS configures the MMC node for a removable SD card. Three
things are wrong for bodybytes and are corrected in
`u-boot/arch/mips/dts/bodybytes,bodybytes.dts`:

**Pinctrl** — the RFB DTS uses `sd_router_mode`, which remaps `i2c`, `uart1`,
`sdmode`, and other pin groups as GPIO to free them for routing chips. On
bodybytes those peripherals are in use; their pin assignments must not change.
`sd_iot_mode` (pre-defined in `mt7628a.dtsi`) sets
`EPHY_APGIO_AIO_EN[4:1]=0xf` (MDI P1–P4 pads go digital), `SD_MODE=0` (SDXC
signals on EPHY P3/P4 pads), and `ESD=0` (IoT routing). The SDXC
data/cmd/clk lines emerge on the MDI P3/P4 pads exactly as the schematic wires
them (SoC pins 51–57). `mdi_p1_gpio` is defined in the board DTS and sets
SPIS_MODE=gpio, making MDI_TN_P1 (GPIO#15) driveable as the eMMC reset output.

**Capability flags** — `cap-sd-highspeed` targets removable SD cards. For a
soldered eMMC this wastes time on card-detect polling and applies the wrong
capabilities. Replaced with `cap-mmc-highspeed` + `non-removable`.
`cap-mmc-highspeed` selects High Speed SDR mode (up to 52 MHz, ≤52 MB/s on the
4-bit bus). This mode supports 3.3 V VCCQ — required on this board. HS200 and
HS400 require 1.8 V VCCQ and are not reachable through the MT7628 SDXC
controller regardless.

**Hardware reset** — the eMMC reset pin is wired to MDI_TN_P1 (SoC pin 42,
gpio0 offset 15, active-low). U-Boot pulses it at power-up via a
`mmc-pwrseq-emmc` node to clear fault conditions. The eMMC's RST_n function is
disabled by default (EXT_CSD[162] = 0x00); pulsing it while disabled is a safe
no-op. If the OS later enables RST_n (EXT_CSD[162] = 0x01), the pulse will
actually reset the device on subsequent power-ups — which is the intended
behaviour.

#### GPIO pin map (EPHY/MDI pads used as GPIO)

When the EPHY pads are in digital mode (`ephy4_1_pad = digital` via
`sd_iot_mode`), the MDI P1-P4 pads become software-accessible. The P3/P4 pads
are consumed by the SDXC controller (SD_MODE=0). The P1 pads are set to GPIO
mode by `mdi_p1_gpio` (SPIS_MODE=gpio) and appear in the gpio0 bank (GPIO#0–31):

| Signal | SoC pin | GPIO # | gpio0 offset | Purpose |
|--------|---------|--------|--------------|---------|
| MDI_TP_P1 | 40 | 14 | 14 | Recovery-boot sensor input |
| MDI_TN_P1 | 42 | 15 | 15 | eMMC hardware reset (active-low) |

The eMMC data/cmd/clk signals (MDI P3/P4 pads) are driven by the SDXC
controller and are not accessible as GPIO while `sd_iot_mode` is active:

| SDXC signal | SoC pin | MDI pad | GPIO # if SD_MODE=GPIO |
|-------------|---------|---------|------------------------|
| SD_D1 | 51 | MDI_RP_P3 | 24 |
| SD_D0 | 52 | MDI_RN_P3 | 25 |
| SD_CLK | 54 | MDI_RP_P4 | 26 |
| SD_CMD | 55 | MDI_RN_P4 | 28 |
| SD_D3 | 56 | MDI_TP_P4 | 29 |
| SD_D2 | 57 | MDI_TN_P4 | 27 |

### Saving config changes

Edit `u-boot/configs/bodybytes_defconfig` directly and re-run
`make bodybytes_defconfig`.

---

## 2 — Compile

```sh
make -j$(nproc)
```

### Output files

| File | Description |
|------|-------------|
| `u-boot.bin` | U-Boot proper, linked at `0x80200000`. Used for JTAG RAM boot. |
| `spl/u-boot-spl.bin` | SPL binary. Runs from NOR flash; initialises PLL+DRAM then loads U-Boot proper. |
| `u-boot-with-spl.bin` | Combined NOR flash image: SPL immediately followed by LZMA-compressed U-Boot. Write this to NOR offset 0. Build explicitly with `make u-boot-with-spl.bin`. |

`CONFIG_SKIP_LOWLEVEL_INIT=y` is set, so `u-boot.bin` expects PLL and DRAM to
already be initialised — exactly what the OpenOCD scripts provide for JTAG RAM
boot. The SPL handles that initialisation when booting from NOR flash.

---

## 3 — Install

Full install sequence: JTAG bootstrap → smoke-test U-Boot in RAM → program NOR
flash → write OpenWRT to eMMC.

### 3a — Bootstrap and smoke-test

Follow [jtag.md](jtag.md) §1 and §2 to verify JTAG connectivity and bring up
PLL and DRAM. Then load `u-boot.bin` from the OpenOCD telnet prompt:

```tcl
load_image u-boot.bin 0x80200000 bin
reg pc 0x80200000
resume
```

U-Boot console should appear on UART2 (TP19/TP20) at **115200 8N1** —
`CONFIG_BAUDRATE` defaults to 115200 and is not overridden in the MT7628 config.

If there is no output:
- Confirm `CONFIG_CONS_INDEX=3` is set and the binary was rebuilt after the change
- Confirm your terminal is set to 115200 8N1

Confirm the U-Boot prompt before continuing — if it does not work in RAM it will
not work from NOR flash either.

### 3b — Build the NOR flash image

The combined NOR image is not part of the default `make` target. Build it
explicitly:

```sh
make u-boot-with-spl.bin
```

`u-boot-with-spl.bin` is the SPL concatenated (no padding — `SPL_PAD_TO=0` for
MTMIPS) with `u-boot-lzma.img` (LZMA-compressed U-Boot proper). This is the
only file written to NOR flash.

### 3c — Load the NOR image into RAM

While U-Boot is running from the step above, load `u-boot-with-spl.bin` into
RAM via OpenOCD. In the telnet session:

```tcl
halt
load_image /path/to/u-boot-with-spl.bin 0x80080000 bin
resume
```

`0x80080000` is above the work area and clear of U-Boot proper at `0x80200000`.
Note the byte count printed by `load_image` — U-Boot does not set `${filesize}`
after an OpenOCD load, so you will need it for the `sf write` command.

### 3d — Program NOR flash

In the U-Boot console:

```
sf probe
sf erase 0 0x40000
sf write 0x80080000 0 0x<byte_count_hex>
```

The erase covers 0x40000 (256 KB): the u-boot binary (0–0x2FFFF) and the env
sector (0x30000–0x3FFFF). The env is erased intentionally — U-Boot writes it
fresh on the first `saveenv`. The factory sector (0x40000, WiFi EEPROM) is
deliberately excluded so that re-flashing does not destroy calibration data.

After a successful write, power-cycle the board.

### 3e — Verify NOR boot

The MT7628 boot ROM reads SPI flash from offset 0 on power-up and runs the SPL.
The SPL:

1. Initialises PLL and DRAM autonomously
2. Locates U-Boot proper immediately after itself in NOR flash
3. Decompresses the LZMA payload to `0x80200000` and jumps to it

U-Boot console should appear on UART2 (TP19/TP20) at 115200 8N1 without any
JTAG intervention.

### 3f — Write OpenWRT to eMMC

Obtain or build a raw OpenWRT disk image for this board. Pre-calculate the block
count on the host (512 bytes per block):

```sh
blkcount=$(( ($(stat -c%s openwrt.img) + 511) / 512 ))
printf "block count: 0x%x\n" $blkcount
```

Load the image into RAM via OpenOCD, then write to eMMC from the U-Boot console.

**Load via OpenOCD** (from the telnet session while U-Boot is running):

```tcl
halt
load_image /path/to/openwrt.img 0x82000000 bin
resume
```

`0x82000000` keeps the image above U-Boot's footprint regardless of image size.
Note the byte count from `load_image`.

**Write to eMMC** (in the U-Boot console):

```
mmc dev 0
mmc write 0x82000000 0 <block_count_hex>
```

Alternatively, once WiFi is configured, TFTP is more practical for large images:

```
setenv ipaddr 192.168.1.1
setenv serverip 192.168.1.100
tftpboot 0x82000000 openwrt.img
mmc dev 0
mmc write 0x82000000 0 <block_count_hex>
```

### 3g — Boot OpenWRT from eMMC

See [openwrt.md §6](openwrt.md#6--boot-configuration) for the `bootcmd`
and `bootargs` configuration. In brief:

```
setenv bootcmd 'mmc dev 0; mmc read 0x82000000 0 0x10000; bootm 0x82000000'
saveenv
boot
```

To enter the recovery bootloader instead of the normal boot path (sensor
trigger, MDI_TP_P1 / SoC pin 40 / gpio0 offset 14), set `CONFIG_PREBOOT` to
read that GPIO and override `bootcmd` before the normal boot proceeds.
