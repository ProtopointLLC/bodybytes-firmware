# MT7628AN JTAG — J-Link EDU Mini V2

## Hardware

| Component | Details |
|-----------|---------|
| SoC | MediaTek MT7628AN — MIPS24KEc @ 575/580 MHz |
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

## Wiring — Board Connector → J-Link EDU Mini V2

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

The MT7628 JTAG pins are multiplexed with Ethernet LED functions. The board must be strapped for JTAG mode so these pins are routed to the EJTAG interface rather than LEDs.

## Reset Signals

Only JTRST\_N is connected to the JTAG header on bodybytes. PORST\_N (system reset) is not wired to the JTAG connector.

| Signal | Board net | J-Link pin | What it resets |
|--------|-----------|------------|----------------|
| TRST (nTRST) | `JTAG_TRST` / `JTRST_N` | 9 | JTAG/EJTAG TAP and debug logic only |

TRST resets the JTAG TAP state machine and debug logic only — it does not reset the CPU or peripherals. Without PORST\_N, OpenOCD cannot force a clean CPU reset. Connect after power-on and use `halt` to stop the running CPU.

The OpenOCD reset configuration for bodybytes:

```tcl
reset_config trst_only
```

With `trst_only`, OpenOCD resets only the TAP when `reset` is issued. The CPU is not affected. Use `halt` (not `reset halt`) to stop the CPU after `init`.

---

## Step 1 — Connect and Halt at Reset

Enter the dev shell first — it sets `OPENOCD_SCRIPTS` so [`openocd/mt7628.cfg`](../openocd/mt7628.cfg) and its dependencies are found by name:

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

Start OpenOCD:

```sh
openocd -f interface/jlink.cfg \
    -c "transport select jtag" \
    -c "adapter speed 100" \
    -c "reset_config trst_only" \
    -f mt7628.cfg \
    -c "init" \
    -c "halt" \
    -c "wait_halt 5000"
```

`trst_only` — bodybytes has no PORST\_N on the JTAG connector. OpenOCD can reset the TAP (JTRST\_N) but not the SoC. Power the board first, then connect OpenOCD. `halt` sends a debug request to the running CPU rather than forcing it to a clean reset entry point.

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

Without PORST\_N, `halt` catches the CPU wherever it was executing — mid-U-Boot, mid-SPL, or in the BROM. The PC value is unpredictable but `mdw 0x10000000` should always read `0x3637544d` ("MT76") confirming the SoC is alive. Proceed with `cpu_pll_init` and `dram_init 256` regardless of where the CPU halted — those scripts are idempotent.

---

## Step 2 — Bootstrap PLL and DRAM

Connect via telnet as above and run the following in order. Each command must succeed before the next.

### 2a — Verify the crystal strap

```tcl
mdw 0xb0000010
```

Reads SYSCFG0. Bit 6 is the hardware XTAL strap:

- `0` → 20/40 MHz crystal — correct for this board
- `1` → 25 MHz crystal — wrong; PLL init will produce the wrong CPU frequency

If bit 6 reads 1, stop and check the strap and hardware.

### 2b — Initialize the PLL

```tcl
cpu_pll_init
```

- Polls `0xb0000028` to check if the ROM already initialized the PLL — it will not have, since the CPU was halted before the ROM ran.
- Takes the `CPU_PLL_FROM_XTAL` path: locks the PLL to the 40 MHz crystal.
- Writes `0x00000101` to CLK_CFG0 (`0xb0000440`), setting CPU and bus clock dividers to 1:1 — CPU now runs at 580 MHz.

The CPU runs from the raw crystal clock until this call completes. That is expected.

### 2c — Initialize DRAM

```tcl
dram_init 256
```

- Reads SYSCFG0 bit 0 to confirm DDR2 (not DDR1).
- Pulses the DDR controller reset.
- Writes the DDR2 PHY configuration registers.
- Calls [`openocd/memc.tcl`](../openocd/memc.tcl) / `ddr_init` with the 256 MB DDR2 timing words and DQ/DQS delay values.

After this returns, 256 MB of DDR2 is live at physical `0x00000000` (KSEG1 uncached alias: `0xa0000000`). Verify:

```tcl
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
# expected: 0xa0000000: deadbeef
```

### 2d — Set the work area

```tcl
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
```

Lets OpenOCD use 4 KB at `0xa0001000` as scratch space for bulk operations such as `load_image`. Without this, transfers fall back to slow register-at-a-time writes. `-work-area-backup 0` skips saving and restoring the memory under the work area — safe here since `0xa0001000` is scratch RAM we own.

### Full sequence

```tcl
targets
reg pc
mdw 0xb0000010
mdw 0x10000000
cpu_pll_init
adapter speed 1000
dram_init 256
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
```

After the last command prints `deadbeef`, the board is initialized and ready to load code.

---

## Step 3 — Load and Run U-Boot

Continue with [flashing.md §4a](flashing.md#4a--bootstrap-via-jtag-and-smoke-test-u-boot).

---

## Flash Map

| Region | Interface | Size | Contents |
|--------|-----------|------|----------|
| SPI NOR | SPI bus 0 | 64 MB | U-Boot at 0x000000, env at 0x040000, WiFi EEPROM at 0x050000, recovery at 0x060000 |
| eMMC | SDXC / MMC | 128 GB | 4-partition GPT: `kernel` (32 MB, raw), `rootfs` (512 MB, squashfs), `rootfs_data` (4 GB, ext4 overlay), `data` (remainder, ext4) — see [flashing.md §5a](flashing.md#5a--gpt-partition-layout) |

SPI NOR is at physical `0x1c000000`, accessible to the CPU at `0x9c000000` (KSEG0 cached) or `0xbc000000` (KSEG1 uncached).

---

## Troubleshooting

| Symptom | Likely cause / next check |
|---------|---------------------------|
| `JTAG tap: ... UNEXPECTED` | Wrong IDCODE — check target config and TDI/TDO wiring |
| `Timed out waiting for device to appear` | VTref missing or target unpowered |
| `Error: JTAG scan chain interrogation failed` | TCK/TMS/TDO wiring, target power, or reset state problem |
| `tap: mt7628.cpu enabled (idcode 0x00000000)` | TDO open, target unpowered, or TAP held in reset |
| `halt` times out | CPU may be held in reset, JTAG mode may not be strapped, or EJTAG pins muxed to LEDs |
| `targets` shows `running` after a previous clean halt | Check for GDB/IDE resume, external reset, watchdog, or stale register reads |
| PC remains `0x9c000000` after `resume; sleep 100; halt` | CPU not progressing from NOR entry — check clock, SPI flash activity, and boot straps |
| `halt` times out after `init` | Board not powered, JTAG mode not strapped (TXD1 must be low), or EPHY LED pins not muxed to JTAG |
