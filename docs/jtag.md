# MT7628AN JTAG Notes — J-Link Mini EDU

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

## Wiring — Board Connector → J-Link Mini EDU

Reference: https://kb.segger.com/9-pin_JTAG/SWD_connector

| Board pos | Wire   | Test point | JTAG signal | SWD silkscreen | J-Link pin |
|-----------|--------|------------|-------------|----------------|------------|
| 1 (top)   | Red    | TP21       | VTref       | VTref          | 1          |
| 2         | Orange | TP22       | GND         | GND            | 3 or 5     |
| 3         | Yellow | TP18       | RESET_N     | nRESET         | 10         |
| 4         | Green  | TP17       | TCK         | SWCLK          | 4          |
| 5         | Blue   | TP16       | TMS         | SWDIO          | 2          |
| 6         | Violet | TP15       | TDI         | NC             | 8          |
| 7 (bot)   | White  | TP14       | TDO         | SWO            | 6          |

> VTref (red, TP21) is a sense input on the J-Link — connect it to the 3.3 V
> rail but do not rely on it to power the board.

---

## Step 1 — Check JTAG Connectivity (core health check)

This only verifies the TAP responds; it does **not** initialize RAM.

### Start OpenOCD

Enter the dev shell first — it sets `OPENOCD_SCRIPTS` so `mt7628.cfg` and
its dependencies are found by name:

```sh
cd /path/to/bodybytes
nix develop .#uboot
```

Then start OpenOCD from any directory:

```sh
openocd -f interface/jlink.cfg \
        -c "transport select jtag" \
        -f mt7628.cfg
```

Expected output — OpenOCD should print something like:

```
Info : J-Link Mini EDU V1 compiled ...
Info : Hardware version: ...
Info : JTAG tap: mt7628.cpu tap/device found: 0x1762824f ...
Info : Examined MIPS core; ...
Info : starting gdb server for mt7628.cpu0 on 3333
Info : Listening on port 4444 for telnet connections
```

If you see `0x1762824f` in the scan — the core is alive on JTAG.

### Connect and probe via telnet

In a second terminal:

```sh
telnet localhost 4444
```

```tcl
# Show all detected TAPs and their IDs
scan_chain

# Show target state
targets

# Halt the CPU (freezes execution)
halt

# Confirm it stopped
targets

# Read a known register to verify coherent communication
reg pc

# Read the chip ID register (should return a MediaTek vendor value)
mdw 0x10000000
```

---

## Step 2 — Bootstrap PLL and DRAM

Start OpenOCD (as in Step 1), then connect via telnet and run the following in
order. Each command must succeed before running the next.

### 2a — Halt the CPU

```tcl
halt
```

The CPU freezes at whatever instruction it was executing.
Confirm with `targets` — status should change from `running` to `halted`.

If the chip is still in reset and `halt` times out, use `reset halt` instead —
this asserts the system reset line and holds the CPU halted the moment it
de-asserts:

```tcl
reset halt
```

### 2b — Verify the crystal strap (sanity check)

```tcl
mdw 0xb0000010
```

This reads SYSCFG0. Bit 6 is the hardware XTAL strap:
- `0` → 20/40 MHz crystal — correct for this board
- `1` → 25 MHz crystal — wrong; PLL init will produce the wrong CPU frequency

If bit 6 reads 1, stop — the board strap or the hardware is misconfigured.

### 2c — Initialise the PLL (`cpu_pll_init`)

```tcl
cpu_pll_init
```

What this does:
- Polls `0xb0000028` to see if the ROM already set up the PLL (it won't have,
  because you halted early).
- Takes the `CPU_PLL_FROM_XTAL` path: tells the PLL to lock to the 40 MHz
  crystal reference.
- Writes `0x00000101` to CLK_CFG_0 (`0xb0000440`), setting CPU and bus clock
  dividers to 1:1 — CPU now runs at full PLL output (580 MHz).

The CPU is running at 40 MHz raw crystal from halt until this call returns.
That is expected.

### 2d — Initialise DRAM (`dram_init`)

```tcl
dram_init 256
```

What this does:
- Reads SYSCFG0 bit 0 to confirm DDR2 (not DDR1) — should be 0 on your board.
- Pulses the DDR controller reset (200 ms hold).
- Writes the DDR2 PHY configuration registers (drive strength, ODT, DLL).
- Calls into `memc.tcl`:`ddr_init` with the 256 MB DDR2 timing word set:
  `{ 0x249CE2E5  0x223A2323  0x68000C43  0x00000452  0x0000000A }`
  and DQ/DQS delay values `0x8282` / `0x8383`.

After this returns, 256 MB of DDR2 is live at physical `0x00000000`
(KSEG1 uncached alias: `0xa0000000`).

Verify RAM is working with a quick write/read test:

```tcl
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
# should print: 0xa0000000: deadbeef
```

### 2e — Set the work area

```tcl
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096
```

This tells OpenOCD it can use 4 KB of RAM at `0xa0001000` as scratch space for
bulk operations like `load_image`. Without this, transfers fall back to a slow
register-at-a-time write.

### Full sequence (copy-paste)

```tcl
halt
mdw 0xb0000010
cpu_pll_init
dram_init 256
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
```

After the last two lines print `deadbeef`, the board is fully initialised and
ready to load code.

---

## Step 3 — Load and run U-Boot

Once DRAM is initialised, continue with [uboot.md §3a](uboot.md#3a--bootstrap-and-smoke-test) to RAM-boot U-Boot.

---

## Flash Map

| Region | Interface | Size | Contents |
|--------|-----------|------|----------|
| SPI NOR | SPI bus 0 | 64 MB | U-Boot (0x0), env (0x30000), WiFi EEPROM (0x40000) |
| eMMC | SDXC / MMC | 128 GB | OS kernel + rootfs (sector 0), remaining space for data |

> SPI NOR is mapped at `0x1c000000` (physical) / `0x9c000000` (KSEG1) on the MT7628.
> eMMC is accessed via the SDXC controller; the OS image is written raw to sector 0.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `JTAG tap: ... UNEXPECTED` | Wrong IDCODE — check wiring TDI/TDO not swapped |
| `Timed out waiting for device to appear` | VTref not connected or wrong voltage |
| `Error: JTAG scan chain interrogation failed` | TCK/TMS not reaching chip; check power-on reset state |
| `tap: mt7628.cpu enabled (idcode 0x00000000)` | TDO line open or chip not powered |
| `halt: timed out waiting for halt` | CPU in reset; try `reset halt` instead of `halt` |
| OpenOCD starts but telnet shows target as `unknown` | Normal before first `halt`; run `halt` to examine |
