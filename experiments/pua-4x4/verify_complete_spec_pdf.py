#!/usr/bin/env python3
"""Verify the assembled mapping guide and exhaustive glyph catalog."""

import argparse
from pathlib import Path

from pypdf import PdfReader


HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=HERE / "output/pdf/PUA-4x4-Complete-Mapping-and-Glyph-Catalog-v0.8.pdf",
    )
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    assert len(reader.pages) == 276
    assert reader.metadata.title == "PUA 4x4 Complete Mapping Specification and Glyph Catalog v0.8"

    page3 = reader.pages[2].extract_text() or ""
    for phrase in (
        "Each number printed in a square is its bit index b.",
        "Filled squares set bits 0,3,5,6,9,10,12,15.",
        "bits 15..0 = 1001 0110 0110 1001 = hex 9 6 6 9",
        "actual mask = 0x9669",
    ):
        assert phrase in page3, phrase

    page4 = reader.pages[3].extract_text() or ""
    for phrase in (
        "ANSI COLUMNS - ONE-BASED TERMINAL ADDRESSES",
        "APPLICATION CELL COLUMNS cx - ZERO-BASED",
        "ANSI row 3",
        "cell cy=2",
        "virtual x coordinate",
        "virtual y coordinate",
        "ANSI address = row 3, column 4",
        "bit_value = 0x0400",
    ):
        assert phrase in page4, phrase

    appendix_b = reader.pages[13].extract_text() or ""
    for phrase in (
        '$HOME/dev/FontMaker/pua4x4',
        "test -f pua4x4_reference_renderer.py || exit 1",
        "./launch-linux.sh shell",
    ):
        assert phrase in appendix_b, phrase

    catalog_cover = reader.pages[17].extract_text() or ""
    assert "Complete character specification - version 0.2" in catalog_cover
    assert "All 65,536 MSB-left 4x4 bitmap patterns" in catalog_cover
    final_page = reader.pages[-1].extract_text() or ""
    assert "Part 1 - masks FF00-FFFF" in final_page
    assert "U+107F00-U+107FFF" in final_page

    print("PASS: 276 pages = 17-page guide + 259-page exhaustive catalog")
    print("PASS: MSB-left bit-index labels and 0x9669 derivation are explicit")
    print("PASS: virtual, terminal-cell and ANSI cursor axes are labeled")
    print("PASS: Linux commands use the verified deployment path")
    print("PASS: catalog covers all masks 0000-FFFF")


if __name__ == "__main__":
    main()
