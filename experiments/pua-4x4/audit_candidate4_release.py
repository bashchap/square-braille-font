#!/usr/bin/env python3
"""Candidate 4 audit: mapping, ownership and full-foreground continuity."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

import audit_multicolour_raster as ownership
import verify_pua4x4_v04_candidate as structure


ROOT = Path(__file__).resolve().parent
PARTS = (
    (0, "PUA4x4Part0V04Candidate.ttf", "PUA4x4Part0V05Candidate4.ttf", 0xF0000),
    (1, "PUA4x4Part1V04Candidate.ttf", "PUA4x4Part1V05Candidate4.ttf", 0x100000),
)
CYAN = (0, 229, 255)
MAGENTA = (255, 64, 160)
BLACK = (0, 0, 0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_geometry_audit(source_dir: Path, candidate_dir: Path) -> dict:
    failures = []
    records = []
    total = 0
    for part, source_name, candidate_name, codepoint_start in PARTS:
        source_path = source_dir / source_name
        candidate_path = candidate_dir / candidate_name
        source = TTFont(source_path, recalcBBoxes=False, recalcTimestamp=False)
        candidate = TTFont(candidate_path, recalcBBoxes=False, recalcTimestamp=False)
        source_cmap = source.getBestCmap()
        candidate_cmap = candidate.getBestCmap()
        part_counts = Counter()
        for offset in range(0x8000):
            codepoint = codepoint_start + offset
            source_name_at_cp = source_cmap.get(codepoint)
            candidate_name_at_cp = candidate_cmap.get(codepoint)
            if source_name_at_cp is None or candidate_name_at_cp is None:
                failures.append({"part": part, "codepoint": codepoint, "error": "missing cmap"})
                continue
            source_glyph = source["glyf"][source_name_at_cp]
            candidate_glyph = candidate["glyf"][candidate_name_at_cp]
            source_coordinates = list(source_glyph.getCoordinates(source["glyf"])[0])
            candidate_coordinates = list(candidate_glyph.getCoordinates(candidate["glyf"])[0])
            if source_coordinates != candidate_coordinates:
                failures.append({"part": part, "codepoint": codepoint, "error": "raw coordinates changed"})
            else:
                part_counts["coordinate_identity"] += 1
            if source["hmtx"].metrics[source_name_at_cp] != candidate["hmtx"].metrics[candidate_name_at_cp]:
                failures.append({"part": part, "codepoint": codepoint, "error": "hmtx changed"})
            else:
                part_counts["hmtx_identity"] += 1
            if candidate_glyph.numberOfContours > 0:
                candidate_glyph.recalcBounds(candidate["glyf"])
                if not (0 <= candidate_glyph.xMin <= candidate_glyph.xMax <= 500 and
                        -200 <= candidate_glyph.yMin <= candidate_glyph.yMax <= 800):
                    failures.append({
                        "part": part, "codepoint": codepoint,
                        "error": "outline crosses terminal cell",
                        "bbox": [candidate_glyph.xMin, candidate_glyph.yMin,
                                 candidate_glyph.xMax, candidate_glyph.yMax],
                    })
                else:
                    part_counts["strict_bboxes"] += 1
                if not candidate_glyph.program.getBytecode():
                    failures.append({"part": part, "codepoint": codepoint, "error": "missing gridfit program"})
                else:
                    part_counts["hinted_nonempty"] += 1
            part_counts["glyphs"] += 1
            total += 1
        records.append({
            "part": part,
            "source": str(source_path),
            "source_sha256": sha256(source_path),
            "candidate": str(candidate_path),
            "candidate_sha256": sha256(candidate_path),
            "counts": dict(part_counts),
        })
        source.close()
        candidate.close()
    return {
        "patterns_checked": total,
        "parts": records,
        "failures": failures[:100],
        "failure_count": len(failures),
        "status": "PASS" if not failures and total == 65536 else "FAIL",
    }


def run_pango(font: str, size: int, markup: str, output: Path) -> None:
    subprocess.run([
        "pango-view", "--no-display", "--pixels", f"--font={font} {size}",
        "--background=#000000", "--margin=0", "--spacing=0", "--line-spacing=1",
        "--hinting=full", "--antialias=none", "--markup", "--text=" + markup,
        "--output=" + str(output),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def background_markup(first: tuple[int, int, int], second: tuple[int, int, int],
                      direction: str) -> str:
    first_hex = "#%02x%02x%02x" % first
    second_hex = "#%02x%02x%02x" % second
    separator = "\n" if direction == "vertical" else ""
    return (
        f'<span background="{first_hex}">{html.escape(" ")}</span>'
        f'{separator}<span background="{second_hex}">{html.escape(" ")}</span>'
    )


def background_continuity_audit(font: str, sizes: list[int], output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for size in sizes:
        for direction in ("horizontal", "vertical"):
            for palette, first, second in (
                ("same", CYAN, CYAN),
                ("different", CYAN, MAGENTA),
            ):
                output = output_dir / f"background-{palette}-{direction}-{size:02d}px.png"
                run_pango(font, size, background_markup(first, second, direction), output)
                image = Image.open(output).convert("RGB")
                nonblack = [
                    (x, y) for y in range(image.height) for x in range(image.width)
                    if image.getpixel((x, y)) != BLACK
                ]
                if not nonblack:
                    black_inside = image.width * image.height
                    bbox = None
                else:
                    xs, ys = zip(*nonblack)
                    bbox = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
                    black_inside = sum(
                        image.getpixel((x, y)) == BLACK
                        for y in range(bbox[1], bbox[3])
                        for x in range(bbox[0], bbox[2])
                    )
                colours = Counter(image.getdata())
                expected_colours_present = colours[first] > 0 and colours[second] > 0
                status = "PASS" if black_inside == 0 and expected_colours_present else "FAIL"
                records.append({
                    "size_px": size,
                    "direction": direction,
                    "palette": palette,
                    "image": str(output),
                    "dimensions": list(image.size),
                    "coloured_bbox": bbox,
                    "black_pixels_inside_coloured_bbox": black_inside,
                    "first_pixels": colours[first],
                    "second_pixels": colours[second],
                    "status": status,
                })
    return {
        "tests": len(records),
        "failures": sum(item["status"] == "FAIL" for item in records),
        "records": records,
        "status": "PASS" if all(item["status"] == "PASS" for item in records) else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "build-v0.4-candidate.1")
    parser.add_argument("--candidate-dir", type=Path, default=ROOT / "build-v0.5-candidate.4-strict")
    parser.add_argument("--font", default="PUA 4x4 v0.5 Candidate 4")
    parser.add_argument("--sizes", default="8,9,10,11,12,13,14,16,18,20")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/audit/candidate4-release-linux")
    parser.add_argument("--report", type=Path, default=ROOT / "output/audit/pua4x4-v0.5-candidate4-release-linux.json")
    args = parser.parse_args()
    sizes = [int(item) for item in args.sizes.split(",") if item.strip()]

    stored = [
        structure.verify_part(args.candidate_dir / PARTS[part][2], part)
        for part in (0, 1)
    ]
    geometry = raw_geometry_audit(args.source_dir, args.candidate_dir)
    foreground = ownership.raster_audit(
        args.font, sizes, ["none"], args.output_dir / "foreground-ownership")
    backgrounds = background_continuity_audit(
        args.font, sizes, args.output_dir / "background-continuity")
    report = {
        "audit": "PUA 4x4 v0.5 Candidate 4 strict-cell foreground audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mapping_formula": "bit = 4 * local_y + (3 - local_x)",
        "stored_font_structure": {
            "patterns_verified": sum(part["patterns_verified"] for part in stored),
            "parts": stored,
            "status": "PASS",
        },
        "candidate1_geometry_identity": geometry,
        "foreground_raster_ownership_antialias_none": foreground,
        "terminal_background_continuity_diagnostic_only": backgrounds,
        "encoding_invariant": {
            "full_cell_mask": "0xFFFF",
            "full_cell_codepoint": "U+107FFF",
            "colour_plane": "foreground",
            "background_substitution_permitted": False,
        },
    }
    gates = {
        "mapping_and_structure": "PASS",
        "strict_cell_geometry": geometry["status"],
        "foreground_cell_ownership": (
            "PASS" if foreground.get("ownership_failures") == 0 else "FAIL"
        ),
        "full_foreground_mask_continuity": (
            "PASS" if foreground.get("same_colour_failures") == 0 else "FAIL"
        ),
    }
    gates["release_gate"] = "PASS" if all(value == "PASS" for value in gates.values()) else "FAIL"
    report["decision"] = gates
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gates, indent=2))
    print(args.report)
    raise SystemExit(0 if gates["release_gate"] == "PASS" else 1)


if __name__ == "__main__":
    main()
