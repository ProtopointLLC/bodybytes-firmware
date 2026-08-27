#!/usr/bin/env python3
"""
Start OpenOCD with a J-Link for MT7628AN JTAG debugging.

Must be run from the repo root inside `nix develop .#uboot` so that
OPENOCD_SCRIPTS is set and mt7628.cfg / interface/jlink.cfg are found.

Board profiles (hardware_reset) are read from scripts/config.ini.

Usage:
  start_openocd_jlink.py --bodybytes
  start_openocd_jlink.py --vocore2
  start_openocd_jlink.py --vocore2 --no-halt

If OpenOCD is already listening it is reused rather than started a second
time, so running this twice - or running it as a task prerequisite when it is
already up - is harmless.

--no-halt skips the halt/wait_halt commands entirely, so OpenOCD stays up
and reaches its normal telnet/tcl/gdb server listen state regardless of
whether a halt would succeed. Use this to attach over telnet (port 4444)
and experiment manually, e.g. with `mips_m4k scan_delay` and `cp0` reads,
without the process dying out from under you on a failed/timed-out halt.
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
    parser.add_argument("--no-halt", action="store_true",
                        help="skip the halt/wait_halt commands; stay attached for manual telnet testing")
    args = parser.parse_args()

    # Reports "ready" so a VS Code background task waiting on that pattern
    # completes instead of hanging.
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
    log(f"ejtag_all_quirk: {'off (SRST wired - stock EJTAG + FASTDATA)' if board.hardware_reset else 'on (no SRST - ALL register, FASTDATA disabled)'}")
    log(f"openocd        : {openocd}")

    argv = [
        openocd,
        "-f", "interface/jlink.cfg",
        "-c", "transport select jtag",
        "-c", "adapter speed 100",
        "-c", f"reset_config {reset_config}",
        "-f", "mt7628.cfg",
    ]

    if board.hardware_reset:
        argv += [
            "-c", "init",
        ]
        if not args.no_halt:
            argv += [
                "-c", "reset halt",
                "-c", "poll",
                "-c", "halt",
                "-c", "wait_halt 5000",
            ]
    else:
        argv += [
            "-c", "mips32 ejtag_all_quirk on",
            "-c", "mt7628.cpu0 configure -defer-examine",
            "-c", "init",
            "-c", "poll off",
            "-c", "adapter assert trst",
            "-c", "sleep 100",
            "-c", "adapter deassert trst",
            "-c", "sleep 10",
            "-c", "mt7628.cpu0 arp_examine",
        ]
        if not args.no_halt:
            argv += [
                "-c", "halt",
                "-c", "sleep 100",
                "-c", "wait_halt 5000",
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
                    if errors_seen and not args.no_halt:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        log("OpenOCD: failed")
                        sys.exit(1)
                    if errors_seen:
                        log(f"OpenOCD: ready, but {len(errors_seen)} error(s) logged above (--no-halt, staying up anyway)")
                    else:
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
