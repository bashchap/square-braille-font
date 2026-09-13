#!/usr/bin/env python3
"""Render deterministic v0.4 terminal probes and record their circumstances."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


P0_BASE = 0xF0000
P1_BASE = 0x100000


def codepoint(mask: int) -> int:
    if mask < 0x8000:
        return P0_BASE + mask
    return P1_BASE + mask - 0x8000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    terminal = shutil.get_terminal_size((80, 24))
    columns = min(80, terminal.columns)
    rows = min(20, terminal.lines)
    full = chr(codepoint(0xFFFF))
    one_bits = "".join(chr(codepoint(mask)) for mask in (0x0008, 0x0004, 0x0002, 0x0001))
    report = {
        "probe": "MATE Terminal v0.4 candidate deterministic field",
        "terminal_columns": terminal.columns,
        "terminal_rows": terminal.lines,
        "solid_columns": columns,
        "solid_rows": rows,
        "solid_mask": "0xFFFF",
        "solid_codepoint": f"U+{codepoint(0xFFFF):06X}",
        "one_bit_masks_left_to_right": ["0x0008", "0x0004", "0x0002", "0x0001"],
        "expectation": "solid field has no internal background pixels; one-bit marks occupy local x=0,1,2,3",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    sys.stdout.write("\x1b]0;PUA 4x4 v0.4 Candidate Terminal Probe\x07")
    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l\x1b[0m\x1b[38;2;255;255;255m")
    for row in range(rows):
        if row:
            sys.stdout.write("\r\n")
        sys.stdout.write(full * columns)
    # The one-bit strip is placed below the field when the terminal has room.
    if terminal.lines > rows + 2:
        sys.stdout.write(f"\x1b[{rows + 2};1H" + one_bits)
    sys.stdout.flush()
    try:
        time.sleep(args.hold)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
