#!/usr/bin/env python3
"""Move a virtual pixel with the arrow keys and leave a colored trail."""

import os
from pathlib import Path
import select
import shutil
import sys
import termios
import tty

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_terminal import terminal_picture

PUA_START = 0xE000
DOT_BIT = ((0, 3), (1, 4), (2, 5), (6, 7))
TRAIL_COLORS = (25, 27, 33, 39, 45, 51)
CURSOR_COLOR = 231


def read_key(fd):
    first = os.read(fd, 1)
    if first != b"\x1b":
        return first
    # Arrow keys normally arrive as ESC [ A/B/C/D. Briefly collect the rest
    # without ever leaving the interface blocked on an incomplete sequence.
    sequence = bytearray(first)
    while len(sequence) < 3 and select.select([fd], [], [], 0.03)[0]:
        sequence.extend(os.read(fd, 1))
    return bytes(sequence)


def render(width, height, trail, cursor):
    columns, rows = width // 2, height // 4
    masks = [[0] * columns for _ in range(rows)]
    shades = [[0] * columns for _ in range(rows)]

    def put(x, y, shade):
        if not (0 <= x < width and 0 <= y < height):
            return
        cell_x, sub_x = divmod(x, 2)
        cell_y, sub_y = divmod(y, 4)
        masks[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
        shades[cell_y][cell_x] = max(shades[cell_y][cell_x], shade)

    total = max(1, len(trail) - 1)
    for index, (x, y) in enumerate(trail):
        put(x, y, min(len(TRAIL_COLORS) - 1, index * len(TRAIL_COLORS) // total))
    put(cursor[0], cursor[1], len(TRAIL_COLORS))

    palette = TRAIL_COLORS + (CURSOR_COLOR,)
    colors = [[palette[shade] for shade in row] for row in shades]
    # tty.setraw() disables the terminal driver's NL -> CRLF conversion.
    # Emit CRLF explicitly or each framebuffer row begins at the prior column,
    # causing autowrap plus LF to skip alternating terminal rows.
    return terminal_picture(
        masks, colors, columns, rows, mapping="square-alias",
        colour_mode="indexed", blank_glyph=True, carriage_return=True,
        reset_at_end=False)


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("trail.py requires an interactive terminal")
    size = shutil.get_terminal_size((80, 24))
    width, height = size.columns * 2, size.lines * 4
    x, y = width // 2, height // 2
    trail = [(x, y)]
    pen_down = True
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    movements = {
        b"\x1b[A": (0, -1),
        b"\x1b[B": (0, 1),
        b"\x1b[C": (1, 0),
        b"\x1b[D": (-1, 0),
    }

    sys.stdout.write("\x1b]0;PUA Square Braille — Trail\x07\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            sys.stdout.write("\x1b[?2026h\x1b[H" + render(width, height, trail, (x, y)) + "\x1b[?2026l")
            sys.stdout.flush()
            key = read_key(fd)
            if key.lower() == b"q":
                break
            if key.lower() == b"c":
                trail = [(x, y)] if pen_down else []
                continue
            if key == b" ":
                pen_down = not pen_down
                if pen_down:
                    trail.append((x, y))
                continue
            if key in movements:
                dx, dy = movements[key]
                x = min(width - 1, max(0, x + dx))
                y = min(height - 1, max(0, y + dy))
                if pen_down and (not trail or trail[-1] != (x, y)):
                    trail.append((x, y))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
