#!/usr/bin/env python3
"""Generate the complete two-font, MSB-left PUA 4x4 experiment."""

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from pua4x4 import PART_PATTERN_COUNT, PARTS


UNITS_PER_EM = 1000
ADVANCE = 500
ASCENT = 800
DESCENT = 200
GRID_SIZE = 4
CELL_WIDTH = ADVANCE // GRID_SIZE
CELL_HEIGHT = (ASCENT + DESCENT) // GRID_SIZE
PIXEL_NAMES = tuple(".pixel%02d" % bit for bit in range(16))
IDENTITY = (1, 0, 0, 1, 0, 0)


def rectangle_glyph(x_min, y_min, x_max, y_max):
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, y_min))
    pen.lineTo((x_min, y_max))
    pen.lineTo((x_max, y_max))
    pen.lineTo((x_max, y_min))
    pen.closePath()
    return pen.glyph()


def empty_glyph():
    return TTGlyphPen(None).glyph()


def pixel_glyph(bit, overfill):
    row, numeric_column = divmod(bit, GRID_SIZE)
    column = GRID_SIZE - 1 - numeric_column
    x_min = column * CELL_WIDTH
    x_max = (column + 1) * CELL_WIDTH
    y_max = ASCENT - row * CELL_HEIGHT
    y_min = ASCENT - (row + 1) * CELL_HEIGHT

    if column == 0:
        x_min -= overfill
    if column == GRID_SIZE - 1:
        x_max += overfill
    if row == 0:
        y_max += overfill
    if row == GRID_SIZE - 1:
        y_min -= overfill
    return rectangle_glyph(x_min, y_min, x_max, y_max)


def pattern_glyph(mask, glyph_set):
    if mask == 0:
        return empty_glyph()
    pen = TTGlyphPen(glyph_set)
    for bit, pixel_name in enumerate(PIXEL_NAMES):
        if mask & (1 << bit):
            pen.addComponent(pixel_name, IDENTITY)
    return pen.glyph()


def notdef_glyph():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, 700))
    pen.lineTo((450, 700))
    pen.lineTo((450, 0))
    pen.closePath()
    pen.moveTo((100, 50))
    pen.lineTo((400, 50))
    pen.lineTo((400, 650))
    pen.lineTo((100, 650))
    pen.closePath()
    return pen.glyph()


def build_part(spec, output_dir, version, overfill):
    pattern_names = tuple(
        "mask%04X" % mask
        for mask in range(spec["mask_start"], spec["mask_start"] + PART_PATTERN_COUNT)
    )
    glyph_order = (".notdef", "space") + PIXEL_NAMES + pattern_names
    glyphs = {".notdef": notdef_glyph(), "space": empty_glyph()}
    for bit, name in enumerate(PIXEL_NAMES):
        glyphs[name] = pixel_glyph(bit, overfill)
    for mask, name in zip(
        range(spec["mask_start"], spec["mask_start"] + PART_PATTERN_COUNT),
        pattern_names,
    ):
        glyphs[name] = pattern_glyph(mask, glyphs)

    character_map = {
        spec["codepoint_start"] + offset: name
        for offset, name in enumerate(pattern_names)
    }
    # Pango may keep spaces within a run selected for a supplementary-PUA
    # face. A real blank space prevents those separators becoming unknown
    # glyph boxes without turning either graphics font into a text font.
    character_map[0x20] = "space"
    metrics = {name: (ADVANCE, 0) for name in glyph_order}

    builder = FontBuilder(UNITS_PER_EM, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(character_map)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ASCENT, descent=-DESCENT, lineGap=0)
    builder.setupNameTable(
        {
            "familyName": spec["family"],
            "styleName": "Regular",
            "uniqueFontIdentifier": "%s;%s" % (spec["postscript"], version),
            "fullName": spec["family"],
            "psName": spec["postscript"],
            "version": "Version %s" % version,
            "description": (
                "Graphics-only 4x4 terminal tiles. Each row is MSB-left: "
                "bits 3,2,1,0 on the top row through 15,14,13,12 on the bottom. Each pixel uses its "
                "exact 125 by 250 font-unit boundary without outline overfill."
            ),
        }
    )
    builder.setupOS2(
        version=4,
        sTypoAscender=ASCENT,
        sTypoDescender=-DESCENT,
        sTypoLineGap=0,
        usWinAscent=ASCENT,
        usWinDescent=DESCENT,
        sxHeight=500,
        sCapHeight=700,
        usWeightClass=400,
        usWidthClass=5,
        fsSelection=0x00C0,
    )
    builder.setupPost(keepGlyphNames=False, isFixedPitch=1)
    builder.setupMaxp()
    # Fixed 1970-01-01 in OpenType's 1904 epoch keeps experimental builds
    # byte-reproducible without emitting malformed-timestamp warnings.
    builder.setupHead(
        created=2082844800,
        modified=2082844800,
        lowestRecPPEM=6,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / (spec["postscript"].replace("-Regular", "") + ".ttf")
    builder.save(output)
    return output


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    parser.add_argument("--version", default="0.3")
    parser.add_argument("--edge-overfill", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.edge_overfill <= 250:
        parser.error("edge-overfill must be in the range 0..250")

    outputs = [
        build_part(spec, args.output_dir, args.version, args.edge_overfill)
        for spec in PARTS
    ]
    manifest = {
        "name": "PUA 4x4",
        "version": args.version,
        "mapping": "MSB-left bit = row * 4 + (3 - column)",
        "advance": ADVANCE,
        "ascent": ASCENT,
        "descent": DESCENT,
        "edge_overfill": args.edge_overfill,
        "pixel_geometry": "exact 125x250 font-unit subcells; no cross-cell intrusion",
        "parts": [
            {
                **spec,
                "mask_end": spec["mask_start"] + PART_PATTERN_COUNT - 1,
                "codepoint_end": spec["codepoint_start"] + PART_PATTERN_COUNT - 1,
                "file": output.name,
                "sha256": sha256(output),
            }
            for spec, output in zip(PARTS, outputs)
        ],
    }
    manifest_path = args.output_dir / "pua4x4-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for output in outputs:
        print(output)
    print(manifest_path)


if __name__ == "__main__":
    main()
