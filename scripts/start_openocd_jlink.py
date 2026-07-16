#!/usr/bin/env python3
"""
Start OpenOCD with a J-Link for MT7628AN JTAG debugging.

Must be run from the repo root inside `nix develop .#uboot` so that
OPENOCD_SCRIPTS is set and mt7628.cfg / interface/jlink.cfg are found.

Usage:
  start_openocd_jlink.py [--bodybytes|--vocore2]

  --bodybytes  (default)  reset_config trst_only + halt
                          No PORST_N on JTAG connector; TAP reset only.
  --vocore2               reset_config trst_and_srst + reset halt
                          PORST_N wired to J6 pin 10; full SoC reset.
"""

import argparse
import os
import shutil
import sys

from lib.log import log


BOARDS = {
    "bodybytes": {
        "reset_config": "trst_only",
        "halt_cmd":     "halt",
    },
    "vocore2": {
        "reset_config": "trst_and_srst separate srst_nogate connect_assert_srst",
        "halt_cmd":     "reset halt",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bodybytes", dest="board", action="store_const", const="bodybytes",
                       help="bodybytes reset config (default)")
    group.add_argument("--vocore2", dest="board", action="store_const", const="vocore2",
                       help="VoCore2 reset config")
    parser.set_defaults(board="bodybytes")
    args = parser.parse_args()

    cfg = BOARDS[args.board]

    openocd = shutil.which("openocd")
    if openocd is None:
        print("error: openocd not found in PATH", file=sys.stderr)
        sys.exit(1)

    log(f"Board        : {args.board}")
    log(f"reset_config : {cfg['reset_config']}")
    log(f"halt_cmd     : {cfg['halt_cmd']}")
    log(f"openocd      : {openocd}")

    argv = [
        openocd,
        "-f", "interface/jlink.cfg",
        "-c", "transport select jtag",
        "-c", "adapter speed 100",
        "-c", f"reset_config {cfg['reset_config']}",
        "-f", "mt7628.cfg",
        "-c", "init",
        "-c", cfg["halt_cmd"],
        "-c", "wait_halt 5000",
    ]

    os.execv(openocd, argv)


if __name__ == "__main__":
    main()
