#!/usr/bin/env python3
"""Audit the exhaustive PUA 4x4 specification PDF."""

import argparse
import re
from pathlib import Path

from pypdf import PdfReader

from pua4x4 import mask_to_codepoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "output/pdf/PUA-4x4-Full-Character-Specification-v0.2.pdf",
    )
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    assert len(reader.pages) == 259
    assert reader.metadata.title == "PUA 4x4 Font Family - Complete Character Specification v0.2"

    checked = 0
    print("Auditing 256 catalog pages...", flush=True)
    for high in range(256):
        page = reader.pages[3 + high]
        text = page.extract_text() or ""
        part = high >> 7
        mask_start = high << 8
        mask_end = mask_start + 0xFF
        assert f"Part {part} - masks {mask_start:04X}-{mask_end:04X}" in text
        pairs = re.findall(r"M ([0-9A-F]{4})\s+U\+([0-9A-F]{6})", text)
        expected = [
            (f"{mask:04X}", f"{mask_to_codepoint(mask):06X}")
            for mask in range(mask_start, mask_end + 1)
        ]
        assert pairs == expected
        checked += len(pairs)
        if high % 64 == 63:
            print(f"  checked through high byte {high:02X}", flush=True)

    assert checked == 65536
    print(f"PASS: {len(reader.pages)} PDF pages")
    print(f"PASS: {checked:,} masks and codepoints explicitly cataloged")
    print("PASS: Part 0/Part 1 page boundaries and document metadata")


if __name__ == "__main__":
    main()
