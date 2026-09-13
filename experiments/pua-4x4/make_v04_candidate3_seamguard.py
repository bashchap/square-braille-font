#!/usr/bin/env python3
"""Derive candidate.3 with a measured 100-unit terminal-edge seam guard.

Candidate.1's cmap and approved 4x4 core geometry remain the oracle. Only
outline coordinates exactly on a terminal-cell exterior edge are moved 100
units outward. Interior 4x4 boundaries are unchanged. Bearings are updated to
preserve the resulting raw outline positions relative to the advance origin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


OVERFILL = 100
PARTS = (
    {
        "part": 0, "source": "PUA4x4Part0V04Candidate.ttf",
        "filename": "PUA4x4Part0V04Candidate3.ttf",
        "family": "PUA 4x4 Part 0 v0.4 Candidate 3",
        "postscript": "PUA4x4Part0V04Candidate3-Regular",
        "codepoint_start": 0xF0000, "codepoint_end": 0xF7FFF,
    },
    {
        "part": 1, "source": "PUA4x4Part1V04Candidate.ttf",
        "filename": "PUA4x4Part1V04Candidate3.ttf",
        "family": "PUA 4x4 Part 1 v0.4 Candidate 3",
        "postscript": "PUA4x4Part1V04Candidate3-Regular",
        "codepoint_start": 0x100000, "codepoint_end": 0x107FFF,
    },
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_names(font: TTFont, family: str, postscript: str) -> None:
    values = {
        1: family, 2: "Regular", 3: f"{postscript};0.4-candidate.3",
        4: family, 5: "Version 0.4-candidate.3", 6: postscript,
        10: (
            "PUA 4x4 MSB-left candidate with exact 4x4 core geometry and a "
            "measured 100-font-unit exterior terminal-cell seam guard."
        ), 16: family, 17: "Regular",
    }
    for record in font["name"].names:
        if record.nameID in values:
            font["name"].setName(values[record.nameID], record.nameID, record.platformID, record.platEncID, record.langID)
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def transform(value: int, low: int, high: int) -> int:
    if value == low:
        return low - OVERFILL
    if value == high:
        return high + OVERFILL
    return value


def build_part(source_dir: Path, output_dir: Path, spec: dict) -> dict:
    source_path = source_dir / spec["source"]
    output_path = output_dir / spec["filename"]
    font = TTFont(source_path, recalcBBoxes=False, recalcTimestamp=False)
    cmap = font.getBestCmap()
    glyf = font["glyf"]
    changed = 0
    for codepoint in range(spec["codepoint_start"], spec["codepoint_end"] + 1):
        name = cmap[codepoint]
        glyph = glyf[name]
        if glyph.numberOfContours <= 0:
            continue
        old = list(glyph.coordinates)
        glyph.coordinates = type(glyph.coordinates)([
            (transform(x, 0, 500), transform(y, -200, 800))
            for x, y in old
        ])
        glyph.recalcBounds(glyf)
        advance, _ = font["hmtx"].metrics[name]
        font["hmtx"].metrics[name] = (advance, glyph.xMin)
        if old != list(glyph.coordinates):
            changed += 1
    replace_names(font, spec["family"], spec["postscript"])
    output_dir.mkdir(parents=True, exist_ok=True)
    font.save(output_path, reorderTables=True)
    font.close()
    return {
        **spec,
        "source_sha256": sha(source_path),
        "sha256": sha(output_path),
        "glyphs_with_exterior_guard": changed,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=root / "build-v0.4-candidate.1")
    parser.add_argument("--output-dir", type=Path, default=root / "build-v0.4-candidate.3-seamguard100")
    args = parser.parse_args()
    records = [build_part(args.source_dir, args.output_dir, spec) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.4 Candidate 3",
        "version": "0.4-candidate.3",
        "mapping": "unchanged: bit = 4 * local_y + (3 - local_x)",
        "cmap": "unchanged from candidate.1",
        "advance_width": 500,
        "core_grid": "unchanged x=0..500, y=-200..800, internal boundaries unchanged",
        "deliberate_difference": (
            "coordinates on x=0, x=500, y=-200 or y=800 are moved 100 "
            "font units outward; hmtx LSB follows the transformed xMin"
        ),
        "reason": "100 was the first tested threshold with zero nonwhite seam pixels at every 8..20 point, 96-DPI probe",
        "parts": records,
    }
    path = args.output_dir / "pua4x4-v0.4-candidate.3-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for record in records:
        print(args.output_dir / record["filename"])
    print(path)


if __name__ == "__main__":
    main()
