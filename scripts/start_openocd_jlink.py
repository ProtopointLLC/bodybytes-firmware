#!/usr/bin/env python3
"""
Start OpenOCD with a J-Link for MT7628AN JTAG debugging.

Must be run from the repo root inside `nix develop .#uboot` so that
OPENOCD_SCRIPTS is set and mt7628.cfg / interface/jlink.cfg are found.

Board profiles (reset_config and halt_cmd) are read from scripts/config.ini.

Usage:
  start_openocd_jlink.py --bodybytes
  start_openocd_jlink.py --vocore2
"""

import argparse
import os
import shutil
import sys

from lib.config import BOARD_NAMES, load_board
from lib.log import log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    for name in BOARD_NAMES:
        group.add_argument(f"--{name}", dest="board", action="store_const", const=name,
                           help=f"use {name} board profile")
    args = parser.parse_args()

    board = load_board(args.board)

    openocd = shutil.which("openocd")
    if openocd is None:
        print("error: openocd not found in PATH", file=sys.stderr)
        sys.exit(1)

    log(f"Board        : {board.name}")
    log(f"reset_config : {board.reset_config}")
    log(f"halt_cmd     : {board.halt_cmd}")
    log(f"openocd      : {openocd}")

    argv = [
        openocd,
        "-f", "interface/jlink.cfg",
        "-c", "transport select jtag",
        "-c", "adapter speed 100",
        "-c", f"reset_config {board.reset_config}",
        "-f", "mt7628.cfg",
        "-c", "init",
        "-c", board.halt_cmd,
        "-c", "wait_halt 5000",
    ]

    os.execv(openocd, argv)


if __name__ == "__main__":
    main()
