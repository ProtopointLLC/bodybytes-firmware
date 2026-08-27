# MT7628AN JTAG - J-Link EDU Mini V2

JTAG is physical, low-level access outside the normal software security boundary — see [security.md - JTAG and direct hardware access](security.md#jtag-and-direct-hardware-access).

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

## OpenOCD: SRST wiring decides which mode you get

Which reset lines are wired decides which EJTAG transport works afterwards. Check which column you are in before debugging anything else.

| | **SRST wired** | **TRST only** |
|---|---|---|
| Board profile | `hardware_reset = true` | `hardware_reset = false` |
| `reset_config` | `trst_and_srst` | `trst_only` |
| Attach lands at | reset vector, `0x9c000000` | arbitrary PC in running firmware |
| FASTDATA bulk write | works, ~59 KiB/s | **disabled** - PRACC fallback, ~2 KiB/s |
| OpenOCD | stock 0.12.0 is correct | needs `mips32 ejtag_all_quirk on` |
| U-Boot (484 KB) to DRAM | ~8 s | ~230 s |

**Prefer SRST wherever the board exposes it** - it is stock, and ~29x faster for bulk transfers. **bodybytes is TRST-only**: `PORST_N` is not brought out to the JTAG header (see [§Reset Signals](#reset-signals)), so this board always takes the second column.

Without SRST, `halt` catches the CPU in a state where selecting the EJTAG CONTROL, ADDRESS and DATA registers *individually* corrupts TAP state. The dev shell's OpenOCD can route halted-mode access through the combined 96-bit ALL register instead, at the cost of FASTDATA. It is **off by default**, so SRST-wired debugging is unaffected:

```
mips32 ejtag_all_quirk [on|off]
```

[`start_openocd_jlink.py`](../scripts/start_openocd_jlink.py) sets it from the board profile and prints the choice at startup:

```
[Info] hardware_reset : False
[Info] reset_config   : trst_only
[Info] ejtag_all_quirk: on (no SRST - ALL register, FASTDATA disabled)
```

With the quirk on, two things are expected and are **not** errors:

- `Fastdata access Failed` / `Falling back to non-bulk write` on every `load_image`.
- Bulk writes at ~2 KiB/s, so loading U-Boot to DRAM takes ~4 minutes instead of ~8 seconds. For multi-megabyte payloads use [`flash_nor_images.py --ymodem`](flashing.md#4c-2---serial-only-update-over-ymodem-no-jtag) rather than JTAG - the ~13 MB OpenWrt recovery image would take roughly 1.8 hours over JTAG in this mode.

Why the workaround is needed, the per-profile attach sequences, and how to change the OpenOCD it lives in: [§MT7628 EJTAG workaround](#mt7628-ejtag-workaround---background).

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

J-Link pin 10 (nRESET) is not connected — bodybytes does not expose PORST\_N on the JTAG header.

VTref (TP21) is a sense input — connect it to the 3.3 V rail but do not use it to power the board.

The JTAG pins are multiplexed with Ethernet LED functions; the board must be strapped for JTAG mode before connecting (see [§JTAG and SD/eMMC](#jtag-and-sdemmc-are-mutually-exclusive)).

## Reset Signals

Only JTRST\_N is connected to the JTAG header on bodybytes. PORST\_N (system reset) is not wired to the JTAG connector.

| Signal | Board net | J-Link pin | What it resets |
|--------|-----------|------------|----------------|
| TRST (nTRST) | `JTAG_TRST` / `JTRST_N` | 9 | JTAG/EJTAG TAP and debug logic only |

TRST resets only the TAP — not the CPU or peripherals. Without PORST\_N, connect after power-on and use `halt` to stop the CPU.

```tcl
reset_config trst_only
```

With `trst_only`, `reset` affects only the TAP. Use `halt` (not `reset halt`) after `init`.

---

## JTAG and SD/eMMC are mutually exclusive

`UART_TXD1` is the MT7628 `DBG_JTAG_MODE` bootstrap, sampled at power-on reset and latched into the **read-only** `SYSCFG0` bit 8:

| `UART_TXD1` at reset | `DBG_JTAG_MODE` | Effect |
|----------------------|-----------------|--------|
| high (pull-up)  | 1 | Normal — the five `EPHY_LED` pins are Ethernet LEDs, **JTAG disabled** |
| low (pull-down) | 0 | **JTAG enabled** — those pins become `TMS`/`TCK`/`TDI`/`TDO`/`TRST` |

The catch: SD/eMMC (SDXC) runs on the **EPHY pads** ("IoT" mode). Enabling JTAG **breaks the SD/eMMC bus** — CMD stops responding and the card never enumerates.

This is a **hardware** mutual-exclusion: latched at reset into a read-only bit, with no software workaround. **You cannot use JTAG and SD/eMMC in the same boot.**

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

So the MIPS JTAG shares the **EPHY_LED** pins (where the J-Link connects), the **Andes JTAG shares the SD data pins** (`SD_MODE=3`), and `DBG_JTAG_MODE` enables both at once. The disturbance happens below the mux layer — every writable pin-mux register (`GPIO1_MODE`, `AGPIO_CFG`, `GPIO2_MODE`) is identical whether the strap is high or low, so there is no register to flip at runtime to get both. **Time-sharing is the only option** (§ workflow below).

**Workflow — strap for JTAG only to flash/bring-up, then strap back to run storage:**
- **bodybytes board:** `UART_TXD1` carries a pull-up (GPIO / JTAG-off) for normal eMMC operation; only pull it low when actively using JTAG.
- **VoCore2:** see [vocore2.md §Breakout Board Setup](vocore2.md#breakout-board-setup).

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

The script reads `hardware_reset` from the board profile in [`scripts/config.ini`](../scripts/config.ini) (`[board:bodybytes]`: `false`, since there's no PORST\_N to drive) and derives `reset_config trst_only` plus a plain `halt` after `init`, waiting up to 5 s for the CPU to halt. Ctrl-C terminates OpenOCD directly.

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

Without PORST\_N, `halt` catches the CPU mid-execution — the PC is unpredictable. `mdw 0x10000000` should always return `0x3637544d` ("MT76") confirming the SoC is alive. The PLL/DRAM scripts are idempotent; proceed regardless of where the CPU halted.

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
5. Runs `dram_init` with `dram_size_mb` from the board profile (`[board:bodybytes]` in [`scripts/config.ini`](../scripts/config.ini))
6. Configures the OpenOCD work area at `0xa0001000` for fast bulk transfers
7. Writes and reads back `0xdeadbeef` at `staging_addr` (`0x81000000` from `[jtag]` in [`scripts/config.ini`](../scripts/config.ini)) to verify DRAM
8. Loads [`u-boot/u-boot.bin`](../u-boot/u-boot.bin) to `uboot_ram_addr` (`0x80200000`) via `load_image`
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

Continue with [flashing.md §4b](flashing.md#4b---full-nor-programming-first-time--production).

---

## Flash Map

See [flashing.md §1a](flashing.md#1a---partition-map) for the full NOR partition map and [flashing.md §5a](flashing.md#5a---gpt-partition-layout) for the eMMC GPT layout.

SPI NOR is at physical `0x1c000000`, accessible to the CPU at `0x9c000000` (KSEG0 cached) or `0xbc000000` (KSEG1 uncached). Use `0xbc000000 + <nor_offset>` for direct JTAG memory reads (e.g. `mdw 0xbc050000 4` to read the first 16 bytes of the factory partition).

---

## MT7628 EJTAG workaround - background

Everything needed to *use* JTAG is [above](#openocd-srst-wiring-decides-which-mode-you-get). This section covers what the modified OpenOCD does, how the two attach sequences are built, and the constraints anyone editing it has to respect.

### Where the code lives

`flake.nix` builds OpenOCD from a fork, pinned by commit rather than by branch:

    https://github.com/ProtopointLLC/bobybytes-openocd   branch: bodybytes

The branch is exactly the `v0.12.0` tag plus **one** commit. Keeping it to a single commit is deliberate - it stays readable as a diff against a known-good release, and `git diff v0.12.0..bodybytes` is the whole change.

Building from git rather than the release tarball means `./configure` has to be bootstrapped and the `jimtcl` / `libjaylink` submodules fetched; `flake.nix` handles both (`autoreconfHook`, `fetchSubmodules = true`). The reported version becomes `0.12.0-snapshot` instead of `0.12.0` - cosmetic, and the expected result of building a checkout.

### What the change does

Two defects on the no-SRST path, one fixed and one refused:

| | Symptom | Resolution |
|---|---|---|
| **Standalone EJTAG registers** | Selecting CONTROL / ADDRESS / DATA individually while halted corrupts TAP state | **Fixed** - route every halted-mode transaction through the 96-bit ALL register (`EJTAG_INST_ALL`, IR `0x0b`), so `wait_for_pracc_rw()` is never reached |
| **FASTDATA** | Bulk writes report complete success while writing nothing to DRAM | **Refused** - `mips32_pracc_fastdata_xfer()` returns `ERROR_TARGET_RESOURCE_NOT_AVAILABLE` so `mips_m4k_bulk_write_memory()` falls back to slow-but-correct PRACC writes |

Both are gated on `ejtag_all_quirk`. With it off, every code path is stock, FASTDATA included.

### Attach sequences differ, and they are not interchangeable

The two modes need genuinely different OpenOCD startup sequences, so `start_openocd_jlink.py` emits one or the other rather than a shared one:

```
SRST wired                     TRST only
----------                     ---------
                               mips32 ejtag_all_quirk on
                               mt7628.cpu0 configure -defer-examine
init                           init
                               poll off
                               adapter assert trst / sleep / deassert
                               mt7628.cpu0 arp_examine
reset halt                     halt
poll                           sleep 100
halt
wait_halt 5000                 wait_halt 5000
```

Without SRST, examination has to be deferred past `init` and run by hand after a manual TRST pulse - the CPU is running and examining it too early does not stick.

### `reset halt` can report success without halting

On the SRST path, `reset halt` prints a convincing halt line while leaving the CPU **out of Debug Mode**. EJTAG CONTROL comes back with `BRKST` (bit 3) clear, but OpenOCD has already cached `target->state` as halted:

```
> reset halt
target halted in MIPS32 mode due to debug-request, pc: 0x87f806a8
> targets
 0* mt7628.cpu0   mips_m4k   little   mt7628.cpu   running      <- not halted
```

with `CONTROL = 0x0000c000` - `PROBEN` set, `BRKST` clear.

The cached state is what makes this bite. Every later `halt` no-ops ("target was already halted"), so nothing recovers it, and every memory access fails:

```
> mdw 0x10000000
                                    <- no output at all
> read_memory 0x10000000 32 1
read_memory: read at 0x10000000 with width=32 and count=1 failed
```

Note that **`mdw` swallows the error** and prints nothing, which makes this much harder to recognise than it should be. Use `read_memory` when diagnosing - it reports the failure.

The fix is one explicit `poll` after `reset halt`: it re-reads `BRKST` and corrects the cached state to `running`, so the `halt` that follows is a real one. Afterwards `CONTROL = 0x4004c008` (`BRKST` set) and memory reads work:

```
> mdw 0x10000000
0x10000000: 3637544d
```

Check the PC too. After `reset halt` it must be `0x9c000000`; a PC in DRAM (`0x8xxxxxxx`) means SRST is not actually resetting the SoC despite the profile claiming it is - a wiring problem, not a software one. `boot_uboot_jtag.py` warns and continues in that case.

### `-defer-examine` and `reset halt` are mutually exclusive

The deferral the TRST-only path needs must never leak onto the SRST path. `arp_reset` un-examines any deferred target *before* asserting reset:

```c
	if (target->defer_examine)
		target_reset_examined(target);
```

and `mips_m4k_assert_reset()` then refuses to drive SRST at all:

```
Warn : Reset is not asserted because the target is not examined.
Warn : Use a reset button or power cycle the target.
Debug: Command 'reset' failed with error code -4
```

Because the un-examine happens *inside* the same `arp_reset` call, no amount of manual `arp_examine` beforehand survives it - `reset halt` fails every time. This is why `-defer-examine` is applied per-profile by the launcher instead of unconditionally in [`mt7628.cfg`](../openocd/mt7628.cfg).

### Invariants

Constraints the ALL-register path depends on. Breaking any of them reintroduces the corruption it exists to avoid, so do not "simplify" them without hardware evidence.

**IR selects must be their own adapter transaction.** Batching an IR select into the same `jtag_execute_queue()` as the following DR scan reproduces exactly the corruption the ALL register exists to avoid. `mt7628_pracc_force_all_ir()` flushes the select on its own and forces the transition through BYPASS rather than trusting OpenOCD's cached `tap->cur_instr`, which is not reliable here.

**Every PRACC instruction needs an ALL=0 completion scan.** That second scan also supplies a NOP for the next sequential fetch, so a PRACC program runs NOP-interleaved and the PC advances by **8 bytes per supplied instruction**, not
4. Every address check in the executor accounts for this.

**Never touch CONTROL/ADDRESS/DATA individually while halted.** This is the entire reason the fork exists.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `JTAG tap: ... UNEXPECTED` | Wrong IDCODE — check target config and TDI/TDO wiring |
| `Timed out waiting for device to appear` | VTref missing or target unpowered |
| `Error: JTAG scan chain interrogation failed` | TCK/TMS/TDO wiring, target power, or reset state |
| `tap: mt7628.cpu enabled (idcode 0x00000000)` | TDO open, target unpowered, or TAP held in reset |
| `halt` times out | JTAG mode not strapped (TXD1 must be low), or EPHY LED pins not muxed to JTAG |
| `targets` shows `running` after clean halt | GDB/IDE resume, external reset, or watchdog |
| `mdw` prints nothing; `read_memory` says "target not halted" | `reset halt` cached a halted state without entering Debug Mode — see [§`reset halt` can report success without halting](#reset-halt-can-report-success-without-halting) |
| PC stuck at `0x9c000000` after resume | CPU not progressing — check clock, SPI flash activity, and boot straps |
