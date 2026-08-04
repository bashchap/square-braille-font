#!/usr/bin/env python3
"""Terminal mapping and virtual-resolution proof for PUA 4x4."""

import argparse
import shutil

from pua4x4 import bit_for_cell, mask_to_codepoint


class Canvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.masks = [[0 for _ in range((width + 3) // 4)] for _ in range((height + 3) // 4)]

    def set(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        character_row, pixel_row = divmod(y, 4)
        character_column, pixel_column = divmod(x, 4)
        self.masks[character_row][character_column] |= 1 << bit_for_cell(
            pixel_row, pixel_column
        )

    def line(self, x0, y0, x1, y1):
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy

    def render(self):
        return "\n".join(
            "".join(chr(mask_to_codepoint(mask)) for mask in row)
            for row in self.masks
        )


def mapping_probe():
    print("PUA 4x4 — one-bit MSB-left row mapping")
    print("Each group below is one character containing four adjacent bit positions.\n")
    for row in range(4):
        masks = [1 << bit_for_cell(row, column) for column in range(4)]
        print(
            "row %d, bits %2d..%2d:  %s"
            % (
                row,
                row * 4,
                row * 4 + 3,
                "  ".join(chr(mask_to_codepoint(mask)) for mask in masks),
            )
        )
    print("\nSplit boundary:")
    for mask in (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF):
        print("mask %04X  U+%06X  %s" % (mask, mask_to_codepoint(mask), chr(mask_to_codepoint(mask))))


def visual_probe(columns, rows):
    virtual_width = columns * 4
    virtual_height = rows * 4
    canvas = Canvas(virtual_width, virtual_height)
    canvas.line(0, 0, virtual_width - 1, virtual_height - 1)
    canvas.line(virtual_width - 1, 0, 0, virtual_height - 1)
    canvas.line(0, virtual_height // 2, virtual_width - 1, virtual_height // 2)
    canvas.line(virtual_width // 2, 0, virtual_width // 2, virtual_height - 1)
    print("PUA 4x4 virtual canvas: %d x %d pixels" % (virtual_width, virtual_height))
    print(canvas.render())
    print("\nFull-cell seam field:")
    full = chr(mask_to_codepoint(0xFFFF))
    for _ in range(min(rows, 8)):
        print(full * columns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--columns", type=int)
    parser.add_argument("--rows", type=int, default=12)
    parser.add_argument("--mapping-only", action="store_true")
    parser.add_argument("--seam-only", action="store_true")
    args = parser.parse_args()
    terminal_columns = shutil.get_terminal_size((80, 24)).columns
    columns = args.columns or max(8, min(60, terminal_columns - 2))
    if args.seam_only:
        full = chr(mask_to_codepoint(0xFFFF))
        print("\n".join(full * columns for _ in range(max(1, args.rows))))
        return
    mapping_probe()
    if args.mapping_only:
        return
    print()
    visual_probe(columns, max(4, args.rows))


if __name__ == "__main__":
    main()
