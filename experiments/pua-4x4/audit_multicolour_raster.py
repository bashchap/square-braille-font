#!/usr/bin/env python3
"""Audit PUA 4x4 mapping, guarded outlines, and multi-colour raster ownership.

The audit deliberately separates three questions that earlier seam probes
conflated:

1. Does mask bit ``4*y + (3-x)`` select the intended 4x4 subcell?
2. Does Candidate 3 differ from Candidate 1 only by its declared 100-unit
   exterior-edge expansion?
3. When adjacent terminal cells have different colours, does ink remain owned
   by the cell that emitted it?

Questions 1 and 2 are checked exhaustively for all 65,536 masks.  Question 3
is checked through the real Pango/Cairo raster path at every configured size,
in both horizontal and vertical paint order, with representative Part 0,
Part 1, split-boundary, edge-bit, solid-field, and box-over-grid cases.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
PART_SPECS = (
    {
        "part": 0,
        "start": 0xF0000,
        "end": 0xF7FFF,
        "candidate1": "PUA4x4Part0V04Candidate.ttf",
        "candidate3": "PUA4x4Part0V04Candidate3.ttf",
    },
    {
        "part": 1,
        "start": 0x100000,
        "end": 0x107FFF,
        "candidate1": "PUA4x4Part1V04Candidate.ttf",
        "candidate3": "PUA4x4Part1V04Candidate3.ttf",
    },
)
NOMINAL = {"x_min": 0, "x_max": 500, "y_min": -200, "y_max": 800}
OVERFILL = 100
BACKGROUND = (0, 0, 0)
FIRST = (0, 229, 255)
SECOND = (255, 64, 160)
SAME = (255, 255, 255)


def cp_for_mask(mask: int) -> int:
    if not 0 <= mask <= 0xFFFF:
        raise ValueError(mask)
    return 0xF0000 + mask if mask < 0x8000 else 0x100000 + mask - 0x8000


def part_for_mask(mask: int) -> int:
    return 0 if mask < 0x8000 else 1


def bit_for_local(local_x: int, local_y: int) -> int:
    return 4 * local_y + (3 - local_x)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glyph_polygons(font: TTFont, glyph_name: str) -> list[list[tuple[int, int]]]:
    """Return simple on-curve polygons; generated PUA glyphs contain no curves."""
    glyph = font["glyf"][glyph_name]
    if glyph.numberOfContours <= 0:
        return []
    coordinates, end_points, flags = glyph.getCoordinates(font["glyf"])
    if not all(flag & 1 for flag in flags):
        raise AssertionError(f"unexpected off-curve point in {glyph_name}")
    polygons = []
    start = 0
    for end in end_points:
        polygons.append([(int(x), int(y)) for x, y in coordinates[start : end + 1]])
        start = end + 1
    return polygons


def point_inside(polygons: list[list[tuple[int, int]]], x: float, y: float) -> bool:
    """Non-zero winding test at a subcell centre."""
    winding = 0
    for polygon in polygons:
        for index, (x1, y1) in enumerate(polygon):
            x2, y2 = polygon[(index + 1) % len(polygon)]
            if y1 <= y < y2:
                cross = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
                if cross > 0:
                    winding += 1
            elif y2 <= y < y1:
                cross = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
                if cross < 0:
                    winding -= 1
    return winding != 0


def sampled_mask(font: TTFont, glyph_name: str) -> int:
    polygons = glyph_polygons(font, glyph_name)
    mask = 0
    for local_y in range(4):
        y = 800 - local_y * 250 - 125
        for local_x in range(4):
            x = local_x * 125 + 62.5
            if point_inside(polygons, x, y):
                mask |= 1 << bit_for_local(local_x, local_y)
    return mask


def transformed_coordinates(font: TTFont, glyph_name: str) -> list[tuple[int, int]]:
    glyph = font["glyf"][glyph_name]
    if glyph.numberOfContours <= 0:
        return []
    coordinates, _, _ = glyph.getCoordinates(font["glyf"])
    result = []
    for x, y in coordinates:
        x = -OVERFILL if x == 0 else 500 + OVERFILL if x == 500 else int(x)
        y = -200 - OVERFILL if y == -200 else 800 + OVERFILL if y == 800 else int(y)
        result.append((x, y))
    return result


def actual_coordinates(font: TTFont, glyph_name: str) -> list[tuple[int, int]]:
    glyph = font["glyf"][glyph_name]
    if glyph.numberOfContours <= 0:
        return []
    coordinates, _, _ = glyph.getCoordinates(font["glyf"])
    return [(int(x), int(y)) for x, y in coordinates]


def bbox(font: TTFont, glyph_name: str) -> tuple[int, int, int, int] | None:
    glyph = font["glyf"][glyph_name]
    if glyph.numberOfContours <= 0:
        return None
    glyph.recalcBounds(font["glyf"])
    return glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax


def exhaustive_outline_audit(candidate1_dir: Path, candidate3_dir: Path) -> dict:
    failures: list[dict] = []
    totals = Counter()
    part_reports = []
    for spec in PART_SPECS:
        path1 = candidate1_dir / spec["candidate1"]
        path3 = candidate3_dir / spec["candidate3"]
        font1 = TTFont(path1, recalcBBoxes=False, recalcTimestamp=False)
        font3 = TTFont(path3, recalcBBoxes=False, recalcTimestamp=False)
        cmap1, cmap3 = font1.getBestCmap(), font3.getBestCmap()
        required = set(range(spec["start"], spec["end"] + 1))
        missing1, missing3 = sorted(required - set(cmap1)), sorted(required - set(cmap3))
        part = Counter()
        for mask in range(spec["part"] * 0x8000, (spec["part"] + 1) * 0x8000):
            codepoint = cp_for_mask(mask)
            name1, name3 = cmap1.get(codepoint), cmap3.get(codepoint)
            if name1 is None or name3 is None:
                failures.append({"mask": f"0x{mask:04X}", "codepoint": f"U+{codepoint:06X}", "failure": "missing cmap"})
                continue
            part["glyphs_checked"] += 1
            logical1, logical3 = sampled_mask(font1, name1), sampled_mask(font3, name3)
            if logical1 != mask or logical3 != mask:
                failures.append({
                    "mask": f"0x{mask:04X}", "codepoint": f"U+{codepoint:06X}",
                    "failure": "sampled logical mask mismatch",
                    "candidate1": f"0x{logical1:04X}", "candidate3": f"0x{logical3:04X}",
                })
            else:
                part["logical_masks_passed"] += 1
            if transformed_coordinates(font1, name1) != actual_coordinates(font3, name3):
                failures.append({"mask": f"0x{mask:04X}", "codepoint": f"U+{codepoint:06X}", "failure": "undeclared coordinate difference"})
            else:
                part["declared_transform_passed"] += 1
            advance1 = font1["hmtx"].metrics[name1][0]
            advance3 = font3["hmtx"].metrics[name3][0]
            if advance1 != 500 or advance3 != 500:
                failures.append({"mask": f"0x{mask:04X}", "codepoint": f"U+{codepoint:06X}", "failure": "advance width", "candidate1": advance1, "candidate3": advance3})
            else:
                part["advance_width_passed"] += 1
            bounds = bbox(font3, name3)
            if mask & 0x8888:
                part["masks_with_left_edge_bits"] += 1
                if bounds and bounds[0] < 0:
                    part["glyphs_crossing_left_boundary"] += 1
            if mask & 0x1111:
                part["masks_with_right_edge_bits"] += 1
                if bounds and bounds[2] > 500:
                    part["glyphs_crossing_right_boundary"] += 1
            if mask & 0x000F:
                part["masks_with_top_edge_bits"] += 1
                if bounds and bounds[3] > 800:
                    part["glyphs_crossing_top_boundary"] += 1
            if mask & 0xF000:
                part["masks_with_bottom_edge_bits"] += 1
                if bounds and bounds[1] < -200:
                    part["glyphs_crossing_bottom_boundary"] += 1
        totals.update(part)
        part_reports.append({
            "part": spec["part"],
            "range": f"U+{spec['start']:06X}-U+{spec['end']:06X}",
            "candidate1": {"path": str(path1), "sha256": sha256(path1), "required_missing": len(missing1)},
            "candidate3": {"path": str(path3), "sha256": sha256(path3), "required_missing": len(missing3)},
            "counts": dict(part),
        })
        font1.close()
        font3.close()

    edge_count = (1 << 16) - (1 << 12)
    broad_adjacent_pair_count = edge_count * edge_count
    # For one shared boundary there are four aligned subpixels.  Per aligned
    # pair the non-overlap states are 00, 01, and 10 (three possibilities).
    # The remaining twelve mask bits in each cell are unrestricted.
    aligned_overlap_pair_count = (1 << 32) - (3 ** 4) * (1 << 24)
    return {
        "scope": "all 65,536 masks; both font parts",
        "mapping_formula": "bit = 4 * local_y + (3 - local_x)",
        "codepoint_formula": "mask < 0x8000: U+0F0000 + mask; otherwise U+100000 + (mask - 0x8000)",
        "nominal_cell_font_units": NOMINAL,
        "declared_candidate3_transform": "x=0->-100, x=500->600, y=-200->-300, y=800->900",
        "parts": part_reports,
        "totals": dict(totals),
        "failures_count": len(failures),
        "failures": failures[:100],
        "edge_risk_combinatorics": {
            "masks_with_any_specific_edge_active": edge_count,
            "fraction": edge_count / 65536,
            "ordered_pairs_with_any_ink_on_both_opposing_edges": broad_adjacent_pair_count,
            "ordered_pairs_with_at_least_one_aligned_opposing_edge_subpixel": aligned_overlap_pair_count,
            "aligned_pair_fraction_of_all_ordered_mask_pairs": aligned_overlap_pair_count / (1 << 32),
            "explanation": "The aligned count requires at least one shared row (horizontal neighbours) or column (vertical neighbours) where both opposing edge bits are active. The later-painted cell can overwrite the earlier cell there when colours differ.",
        },
        "status": "PASS" if not failures else "FAIL",
    }


@dataclass(frozen=True)
class RasterCase:
    name: str
    direction: str
    first_mask: int
    second_mask: int
    purpose: str


RASTER_CASES = (
    RasterCase("solid_horizontal", "horizontal", 0xFFFF, 0xFFFF, "maximum horizontal ownership conflict"),
    RasterCase("solid_vertical", "vertical", 0xFFFF, 0xFFFF, "maximum vertical ownership conflict"),
    RasterCase("split_p0_to_p1", "horizontal", 0x7FFF, 0x8000, "font Part 0/Part 1 split boundary"),
    RasterCase("split_p1_to_p0", "horizontal", 0x8000, 0x7FFF, "font Part 1/Part 0 split boundary"),
    RasterCase("box_grid_right", "horizontal", 0x9F00, 0x8888, "reported right-side grid-over-box reproduction"),
    RasterCase("box_grid_below", "vertical", 0x00F9, 0x000F, "reported lower-grid-over-box reproduction"),
    RasterCase("top_row_edge_bits", "horizontal", 0x0001, 0x0008, "right/left one-bit edge pair, top row"),
    RasterCase("row_1_edge_bits", "horizontal", 0x0010, 0x0080, "right/left one-bit edge pair, row 1"),
    RasterCase("row_2_edge_bits", "horizontal", 0x0100, 0x0800, "right/left one-bit edge pair, row 2"),
    RasterCase("bottom_row_edge_bits", "horizontal", 0x1000, 0x8000, "right/left one-bit edge pair, bottom row"),
    RasterCase("left_column_edge_bits", "vertical", 0x8000, 0x0008, "bottom/top one-bit edge pair, left column"),
    RasterCase("column_1_edge_bits", "vertical", 0x4000, 0x0004, "bottom/top one-bit edge pair, column 1"),
    RasterCase("column_2_edge_bits", "vertical", 0x2000, 0x0002, "bottom/top one-bit edge pair, column 2"),
    RasterCase("right_column_edge_bits", "vertical", 0x1000, 0x0001, "bottom/top one-bit edge pair, right column"),
)


def pango_markup(first_mask: int, second_mask: int, direction: str, first_colour: tuple[int, int, int], second_colour: tuple[int, int, int]) -> str:
    first = html.escape(chr(cp_for_mask(first_mask)))
    second = html.escape(chr(cp_for_mask(second_mask)))
    first_hex = "#%02x%02x%02x" % first_colour
    second_hex = "#%02x%02x%02x" % second_colour
    separator = "\n" if direction == "vertical" else ""
    return f'<span foreground="{first_hex}">{first}</span>{separator}<span foreground="{second_hex}">{second}</span>'


def run_pango(font: str, size: int, markup: str, output: Path, antialias: str = "none") -> None:
    command = [
        "pango-view", "--no-display", "--pixels", f"--font={font} {size}",
        "--background=#000000", "--foreground=#ffffff", "--margin=0",
        "--spacing=0", "--line-spacing=1", "--hinting=full",
        f"--antialias={antialias}", "--markup", "--text=" + markup,
        "--output=" + str(output),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def ownership_counts(image: Image.Image, direction: str) -> dict:
    rgb = image.convert("RGB")
    width, height = rgb.size
    if direction == "horizontal":
        # Pango assigns the extra raster column/row to the first logical cell
        # when a two-cell extent rounds to an odd number of device pixels.
        split = (width + 1) // 2
        first_region = (0, 0, split, height)
        second_region = (split, 0, width, height)
    else:
        split = (height + 1) // 2
        first_region = (0, 0, width, split)
        second_region = (0, split, width, height)

    def count_colour(region: tuple[int, int, int, int], colour: tuple[int, int, int]) -> int:
        x0, y0, x1, y1 = region
        return sum(rgb.getpixel((x, y)) == colour for y in range(y0, y1) for x in range(x0, x1))

    second_in_first = count_colour(first_region, SECOND)
    first_in_second = count_colour(second_region, FIRST)
    return {
        "dimensions": [width, height],
        "partition": split,
        "second_colour_pixels_in_first_cell": second_in_first,
        "first_colour_pixels_in_second_cell": first_in_second,
        "foreign_colour_pixels": second_in_first + first_in_second,
        "partition_foreign_colour_pixels": second_in_first + first_in_second,
    }


def isolated_overlap(first_image: Image.Image, second_image: Image.Image) -> int:
    """Count device pixels inked by both adjacent glyph footprints.

    This is independent of any rounded midpoint assumption.  The two control
    images have identical two-cell logical layouts; only the first or second
    glyph is non-empty.  Any shared device pixel proves raster footprints from
    distinct terminal cells overlap before paint order is considered.
    """
    first_rgb = first_image.convert("RGB")
    second_rgb = second_image.convert("RGB")
    if first_rgb.size != second_rgb.size:
        raise AssertionError(f"control layout mismatch: {first_rgb.size} != {second_rgb.size}")
    return sum(a != BACKGROUND and b != BACKGROUND for a, b in zip(first_rgb.getdata(), second_rgb.getdata()))


def raster_audit(font: str, sizes: list[int], antialias_modes: list[str], output_dir: Path) -> dict:
    if shutil.which("pango-view") is None:
        return {"status": "SKIPPED", "reason": "pango-view is not installed"}
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for antialias in antialias_modes:
        for size in sizes:
            for case in RASTER_CASES:
                path = output_dir / f"{case.name}-{antialias}-{size:02d}px.png"
                run_pango(font, size, pango_markup(case.first_mask, case.second_mask, case.direction, FIRST, SECOND), path, antialias)
                counts = ownership_counts(Image.open(path), case.direction)
                first_control = output_dir / f"{case.name}-{antialias}-{size:02d}px-first-only.png"
                second_control = output_dir / f"{case.name}-{antialias}-{size:02d}px-second-only.png"
                run_pango(font, size, pango_markup(case.first_mask, 0x0000, case.direction, FIRST, SECOND), first_control, antialias)
                run_pango(font, size, pango_markup(0x0000, case.second_mask, case.direction, FIRST, SECOND), second_control, antialias)
                overlap = isolated_overlap(Image.open(first_control), Image.open(second_control))
                records.append({
                    "case": case.name,
                    "purpose": case.purpose,
                    "direction": case.direction,
                    "size_px": size,
                    "antialias": antialias,
                    "first": {"mask": f"0x{case.first_mask:04X}", "codepoint": f"U+{cp_for_mask(case.first_mask):06X}", "part": part_for_mask(case.first_mask), "colour": "#00e5ff"},
                    "second": {"mask": f"0x{case.second_mask:04X}", "codepoint": f"U+{cp_for_mask(case.second_mask):06X}", "part": part_for_mask(case.second_mask), "colour": "#ff40a0"},
                    "image": str(path),
                    "first_only_image": str(first_control),
                    "second_only_image": str(second_control),
                    **counts,
                    "isolated_footprint_overlap_pixels": overlap,
                    "status": "PASS" if overlap == 0 else "FAIL",
                })

    # Same-colour solid neighbours must not expose black *between their ink*.
    #
    # pango-view's output surface may be one device pixel taller than the ink
    # because the rounded line box and rounded glyph outline do not always have
    # the same exterior extent.  That exterior padding is not an inter-cell
    # seam.  Count black pixels only inside the bounding box of the coloured
    # ink.  A black row/column at a join is necessarily inside this box and is
    # still a failure.
    same_colour = []
    for antialias in antialias_modes:
        for size in sizes:
            for direction in ("horizontal", "vertical"):
                markup = pango_markup(0xFFFF, 0xFFFF, direction, SAME, SAME)
                path = output_dir / f"same-colour-solid-{direction}-{antialias}-{size:02d}px.png"
                run_pango(font, size, markup, path, antialias)
                image = Image.open(path).convert("RGB")
                nonblack = [
                    (x, y)
                    for y in range(image.height)
                    for x in range(image.width)
                    if image.getpixel((x, y)) != BACKGROUND
                ]
                if nonblack:
                    xs, ys = zip(*nonblack)
                    coloured_bbox = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
                    black_inside = sum(
                        image.getpixel((x, y)) == BACKGROUND
                        for y in range(coloured_bbox[1], coloured_bbox[3])
                        for x in range(coloured_bbox[0], coloured_bbox[2])
                    )
                else:
                    coloured_bbox = None
                    black_inside = image.width * image.height
                exterior_black = sum(pixel == BACKGROUND for pixel in image.getdata()) - black_inside
                same_colour.append({
                    "size_px": size, "direction": direction, "antialias": antialias, "image": str(path),
                    "dimensions": list(image.size),
                    "coloured_bbox": coloured_bbox,
                    "black_pixels_inside_coloured_bbox": black_inside,
                    "exterior_line_box_background_pixels": exterior_black,
                    # Retained for schema compatibility; it now means an
                    # actual gap enclosed by the coloured glyph field.
                    "black_pixels": black_inside,
                    "status": "PASS" if black_inside == 0 else "FAIL",
                })

    failures = [record for record in records if record["status"] == "FAIL"]
    same_failures = [record for record in same_colour if record["status"] == "FAIL"]
    return {
        "renderer": "pango-view via Pango/Cairo",
        "font": font,
        "sizes_px": sizes,
        "antialias_modes": antialias_modes,
        "colours": {"first": "#00e5ff", "second": "#ff40a0", "background": "#000000"},
        "ownership_invariant": "Raster footprints emitted by two distinct terminal cells must not occupy the same device pixel; otherwise paint order can replace the earlier cell's colour/depth result.",
        "cases": records,
        "ownership_failures": len(failures),
        "ownership_tests": len(records),
        "same_colour_solid_tests": same_colour,
        "same_colour_failures": len(same_failures),
        "status": "PASS" if not failures and not same_failures else "FAIL",
    }


def make_contact_sheet(raster: dict, output: Path, candidate_label: str, size_filter: int = 14, antialias_filter: str = "none") -> None:
    cases = [record for record in raster.get("cases", []) if record["size_px"] == size_filter and record["antialias"] == antialias_filter]
    if not cases:
        return
    font = ImageFont.load_default()
    cards = []
    for record in cases:
        source = Image.open(record["image"]).convert("RGB")
        scale = max(1, 140 // max(source.width, source.height))
        preview = source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST)
        card = Image.new("RGB", (420, 210), (7, 14, 22))
        draw = ImageDraw.Draw(card)
        draw.text((12, 10), record["case"], fill=(80, 225, 255), font=font)
        draw.text((12, 28), record["purpose"], fill=(210, 220, 230), font=font)
        card.paste(preview, (12, 58))
        draw.text((180, 64), f"{record['first']['mask']} -> {record['second']['mask']}", fill=(255, 190, 60), font=font)
        draw.text((180, 82), f"footprint overlap: {record['isolated_footprint_overlap_pixels']} px", fill=(255, 90, 110) if record["status"] == "FAIL" else (80, 240, 150), font=font)
        draw.text((180, 100), f"status: {record['status']}", fill=(255, 90, 110) if record["status"] == "FAIL" else (80, 240, 150), font=font)
        cards.append(card)
    columns = 2
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 420, rows * 210 + 54), (3, 8, 14))
    draw = ImageDraw.Draw(sheet)
    draw.text((14, 14), f"PUA 4x4 {candidate_label} multi-colour ownership audit — {size_filter}px", fill=(80, 225, 255), font=font)
    draw.text((14, 32), "Cyan=first cell, magenta=second cell; any colour in the other cell is a raster ownership failure.", fill=(210, 220, 230), font=font)
    for index, card in enumerate(cards):
        sheet.paste(card, ((index % columns) * 420, 54 + (index // columns) * 210))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate1-dir", type=Path, default=ROOT / "build-v0.4-candidate.1")
    parser.add_argument("--candidate3-dir", type=Path, default=ROOT / "build-v0.4-candidate.3-seamguard100")
    parser.add_argument("--font", default="PUA 4x4 v0.4 Candidate 3")
    parser.add_argument("--candidate-label", default="Candidate 3")
    parser.add_argument("--sizes", default="8,9,10,11,12,13,14,16,18,20")
    parser.add_argument("--antialias-modes", default="none,gray,subpixel")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/audit/multicolour-raster-v0.4")
    parser.add_argument("--report", type=Path, default=ROOT / "output/audit/pua4x4-v0.4-full-raster-audit.json")
    parser.add_argument("--structural-only", action="store_true")
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",") if value.strip()]
    antialias_modes = [value.strip() for value in args.antialias_modes.split(",") if value.strip()]

    structural = exhaustive_outline_audit(args.candidate1_dir, args.candidate3_dir)
    raster = {"status": "SKIPPED", "reason": "--structural-only"} if args.structural_only else raster_audit(args.font, sizes, antialias_modes, args.output_dir)
    report = {
        "audit": f"PUA 4x4 {args.candidate_label} full mapping/outline/multi-colour raster audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "structural": structural,
        "raster": raster,
        "decision": {
            "mapping_and_codepoint_status": structural["status"],
            "tested_raster_font": args.font,
            "same_colour_seam_status": "SKIPPED" if raster["status"] == "SKIPPED" else ("PASS" if raster["same_colour_failures"] == 0 else "FAIL"),
            "multi_colour_cell_ownership_status": "SKIPPED" if raster["status"] == "SKIPPED" else ("PASS" if raster["ownership_failures"] == 0 else "FAIL"),
            "tested_raster_release_gate": "FAIL" if raster.get("ownership_failures", 0) or raster.get("same_colour_failures", 0) else ("PASS" if raster["status"] != "SKIPPED" and structural["status"] == "PASS" else "INCOMPLETE"),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if raster.get("cases"):
        slug = args.candidate_label.lower().replace(" ", "-")
        make_contact_sheet(
            raster,
            args.output_dir / f"pua4x4-{slug}-multicolour-contact-sheet-14px.png",
            args.candidate_label,
            14,
        )
    print(json.dumps(report["decision"], indent=2))
    print(args.report)


if __name__ == "__main__":
    main()
