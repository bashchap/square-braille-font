#!/usr/bin/env python3
"""Controlled sparse PUA seam probe: fixed one-subpixel vertical columns."""

import argparse
import os
import shutil
import subprocess
import sys
import time

from pua4x4_backend import mask_to_codepoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=20.0)
    parser.add_argument("--capture", help="PNG path; captures only this terminal window")
    args = parser.parse_args()
    size = shutil.get_terminal_size((100, 30))
    columns, rows = size.columns, size.lines
    patterns = (
        (columns // 6, 0x1111, (0, 255, 255)),
        (columns * 2 // 6, 0x2222, (64, 180, 255)),
        (columns * 3 // 6, 0x4444, (255, 180, 32)),
        (columns * 4 // 6, 0x8888, (255, 80, 180)),
        (columns * 5 // 6, 0xFFFF, (255, 255, 255)),
    )
    sys.stdout.write("\x1b]0;PUA Sparse Vertical Seam Probe\x07"
                     "\x1b[?1049h\x1b[2J\x1b[?25l")
    for x, pattern, color in patterns:
        sys.stdout.write("\x1b[38;2;%d;%d;%dm" % color)
        for row in range(1, rows + 1):
            sys.stdout.write("\x1b[%d;%dH%s" % (row, x, chr(mask_to_codepoint(pattern))))
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
