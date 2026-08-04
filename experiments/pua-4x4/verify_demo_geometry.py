#!/usr/bin/env python3
"""Verify demo raster geometry independently of font rendering."""

from collections import defaultdict

from pua4x4 import bit_for_cell
from pua4x4_demo import Canvas


def decode(canvas):
    pixels = set()
    for character_row, row in enumerate(canvas.masks):
        for character_column, mask in enumerate(row):
            for pixel_row in range(4):
                for pixel_column in range(4):
                    bit = bit_for_cell(pixel_row, pixel_column)
                    if mask & (1 << bit):
                        pixels.add(
                            (
                                character_column * 4 + pixel_column,
                                character_row * 4 + pixel_row,
                            )
                        )
    return pixels


def diagonal(width=240, height=48, descending=True):
    canvas = Canvas(width, height)
    if descending:
        canvas.line(0, 0, width - 1, height - 1)
    else:
        canvas.line(0, height - 1, width - 1, 0)
    return decode(canvas)


def row_spans(pixels, height):
    rows = defaultdict(list)
    for x, y in pixels:
        rows[y].append(x)
    spans = []
    for y in range(height):
        xs = sorted(rows[y])
        assert xs == list(range(xs[0], xs[-1] + 1)), (y, xs)
        spans.append((xs[0], xs[-1]))
    return spans


def main():
    width, height = 240, 48
    down = diagonal(width, height, True)
    up = diagonal(width, height, False)

    assert len(down) == width
    assert len(up) == width
    assert up == {(x, height - 1 - y) for x, y in down}
    assert down == {(width - 1 - x, height - 1 - y) for x, y in down}

    spans = row_spans(down, height)
    lengths = [end - start + 1 for start, end in spans]
    assert lengths[0] == lengths[-1] == 3
    assert set(lengths[1:-1]) == {5, 6}
    assert sum(lengths) == width

    print("PASS: PUA 4x4 demo diagonal geometry")
    print(f"  virtual canvas: {width} x {height}")
    print(f"  unique diagonal pixels: {len(down)}")
    print("  mirror symmetry: exact")
    print(f"  row run lengths: {lengths}")


if __name__ == "__main__":
    main()
