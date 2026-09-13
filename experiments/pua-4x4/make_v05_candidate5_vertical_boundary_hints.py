#!/usr/bin/env python3
"""Build Candidate 5 with outward rounding only at terminal-row boundaries.

Raw geometry, cmap, advances and MSB-left mapping remain byte-equivalent to
Candidate 1.  At raster time, real contour points on y=800 round upward and
points on y=-200 round downward.  All interior y boundaries and every x point
round to the nearest grid line.  This makes the full glyph's device-pixel
height match a rounded terminal row without horizontal overfill.
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
        "part": 0, "source": "PUA4x4Part0V04Candidate.ttf",
        "filename": "PUA4x4Part0V05Candidate5.ttf",
        "family": "PUA 4x4 Part 0 v0.5 Candidate 5",
        "postscript": "PUA4x4Part0V05Candidate5-Regular",
        "start": 0xF0000, "end": 0xF7FFF,
    },
    {
        "part": 1, "source": "PUA4x4Part1V04Candidate.ttf",
        "filename": "PUA4x4Part1V05Candidate5.ttf",
        "family": "PUA 4x4 Part 1 v0.5 Candidate 5",
        "postscript": "PUA4x4Part1V05Candidate5-Regular",
        "start": 0x100000, "end": 0x107FFF,
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_names(font: TTFont, family: str, postscript: str) -> None:
    values = {
        1: family, 2: "Regular", 3: f"{postscript};0.5-candidate.5",
        4: family, 5: "Version 0.5-candidate.5", 6: postscript,
        10: (
            "Strict raw-cell PUA 4x4 diagnostic candidate. Exterior terminal "
            "row points use outward device-grid rounding; no raw overfill."
        ),
        16: family, 17: "Regular",
    }
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def boundary_program(coordinates) -> Program:
    assembly = ["SVTCA[0]"]
    current_round = None
    for point, (_, y) in enumerate(coordinates):
        wanted = "RUTG[ ]" if y == 800 else "RDTG[ ]" if y == -200 else "RTG[ ]"
        if wanted != current_round:
            assembly.append(wanted)
            current_round = wanted
        assembly.extend((f"PUSHB[ ] {point}", "MDAP[1]"))
    assembly.extend(("SVTCA[1]", "RTG[ ]"))
    for point in range(len(coordinates)):
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
    maximum = 0
    hinted = 0
    for codepoint in range(spec["start"], spec["end"] + 1):
        glyph = glyf[cmap[codepoint]]
        if glyph.numberOfContours <= 0:
            continue
        glyph.program = boundary_program(glyph.coordinates)
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
        **spec, "source_sha256": sha256(source), "sha256": sha256(output),
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
        default=root / "build-v0.5-candidate.5-vertical-boundary-hints",
    )
    args = parser.parse_args()
    records = [build_part(args.source_dir, args.output_dir, spec) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.5 Candidate 5",
        "status": "DIAGNOSTIC_NOT_RELEASED",
        "mapping": "bit = 4 * local_y + (3 - local_x)",
        "raw_geometry": "Candidate 1 exact core; unchanged",
        "raw_overfill": 0,
        "device_rounding": {
            "y=800": "round up to grid",
            "y=-200": "round down to grid",
            "other y": "round to grid",
            "all x": "round to grid",
        },
        "parts": records,
    }
    path = args.output_dir / "pua4x4-v0.5-candidate.5-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for record in records:
        print(args.output_dir / record["filename"])
    print(path)


if __name__ == "__main__":
    main()
