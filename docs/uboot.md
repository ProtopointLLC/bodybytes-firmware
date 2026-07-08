# U-Boot — MT7628AN

Source tree: `u-boot/` submodule (tag `v2026.04`)

## Board files

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

`bodybytes_defconfig` is a complete standalone defconfig incorporating all board-specific settings. To change a Kconfig option, edit it directly and re-run `make bodybytes_defconfig`.

### What the defconfig sets

#### UART2 console

The default MT7628 config uses UART0. One Kconfig change is needed.

**`CONFIG_CONS_INDEX=3`** — selects UART2 as console and triggers the SPL pin mux setup in `arch/mips/mach-mtmips/mt7628/serial.c`.

The SPL serial driver also requires `CFG_SYS_NS16550_COM3` (UART2's MMIO address, `0xb0000e00`). There is no Kconfig symbol for this; it is defined in `u-boot/include/configs/bodybytes.h` under the `XPL_BUILD && SPL_SERIAL` guard alongside the other NS16550 constants.

`CONS_INDEX` is 1-based while the hardware names are 0-based, so UARTLITE**2** = index **3**:

| `CONS_INDEX` | Hardware  |
|--------------|-----------|
| 1 (default)  | UARTLITE0 |
| 2            | UARTLITE1 |
| 3            | UARTLITE2 |

`SPL_UART2_SPIS_PINMUX` must stay **unset** (default). On this board UART2 is on the EPHY/MDI pins — the no-`SPL_UART2_SPIS_PINMUX` path in the SPL sets `EPHY_GPIO_AIO_EN` and clears `UART2_MODE`, which routes to:

| Signal   | SoC pin | Net       | Test point |
|----------|---------|-----------|------------|
| UART2 TX | 47      | MDI_TP_P2 | TP20       |
| UART2 RX | 48      | MDI_TN_P2 | TP19       |

#### eMMC support

The MT7628 RFB defconfig has no eMMC options — U-Boot cannot access the 128 GB eMMC without them. `bodybytes_defconfig` enables `CONFIG_MMC`, `CONFIG_MMC_WRITE`, `CONFIG_CMD_MMC`, and `CONFIG_MMC_MTK`. The DTS has the MMC controller node enabled.

#### SPI NOR flash

**`CONFIG_SPI_FLASH_BAR=y`** — critical. The W25Q512JV is 64 MB but carries no `SPI_NOR_4B_OPCODES` flag, so it uses a Bank Address Register (BAR) to reach addresses above 16 MB. Without this option U-Boot can only see the first 16 MB of flash.

**Speed** — the MT7628 RFB defconfig leaves `CONFIG_SF_DEFAULT_SPEED` and `CONFIG_ENV_SPI_MAX_HZ` at 1 MHz. `CONFIG_ENV_SPI_MAX_HZ` controls env save/restore independently and is not overridden by the DTS `spi-max-frequency`; both are set to 25 MHz in `bodybytes_defconfig`.

Note: the MT7621 SPI controller is half-duplex and does not support quad or dual I/O. `CONFIG_SPI_FLASH_SMART_HWCAPS=y` already ensures the driver will not attempt modes the controller cannot handle.

#### eMMC DTS: SD vs eMMC profile

The MT7628 RFB DTS configures the MMC node for a removable SD card. Three things are corrected in `u-boot/arch/mips/dts/bodybytes,bodybytes.dts`:

**Pinctrl** — the RFB DTS uses `sd_router_mode`, which remaps `i2c`, `uart1`, `sdmode`, and other pin groups as GPIO to free them for routing chips. On bodybytes those peripherals are in use; their pin assignments must not change. `sd_iot_mode` (pre-defined in `mt7628a.dtsi`) sets `EPHY_APGIO_AIO_EN[4:1]=0xf` (MDI P1–P4 pads go digital), `SD_MODE=0` (SDXC signals on EPHY P3/P4 pads), and `ESD=0` (IoT routing). The SDXC data/cmd/clk lines emerge on the MDI P3/P4 pads exactly as the schematic wires them (SoC pins 51–57). `mdi_p1_gpio` is defined in the board DTS and sets SPIS_MODE=gpio, making MDI_TN_P1 (GPIO#15) driveable as the eMMC reset output.

**Capability flags** — `cap-sd-highspeed` targets removable SD cards. For a soldered eMMC, replaced with `cap-mmc-highspeed` + `non-removable`. `cap-mmc-highspeed` selects High Speed SDR mode (up to 52 MHz, ≤52 MB/s on the 4-bit bus) and supports 3.3 V VCCQ — required on this board. HS200 and HS400 require 1.8 V VCCQ and are not reachable through the MT7628 SDXC controller regardless.

**Hardware reset** — the eMMC reset pin is wired to MDI_TN_P1 (SoC pin 42, gpio0 offset 15, active-low). U-Boot pulses it at power-up via a `mmc-pwrseq-emmc` node to clear fault conditions. The eMMC's RST_n function is disabled by default (EXT_CSD[162] = 0x00); pulsing it while disabled is a safe no-op. If the OS later enables RST_n (EXT_CSD[162] = 0x01), the pulse will actually reset the device on subsequent power-ups — which is the intended behaviour.

#### GPIO pin map (EPHY/MDI pads used as GPIO)

When the EPHY pads are in digital mode (`ephy4_1_pad = digital` via `sd_iot_mode`), the MDI P1–P4 pads become software-accessible. The P3/P4 pads are consumed by the SDXC controller (SD_MODE=0). The P1 pads are set to GPIO mode by `mdi_p1_gpio` (SPIS_MODE=gpio) and appear in the gpio0 bank (GPIO#0–31):

| Signal    | SoC pin | GPIO # | gpio0 offset | Purpose |
|-----------|---------|--------|--------------|---------|
| MDI_TP_P1 | 40      | 14     | 14           | Recovery-boot sensor input |
| MDI_TN_P1 | 42      | 15     | 15           | eMMC hardware reset (active-low) |

The eMMC data/cmd/clk signals (MDI P3/P4 pads) are driven by the SDXC controller and are not accessible as GPIO while `sd_iot_mode` is active:

| SDXC signal | SoC pin | MDI pad    | GPIO # if SD_MODE=GPIO |
|-------------|---------|------------|------------------------|
| SD_D1       | 51      | MDI_RP_P3  | 24 |
| SD_D0       | 52      | MDI_RN_P3  | 25 |
| SD_CLK      | 54      | MDI_RP_P4  | 26 |
| SD_CMD      | 55      | MDI_RN_P4  | 28 |
| SD_D3       | 56      | MDI_TP_P4  | 29 |
| SD_D2       | 57      | MDI_TN_P4  | 27 |

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
| `u-boot-with-spl.bin` | Combined NOR flash image: SPL immediately followed by LZMA-compressed U-Boot. Write this to NOR offset 0. |

`CONFIG_SKIP_LOWLEVEL_INIT=y` is set, so `u-boot.bin` expects PLL and DRAM to already be initialised — exactly what the OpenOCD scripts provide for JTAG RAM boot. The SPL handles that initialisation when booting from NOR flash.

---

## 3 — Install

See [flashing.md](flashing.md) for the complete install sequence: NOR flash layout, factory EEPROM generation, full NOR programming, U-Boot-only updates, eMMC write, boot configuration, and hardware write protection.
