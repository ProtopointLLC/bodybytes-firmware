# bodybytes

Development environment for JTAG debugging the MT7628AN SoC via OpenOCD.

## OpenOCD scripts

Custom OpenOCD target scripts live in a separate repository at
`/home/christoph/Documents/GitHub/openocd-scripts`. The `mt7628/` subdirectory
there contains `mt7628.cfg`, `mmio.tcl`, and `memc.tcl`.

The dev shell (`nix develop`) sets `OPENOCD_SCRIPTS` to that directory so
OpenOCD can find those scripts by name without requiring a `cd` first.

## Connecting to the board

See [docs/notes.md](docs/notes.md) for full wiring, JTAG bring-up, PLL/DRAM
initialisation, and U-Boot RAM-boot instructions.
