#!/usr/bin/env python3
"""Draw a centered filled 180x120 RGB triangle, one virtual pixel at a time."""

import argparse
import shutil
import sys
import time


from pua4x4_backend import DOT_BIT, mask_to_codepoint


def triangle_pixels(screen_width, screen_height):
    if screen_width < 180 or screen_height < 120:
        raise SystemExit("terminal virtual framebuffer must be at least 180x120 pixels")
    left = (screen_width - 180) // 2
    top = (screen_height - 120) // 2
    apex_x = left + 89
    points = []
    for dy in range(120):
        amount = dy / 119
        row_left = round(apex_x + (left - apex_x) * amount)
        row_right = round(apex_x + (left + 179 - apex_x) * amount)
        for x in range(row_left, row_right + 1):
            # Barycentric-style vertex colors: red apex, green lower-left,
            # blue lower-right.
            horizontal = 0.5 if row_right == row_left else (x - row_left) / (row_right - row_left)
            red = round(255 * (1 - amount))
            green = round(255 * amount * (1 - horizontal))
            blue = round(255 * amount * horizontal)
            points.append(((x, top + dy), (red, green, blue)))
    return points


def cell_colors(points):
    totals = {}
    for (x, y), color in points:
        key = (y // 4, x // 4)
        entry = totals.setdefault(key, [0, 0, 0, 0])
        entry[0] += color[0]
        entry[1] += color[1]
        entry[2] += color[2]
        entry[3] += 1
    return {key: tuple(round(channel / value[3]) for channel in value[:3])
            for key, value in totals.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pps", type=float, default=3000.0, help="pixels drawn per second")
    parser.add_argument("--hold", type=float, default=5.0, help="seconds to retain completed triangle")
    args = parser.parse_args()
    if args.pps <= 0 or args.hold < 0:
        parser.error("pps must be positive and hold must be non-negative")

    size = shutil.get_terminal_size((80, 24))
    points = triangle_pixels(size.columns * 4, size.lines * 4)
    colors = cell_colors(points)
    masks = [[0] * size.columns for _ in range(size.lines)]
    interval = 1.0 / args.pps
    start = time.monotonic()
    sys.stdout.write("\x1b]0;PUA 4x4 — Filled 180x120 RGB Triangle\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        for count, ((x, y), _) in enumerate(points, 1):
            cell_x, sub_x = divmod(x, 4)
            cell_y, sub_y = divmod(y, 4)
            masks[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
            red, green, blue = colors[(cell_y, cell_x)]
            glyph = chr(mask_to_codepoint(masks[cell_y][cell_x]))
            sys.stdout.write(
                "\x1b[?2026h\x1b[%d;%dH\x1b[38;2;%d;%d;%dm%s\x1b[?2026l"
                % (cell_y + 1, cell_x + 1, red, green, blue, glyph)
            )
            if count % 32 == 0:
                sys.stdout.flush()
            delay = start + count * interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        sys.stdout.flush()
        if args.hold:
            time.sleep(args.hold)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
