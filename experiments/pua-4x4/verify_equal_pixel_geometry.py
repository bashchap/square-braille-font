#!/usr/bin/env python3
"""Prove all sixteen PUA 4x4 components have equal, non-intruding bounds."""

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont


EXPECTED = {
    bit: (
        (3 - (bit % 4)) * 125,
        800 - ((bit // 4) + 1) * 250,
        (4 - (bit % 4)) * 125,
        800 - (bit // 4) * 250,
    )
    for bit in range(16)
}


def verify(path):
    font = TTFont(path, lazy=False)
    order = font.getGlyphOrder()
    glyf = font["glyf"]
    measured = []
    for bit in range(16):
        glyph = glyf[order[2 + bit]]
        actual = (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)
        assert actual == EXPECTED[bit], (path, bit, actual, EXPECTED[bit])
        x0, y0, x1, y1 = actual
        assert x1 - x0 == 125
        assert y1 - y0 == 250
        assert 0 <= x0 < x1 <= 500
        assert -200 <= y0 < y1 <= 800
        measured.append(actual)
    font.close()
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path, nargs="?", default=Path("build"))
    args = parser.parse_args()
    first = verify(args.build_dir / "PUA4x4Part0.ttf")
    second = verify(args.build_dir / "PUA4x4Part1.ttf")
    assert first == second
    print("PASS: all 16 components in both parts are exactly 125 x 250 units")
    print("PASS: all component bounds remain inside the 500 x 1000 character cell")
    print("PASS: local columns 0,1,2,3 and rows 0,1,2,3 have equal geometry")
    print("PASS: physical columns implement MSB-left rows 3,2,1,0 through 15,14,13,12")


if __name__ == "__main__":
    main()
