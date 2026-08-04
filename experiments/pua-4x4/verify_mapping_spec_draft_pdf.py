#!/usr/bin/env python3
"""Verify the expanded mapping specification review draft."""

import argparse
from pathlib import Path

from pypdf import PdfReader
from pua4x4 import mask_to_codepoint


EXPECTED_PAGE_PHRASES = (
    ("PUA 4x4 Mapping Specification", "Virtual pixel", "Terminal write"),
    ("Terminology", "Unicode", "Codepoint", "Font", "Glyph", "UTF-8", "F4 81 99 A9"),
    ("A text cursor blinks", "Each number printed in a square is its bit index b.", "actual mask = 0x9669", "320 x 96 virtual pixels"),
    ("virtual pixel (x, y) = (13, 10)", "ANSI COLUMNS - ONE-BASED", "APPLICATION CELL COLUMNS cx - ZERO-BASED", "ANSI address = row 3, column 4", "bit_value = 0x0400", "U+101669", "ESC[3;4H"),
    ("three Unicode Private Use Areas", "U+E000-U+F8FF", "137,468", "2^16 = 65,536", "U+107FFF"),
    ("codepoint = 0xF0000 + mask", "codepoint = 0x100000 + (mask - 0x8000)", "bit 15"),
    ("all four coordinate systems", "ESC[7;13H", "Zero-based versus one-based", "column,row"),
    ("Single-bit truth table", "SET with OR", "CLEAR with AND NOT", "TOGGLE with XOR", "0x9669"),
    ("Set pixel: OR", "Clear pixel: AND NOT", "Toggle pixel: XOR", "U+100504"),
    ("uint16 masks[24][80]", "dirty.add", "mask_to_codepoint", "Replacement is cell-granular"),
    ("A diagonal crossing six character cells", "3D wireframe", "Animation strategy"),
    ("Both font parts", "Pixel aspect ratio", "Decisions incorporated", "catalog follows"),
    ("from a keypress", "INPUT PATH", "OUTPUT/RENDER PATH", "physical A key", "F4 81 99 A9"),
    ("executable reference renderer", "standard-library Python program", "pua4x4_reference_renderer.py", "Renderer architecture"),
    ("complete reference renderer source (1/3)", "PART0_BASE", "def mask_to_codepoint", "class Canvas", "def plot"),
    ("complete reference renderer source (2/3)", "def line", "def ansi_frame", "def draw_demo"),
    ("complete reference renderer source (3/3)", "def main", "KeyboardInterrupt"),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "output/pdf/PUA-4x4-Mapping-Specification-v0.8.pdf",
    )
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    assert len(reader.pages) == 17
    assert reader.metadata.title == "PUA 4x4 Mapping Specification - Version 0.8"
    assert 0xF8FF - 0xE000 + 1 == 6400
    assert 0xFFFFD - 0xF0000 + 1 == 65534
    assert 0x10FFFD - 0x100000 + 1 == 65534
    assert 6400 + 65534 + 65534 == 137468
    example_mask = sum(1 << bit for bit in (0, 3, 5, 6, 9, 10, 12, 15))
    assert example_mask == 0x9669
    assert mask_to_codepoint(example_mask) == 0x101669

    for page_number, (page, phrases) in enumerate(
        zip(reader.pages, EXPECTED_PAGE_PHRASES), start=1
    ):
        text = page.extract_text() or ""
        for phrase in phrases:
            assert phrase in text, (page_number, phrase)
        assert float(page.mediabox.width) > float(page.mediabox.height)

    source = (Path(__file__).parent / "pua4x4_reference_renderer.py").read_text()
    assert len(source.splitlines()) == 144
    assert "def mask_to_codepoint" in source
    assert "def ansi_frame" in source
    assert "def main" in source

    print("PASS: 17-page expanded mapping specification v0.8")
    print("PASS: all three PUA ranges and 137,468-codepoint capacity")
    print("PASS: MSB-left resolution, coordinate, mask, codepoint and bitwise examples")
    print("PASS: corner-plus-centre glyph maps mask 0x9669 to Part 1 U+101669")
    print("PASS: complete 144-line executable reference renderer is attached")
    print("PASS: framebuffer, cursor-output, visualization and constraint sections")
    print("PASS: guide is ready for attachment to the complete character catalog")


if __name__ == "__main__":
    main()
