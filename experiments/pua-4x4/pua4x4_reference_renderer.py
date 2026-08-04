#!/usr/bin/env python3
"""Minimal, executable PUA 4x4 terminal renderer (standard library only)."""

import argparse
import shutil
import sys
import time


PART0_BASE = 0xF0000
PART1_BASE = 0x100000
PART_SPLIT = 0x8000


def mask_to_codepoint(mask):
    """Map one unsigned 16-bit cell mask to the project PUA convention."""
    if not 0 <= mask <= 0xFFFF:
        raise ValueError("mask must be between 0x0000 and 0xFFFF")
    if mask < PART_SPLIT:
        return PART0_BASE + mask
    return PART1_BASE + (mask - PART_SPLIT)


class Canvas:
    """A 4C x 4R virtual-pixel canvas backed by C x R cell masks."""

    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.width = columns * 4
        self.height = rows * 4
        self.masks = [[0 for _ in range(columns)] for _ in range(rows)]

    def erase(self):
        for row in self.masks:
            row[:] = [0] * self.columns

    def address(self, x, y):
        """Return cell column/row, bit index and selector for virtual (x,y)."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        cell_column, local_column = divmod(x, 4)
        cell_row, local_row = divmod(y, 4)
        bit = local_row * 4 + (3 - local_column)
        return cell_column, cell_row, bit, 1 << bit

    def plot(self, x, y, operation="set"):
        location = self.address(x, y)
        if location is None:
            return
        cell_column, cell_row, _bit, selector = location
        old = self.masks[cell_row][cell_column]
        if operation == "set":
            new = old | selector
        elif operation == "clear":
            new = old & ~selector & 0xFFFF
        elif operation == "toggle":
            new = old ^ selector
        else:
            raise ValueError("operation must be set, clear or toggle")
        self.masks[cell_row][cell_column] = new

    def line(self, x0, y0, x1, y1, operation="set"):
        """Integer Bresenham line in virtual-pixel coordinates."""
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.plot(x0, y0, operation)
            if x0 == x1 and y0 == y1:
                return
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += sx
            if doubled <= dx:
                error += dx
                y0 += sy

    def ansi_frame(self, origin_row=1, origin_column=1):
        """Encode all masks as cursor-addressed UTF-8 terminal text."""
        output = []
        for cell_row, row in enumerate(self.masks):
            ansi_row = origin_row + cell_row
            output.append(f"\x1b[{ansi_row};{origin_column}H")
            output.append("".join(chr(mask_to_codepoint(mask)) for mask in row))
        return "".join(output)


def draw_demo(canvas, phase):
    """Draw a border, diagonals and a moving cross using virtual pixels."""
    canvas.erase()
    right = canvas.width - 1
    bottom = canvas.height - 1
    canvas.line(0, 0, right, 0)
    canvas.line(right, 0, right, bottom)
    canvas.line(right, bottom, 0, bottom)
    canvas.line(0, bottom, 0, 0)
    canvas.line(0, 0, right, bottom)
    canvas.line(0, bottom, right, 0)
    moving_x = int((phase % 1.0) * right)
    moving_y = int(((phase * 0.63) % 1.0) * bottom)
    for offset in range(-5, 6):
        canvas.plot(moving_x + offset, moving_y)
        canvas.plot(moving_x, moving_y + offset)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--columns", type=int)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="0 runs until Ctrl-C")
    args = parser.parse_args()
    terminal = shutil.get_terminal_size((80, 24))
    columns = args.columns or terminal.columns
    rows = args.rows or max(1, terminal.lines - 1)
    canvas = Canvas(columns, rows)
    started = time.monotonic()
    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[?25l")
    try:
        while True:
            frame_started = time.monotonic()
            elapsed = frame_started - started
            if args.seconds and elapsed >= args.seconds:
                break
            draw_demo(canvas, elapsed * 0.18)
            sys.stdout.write(canvas.ansi_frame())
            sys.stdout.flush()
            delay = (1.0 / args.fps) - (time.monotonic() - frame_started)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
