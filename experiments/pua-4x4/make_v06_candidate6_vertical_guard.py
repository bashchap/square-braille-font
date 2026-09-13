#!/usr/bin/env python3
"""Build Candidate 6 with a vertical-only terminal seam guard.

Candidate 6 preserves Candidate 4's approved cmap, MSB-left bit mapping,
horizontal ownership, advance width and TrueType instructions.  It expands
only the two exterior vertical edges of graphics contours by 100 font units:
the top edge y=800 becomes y=900 and the bottom edge y=-200 becomes y=-300.
Internal 4x4 pixel boundaries and all x coordinates remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


PARTS = (
    {
        "part": 0,
        "source": "PUA4x4Part0V05Candidate4.ttf",
        "filename": "PUA4x4Part0V06Candidate6.ttf",
        "family": "PUA 4x4 Part 0 v0.6 Candidate 6",
        "postscript": "PUA4x4Part0V06Candidate6-Regular",
        "codepoint_start": 0xF0000,
        "codepoint_end": 0xF7FFF,
    },
    {
        "part": 1,
        "source": "PUA4x4Part1V05Candidate4.ttf",
        "filename": "PUA4x4Part1V06Candidate6.ttf",
        "family": "PUA 4x4 Part 1 v0.6 Candidate 6",
        "postscript": "PUA4x4Part1V06Candidate6-Regular",
        "codepoint_start": 0x100000,
        "codepoint_end": 0x107FFF,
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_names(font: TTFont, family: str, postscript: str) -> None:
    values = {
        1: family,
        2: "Regular",
        3: f"{postscript};0.6-candidate.6",
        4: family,
        5: "Version 0.6-candidate.6",
        6: postscript,
        10: (
            "PUA 4x4 graphics candidate with MSB-left mapping, strict "
            "horizontal ownership and a vertical-only 100-unit seam guard."
        ),
        16: family,
        17: "Regular",
    }
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def build_part(source_dir: Path, output_dir: Path, spec: dict) -> dict:
    source = source_dir / spec["source"]
    output = output_dir / spec["filename"]
    font = TTFont(source, recalcBBoxes=False, recalcTimestamp=False)
    cmap = font.getBestCmap()
    glyf = font["glyf"]
    changed_points = 0
    changed_glyphs = 0
    x_coordinates_changed = 0
    for codepoint in range(spec["codepoint_start"], spec["codepoint_end"] + 1):
        glyph = glyf[cmap[codepoint]]
        if glyph.numberOfContours <= 0:
            continue
        original = list(glyph.coordinates)
        guarded = []
        glyph_changed = False
        for x, y in original:
            guarded_y = -300 if y == -200 else 900 if y == 800 else y
            guarded.append((x, guarded_y))
            if guarded_y != y:
                changed_points += 1
                glyph_changed = True
        x_coordinates_changed += sum(
            1 for (old_x, _), (new_x, _) in zip(original, guarded)
            if old_x != new_x
        )
        if glyph_changed:
            changed_glyphs += 1
            glyph.coordinates = type(glyph.coordinates)(guarded)
            glyph.recalcBounds(glyf)

    replace_names(font, spec["family"], spec["postscript"])
    output_dir.mkdir(parents=True, exist_ok=True)
    font.save(output, reorderTables=True)
    font.close()
    return {
        **spec,
        "source_sha256": sha256(source),
        "sha256": sha256(output),
        "changed_glyphs": changed_glyphs,
        "changed_points": changed_points,
        "x_coordinates_changed": x_coordinates_changed,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=root / "build-v0.5-candidate.4-strict",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "build-v0.6-candidate.6-vertical-guard",
    )
    args = parser.parse_args()
    records = [build_part(args.source_dir, args.output_dir, spec) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.6 Candidate 6",
        "version": "0.6-candidate.6",
        "mapping": "bit = 4 * local_y + (3 - local_x)",
        "codepoints": (
            "mask < 0x8000: U+0F0000 + mask; otherwise "
            "U+100000 + (mask - 0x8000)"
        ),
        "source_geometry": "Candidate 4 strict hinted geometry",
        "geometry_change": (
            "vertical exterior only: y=-200 to -300 and y=800 to 900; "
            "x coordinates and internal 4x4 boundaries unchanged"
        ),
        "horizontal_cell_bounds": "x=0..500; advance=500",
        "vertical_guard_bounds": "y=-300..900",
        "horizontal_overfill": 0,
        "encoding_invariant": (
            "full occupancy remains foreground mask 0xFFFF at U+107FFF; "
            "no background or reverse-video substitution"
        ),
        "known_limit": (
            "MATE Terminal can expose horizontal seams at its two smallest "
            "Ctrl-minus zoom levels; normal and enlarged supported sizes pass"
        ),
        "parts": records,
    }
    path = args.output_dir / "pua4x4-v0.6-candidate.6-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for record in records:
        print(args.output_dir / record["filename"])
    print(path)


if __name__ == "__main__":
    main()
