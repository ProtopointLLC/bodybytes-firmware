# Flashing — MT7628AN / Bodybytes

Prerequisites: U-Boot built ([uboot.md](uboot.md)), OpenWrt built ([openwrt.md](openwrt.md)), JTAG connected ([jtag.md](jtag.md)).

---

## 1 — NOR flash layout (W25Q512JV, 64 MB)

### 1a — Partition map

| Offset | End | Size | Label | r/w | Description |
|--------|-----|------|-------|-----|-------------|
| `0x000000` | `0x03FFFF` | 256 KB | `u-boot` | RO | SPL + LZMA-compressed U-Boot |
| `0x040000` | `0x04FFFF` | 64 KB | `u-boot-env` | RW | U-Boot environment (one erase block) |
| `0x050000` | `0x05FFFF` | 64 KB | `factory` | RO | WiFi EEPROM (1 KB) + MAC address |
| `0x060000` | `0x3FFFFFF` | 63.625 MB | `recovery` | RO | Immutable OpenWrt initramfs kernel; boots directly from NOR in recovery mode |

Total: 64 MB (`0x4000000`)

### 1b — Partition details

**`u-boot` (0x000000, 256 KB)**

Stores `u-boot-with-spl.bin`: SPL (≤64 KB) followed by LZMA-compressed U-Boot proper. At power-up the MT7628 boot ROM reads NOR offset 0 and executes the SPL, which initialises the PLL and DDR2, decompresses U-Boot to `0x80200000`, and jumps there. Current binary is ~173 KB; 83 KB headroom remains.

**`u-boot-env` (0x040000, 64 KB)**

One 64 KB erase block. `CONFIG_ENV_OFFSET=0x040000`, `CONFIG_ENV_SIZE=0x1000` (4 KB active payload), `CONFIG_ENV_SECT_SIZE=0x10000`. U-Boot erases and rewrites this block on `saveenv`. Pre-programmed by `generate_nor_image.py` via `u-boot/tools/mkenvimage` using `board/bodybytes/bodybytes/bodybytes.env` — the env is valid from the very first power-up. The partition is left writable in the OpenWrt DTS so that `fw_setenv` (from the `u-boot-envtools` package) can update variables at runtime — for example, to arm the boot counter before a sysupgrade.

**`factory` (0x050000, 64 KB)**

Holds a 1 KB WiFi EEPROM blob at the start; remaining 63 KB is 0xFF. The DTS exposes the first 1 KB as an nvmem cell (`eeprom@0`) consumed by `&wmac`. Never erase this partition during firmware updates — it is marked `read-only` in the DTS. See §2 for EEPROM format details.

**`recovery` (0x060000, 63.625 MB)**

OpenWrt initramfs kernel (`initramfs-kernel.bin`), stored read-only. Boots directly from the NOR memory-mapped window at `0xBC060000` when U-Boot detects the recovery trigger (GPIO#14 low). The initramfs image is self-contained — kernel + rootfs packed into a single uImage; no separate squashfs mount from NOR or eMMC is needed. The running recovery system is entirely in RAM and cannot modify NOR, making it a safe environment to repair a broken eMMC.

Spans the W25Q512JV EAR (Extended Address Register) boundary at 16 MB; `CONFIG_SPI_FLASH_BAR=y` makes U-Boot cross 16 MB boundaries transparently:

| EAR | Address range | Region |
|-----|---------------|--------|
| 0 | `0x00000000`–`0x00FFFFFF` | first 16 MB |
| 1 | `0x01000000`–`0x01FFFFFF` | 16–32 MB |
| 2 | `0x02000000`–`0x02FFFFFF` | 32–48 MB |
| 3 | `0x03000000`–`0x03FFFFFF` | 48–64 MB |

---

## 2 — WiFi factory EEPROM

### 2a — EEPROM format

The mt7603 driver (which handles MT7628) reads a 1 KB (0x400 byte) EEPROM from the `factory` partition. The first 10 bytes must be set at manufacture time; all RF calibration fields can be zero because `mediatek,eeprom-merge-otp` instructs the driver to overlay them from the on-chip eFuse at boot.

| Offset | Size | Field | Value |
|--------|------|-------|-------|
| `0x000` | 2 B | Chip ID (`MT_EE_CHIP_ID`) | `0x7628` little-endian — required; if invalid driver uses eFuse wholesale |
| `0x002` | 2 B | Version | `0x0000` — driver ignores for MT7628 |
| `0x004` | 6 B | WiFi MAC (`MT_EE_MAC_ADDR`) | your assigned MAC address |
| `0x00a`–`0x3FF` | — | RF calibration | zero; merged from on-chip eFuse at boot |

If the factory partition is entirely erased (all `0xFF`), `mt7603_check_eeprom` returns `-EINVAL` and the driver copies the full eFuse wholesale instead of merging — including whatever MAC MediaTek burned into the chip (often `0xFF:FF:FF:FF:FF:FF` on engineering samples). Always write a valid factory blob with your own MAC.

### 2b — Dumping from reference hardware

The MT7628AN SPI NOR is memory-mapped at physical `0x1C000000` (KSEG1: `0xBC000000`), so it can be read without any flash driver via JTAG:

```tcl
# OpenOCD: read 64 KB factory partition directly from NOR memory window
# VoCore2 factory is at flash offset 0x40000; bodybytes is at 0x50000
dump_image vocore2_factory.bin 0xBC040000 0x10000
```

On stock VoCore2 U-Boot (v1.1.3, no `sf` command), load into RAM first if preferred:

```
# U-Boot console (VoCore2 factory partition at 0x40000)
md.b 0xBC040000 10
```

The first two bytes should read `28 76` (chip ID `0x7628` LE). Then dump via OpenOCD:

```tcl
dump_image vocore2_factory.bin 0xBC040000 0x10000
```

Verified contents of `docs/vocore2_factory.bin` (reference dump):

| Offset | VoCore2 value | Bodybytes | Note |
|--------|---------------|-----------|------|
| `0x000` | `28 76` | `28 76` | Chip ID — format matches |
| `0x004` | `b8:d8:12:6c:d2:f4` | your MAC | WiFi MAC — offset matches |
| `0x028` | `b8:d8:12:6c:d2:f5` | `00` | Ethernet MAC+1 — bodybytes has no ethernet |
| `0x02e` | `b8:d8:12:6c:d2:f7` | `00` | AP/STA second MAC — unused |
| `0x034` | `11 34` (`NIC_CONF_0`) | `00` | External PA/LNA config; zero = integrated PA, correct for MT7628AN |
| `0x050`–`0x145` | RF cal data | `00` | Merged from eFuse at boot via `eeprom-merge-otp` |

The VoCore2 has RF calibration burned from factory testing. Bodybytes zeroes those fields and relies on the eFuse path — this is the designed use case for `mediatek,eeprom-merge-otp`.

### 2c — What `generate_nor_image.py` writes

The script produces a correctly formatted 1 KB EEPROM blob embedded in the `factory` partition:

```python
eeprom = bytearray(0x400)        # 1 KB, all zeros
eeprom[0x00:0x02] = b'\x28\x76'  # chip ID 0x7628 LE
eeprom[0x04:0x0a] = mac_bytes    # 6-byte MAC from --mac argument
# bytes 0x0a–0x3FF: zero; eFuse merge fills RF cal fields at boot
```

---

## 3 — Assemble NOR image

From the repo root:

```sh
scripts/generate_nor_image.py AA:BB:CC:DD:EE:FF
```

Produces `assets/bodybytes_nor_image.bin` (64 MB, all gaps `0xFF`) containing:

| Offset | Content |
|--------|---------|
| `0x000000` | `u-boot/u-boot-with-spl.bin` |
| `0x040000` | U-Boot env, pre-programmed by `u-boot/tools/mkenvimage` from `board/bodybytes/bodybytes/bodybytes.env` |
| `0x050000` | 1 KB WiFi EEPROM blob (chip ID `0x7628` + MAC from `--mac`) |
| `0x060000` | `openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-recovery.bin` |

The script also prints the two `sf` commands needed to program the image from U-Boot. Use `--out` to override the output path.

---

## 4 — Program SPI NOR

### 4a — Bootstrap via JTAG and smoke-test U-Boot

Follow [jtag.md](jtag.md) §1 and §2 to verify JTAG connectivity and initialise PLL and DRAM.

Load `u-boot.bin` into RAM from the OpenOCD telnet prompt:

```tcl
load_image u-boot/u-boot.bin 0x80200000 bin
reg pc 0x80200000
resume
```

U-Boot should appear on **UART2 (TP19/TP20)** at **115200 8N1**:

```sh
picocom -b 115200 --flow n /dev/ttyUSB0
```

If there is no output: confirm `CONFIG_CONS_INDEX=3` is set, the binary was rebuilt, the terminal is **115200 8N1**, and the JTAG bootstrap completed successfully.

Do not continue until U-Boot runs correctly from RAM. If it does not execute reliably from RAM it will not execute correctly after being programmed into NOR.

### 4b — Full NOR programming (first-time / production)

Bodybytes has no Ethernet; the only way to transfer the image is via JTAG. Load `assets/bodybytes_nor_image.bin` into RAM while U-Boot idles at its prompt (no halt needed):

```tcl
load_image assets/bodybytes_nor_image.bin 0x80000000 bin
```

Then run the two `sf` commands printed by `generate_nor_image.py` at the U-Boot console:

```
sf probe
sf erase 0 0x4000000
sf write 0x80000000 0 0x4000000
```

This erases and rewrites the full 64 MB in one pass. All partition contents — U-Boot, env, factory EEPROM, and recovery kernel — are already assembled in the image at their correct offsets.

Alternatively, write `assets/bodybytes_nor_image.bin` directly with a SPI flash programmer (e.g. `flashrom`) without involving U-Boot at all.

### 4c — U-Boot-only update (development)

For iterating on U-Boot without touching the factory or recovery partitions, load just `u-boot-with-spl.bin` while U-Boot is running at its prompt:

```tcl
# OpenOCD telnet
load_image u-boot/u-boot-with-spl.bin 0x80080000 bin
```

Note the byte count from `load_image`, then at the U-Boot console:

```
sf probe
sf erase 0 0x50000
sf write 0x80080000 0 0x<byte_count_hex>
```

This erases u-boot + env (preserving factory at `0x050000`) and writes the new binary. The env partition is erased — run `saveenv` at the U-Boot prompt on the next boot to restore compiled-in defaults, or load a fresh `assets/bodybytes_nor_image.bin` and re-program the env sector: `sf erase 0x40000 0x10000; sf write 0x80040000 0x40000 0x1000`. Power-cycle to boot from the updated NOR.

### 4d — Verify NOR boot

Power-cycle the board (no JTAG required). The MT7628 boot ROM reads NOR offset 0, executes the SPL, which initialises PLL and DRAM, decompresses U-Boot to `0x80200000`, and transfers control.

U-Boot should appear on **UART2 (TP19/TP20)** at **115200 8N1** without any JTAG assistance. Successful boot confirms: SPL runs, DRAM initialisation succeeds, NOR image layout is correct, U-Boot proper loads.

---

## 5 — eMMC

`emmc_do_upgrade` in `platform.sh` writes the regular kernel to `kernel` (p1) and the squashfs rootfs to `rootfs` (p2) on every sysupgrade. libfstools auto-mounts `rootfs_data` (p3) as `/overlay` by GPT label. The eMMC is never imaged wholesale — `sysupgrade.bin` (~50–100 MB) is the transfer artifact for both first install and all subsequent upgrades.

### 5a — GPT partition layout

| # | Label | Type | Size | Content |
|---|-------|------|------|---------|
| 1 | `kernel` | Linux filesystem | 32 MB | Regular kernel binary (raw uImage); U-Boot reads from the partition start; sysupgrade writes here |
| 2 | `rootfs` | Linux filesystem | 512 MB | squashfs rootfs; written by sysupgrade; preinit mounts read-only |
| 3 | `rootfs_data` | Linux filesystem | 4 GB | ext4; auto-mounted at `/overlay` by libfstools on every boot; all `opkg install` output lands here |
| 4 | `data` | Linux filesystem | ~123.5 GB (remainder) | ext4; file server storage, auto-mounted at `/mnt/data` by block-mount |

`kernel` and `rootfs` hold raw binary data, not filesystems. U-Boot reads a 32 MB window from the start of `kernel` and passes it to `bootm`; the uImage header contains the actual image size. preinit's `mount_root` scans block devices for squashfs magic; there is no `root=` kernel argument.

The `rootfs_data` label is the standard libfstools extroot partition name. `fstools` mounts it at `/overlay` automatically at every boot with no UCI fstab entry required.

### 5b — First install from NOR recovery

The NOR recovery image (initramfs) includes `parted` in `DEVICE_PACKAGES`, so partitioning can be done entirely from the running recovery shell over SSH or the LuCI web interface.

**Step 1 — boot NOR recovery**

Hold the magnet against the hall-effect sensor during power-on. U-Boot detects GPIO#14 low and runs `bootcmd_recovery`, booting the initramfs from NOR. The device comes up as a standard OpenWrt AP; connect to its WiFi network and SSH in as root (no password by default).

**Step 2 — partition the eMMC** (one-time, on a fresh or wiped eMMC)

```sh
parted -s /dev/mmcblk0 mklabel gpt
parted -s /dev/mmcblk0 mkpart kernel   1MiB   33MiB
parted -s /dev/mmcblk0 mkpart rootfs  33MiB  545MiB
parted -s /dev/mmcblk0 mkpart rootfs_data 545MiB 4641MiB
parted -s /dev/mmcblk0 mkpart data  4641MiB 100%
mkfs.ext4 -L rootfs_data /dev/mmcblk0p3
mkfs.ext4 -L data        /dev/mmcblk0p4
```

These sizes match the GPT layout in §5a. `parted` uses the partition name as the GPT label. `mkfs.ext4 -L data` sets the ext4 filesystem label that `block-mount` uses to auto-mount the partition.

**Step 3 — install via sysupgrade**

Transfer `sysupgrade.bin` to the device and run sysupgrade. Either:

*Via LuCI web interface:* open `http://192.168.1.1` → System → Backup / Flash Firmware → Flash new firmware image → upload `openwrt-ramips-mt76x8-bodybytes_bodybytes-sysupgrade.bin`.

*Via SSH:*

```sh
# On the host — transfer sysupgrade.bin to the device's RAM
scp openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-sysupgrade.bin \
    root@192.168.1.1:/tmp/

# On the device
sysupgrade -n /tmp/openwrt-ramips-mt76x8-bodybytes_bodybytes-sysupgrade.bin
```

`emmc_do_upgrade` finds `kernel` and `rootfs` partitions by GPT label, writes the kernel and squashfs, and reboots into the new firmware. All subsequent upgrades follow the same flow (web UI or `sysupgrade`), without the partitioning step.

### 5c — OpenWrt storage mounts

The `rootfs_data` partition is auto-mounted at `/overlay` by libfstools (`fstools` package) without any configuration — libfstools scans GPT labels at boot and mounts any partition labelled `rootfs_data` as the overlay.

The `data` partition is mounted automatically by `block-mount` via `option auto_mount 1` in `/etc/config/fstab` (shipped in the subtarget base-files). `block-mount` scans block devices via `blkid`, matches the ext4 filesystem label set by `mkfs.ext4 -L data`, and mounts it at `/mnt/data`. If the partition is absent or unformatted — e.g. during recovery with a fresh eMMC — the scan finds nothing and boot continues normally.

`block-mount` and `kmod-fs-ext4` must be present in the image (both are in `DEVICE_PACKAGES`) for auto-mount to work.

See [openwrt.md](openwrt.md) for the board profile and sysupgrade dispatch.

---

## 6 — Boot configuration

### 6a — Recovery trigger

MDI_TP_P1 (SoC pin 40, GPIO#14) is connected to a **Texas Instruments DRV5032FCDBZT** hall-effect sensor. The sensor is omnipolar (activates on either magnet pole), operates at 3.3 V, and has an active-low open-drain output with a pull-up resistor on the board. Holding a magnet near the sensor pulls GPIO#14 low.

U-Boot reads GPIO#14 at startup before attempting any boot:
- **GPIO#14 high** (no magnet) → normal boot from eMMC
- **GPIO#14 low** (magnet present) → recovery boot directly from NOR

### 6b — bootcmd

The full boot logic — hall sensor check, `bootcmd_recovery`, and `bootcmd_normal` — is defined in `board/bodybytes/bodybytes/bodybytes.env`, which the U-Boot build auto-detects and compiles into `default_environment[]`. The env partition is pre-programmed by `generate_nor_image.py` using the same file via `u-boot/tools/mkenvimage`, so the env is valid from the very first power-up. `fw_setenv` calls from OpenWrt read-modify-write the partition, preserving the boot commands across all sysupgrade cycles.

A blank or corrupt env partition always falls back to the compiled-in values, so the device can recover even if the env partition is erased. To manually persist a customisation after changing a variable at the U-Boot prompt:

```
saveenv
```

`gpio read 14` returns 0 (success/true in U-Boot `if`) when GPIO#14 is low — magnet present → recovery. `part start mmc 0 1 ks` stores the sector offset of GPT partition 1 (`kernel`) into `${ks}`; `mmc read` then loads 0x10000 sectors (32 MB) from there. `bootm` reads the actual image size from the uImage header and ignores trailing data. `0xBC060000` is the NOR memory-mapped address of the recovery partition (NOR physical `0x1C060000`, KSEG1 uncached alias).

`CONFIG_CMD_PART=y` and `CONFIG_EFI_PARTITION=y` must be set in `bodybytes_defconfig` for `part start` to work — see [uboot.md](uboot.md).

### 6c — Boot sequence

Normal boot:
1. U-Boot reads GPIO#14 → high → runs `bootcmd_normal`
2. Reads GPT partition 1 (`kernel`) from eMMC into RAM at `0x82000000`
3. `bootm 0x82000000` decompresses the regular kernel; the kernel's built-in minimal initramfs runs preinit which calls `mount_root`
4. `mount_root` (fstools) scans block devices for squashfs magic, finds p2 (`rootfs`), and mounts it read-only; then detects the `rootfs_data` GPT label on p3 and layers it at `/overlay` via overlayfs

Recovery boot:
1. U-Boot reads GPIO#14 → low → runs `bootcmd_recovery`
2. `bootm 0xBC060000` reads the uImage header from NOR, decompresses the initramfs kernel to RAM, and boots
3. OpenWrt runs entirely from RAM; eMMC is untouched and available for repair

---

## 7 — Hardware write protection

The W25Q512JV `/WP` pin (active-low) enables status-register-based write protection when asserted. For a production unit, pull `/WP` low after the final programming step and set Block Protect bits (BP3–BP0 in Status Register 1) to protect the entire array. The `SRP=1` bit (with `/WP` asserted) locks the status register itself against further changes.

For development boards, leave `/WP` high (unasserted) to allow re-programming via JTAG.
