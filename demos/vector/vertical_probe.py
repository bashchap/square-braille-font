#!/usr/bin/env python3
"""Controlled sparse PUA seam probe: fixed one-subpixel vertical columns."""

import argparse
import os
import shutil
import subprocess
import sys
import time


PUA_START = 0xE000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=20.0)
    parser.add_argument("--capture", help="PNG path; captures only this terminal window")
    args = parser.parse_args()
    size = shutil.get_terminal_size((100, 30))
    columns, rows = size.columns, size.lines
    patterns = (
        (columns // 5, 0x47, (0, 255, 255)),   # dots 1,2,3,7: left column
        (columns * 2 // 5, 0xB8, (255, 180, 32)),  # dots 4,5,6,8: right column
        (columns * 3 // 5, 0xFF, (255, 0, 255)),   # full cell reference
    )
    sys.stdout.write("\x1b]0;PUA Sparse Vertical Seam Probe\x07"
                     "\x1b[?1049h\x1b[2J\x1b[?25l")
    for x, pattern, color in patterns:
        sys.stdout.write("\x1b[38;2;%d;%d;%dm" % color)
        for row in range(1, rows + 1):
            sys.stdout.write("\x1b[%d;%dH%s" % (row, x, chr(PUA_START + pattern)))
    sys.stdout.write("\x1b[0m")
    sys.stdout.flush()
    try:
        if args.capture:
            time.sleep(0.75)
            window_id = os.environ.get("WINDOWID")
            if not window_id:
                raise SystemExit("MATE Terminal did not provide WINDOWID")
            subprocess.run(["import", "-window", window_id, args.capture], check=True)
        time.sleep(args.hold)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
