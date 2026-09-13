#!/usr/bin/env python3
"""Measure candidate.3's deliberate exterior one-bit seam-guard overhang."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image


def cp(mask: int) -> int:
    return 0xF0000 + mask if mask < 0x8000 else 0x100000 + mask - 0x8000


def runs(image: Image.Image):
    gray = image.convert("L")
    occupied = [any(gray.getpixel((x, y)) for y in range(gray.height)) for x in range(gray.width)]
    result, start = [], None
    for x, value in enumerate(occupied + [False]):
        if value and start is None:
            start = x
        elif not value and start is not None:
            result.append([start, x]); start = None
    return result


def render(font: str, label: str, mask: int, output_dir: Path):
    text = chr(cp(0)) + chr(cp(mask)) + chr(cp(0))
    path = output_dir / f"{label}-mask-{mask:04x}-40px.png"
    subprocess.run([
        "pango-view", "--no-display", "--pixels", f"--font={font} 40",
        "--foreground=#ffffff", "--background=#000000", "--margin=0",
        "--spacing=0", "--line-spacing=1", "--text=" + text,
        "--output=" + str(path),
    ], check=True)
    image = Image.open(path).convert("RGB")
    return {"mask": f"0x{mask:04X}", "image": str(path), "dimensions": list(image.size), "ink_runs": runs(image)}


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=root / "output/audit/candidate3-onebit-overhang")
    parser.add_argument("--output", type=Path, default=root / "output/audit/pua4x4-v0.4-candidate3-onebit-overhang.json")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    masks = (0x0008, 0x0004, 0x0002, 0x0001)
    baseline = [render("PUA 4x4 v0.4 Candidate", "candidate1", mask, args.output_dir) for mask in masks]
    guarded = [render("PUA 4x4 v0.4 Candidate 3", "candidate3", mask, args.output_dir) for mask in masks]
    report = {
        "audit": "candidate.3 isolated one-bit exterior overhang",
        "circumstance": "pango-view, 40 pixel font, three cells: empty + tested mask + empty",
        "core_expected_x_ranges_in_middle_cell": {
            "0x0008": [20, 25], "0x0004": [25, 30],
            "0x0002": [30, 35], "0x0001": [35, 40],
        },
        "candidate1_exact_core": baseline,
        "candidate3_seam_guard_100": guarded,
        "expected_declared_difference": (
            "left-edge mask 0x0008 may ink before x=20 and right-edge mask "
            "0x0001 may ink after x=40; interior masks remain candidate.1-identical"
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("candidate.1", [(x["mask"], x["ink_runs"]) for x in baseline])
    print("candidate.3", [(x["mask"], x["ink_runs"]) for x in guarded])
    print(args.output)


if __name__ == "__main__":
    main()
