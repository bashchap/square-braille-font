#!/usr/bin/env python3
"""Animate snow at 2x4 sub-character resolution with PUA Square Braille."""

import argparse
import math
import os
import random
import shutil
import signal
import sys
import time


PUA_START = 0xE000
# Braille bit numbers at each position in a 2-column by 4-row cell.
DOT_BIT = ((0, 3), (1, 4), (2, 5), (6, 7))


class Flake:
    def __init__(self, width, height, initial=False):
        self.x = random.uniform(0, max(0, width - 1))
        self.y = random.uniform(0, height - 1) if initial else random.uniform(-8, -1)
        self.speed = random.uniform(4.0, 13.0)
        self.drift = random.uniform(-1.8, 1.8)
        self.phase = random.uniform(0, math.tau)
        self.wobble = random.uniform(0.8, 2.8)
        self.large = random.random() < 0.12
        self.shade = 2 if self.large else (1 if self.speed > 8.0 else 0)

    def step(self, dt, elapsed, width, height, wind):
        self.y += self.speed * dt
        self.x += (self.drift + wind + math.sin(elapsed * self.wobble + self.phase) * 1.4) * dt
        self.x %= width
        return self.y < height


def put_pixel(buffer, shades, px_width, px_height, x, y, shade):
    x, y = int(round(x)), int(round(y))
    if not (0 <= x < px_width and 0 <= y < px_height):
        return
    cell_x, sub_x = divmod(x, 2)
    cell_y, sub_y = divmod(y, 4)
    buffer[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
    shades[cell_y][cell_x] = max(shades[cell_y][cell_x], shade)


def draw_flake(buffer, shades, px_width, px_height, flake):
    put_pixel(buffer, shades, px_width, px_height, flake.x, flake.y, flake.shade)
    if flake.large:
        # A tiny five-pixel crystal in the virtual pixel grid.
        put_pixel(buffer, shades, px_width, px_height, flake.x - 1, flake.y, flake.shade)
        put_pixel(buffer, shades, px_width, px_height, flake.x + 1, flake.y, flake.shade)
        put_pixel(buffer, shades, px_width, px_height, flake.x, flake.y - 1, flake.shade)
        put_pixel(buffer, shades, px_width, px_height, flake.x, flake.y + 1, flake.shade)


def frame_text(flakes, columns, rows):
    px_width, px_height = columns * 2, rows * 4
    buffer = [[0] * columns for _ in range(rows)]
    shades = [[0] * columns for _ in range(rows)]
    for flake in flakes:
        draw_flake(buffer, shades, px_width, px_height, flake)
    # U+E000 is blank; adding the eight-bit mask selects the matching glyph.
    palette = (39, 51, 231)  # blue, cyan, white
    lines = []
    for row_masks, row_shades in zip(buffer, shades):
        parts = []
        active_shade = None
        for mask, shade in zip(row_masks, row_shades):
            if mask and shade != active_shade:
                parts.append("\x1b[38;5;%dm" % palette[shade])
                active_shade = shade
            parts.append(chr(PUA_START + mask))
        lines.append("".join(parts))
    return "\n".join(lines)


def terminal_size(args):
    actual = shutil.get_terminal_size((80, 24))
    columns = args.columns or actual.columns
    # Reserve no status line: alternate-screen mode gives the animation the lot.
    rows = args.rows or actual.lines
    if columns < 2 or rows < 2:
        raise SystemExit("terminal must be at least 2 columns by 2 rows")
    return columns, rows


def animate(args):
    columns, rows = terminal_size(args)
    px_width, px_height = columns * 2, rows * 4
    count = args.flakes if args.flakes is not None else max(20, (px_width * px_height) // 110)
    flakes = [Flake(px_width, px_height, initial=True) for _ in range(count)]
    start = previous = time.monotonic()
    frame = 0

    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        while args.frames == 0 or frame < args.frames:
            deadline = start + (frame + 1) / args.fps
            now = time.monotonic()
            # Fixed simulation steps prevent scheduler jitter from becoming
            # uneven flake displacement. The deadline still follows wall time.
            dt = 1.0 / args.fps
            previous = now
            elapsed = now - start
            survivors = []
            for flake in flakes:
                if flake.step(dt, elapsed, px_width, px_height, args.wind):
                    survivors.append(flake)
            while len(survivors) < count:
                survivors.append(Flake(px_width, px_height))
            flakes = survivors
            # DEC mode 2026 asks VTE to present the full frame atomically.
            sys.stdout.write("\x1b[?2026h\x1b[H" + frame_text(flakes, columns, rows) + "\x1b[?2026l")
            sys.stdout.flush()
            frame += 1
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=float, default=30.0, help="frames per second (default: 30)")
    parser.add_argument("--flakes", type=int, help="flake count (default: based on screen area)")
    parser.add_argument("--wind", type=float, default=0.7, help="horizontal virtual pixels/second")
    parser.add_argument("--columns", type=int, help="override terminal columns (useful for tests)")
    parser.add_argument("--rows", type=int, help="override terminal rows (useful for tests)")
    parser.add_argument("--frames", type=int, default=0, help="stop after N frames; 0 runs until Ctrl-C")
    args = parser.parse_args()
    if args.fps <= 0 or (args.flakes is not None and args.flakes < 0) or args.frames < 0:
        parser.error("fps must be positive; flakes and frames must be non-negative")
    return args


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        animate(parse_args())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
