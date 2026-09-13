#!/usr/bin/env python3
"""Display deterministic differently-coloured PUA 4x4 boundary probes."""

from __future__ import annotations

import argparse
import sys
import time


def codepoint(mask: int) -> int:
    return 0xF0000 + mask if mask < 0x8000 else 0x100000 + mask - 0x8000


def glyph(mask: int, red: int, green: int, blue: int) -> str:
    return f"\x1b[38;2;{red};{green};{blue}m{chr(codepoint(mask))}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=90.0)
    parser.add_argument("--candidate-label", default="Candidate 3")
    args = parser.parse_args()
    cyan = (0, 229, 255)
    magenta = (255, 64, 160)
    teal = (0, 80, 112)
    white = (255, 255, 255)
    lines = [
        f"PUA 4x4 {args.candidate_label.upper()} - TERMINAL MULTICOLOUR RASTER AUDIT",
        "cyan cell is emitted first; the differently-coloured right/below cell is emitted later",
        "",
        "SOLID / SOLID, HORIZONTAL:",
        "".join(glyph(0xFFFF, *cyan) + glyph(0xFFFF, *magenta) for _ in range(20)),
        "",
        "BOX / GRID, HORIZONTAL (reported right-side failure):",
        "".join(glyph(0x9F00, *cyan) + glyph(0x8888, *teal) for _ in range(20)),
        "",
        "SAME-COLOUR SOLID CONTROL (must have no black seam):",
        "".join(glyph(0xFFFF, *white) + glyph(0xFFFF, *white) for _ in range(20)),
        "",
        "VERTICAL SOLID / SOLID:",
        glyph(0xFFFF, *cyan) * 20,
        glyph(0xFFFF, *magenta) * 20,
    ]
    sys.stdout.write("\x1b]0;PUA4X4-MULTICOLOUR-RASTER-AUDIT\x07\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    for line in lines:
        sys.stdout.write("\x1b[0m" + line + "\r\n")
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
