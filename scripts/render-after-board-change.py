#!/usr/bin/env python3
"""Wait for the KiCad board file to settle, then refresh its 3D renders."""
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "IOT_LC.kicad_pcb"


def fingerprint():
    try:
        stat = BOARD.stat()
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def main():
    stable_since = time.monotonic()
    previous = fingerprint()
    while time.monotonic() - stable_since < 2.5:
        time.sleep(0.5)
        current = fingerprint()
        if current != previous:
            previous = current
            stable_since = time.monotonic()
    if previous is None:
        print(f"Board file not found: {BOARD}", file=sys.stderr)
        return 1
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render-pcb-3d.py")],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
