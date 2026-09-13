#!/usr/bin/env python3
"""Exhaustively verify v0.4 candidate cmap and stored simple outlines.

Expected codepoints and boundary edges are calculated independently from the
approved formulas. Every one of 65,536 glyphs is read back from the generated
TrueType files and compared with that expectation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from fontTools.ttLib import TTFont


GRID = 4
ADVANCE = 500
ASCENT = 800
DESCENT = 200
CELL_WIDTH = 125
CELL_HEIGHT = 250
PART_SIZE = 0x8000
P0_BASE = 0xF0000
P1_BASE = 0x100000
X_GRID = {0, 125, 250, 375, 500}
Y_GRID = {-200, 50, 300, 550, 800}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_codepoint(mask: int) -> int:
    if not 0 <= mask <= 0xFFFF:
        raise ValueError(mask)
    if mask < 0x8000:
        return P0_BASE + mask
    return P1_BASE + (mask - 0x8000)


def expected_cell_edges(mask: int):
    """Calculate directed unit boundary edges without generator imports."""
    edges = set()
    for local_y in range(GRID):
        for local_x in range(GRID):
            bit = 4 * local_y + (3 - local_x)
            if not mask & (1 << bit):
                continue
            x_min = local_x * CELL_WIDTH
            x_max = x_min + CELL_WIDTH
            y_max = ASCENT - local_y * CELL_HEIGHT
            y_min = y_max - CELL_HEIGHT
            clockwise = (
                ((x_min, y_min), (x_min, y_max)),
                ((x_min, y_max), (x_max, y_max)),
                ((x_max, y_max), (x_max, y_min)),
                ((x_max, y_min), (x_min, y_min)),
            )
            for edge in clockwise:
                reverse = (edge[1], edge[0])
                if reverse in edges:
                    edges.remove(reverse)
                else:
                    edges.add(edge)
    return edges


def glyph_contours(font: TTFont, glyph_name: str):
    glyph = font["glyf"][glyph_name]
    if glyph.isComposite():
        raise AssertionError(f"candidate glyph {glyph_name} is composite")
    if glyph.numberOfContours == 0:
        return []
    coordinates, end_points, flags = glyph.getCoordinates(font["glyf"])
    assert all(flag & 0x01 for flag in flags), glyph_name
    contours = []
    start = 0
    for end in end_points:
        contours.append([tuple(point) for point in coordinates[start:end + 1]])
        start = end + 1
    return contours


def expand_edge(start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    assert (dx == 0) != (dy == 0), (start, end)
    unit = CELL_HEIGHT if dx == 0 else CELL_WIDTH
    distance = abs(dy if dx == 0 else dx)
    assert distance % unit == 0, (start, end)
    steps = distance // unit
    step_x = 0 if dx == 0 else (unit if dx > 0 else -unit)
    step_y = 0 if dy == 0 else (unit if dy > 0 else -unit)
    result = set()
    current = start
    for _ in range(steps):
        following = (current[0] + step_x, current[1] + step_y)
        result.add((current, following))
        current = following
    assert current == end
    return result


def actual_cell_edges(contours):
    edges = set()
    for contour in contours:
        assert len(contour) >= 4
        for index, start in enumerate(contour):
            end = contour[(index + 1) % len(contour)]
            edges.update(expand_edge(start, end))
    return edges


def shifted_edges(edges, shift_x):
    return {
        (
            (start[0] + shift_x, start[1]),
            (end[0] + shift_x, end[1]),
        )
        for start, end in edges
    }


def point_in_contours(point, contours) -> bool:
    """Non-zero winding test at a cell center; all candidate edges are lines."""
    px, py = point
    winding = 0
    for contour in contours:
        for index, first in enumerate(contour):
            second = contour[(index + 1) % len(contour)]
            x1, y1 = first
            x2, y2 = second
            cross = (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1)
            if y1 <= py < y2 and cross > 0:
                winding += 1
            elif y2 <= py < y1 and cross < 0:
                winding -= 1
    return winding != 0


def decoded_mask(contours) -> int:
    mask = 0
    for local_y in range(GRID):
        for local_x in range(GRID):
            x = local_x * CELL_WIDTH + CELL_WIDTH / 2
            y_max = ASCENT - local_y * CELL_HEIGHT
            y = y_max - CELL_HEIGHT / 2
            if point_in_contours((x, y), contours):
                bit = 4 * local_y + (3 - local_x)
                mask |= 1 << bit
    return mask


def verify_part(path: Path, part: int):
    font = TTFont(path, lazy=False)
    cmap = font.getBestCmap()
    start_mask = part * PART_SIZE
    start_codepoint = P0_BASE if part == 0 else P1_BASE
    expected_codepoints = set(range(start_codepoint, start_codepoint + PART_SIZE))
    assert any(table.format == 12 for table in font["cmap"].tables)
    assert set(cmap) == expected_codepoints | {0x20}
    assert font["maxp"].numGlyphs == PART_SIZE + 2
    assert font["head"].unitsPerEm == 1000
    assert (font["hhea"].ascent, font["hhea"].descent, font["hhea"].lineGap) == (
        ASCENT, -DESCENT, 0
    )
    assert font["hmtx"].metrics[cmap[0x20]] == (ADVANCE, 0)
    assert font["glyf"][cmap[0x20]].numberOfContours == 0

    contour_histogram = Counter()
    point_histogram = Counter()
    for offset in range(PART_SIZE):
        mask = start_mask + offset
        codepoint = start_codepoint + offset
        assert codepoint == expected_codepoint(mask)
        glyph_name = cmap[codepoint]
        assert font.getGlyphID(glyph_name) == offset + 2
        contours = glyph_contours(font, glyph_name)

        points = [point for contour in contours for point in contour]
        assert all(point[0] in X_GRID and point[1] in Y_GRID for point in points), (
            mask, points
        )
        actual_edges = actual_cell_edges(contours)
        expected_edges = expected_cell_edges(mask)
        assert actual_edges == expected_edges, (
            f"mask 0x{mask:04X}", actual_edges ^ expected_edges
        )
        expected_x_min = min((point[0] for point in points), default=0)
        advance, left_side_bearing = font["hmtx"].metrics[glyph_name]
        assert advance == ADVANCE
        assert left_side_bearing == expected_x_min, (
            f"mask 0x{mask:04X}", left_side_bearing, expected_x_min
        )
        effective_shift_x = left_side_bearing - expected_x_min
        positioned_edges = shifted_edges(actual_edges, effective_shift_x)
        assert positioned_edges == expected_edges, (
            f"mask 0x{mask:04X}", "effective placement mismatch",
            positioned_edges ^ expected_edges,
        )
        actual_mask = decoded_mask(contours)
        assert actual_mask == mask, (
            f"mask 0x{mask:04X}", f"decoded 0x{actual_mask:04X}"
        )
        contour_histogram[len(contours)] += 1
        point_histogram[len(points)] += 1

    result = {
        "part": part,
        "file": str(path),
        "file_size": path.stat().st_size,
        "sha256": sha256(path),
        "mask_range": [start_mask, start_mask + PART_SIZE - 1],
        "codepoint_range": [start_codepoint, start_codepoint + PART_SIZE - 1],
        "glyph_count": font["maxp"].numGlyphs,
        "patterns_verified": PART_SIZE,
        "composite_pattern_glyphs": 0,
        "horizontal_metric_mismatches": 0,
        "effective_position_mismatches": 0,
        "format_12_cmap": True,
        "contour_count_histogram": dict(sorted(contour_histogram.items())),
        "point_count_histogram": dict(sorted(point_histogram.items())),
    }
    font.close()
    return result


def sample_record(mask: int):
    codepoint = expected_codepoint(mask)
    return {
        "mask": mask,
        "mask_hex": f"0x{mask:04X}",
        "binary_msb_to_lsb": f"{mask:016b}",
        "part": 0 if mask < 0x8000 else 1,
        "codepoint": codepoint,
        "codepoint_hex": f"U+{codepoint:06X}",
        "bitmap": [
            "".join(
                "#" if mask & (1 << (4 * y + (3 - x))) else "."
                for x in range(4)
            )
            for y in range(4)
        ],
        "expected_boundary_unit_edges": len(expected_cell_edges(mask)),
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "font_dir",
        nargs="?",
        type=Path,
        default=root / "build-v0.4-candidate.1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-font-audit.json",
    )
    parser.add_argument(
        "--mathematics-evidence",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-mathematics-proof-v1.0.json",
    )
    parser.add_argument("--part0-name", default="PUA4x4Part0V04Candidate.ttf")
    parser.add_argument("--part1-name", default="PUA4x4Part1V04Candidate.ttf")
    args = parser.parse_args()

    mathematics = json.loads(args.mathematics_evidence.read_text(encoding="utf-8"))
    assert mathematics["status"] == "PASS_MATHEMATICS_ONLY"
    assert mathematics["authoritative_layout"] == [
        [3, 2, 1, 0],
        [7, 6, 5, 4],
        [11, 10, 9, 8],
        [15, 14, 13, 12],
    ]

    paths = (
        args.font_dir / args.part0_name,
        args.font_dir / args.part1_name,
    )
    parts = [verify_part(path, part) for part, path in enumerate(paths)]
    samples = [sample_record(mask) for mask in (
        0x0000, 0x0001, 0x0002, 0x0004, 0x0008, 0x0400,
        0x7FFF, 0x8000, 0x8001, 0x9669, 0xFFFF,
    )]
    report = {
        "audit": "PUA 4x4 v0.4 candidate stored-font proof",
        "gate": "B - cmap and stored outline identity",
        "status": "PASS_FONT_STRUCTURE_ONLY",
        "not_proven_by_this_gate": [
            "Fontconfig family selection",
            "Pango shaping and fallback",
            "terminal cell placement",
            "terminal raster output",
        ],
        "approved_mathematics_evidence": {
            "file": str(args.mathematics_evidence),
            "sha256": sha256(args.mathematics_evidence),
        },
        "formula": "bit = 4 * local_y + (3 - local_x)",
        "outline_expectation": (
            "simple union contours equal the selected 4x4 cells exactly; "
            "all shared internal edges absent"
        ),
        "parts": parts,
        "patterns_verified": sum(item["patterns_verified"] for item in parts),
        "unique_codepoints_verified": len({expected_codepoint(mask) for mask in range(0x10000)}),
        "outline_edge_mismatches": 0,
        "decoded_mask_mismatches": 0,
        "horizontal_metric_mismatches": 0,
        "effective_position_mismatches": 0,
        "composite_pattern_glyphs": 0,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: approved mathematics evidence loaded and matched")
    print("PASS: 65,536 cmap entries select 65,536 unique candidate glyphs")
    print("PASS: 65,536 stored outlines equal their independent boundary-edge oracle")
    print("PASS: 65,536 stored outlines decode to their complete 16-bit masks")
    print("PASS: 65,536 hmtx bearings preserve the approved physical x positions")
    print("PASS: zero pattern glyphs are composite; shared internal edges are absent")
    print(args.output)


if __name__ == "__main__":
    main()
