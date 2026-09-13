#!/usr/bin/env python3
"""Color test for cell tiling and 4x4 virtual-pixel addressing."""

import argparse
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "demos"))
from native_terminal import terminal_picture

from pua4x4_backend import DOT_BIT, mask_to_codepoint


def full_frame(columns, rows, mode, tick):
    masks = [[0] * columns for _ in range(rows)]
    colors = [[0] * columns for _ in range(rows)]
    for cy in range(rows):
        for cx in range(columns):
            if mode == "solid":
                color, mask = 201, 0xFFFF
            elif mode == "checker":
                color, mask = ((196, 51)[(cx + cy) & 1], 0xFFFF)
            else:
                color = (226, 46, 51, 201)[cy % 4]
                mask = 0
                for sy in range(4):
                    for sx in range(4):
                        px, py = cx * 4 + sx, cy * 4 + sy
                        if (px - py - tick) % 13 in (0, 1):
                            mask |= 1 << DOT_BIT[sy][sx]
            masks[cy][cx] = mask
            colors[cy][cx] = color
    return terminal_picture(
        masks, colors, columns, rows, mapping="pua4",
        colour_mode="indexed", blank_glyph=True, reset_at_end=False)


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
