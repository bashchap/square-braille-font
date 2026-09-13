#!/usr/bin/env python3
"""Derive candidate.2 by adding native grid instructions to candidate.1.

The cmap, approved MSB-left masks, advance widths, bearings and raw outline
coordinates are unchanged. The only geometric operation performed by the
TrueType interpreter is rounding every existing contour point to the current
device pixel grid, independently on y and x. This diagnostic candidate tests
whether fractional-ppem edge coverage is the source of terminal seams.
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
        "filename": "PUA4x4Part0V04Candidate2.ttf",
        "family": "PUA 4x4 Part 0 v0.4 Candidate 2",
        "postscript": "PUA4x4Part0V04Candidate2-Regular",
        "codepoint_start": 0xF0000,
        "codepoint_end": 0xF7FFF,
    },
    {
        "part": 1,
        "source": "PUA4x4Part1V04Candidate.ttf",
        "filename": "PUA4x4Part1V04Candidate2.ttf",
        "family": "PUA 4x4 Part 1 v0.4 Candidate 2",
        "postscript": "PUA4x4Part1V04Candidate2-Regular",
        "codepoint_start": 0x100000,
        "codepoint_end": 0x107FFF,
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_names(font: TTFont, family: str, postscript: str) -> None:
    values = {
        1: family,
        2: "Regular",
        3: f"{postscript};0.4-candidate.2",
        4: family,
        5: "Version 0.4-candidate.2",
        6: postscript,
        10: (
            "Diagnostic candidate with the approved PUA 4x4 MSB-left cmap, "
            "unchanged exact outlines and native per-point grid instructions."
        ),
        16: family,
        17: "Regular",
    }
    table = font["name"]
    for record in table.names:
        if record.nameID in values:
            table.setName(
                values[record.nameID], record.nameID,
                record.platformID, record.platEncID, record.langID,
            )
    for name_id, value in values.items():
        table.setName(value, name_id, 3, 1, 0x409)
        table.setName(value, name_id, 1, 0, 0)


def point_gridfit_program(point_count: int) -> Program:
    assembly = ["SVTCA[0]", "RTG[ ]"]  # y projection/freedom vector
    for point in range(point_count):
        assembly.extend((f"PUSHB[ ] {point}", "MDAP[1]"))
    assembly.extend(("SVTCA[1]", "RTG[ ]"))  # x projection/freedom vector
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
        point_count = len(glyph.coordinates)
        glyph.program = point_gridfit_program(point_count)
        maximum = max(maximum, len(glyph.program.getBytecode()))
        hinted += 1

    # Bit 3 requests integer ppem scaler math. The outlines and metrics remain
    # identical to candidate.1; only device-grid execution differs.
    font["head"].flags |= 0x0008
    gasp = newTable("gasp")
    gasp.version = 1
    gasp.gaspRange = {65535: 0x000F}
    font["gasp"] = gasp
    replace_names(font, spec["family"], spec["postscript"])
    font["maxp"].maxSizeOfInstructions = maximum
    # Each PUSHB/MDAP pair uses one stack element. FontBuilder's unhinted
    # source declares zero, which causes a conforming interpreter to reject
    # the added programs instead of executing them.
    font["maxp"].maxStackElements = 1
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
        default=root / "build-v0.4-candidate.2-hinted",
    )
    args = parser.parse_args()
    records = [build_part(args.source_dir, args.output_dir, spec) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.4 Candidate 2",
        "version": "0.4-candidate.2",
        "purpose": "native-grid-hinting diagnostic",
        "mathematical_mapping": "unchanged from approved candidate.1",
        "cmap": "unchanged from candidate.1",
        "raw_outlines": "unchanged from candidate.1",
        "hmtx": "unchanged from candidate.1",
        "runtime_difference": (
            "every real contour point executes MDAP[1] on y then x; head "
            "integer-ppem flag and gasp gridfit/gray flags are enabled"
        ),
        "parts": records,
    }
    path = args.output_dir / "pua4x4-v0.4-candidate.2-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for record in records:
        print(args.output_dir / record["filename"])
    print(path)


if __name__ == "__main__":
    main()
