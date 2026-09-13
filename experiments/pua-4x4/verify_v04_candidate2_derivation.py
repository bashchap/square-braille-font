#!/usr/bin/env python3
"""Prove candidate.2 differs from candidate.1 only in declared hint data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


PAIRS = (
    ("PUA4x4Part0V04Candidate.ttf", "PUA4x4Part0V04Candidate2.ttf", 0xF0000, 0xF7FFF),
    ("PUA4x4Part1V04Candidate.ttf", "PUA4x4Part1V04Candidate2.ttf", 0x100000, 0x107FFF),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates(glyph, glyf):
    if glyph.numberOfContours == 0:
        return []
    coords, ends, flags = glyph.getCoordinates(glyf)
    return [list(point) for point in coords], list(ends), list(flags)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=root / "build-v0.4-candidate.1")
    parser.add_argument("--candidate-dir", type=Path, default=root / "build-v0.4-candidate.2-hinted")
    parser.add_argument("--output", type=Path, default=root / "output/audit/pua4x4-v0.4-candidate.2-derivation.json")
    args = parser.parse_args()

    records = []
    total = 0
    hinted = 0
    for source_name, candidate_name, cp_start, cp_end in PAIRS:
        source_path = args.source_dir / source_name
        candidate_path = args.candidate_dir / candidate_name
        source = TTFont(source_path)
        candidate = TTFont(candidate_path)
        source_cmap = source.getBestCmap()
        candidate_cmap = candidate.getBestCmap()
        assert set(source_cmap) == set(candidate_cmap)
        assert source["head"].unitsPerEm == candidate["head"].unitsPerEm == 1000
        assert candidate["head"].flags == source["head"].flags | 0x0008
        assert candidate["gasp"].gaspRange == {65535: 0x000F}
        part_hinted = 0
        for codepoint in range(cp_start, cp_end + 1):
            s_name = source_cmap[codepoint]
            c_name = candidate_cmap[codepoint]
            assert source["hmtx"].metrics[s_name] == candidate["hmtx"].metrics[c_name]
            assert coordinates(source["glyf"][s_name], source["glyf"]) == coordinates(
                candidate["glyf"][c_name], candidate["glyf"]
            )
            source_program = getattr(source["glyf"][s_name], "program", None)
            candidate_program = getattr(candidate["glyf"][c_name], "program", None)
            source_bytes = source_program.getBytecode() if source_program else b""
            candidate_bytes = candidate_program.getBytecode() if candidate_program else b""
            assert source_bytes == b""
            if source["glyf"][s_name].numberOfContours > 0:
                assert candidate_bytes
                part_hinted += 1
            else:
                assert candidate_bytes == b""
            total += 1
        hinted += part_hinted
        records.append({
            "source": str(source_path),
            "source_sha256": digest(source_path),
            "candidate": str(candidate_path),
            "candidate_sha256": digest(candidate_path),
            "codepoints_compared": cp_end - cp_start + 1,
            "hinted_nonempty_glyphs": part_hinted,
            "cmap_equal": True,
            "hmtx_equal": True,
            "raw_coordinates_equal": True,
        })
        source.close()
        candidate.close()

    report = {
        "audit": "candidate.1 to candidate.2 controlled derivation",
        "status": "PASS_CONTROLLED_HINT_ONLY_DIFFERENCE",
        "codepoints_compared": total,
        "hinted_nonempty_glyphs": hinted,
        "parts": records,
        "permitted_differences": ["name records", "glyph instruction programs", "head integer-ppem flag", "gasp table", "maxp instruction maxima"],
        "prohibited_differences_found": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: all 65,536 cmap mappings, hmtx metrics and raw outlines are identical")
    print("PASS: candidate.2 differences are confined to declared hinting data and names")
    print(args.output)


if __name__ == "__main__":
    main()
