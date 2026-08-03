#!/usr/bin/env fontforge
"""Generate a tiled-square Braille font in the Unicode Private Use Area."""

import argparse
import os

import fontforge


DOT_NUMBERS = (
    (1, 4),
    (2, 5),
    (3, 6),
    (7, 8),
)


def add_component_outline(layer, cells, cell_w, cell_h, top, bottom, width, overfill):
    """Draw the external boundary of one 4-connected group of grid cells."""
    edges = set()
    for row, col in cells:
        x0, x1 = col * cell_w, (col + 1) * cell_w
        y1, y0 = top - row * cell_h, top - (row + 1) * cell_h
        if col == 0:
            x0 -= overfill
        if col == 1:
            x1 = width + overfill
        if row == 0:
            y1 = top + overfill
        if row == 3:
            y0 = bottom - overfill
        for edge in (((x0, y0), (x0, y1)), ((x0, y1), (x1, y1)),
                     ((x1, y1), (x1, y0)), ((x1, y0), (x0, y0))):
            reverse = (edge[1], edge[0])
            if reverse in edges:
                edges.remove(reverse)
            else:
                edges.add(edge)

    successors = {start: end for start, end in edges}
    start = next(iter(successors))
    contour = fontforge.contour()
    contour.moveTo(*start)
    point = successors[start]
    while point != start:
        contour.lineTo(*point)
        point = successors[point]
    contour.closed = True
    layer += contour


def connected_components(cells):
    remaining = set(cells)
    while remaining:
        seed = remaining.pop()
        component = {seed}
        pending = [seed]
        while pending:
            row, col = pending.pop()
            for neighbor in ((row - 1, col), (row + 1, col),
                             (row, col - 1), (row, col + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    pending.append(neighbor)
        yield component


def build_font(args):
    if args.width % 2 or (args.ascent + args.descent) % 4:
        raise SystemExit("width must divide by 2 and total em height must divide by 4")

    font = fontforge.font()
    font.encoding = "UnicodeFull"
    font.fontname = args.font_name.replace(" ", "-")
    font.familyname = args.font_name
    font.fullname = args.font_name
    font.version = args.version
    # PANOSE proportion 9 declares a monospaced font to font selectors.
    font.os2_panose = (2, 11, 5, 9, 2, 2, 2, 2, 2, 4)
    font.comment = (
        "Square-cell rendering of the Unicode Braille Patterns block "
        "U+2800-U+28FF, mapped in order to a Unicode Private Use Area."
    )
    font.em = args.ascent + args.descent
    font.ascent = args.ascent
    font.descent = args.descent
    font.hhea_ascent = args.ascent
    font.hhea_ascent_add = False
    font.hhea_descent = -args.descent
    font.hhea_descent_add = False
    font.hhea_linegap = 0
    font.os2_typoascent = args.ascent
    font.os2_typoascent_add = False
    font.os2_typodescent = -args.descent
    font.os2_typodescent_add = False
    font.os2_typolinegap = 0
    font.os2_winascent = args.ascent
    font.os2_winascent_add = False
    font.os2_windescent = args.descent
    font.os2_windescent_add = False
    font.os2_use_typo_metrics = True

    notdef = font.createChar(-1, ".notdef")
    notdef.width = args.width

    # VTE derives terminal cell metrics from ordinary printable characters.
    # Encoding blank ASCII anchors prevents a fallback font with a different
    # advance/line box from determining the graphics terminal's cell size.
    for codepoint in range(0x20, 0x7F):
        metric_anchor = font.createChar(codepoint)
        metric_anchor.width = args.width

    cell_w = args.width // 2
    cell_h = (args.ascent + args.descent) // 4
    top = args.ascent

    for pattern in range(256):
        codepoint = args.pua_start + pattern
        glyph = font.createChar(codepoint, "uni%04X" % codepoint)
        glyph.width = args.width
        cells = {(row, col) for row, dot_pair in enumerate(DOT_NUMBERS)
                 for col, dot_number in enumerate(dot_pair)
                 if pattern & (1 << (dot_number - 1))}
        layer = fontforge.layer()
        for component in connected_components(cells):
            add_component_outline(layer, component, cell_w, cell_h, top,
                                  -args.descent, args.width, args.edge_overfill)
        glyph.foreground = layer
        glyph.width = args.width

    if args.autoinstruct:
        font.selection.all()
        font.autoHint()
        font.autoInstr()
        font.gasp_version = 1
        font.gasp = ((65535, ("gridfit", "antialias", "symmetric-smoothing",
                              "gridfit+smoothing")),)

    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.join(args.output_dir, font.fontname)
    font.generate(base + ".ttf", flags=("opentype",))
    font.generate(base + ".otf", flags=("opentype",))
    font.save(base + ".sfd")
    font.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-name", default="PUA Square Braille")
    parser.add_argument("--pua-start", type=lambda value: int(value, 0), default=0xE000)
    parser.add_argument("--width", type=int, default=500)
    parser.add_argument("--ascent", type=int, default=800)
    parser.add_argument("--descent", type=int, default=200)
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--edge-overfill", type=int, default=0,
                        help="font units extended beyond outer glyph boundaries")
    parser.add_argument("--autoinstruct", action="store_true",
                        help="generate TrueType grid-fitting instructions")
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    if args.edge_overfill < 0:
        parser.error("edge-overfill must be non-negative")
    return args


if __name__ == "__main__":
    build_font(parse_args())
