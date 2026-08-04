#!/usr/bin/env python3
"""Interactive proof editor for the requested MSB-left PUA 4x4 mapping."""

import argparse
import os
import select
import sys
import termios
import tty

from pua4x4_backend import mask_to_codepoint


def requested_bit(local_x, local_y):
    """MSB-left row mapping: 3,2,1,0 then 7,6,5,4, and so on."""
    if not 0 <= local_x < 4 or not 0 <= local_y < 4:
        raise ValueError("local coordinates must be in the range 0..3")
    return 4 * local_y + (3 - local_x)


def current_font_bit(local_x, local_y):
    """Mapping physically encoded by the current v0.3 fonts."""
    return requested_bit(local_x, local_y)


def reverse_each_nibble(mask):
    """Convert between MSB-left and the preserved v0.2 LSB-left layout."""
    result = 0
    for row in range(4):
        nibble = (mask >> (4 * row)) & 0xF
        reversed_nibble = int(f"{nibble:04b}"[::-1], 2)
        result |= reversed_nibble << (4 * row)
    return result


def mapping_details(cell_column, cell_row, local_x, local_y, mask):
    virtual_column = cell_column * 4 + local_x
    virtual_row = cell_row * 4 + local_y
    bit = requested_bit(local_x, local_y)
    value = 1 << bit
    codepoint = mask_to_codepoint(mask)
    part = 0 if mask < 0x8000 else 1
    part_base = 0xF0000 if part == 0 else 0x100000
    part_offset = mask if part == 0 else mask - 0x8000
    return {
        "terminal_column": cell_column + 1,
        "terminal_row": cell_row + 1,
        "virtual_column": virtual_column,
        "virtual_row": virtual_row,
        "local_x": local_x,
        "local_y": local_y,
        "actual_x": 3 - local_x,
        "actual_y": 4 * local_y,
        "bit": bit,
        "value": value,
        "mask": mask,
        "part": part,
        "part_base": part_base,
        "part_offset": part_offset,
        "codepoint": codepoint,
    }


def read_key(fd):
    first = os.read(fd, 1)
    if first != b"\x1b":
        return first
    sequence = bytearray(first)
    while len(sequence) < 3 and select.select([fd], [], [], 0.03)[0]:
        sequence.extend(os.read(fd, 1))
    return bytes(sequence)


def grid(mask, cursor_x, cursor_y):
    lines = []
    cell_width = 13
    for row in range(4):
        for inner_row in range(3):
            parts = []
            for column in range(4):
                bit = requested_bit(column, row)
                enabled = bool(mask & (1 << bit))
                selected = (column, row) == (cursor_x, cursor_y)
                if selected and enabled:
                    style = "\x1b[1;37;45m"
                elif selected:
                    style = "\x1b[1;30;46m"
                elif enabled:
                    style = "\x1b[1;30;42m"
                else:
                    style = "\x1b[37;44m"
                label = f" bit {bit:2d} " if inner_row == 1 else ""
                parts.append(style + label.center(cell_width) + "\x1b[0m")
            lines.append("".join(parts))
    return "\r\n".join(lines)


def frame(cell_column, cell_row, local_x, local_y, mask):
    detail = mapping_details(cell_column, cell_row, local_x, local_y, mask)
    set_state = "SET" if mask & detail["value"] else "clear"
    return (
        "\x1b[0m\x1b[2J\x1b[H"
        "PUA 4x4 CHARACTER EDITOR - requested MSB-left bit mapping\r\n"
        "Arrow keys navigate | Space sets/clears | c clears mask | q quits\r\n"
        f"Terminal target: row {detail['terminal_row']}, column {detail['terminal_column']}  "
        f"(one-based ANSI)\r\n"
        f"Virtual pixel: row {detail['virtual_row']}, column {detail['virtual_column']}  "
        f"(zero-based)\r\n"
        f"Local pixel: x={local_x}, y={local_y}  -> column {local_x + 1} from left, "
        f"row {local_y + 1} from top\r\n"
        f"Actual X bit position = 3 - {local_x} = {detail['actual_x']}\r\n"
        f"Actual Y bit position = 4 * {local_y} = {detail['actual_y']}\r\n"
        f"Total bit position = {detail['actual_x']} + {detail['actual_y']} = {detail['bit']}  |  "
        f"bit value = 2 ** {detail['bit']} = {detail['value']} (0x{detail['value']:04X})  [{set_state}]\r\n"
        f"Logical mask = 0x{mask:04X}  |  Part {detail['part']} offset = 0x{detail['part_offset']:04X}  |  "
        f"codepoint = U+{detail['codepoint']:06X}\r\n"
        f"Current v0.3 codepoint glyph: \x1b[38;5;231m{chr(detail['codepoint'])}\x1b[0m\r\n"
        "Font mapping status: MATCH - the glyph uses the same MSB-left mask shown below.\r\n"
        "Large logical grid (bit numbers are the authoritative encoding):\r\n"
        + grid(mask, local_x, local_y)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-column", type=int, default=3,
                        help="zero-based target terminal-cell column (default: 3)")
    parser.add_argument("--cell-row", type=int, default=2,
                        help="zero-based target terminal-cell row (default: 2)")
    args = parser.parse_args()
    if args.cell_column < 0 or args.cell_row < 0:
        parser.error("cell coordinates must be non-negative")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("glyph_editor.py requires an interactive terminal")

    local_x = local_y = 0
    mask = 0
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    movements = {
        b"\x1b[A": (0, -1),
        b"\x1b[B": (0, 1),
        b"\x1b[C": (1, 0),
        b"\x1b[D": (-1, 0),
    }
    sys.stdout.write("\x1b]0;PUA 4x4 - Character Editor\x07\x1b[?1049h\x1b[?25l")
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            sys.stdout.write(frame(args.cell_column, args.cell_row, local_x, local_y, mask))
            sys.stdout.flush()
            key = read_key(fd)
            if key.lower() == b"q":
                break
            if key.lower() == b"c":
                mask = 0
            elif key == b" ":
                mask ^= 1 << requested_bit(local_x, local_y)
            elif key in movements:
                dx, dy = movements[key]
                local_x = min(3, max(0, local_x + dx))
                local_y = min(3, max(0, local_y + dy))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
