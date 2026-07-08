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
| `0x060000` | `0x3FFFFFF` | 63.625 MB | `recovery` | RO | OpenWrt sysupgrade image for eMMC restore |

Total: 64 MB (`0x4000000`)

### 1b — Partition details

**`u-boot` (0x000000, 256 KB)**

Stores `u-boot-with-spl.bin`: SPL (≤64 KB) followed by LZMA-compressed U-Boot proper. At power-up the MT7628 boot ROM reads NOR offset 0 and executes the SPL, which initialises the PLL and DDR2, decompresses U-Boot to `0x80200000`, and jumps there. Current binary is ~173 KB; 83 KB headroom remains.

**`u-boot-env` (0x040000, 64 KB)**

One 64 KB erase block. `CONFIG_ENV_OFFSET=0x040000`, `CONFIG_ENV_SIZE=0x1000` (4 KB active payload), `CONFIG_ENV_SECT_SIZE=0x10000`. U-Boot erases and rewrites this block on `saveenv`. Never programmed at manufacturing time — U-Boot creates it on first `saveenv`.

**`factory` (0x050000, 64 KB)**

Holds a 1 KB WiFi EEPROM blob at the start; remaining 63 KB is 0xFF. The DTS exposes the first 1 KB as an nvmem cell (`eeprom@0`) consumed by `&wmac`. Never erase this partition during firmware updates — it is marked `read-only` in the DTS. See §2 for EEPROM format details.

**`recovery` (0x060000, 63.625 MB)**

OpenWrt squashfs sysupgrade image, stored read-only. At factory reset U-Boot reads this image and writes it to eMMC sector 0. Spans the W25Q512JV EAR (Extended Address Register) boundary at 16 MB; `CONFIG_SPI_FLASH_BAR=y` makes U-Boot cross 16 MB boundaries transparently:

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

Produces `nor_image.bin` (64 MB) containing:
- U-Boot from `u-boot/u-boot-with-spl.bin`
- Factory EEPROM with chip ID + MAC at `0x050000`
- OpenWrt sysupgrade from `openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin`
- All gaps filled with `0xFF`

The script prints the exact `sf` commands needed to program each region from U-Boot. Override default paths with `--uboot`, `--openwrt`, and `--out`.

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

Bodybytes has no Ethernet; the only way to transfer `nor_image.bin` is via JTAG. Load it into RAM while U-Boot idles at its prompt (no halt needed):

```tcl
load_image nor_image.bin 0x80000000 bin
```

Then run the `sf` commands printed by `generate_nor_image.py` at the U-Boot console (example for a ~10 MB OpenWrt image):

```
sf probe
sf erase 0 0x50000
sf write 0x80000000 0 0x<uboot_size>
sf erase 0x50000 0x10000
sf write 0x80050000 0x50000 0x400
sf erase 0x60000 0x<recovery_size_aligned>
sf write 0x80060000 0x60000 0x<recovery_size>
```

The env sector (`0x040000`) is not programmed — U-Boot creates it on first `saveenv`.

Alternatively, write `nor_image.bin` directly with a SPI flash programmer (e.g. `flashrom`) without involving U-Boot at all.

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

This erases u-boot + env (preserving factory at `0x050000`) and writes the new binary. Power-cycle to boot from the updated NOR.

### 4d — Verify NOR boot

Power-cycle the board (no JTAG required). The MT7628 boot ROM reads NOR offset 0, executes the SPL, which initialises PLL and DRAM, decompresses U-Boot to `0x80200000`, and transfers control.

U-Boot should appear on **UART2 (TP19/TP20)** at **115200 8N1** without any JTAG assistance. Successful boot confirms: SPL runs, DRAM initialisation succeeds, NOR image layout is correct, U-Boot proper loads.

---

## 5 — Write OpenWrt to eMMC

Pre-calculate the block count on the host (512 bytes per block):

```sh
img=openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin
blkcount=$(( ($(stat -c%s "$img") + 511) / 512 ))
printf "block count: 0x%x\n" $blkcount
```

Load the image into RAM via OpenOCD (halt CPU first to avoid DRAM conflict during large transfers):

```tcl
halt
load_image openwrt/bin/targets/ramips/mt76x8/openwrt-ramips-mt76x8-bodybytes_bodybytes-squashfs-sysupgrade.bin 0x82000000 bin
resume
```

`0x82000000` keeps the image above U-Boot's footprint. Note the byte count from `load_image`.

Write to eMMC from the U-Boot console:

```
mmc dev 0
mmc write 0x82000000 0 <block_count_hex>
```

---

## 6 — Boot configuration

Set `bootcmd` once from the U-Boot console:

```
setenv bootcmd 'mmc dev 0; mmc read 0x82000000 0 0x10000; bootm 0x82000000'
saveenv
boot
```

The kernel command line (rootfs location, overlayfs) will be refined once a first boot is achieved. `bootargs = "console=ttyS2,115200"` from the DTS is the baseline; U-Boot can extend it with `setenv bootargs`.

---

## 7 — Hardware write protection

The W25Q512JV `/WP` pin (active-low) enables status-register-based write protection when asserted. For a production unit, pull `/WP` low after the final programming step and set Block Protect bits (BP3–BP0 in Status Register 1) to protect the entire array. The `SRP=1` bit (with `/WP` asserted) locks the status register itself against further changes.

For development boards, leave `/WP` high (unasserted) to allow re-programming via JTAG.
