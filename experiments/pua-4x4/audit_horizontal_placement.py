#!/usr/bin/env python3
"""Prove the v0.3 horizontal-placement defect and v0.4 correction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


PART_SIZE = 0x8000
P0_BASE = 0xF0000
P1_BASE = 0x100000
ADVANCE = 500
CELL_WIDTH = 125


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_x_min(mask: int):
    if mask == 0:
        return None
    columns = [
        local_x
        for local_y in range(4)
        for local_x in range(4)
        if mask & (1 << (4 * local_y + (3 - local_x)))
    ]
    return min(columns) * CELL_WIDTH


def audit_pair(paths, label, glyph_id_start):
    mismatches = []
    raw_outline_mismatches = []
    samples = []
    patterns = 0
    for part, path in enumerate(paths):
        font = TTFont(path, lazy=False)
        cmap = font.getBestCmap()
        start_mask = part * PART_SIZE
        start_codepoint = P0_BASE if part == 0 else P1_BASE
        for offset in range(PART_SIZE):
            mask = start_mask + offset
            codepoint = start_codepoint + offset
            name = cmap[codepoint]
            assert font.getGlyphID(name) == glyph_id_start + offset
            advance, lsb = font["hmtx"].metrics[name]
            assert advance == ADVANCE
            glyph = font["glyf"][name]
            expected = expected_x_min(mask)
            if expected is None:
                assert glyph.numberOfContours == 0
                continue
            raw_x_min = glyph.xMin
            if raw_x_min != expected:
                raw_outline_mismatches.append(mask)
            # TrueType's left phantom point is xMin-lsb, so the effective
            # placement relative to the pen origin is raw_x-(xMin-lsb).
            origin_shift = lsb - raw_x_min
            effective_x_min = raw_x_min + origin_shift
            if effective_x_min != expected:
                mismatches.append(mask)
            if mask in (0x0001, 0x0002, 0x0004, 0x0008, 0x0400, 0x8000):
                samples.append({
                    "mask_hex": f"0x{mask:04X}",
                    "codepoint_hex": f"U+{codepoint:06X}",
                    "raw_outline_x_min": raw_x_min,
                    "hmtx_left_side_bearing": lsb,
                    "left_phantom_point_x": raw_x_min - lsb,
                    "effective_origin_shift_x": origin_shift,
                    "effective_rendered_x_min": effective_x_min,
                    "mathematical_expected_x_min": expected,
                    "matches": effective_x_min == expected,
                })
            patterns += 1
        font.close()
    return {
        "label": label,
        "files": [
            {"file": str(path), "sha256": sha256(path)} for path in paths
        ],
        "nonempty_patterns_checked": patterns,
        "raw_outline_x_min_mismatches": len(raw_outline_mismatches),
        "effective_horizontal_placement_mismatches": len(mismatches),
        "mismatch_masks_first_32": [f"0x{mask:04X}" for mask in mismatches[:32]],
        "samples": samples,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--v03-dir", type=Path, default=root / "build-v0.3"
    )
    parser.add_argument(
        "--v04-dir", type=Path, default=root / "build-v0.4-candidate.1"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-horizontal-placement-root-cause.json",
    )
    args = parser.parse_args()
    v03 = audit_pair(
        (
            args.v03_dir / "PUA4x4Part0.ttf",
            args.v03_dir / "PUA4x4Part1.ttf",
        ),
        "v0.3 released composite fonts",
        18,
    )
    v04 = audit_pair(
        (
            args.v04_dir / "PUA4x4Part0V04Candidate.ttf",
            args.v04_dir / "PUA4x4Part1V04Candidate.ttf",
        ),
        "v0.4 candidate direct-union fonts",
        2,
    )
    assert v03["raw_outline_x_min_mismatches"] == 0
    assert v03["effective_horizontal_placement_mismatches"] == 4095
    assert v04["raw_outline_x_min_mismatches"] == 0
    assert v04["effective_horizontal_placement_mismatches"] == 0
    report = {
        "audit": "PUA 4x4 horizontal placement root-cause proof",
        "status": "ROOT_CAUSE_CONFIRMED_AND_CANDIDATE_CORRECTED",
        "true_type_formula": (
            "effective_x = raw_x - (xMin - leftSideBearing); therefore "
            "effective_xMin = leftSideBearing"
        ),
        "mathematical_requirement": (
            "effective rendered x positions must equal local_x * 125"
        ),
        "v0.3": v03,
        "v0.4_candidate": v04,
        "conclusion": (
            "v0.3 stored the correct raw x coordinates but wrote lsb=0 for "
            "every pattern. All 4,095 nonempty Part 0 masks without a set "
            "left-edge pixel were shifted left at render time. The candidate "
            "writes lsb=xMin and has zero effective placement mismatches."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: v0.3 raw stored outlines match the mathematical x coordinates")
    print("FAIL CONFIRMED: v0.3 has 4,095 effective horizontal-placement mismatches")
    print("PASS: v0.4 candidate has zero effective horizontal-placement mismatches")
    print(args.output)


if __name__ == "__main__":
    main()
