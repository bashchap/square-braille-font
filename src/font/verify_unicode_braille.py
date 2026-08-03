#!/usr/bin/env python3
"""Verify official Braille aliases, PUA compatibility and normal text."""

from __future__ import annotations

import argparse

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont


def outline(font, name):
    pen = RecordingPen()
    font.getGlyphSet()[name].draw(pen)
    return pen.value


def verify(path):
    font = TTFont(path)
    cmap = font.getBestCmap()
    assert font["head"].unitsPerEm == 1000
    assert font["hhea"].ascent == 800 and font["hhea"].descent == -200

    for codepoint in range(0x20, 0x7F):
        assert codepoint in cmap, hex(codepoint)
        assert font["hmtx"][cmap[codepoint]][0] == 500

    for pattern in range(256):
        braille = 0x2800 + pattern
        pua = 0xE000 + pattern
        assert braille in cmap and pua in cmap
        assert cmap[braille] == cmap[pua], (hex(braille), "not a true glyph alias")
        assert font["hmtx"][cmap[braille]][0] == 500
        assert outline(font, cmap[braille]) == outline(font, cmap[pua])

    for codepoint in (0x00E9, 0x03A9, 0x0416, 0x20AC, 0x2192, 0x2500, 0x2588):
        assert codepoint in cmap, hex(codepoint)

    family = font["name"].getName(1, 3, 1, 0x409).toUnicode()
    assert family == "Square Braille Unicode Text Seamless", family
    font.close()
    print(f"PASS {path}: text + U+2800-U+28FF + U+E000-U+E0FF")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fonts", nargs="+")
    args = parser.parse_args()
    for path in args.fonts:
        verify(path)


if __name__ == "__main__":
    main()
