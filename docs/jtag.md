# MT7628AN JTAG - J-Link EDU Mini V2

## Hardware

| Component | Details |
|-----------|---------|
| SoC | MediaTek MT7628AN - MIPS24KEc @ 575/580 MHz |
| JTAG adapter | Segger J-Link EDU Mini V2 |
| Crystal | 40 MHz external oscillator |
| RAM | 256 MB DDR2 |
| Boot flash | 64 MB SPI NOR (U-Boot + WiFi EEPROM) |
| App storage | 128 GB eMMC (Kingston EMMC128-IY29-5B111) |

## JTAG TAP

| Field | Value |
|-------|-------|
| IR length | 5 bits |
| Expected IDCODE | `0x1762824f` |
| Target type | `mips_m4k` (little-endian) |

## Wiring - Board Connector → J-Link EDU Mini V2

Reference: <https://kb.segger.com/9-pin_JTAG/SWD_connector>

| Board pos | Wire   | Test point | JTAG signal | SWD silkscreen | J-Link pin |
|-----------|--------|------------|-------------|----------------|------------|
| 1 (top)   | Red    | TP21       | VTref       | VTref          | 1          |
| 2         | Orange | TP22       | GND         | GND            | 3 or 5     |
| 3         | Yellow | TP18       | JTRST\_N    | nTRST          | 9          |
| 4         | Green  | TP17       | TCK         | SWCLK          | 4          |
| 5         | Blue   | TP16       | TMS         | SWDIO          | 2          |
| 6         | Violet | TP15       | TDI         | NC             | 8          |
| 7 (bot)   | White  | TP14       | TDO         | SWO            | 6          |

J-Link pin 10 (nRESET) is not connected - bodybytes does not expose PORST\_N on the JTAG header.

VTref (TP21) is a sense input - connect it to the 3.3 V rail but do not use it to power the board.

The MT7628 JTAG pins are multiplexed with Ethernet LED functions. The board must be strapped for JTAG mode so these pins are routed to the EJTAG interface rather than LEDs.

## Reset Signals

Only JTRST\_N is connected to the JTAG header on bodybytes. PORST\_N (system reset) is not wired to the JTAG connector.

| Signal | Board net | J-Link pin | What it resets |
|--------|-----------|------------|----------------|
| TRST (nTRST) | `JTAG_TRST` / `JTRST_N` | 9 | JTAG/EJTAG TAP and debug logic only |

TRST resets the JTAG TAP state machine and debug logic only - it does not reset the CPU or peripherals. Without PORST\_N, OpenOCD cannot force a clean CPU reset. Connect after power-on and use `halt` to stop the running CPU.

The OpenOCD reset configuration for bodybytes:

```tcl
reset_config trst_only
```

With `trst_only`, OpenOCD resets only the TAP when `reset` is issued. The CPU is not affected. Use `halt` (not `reset halt`) to stop the CPU after `init`.

---

## JTAG and SD/eMMC are mutually exclusive

`UART_TXD1` is the MT7628 `DBG_JTAG_MODE` bootstrap, sampled at power-on reset and latched into the **read-only** `SYSCFG0` bit 8:

| `UART_TXD1` at reset | `DBG_JTAG_MODE` | Effect |
|----------------------|-----------------|--------|
| high (pull-up)  | 1 | Normal — the five `EPHY_LED` pins are Ethernet LEDs, **JTAG disabled** |
| low (pull-down) | 0 | **JTAG enabled** — those pins become `TMS`/`TCK`/`TDI`/`TDO`/`TRST` |

The catch: on this SoC the SD/eMMC (SDXC) controller is muxed onto the **EPHY (Ethernet-PHY) pads** ("IoT" mode). Enabling JTAG **breaks the SD/eMMC bus** — the CMD line stops responding, so every command reads back all-zero and the card never enumerates (Linux loops on `no support for card's volts`; U-Boot's `mmc rescan` fails silently).

This is a **hardware** mutual-exclusion, not a software setting: it is latched into a read-only bit at reset, and every *writable* pin-mux register is identical in both modes (measured — `GPIO1_MODE`, `AGPIO_CFG`, `GPIO2_MODE` all byte-identical whether the strap is high or low). There is no register to flip at runtime to get both at once. **You cannot debug the CPU over JTAG and use SD/eMMC in the same boot.**

### Why: the SD bus doubles as the Andes JTAG

The MT7628 has **two processors**, and therefore two JTAG interfaces:

- **MIPS 24KEc** — the main application CPU (575/580 MHz) running BootROM → U-Boot → Linux. This is the one you debug during bring-up.
- **Andes "N9"** — a separate small coprocessor (Andes/AndeStar ISA) that runs the **Wi-Fi firmware** (802.11 MAC/baseband; the `mt7628_e1/e2.bin` blobs). You essentially never debug it.

| | MIPS JTAG | Andes JTAG |
|---|---|---|
| Debugs | MIPS 24KEc (main CPU) | Andes N9 (Wi-Fi coprocessor) |
| Debug arch | MIPS **EJTAG** | Andes **AICE / AndeStar** |
| Pins | `EPHY_LED0–4` (139–143) — where the J-Link connects | the **SDXC data pins** (`SD_MODE=3`) |
| Tooling | OpenOCD, `mips_m4k` (this doc) | Andes ICEman (rarely used) |

"JTAG" in this doc always means the **MIPS EJTAG** on the EPHY_LED pins. The Andes JTAG is collateral: you can't select just one, because both are gated by the single `DBG_JTAG_MODE` strap — and the Andes TAP's pins are the SD bus.

The overlap is in the datasheet register fields — two independent JTAG-vs-storage collisions, one strap that enables both:

- **`SYSCFG0` bit 8 `DBG_JTAG_MODE`** — "JTAG for MIPS **and Andes**". The single `UART_TXD1` strap enables *both* JTAG TAPs: the MIPS CPU's and the Andes (N9 Wi-Fi coprocessor) one.
- **`GPIO1_MODE` (`0x10000060`) bits [11:10] `SD_MODE`** — "SDXC GPIO mode: `0: SDXC`, `1: GPIO`, `2: UTIF`, **`3: Andes JTAG`**". The SDXC data pins *are* an alternate for the **Andes JTAG** interface — the same silicon.
- **`AGPIO_CFG` (`0x1000003C`) bits [20:17] `EPHY_GPIO_AIO_EN`** — selects EPHY P1–P4 as digital PADs (reset = digital); this is what routes SDXC onto the EPHY pads in the first place.

So the MIPS JTAG shares the **EPHY_LED** pins (where the J-Link connects), the **Andes JTAG shares the SD data pins** (`SD_MODE=3`), and `DBG_JTAG_MODE` enables both at once. Be precise about how much of this the datasheet actually proves:

- **Confirmed (datasheet):** the *sharing*. `SD_MODE = 3 = Andes JTAG` is a literal register-field value — those pins are designed to be either SDXC or the Andes debug interface. (Only the field description states it; the SD pin-share table tabulates just the `SDXC` and `GPIO` columns, so there is no per-pin JTAG-signal map.)
- **Inferred (measured, not documented):** the *runtime break*. With JTAG strapped on, `SD_MODE` still reads `0`/SDXC — the pins are **not** re-muxed to Andes JTAG — yet SD fails anyway. So the disturbance happens **below the mux**, in the shared debug/analog state the strap creates. That is why every writable register is identical in both modes and none of them undoes it, and why **time-sharing is the only option** (§ workflow below).

Net: the datasheet confirms the SD bus and the Andes debug interface are the same silicon, but stops short of explaining why enabling `DBG_JTAG_MODE` kills the bus while the mux still points at SDXC. This conflict is called out as a warning nowhere — in the datasheet or in vendor/OpenWrt docs — the register fields above are its only trace.

**Workflow — strap for JTAG only to flash/bring-up, then strap back to run storage:**
- **bodybytes board:** `UART_TXD1` carries a pull-up (GPIO / JTAG-off) for normal eMMC operation; only pull it low when actively using JTAG.
- **VoCore2 breakout:** `JP1` at "GPIO" (1-2) = SD/eMMC works; `JP1` at "JTAG" (2-3) = JTAG works — see [vocore2.md](vocore2.md).

So to test SD/eMMC in U-Boot: flash U-Boot to NOR over JTAG, then strap to GPIO mode, reboot, and drive U-Boot over the UART console.

---

## Step 1 - Connect and Halt at Reset

Enter the dev shell first - it sets `OPENOCD_SCRIPTS` so [`openocd/mt7628.cfg`](../openocd/mt7628.cfg) and its dependencies are found by name:

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

Start OpenOCD:

```sh
scripts/start_openocd_jlink.py --bodybytes
```

`trst_only` - bodybytes has no PORST\_N on the JTAG connector. OpenOCD can reset the TAP (JTRST\_N) but not the SoC. Power the board first, then connect OpenOCD. `halt` sends a debug request to the running CPU rather than forcing it to a clean reset entry point.

The script reads `reset_config` and `halt_cmd` from the board profile in `scripts/config.ini` (`[board:bodybytes]`: `trst_only` / `halt`), issues the halt command after `init`, and waits up to 5 s for the CPU to halt. Ctrl-C terminates OpenOCD directly.

Expected output:

```
jtag
adapter speed: 100 kHz

trst_only

Info : J-Link EDU Mini V2 compiled Dec 10 2025 15:50:17
Info : Hardware version: 2.00
Info : VTarget = 3.316 V
Info : clock speed 100 kHz
Info : JTAG tap: mt7628.cpu tap/device found: 0x1762824f (mfg: 0x127 (MIPS Technologies), part: 0x7628, ver: 0x1)
Info : starting gdb server for mt7628.cpu0 on 3333
Info : Listening on port 3333 for gdb connections
Info : Listening on port 6666 for tcl connections
Info : Listening on port 4444 for telnet connections
target halted in MIPS32 mode due to debug-request, pc: 0x9c...
```

### Verify halt state via telnet

In a second terminal:

```sh
telnet localhost 4444
```

```tcl
> targets
    TargetName         Type       Endian TapName            State
--  ------------------ ---------- ------ ------------------ -------
 0* mt7628.cpu0        mips_m4k   little mt7628.cpu         halted

> reg pc
pc (/32): 0x9c...    (somewhere in NOR or RAM, depending on where boot reached)

> mdw 0x10000000
0x10000000: 3637544d
```

Without PORST\_N, `halt` catches the CPU wherever it was executing - mid-U-Boot, mid-SPL, or in the BROM. The PC value is unpredictable but `mdw 0x10000000` should always read `0x3637544d` ("MT76") confirming the SoC is alive. Proceed with `cpu_pll_init` and `dram_init 256` regardless of where the CPU halted - those scripts are idempotent.

---

## Step 2 - Bootstrap PLL, DRAM, and boot U-Boot

With OpenOCD running and the CPU halted, run from the repo root (inside `nix develop .#uboot`):

```sh
scripts/boot_uboot_jtag.py --bodybytes
```

The script performs the full sequence automatically:

1. Halts the CPU and checks the PC against the reset vector (`0x9c000000`); logs a warning if it differs but continues
2. Reads `0x10000000` and confirms the MT7628 chip ID (`0x3637544d`); aborts if it does not match
3. Runs `cpu_pll_init` - locks the PLL to the 40 MHz crystal, sets CPU to 580 MHz
4. Raises adapter speed to 1000 kHz
5. Runs `dram_init` with `dram_size_mb` from the board profile (`[board:bodybytes]` in `scripts/config.ini`)
6. Configures the OpenOCD work area at `0xa0001000` for fast bulk transfers
7. Writes and reads back `0xdeadbeef` at `staging_addr` (`0x81000000` from `[jtag]` in `scripts/config.ini`) to verify DRAM
8. Loads `u-boot/u-boot.bin` to `uboot_ram_addr` (`0x80200000`) via `load_image`
9. Sets PC to `0x80200000` and resumes; then opens serial (`/dev/ttyUSB0`), interrupts U-Boot autoboot, and confirms the prompt with `version`

All steps are logged with timestamps. The script exits with an error if any step fails.

### Manual reference (telnet)

The equivalent manual sequence via `telnet localhost 4444`:

```tcl
halt
reg pc
mdw 0x10000000
cpu_pll_init
adapter speed 1000
dram_init 256
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
mww 0x81000000 0xdeadbeef
mdw 0x81000000
load_image u-boot/u-boot.bin 0x80200000 bin
reg pc 0x80200000
resume
```

For the PLL and DRAM details see the comments in [`openocd/mt7628.cfg`](../openocd/mt7628.cfg) and [`openocd/memc.tcl`](../openocd/memc.tcl).

---

## Step 3 - Flash NOR

Continue with [flashing.md §4b](flashing.md#4b--full-nor-programming-first-time--production).

---

## Flash Map

See [flashing.md §1a](flashing.md#1a--partition-map) for the full NOR partition map and [flashing.md §5a](flashing.md#5a--gpt-partition-layout) for the eMMC GPT layout.

SPI NOR is at physical `0x1c000000`, accessible to the CPU at `0x9c000000` (KSEG0 cached) or `0xbc000000` (KSEG1 uncached). Use `0xbc000000 + <nor_offset>` for direct JTAG memory reads (e.g. `mdw 0xbc050000 4` to read the first 16 bytes of the factory partition).

---

## Troubleshooting

| Symptom | Likely cause / next check |
|---------|---------------------------|
| `JTAG tap: ... UNEXPECTED` | Wrong IDCODE - check target config and TDI/TDO wiring |
| `Timed out waiting for device to appear` | VTref missing or target unpowered |
| `Error: JTAG scan chain interrogation failed` | TCK/TMS/TDO wiring, target power, or reset state problem |
| `tap: mt7628.cpu enabled (idcode 0x00000000)` | TDO open, target unpowered, or TAP held in reset |
| `halt` times out | CPU may be held in reset, JTAG mode may not be strapped, or EJTAG pins muxed to LEDs |
| `targets` shows `running` after a previous clean halt | Check for GDB/IDE resume, external reset, watchdog, or stale register reads |
| PC remains `0x9c000000` after `resume; sleep 100; halt` | CPU not progressing from NOR entry - check clock, SPI flash activity, and boot straps |
| `halt` times out after `init` | Board not powered, JTAG mode not strapped (TXD1 must be low), or EPHY LED pins not muxed to JTAG |
