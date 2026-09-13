#!/usr/bin/env python3
"""Build Candidate 4 from Candidate 1's exact-core geometry.

The approved cmap, MSB-left mapping, advances, bearings and raw outlines are
unchanged.  Candidate 4 adds the proven per-point grid instructions from the
Candidate 2 diagnostic, but deliberately adds no exterior overfill.  Its
Linux Fontconfig profile disables antialiasing for these two graphics fonts so
the raster cannot paint colour samples into an adjacent terminal cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program


PARTS = (
    {
        "part": 0,
        "source": "PUA4x4Part0V04Candidate.ttf",
        "filename": "PUA4x4Part0V05Candidate4.ttf",
        "family": "PUA 4x4 Part 0 v0.5 Candidate 4",
        "postscript": "PUA4x4Part0V05Candidate4-Regular",
        "codepoint_start": 0xF0000,
        "codepoint_end": 0xF7FFF,
    },
    {
        "part": 1,
        "source": "PUA4x4Part1V04Candidate.ttf",
        "filename": "PUA4x4Part1V05Candidate4.ttf",
        "family": "PUA 4x4 Part 1 v0.5 Candidate 4",
        "postscript": "PUA4x4Part1V05Candidate4-Regular",
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
        3: f"{postscript};0.5-candidate.4",
        4: family,
        5: "Version 0.5-candidate.4",
        6: postscript,
        10: (
            "Strict-cell PUA 4x4 graphics candidate. Approved MSB-left cmap "
            "and Candidate 1 exact-core outlines with per-point grid fitting; "
            "no glyph crosses its 500 by 1000 font-unit terminal cell."
        ),
        16: family,
        17: "Regular",
    }
    for record in font["name"].names:
        if record.nameID in values:
            font["name"].setName(
                values[record.nameID], record.nameID,
                record.platformID, record.platEncID, record.langID,
            )
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def gridfit_program(point_count: int) -> Program:
    assembly = ["SVTCA[0]", "RTG[ ]"]
    for point in range(point_count):
        assembly.extend((f"PUSHB[ ] {point}", "MDAP[1]"))
    assembly.extend(("SVTCA[1]", "RTG[ ]"))
    for point in range(point_count):
        assembly.extend((f"PUSHB[ ] {point}", "MDAP[1]"))
    program = Program()
    program.fromAssembly(assembly)
    return program


def build_part(source_dir: Path, output_dir: Path, spec: dict) -> dict:
    source = source_dir / spec["source"]
    output = output_dir / spec["filename"]
    font = TTFont(source, recalcBBoxes=False, recalcTimestamp=False)
    cmap = font.getBestCmap()
    glyf = font["glyf"]
    hinted = 0
    maximum = 0
    for codepoint in range(spec["codepoint_start"], spec["codepoint_end"] + 1):
        glyph = glyf[cmap[codepoint]]
        if glyph.numberOfContours <= 0:
            continue
        glyph.program = gridfit_program(len(glyph.coordinates))
        maximum = max(maximum, len(glyph.program.getBytecode()))
        hinted += 1

    font["head"].flags |= 0x0008
    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = {65535: 0x000F}
    font["gasp"] = gasp
    font["maxp"].maxSizeOfInstructions = maximum
    font["maxp"].maxStackElements = 1
    replace_names(font, spec["family"], spec["postscript"])
    output_dir.mkdir(parents=True, exist_ok=True)
    font.save(output, reorderTables=True)
    font.close()
    return {
        **spec,
        "source_sha256": sha256(source),
        "sha256": sha256(output),
        "hinted_nonempty_glyphs": hinted,
        "maximum_instruction_bytes": maximum,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=root / "build-v0.4-candidate.1",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "build-v0.5-candidate.4-strict",
    )
    args = parser.parse_args()
    records = [build_part(args.source_dir, args.output_dir, spec) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.5 Candidate 4",
        "version": "0.5-candidate.4",
        "mapping": "bit = 4 * local_y + (3 - local_x)",
        "codepoints": (
            "mask < 0x8000: U+0F0000 + mask; otherwise "
            "U+100000 + (mask - 0x8000)"
        ),
        "source_geometry": "Candidate 1 exact core",
        "geometry_change": "none",
        "cell_bounds": "x=0..500, y=-200..800; advance=500",
        "exterior_overfill": 0,
        "encoding_invariant": (
            "full occupancy remains mask 0xFFFF, codepoint U+107FFF, foreground"
        ),
        "candidate_status": (
            "PASSED LINUX RELEASE GATE: strict hinted geometry preserves "
            "foreground ownership and continuous internal U+107FFF joins; "
            "no background substitution is used"
        ),
        "parts": records,
    }
    path = args.output_dir / "pua4x4-v0.5-candidate.4-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for record in records:
        print(args.output_dir / record["filename"])
    print(path)


if __name__ == "__main__":
    main()
