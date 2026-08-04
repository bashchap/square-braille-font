#!/usr/bin/env python3
"""Attach the exhaustive glyph catalog to the educational mapping guide."""

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


HERE = Path(__file__).resolve().parent
PDF_DIR = HERE / "output" / "pdf"


def assemble(guide: Path, catalog: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.append(str(guide), outline_item="Part I - Mapping and renderer guide")
    writer.append(str(catalog), outline_item="Part II - Complete 65,536-glyph catalog")
    writer.add_metadata(
        {
            "/Title": "PUA 4x4 Complete Mapping Specification and Glyph Catalog v0.8",
            "/Author": "square-braille-font project",
            "/Subject": "Terminal coordinate mapping, bitmask operations, reference renderer, and exhaustive PUA 4x4 glyph catalog",
            "/Keywords": "PUA, Unicode, 4x4, terminal graphics, bitmask, glyph catalog, ANSI, renderer",
        }
    )
    with output.open("wb") as stream:
        writer.write(stream)

    reopened = PdfReader(output)
    expected = len(PdfReader(guide).pages) + len(PdfReader(catalog).pages)
    if len(reopened.pages) != expected:
        raise RuntimeError(f"assembled page count {len(reopened.pages)} != {expected}")
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--guide",
        type=Path,
        default=PDF_DIR / "PUA-4x4-Mapping-Specification-v0.8.pdf",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=PDF_DIR / "PUA-4x4-Full-Character-Specification-v0.2.pdf",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PDF_DIR / "PUA-4x4-Complete-Mapping-and-Glyph-Catalog-v0.8.pdf",
    )
    args = parser.parse_args()
    assemble(args.guide, args.catalog, args.output)


if __name__ == "__main__":
    main()
