# U-Boot - MT7628AN

Source tree: `u-boot/` submodule (tag `v2026.04`) - see [building.md](building.md) for build steps.

## Board files

| File | Purpose |
|------|---------|
| [`u-boot/configs/bodybytes_defconfig`](../u-boot/configs/bodybytes_defconfig) | Complete standalone defconfig |
| [`u-boot/arch/mips/dts/bodybytes,bodybytes.dts`](../u-boot/arch/mips/dts/bodybytes,bodybytes.dts) | Full board device tree |
| [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h) | Board config header: `CFG_SYS_NS16550_COM3` (UART2 MMIO for SPL legacy serial path) |
| [`u-boot/board/bodybytes/bodybytes/bodybytes.env`](../u-boot/board/bodybytes/bodybytes/bodybytes.env) | Default environment: `bootcmd`, `boot_selected`, `boot_auto`, `boot_mmc`, `boot_sf`, `fit_load_mmc`, `fit_load_sf`, `fit_get_size`, `altbootcmd`, `bootmenu_*`, address/layout variables; auto-detected by the build system and compiled into `default_environment[]`; also used by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) as `mkenvimage` input |
| [`u-boot/board/bodybytes/bodybytes/Kconfig`](../u-boot/board/bodybytes/bodybytes/Kconfig) | Board vendor/name declarations |
| [`u-boot/board/bodybytes/bodybytes/MAINTAINERS`](../u-boot/board/bodybytes/bodybytes/MAINTAINERS) | File ownership record |
| [`u-boot/drivers/mmc/mtk-sd.c`](../u-boot/drivers/mmc/mtk-sd.c) | MT7628 MSDC MMC driver: patched to add `mmc-pwrseq` support at probe time and to remove the hardcoded `use_internal_cd = true` from `mt7620_compat` (card-detect is now disabled via `builtin-cd = <0>` in the DTS instead) |
| [`u-boot/arch/mips/mach-mtmips/mt7628/Kconfig`](../u-boot/arch/mips/mach-mtmips/mt7628/Kconfig) | MT7628 SoC Kconfig: adds `BOARD_BODYBYTES` entry and sources the board Kconfig |
| [`u-boot/arch/mips/dts/Makefile`](../u-boot/arch/mips/dts/Makefile) | DTS build list: adds `bodybytes,bodybytes.dtb` under `CONFIG_BOARD_BODYBYTES` |

---

## 1 - Defconfig

### UART2 console

The default MT7628 config uses UART0. One Kconfig change is needed.

**`CONFIG_CONS_INDEX=3`** - selects UART2 as console and triggers the SPL pin mux setup in [`u-boot/arch/mips/mach-mtmips/mt7628/serial.c`](../u-boot/arch/mips/mach-mtmips/mt7628/serial.c).

The SPL serial driver also requires `CFG_SYS_NS16550_COM3` (UART2's MMIO address, `0xb0000e00`), defined in [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h). This is why [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h) exists at all.

**Why [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h) is necessary:** `serial_mtk.c` has two codepaths gated on `CONFIG_IS_ENABLED(DM_SERIAL)`. U-Boot proper has `CONFIG_DM_SERIAL=y` and takes the DM path - it gets the UART base address from the DTS `uart2@e00` node, so no `CFG_SYS_NS16550_COM*` is needed there. The SPL has `CONFIG_SPL_DM=y` but `CONFIG_SPL_DM_SERIAL` is **not** set. `CONFIG_IS_ENABLED(DM_SERIAL)` in an SPL build resolves to `CONFIG_SPL_DM_SERIAL` (not `CONFIG_DM_SERIAL`), so the SPL serial driver takes the legacy non-DM path, which uses a static struct initialized directly from `CFG_SYS_NS16550_COM##port`. There is a hard `#error` in that path if `CONS_INDEX == 3` and `CFG_SYS_NS16550_COM3` is not defined. `mt7628.h` only defines `COM1` (UART0 at `0xb0000c00`); [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h) adds `COM3` for UART2. Without [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h) the SPL build fails at compile time. There is no Kconfig symbol for the UART MMIO address, so the `#define` in the header is the only option.

`CONS_INDEX` is 1-based while the hardware names are 0-based, so UARTLITE**2** = index **3**:

| `CONS_INDEX` | Hardware  |
|--------------|-----------|
| 1 (default)  | UARTLITE0 |
| 2            | UARTLITE1 |
| 3            | UARTLITE2 |

`SPL_UART2_SPIS_PINMUX` must stay **unset** (default). On this board UART2 is on the EPHY/MDI pins - the no-`SPL_UART2_SPIS_PINMUX` path in the SPL sets `EPHY_GPIO_AIO_EN` and clears `UART2_MODE`, which routes to:

| Signal   | SoC pin | Net       | Test point |
|----------|---------|-----------|------------|
| UART2 TX | 47      | MDI_TP_P2 | TP20       |
| UART2 RX | 48      | MDI_TN_P2 | TP19       |

**U-Boot proper DTS:** The SPL configures `EPHY_GPIO_AIO_EN` in C code. U-Boot proper uses DM and applies pinctrl states at driver probe time: `&uart2` is enabled with `pinctrl-names = "default"` and `pinctrl-0 = <&uart2_pins &ephy_iot_mode>`. `uart2_pins` sets `UART2_MODE=0` (route UART2 signals to MDI P2 pads); `ephy_iot_mode` sets `AGPIO_CFG[20:17]=0xf` (MDI P1–P4 pads to digital mode, enabling the signal path). Both states are applied when uart2 is probed. The `uart2` node does not need an explicit `bootph-all` marker - U-Boot propagates the pre-relocation requirement via the `stdout-path` dependency chain.

### Boot variables

The boot variables live in [`u-boot/board/bodybytes/bodybytes/bodybytes.env`](../u-boot/board/bodybytes/bodybytes/bodybytes.env). The U-Boot build system auto-detects that file and compiles it into `default_environment[]`. A blank or corrupt `u-boot-env` partition still boots correctly because U-Boot falls back to the compiled-in defaults. [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) passes the file directly to `mkenvimage` to generate the env partition - the same source file serves both purposes with no duplication. When changing a boot variable, edit only `bodybytes.env`.

The file begins with a block of layout variables (`bootlimit`, `dram_staging`, `dram_staging_max`, `gpio_recovery`, `mmc_dev`, `mmc_part`, `block_size`, `block_mask`, `sf_recovery`, `sf_recovery_max`) that parameterise all the boot commands below them, making it straightforward to adapt the env for different hardware without touching the boot logic.

#### Boot menu

The boot menu (`CONFIG_CMD_BOOTMENU=y`, `CONFIG_AUTOBOOT_MENU_SHOW=y`) exposes two entries plus a shell escape:

| Entry | Command | Effect |
|-------|---------|--------|
| Normal boot | `run boot_selected` | eMMC boot with automatic NOR recovery fallback |
| Recovery boot | `run boot_sf` | NOR recovery boot unconditionally |
| U-Boot shell | *(empty)* | Exits the menu and drops to the interactive prompt |

The menu is a manual override available when serial access is present. If the autoboot countdown expires with no selection, `bootcmd` runs the boot sequence automatically.

#### `bootcmd`

`bootcmd=run boot_selected`. It unconditionally delegates to `boot_selected`, which performs the hall-sensor check and routes to the appropriate boot path.

#### `boot_selected` - hall-sensor dispatch

`boot_selected` reads the TI DRV5032FCDBZT omnipolar hall-effect sensor on GPIO#14 (MDI_TP_P1, active-low, open-drain with board pull-up) to decide which boot path to take.

`gpio read recovery_state ${gpio_recovery}` reads the pin level into the environment variable `recovery_state` and returns success if the GPIO is accessible, failure otherwise. If the read fails (GPIO unavailable), the device falls back to NOR recovery unconditionally. If it succeeds, `recovery_state` is compared: `"0"` means the pin is low (magnet present, sensor asserted) → NOR recovery (`run boot_sf`); otherwise → normal eMMC boot with fallback (`run boot_auto`).

The correct `gpio read <varname> <pin>` syntax (storing the level in a variable and testing it explicitly) is used rather than `gpio read <pin>` alone, because the latter's exit code reflects the GPIO level, making it impossible to distinguish an asserted input from a command failure.

#### `boot_auto` - eMMC with fallback

`boot_auto` attempts `boot_mmc`. If that fails for any reason (eMMC absent, GPT corrupt, read error, FIT format invalid), it prints a message and runs `boot_sf` instead. This is the path taken by `boot_selected` on a normal (no-magnet) power-up and by the "Normal boot" menu entry.

#### `boot_mmc` - eMMC FIT load

`boot_mmc` prints a header line, calls `fit_load_mmc` to load the FIT image, then boots it: `echo "Booting eMMC FIT" && run fit_load_mmc && bootm ${dram_staging}`.

`fit_load_mmc` performs the actual loading from the eMMC `kernel` GPT partition (named by `mmc_part`):

1. `mmc dev` / `mmc rescan` - select and enumerate the eMMC.
2. `part start` / `part size` - locate the `kernel` partition and sanity-check that it contains at least one block.
3. Read one block into `dram_staging` (`0x82000000`) and call `fit_get_size` to parse the FIT header and extract `fit_size`.
4. Convert `fit_size` to a block count (ceiling division using `block_size` = 512 bytes and `block_mask`), verify `fit_blocks` is nonzero and does not exceed the partition, then read the full image.
5. Returns success; `boot_mmc` then calls `bootm ${dram_staging}`. The embedded DTB carries `bootargs`; no `setenv bootargs` is needed.

The eMMC rootfs DTB carries `root=/dev/mmcblk0p2`. fstools mounts `rootfs_data` (partition 3) as the overlay and `data` (partition 4) at `/mnt/data`. `root=PARTLABEL=rootfs` must **not** be used - fstools `partname_volume_find` returns NULL for non-`/dev/` root values unless `fstools_partname_fallback_scan=1` is set, which would break the overlay mount.

#### `boot_sf` - NOR recovery FIT load

`boot_sf` prints a header line, calls `fit_load_sf` to load the FIT image from NOR, then boots it: `echo "Booting NOR recovery FIT" && run fit_load_sf && bootm ${dram_staging}`.

The image cannot be booted directly from the NOR memory-mapped window (KSEG1 at `0xBE000000`). The MT7628 SPI controller's XIP (execute/read-in-place) path uses 3-byte addressing, which is unreliable for a 64 MB flash that U-Boot has placed into 4-byte addressing mode via the Bank Address Register (`CONFIG_SPI_FLASH_BAR=y`). Additionally, `fdt_check_full()` inside `bootm` walks the FDT structure and fails against the memory-mapped window even for addresses within the first 16 MB. The solution is to copy the image to DRAM first using `sf read`, which goes through the SPI driver with correct BAR-aware addressing, then boot from DRAM.

`fit_load_sf` performs the actual NOR load. `sf probe` reinitialises the SPI controller before each load. The sequence is:

1. `sf probe` - initialise the SPI NOR controller.
2. Read one `block_size` (512 bytes) from `sf_recovery` (`0x60000`, the start of the recovery partition) into `dram_staging`, then call `fit_get_size` to extract `fit_size` from the FIT header. `fit_get_size` also validates that `fit_size` is at least 64 bytes and does not exceed `dram_staging_max` (32 MB), so a corrupt or oversize image is rejected before the bulk read.
3. Verify `fit_size` does not exceed `sf_recovery_max` (`0x01fa0000`, ~31.6 MB). This is half the actual NOR `recovery` partition size (0x3fa0000, ~63.3 MB on the 64 MB flash) - kept at ~31.6 MB for compatibility with potential 32 MB NOR variants.
4. Read the full `fit_size` bytes from `sf_recovery` into `dram_staging`.
5. Returns success; `boot_sf` then calls `bootm ${dram_staging}` - boot the FIT from DRAM.

#### `fit_get_size` - FIT header parser

`fit_get_size` is a helper called by both loaders. It temporarily points the U-Boot FDT working pointer at `dram_staging` (where one block has already been read), calls `fdt header get fit_size totalsize` to extract the FIT's declared total size into `fit_size`, then restores the FDT pointer to `fdtcontroladdr` as a side-effect (using `;` so the restore does not affect the return value). `fdtcontroladdr` is U-Boot's live control FDT address, set before any env scripts run via `CONFIG_PREBOOT="fdt addr ${fdtcontroladdr}"`. It returns failure if the header is invalid, if `totalsize` cannot be read, or if `fit_size` is below 64 bytes or above `dram_staging_max`.

### Env partition pre-programming

U-Boot has two env sources: the compiled-in `default_environment[]` array and the env partition in NOR flash (offset `0x040000`, 4 KB, CRC32-prefixed). When the env partition CRC is valid, U-Boot loads from flash exclusively - the compiled-in defaults are never consulted. This means all boot variables must be present in the partition from the first flash.

[`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) generates the env partition on the fly: it passes [`u-boot/board/bodybytes/bodybytes/bodybytes.env`](../u-boot/board/bodybytes/bodybytes/bodybytes.env) directly to [`u-boot/tools/mkenvimage`](../u-boot/tools/mkenvimage), producing a correctly formatted binary - 4-byte CRC32 header, null-terminated `key=value` pairs, 0xFF padding to 4 KB. No patching of the source file is needed; all layout values are variables defined within the env itself. The env partition is valid from the very first power-up.

The `u-boot-env` DTS partition does **not** carry `read-only;` (unlike the `u-boot`, `factory`, and `recovery` partitions). The env partition is writable from Linux via `fw_setenv`. However, OpenWrt never writes to it for boot control - the bootcount mechanism uses the SYSCTL MEMO2 register instead (see [Boot counter](#boot-counter-failed-boot-recovery)), avoiding NOR write wear on every boot. `bootlimit=3` and `altbootcmd` are fixed in both the compiled-in env and the pre-programmed NOR partition and never need to change. `fw_printenv` can read the env for diagnostics; `fw_setenv` can write it if needed. `saveenv` from the U-Boot interactive prompt also writes the partition.

A blank or corrupt env partition falls back to the compiled-in defaults, so the device always boots. If the env partition is erased (e.g. by a U-Boot-only flash update), run `saveenv` at the U-Boot prompt to restore the compiled-in defaults to flash.

### Boot counter (failed-boot recovery)

`CONFIG_BOOTCOUNT_LIMIT=y` enables the bootcount subsystem. `CONFIG_BOOTCOUNT_GENERIC=y` selects the generic memory-mapped register backend, which stores the count in the MT7628 SYSCTL MEMO2 register (`0xb000006c`, KSEG1 uncached). The count survives soft resets (warm reboots) but is lost on power-off - exactly right for tracking consecutive failed boot attempts. Unlike `BOOTCOUNT_ENV`, no NOR write occurs during any boot.

**Register encoding** (`CONFIG_SYS_BOOTCOUNT_SINGLEWORD=y`): MEMO2 packs two fields into one 32-bit word — bits [31:16] hold the magic sentinel `0xB001` (upper half of `CONFIG_SYS_BOOTCOUNT_MAGIC 0xB001C041`), and bits [15:0] hold the boot count. `bootcount_load()` returns 0 if [31:16] does not match the magic (uninitialized or power-cycled register). Linux sees this register at physical address `0x1000006c`; the `devmem` command uses the physical address.

| Register | U-Boot address | Linux physical |
|----------|---------------|----------------|
| SYSCTL MEMO2 | `0xb000006c` (KSEG1) | `0x1000006c` |

The mechanism integrates with the sysupgrade flow (see [openwrt.md - Sysupgrade](openwrt.md#sysupgrade)):

| Step | Actor | Action |
|------|-------|--------|
| Before firmware write | `platform.sh` | `devmem 0x1000006c 32 0xB0010000` - reset MEMO2 to count=0 |
| Each U-Boot boot | `bootcount_inc()` | reads MEMO2, increments count, writes back; mirrors count to in-memory env (no NOR write) |
| Limit exceeded | `bootcount_error()` | reads `bootlimit` from env (fixed at `3`); runs `altbootcmd` (`echo "Boot count: ${bootcount} / ${bootlimit} - limit exceeded"; run boot_sf`) |
| Successful boot (runlevel 99) | `init.d/bootcount` | `devmem 0x1000006c 32 0xB0010000` - resets MEMO2 to count=0 |

**Auto-recovery flow:**

1. Sysupgrade writes `0xB0010000` to MEMO2 (count=0 with magic), burns the new kernel to GPT partition 1 (`kernel`), and burns the squashfs rootfs to GPT partition 2 (`rootfs`). No NOR write.
2. On each U-Boot boot, `bootcount_inc()` reads MEMO2, increments the count, and writes it back. The count is also mirrored to the in-memory env (`env_set_ulong`), but `env_save()` is never called - no NOR write.
3. `bootcount_error()` checks `count > bootlimit`. `bootlimit=3` is read from the env (fixed in the compiled-in default and the NOR env partition). If the limit is exceeded, U-Boot runs `altbootcmd` (which prints a message and runs `boot_sf`) instead of `bootcmd`, booting directly from NOR regardless of the hall sensor.
4. If the new firmware boots successfully and reaches runlevel 99, `init.d/bootcount` writes `0xB0010000` to MEMO2, resetting the counter to zero. All subsequent boots increment from 0, so the limit is never triggered during normal operation.

**Why BOOTCOUNT_GENERIC instead of BOOTCOUNT_ENV:** BOOTCOUNT_ENV would write `bootcount` to the NOR env partition via `fw_setenv` on every boot - this causes unnecessary NOR write wear. BOOTCOUNT_GENERIC stores the count in a SoC scratch register: no flash access at all, and the count is lost on power-off (exactly the right semantics - only consecutive failed attempts within a session are counted). The `bootlimit=3` value stays fixed in the env permanently.

**Defconfig symbols:** `CONFIG_BOOTCOUNT_LIMIT=y`, `CONFIG_BOOTCOUNT_GENERIC=y`, `CONFIG_SYS_BOOTCOUNT_ADDR=0xb000006c`, `CONFIG_SYS_BOOTCOUNT_SINGLEWORD=y`, `CONFIG_SYS_BOOTCOUNT_LE=y`, `CONFIG_CMD_BOOTCOUNT=y`. `CONFIG_SYS_BOOTCOUNT_MAGIC` defaults to `0xB001C041` from the Kconfig when `BOOTCOUNT_GENERIC` is selected - no explicit definition is needed in [`u-boot/include/configs/bodybytes.h`](../u-boot/include/configs/bodybytes.h). The `gardena-smart-gateway-mt7688` board in the same U-Boot tree uses the identical register address on the same SoC and confirms this approach.

### eMMC support

The MT7628 RFB defconfig has no eMMC options - U-Boot cannot access the eMMC without them. [`u-boot/configs/bodybytes_defconfig`](../u-boot/configs/bodybytes_defconfig) enables `CONFIG_MMC`, `CONFIG_MMC_WRITE`, `CONFIG_CMD_MMC`, `CONFIG_MMC_MTK`, `CONFIG_PWRSEQ=y`, and `CONFIG_MMC_PWRSEQ=y`. The DTS has the MMC controller node enabled. `CONFIG_PWRSEQ` / `CONFIG_MMC_PWRSEQ` are required to compile the pwrseq support added to [`u-boot/drivers/mmc/mtk-sd.c`](../u-boot/drivers/mmc/mtk-sd.c).

The eMMC uses a GPT partition layout. Four additional options are set in [`u-boot/configs/bodybytes_defconfig`](../u-boot/configs/bodybytes_defconfig):

| Option | Purpose |
|--------|---------|
| `CONFIG_EFI_PARTITION=y` | GPT partition table parsing in the MMC layer |
| `CONFIG_PARTITION_UUIDS=y` | UUID support required by GPT code paths |
| `CONFIG_CMD_PART=y` | `part start` / `part size` commands; used in `fit_load_mmc` to locate the `kernel` GPT partition |
| `CONFIG_CMD_GPT=y` | `gpt write` command; available for ad-hoc partitioning from the U-Boot prompt (primary install uses `parted` from NOR recovery - see [flashing.md §5b](flashing.md#5b--first-install-from-nor-recovery)) |

### SPI NOR flash

**`CONFIG_SPI_FLASH_BAR=y`** - critical. The W25Q512JV is 64 MB but carries no `SPI_NOR_4B_OPCODES` flag, so it uses a Bank Address Register (BAR) to reach addresses above 16 MB. Without this option U-Boot can only see the first 16 MB of flash.

**Speed** - the MT7628 RFB defconfig leaves `CONFIG_SF_DEFAULT_SPEED` and `CONFIG_ENV_SPI_MAX_HZ` at 1 MHz. `CONFIG_ENV_SPI_MAX_HZ` controls env save/restore independently and is not overridden by the DTS `spi-max-frequency`; both are set to 25 MHz in [`u-boot/configs/bodybytes_defconfig`](../u-boot/configs/bodybytes_defconfig).

Note: the MT7621 SPI controller is half-duplex and does not support quad or dual I/O. `CONFIG_SPI_FLASH_SMART_HWCAPS=y` (default y) already ensures the driver will not attempt modes the controller cannot handle.

**MTD layer** - `CONFIG_SPI_FLASH_MTD=y` and `CONFIG_MTD=y` expose the NOR flash through the MTD subsystem, enabling `CONFIG_CMD_MTD` (`mtd` shell command) for ad-hoc erase/read/write from the U-Boot prompt.

**SFDP** - `CONFIG_SPI_FLASH_SFDP_SUPPORT=y` allows the SPI NOR driver to read flash parameters (capacity, erase sizes, timing) from the flash's SFDP tables, supplementing the per-manufacturer entries already in the defconfig.

### D-cache disabled

**`CONFIG_MIPS_CACHE_DISABLE=y`** - all other MT7628 boards in the tree (mt7628_rfb, linkit-7688, and others) carry this flag; bodybytes follows the same pattern.

With `CONFIG_MIPS_CACHE_SETUP=y` and `CONFIG_MIPS_CACHE_DISABLE=y` set together, the generic MIPS start code initialises the cache arrays (required on 24KEc to avoid tag parity faults) and then immediately disables them. U-Boot runs fully uncached for its entire lifetime.

**Why this matters for JTAG flashing:** [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) loads a binary into DRAM via OpenOCD `load_image` (PRACC - the CPU executes the write through its virtual address space), then issues `sf write <addr>` from U-Boot to program NOR. Without cache disabled, the D-cache can hold stale lines over the physical DRAM that JTAG just wrote; `sf write` then reads those stale lines rather than the newly written data, silently programming garbage into NOR. With cache disabled, every load and store goes directly to DRAM - JTAG writes are immediately visible to U-Boot with no coherency step required.

**Why this also matters for kernel boot stability:** With cache enabled and a stack at a hardcoded KSEG0 address above the physical RAM size (e.g. `0x89001F00` in the vendor U-Boot), MIPS KSEG0 aliasing means those dirty D-cache lines map to a physical address that wraps into real RAM - on a 128 MB device, `0x89001F00` → physical `0x09001F00` wraps to `0x01001F00`, which also maps to `0x81001F00`. During early boot, Linux writes back the entire D-cache; the stale lines for that aliased address corrupt whatever the kernel placed there - typically the Device Tree. The resulting panic manifests as an unaligned-access trap in `__of_find_property` before any drivers initialise. Running U-Boot fully uncached eliminates this class of failure: no dirty lines accumulate during the U-Boot lifetime, so there is nothing stale for Linux to flush.

**Linux is unaffected.** The MIPS kernel unconditionally re-enables and re-configures the caches during early `cpu_probe` / `cpu_cache_init` before any driver or userspace code runs.

### DRAM initialization (SPL)

The MT7628 has no on-chip SRAM. The SPL therefore cannot run C code until it has both an initialized cache and a stack, which creates a chicken-and-egg problem: DRAM must be initialized to provide a stack, but C code is needed to initialize DRAM.

The MediaTek port resolves this with a cache-as-SRAM trick, driven by `SOC_MT7628` auto-selecting `MIPS_INIT_STACK_IN_SRAM`, `MIPS_SRAM_INIT`, and `SYS_MIPS_CACHE_INIT_RAM_LOAD` in [`u-boot/arch/mips/mach-mtmips/Kconfig`](../u-boot/arch/mips/mach-mtmips/Kconfig).

**SPL start sequence** ([`arch/mips/cpu/start.S`](../u-boot/arch/mips/cpu/start.S)):

| Step | Code | Effect |
|------|------|--------|
| 1 | `mips_cache_disable` | CP0_CONFIG[K0] = UNCACHED (2). Cache hardware still present - just not serving KSEG0 |
| 2 | `mips_sram_init` | Zeros I/D cache tag arrays (prevents parity faults). Then re-enables KSEG0 as cacheable and locks 16 KB of D-cache (`CACHE_STACK_BASE`…+0x4000) with VALID+DIRTY+LOCK - these lines act as fake SRAM |
| 3 | `setup_stack_gd` | Sets sp = `SYS_INIT_SP_ADDR` (0x80080000, KSEG0). Accesses hit the locked D-cache; no DRAM access occurs |
| 4 | `lowlevel_init` → `mt7628_init()` | Calls `mt7628_ddr_init()` in [`arch/mips/mach-mtmips/mt7628/ddr.c`](../u-boot/arch/mips/mach-mtmips/mt7628/ddr.c): detects DDR type (DDR1/DDR2) and package variant from SYSCFG0, selects the matching timing table, runs `ddr1_init()`/`ddr2_init()`, calibrates DQ/DQS delays. Sets `gd->ram_size`. After return: flushes locked D-cache lines to real DRAM (`HIT_WRITEBACK_INV_D`), then sets KSEG0 uncached again |
| 5 | `mips_cache_reset` | Full cache-tag re-initialization. Leaves CP0_CONFIG[K0] unchanged (uncached) |
| 6 | `board_init_f` | `spl_init()`, serial init, then `board_init_r()` loads U-Boot proper from NOR via `spl_nor_get_uboot_base()` (first image after `__image_copy_end`, skipping an optional FDT blob) |

**Why `CONFIG_SKIP_LOWLEVEL_INIT=y` does not break the SPL.** `CONFIG_IS_ENABLED(X)` in an SPL build resolves to `CONFIG_SPL_X` (not `CONFIG_X`). `CONFIG_SPL_SKIP_LOWLEVEL_INIT` is not set in the defconfig, so the macro evaluates to false inside SPL - `lowlevel_init` is called and DRAM is initialized. In U-Boot proper (non-SPL build) the macro resolves to `CONFIG_SKIP_LOWLEVEL_INIT=y`, so `lowlevel_init` is correctly skipped - DRAM is already up.

**DRAM type and size are fully auto-detected at runtime.** `mt7628_ddr_init()` reads `SYSCTL_SYSCFG0_REG` for DDR type and `SYSCTL_CHIP_REV_ID_REG` for the package ID (KN package forces DDR1), and `SYSCTL_CLKCFG0_REG` to choose between 160 MHz and 200 MHz timing tables. The timing tables in `ddr.c` cover DDR1 and DDR2 at both speeds in sizes from 8 MB to 256 MB. No board-specific DRAM configuration is required.

### eMMC DTS

The MT7628 RFB DTS configures the MMC node for a removable SD card. The bodybytes DTS adapts it for a soldered eMMC:

**Pinctrl** - the RFB DTS uses `sd_router_mode`, which remaps `i2c`, `uart1`, `sdmode`, and other pin groups as GPIO to free them for routing chips. On bodybytes those peripherals are in use; their pin assignments must not change. `sd_iot_mode` (pre-defined in `mt7628a.dtsi`) sets `EPHY_APGIO_AIO_EN[4:1]=0xf` (MDI P1–P4 pads go digital), `SD_MODE=0` (SDXC signals on EPHY P3/P4 pads), and `ESD=0` (IoT routing). The SDXC data/cmd/clk lines emerge on the MDI P3/P4 pads exactly as the schematic wires them (SoC pins 51–57).

**Card detect** - the MTK SDXC driver's `mt7620_compat` originally had `use_internal_cd = true` (the MT7628 shares this compat entry). This was removed in the patched [`u-boot/drivers/mmc/mtk-sd.c`](../u-boot/drivers/mmc/mtk-sd.c) so internal card-detect is no longer assumed by default. The DTS sets `builtin-cd = <0>` to make this explicit. The eMMC is always present; no card-detect mechanism is needed.

**Bus width** - `bus-width = <4>` (4-bit). 8-bit is not possible: the dtsi defines `emmc_iot_8bit_mode` which would supply SD_D4–SD_D7 by remapping `groups = "uart2"; function = "sdxc d5 d4"`, conflicting with UART2 as the system console.

**Clock** - `max-frequency = <1000000>` caps the SDXC clock at 1 MHz. This is conservative but sufficient for U-Boot boot time. No `cap-mmc-highspeed` or `non-removable` is set in the current DTS.

**Power sequencing** - [`u-boot/drivers/mmc/mtk-sd.c`](../u-boot/drivers/mmc/mtk-sd.c) was patched to call `mmc_pwrseq_get_power()` / `pwrseq_set_power()` at probe time (`CONFIG_MMC_PWRSEQ=y`). The current DTS does not include an `mmc-pwrseq` node, so the pwrseq code is compiled in but no pulse is issued. If an `mmc-pwrseq-emmc` node with `reset-gpios = <&gpio0 15 GPIO_ACTIVE_LOW>` is added to the DTS, U-Boot will pulse MDI_TN_P1 (GPIO#15, the eMMC RST_n line) at probe time to clear fault conditions.

### GPIO pin map (EPHY/MDI pads used as GPIO)

When the EPHY pads are in digital mode (`ephy4_1_pad = digital` via `sd_iot_mode`), the MDI P1–P4 pads become software-accessible. The P3/P4 pads are consumed by the SDXC controller (SD_MODE=0). The P1 pads are set to GPIO mode by `mdi_p1_gpio` (SPIS_MODE=gpio) and appear in the gpio0 bank (GPIO#0–31):

| Signal    | SoC pin | GPIO # | gpio0 offset | Purpose |
|-----------|---------|--------|--------------|---------|
| MDI_TP_P1 | 40      | 14     | 14           | Recovery-boot trigger input - TI DRV5032FCDBZT hall-effect sensor (omnipolar, active-low, open-drain, pull-up on board); low = magnet present = boot from NOR recovery partition |
| MDI_TN_P1 | 42      | 15     | 15           | eMMC RST_n line (active-low); made driveable by `mdi_p1_gpio`; currently not driven (no `mmc-pwrseq` node in DTS) |

**How GPIO#14 and GPIO#15 are derived:** The MT7628 assigns GPIO numbers based on each pad's index in the pin table in [`u-boot/drivers/pinctrl/mtmips/pinctrl-mt7628.c`](../u-boot/drivers/pinctrl/mtmips/pinctrl-mt7628.c) (`mt7628_pins[]`). When `SPIS_MODE = gpio` (set by `mdi_p1_gpio`), the four SPIS pads become GPIOs at consecutive indices in that table:

| `mt7628_pins[]` index | Pin name   | MDI pad   | SoC pin | GPIO # |
|-----------------------|------------|-----------|---------|--------|
| 14                    | `spis_cs`  | MDI_TP_P1 | 40      | 14     |
| 15                    | `spis_clk` | MDI_TN_P1 | 42      | 15     |
| 16                    | `spis_miso`| MDI_RP_P1 | 43      | 16     |
| 17                    | `spis_mosi`| MDI_RN_P1 | 44      | 17     |

U-Boot's `gpio` command uses a flat GPIO number = `bank × 32 + offset`. Both pads are in gpio0 (bank 0), so the flat numbers are 0×32+14 = **14** and 0×32+15 = **15**. These are verified from `mt7628_pins[]` indices and confirmed by `gpio_recovery=14` in the env. If `mmc-pwrseq-emmc` is added to the DTS, the correct DTS reference for the RST_n GPIO is `<&gpio0 15 GPIO_ACTIVE_LOW>`.

The eMMC data/cmd/clk signals (MDI P3/P4 pads) are driven by the SDXC controller and are not accessible as GPIO while `sd_iot_mode` is active:

| SDXC signal | SoC pin | MDI pad    | GPIO # if SD_MODE=GPIO |
|-------------|---------|------------|------------------------|
| SD_D1       | 51      | MDI_RP_P3  | 24 |
| SD_D0       | 52      | MDI_RN_P3  | 25 |
| SD_CLK      | 54      | MDI_RP_P4  | 26 |
| SD_CMD      | 55      | MDI_RN_P4  | 27 |
| SD_D3       | 56      | MDI_TP_P4  | 28 |
| SD_D2       | 57      | MDI_TN_P4  | 29 |
