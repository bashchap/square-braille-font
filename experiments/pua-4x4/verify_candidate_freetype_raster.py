#!/usr/bin/env python3
"""Verify candidate glyph rasters against exact 4x4 expectations.

Pillow's FreeType renderer is used as a deterministic font raster gate, not as
a substitute for the later Pango and terminal gates. Sizes 40 and 80 pixels
per em make every 125 x 250 unit subcell an integer pixel rectangle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


P0_BASE = 0xF0000
P1_BASE = 0x100000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def codepoint(mask: int) -> int:
    if mask < 0x8000:
        return P0_BASE + mask
    return P1_BASE + mask - 0x8000


def expected_image(mask: int, ppem: int) -> Image.Image:
    width = ppem // 2
    cell_width = width // 4
    cell_height = ppem // 4
    image = Image.new("L", (width, ppem), 0)
    pixels = image.load()
    for local_y in range(4):
        for local_x in range(4):
            bit = 4 * local_y + (3 - local_x)
            if not mask & (1 << bit):
                continue
            for y in range(local_y * cell_height, (local_y + 1) * cell_height):
                for x in range(local_x * cell_width, (local_x + 1) * cell_width):
                    pixels[x, y] = 255
    return image


def actual_image(mask: int, ppem: int, font_paths) -> Image.Image:
    path = font_paths[0 if mask < 0x8000 else 1]
    font = ImageFont.truetype(str(path), size=ppem)
    character = chr(codepoint(mask))
    width = ppem // 2
    assert font.getlength(character) == width
    image = Image.new("L", (width, ppem), 0)
    draw = ImageDraw.Draw(image)
    draw.text((0, 4 * ppem // 5), character, font=font, fill=255, anchor="ls")
    return image


def compare(mask: int, ppem: int, font_paths):
    expected = expected_image(mask, ppem)
    actual = actual_image(mask, ppem, font_paths)
    expected_pixels = expected.tobytes()
    actual_pixels = actual.tobytes()
    mismatches = sum(a != b for a, b in zip(actual_pixels, expected_pixels))
    partial = sum(value not in (0, 255) for value in actual_pixels)
    return {
        "mask": mask,
        "mask_hex": f"0x{mask:04X}",
        "codepoint_hex": f"U+{codepoint(mask):06X}",
        "ppem": ppem,
        "width": ppem // 2,
        "height": ppem,
        "mismatched_pixels": mismatches,
        "partially_covered_pixels": partial,
        "expected_white_pixels": sum(value == 255 for value in expected_pixels),
        "actual_white_pixels": sum(value == 255 for value in actual_pixels),
    }


def make_visual(path: Path, ppem: int, masks, font_paths) -> None:
    scale = 3
    tile_width = ppem // 2
    tile_height = ppem
    gap = 8
    columns = len(masks)
    canvas = Image.new(
        "RGB",
        ((tile_width * scale + gap) * columns + gap,
         tile_height * scale * 2 + gap * 3),
        (25, 30, 38),
    )
    for index, mask in enumerate(masks):
        x = gap + index * (tile_width * scale + gap)
        expected = expected_image(mask, ppem).resize(
            (tile_width * scale, tile_height * scale), Image.Resampling.NEAREST
        ).convert("RGB")
        actual = actual_image(mask, ppem, font_paths).resize(
            (tile_width * scale, tile_height * scale), Image.Resampling.NEAREST
        ).convert("RGB")
        canvas.paste(expected, (x, gap))
        canvas.paste(actual, (x, tile_height * scale + 2 * gap))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--font-dir",
        type=Path,
        default=root / "build-v0.4-candidate.1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-freetype-raster.json",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-freetype-expected-actual.png",
    )
    args = parser.parse_args()
    font_paths = (
        args.font_dir / "PUA4x4Part0V04Candidate.ttf",
        args.font_dir / "PUA4x4Part1V04Candidate.ttf",
    )

    masks = [0x0000]
    masks.extend(1 << bit for bit in range(16))
    masks.extend((
        0x000F, 0x00F0, 0x0F00, 0xF000,
        0x1111, 0x2222, 0x4444, 0x8888,
        0x0660, 0x6996, 0x9669, 0x7FFF, 0x8000, 0xFFFF,
    ))
    records = [
        compare(mask, ppem, font_paths)
        for ppem in (40, 80)
        for mask in masks
    ]
    mismatch_total = sum(record["mismatched_pixels"] for record in records)
    partial_total = sum(record["partially_covered_pixels"] for record in records)
    assert mismatch_total == 0, [
        record for record in records if record["mismatched_pixels"]
    ]
    assert partial_total == 0

    visual_masks = (0x0008, 0x0004, 0x0002, 0x0001, 0x0660, 0x9669, 0xFFFF)
    make_visual(args.image, 40, visual_masks, font_paths)
    report = {
        "audit": "PUA 4x4 v0.4 candidate FreeType raster proof",
        "gate": "C - deterministic standalone raster",
        "status": "PASS_FREETYPE_RASTER_ONLY",
        "not_proven_by_this_gate": [
            "Fontconfig family selection",
            "Pango shaping and fallback",
            "terminal cell placement",
            "terminal raster output",
        ],
        "font_files": [
            {"file": str(path), "sha256": sha256(path)} for path in font_paths
        ],
        "integer_grid_sizes_ppem": [40, 80],
        "masks_per_size": len(masks),
        "raster_cases": len(records),
        "mismatched_pixels": mismatch_total,
        "partially_covered_pixels": partial_total,
        "records": records,
        "comparison_image": str(args.image),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(records)} exact FreeType expected/actual raster cases")
    print("PASS: zero mismatched pixels and zero partially covered pixels")
    print(args.output)
    print(args.image)


if __name__ == "__main__":
    main()
