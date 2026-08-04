#!/usr/bin/env python3
"""3D starfield fly-through on the PUA 4x4 virtual framebuffer."""

import argparse
import math
import random
import shutil
import sys
import time


from pua4x4_backend import DOT_BIT, mask_to_codepoint
PALETTE = (17, 27, 39, 51, 159, 231)  # deep blue through white


class Star:
    def __init__(self, initial=True):
        self.reset(initial)

    def reset(self, initial=False):
        angle = random.random() * math.tau
        radius = math.sqrt(random.random())
        self.x = math.cos(angle) * radius
        self.y = math.sin(angle) * radius
        self.z = random.uniform(0.08, 1.0) if initial else 1.0
        self.rate = random.uniform(0.16, 0.34)


def project(star, width, height, z=None):
    z = star.z if z is None else z
    focal = min(width, height) * 0.72
    return width / 2 + star.x * focal / z, height / 2 + star.y * focal / z


def put_pixel(masks, shades, width, height, x, y, shade):
    x, y = int(round(x)), int(round(y))
    if not (0 <= x < width and 0 <= y < height):
        return
    cell_x, sub_x = divmod(x, 4)
    cell_y, sub_y = divmod(y, 4)
    masks[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
    shades[cell_y][cell_x] = max(shades[cell_y][cell_x], shade)


def draw_line(masks, shades, width, height, x0, y0, x1, y1, shade):
    steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
    for step in range(steps + 1):
        amount = step / steps
        put_pixel(masks, shades, width, height,
                  x0 + (x1 - x0) * amount, y0 + (y1 - y0) * amount, shade)


def render(stars, columns, rows, dt):
    width, height = columns * 4, rows * 4
    masks = [[0] * columns for _ in range(rows)]
    shades = [[0] * columns for _ in range(rows)]
    for star in stars:
        x, y = project(star, width, height)
        tail_z = min(1.1, star.z + star.rate * dt * 2.5)
        tx, ty = project(star, width, height, tail_z)
        shade = min(len(PALETTE) - 1, int((1.0 - star.z) * len(PALETTE)))
        draw_line(masks, shades, width, height, tx, ty, x, y, shade)
        if star.z < 0.18:
            put_pixel(masks, shades, width, height, x + 1, y, shade)
            put_pixel(masks, shades, width, height, x, y + 1, shade)

    lines = []
    for row_masks, row_shades in zip(masks, shades):
        parts, active = [], None
        for mask, shade in zip(row_masks, row_shades):
            if mask and shade != active:
                parts.append("\x1b[38;5;%dm" % PALETTE[shade])
                active = shade
            parts.append(chr(mask_to_codepoint(mask)))
        lines.append("".join(parts))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--stars", type=int, help="default scales with terminal area")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--frames", type=int, default=0, help="0 runs until Ctrl-C")
    args = parser.parse_args()
    if args.fps <= 0 or args.speed <= 0 or args.frames < 0:
        parser.error("fps and speed must be positive; frames must be non-negative")
    if args.seed is not None:
        random.seed(args.seed)

    size = shutil.get_terminal_size((80, 24))
    count = args.stars if args.stars is not None else max(80, size.columns * size.lines // 7)
    stars = [Star() for _ in range(count)]
    dt = 1.0 / args.fps
    start = time.monotonic()
    frame = 0
    sys.stdout.write("\x1b]0;PUA 4x4 — Starfield\x07\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        while args.frames == 0 or frame < args.frames:
            deadline = start + (frame + 1) * dt
            for star in stars:
                star.z -= star.rate * args.speed * dt
                if star.z <= 0.035:
                    star.reset()
                x, y = project(star, size.columns * 4, size.lines * 4)
                if x < -3 or x >= size.columns * 4 + 3 or y < -3 or y >= size.lines * 4 + 3:
                    star.reset()
            sys.stdout.write("\x1b[?2026h\x1b[H" + render(stars, size.columns, size.lines, dt) + "\x1b[?2026l")
            sys.stdout.flush()
            frame += 1
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
