#!/usr/bin/env python3
"""
Start OpenOCD with a J-Link for MT7628AN JTAG debugging.

Must be run from the repo root inside `nix develop .#uboot` so that
OPENOCD_SCRIPTS is set and mt7628.cfg / interface/jlink.cfg are found.

Board profiles (hardware_reset) are read from scripts/config.ini.

Usage:
  start_openocd_jlink.py --bodybytes
  start_openocd_jlink.py --vocore2

If OpenOCD is already listening it is reused rather than started a second
time, so running this twice - or running it as a task prerequisite when it is
already up - is harmless.

The core is always left cleanly halted; OpenOCD exits non-zero if it is not.
"""

import argparse
import shutil
import socket
import subprocess
import sys

from lib.config import BOARD_NAMES, OPENOCD_HOST, OPENOCD_PORT, load_board
from lib.log import log, ts

READY_PATTERN = "MT7628_STARTUP_READY"


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """True if something is already accepting connections on host:port."""
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    for name in BOARD_NAMES:
        group.add_argument(f"--{name}", dest="board", action="store_const", const=name,
                           help=f"use {name} board profile")
    args = parser.parse_args()

    # Reports "ready" so a waiting VS Code background task completes.
    if _port_open(OPENOCD_HOST, OPENOCD_PORT):
        log(f"OpenOCD already listening on {OPENOCD_HOST}:{OPENOCD_PORT} - "
            f"reusing it, not starting a second one; ready")
        return

    board = load_board(args.board)

    openocd = shutil.which("openocd")
    if openocd is None:
        print("error: openocd not found in PATH", file=sys.stderr)
        sys.exit(1)

    if board.hardware_reset:
        reset_config = "trst_and_srst separate srst_nogate connect_assert_srst"
    else:
        reset_config = "trst_only"

    log(f"Board          : {board.name}")
    log(f"hardware_reset : {board.hardware_reset}")
    log(f"reset_config   : {reset_config}")
    log(f"ejtag_all_quirk: {'off (SRST wired - stock EJTAG)' if board.hardware_reset else 'on (no SRST - ALL register, FASTDATA off)'}")
    if not board.hardware_reset:
        log("ejtag_reset    : EJTAGBOOT + RSTCTL.SYS_RST")
    log(f"openocd        : {openocd}")

    common = [
        openocd,
        "-f", "interface/jlink.cfg",
        "-c", "transport select jtag",
        "-c", "adapter speed 100",
        "-c", f"reset_config {reset_config}",
        "-f", "mt7628.cfg",
    ]

    if not board.hardware_reset:
        # Pass 1: reset over EJTAG, then exit - pass 2 needs a fresh process.
        log("EJTAG reset    : pass 1/2 - resetting SoC")
        reset_argv = common + [
            "-c", "mips32 ejtag_all_quirk on",
            "-c", "mt7628.cpu0 configure -defer-examine",
            "-c", "init",
            "-c", "poll off",
            "-c", "adapter assert trst",
            "-c", "sleep 100",
            "-c", "adapter deassert trst",
            "-c", "sleep 10",
            "-c", "mt7628.cpu0 arp_examine",

            # SYS_RST is written over PRACC, so halt first.
            "-c", "halt",
            "-c", "wait_halt 2000",
            # EJTAGBOOT: arm the TAP so the next reset traps at the reset vector.
            "-c", "irscan mt7628.cpu 0x0c",
            # RSTCTL.SYS_RST. Fails mid-access as the SoC resets - that is success.
            "-c", "catch { mww 0xb0000034 0x1 }",
            "-c", "shutdown",
        ]
        rc = subprocess.run(reset_argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
        for line in rc.stdout.splitlines():
            print(f"{ts()} [reset] {line.rstrip()}", flush=True)
        log(f"EJTAG reset    : pass 1/2 done (exit {rc.returncode})")

    argv = list(common)

    if board.hardware_reset:
        argv += [
            "-c", "init",
            "-c", "reset halt",
            "-c", "poll",
            "-c", "halt",
            "-c", "wait_halt 5000",
        ]
    else:
        # Pass 2: attach to the core parked in dmseg; no TRST, no defer-examine.
        argv += [
            "-c", "mips32 ejtag_all_quirk on",
            "-c", "init",
            "-c", "poll",
            "-c", "halt",
            "-c", "wait_halt 5000",
            "-c", "reg pc",
        ]

    argv += [
        "-c", f"echo {READY_PATTERN}",
    ]

    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    startup_ok = False
    errors_seen = []
    try:
        for line in proc.stdout:
            print(f"{ts()} [OpenOCD] {line.rstrip()}", flush=True)
            if not startup_ok:
                if READY_PATTERN in line:
                    if errors_seen:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        log("OpenOCD: failed")
                        sys.exit(1)
                    log("OpenOCD: ready")
                    startup_ok = True
                elif line.startswith("Error:"):
                    errors_seen.append(line.rstrip())
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        sys.exit(0)
    finally:
        proc.stdout.close()
    proc.wait()
    if not startup_ok:
        log(f"OpenOCD: failed (exit {proc.returncode})")
        sys.exit(proc.returncode if proc.returncode != 0 else 1)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
