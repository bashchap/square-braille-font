#!/usr/bin/env python3
"""Create Candidate-4 copies with only forced-integer PPEM disabled."""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont


PARTS = (
    ("build-v0.5-candidate.4-strict", "PUA4x4Part0V05Candidate4.ttf", "PUA4x4Part0FractionalPpemProbe.ttf", "PUA 4x4 Part 0 Fractional PPEM Probe", "PUA4x4Part0FractionalPpemProbe-Regular"),
    ("build-v0.5-candidate.4-strict", "PUA4x4Part1V05Candidate4.ttf", "PUA4x4Part1FractionalPpemProbe.ttf", "PUA 4x4 Part 1 Fractional PPEM Probe", "PUA4x4Part1FractionalPpemProbe-Regular"),
    ("build-v0.5-candidate.5-vertical-boundary-hints", "PUA4x4Part0V05Candidate5.ttf", "PUA4x4Part0FractionalBoundaryProbe.ttf", "PUA 4x4 Part 0 Fractional Boundary Probe", "PUA4x4Part0FractionalBoundaryProbe-Regular"),
    ("build-v0.5-candidate.5-vertical-boundary-hints", "PUA4x4Part1V05Candidate5.ttf", "PUA4x4Part1FractionalBoundaryProbe.ttf", "PUA 4x4 Part 1 Fractional Boundary Probe", "PUA4x4Part1FractionalBoundaryProbe-Regular"),
)


def main() -> None:
    root = Path(__file__).resolve().parent
    output_dir = root / "output" / "fractional-ppem-probe"
    output_dir.mkdir(parents=True, exist_ok=True)
    for source_dir, source_name, output_name, family, postscript in PARTS:
        font = TTFont(root / source_dir / source_name, recalcBBoxes=False, recalcTimestamp=False)
        font["head"].flags &= ~0x0008
        values = {
            1: family, 2: "Regular", 3: f"{postscript};fractional-ppem-probe",
            4: family, 5: "Fractional PPEM probe", 6: postscript,
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
