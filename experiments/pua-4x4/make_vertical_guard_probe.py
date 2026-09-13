#!/usr/bin/env python3
"""Build a diagnostic Candidate-4 copy with vertical-only seam guard."""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont


PARTS = (
    ("PUA4x4Part0V05Candidate4.ttf", "PUA4x4Part0VerticalGuardProbe.ttf", "PUA 4x4 Part 0 Vertical Guard Probe", "PUA4x4Part0VerticalGuardProbe-Regular", 0xF0000, 0xF7FFF),
    ("PUA4x4Part1V05Candidate4.ttf", "PUA4x4Part1VerticalGuardProbe.ttf", "PUA 4x4 Part 1 Vertical Guard Probe", "PUA4x4Part1VerticalGuardProbe-Regular", 0x100000, 0x107FFF),
)


def main() -> None:
    root = Path(__file__).resolve().parent
    source_dir = root / "build-v0.5-candidate.4-strict"
    output_dir = root / "output" / "vertical-guard-probe"
    output_dir.mkdir(parents=True, exist_ok=True)
    for source_name, output_name, family, postscript, start, end in PARTS:
        font = TTFont(source_dir / source_name, recalcBBoxes=False, recalcTimestamp=False)
        cmap = font.getBestCmap()
        glyf = font["glyf"]
        for codepoint in range(start, end + 1):
            glyph = glyf[cmap[codepoint]]
            if glyph.numberOfContours <= 0:
                continue
            glyph.coordinates = type(glyph.coordinates)([
                (x, -300 if y == -200 else 900 if y == 800 else y)
                for x, y in glyph.coordinates
            ])
            glyph.recalcBounds(glyf)
        values = {
            1: family, 2: "Regular", 3: f"{postscript};vertical-guard-probe",
            4: family, 5: "Vertical guard probe", 6: postscript,
            16: family, 17: "Regular",
        }
        for name_id, value in values.items():
            font["name"].setName(value, name_id, 3, 1, 0x409)
            font["name"].setName(value, name_id, 1, 0, 0)
        output = output_dir / output_name
        font.save(output, reorderTables=True)
        font.close()
        print(output)


if __name__ == "__main__":
    main()
