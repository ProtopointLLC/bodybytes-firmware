# U-Boot — MT7628AN

Source tree: `u-boot/` submodule (tag `v2026.04`)

## Board files

| File | Purpose |
|------|---------|
| `u-boot/configs/bodybytes_defconfig` | Complete standalone defconfig |
| `u-boot/arch/mips/dts/bodybytes,bodybytes.dts` | Full board device tree |
| `u-boot/include/configs/bodybytes.h` | Board config header: `CFG_SYS_NS16550_COM3` (UART2 MMIO for SPL legacy path) |
| `u-boot/board/bodybytes/bodybytes/bodybytes.env` | Default environment: `bootcmd`, `bootcmd_normal`, `bootcmd_recovery`, `altbootcmd`, `bootmenu_*`; auto-detected by the build system and compiled into `default_environment[]`; also used directly by `scripts/generate_nor_image.py` as `mkenvimage` input |
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

The SPL serial driver also requires `CFG_SYS_NS16550_COM3` (UART2's MMIO address, `0xb0000e00`), defined in `u-boot/include/configs/bodybytes.h`. This is why `bodybytes.h` exists at all.

The boot variables (`bootcmd`, `bootcmd_normal`, `bootcmd_recovery`, `altbootcmd`, `bootmenu_*`) live in `board/bodybytes/bodybytes/bodybytes.env`. The U-Boot build system auto-detects that file (because it matches `board/<vendor>/<board>/<SYS_BOARD>.env`) and compiles it into `default_environment[]` — the same compiled-in fallback that makes recovery independent of the env partition. A blank or corrupt `u-boot-env` still boots correctly because U-Boot uses `default_environment[]`. The env partition is pre-programmed at NOR image build time by `generate_nor_image.py`, which passes the same `bodybytes.env` directly to `mkenvimage` — one file, no duplication (see below).

`bodybytes.env` also defines `bootmenu_0` and `bootmenu_1` so the boot menu (`CONFIG_CMD_BOOTMENU=y`, `CONFIG_AUTOBOOT_MENU_SHOW=y`, `CONFIG_BOOTDELAY=5`) shows meaningful entries:

| Entry | Command |
|-------|---------|
| `Normal boot (eMMC)` | `run bootcmd_normal` |
| `Recovery boot (NOR)` | `run bootcmd_recovery` |
| `U-Boot shell` | *(empty — exits menu and drops to interactive prompt)* |

The menu is a manual override for when serial access is available. If the 5-second countdown expires with no selection, U-Boot falls through to `bootcmd`, which checks the hall sensor and picks the boot path automatically. The sensor check only runs on timeout — a menu selection bypasses it, which is intentional.

#### bootcmd, bootcmd\_normal, bootcmd\_recovery — step by step

**`bootcmd`** (hall-sensor dispatch, runs on autoboot timeout):

```
gpio input 14
if gpio read 14; then
    run bootcmd_recovery
else
    run bootcmd_normal
fi
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `gpio input 14` | Configures GPIO#14 (MDI_TP_P1) as an input. Required before reading; the pad direction is not set by the pinctrl driver at this point. |
| 2 | `gpio read 14` | Reads the logic level. Returns exit code 0 (true) if the pin is **low** (magnet present, sensor pulls down through open-drain output), exit code 1 (false) if **high** (pull-up, no magnet). U-Boot `if` treats exit code 0 as the true branch. |
| 3a | `run bootcmd_recovery` | Pin low → recovery boot. |
| 3b | `run bootcmd_normal` | Pin high → normal eMMC boot. |

**`bootcmd_recovery`** (boot initramfs kernel directly from NOR):

```
echo 'Boot: recovery (NOR)'
bootm 0xBC060000
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `echo 'Boot: recovery (NOR)'` | Prints the selected boot path to the serial console. Printed whether triggered automatically by the hall sensor or selected manually from the boot menu. |
| 2 | `bootm 0xBC060000` | Reads the uImage header at NOR KSEG1 address `0xBC060000` (= NOR physical offset `0x060000`, the recovery partition). The header specifies the image type, load address, entry point, and compressed size. `bootm` decompresses the kernel into the load address in DRAM, sets up the kernel command line and FDT, and jumps to the entry point. No MMC access occurs; the entire operation runs through the NOR memory-mapped window. |

**`bootcmd_normal`** (load kernel from eMMC GPT partition 1 and boot):

```
echo 'Boot: normal (eMMC)'
mmc dev 0
part start mmc 0 1 ks
mmc read 0x82000000 ${ks} 0x10000
bootm 0x82000000
```

| Step | Command | Effect |
|------|---------|--------|
| 1 | `echo 'Boot: normal (eMMC)'` | Prints the selected boot path to the serial console. Printed whether triggered automatically by the hall sensor or selected manually from the boot menu. |
| 2 | `mmc dev 0` | Selects eMMC as the active MMC device. Required before any `mmc` or `part` command. |
| 3 | `part start mmc 0 1 ks` | Reads the GPT on eMMC device 0, finds partition 1 (`kernel`), and stores its start sector (LBA) in the env variable `${ks}`. Requires `CONFIG_CMD_PART=y` and `CONFIG_EFI_PARTITION=y`. |
| 4 | `mmc read 0x82000000 ${ks} 0x10000` | Reads 0x10000 sectors (32 MB) from LBA `${ks}` into DRAM at `0x82000000`. The partition holds the regular kernel binary written raw; 32 MB matches the partition size and `bootm` ignores data past the uImage header's declared size. |
| 5 | `bootm 0x82000000` | Same as bootcmd\_recovery but reads the uImage header from DRAM at `0x82000000`. Decompresses and boots the regular kernel. The kernel's built-in minimal initramfs runs preinit, which calls `mount_root`: scans block devices for squashfs magic, mounts partition 2 (`rootfs`) read-only, then mounts partition 3 (`rootfs_data`, found by GPT label) at `/overlay` via overlayfs. |

**Why `bodybytes.h` is necessary:** `serial_mtk.c` has two codepaths gated on `CONFIG_IS_ENABLED(DM_SERIAL)`. U-Boot proper has `CONFIG_DM_SERIAL=y` and takes the DM path — it gets the UART base address from the DTS `uart2@e00` node, so no `CFG_SYS_NS16550_COM*` is needed there. The SPL has `CONFIG_SPL_DM` **not** set, so it takes the legacy non-DM path, which uses a static struct initialized directly from `CFG_SYS_NS16550_COM##port`. There is a hard `#error` in that path if `CONS_INDEX == 3` and `CFG_SYS_NS16550_COM3` is not defined. `mt7628.h` only defines `COM1` (UART0 at `0xb0000c00`); `bodybytes.h` adds `COM3` for UART2. Without `bodybytes.h` the SPL build fails at compile time. There is no Kconfig symbol for the UART MMIO address, so the `#define` in the header is the only option.

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

#### Env partition pre-programming

U-Boot has two env sources: the compiled-in `default_environment[]` array (built from `bodybytes.env` at compile time) and the env partition in NOR flash. When the env partition CRC is valid U-Boot loads from flash exclusively — the compiled-in defaults are never consulted. This means that once any tool has written to the env partition (e.g. the first `fw_setenv` call from OpenWrt), `bootcmd`, `altbootcmd`, and friends must already be present in the partition or they go missing.

`scripts/generate_nor_image.py` pre-programs the env partition at offset `0x040000` by calling `u-boot/tools/mkenvimage` (built as part of the normal U-Boot build) with `board/bodybytes/bodybytes/bodybytes.env` as input. `mkenvimage` produces a correctly formatted 4 KB binary — a 4-byte CRC32 header followed by null-terminated `key=value` pairs and 0xFF padding — which is embedded directly into the NOR image. The env is valid from the very first power-up; every `fw_setenv` call from OpenWrt safely read-modify-writes the partition without losing boot variables.

`bodybytes.env` is the single source of truth for all boot variables. The U-Boot build compiles it into `default_environment[]` and `generate_nor_image.py` passes it to `mkenvimage` — the same file serves both purposes with no duplication. When adding or changing a boot variable, edit only `bodybytes.env`.

A blank or corrupt env partition still falls back to the compiled-in defaults so the device always boots. If the env is erased (e.g. by a U-Boot-only flash update), run `saveenv` at the U-Boot prompt to restore the compiled-in defaults, or re-program the full NOR image via `generate_nor_image.py`.

#### Boot counter (failed-boot recovery)

`CONFIG_BOOTCOUNT_LIMIT=y` enables the bootcount subsystem. `CONFIG_BOOTCOUNT_ENV=y` selects the env-partition backend, which stores `bootcount` in the U-Boot env (NOR flash, `/dev/mtd1`) and only counts when `upgrade_available=1`.

The mechanism integrates with the sysupgrade flow (see [openwrt.md — Sysupgrade](openwrt.md#sysupgrade)):

| Variable | Set by | Value | Meaning |
|----------|--------|-------|---------|
| `upgrade_available` | `platform.sh` before write | `1` | New firmware written; count failed boots |
| `bootcount` | U-Boot at each boot | incremented | Number of times booted since sysupgrade |
| `bootlimit` | `platform.sh` before write | `3` | Threshold; recovery triggers when `bootcount > bootlimit` |
| `altbootcmd` | `platform.sh` / `bodybytes.env` | `run bootcmd_recovery` | Command to run when limit exceeded |
| `upgrade_available` | `init.d/bootcount` after success | `0` | Successful boot confirmed; stop counting |

**Auto-recovery flow:**

1. Sysupgrade writes `upgrade_available=1`, `bootcount=0`, `bootlimit=3` to the env partition, burns the new kernel to GPT partition 1 (`kernel`), and burns the squashfs rootfs to GPT partition 2 (`rootfs`).
2. On each subsequent boot U-Boot calls `bootcount_inc()` → increments `bootcount` and calls `env_save()` (only while `upgrade_available=1`).
3. `bootcount_error()` checks `bootcount > bootlimit`. If true, U-Boot runs `altbootcmd` (`run bootcmd_recovery`) instead of `bootcmd`. This bypasses the hall-sensor GPIO check and boots directly from NOR — regardless of whether a magnet is present.
4. If the new firmware boots successfully and reaches runlevel 99, `init.d/bootcount` sets `upgrade_available=0` and `bootcount=0`. Counting stops for all future boots until the next sysupgrade.

`platform.sh` and `init.d/bootcount` can therefore call `fw_setenv` unconditionally without risk of losing boot commands — see [Env partition pre-programming](#env-partition-pre-programming) above.

#### eMMC support

The MT7628 RFB defconfig has no eMMC options — U-Boot cannot access the 128 GB eMMC without them. `bodybytes_defconfig` enables `CONFIG_MMC`, `CONFIG_MMC_WRITE`, `CONFIG_CMD_MMC`, and `CONFIG_MMC_MTK`. The DTS has the MMC controller node enabled.

The eMMC uses a GPT partition layout. Four additional options are set in `bodybytes_defconfig`:

| Option | Purpose |
|--------|---------|
| `CONFIG_EFI_PARTITION=y` | GPT partition table parsing in the MMC layer |
| `CONFIG_PARTITION_UUIDS=y` | UUID support required by GPT code paths |
| `CONFIG_CMD_PART=y` | `part start` / `part size` commands; used in `bootcmd_normal` to locate GPT partition 1 |
| `CONFIG_CMD_GPT=y` | `gpt write` command; used during manufacturing to partition a fresh eMMC from U-Boot |

#### SPI NOR flash

**`CONFIG_SPI_FLASH_BAR=y`** — critical. The W25Q512JV is 64 MB but carries no `SPI_NOR_4B_OPCODES` flag, so it uses a Bank Address Register (BAR) to reach addresses above 16 MB. Without this option U-Boot can only see the first 16 MB of flash.

**Speed** — the MT7628 RFB defconfig leaves `CONFIG_SF_DEFAULT_SPEED` and `CONFIG_ENV_SPI_MAX_HZ` at 1 MHz. `CONFIG_ENV_SPI_MAX_HZ` controls env save/restore independently and is not overridden by the DTS `spi-max-frequency`; both are set to 25 MHz in `bodybytes_defconfig`.

Note: the MT7621 SPI controller is half-duplex and does not support quad or dual I/O. `CONFIG_SPI_FLASH_SMART_HWCAPS=y` already ensures the driver will not attempt modes the controller cannot handle.

#### eMMC DTS: SD vs eMMC profile

The MT7628 RFB DTS configures the MMC node for a removable SD card. Three things are corrected in `u-boot/arch/mips/dts/bodybytes,bodybytes.dts`:

**Pinctrl** — the RFB DTS uses `sd_router_mode`, which remaps `i2c`, `uart1`, `sdmode`, and other pin groups as GPIO to free them for routing chips. On bodybytes those peripherals are in use; their pin assignments must not change. `sd_iot_mode` (pre-defined in `mt7628a.dtsi`) sets `EPHY_APGIO_AIO_EN[4:1]=0xf` (MDI P1–P4 pads go digital), `SD_MODE=0` (SDXC signals on EPHY P3/P4 pads), and `ESD=0` (IoT routing). The SDXC data/cmd/clk lines emerge on the MDI P3/P4 pads exactly as the schematic wires them (SoC pins 51–57). `mdi_p1_gpio` is defined in the board DTS and sets SPIS_MODE=gpio, making MDI_TN_P1 (GPIO#15) driveable as the eMMC reset output.

**Capability flags** — `cap-sd-highspeed` targets removable SD cards. For a soldered eMMC, replaced with `cap-mmc-highspeed` + `non-removable`. `cap-mmc-highspeed` selects High Speed SDR mode (up to 52 MHz, ≤52 MB/s on the 4-bit bus) and supports 3.3 V VCCQ — required on this board. HS200 and HS400 require 1.8 V VCCQ and are not reachable through the MT7628 SDXC controller regardless.

**Hardware reset** — the eMMC reset pin is wired to MDI_TN_P1 (SoC pin 42, gpio0 offset 15, active-low). U-Boot pulses it at power-up via a `mmc-pwrseq-emmc` node to clear fault conditions. The eMMC's RST_n function is disabled by default (EXT_CSD[162] = 0x00); pulsing it while disabled is a safe no-op. If the OS later enables RST_n (EXT_CSD[162] = 0x01), the pulse will actually reset the device on subsequent power-ups — which is the intended behaviour.

This is the canonical U-Boot pattern: `drivers/mmc/mmc-pwrseq.c` registers `compatible = "mmc-pwrseq-emmc"` as a proper `U_BOOT_DRIVER` and the `reset-gpios` + `mmc-pwrseq = <&emmc_pwrseq>` DTS pattern is used identically across multiple ARM platforms (Rockchip PX30, Allwinner A20, TI AM335x). The U-Boot driver ignores the `enable` argument and unconditionally pulses RST_n once at MMC probe time: assert for 1 µs then deassert for 200 µs. With `GPIO_ACTIVE_LOW`, `dm_gpio_set_value(&reset, 1)` drives MDI_TN_P1 physically low (RST_n asserted), then `dm_gpio_set_value(&reset, 0)` drives it high (RST_n deasserted).

#### GPIO pin map (EPHY/MDI pads used as GPIO)

When the EPHY pads are in digital mode (`ephy4_1_pad = digital` via `sd_iot_mode`), the MDI P1–P4 pads become software-accessible. The P3/P4 pads are consumed by the SDXC controller (SD_MODE=0). The P1 pads are set to GPIO mode by `mdi_p1_gpio` (SPIS_MODE=gpio) and appear in the gpio0 bank (GPIO#0–31):

| Signal    | SoC pin | GPIO # | gpio0 offset | Purpose |
|-----------|---------|--------|--------------|---------|
| MDI_TP_P1 | 40      | 14     | 14           | Recovery-boot trigger input — TI DRV5032FCDBZT hall-effect sensor (omnipolar, active-low, open-drain, pull-up on board); low = magnet present = boot from NOR recovery partition |
| MDI_TN_P1 | 42      | 15     | 15           | eMMC hardware reset (active-low) |

**How GPIO#14 and GPIO#15 are derived:** The MT7628 assigns GPIO numbers based on each pad's index in the pin table in `drivers/pinctrl/mtmips/pinctrl-mt7628.c` (`mt7628_pins[]`). When `SPIS_MODE = gpio` (set by `mdi_p1_gpio`), the four SPIS pads become GPIOs at consecutive indices in that table:

| `mt7628_pins[]` index | Pin name   | MDI pad   | SoC pin | GPIO # |
|-----------------------|------------|-----------|---------|--------|
| 14                    | `spis_cs`  | MDI_TP_P1 | 40      | 14     |
| 15                    | `spis_clk` | MDI_TN_P1 | 42      | 15     |
| 16                    | `spis_miso`| MDI_RP_P1 | 43      | 16     |
| 17                    | `spis_mosi`| MDI_RN_P1 | 44      | 17     |

U-Boot's `gpio` command uses a flat GPIO number = `bank × 32 + offset`. Both pads are in gpio0 (bank 0), so the flat numbers are 0×32+14 = **14** and 0×32+15 = **15**. This is confirmed by the DTS: `reset-gpios = <&gpio0 15 GPIO_ACTIVE_LOW>` for MDI_TN_P1.

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
