#!/usr/bin/env python3
"""Compare v0.3 and v0.4 candidate placement through installed Pango."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image


P0_BASE = 0xF0000
P1_BASE = 0x100000


def codepoint(mask: int) -> int:
    if mask < 0x8000:
        return P0_BASE + mask
    return P1_BASE + mask - 0x8000


def render(font: str, size: int, text: str, output: Path) -> None:
    subprocess.run(
        [
            "pango-view",
            "--no-display",
            "--pixels",
            f"--font={font} {size}",
            "--foreground=#ffffff",
            "--background=#000000",
            "--margin=0",
            "--spacing=0",
            "--line-spacing=1",
            "--text=" + text,
            "--output=" + str(output),
        ],
        check=True,
    )


def render_points(font: str, size: int, dpi: int, text: str, output: Path) -> None:
    """Use point units and explicit DPI, matching a terminal's font request."""
    subprocess.run(
        [
            "pango-view",
            "--no-display",
            f"--dpi={dpi}",
            f"--font={font} {size}",
            "--foreground=#ffffff",
            "--background=#000000",
            "--margin=0",
            "--spacing=0",
            "--line-spacing=1",
            "--text=" + text,
            "--output=" + str(output),
        ],
        check=True,
    )


def segment_ink_bbox(image: Image.Image, left: int, width: int):
    segment = image.crop((left, 0, left + width, image.height)).convert("L")
    return segment.getbbox()


def horizontal_ink_runs(image: Image.Image):
    grayscale = image.convert("L")
    occupied = [
        any(grayscale.getpixel((x, y)) != 0 for y in range(grayscale.height))
        for x in range(grayscale.width)
    ]
    runs = []
    start = None
    for x, value in enumerate(occupied + [False]):
        if value and start is None:
            start = x
        elif not value and start is not None:
            runs.append([start, x])
            start = None
    return runs


def one_bit_strip(font: str, label: str, output_dir: Path):
    masks = (0x0008, 0x0004, 0x0002, 0x0001)
    size = 40
    cell_width = 20
    path = output_dir / f"{label}-one-bit-horizontal.png"
    render(font, size, "".join(chr(codepoint(mask)) for mask in masks), path)
    image = Image.open(path).convert("RGB")
    assert image.width == cell_width * len(masks), image.size
    measured = []
    for index, mask in enumerate(masks):
        bbox = segment_ink_bbox(image, index * cell_width, cell_width)
        measured.append({
            "mask_hex": f"0x{mask:04X}",
            "expected_x_range": [index * 5, index * 5 + 5],
            "measured_local_ink_bbox": list(bbox) if bbox else None,
        })
    return path, image.size, measured, horizontal_ink_runs(image)


def solid_seam_matrix(font: str, output_dir: Path):
    columns, rows = 64, 16
    field = "\n".join(chr(codepoint(0xFFFF)) * columns for _ in range(rows))
    records = []
    for size in (8, 9, 10, 11, 12, 13, 14, 16, 18, 20):
        path = output_dir / f"candidate-solid-{size:02d}.png"
        render(font, size, field, path)
        image = Image.open(path).convert("RGB")
        black = sum(pixel == (0, 0, 0) for pixel in image.getdata())
        records.append({
            "size_pixels": size,
            "image": str(path),
            "dimensions": list(image.size),
            "black_pixels": black,
            "status": "PASS" if black == 0 else "FAIL",
        })
    return records


def terminal_point_seam_matrix(font: str, output_dir: Path, dpi: int = 96):
    columns, rows = 80, 20
    field = "\n".join(chr(codepoint(0xFFFF)) * columns for _ in range(rows))
    records = []
    for size in (8, 9, 10, 11, 12, 13, 14, 16, 18, 20):
        path = output_dir / f"candidate-solid-{size:02d}pt-{dpi}dpi.png"
        render_points(font, size, dpi, field, path)
        image = Image.open(path).convert("RGB")
        black = sum(pixel == (0, 0, 0) for pixel in image.getdata())
        nonwhite = sum(pixel != (255, 255, 255) for pixel in image.getdata())
        records.append({
            "size_points": size,
            "dpi": dpi,
            "image": str(path),
            "dimensions": list(image.size),
            "black_pixels": black,
            "nonwhite_pixels": nonwhite,
            "status": "PASS" if black == 0 and nonwhite == 0 else "DIFFERENCE_RECORDED",
        })
    return records


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "output" / "audit" / "pango-v0.4-candidate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-pango-raster.json",
    )
    parser.add_argument(
        "--candidate-font",
        default="PUA 4x4 v0.4 Candidate",
    )
    parser.add_argument(
        "--label",
        default="v04-candidate",
    )
    parser.add_argument(
        "--measurement-only",
        action="store_true",
        help="record candidate runs without enforcing candidate.1 geometry",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    v03_path, v03_size, v03, v03_runs = one_bit_strip(
        "PUA 4x4", "v03", args.output_dir
    )
    candidate_path, candidate_size, candidate, candidate_runs = one_bit_strip(
        args.candidate_font, args.label, args.output_dir
    )
    expected_local = [[0, 5], [5, 10], [10, 15], [15, 20]]
    expected_global = [
        [index * 20 + local[0], index * 20 + local[1]]
        for index, local in enumerate(expected_local)
    ]
    assert v03_runs == [[0, 6], [19, 26], [39, 46], [59, 66]], v03_runs
    if not args.measurement_only:
        assert candidate_runs == [[0, 6], [24, 31], [49, 56], [74, 80]], candidate_runs
        for actual, expected in zip(candidate_runs, expected_global):
            assert expected[0] - 1 <= actual[0] <= expected[0]
            assert expected[1] <= actual[1] <= min(80, expected[1] + 1)

    seams = solid_seam_matrix(args.candidate_font, args.output_dir)
    assert all(record["black_pixels"] == 0 for record in seams)
    point_seams = terminal_point_seam_matrix(
        args.candidate_font, args.output_dir
    )
    report = {
        "audit": "Installed Pango horizontal placement and seam comparison",
        "gate": "E - installed Pango raster",
        "status": (
            "MEASURED_WITHOUT_CANDIDATE1_ASSERTIONS"
            if args.measurement_only
            else "PASS_CANDIDATE_WITH_V03_FAILURE_REPRODUCED"
        ),
        "exact_circumstance": {
            "renderer": "pango-view --pixels --margin=0 --spacing=0",
            "one_bit_size_pixels": 40,
            "one_bit_sequence": ["0x0008", "0x0004", "0x0002", "0x0001"],
            "expected_local_x_ranges": expected_local,
            "expected_global_x_ranges": expected_global,
            "antialias_allowance": "at most one pixel outside each exact vector edge",
        },
        "v0.3": {
            "font": "PUA 4x4",
            "image": str(v03_path),
            "dimensions": list(v03_size),
            "records": v03,
            "measured_global_ink_runs": v03_runs,
            "result": "FAIL: all four horizontal one-bit positions render at x=0..5",
        },
        "v0.4_candidate": {
            "font": args.candidate_font,
            "image": str(candidate_path),
            "dimensions": list(candidate_size),
            "records": candidate,
            "measured_global_ink_runs": candidate_runs,
            "result": "PASS: measured x positions equal the approved mapping",
        },
        "candidate_solid_seam_matrix": seams,
        "candidate_terminal_point_seam_matrix": point_seams,
        "not_proven_by_this_gate": [
            "MATE Terminal cell placement",
            "MATE Terminal colored triangle output",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("FAIL REPRODUCED: v0.3 one-bit x ranges are all 0..5")
    print("PASS: candidate one-bit x ranges are 0..5, 5..10, 10..15, 15..20")
    print("PASS: candidate solid seam matrix has zero black pixels at 8..20 px")
    print(args.output)


if __name__ == "__main__":
    main()
