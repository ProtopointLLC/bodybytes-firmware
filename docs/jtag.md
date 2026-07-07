# MT7628AN JTAG Notes - J-Link EDU Mini V2

## Hardware

| Component | Details |
|-----------|---------|
| SoC | MediaTek MT7628AN — MIPS24KEc @ 575/580 MHz |
| JTAG adapter | Segger J-Link Mini EDU |
| Crystal | 40 MHz external oscillator |
| RAM | 256 MB DDR2 |
| Boot flash | 64 MB SPI NOR (U-Boot + WiFi EEPROM) |
| App storage | 128 GB eMMC (Kingston EMMC128-IY29-5B111) — OS lives here |

## JTAG TAP

| Field | Value |
|-------|-------|
| IR length | 5 bits |
| Expected IDCODE | `0x1762824f` |
| Target type | `mips_m4k` (little-endian) |

## Reset Signals

The connector exposes two different active-low reset lines:

| Signal | Board signal | J-Link signal | What it resets |
|--------|--------------|---------------|----------------|
| TRST / nTRST | `JTAG_TRST` / `JTRST_N` | pin 9 on this setup | JTAG/EJTAG TAP and debug logic only |
| SRST / nRESET | `RESET` / `PORST_N` | pin 10 | Whole SoC/system reset |

TRST does not reset the CPU. It only resets the JTAG/EJTAG TAP state machine and
debug logic. SRST/PORST_N resets the MT7628 system and returns execution to the
boot entry point.

For this board, both reset lines have pull-ups. In practice the working OpenOCD
configuration is to leave the adapter-specific TRST drive mode implicit and use
SRST as OpenOCD/J-Link's default open-drain reset:

```tcl
reset_config trst_and_srst separate srst_nogate connect_assert_srst
```

## Wiring - Board Connector to J-Link EDU Mini V2

Reference: <https://kb.segger.com/9-pin_JTAG/SWD_connector>

| Board pos | Wire   | Test point | JTAG signal | SWD silkscreen | J-Link pin |
|-----------|--------|------------|-------------|----------------|------------|
| 1 (top)   | Red    | TP21       | VTref       | VTref          | 1          |
| 2         | Orange | TP22       | GND         | GND            | 3 or 5     |
| 3         | Yellow | TP18       | RESET_N     | nRESET         | 10         |
| 4         | Green  | TP17       | TCK         | SWCLK          | 4          |
| 5         | Blue   | TP16       | TMS         | SWDIO          | 2          |
| 6         | Violet | TP15       | TDI         | NC             | 8          |
| 7 (bot)   | White  | TP14       | TDO         | SWO            | 6          |

VTref is a sense input on the J-Link. Connect it to the board's 3.3 V rail, but
do not rely on it to power the board.

The MT7628 pins are multiplexed with Ethernet LED functions. Make sure the board
is strapped/configured for JTAG mode so these pins are available as EJTAG rather
than LED GPIOs.

## Step 1 - Check EJTAG Connectivity and Halt at Reset

Enter the dev shell first. It sets `OPENOCD_SCRIPTS` so `mt7628.cfg` and its dependencies are found by name:

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

Then start OpenOCD:

```sh
openocd -f interface/jlink.cfg \
    -c "transport select jtag" \
    -c "adapter speed 100" \
    -c "reset_config trst_and_srst separate srst_nogate connect_assert_srst" \
    -f mt7628.cfg \
    -c "init" \
    -c "reset halt" \
    -c "wait_halt 10000"
```

Expected output:

```text
jtag
adapter speed: 100 kHz

trst_and_srst separate srst_nogate trst_push_pull srst_open_drain connect_assert_srst

dram_init
Info : J-Link EDU Mini V2 compiled Dec 10 2025 15:50:17
Info : Hardware version: 2.00
Info : VTarget = 3.316 V
Info : clock speed 100 kHz
Info : JTAG tap: mt7628.cpu tap/device found: 0x1762824f (mfg: 0x127 (MIPS Technologies), part: 0x7628, ver: 0x1)
Info : starting gdb server for mt7628.cpu0 on 3333
Info : Listening on port 3333 for gdb connections
Error: isa info not available, failed to read cp0 config register: 0
target halted in MIPS32 mode due to undefined, pc: 0x00000000
Info : JTAG tap: mt7628.cpu tap/device found: 0x1762824f (mfg: 0x127 (MIPS Technologies), part: 0x7628, ver: 0x1)
Error: isa info not available, failed to read cp0 config register: 0
target halted in MIPS32 mode due to debug-request, pc: 0x00000000
Info : Listening on port 6666 for tcl connections
Info : Listening on port 4444 for telnet connections
```

## Telnet Checks

In a second terminal:

```sh
telnet localhost 4444
```

Expected interaction:

```sh
Open On-Chip Debugger
> targets
    TargetName         Type       Endian TapName            State       
--  ------------------ ---------- ------ ------------------ ------------
 0* mt7628.cpu0        mips_m4k   little mt7628.cpu         halted

> reg pc
pc (/32): 0x9c000001

> mdw 0x10000000
0x10000000: 3637544d 
```

After reset, the MT7628 begins execution from the SPI boot flash window as seen
through the MIPS cached KSEG0 alias:

```text
virtual  0x9c000000
physical 0x1c000000
```

So a clean `reset halt` should leave the CPU halted at `0x9c000000`.

The system controller identification register `0x10000000` should read `0x3637544d`, which decodes to "MT76" , the chip ID.

---

## Step 2 - Bootstrap PLL and DRAM

Start OpenOCD as in Step 1, then connect via telnet and run the following in
order. Each command must succeed before running the next.

### 2b - Verify the crystal strap

```tcl
mdw 0xb0000010
```

This reads SYSCFG0. Bit 6 is the hardware XTAL strap:

- `0` -> 20/40 MHz crystal - correct for this board
- `1` -> 25 MHz crystal - wrong; PLL init will produce the wrong CPU frequency

If bit 6 reads 1, stop and check the strap/hardware.

### 2c - Initialise the PLL

```tcl
cpu_pll_init
```

What this does:

- polls `0xb0000028` to see if the ROM already set up the PLL;
- takes the `CPU_PLL_FROM_XTAL` path if halted before ROM init;
- writes `0x00000101` to CLK_CFG_0 (`0xb0000440`), setting CPU and bus clock
  dividers to 1:1.

The CPU is running from the raw crystal clock until this call completes. That is
expected.

### 2d - Initialise DRAM

```tcl
dram_init 256
```

What this does:

- reads SYSCFG0 bit 0 to confirm DDR2 rather than DDR1;
- pulses the DDR controller reset;
- writes the DDR2 PHY configuration registers;
- calls into `memc.tcl` / `ddr_init` with the 256 MB DDR2 timing words and DQ/DQS
  delay values.

After this returns, DDR2 should be live at physical `0x00000000`; use the KSEG1
uncached alias `0xa0000000` for simple tests.

Verify RAM:

```tcl
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
```

Expected:

```text
0xa0000000: deadbeef
```

### 2e - Set the OpenOCD work area

```tcl
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096
```

This lets OpenOCD use 4 KB of RAM at `0xa0001000` as scratch space for bulk
operations such as `load_image`.

### Full sequence

```tcl
reset halt
mdw 0xb0000010
cpu_pll_init
dram_init 256
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
```

After the last command prints `deadbeef`, the board is initialized enough to
load code into RAM.

## Step 3 - Load and Run U-Boot

Once DRAM is initialized, continue with [uboot.md section 3a](uboot.md#3a--bootstrap-and-smoke-test) to RAM-boot U-Boot.

## Flash Map

| Region | Interface | Size | Contents |
|--------|-----------|------|----------|
| SPI NOR | SPI bus 0 | 64 MB | U-Boot at offset 0x0, env at 0x30000, WiFi EEPROM at 0x40000 |
| eMMC | SDXC / MMC | 128 GB | OS kernel + rootfs from sector 0, remaining space for data |

SPI NOR is mapped at physical `0x1c000000` and appears to the CPU at virtual
`0x9c000000` through the cached KSEG0 alias.

## Troubleshooting

| Symptom | Likely cause / next check |
|---------|---------------------------|
| `JTAG tap: ... UNEXPECTED` | Wrong IDCODE; check target config and TDI/TDO wiring |
| `Timed out waiting for device to appear` | VTref missing or target unpowered |
| `Error: JTAG scan chain interrogation failed` | TCK/TMS/TDO wiring, target power, or reset state problem |
| `tap: mt7628.cpu enabled (idcode 0x00000000)` | TDO open, target unpowered, or TAP held reset |
| `halt` times out | CPU may be held in reset, JTAG mode may not be strapped, or EJTAG pins may be muxed away |
| `targets` shows `running` after a previous clean halt | Check for GDB/IDE resume, external reset, watchdog/supervisor, or stale running-state register reads |
| PC remains `0x9c000000` after `resume; sleep 100; halt` | CPU is not progressing from reset entry; check PORST_N, clock, SPI flash activity, and boot straps |
| Explicit `trst_open_drain` or explicit `trst_push_pull srst_open_drain` fails | Use the known-good implicit reset mode: `reset_config trst_and_srst separate srst_nogate connect_assert_srst` |