#!/usr/bin/env fontforge
"""Add ordinary text glyphs to a generated PUA Square Braille font."""

import argparse
import os

import fontforge
import psMat


PUA_FIRST = 0xE000
PUA_LAST = 0xE0FF


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphics-font", required=True)
    parser.add_argument("--text-font", required=True)
    parser.add_argument("--font-name", default="PUA Square Braille Text Seamless")
    parser.add_argument("--version", default="1.2")
    parser.add_argument("--output-dir", default="dist")
    return parser.parse_args()


def main():
    args = parse_args()
    target = fontforge.open(args.graphics_font)
    source = fontforge.open(args.text_font)

    # Normalize text vertically to the graphics font's 1000-unit em.  DejaVu
    # Sans Mono is then condensed horizontally into the established 500-unit
    # terminal advance without changing its baseline or vertical proportions.
    source.em = target.em
    source_advance = source[ord("M")].width
    target_advance = target[PUA_FIRST].width
    x_scale = float(target_advance) / source_advance

    copied = 0
    zero_width = 0
    for source_glyph in source.glyphs():
        codepoint = source_glyph.unicode
        if (codepoint < 0x20 or codepoint > 0x10FFFF or
                PUA_FIRST <= codepoint <= PUA_LAST):
            continue

        original_width = source_glyph.width
        glyph = target.createChar(codepoint)
        source.selection.none()
        source.selection.select(("unicode",), codepoint)
        source.copy()
        target.selection.none()
        target.selection.select(("unicode",), codepoint)
        target.paste()

        glyph.transform(psMat.scale(x_scale, 1.0))
        if original_width == 0:
            glyph.width = 0
            zero_width += 1
        else:
            glyph.width = target_advance
        copied += 1

    target.fontname = args.font_name.replace(" ", "") + "-Regular"
    target.familyname = args.font_name
    target.fullname = args.font_name
    target.weight = "Regular"
    target.os2_weight = 400
    target.macstyle = 0
    target.version = args.version
    target.comment = (
        "Text-capable terminal font containing seamless square-cell graphics "
        "at U+E000-U+E0FF. The PUA patterns correspond by offset to Unicode "
        "Braille Patterns U+2800-U+28FF. Text outlines derive from DejaVu "
        "Sans Mono and are normalized to a 500-unit terminal cell."
    )
    target.copyright = (
        "Square PUA glyphs generated for this project. Text glyphs derived "
        "from DejaVu Sans Mono. Copyright (c) 2003 by Bitstream, Inc. All "
        "Rights Reserved. DejaVu changes are in public domain. Distributed "
        "under the Bitstream Vera font license; see LICENSE-DejaVu.txt."
    )

    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.join(args.output_dir, args.font_name.replace(" ", "-"))
    target.generate(base + ".ttf", flags=("opentype",))
    target.generate(base + ".otf", flags=("opentype",))
    target.save(base + ".sfd")
    target.close()
    source.close()
    print("Copied %d text glyphs (%d zero-width)" % (copied, zero_width))


if __name__ == "__main__":
    main()
