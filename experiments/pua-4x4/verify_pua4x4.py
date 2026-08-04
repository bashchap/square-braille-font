#!/usr/bin/env python3
"""Exhaustively verify the mathematical and TrueType PUA 4x4 mappings."""

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTFont

from pua4x4 import (
    PART_PATTERN_COUNT,
    PARTS,
    TOTAL_PATTERN_COUNT,
    codepoint_to_mask,
    mask_to_codepoint,
)


COMPONENT_GLYPH_IDS = set(range(2, 18))
PATTERN_GLYPH_ID_START = 18


def component_bits(font, glyph_name):
    glyph = font["glyf"][glyph_name]
    if not glyph.isComposite():
        if glyph.numberOfContours == 0:
            return set()
        raise AssertionError("pattern glyph %s is neither empty nor composite" % glyph_name)
    bits = set()
    for component in glyph.components:
        glyph_id = font.getGlyphID(component.glyphName)
        if glyph_id not in COMPONENT_GLYPH_IDS:
            raise AssertionError("unexpected component glyph ID %d" % glyph_id)
        bits.add(glyph_id - 2)
    return bits


def verify_part(spec, path):
    font = TTFont(path, lazy=False)
    expected_glyphs = 1 + 1 + 16 + PART_PATTERN_COUNT
    assert font["maxp"].numGlyphs == expected_glyphs
    assert font["head"].unitsPerEm == 1000
    assert font["hhea"].ascent == 800
    assert font["hhea"].descent == -200
    assert font["hhea"].lineGap == 0
    assert any(table.format == 12 for table in font["cmap"].tables)

    cmap = font.getBestCmap()
    expected_codepoints = set(
        range(spec["codepoint_start"], spec["codepoint_start"] + PART_PATTERN_COUNT)
    )
    expected_codepoints.add(0x20)
    assert set(cmap) == expected_codepoints

    assert font["glyf"][cmap[0x20]].numberOfContours == 0
    assert font["hmtx"].metrics[cmap[0x20]][0] == 500

    for offset, codepoint in enumerate(
        range(spec["codepoint_start"], spec["codepoint_start"] + PART_PATTERN_COUNT)
    ):
        mask = spec["mask_start"] + offset
        assert codepoint == mask_to_codepoint(mask)
        assert codepoint_to_mask(codepoint) == mask
        glyph_name = cmap[codepoint]
        assert font.getGlyphID(glyph_name) == PATTERN_GLYPH_ID_START + offset
        actual_bits = component_bits(font, glyph_name)
        expected_bits = {bit for bit in range(16) if mask & (1 << bit)}
        assert actual_bits == expected_bits, (
            "mask %04X: expected %r, found %r" % (mask, expected_bits, actual_bits)
        )
        assert font["hmtx"].metrics[glyph_name][0] == 500
    font.close()
    print(
        "PASS Part %d: masks %04X..%04X, codepoints U+%X..U+%X"
        % (
            spec["part"],
            spec["mask_start"],
            spec["mask_start"] + PART_PATTERN_COUNT - 1,
            spec["codepoint_start"],
            spec["codepoint_start"] + PART_PATTERN_COUNT - 1,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", type=Path, nargs="?", default=Path("build"))
    args = parser.parse_args()
    manifest_path = args.build_dir / "pua4x4-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["parts"]) == 2

    seen = set()
    for spec, entry in zip(PARTS, manifest["parts"]):
        path = args.build_dir / entry["file"]
        verify_part(spec, path)
        seen.update(
            range(spec["codepoint_start"], spec["codepoint_start"] + PART_PATTERN_COUNT)
        )
    assert len(seen) == TOTAL_PATTERN_COUNT
    assert len({mask_to_codepoint(mask) for mask in range(TOTAL_PATTERN_COUNT)}) == TOTAL_PATTERN_COUNT
    print("PASS complete PUA 4x4 mapping: 65,536 unique MSB-left patterns")


if __name__ == "__main__":
    main()
