#!/usr/bin/env python3
"""Display every generated graphics glyph, with its mask and codepoint.

The Square Braille catalog contains 256 patterns.  The PUA 4x4 catalog contains
65,536 patterns, so it is paged by default.  This program deliberately tests
the terminal's actual font selection: it prints Unicode characters rather than
rendering outlines itself.
"""

from __future__ import annotations

import argparse
import shutil
import sys


def pua4_codepoint(mask: int) -> int:
    if not 0 <= mask <= 0xFFFF:
        raise ValueError("PUA 4x4 mask is outside 0x0000..0xFFFF")
    return 0xF0000 + mask if mask < 0x8000 else 0x100000 + mask - 0x8000


def pages(lines, enabled: bool):
    page_height = max(4, shutil.get_terminal_size((80, 24)).lines - 2)
    for number, line in enumerate(lines, 1):
        print(line)
        if enabled and number % page_height == 0:
            try:
                answer = input("-- Enter: next page | q: quit -- ")
            except EOFError:
                return
            if answer.strip().lower().startswith("q"):
                return


def square_lines(base: int, title: str):
    yield title
    yield "Each row is MASK 00..FF; 16 generated characters per row."
    for start in range(0, 0x100, 0x10):
        glyphs = "".join(chr(base + mask) for mask in range(start, start + 16))
        yield f"{start:02X}-{start + 15:02X}  {glyphs}"


def pua4_lines():
    yield "PUA 4x4 v0.6 Candidate 6: all 65,536 masks"
    yield "MSB-left rows: 3210 / 7654 / BA98 / FEDC; 16 glyphs per line."
    for start in range(0, 0x10000, 0x10):
        glyphs = "".join(chr(pua4_codepoint(mask))
                         for mask in range(start, start + 16))
        part = "P0" if start < 0x8000 else "P1"
        first = pua4_codepoint(start)
        last = pua4_codepoint(start + 15)
        yield (f"{part} mask {start:04X}-{start + 15:04X}  "
               f"U+{first:06X}-U+{last:06X}  {glyphs}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "catalog", choices=("square", "square-pua", "pua4", "all"),
        help=("square=U+2800..U+28FF; square-pua=U+E000..U+E0FF; "
              "pua4=all P0/P1 masks"))
    parser.add_argument("--no-pager", action="store_true",
                        help="write the complete catalog without prompting")
    return parser.parse_args()


def main():
    args = parse_args()
    catalogs = []
    if args.catalog in ("square", "all"):
        catalogs.append(square_lines(
            0x2800, "Square Braille official Unicode block U+2800..U+28FF"))
    if args.catalog in ("square-pua", "all"):
        catalogs.append(square_lines(
            0xE000, "Square Braille compatibility aliases U+E000..U+E0FF"))
    if args.catalog in ("pua4", "all"):
        catalogs.append(pua4_lines())
    for index, catalog in enumerate(catalogs):
        if index:
            print()
        pages(catalog, not args.no_pager and sys.stdout.isatty())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
