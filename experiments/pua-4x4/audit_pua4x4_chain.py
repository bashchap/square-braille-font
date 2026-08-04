#!/usr/bin/env python3
"""Independent, machine-readable audit of the complete PUA 4x4 mapping chain."""

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


PART_SIZE = 32768
P0_BASE = 0xF0000
P1_BASE = 0x100000


def expected_codepoint(mask):
    if not 0 <= mask <= 0xFFFF:
        raise ValueError(mask)
    return P0_BASE + mask if mask < 0x8000 else P1_BASE + mask - 0x8000


def expected_bits(mask):
    return {bit for bit in range(16) if mask & (1 << bit)}


def bitmap(mask):
    return [
        "".join("#" if mask & (1 << (row * 4 + (3 - column))) else "."
                for column in range(4))
        for row in range(4)
    ]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_component_bounds(bit, overfill=100):
    row, numeric_column = divmod(bit, 4)
    column = 3 - numeric_column
    x_min, x_max = column * 125, (column + 1) * 125
    y_max, y_min = 800 - row * 250, 800 - (row + 1) * 250
    if column == 0:
        x_min -= overfill
    if column == 3:
        x_max += overfill
    if row == 0:
        y_max += overfill
    if row == 3:
        y_min -= overfill
    return [x_min, y_min, x_max, y_max]


def audit_font(path, part, edge_overfill):
    font = TTFont(path, lazy=False)
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()
    glyf = font["glyf"]
    start_mask = part * PART_SIZE
    start_cp = P0_BASE if part == 0 else P1_BASE
    format12 = any(table.format == 12 for table in font["cmap"].tables)
    assert format12
    assert font["maxp"].numGlyphs == 32786
    assert font["head"].unitsPerEm == 1000
    assert font["hhea"].ascent == 800
    assert font["hhea"].descent == -200
    assert font["hhea"].lineGap == 0

    component_bounds = []
    for bit in range(16):
        name = order[2 + bit]
        glyph = glyf[name]
        actual = [glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax]
        expected = expected_component_bounds(bit, edge_overfill)
        assert actual == expected, (bit, actual, expected)
        component_bounds.append({"bit": bit, "actual": actual, "expected": expected})

    for offset in range(PART_SIZE):
        mask = start_mask + offset
        codepoint = start_cp + offset
        assert codepoint == expected_codepoint(mask)
        glyph_name = cmap[codepoint]
        assert font.getGlyphID(glyph_name) == 18 + offset
        glyph = glyf[glyph_name]
        if mask == 0:
            actual = set()
            assert not glyph.isComposite() and glyph.numberOfContours == 0
        else:
            assert glyph.isComposite()
            actual = {font.getGlyphID(component.glyphName) - 2
                      for component in glyph.components}
            assert all(component.getComponentInfo()[1] == (1, 0, 0, 1, 0, 0)
                       for component in glyph.components)
        assert actual == expected_bits(mask), (mask, actual, expected_bits(mask))
        assert font["hmtx"].metrics[glyph_name] == (500, 0)

    result = {
        "part": part,
        "file": str(path),
        "sha256": sha256(path),
        "mask_range": [start_mask, start_mask + PART_SIZE - 1],
        "codepoint_range": [start_cp, start_cp + PART_SIZE - 1],
        "glyph_count": font["maxp"].numGlyphs,
        "format_12_cmap": format12,
        "component_bounds": component_bounds,
        "patterns_verified": PART_SIZE,
    }
    font.close()
    return result


def geometry_mask(character_column, character_row, tick):
    mask = 0
    for local_y in range(4):
        for local_x in range(4):
            x = character_column * 4 + local_x
            y = character_row * 4 + local_y
            if (x - y - tick) % 13 in (0, 1):
                mask |= 1 << (local_y * 4 + (3 - local_x))
    return mask


def audit_geometry():
    occurrences = {}
    for character_row in range(13):
        for character_column in range(13):
            for tick in range(13):
                mask = geometry_mask(character_column, character_row, tick)
                occurrences.setdefault(mask, 0)
                occurrences[mask] += 1

                # Independently decode the mask and compare every local pixel
                # with the analytic predicate that generated it.
                for local_y in range(4):
                    for local_x in range(4):
                        x = character_column * 4 + local_x
                        y = character_row * 4 + local_y
                        analytic = (x - y - tick) % 13 in (0, 1)
                        decoded = bool(mask & (1 << (local_y * 4 + (3 - local_x))))
                        assert decoded == analytic

    return [
        {
            "mask": mask,
            "mask_hex": f"0x{mask:04X}",
            "part": mask >> 15,
            "codepoint": expected_codepoint(mask),
            "codepoint_hex": f"U+{expected_codepoint(mask):06X}",
            "bitmap": bitmap(mask),
            "occurrences_in_13x13x13_phase_audit": count,
        }
        for mask, count in sorted(occurrences.items())
    ]


def mask_record(mask):
    return {
        "mask": mask,
        "mask_hex": f"0x{mask:04X}",
        "part": mask >> 15,
        "codepoint": expected_codepoint(mask),
        "codepoint_hex": f"U+{expected_codepoint(mask):06X}",
        "bits": sorted(expected_bits(mask)),
        "bitmap": bitmap(mask),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font_dir", type=Path, nargs="?", default=Path("build"))
    parser.add_argument("--output", type=Path, default=Path("output/audit/pua4x4-chain-audit.json"))
    parser.add_argument("--edge-overfill", type=int, default=0)
    args = parser.parse_args()
    parts = [
        audit_font(args.font_dir / "PUA4x4Part0.ttf", 0, args.edge_overfill),
        audit_font(args.font_dir / "PUA4x4Part1.ttf", 1, args.edge_overfill),
    ]
    boundary = [mask_record(mask) for mask in
                (0x0000, 0x0001, 0x0008, 0x7FFE, 0x7FFF,
                 0x8000, 0x8001, 0x8C63, 0xC631, 0xFFFE, 0xFFFF)]
    geometry = audit_geometry()
    report = {
        "audit": "Independent PUA 4x4 mathematical-to-TrueType chain",
        "status": "PASS",
        "edge_overfill": args.edge_overfill,
        "mapping": "bit = 4 * local_y + (3 - local_x)",
        "part_formula": {
            "P0": "mask < 0x8000: codepoint = 0xF0000 + mask",
            "P1": "mask >= 0x8000: codepoint = 0x100000 + (mask - 0x8000)",
        },
        "parts": parts,
        "patterns_verified": sum(part["patterns_verified"] for part in parts),
        "unique_codepoints_verified": len({expected_codepoint(mask) for mask in range(65536)}),
        "boundary_samples": boundary,
        "geometry_test": {
            "predicate": "(virtual_x - virtual_y - tick) mod 13 is 0 or 1",
            "phase_cases_verified": 13 * 13 * 13,
            "decode_mismatches": 0,
            "unique_masks": geometry,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {report['patterns_verified']:,} patterns and "
          f"{report['unique_codepoints_verified']:,} unique codepoints")
    print(f"PASS: {report['geometry_test']['phase_cases_verified']:,} geometry phase cases, "
          "zero decode mismatches")
    print(args.output)


if __name__ == "__main__":
    main()
