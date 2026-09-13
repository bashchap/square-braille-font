#!/usr/bin/env python3
"""Generate isolated v0.4 direct-union PUA 4x4 candidate fonts.

The accepted MSB-left mask mathematics is unchanged. Unlike v0.3, each
pattern is stored as a simple outline of the selected 4x4 cell union. Shared
internal edges are removed before the TrueType glyph is written. The distinct
family and file names allow v0.3 and this candidate to coexist during tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


UNITS_PER_EM = 1000
ADVANCE = 500
ASCENT = 800
DESCENT = 200
GRID = 4
CELL_WIDTH = 125
CELL_HEIGHT = 250
PART_SIZE = 0x8000
IDENTITY_VERSION = "0.4-candidate.1"

PARTS = (
    {
        "part": 0,
        "family": "PUA 4x4 Part 0 v0.4 Candidate",
        "postscript": "PUA4x4Part0V04Candidate-Regular",
        "filename": "PUA4x4Part0V04Candidate.ttf",
        "mask_start": 0x0000,
        "codepoint_start": 0xF0000,
    },
    {
        "part": 1,
        "family": "PUA 4x4 Part 1 v0.4 Candidate",
        "postscript": "PUA4x4Part1V04Candidate-Regular",
        "filename": "PUA4x4Part1V04Candidate.ttf",
        "mask_start": 0x8000,
        "codepoint_start": 0x100000,
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def empty_glyph():
    return TTGlyphPen(None).glyph()


def rectangle_glyph(x_min: int, y_min: int, x_max: int, y_max: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, y_min))
    pen.lineTo((x_min, y_max))
    pen.lineTo((x_max, y_max))
    pen.lineTo((x_max, y_min))
    pen.closePath()
    return pen.glyph()


def bit_for_local(local_x: int, local_y: int) -> int:
    return 4 * local_y + (3 - local_x)


def cell_box(local_x: int, local_y: int) -> tuple[int, int, int, int]:
    x_min = local_x * CELL_WIDTH
    x_max = (local_x + 1) * CELL_WIDTH
    y_max = ASCENT - local_y * CELL_HEIGHT
    y_min = y_max - CELL_HEIGHT
    return x_min, y_min, x_max, y_max


def union_boundary_edges(mask: int):
    """Return clockwise directed boundary edges after shared-edge removal."""
    edges = set()
    for local_y in range(GRID):
        for local_x in range(GRID):
            if not mask & (1 << bit_for_local(local_x, local_y)):
                continue
            x_min, y_min, x_max, y_max = cell_box(local_x, local_y)
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


def direction(edge) -> int:
    """Return N/E/S/W as 0/1/2/3, ordered clockwise."""
    (x0, y0), (x1, y1) = edge
    delta = (x1 - x0, y1 - y0)
    return {
        (0, CELL_HEIGHT): 0,
        (CELL_WIDTH, 0): 1,
        (0, -CELL_HEIGHT): 2,
        (-CELL_WIDTH, 0): 3,
    }[delta]


def simplify_loop(points):
    """Remove collinear vertices while retaining contour orientation."""
    result = list(points)
    changed = True
    while changed and len(result) > 4:
        changed = False
        reduced = []
        count = len(result)
        for index, current in enumerate(result):
            previous = result[(index - 1) % count]
            following = result[(index + 1) % count]
            first = (current[0] - previous[0], current[1] - previous[1])
            second = (following[0] - current[0], following[1] - current[1])
            if first[0] * second[1] - first[1] * second[0] == 0:
                changed = True
            else:
                reduced.append(current)
        if reduced:
            result = reduced
        else:
            break
    return result


def trace_union_contours(mask: int):
    """Trace boundary loops, choosing the right turn at diagonal contacts."""
    unused = union_boundary_edges(mask)
    contours = []
    while unused:
        edge = min(unused)
        unused.remove(edge)
        start = edge[0]
        points = [start, edge[1]]
        previous_direction = direction(edge)
        while points[-1] != start:
            vertex = points[-1]
            candidates = [candidate for candidate in unused if candidate[0] == vertex]
            if not candidates:
                raise AssertionError((mask, "open contour", points))

            def turn_priority(candidate):
                turn = (direction(candidate) - previous_direction) % 4
                return {1: 0, 0: 1, 3: 2, 2: 3}[turn]

            edge = min(candidates, key=lambda item: (turn_priority(item), item))
            unused.remove(edge)
            previous_direction = direction(edge)
            points.append(edge[1])
        contours.append(simplify_loop(points[:-1]))
    return contours


def pattern_glyph(mask: int):
    if mask == 0:
        return empty_glyph()
    pen = TTGlyphPen(None)
    for contour in trace_union_contours(mask):
        pen.moveTo(contour[0])
        for point in contour[1:]:
            pen.lineTo(point)
        pen.closePath()
    return pen.glyph()


def pattern_left_side_bearing(mask: int) -> int:
    """Keep raw outline x coordinates fixed relative to the advance origin."""
    if mask == 0:
        return 0
    selected_columns = [
        local_x
        for local_y in range(GRID)
        for local_x in range(GRID)
        if mask & (1 << bit_for_local(local_x, local_y))
    ]
    return min(selected_columns) * CELL_WIDTH


def notdef_glyph():
    return rectangle_glyph(50, 0, 450, 700)


def build_part(spec, output_dir: Path, version: str) -> Path:
    masks = range(spec["mask_start"], spec["mask_start"] + PART_SIZE)
    pattern_names = tuple(f"mask{mask:04X}" for mask in masks)
    glyph_order = (".notdef", "space") + pattern_names
    glyphs = {".notdef": notdef_glyph(), "space": empty_glyph()}
    for mask, name in zip(masks, pattern_names):
        glyphs[name] = pattern_glyph(mask)

    cmap = {
        spec["codepoint_start"] + offset: name
        for offset, name in enumerate(pattern_names)
    }
    cmap[0x20] = "space"
    metrics = {".notdef": (ADVANCE, 50), "space": (ADVANCE, 0)}
    for mask, name in zip(masks, pattern_names):
        # In TrueType the effective rendered x coordinate is
        # raw_x - xMin + leftSideBearing. Setting lsb=xMin makes the effective
        # coordinate equal raw_x, which is required by the approved 4x4 grid.
        metrics[name] = (ADVANCE, pattern_left_side_bearing(mask))

    builder = FontBuilder(UNITS_PER_EM, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ASCENT, descent=-DESCENT, lineGap=0)
    builder.setupNameTable(
        {
            "familyName": spec["family"],
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{spec['postscript']};{version}",
            "fullName": spec["family"],
            "psName": spec["postscript"],
            "version": f"Version {version}",
            "description": (
                "Candidate graphics-only 4x4 terminal tiles using the approved "
                "MSB-left mapping. Every glyph is a simple outline of the exact "
                "selected-cell union; shared internal edges are removed."
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
    builder.setupHead(
        created=2082844800,
        modified=2082844800,
        lowestRecPPEM=4,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / spec["filename"]
    builder.save(output)
    return output


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "build-v0.4-candidate.1",
    )
    parser.add_argument("--version", default=IDENTITY_VERSION)
    args = parser.parse_args()

    outputs = [build_part(spec, args.output_dir, args.version) for spec in PARTS]
    manifest = {
        "name": "PUA 4x4 v0.4 Candidate",
        "version": args.version,
        "status": "candidate-not-installed-by-default",
        "mapping": "MSB-left bit = 4 * local_y + (3 - local_x)",
        "outline_model": "simple union contours; shared internal edges removed",
        "horizontal_placement": (
            "leftSideBearing equals each nonempty glyph xMin, preserving raw "
            "outline coordinates relative to the fixed advance origin"
        ),
        "units_per_em": UNITS_PER_EM,
        "advance": ADVANCE,
        "ascent": ASCENT,
        "descent": DESCENT,
        "grid": [4, 4],
        "subcell": [CELL_WIDTH, CELL_HEIGHT],
        "outline_bounds": [0, -DESCENT, ADVANCE, ASCENT],
        "edge_overfill": 0,
        "parts": [
            {
                **spec,
                "mask_end": spec["mask_start"] + PART_SIZE - 1,
                "codepoint_end": spec["codepoint_start"] + PART_SIZE - 1,
                "file": output.name,
                "sha256": sha256(output),
            }
            for spec, output in zip(PARTS, outputs)
        ],
    }
    manifest_path = args.output_dir / "pua4x4-v0.4-candidate-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for output in outputs:
        print(output)
    print(manifest_path)


if __name__ == "__main__":
    main()
