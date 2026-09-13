#!/usr/bin/env python3
"""Measure terminal-cell seam attenuation in paired triangle captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "demos4x4"))
from pua4x4_backend import DOT_BIT  # noqa: E402
from triangle import cell_colors, triangle_pixels  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def framebuffer(columns: int, rows: int):
    points = triangle_pixels(columns * 4, rows * 4)
    colors = cell_colors(points)
    masks = [[0] * columns for _ in range(rows)]
    for (x, y), _ in points:
        cell_x, sub_x = divmod(x, 4)
        cell_y, sub_y = divmod(y, 4)
        masks[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
    return masks, colors


def analyze(path: Path, masks, colors, cell_width: int, cell_height: int,
            origin_x: int, origin_y: int):
    image = Image.open(path).convert("RGB")
    low_all = low_boundary = low_interior = 0
    all_pixels = boundary_pixels = interior_pixels = 0
    ratio_sum_boundary = ratio_sum_interior = 0.0
    full_cells = 0
    for cell_y, row in enumerate(masks):
        for cell_x, mask in enumerate(row):
            if mask != 0xFFFF:
                continue
            expected = colors[(cell_y, cell_x)]
            expected_sum = sum(expected)
            if expected_sum < 32:
                continue
            full_cells += 1
            for py in range(cell_height):
                for px in range(cell_width):
                    actual = image.getpixel((origin_x + cell_x * cell_width + px,
                                             origin_y + cell_y * cell_height + py))
                    ratio = sum(actual) / expected_sum
                    boundary = px in (0, cell_width - 1) or py in (0, cell_height - 1)
                    all_pixels += 1
                    low = ratio < 0.90
                    low_all += int(low)
                    if boundary:
                        boundary_pixels += 1
                        low_boundary += int(low)
                        ratio_sum_boundary += ratio
                    else:
                        interior_pixels += 1
                        low_interior += int(low)
                        ratio_sum_interior += ratio
    return {
        "image": str(path),
        "sha256": sha(path),
        "dimensions": list(image.size),
        "full_cells_measured": full_cells,
        "pixels_measured": all_pixels,
        "low_coverage_threshold": "sum(actual RGB) / sum(expected ANSI RGB) < 0.90",
        "low_coverage_pixels": low_all,
        "low_coverage_fraction": low_all / all_pixels,
        "boundary": {
            "pixels": boundary_pixels,
            "low_coverage_pixels": low_boundary,
            "low_coverage_fraction": low_boundary / boundary_pixels,
            "mean_coverage_ratio": ratio_sum_boundary / boundary_pixels,
        },
        "interior": {
            "pixels": interior_pixels,
            "low_coverage_pixels": low_interior,
            "low_coverage_fraction": low_interior / interior_pixels,
            "mean_coverage_ratio": ratio_sum_interior / interior_pixels,
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate1", type=Path, default=root / "output/audit/terminal-v0.4-candidate/triangle-14pt.png")
    parser.add_argument("--candidate3", type=Path, default=root / "output/audit/terminal-v0.4-candidate3/triangle-14pt.png")
    parser.add_argument("--output", type=Path, default=root / "output/audit/pua4x4-v0.4-terminal-triangle-comparison.json")
    parser.add_argument("--columns", type=int, default=211)
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--cell-width", type=int, default=9)
    parser.add_argument("--cell-height", type=int, default=19)
    parser.add_argument("--origin-x", type=int, default=0)
    parser.add_argument("--origin-y", type=int, default=25)
    args = parser.parse_args()
    masks, colors = framebuffer(args.columns, args.rows)
    candidate1 = analyze(args.candidate1, masks, colors, args.cell_width, args.cell_height, args.origin_x, args.origin_y)
    candidate3 = analyze(args.candidate3, masks, colors, args.cell_width, args.cell_height, args.origin_x, args.origin_y)
    report = {
        "audit": "MATE Terminal paired triangle seam measurement",
        "exact_circumstance": {
            "terminal_grid": [args.columns, args.rows],
            "measured_cell_pixels": [args.cell_width, args.cell_height],
            "content_origin_pixels": [args.origin_x, args.origin_y],
            "profile_font_size_points": 14,
            "display_dpi": 96,
            "same_demo": "demos4x4/triangle.py --pps 100000",
        },
        "expectation": "full-mask cell boundary pixels have the same foreground coverage as cell interiors",
        "candidate1_exact_core": candidate1,
        "candidate3_seam_guard_100": candidate3,
        "outcome": {
            "candidate1_boundary_low_coverage_pixels": candidate1["boundary"]["low_coverage_pixels"],
            "candidate3_boundary_low_coverage_pixels": candidate3["boundary"]["low_coverage_pixels"],
            "candidate3_pass": candidate3["boundary"]["low_coverage_pixels"] == 0,
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("candidate.1 boundary low-coverage pixels:", candidate1["boundary"]["low_coverage_pixels"])
    print("candidate.3 boundary low-coverage pixels:", candidate3["boundary"]["low_coverage_pixels"])
    print(args.output)


if __name__ == "__main__":
    main()
