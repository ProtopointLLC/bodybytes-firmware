# Flashing - MT7628AN / Bodybytes

Prerequisites: U-Boot built ([uboot.md](uboot.md)), OpenWrt built ([openwrt.md](openwrt.md)). §4 additionally requires JTAG connected ([jtag.md](jtag.md)).

---

## 1 - NOR flash layout (W25Q512JV, 64 MB)

### 1a - Partition map

| Offset | End | Size | Label | r/w | Description |
|--------|-----|------|-------|-----|-------------|
| `0x000000` | `0x03FFFF` | 256 KB | `u-boot` | RO | SPL + LZMA-compressed U-Boot |
| `0x040000` | `0x04FFFF` | 64 KB | `u-boot-env` | RO† | U-Boot environment (one erase block) |
| `0x050000` | `0x05FFFF` | 64 KB | `factory` | RO | WiFi EEPROM (1 KB) + MAC address |
| `0x060000` | `0x3FFFFFF` | 63.625 MB | `recovery` | RO | Immutable OpenWrt initramfs kernel; boots directly from NOR in recovery mode |

Total: 64 MB (`0x4000000`). † Writable from U-Boot via `saveenv`; marked `read-only` in the OpenWrt DTS.

### 1b - Partition details

**`u-boot` (0x000000, 256 KB)**

Stores `u-boot-with-spl.bin`: SPL (≤64 KB) followed by LZMA-compressed U-Boot proper. At power-up the MT7628 boot ROM reads NOR offset 0 and executes the SPL, which initialises the PLL and DDR2, decompresses U-Boot to `0x80200000`, and jumps there. Current binary is ~173 KB; 83 KB headroom remains.

**`u-boot-env` (0x040000, 64 KB)**

One 64 KB erase block. `CONFIG_ENV_OFFSET=0x040000`, `CONFIG_ENV_SIZE=0x1000` (4 KB active payload), `CONFIG_ENV_SECT_SIZE=0x10000`. U-Boot erases and rewrites this block on `saveenv`. Generated on the fly by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) via [`u-boot/tools/mkenvimage`](../u-boot/tools/mkenvimage) from [`u-boot/board/bodybytes/bodybytes/bodybytes.env`](../u-boot/board/bodybytes/bodybytes/bodybytes.env) - the env is valid from the very first power-up. The partition is marked `read-only` in the OpenWrt DTS; `fw_setenv` cannot write to it without loading `kmod-mtd-rw` first. A blank or corrupt env partition falls back to the compiled-in defaults automatically.

The DTS partition size is `0x10000` (one full erase block) even though `CONFIG_ENV_SIZE` is only `0x1000`. This is required: NOR flash can only be erased in whole sectors (64 KB on the W25Q512JV). Both U-Boot's `saveenv` (which erases `CONFIG_ENV_SECT_SIZE` bytes) and Linux's `fw_setenv` (which issues an erase ioctl for `secsize=0x10000` bytes against `/dev/mtdN`) would fail if the MTD partition were smaller than one sector. The `envsize=0x1000` / `secsize=0x10000` split in the uboot-envtools config (`ubootenv_add_mtd "u-boot-env" "0x0" "0x1000" "0x10000"`) correctly reflects this: 4 KB of active env data within a 64 KB erase unit.

**`factory` (0x050000, 64 KB)**

Holds a 1 KB WiFi EEPROM blob at the start; remaining 63 KB is 0xFF. The DTS exposes the first 1 KB as an nvmem cell (`eeprom@0`) consumed by `&wmac`. Never erase this partition during firmware updates - it is marked `read-only` in the DTS. See §2 for EEPROM format details.

**`recovery` (0x060000, 63.625 MB)**

OpenWrt initramfs kernel (`initramfs-kernel.bin`), stored read-only. When U-Boot detects the recovery trigger (GPIO#14 low) it runs `boot_sf` → `fit_load_sf`: `sf probe` switches the W25Q512JV to 4-byte addressing, reads one block from NOR offset `0x60000` to parse the FIT header and determine the image size, then reads the full image into RAM at `${dram_staging}`, and `bootm` boots from RAM. The initramfs image is self-contained — kernel + rootfs packed into a single FIT image; no separate squashfs mount from NOR or eMMC is needed. The running recovery system is entirely in RAM and cannot modify NOR, making it a safe environment to repair a broken eMMC.

The recovery partition spans the W25Q512JV EAR (Extended Address Register) boundary at 16 MB. `sf read` uses the SPI driver with `CONFIG_SPI_FLASH_BAR=y`, which updates the EAR before each cross-boundary read and can address all four 16 MB regions transparently. Only the bytes indicated by the FIT header are transferred, not the full partition.

| EAR | Address range | Region |
|-----|---------------|--------|
| 0 | `0x00000000`–`0x00FFFFFF` | first 16 MB |
| 1 | `0x01000000`–`0x01FFFFFF` | 16–32 MB |
| 2 | `0x02000000`–`0x02FFFFFF` | 32–48 MB |
| 3 | `0x03000000`–`0x03FFFFFF` | 48–64 MB |

---

## 2 - WiFi factory EEPROM

### 2a - EEPROM format

The mt7603 driver (which handles MT7628) reads a 1 KB (0x400 byte) EEPROM from the `factory` partition. The first 10 bytes must be set at manufacture time; all RF calibration fields can be zero because `mediatek,eeprom-merge-otp` instructs the driver to overlay them from the on-chip eFuse at boot.

| Offset | Size | Field | Value |
|--------|------|-------|-------|
| `0x000` | 2 B | Chip ID (`MT_EE_CHIP_ID`) | `0x7628` little-endian - required; if invalid driver uses eFuse wholesale |
| `0x002` | 2 B | Version | `0x0000` - driver ignores for MT7628 |
| `0x004` | 6 B | WiFi MAC (`MT_EE_MAC_ADDR`) | your assigned MAC address |
| `0x00a`–`0x3FF` | - | RF calibration | zero; merged from on-chip eFuse at boot |

If the factory partition is entirely erased (all `0xFF`), `mt7603_check_eeprom` returns `-EINVAL` and the driver copies the full eFuse wholesale instead of merging - including whatever MAC MediaTek burned into the chip (often `0xFF:FF:FF:FF:FF:FF` on engineering samples). Always write a valid factory blob with your own MAC.

### 2b - Reading the factory partition via JTAG

The MT7628AN SPI NOR is memory-mapped at physical `0x1C000000` (KSEG1: `0xBC000000`), so the factory partition can be read without any flash driver. With U-Boot running, `md.b 0xBC050000 10` shows the first 16 bytes — `28 76` in the first two bytes confirms chip ID `0x7628` LE. To dump the full 64 KB partition from OpenOCD telnet:

```tcl
dump_image build/bodybytes_factory.bin 0xBC050000 0x10000
```

Expected bodybytes field values:

| Offset | Bodybytes value | Note |
|--------|-----------------|------|
| `0x000` | `28 76` | Chip ID `0x7628` LE — required |
| `0x004` | your MAC | WiFi MAC address |
| `0x028` | `00` | Ethernet MAC+1 — bodybytes has no ethernet |
| `0x02e` | `00` | AP/STA second MAC — unused |
| `0x034` | `00` | `NIC_CONF_0` — zero = integrated PA, correct for MT7628AN |
| `0x050`–`0x145` | `00` | RF cal fields — merged from on-chip eFuse at boot via `mediatek,eeprom-merge-otp` |

### 2c - What [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) generates for u-boot-env and factory

The script generates a 1 KB blob (all zeros) with chip ID `0x7628` LE at offset `0x00` and the 6-byte MAC at offset `0x04`; bytes `0x0a`–`0x3FF` are zero and left for the eFuse merge at boot. This blob is embedded at the start of the 64 KB `factory` partition region (rest is `0xFF`).

---

## 3 - Assemble full NOR image (CH341A only)

For CH341A programming, assemble the full NOR image from the repo root inside the dev shell (`nix develop .#uboot`) by running `scripts/flash_nor_images.py --bodybytes --file --mac AA:BB:CC:DD:EE:FF` (`--file` implies `--all`; `--mac` is required because the factory partition contains the WiFi MAC). The script generates `build/bodybytes_nor_image.bin` (size from `[nor]->total_size_mb`, all gaps `0xFF`) and prints the exact `flashrom -p ch341a_spi ...` command to program it. Contents:

| Offset | Content |
|--------|---------|
| `0x000000` | [`u-boot/u-boot-with-spl.bin`](../u-boot/u-boot-with-spl.bin) |
| `0x040000` | U-Boot env (generated by `mkenvimage` from `bodybytes.env`) |
| `0x050000` | WiFi EEPROM blob (chip ID + MAC) |
| `0x060000` | [`openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes_recovery-squashfs-recovery.bin) |

---

## 4 - Program SPI NOR

All scripted flashing uses the Python scripts in `scripts/`. Configuration (serial port, OpenOCD address, NOR size, etc.) lives in [`scripts/config.ini`](../scripts/config.ini). Run all scripts from the repo root inside the dev shell (`nix develop .#uboot`).

### 4a - Bootstrap via JTAG and bring up U-Boot in RAM

Follow [jtag.md](jtag.md) §1 to connect OpenOCD and halt the CPU. Then run `scripts/boot_uboot_jtag.py --bodybytes`. This script automates the full bring-up sequence: verifies the PC and chip ID, initialises PLL and DRAM, tests DRAM, loads `u-boot/u-boot.bin` into RAM via JTAG, and resumes execution. It waits 5 seconds for U-Boot to reach its prompt and exits once done.

U-Boot should appear on **UART2 (TP19/TP20)** at **115200 8N1**: connect with `picocom -b 115200 --flow n /dev/ttyUSB0`.

Do not continue until U-Boot runs correctly from RAM. If it does not execute reliably from RAM it will not execute correctly after being programmed into NOR.

**VS Code tasks:** _JTAG: Boot U-Boot from RAM_ runs `scripts/boot_uboot_jtag.py --bodybytes` and starts _JTAG: Start OpenOCD J-Link_ automatically as a prerequisite - replaces both the OpenOCD setup and the `boot_uboot_jtag.py` step above. _Serial Monitor_ opens `picocom` on `/dev/ttyUSB0` at 115200 8N1 in a dedicated terminal.

### 4b - Full NOR programming (first-time / production)

With U-Boot running at its prompt, run `scripts/flash_nor_images.py --bodybytes --full-erase` to wipe the entire chip first, then `scripts/flash_nor_images.py --bodybytes --all --mac AA:BB:CC:DD:EE:FF` to write all partitions in one pass. `--full-erase` and partition flags are mutually exclusive — run erase separately, then flash. `--all` loads each binary into RAM via JTAG, resumes U-Boot, and writes it to NOR using `sf` at the correct offsets from the U-Boot DTB. `--mac` is required with `--all` because it includes the factory (WiFi EEPROM) partition.

**VS Code task:** _JTAG: Flash NOR_ runs `scripts/flash_nor_images.py --bodybytes --all --mac AA:BB:CC:DD:EE:FF` and starts _JTAG: Start OpenOCD J-Link_ automatically — equivalent to the `--all` step. Run `--full-erase` manually first if a full chip wipe is needed.

Alternatively, program via CH341A SPI programmer without involving U-Boot (board must be powered off). Run `scripts/flash_nor_images.py --bodybytes --file --mac ...` (§3) — it prints the exact `flashrom` command to use.

### 4c - Incremental update (development)

To re-flash individual partitions without a full chip erase, pass partition flags to `flash_nor_images.py --bodybytes`: `--u-boot` for U-Boot only, `--recovery` for the recovery kernel only, or multiple flags together (e.g. `--u-boot-env --factory --mac AA:BB:CC:DD:EE:FF`) to flash both in one pass. `--mac` is required whenever `--factory` is included. Each partition is erased to its DTS-defined size before writing. The env partition is erased — run `saveenv` at the U-Boot prompt on the next boot to restore the compiled-in defaults. Power-cycle to boot from the updated NOR.

### 4d - Verify NOR boot

Power-cycle the board (no JTAG required). The MT7628 boot ROM reads NOR offset 0, executes the SPL, which initialises PLL and DRAM, decompresses U-Boot to `0x80200000`, and transfers control.

U-Boot should appear on **UART2 (TP19/TP20)** at **115200 8N1** without any JTAG assistance. Successful boot confirms: SPL runs, DRAM initialisation succeeds, NOR image layout is correct, U-Boot proper loads.

---

## 5 - eMMC

`emmc_do_upgrade` in `platform.sh` writes the regular kernel to `kernel` (p1) and the squashfs rootfs to `rootfs` (p2) on every sysupgrade. libfstools auto-mounts `rootfs_data` (p3) as `/overlay` by GPT label. The eMMC is never imaged wholesale - `sysupgrade.bin` (~50–100 MB) is the transfer artifact for both first install and all subsequent upgrades.

### 5a - GPT partition layout

All four partitions use the "Linux filesystem" GPT type GUID (`0FC63DAF…`), set automatically by `parted mkpart` without an explicit filesystem type. The GPT type does not enforce any filesystem; only p3 and p4 have actual filesystems.

| # | Label | Filesystem | Size | Content |
|---|-------|-----------|------|---------|
| 1 | `kernel` | none (raw) | 32 MB | Raw FIT image (LZMA kernel + DTB); written by sysupgrade via `dd`; read by U-Boot via `mmc read` |
| 2 | `rootfs` | none (raw) | 512 MB | Raw squashfs rootfs; written by sysupgrade via `dd`; mounted read-only by the kernel |
| 3 | `rootfs_data` | ext4 | 4 GB | Overlay for OpenWrt packages and config; auto-mounted at `/overlay` by libfstools on every boot |
| 4 | `data` | ext4 | ~123.5 GB (remainder) | User file storage; auto-mounted at `/mnt/data` by block-mount |

`kernel` and `rootfs` hold raw binary data - no filesystem is created on them during first install, and sysupgrade raw-writes them with `dd` on every upgrade. `fit_load_mmc` does a two-pass read: reads one block first to parse the FIT header and determine `fit_size`, then reads exactly that many blocks — not the full 32 MB. `bootm` parses the FIT header to locate the LZMA kernel and DTB nodes, decompresses the kernel, applies memory and bootargs fixup to the extracted DTB, and boots. `root=/dev/mmcblk0p2 rootwait` in the main DTB's `chosen/bootargs` node tells the kernel where to find the squashfs rootfs.

The `rootfs_data` label is the standard libfstools extroot partition name. `fstools` mounts it at `/overlay` automatically at every boot with no UCI fstab entry required.

### 5b - First install from NOR recovery

The NOR recovery image (initramfs) includes `parted` in `DEVICE_PACKAGES`, so partitioning can be done entirely from the running recovery shell over SSH or the LuCI web interface.

**Step 1 - boot NOR recovery**

Hold the magnet against the hall-effect sensor during power-on. U-Boot detects GPIO#14 low and runs `boot_sf` (via `boot_selected`), booting the initramfs from NOR. The device comes up as a standard OpenWrt AP; connect to its WiFi network and SSH in as root (no password by default).

**Step 2 - partition the eMMC** (one-time, on a fresh or wiped eMMC)

Create a GPT with `parted -s /dev/mmcblk0 mklabel gpt`, then create the four partitions matching the layout in §5a: `kernel` at 1–33 MiB, `rootfs` at 33–545 MiB, `rootfs_data` at 545–4641 MiB, and `data` from 4641 MiB to 100%. Use `parted -s /dev/mmcblk0 mkpart <label> <start> <end>` for each — `parted` uses the name argument as the GPT partition label. Finally, `mkfs.ext4 -L rootfs_data /dev/mmcblk0p3` and `mkfs.ext4 -L data /dev/mmcblk0p4` format the overlay and data partitions; the `-L` flag sets the ext4 filesystem label that `block-mount` uses to auto-mount.

**Step 3 - install via sysupgrade**

Transfer `sysupgrade.bin` to the device and run sysupgrade. Either:

_Via LuCI web interface:_ open `http://192.168.1.1` → System → Backup / Flash Firmware → Flash new firmware image → upload [`openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin`](../openwrt/bin/targets/ramips/mt76x8/openwrt-25.12.4-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin).

_Via SSH:_ copy `sysupgrade.bin` to `/tmp/` on the device with `scp`, then run `sysupgrade -n /tmp/<filename>` on the device (`-n` skips preserving settings, appropriate for first install).

`emmc_do_upgrade` finds `kernel` and `rootfs` partitions by GPT label, writes the kernel and squashfs, and reboots into the new firmware. All subsequent upgrades follow the same flow (web UI or `sysupgrade`), without the partitioning step.

### 5c - OpenWrt storage mounts

`rootfs_data` is auto-mounted at `/overlay` by libfstools (by GPT label, no UCI entry needed). `data` is mounted at `/mnt/data` via a fstab entry written by `90_defaults` on first boot; if the partition is absent during NOR recovery boot, the label scan finds nothing and boot continues. See [openwrt.md §1 - Board profiles](openwrt.md#board-profiles) for the full mount configuration details.

---

## 6 - Boot configuration

### 6a - Recovery trigger

MDI_TP_P1 (SoC pin 40, GPIO#14) is connected to a **Texas Instruments DRV5032FCDBZT** hall-effect sensor. The sensor is omnipolar (activates on either magnet pole), operates at 3.3 V, and has an active-low open-drain output with a pull-up resistor on the board. Holding a magnet near the sensor pulls GPIO#14 low.

U-Boot reads GPIO#14 at startup before attempting any boot:

- **GPIO#14 high** (no magnet) → normal boot from eMMC
- **GPIO#14 low** (magnet present) → recovery boot directly from NOR

### 6b - bootcmd

The full boot logic is defined in [`u-boot/board/bodybytes/bodybytes/bodybytes.env`](../u-boot/board/bodybytes/bodybytes/bodybytes.env), compiled into `default_environment[]` and also written to NOR by [`scripts/flash_nor_images.py`](../scripts/flash_nor_images.py) via `mkenvimage`. See [uboot.md - Boot sequence](uboot.md#boot-sequence) for the complete variable reference (`boot_selected`, `boot_auto`, `boot_mmc`, `boot_sf`, `fit_load_mmc`, `fit_load_sf`).

Key points relevant to flashing:
- A blank or corrupt env partition falls back to the compiled-in defaults automatically.
- The NOR env partition is `read-only` in the OpenWrt DTS; `fw_setenv` cannot write to it without loading `kmod-mtd-rw`. The compiled-in env is the authoritative copy.
- To manually persist a change after modifying a variable at the U-Boot prompt, run `saveenv`.
- `gpio read recovery_state ${gpio_recovery}` reads GPIO#14 into a variable; `test "${recovery_state}" = "0"` is true when the pin is low (magnet present → `boot_sf`). `boot_auto` is the eMMC path; `boot_sf` is the NOR recovery path.
- For NOR recovery boot: `fit_load_sf` does a two-pass read — reads one block first to parse the FIT header and extract the image size, then reads the exact number of bytes. XIP via `0xBC060000` is not used because the MT7628AN CHIP_MODE strapping selects 3-byte auto-read (16 MB window), insufficient for recovery images that span the 16 MB boundary.
- `CONFIG_CMD_PART=y` and `CONFIG_EFI_PARTITION=y` must be set in `bodybytes_defconfig` for `part start` (used by `fit_load_mmc`) to work - see [uboot.md](uboot.md).

### 6c - Boot sequence

Normal boot:

1. U-Boot reads GPIO#14 → high → `boot_selected` runs `boot_auto`
2. `fit_load_mmc`: reads GPT partition `kernel` (p1) from eMMC into `${dram_staging}` (0x82000000) using `part start`/`part size` + a two-pass `mmc read`; the FIT DTB already contains `console=ttyS2,115200 root=/dev/mmcblk0p2 rootwait` in its `chosen.bootargs`
3. `bootm ${dram_staging}` parses the FIT image: extracts and decompresses the kernel, extracts the DTB, applies memory and bootargs fixup to the DTB, then jumps to the kernel entry
4. Linux mounts squashfs rootfs (p2) as root; libfstools (fstools) detects the `rootfs_data` GPT label on p3 and layers it at `/overlay` via overlayfs

Recovery boot:

1. U-Boot reads GPIO#14 → low → `boot_selected` runs `boot_sf`
2. `fit_load_sf`: `sf probe` switches W25Q512JV to 4-byte mode; reads one block from NOR offset `0x60000` to parse the FIT header and determine `fit_size`, then reads the full image into `${dram_staging}`
3. `bootm ${dram_staging}` parses the FIT image, decompresses the initramfs kernel, and boots with the embedded DTB
4. OpenWrt runs entirely from RAM; eMMC is untouched and available for repair

---

## 7 - Hardware write protection

The W25Q512JV `/WP` pin (active-low) enables status-register-based write protection when asserted. For a production unit, pull `/WP` low after the final programming step and set Block Protect bits (BP3–BP0 in Status Register 1) to protect the entire array. The `SRP=1` bit (with `/WP` asserted) locks the status register itself against further changes.

For development boards, leave `/WP` high (unasserted) to allow re-programming via JTAG.
