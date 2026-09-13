#!/usr/bin/env python3
"""Exhaustively prove the candidate.1 to candidate.3 seam-guard transform."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


OVERFILL = 100
PAIRS = (
    ("PUA4x4Part0V04Candidate.ttf", "PUA4x4Part0V04Candidate3.ttf", 0xF0000, 0xF7FFF),
    ("PUA4x4Part1V04Candidate.ttf", "PUA4x4Part1V04Candidate3.ttf", 0x100000, 0x107FFF),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transformed(point):
    x, y = point
    x = -OVERFILL if x == 0 else 500 + OVERFILL if x == 500 else x
    y = -200 - OVERFILL if y == -200 else 800 + OVERFILL if y == 800 else y
    return x, y


def coordinates(glyph, glyf):
    if glyph.numberOfContours == 0:
        return [], []
    coords, ends, _ = glyph.getCoordinates(glyf)
    return list(coords), list(ends)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=root / "build-v0.4-candidate.1")
    parser.add_argument("--candidate-dir", type=Path, default=root / "build-v0.4-candidate.3-seamguard100")
    parser.add_argument("--output", type=Path, default=root / "output/audit/pua4x4-v0.4-candidate.3-derivation.json")
    args = parser.parse_args()
    records = []
    total = changed = 0
    for source_name, candidate_name, cp_start, cp_end in PAIRS:
        source_path, candidate_path = args.source_dir / source_name, args.candidate_dir / candidate_name
        source, candidate = TTFont(source_path), TTFont(candidate_path)
        source_cmap, candidate_cmap = source.getBestCmap(), candidate.getBestCmap()
        assert set(source_cmap) == set(candidate_cmap)
        part_changed = 0
        for codepoint in range(cp_start, cp_end + 1):
            s_name, c_name = source_cmap[codepoint], candidate_cmap[codepoint]
            s_coords, s_ends = coordinates(source["glyf"][s_name], source["glyf"])
            c_coords, c_ends = coordinates(candidate["glyf"][c_name], candidate["glyf"])
            assert s_ends == c_ends
            expected = [transformed(point) for point in s_coords]
            assert expected == c_coords, (hex(codepoint), expected, c_coords)
            s_advance, _ = source["hmtx"].metrics[s_name]
            c_advance, c_lsb = candidate["hmtx"].metrics[c_name]
            assert s_advance == c_advance == 500
            if c_coords:
                assert c_lsb == min(point[0] for point in c_coords)
            else:
                assert c_lsb == 0
            if s_coords != c_coords:
                part_changed += 1
            total += 1
        changed += part_changed
        records.append({"source": str(source_path), "source_sha256": sha(source_path), "candidate": str(candidate_path), "candidate_sha256": sha(candidate_path), "codepoints": cp_end-cp_start+1, "guarded_glyphs": part_changed})
        source.close(); candidate.close()
    report = {
        "audit": "candidate.1 to candidate.3 controlled seam-guard derivation",
        "status": "PASS_EXACT_DECLARED_TRANSFORM",
        "codepoints_compared": total,
        "glyphs_with_guard": changed,
        "formula_and_cmap_changes": 0,
        "unexpected_outline_changes": 0,
        "guard_transform": "x: 0->-100, 500->600; y: -200->-300, 800->900; all other coordinates unchanged",
        "parts": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: all 65,536 cmap entries retain the approved mapping")
    print("PASS: every candidate.3 coordinate equals the declared candidate.1 transform")
    print(args.output)


if __name__ == "__main__":
    main()
