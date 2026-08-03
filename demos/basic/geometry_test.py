#!/usr/bin/env python3
"""Color test for cell tiling and 2x4 virtual-pixel addressing."""

import argparse
import shutil
import sys
import time


PUA_START = 0xE000
DOT_BIT = ((0, 3), (1, 4), (2, 5), (6, 7))


def full_frame(columns, rows, mode, tick):
    lines = []
    for cy in range(rows):
        parts = []
        last_color = None
        for cx in range(columns):
            if mode == "solid":
                color, mask = 201, 0xFF
            elif mode == "checker":
                color, mask = ((196, 51)[(cx + cy) & 1], 0xFF)
            else:
                color = (226, 46, 51, 201)[cy % 4]
                mask = 0
                for sy in range(4):
                    for sx in range(2):
                        px, py = cx * 2 + sx, cy * 4 + sy
                        if (px - py - tick) % 13 in (0, 1):
                            mask |= 1 << DOT_BIT[sy][sx]
            if color != last_color:
                parts.append("\x1b[38;5;%dm" % color)
                last_color = color
            parts.append(chr(PUA_START + mask))
        lines.append("".join(parts))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("solid", "checker", "subpixels"))
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    size = shutil.get_terminal_size((80, 24))
    stages = (args.stage,) if args.stage else ("solid", "checker", "subpixels")
    title = "PUA-%s-TEST" % ((args.stage or "geometry").upper())
    sys.stdout.write("\x1b]0;%s\x07\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l" % title)
    sys.stdout.flush()
    try:
        for stage in stages:
            started = time.monotonic()
            tick = 0
            while time.monotonic() - started < args.seconds:
                sys.stdout.write("\x1b[?2026h\x1b[H" + full_frame(size.columns, size.lines, stage, tick) + "\x1b[?2026l")
                sys.stdout.flush()
                tick += 1
                time.sleep(1 / 20 if stage == "subpixels" else 0.25)
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
