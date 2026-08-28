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
| OpenOCD | stock 0.12.0 is correct | needs `mips32 ejtag_all_quirk on` |
| FASTDATA bulk write | stock path | unsupported, falls back to PRACC |
| U-Boot (484 KB) to DRAM | ~8 s | **~3.5 min** |

**bodybytes is TRST-only**: `PORST_N` is not brought out to the JTAG header (see [§Reset Signals](#reset-signals)), so this board always takes the second column.

Without SRST, `halt` catches the CPU in a state where selecting the EJTAG CONTROL, ADDRESS and DATA registers *individually* returns corrupt values. The dev shell's OpenOCD routes halted-mode access through the combined 96-bit ALL register instead, and re-selects the instruction register on every access rather than trusting OpenOCD's cache. Both are **off by default**, so SRST-wired debugging is unaffected:

```
mips32 ejtag_all_quirk [on|off]
```

There is one switch, not several. `off` is exactly stock OpenOCD, correct on this part when SRST is wired. `on` selects the whole TRST-only path together: ALL-register routing, IR re-selected on every access, and FASTDATA refused so bulk writes fall back to PRACC.

[`start_openocd_jlink.py`](../scripts/start_openocd_jlink.py) sets it from the board profile and prints the choice at startup:

```
[Info] hardware_reset : False
[Info] reset_config   : trst_only
[Info] ejtag_all_quirk: on (no SRST - ALL register, FASTDATA off)
```

Bulk writes run at ~2.3 KiB/s with the adapter on a native USB port, so the 484 KB U-Boot takes ~3.5 minutes. `Fastdata access Failed` followed by `Falling back to non-bulk write` is **expected** on this path and is not a fault: OpenOCD tries FASTDATA, the quirk refuses it, and PRACC writes do the work. Every load is CRC32-checked afterwards - see [§Verify every bulk write](#verify-every-bulk-write).

PRACC writes are latency-bound, not bandwidth-bound: about eight USB round trips per 32-bit word, with only a few bytes in each. Throughput therefore tracks USB round-trip latency rather than link speed, and a virtualised USB stack costs a lot. Measured with the same J-Link and board: **~2.3 KiB/s** on a native port, **~0.9 KiB/s** through VirtualBox with an xHCI controller, and **~0.12 KiB/s** through VirtualBox with OHCI - 3.5 minutes, 9 minutes and over an hour for the same 484 KB. If you run this in a VM, give it an xHCI (USB 3.0) controller: the J-Link is a full-speed device, and an EHCI controller hands full-speed devices to its companion OHCI, so enabling USB 2.0 alone does not help.

Because that range is so wide, the scripts bound **silence rather than duration**: OpenOCD reports progress every ~2 s, so `load_image` may take an hour without being a timeout, while a target that stops reporting fails after `LOAD_IDLE_SECONDS`. Do not replace this with a fixed timeout computed from a throughput guess - no single figure is right across native and virtualised USB.

For multi-megabyte payloads use [`flash_nor_images.py --ymodem`](flashing.md#4c-2---serial-only-update-over-ymodem-no-jtag). On the TRST-only path JTAG is the slow option: at ~2.3 KiB/s the ~13 MB OpenWrt recovery image would take over an hour, so JTAG is for getting U-Boot into DRAM, and YMODEM carries anything large after that.

On the TRST-only path the launcher then resets the SoC over JTAG alone and re-enters at the reset vector - what an SRST-wired board gets from `reset halt`, with no reset wire, no working firmware and no valid NOR required. See [§Resetting without a reset line](#resetting-without-a-reset-line).

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
4. Raises adapter speed to 1000 kHz, then re-selects the IR (see below)
5. Runs `dram_init` with `dram_size_mb` from the board profile (`[board:bodybytes]` in [`scripts/config.ini`](../scripts/config.ini))
6. Configures the OpenOCD work area at `0xa0001000`, which the CRC32 check in step 9 runs from
7. Writes and reads back `0xdeadbeef` at `staging_addr` (`0x81000000` from `[jtag]` in [`scripts/config.ini`](../scripts/config.ini)) to verify DRAM
8. Loads [`u-boot/u-boot.bin`](../u-boot/u-boot.bin) to `uboot_ram_addr` (`0x80200000`) via `load_image`
9. CRC32s the image in DRAM with `verify_image_checksum` and aborts on mismatch
10. Sets PC to `0x80200000` and resumes; then opens serial (`/dev/ttyUSB0`), interrupts U-Boot autoboot, and confirms the prompt with `version`

All steps are logged with timestamps. The script exits with an error if any step fails.

### Manual reference (telnet)

The equivalent manual sequence via `telnet localhost 4444`:

```tcl
halt
reg pc
mdw 0x10000000
cpu_pll_init
adapter speed 1000
irscan mt7628.cpu 0x1f
dram_init 256
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
mww 0x81000000 0xdeadbeef
mdw 0x81000000
load_image u-boot/u-boot.bin 0x80200000 bin
verify_image_checksum u-boot/u-boot.bin 0x80200000 bin
reg pc 0x80200000
resume
```

**`irscan mt7628.cpu 0x1f` after every `adapter speed` change is mandatory, not cosmetic.** Changing adapter speed resets the TAP, which reloads `IDCODE` into the instruction register. OpenOCD does not invalidate `tap->cur_instr` on that path, so `mips_ejtag_set_instr()` believes the IR still holds whatever it last selected and **skips the re-scan** - every subsequent EJTAG access then reads the `IDCODE` register instead of the one it asked for. Selecting BYPASS by hand puts the cache and the hardware back in agreement and forces the next access to scan the IR for real.


**The work area must be configured after `dram_init`, not in [`mt7628.cfg`](../openocd/mt7628.cfg).** `mips32_checksum_memory()` uploads its CRC32 loop there and runs it on the target, so without one `verify_image_checksum` cannot run and the load goes unverified. OpenOCD allocates it lazily, so declaring it earlier gains nothing; it would only let something run out of dead DRAM before `dram_init`. `0xa0001000` is KSEG1 (uncached) at the bottom of DRAM, clear of both the U-Boot load address and the staging area.

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

`flake.nix` builds OpenOCD from a fork, pinned by commit:

    https://github.com/ProtopointLLC/bobybytes-openocd   branch: bodybytes

The branch is the `v0.12.0` tag plus a few self-contained commits, so `git diff v0.12.0..bodybytes` reads as one change against a known-good release. Building from git means `./configure` is bootstrapped and the `jimtcl` / `libjaylink` submodules fetched; `flake.nix` handles both. The version reports as `0.12.0-snapshot`, which is just what building a checkout does.

### The defect

**EJTAG in one paragraph.** MIPS has no memory-mapped debug bus. To read a word, the probe halts the core and *feeds it instructions one at a time*: the core fetches from a magic address range (`dmseg`, based at `0xff200000`), and each fetch appears to the probe as a "processor access" waiting to be serviced. The probe reads three registers to see what the core wants - CONTROL (access pending? read or write?), ADDRESS (from where?) and DATA (the payload) - supplies an instruction, and repeats. This is PRACC, and every memory read, register read and `load_image` on this target runs on it.

Those three registers can be selected individually, or together through a combined 96-bit **ALL** register. Stock OpenOCD uses the individual ones.

**On MT7628AN without a wired SRST, the individually-selected CONTROL register does not read correctly.** Its low half is right; the upper half reads as ones:

```
good  0x4004c008
bad   0xffffc008
```

That is provably not the register. The ECR has bits hardwired to zero (28:24, 23, 17, and 11:4). In the bad read the hardwired zeros *below* bit 16 are correctly zero and the ones *above* it read as one - no register can do that, so bits 16 and up are not coming from the ECR.

The upper half is where everything PRACC depends on lives: `PrAcc` (access pending), `PRnW` (read or write), `Psz` (size), `Rocc` (reset occurred). Read as ones, the executor takes every pending fetch for a store and reports `unexpected write at address ff2002xx` until it gives up.

**The ALL register is unaffected.** Same core state, same moment: 116 corrupt reads via the individual registers, 0 via ALL.

Why the individual selects fail and ALL does not is **not explained**. Treat it as an observed property of this part.

### How the workaround follows

`mips32 ejtag_all_quirk on` switches four things together.

**1. Route halted-mode access through ALL.** Direct consequence of the above.

**2. Re-select the instruction register on every access.** This TAP does not reliably stay on the last selected instruction, and `mips_ejtag_set_instr()` normally skips the IR scan when `tap->cur_instr` already matches. When that happens OpenOCD scans whatever register the TAP actually holds - reading `0xffff824f` from what it believes is CONTROL, whose low half is `IDCODE[15:0]` for this part (`0x1762824f`).

**3. Two scans per instruction.** Each supplied instruction needs a second, zero-valued ALL scan, which services the next sequential fetch with a NOP. PRACC programs therefore run NOP-interleaved and **the PC advances by 8 bytes per supplied instruction, not 4**. Every address check in the executor accounts for this; stock's `fetch_addr += 4` desynchronises immediately.

**4. Steer the core back to `PRACC_TEXT`.** There is no memory behind dmseg: the core executes whatever the probe hands it and its PC only ever advances, so a core that has drifted off `PRACC_TEXT` (`0xff200200`) cannot return on its own - the probe has to feed it a branch. PRACC programs are position-dependent, assembled assuming execution starts there, and after a reset entry the core is one instruction past it. `mt7628_pracc_jump_to_text()` does this, bounded to three attempts like stock's `mips32_pracc_clean_text_jump()`.

**FASTDATA cannot be rescued the same way, and is refused.** Routing through ALL works for CONTROL, ADDRESS and DATA because the ALL register is a combined view of those three. FASTDATA has no such alias, and the FASTDATA register does not service processor accesses on this part: a scan against it leaves the transfer handler's read still pending at `FASTDATA_AREA`, so the handler never receives a word. `mips32_pracc_fastdata_xfer()` therefore returns `ERROR_TARGET_RESOURCE_NOT_AVAILABLE` under the quirk, and `mips_m4k_bulk_write_memory()` falls back to PRACC writes.

### What it costs

`ejtag_all_quirk off` is stock OpenOCD byte for byte, and is the right choice when SRST is wired.

With it on, bulk writes lose FASTDATA and run over PRACC instead: ~2.3 KiB/s against the ~70 KiB/s an SRST-wired board gets, so 484 KB takes ~3.5 minutes rather than ~7 s. That is the whole price. No state checks are given up: an ALL scan can peek without consuming by writing `PrAcc` as 1 instead of 0.

### Verify every bulk write

**`load_image` reporting success does not prove the image landed.** Its byte count and KiB/s come from what OpenOCD queued, not from what the target accepted, and the FASTDATA path cannot tell the difference: `mips_ejtag_fastdata_scan()` leaves the SPRACC acknowledgement's `in_value` NULL, so it always returns `ERROR_OK` whether or not the core consumed the word. A silent no-op load is therefore indistinguishable from a real one by its output alone.

[`boot_uboot_jtag.py`](../scripts/boot_uboot_jtag.py) closes that gap: it CRC32s the image in DRAM after every load and refuses to start the core on a mismatch. `verify_image_checksum <file> <addr> bin` uploads a CRC loop into the work area and runs it on the target, so it costs seconds - ~4 s for 484 KB, against ~3.5 minutes for the load itself. Do the same after any hand-driven `load_image`.

### Attach sequences differ, and they are not interchangeable

The two modes need different startup sequences, so `start_openocd_jlink.py` emits one or the other:

```
SRST wired            TRST only, pass 1        TRST only, pass 2
one process           reset the SoC            attach to the reset core
-----------           ---------------------    ------------------------
                      mips32 ejtag_all_quirk on
                      mt7628.cpu0 configure
                          -defer-examine
init                  init                     init
                      poll off
                      adapter assert trst
                          / sleep / deassert
                      mt7628.cpu0 arp_examine
reset halt            halt / wait_halt 2000
poll                  irscan mt7628.cpu 0x0c   poll
halt                  mww 0xb0000034 0x1       halt
wait_halt 5000        shutdown                 wait_halt 5000
```

Pass 2 also enables the quirk, and omits `-defer-examine`: examine only reads IDCODE/IMPCODE, and deferring would block the `poll` that performs the debug entry.

Without SRST, examination has to be deferred past `init` and run by hand after a manual TRST pulse - the CPU is running, and examining it too early does not stick.

`-defer-examine` must never leak onto the SRST path: `arp_reset` un-examines a deferred target *before* asserting, inside the same call, so no amount of manual `arp_examine` beforehand survives it and `reset halt` fails every time:

```
Warn : Reset is not asserted because the target is not examined.
```

That is why the launcher applies it per-profile rather than [`mt7628.cfg`](../openocd/mt7628.cfg) applying it unconditionally.

### `reset halt` can report success without halting

On the SRST path, `reset halt` prints a convincing halt line while leaving the CPU **out of Debug Mode** - EJTAG CONTROL comes back with `BRKST` (bit 3) clear, but OpenOCD has already cached `target->state` as halted:

```
> reset halt
target halted in MIPS32 mode due to debug-request, pc: 0x87f806a8
> targets
 0* mt7628.cpu0   mips_m4k   little   mt7628.cpu   running      <- not halted
```

Every later `halt` then no-ops as "already halted", and memory access fails. **`mdw` swallows the error and prints nothing**; use `read_memory` when diagnosing, which reports it.

One explicit `poll` after `reset halt` fixes it: it re-reads `BRKST`, corrects the cached state, and the following `halt` is a real one.

Check the PC too. After `reset halt` it must be `0x9c000000`; a PC in DRAM (`0x8xxxxxxx`) means SRST is not actually resetting the SoC despite the profile claiming it is - a wiring problem, not a software one.

### Resetting without a reset line

`PORST_N` is the only reset input that works regardless of software state, and it is not routed to the JTAG header on bodybytes. Everything else needs something that may already be broken:

| | Why not |
|---|---|
| `ECR.PrRst` (bit 16) | Latches and reads back `1`, resets nothing. The bit exists but is not wired on this SoC |
| U-Boot `reset` / Linux `reboot` | Needs working firmware |
| `EJTAGBOOT` alone | Only changes what the *next* reset does; it cannot cause one |
| `TRST` | Resets the TAP only - and clears the `EJTAGBOOT` arming |

`RSTCTL.SYS_RST` works and only needs PRACC, which `ejtag_all_quirk` supplies from any software state. [`start_openocd_jlink.py`](../scripts/start_openocd_jlink.py) chains the two inline, in reset pass 1:

1. Halt via the quirk path. Works from any state, just slowly.
2. `irscan mt7628.cpu 0x0c` - `EJTAGBOOT`. A TAP instruction, so **no EJTAG Control write has to succeed** for it to take. It makes the next reset enter Debug Mode at the reset vector with `ProbEn`/`ProbTrap` set by hardware.
3. Set bit 0 of `RSTCTL` (`0xb0000034`) - `SYS_RST`, "whole system reset ... except for power-on CR". Being a *warm* reset it does not reset the TAP, so the step-2 arming survives. A plain `mww`, not a read-modify-write: the latter runs two PRACC programs and doubles the transactions in flight when the SoC disappears underneath them. The write never completes cleanly, because the SoC resets underneath the access servicing it; that error is the expected outcome.
4. Exit, and re-attach with a second OpenOCD process.

**NOR contents are irrelevant** - the core is trapped in dmseg before it fetches a single instruction from flash, so a blank or corrupt chip makes no difference.

Step 4 is not optional. After the reset OpenOCD still has `target->state` cached as halted and the pre-reset register file in hand, so `poll` returns early and `halt` no-ops - every reading afterwards is a replay of stale data. The only Tcl command that invalidates it, `arp_reset`, is unusable here for the reason in [§Attach sequences](#attach-sequences-differ-and-they-are-not-interchangeable). A fresh process has no cache to fight.

Pass 2 omits the TRST pulse (a TAP reset would clear `ProbEn`/`ProbTrap` and strand the core) and `-defer-examine` (examine only reads IDCODE/IMPCODE, and deferring would block the poll that performs the debug entry). The core re-enters at the exception vector rather than at `PRACC_TEXT`, so debug entry depends on the executor steering it back.

Both passes run automatically whenever the board profile has `hardware_reset = false`. There is no flag to enable or skip it; the script always leaves the core cleanly halted and exits non-zero if it cannot. The PC afterwards must be `0x9c000000` - a PC in DRAM means the reset did not take.

### Invariants

Constraints the ALL-register path depends on. Breaking any reintroduces the corruption it exists to avoid, so do not "simplify" them without hardware evidence.

**Never select CONTROL / ADDRESS / DATA individually while halted.** This is the whole reason the fork exists.

**Every supplied instruction needs a zero-valued ALL completion scan.** It also supplies the NOP for the next sequential fetch, so the PC advances by 8 bytes per instruction, not 4.

**Never trust `tap->cur_instr`.** The IR is re-selected on every access, and `mt7628_pracc_force_all_ir()` drives the transition physically through BYPASS.

**Entry must be steered back to `PRACC_TEXT`.** The core re-enters at the exception vector, one instruction past where PRACC programs assume they start.

**FASTDATA stays refused.** The register does not service processor accesses on this part and has no ALL-register alias to route around it, so bulk writes go over PRACC. Re-enabling it produces loads that report success and write nothing.

**Bulk writes are verified.** `load_image` cannot detect a transfer the target ignored, so every load is followed by `verify_image_checksum`.

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
| `Fastdata access Failed` / `Falling back to non-bulk write` | Normal with `ejtag_all_quirk on` — FASTDATA is refused and PRACC writes take over |
| `load_image` reports success but the target misbehaves | Check the CRC: `verify_image_checksum <file> <addr> bin`. A byte count alone does not prove the write landed |
| `CRC32 mismatch` from `boot_uboot_jtag.py` | Image did not land; do not resume. Confirm the work area is set after `dram_init` |
| `verify_image_checksum` says `not enough working area` | Work area missing — see [§Step 2](#step-2---bootstrap-pll-dram-and-boot-u-boot) |
