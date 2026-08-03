#!/usr/bin/env python3
"""Create a text font with square glyphs at Unicode Braille and PUA aliases."""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont


BRAILLE_FIRST = 0x2800
PUA_FIRST = 0xE000
COUNT = 256
FAMILY = "Square Braille Unicode Text Seamless"
FULL_NAME = FAMILY
POSTSCRIPT_NAME = "SquareBrailleUnicodeTextSeamless-Regular"
VERSION = "Version 1.3"
DESCRIPTION = (
    "Text-capable monospaced terminal font with seamless square-cell Braille "
    "at official Unicode Braille Patterns U+2800-U+28FF and compatibility "
    "aliases at Private Use Area U+E000-U+E0FF."
)


def replace_names(font: TTFont) -> None:
    replacements = {
        1: FAMILY,
        2: "Regular",
        3: f"1.3;Square Braille Unicode Text Seamless;Regular",
        4: FULL_NAME,
        5: VERSION,
        6: POSTSCRIPT_NAME,
        10: DESCRIPTION,
        16: FAMILY,
        17: "Regular",
    }
    table = font["name"]
    for record in table.names:
        if record.nameID in replacements:
            table.setName(replacements[record.nameID], record.nameID,
                          record.platformID, record.platEncID, record.langID)
    # Ensure both common Windows and Macintosh name encodings are present.
    for name_id, value in replacements.items():
        table.setName(value, name_id, 3, 1, 0x409)
        table.setName(value, name_id, 1, 0, 0)


def build(source: Path, output: Path) -> None:
    font = TTFont(source, recalcBBoxes=False, recalcTimestamp=False)
    best = font.getBestCmap()
    missing = [PUA_FIRST + offset for offset in range(COUNT)
               if PUA_FIRST + offset not in best]
    if missing:
        raise SystemExit(f"source lacks PUA glyph {missing[0]:#06x}")

    changed_tables = 0
    for subtable in font["cmap"].tables:
        if not subtable.isUnicode():
            continue
        if not all(PUA_FIRST + offset in subtable.cmap for offset in range(COUNT)):
            continue
        for offset in range(COUNT):
            subtable.cmap[BRAILLE_FIRST + offset] = subtable.cmap[PUA_FIRST + offset]
        changed_tables += 1
    if not changed_tables:
        raise SystemExit("no Unicode cmap subtable contains the complete PUA mapping")

    replace_names(font)
    output.parent.mkdir(parents=True, exist_ok=True)
    font.save(output, reorderTables=False)
    font.close()
    print(f"mapped 256 Unicode Braille codepoints in {changed_tables} cmap tables")
    print(f"wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
