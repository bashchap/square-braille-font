#!/usr/bin/env python3
"""Verify one-left-key trail movement selects one adjacent MSB-left bit."""

import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "demos4x4"))

from pua4x4_backend import codepoint_to_mask  # noqa: E402
from trail import cursor_coordinates, render, render_status  # noqa: E402


def emitted_masks(picture):
    masks = []
    for character in picture:
        value = ord(character)
        if 0xF0000 <= value <= 0xF7FFF or 0x100000 <= value <= 0x107FFF:
            masks.append(codepoint_to_mask(value))
    return masks


def decode(masks, columns):
    pixels = set()
    for index, mask in enumerate(masks):
        cell_y, cell_x = divmod(index, columns)
        for bit in range(16):
            if mask & (1 << bit):
                local_y, numeric_column = divmod(bit, 4)
                local_x = 3 - numeric_column
                pixels.add((cell_x * 4 + local_x, cell_y * 4 + local_y))
    return pixels


def main():
    position = cursor_coordinates(13, 10)
    assert position == {
        "terminal_row": 6,
        "terminal_column": 4,
        "virtual_row": 10,
        "virtual_column": 13,
        "bit_position": 10,
    }, position
    status = render_status(13, 10)
    assert "Terminal row: 6  column: 4" in status
    assert "Virtual row: 10  column: 13" in status
    assert "Bit position: 10" in status

    width, height = 12, 4
    columns = width // 4
    # One isolated cursor moving left through and across a character boundary.
    for x in range(10, -1, -1):
        masks = emitted_masks(render(width, height, [], (x, 1)))
        assert len(masks) == columns
        assert decode(masks, columns) == {(x, 1)}, (x, masks)
        cell_x, local_x = divmod(x, 4)
        expected = 1 << (4 + (3 - local_x))
        assert masks[cell_x] == expected, (x, masks[cell_x], expected)

    # The accumulated trail must add exactly one neighboring virtual pixel per
    # left-key press; it must never invent or skip a position.
    trail = []
    for x in range(10, -1, -1):
        trail.append((x, 1))
        masks = emitted_masks(render(width, height, trail, (x, 1)))
        assert decode(masks, columns) == set(trail), (x, masks)

    print("PASS: isolated cursor selects the exact adjacent bit for 11 left steps")
    print("PASS: accumulated trail adds one and only one virtual pixel per step")
    print("PASS: movement crosses character boundaries without a codepoint jump")
    print("PASS: status reports one-based terminal coordinates and zero-based virtual coordinates/bit")


if __name__ == "__main__":
    main()
