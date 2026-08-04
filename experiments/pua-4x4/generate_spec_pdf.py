#!/usr/bin/env python3
"""Generate the exhaustive PUA 4x4 character specification PDF."""

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from pua4x4 import mask_to_codepoint


PAGE_SIZE = landscape(A3)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE
TOTAL_CATALOG_PAGES = 256
FRONT_PAGES = 3
TOTAL_PAGES = FRONT_PAGES + TOTAL_CATALOG_PAGES

INK = colors.HexColor("#10233F")
MUTED = colors.HexColor("#53657A")
GRID = colors.HexColor("#C8D2DE")
PALE = colors.HexColor("#F3F6F9")
PART0 = colors.HexColor("#047D9D")
PART1 = colors.HexColor("#7B3FB2")


def fit_text(pdf, text, x, y, max_width, size, font="Helvetica"):
    while size > 4 and stringWidth(text, font, size) > max_width:
        size -= 0.25
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)


def page_footer(pdf, page_number):
    pdf.setStrokeColor(GRID)
    pdf.line(32, 25, PAGE_WIDTH - 32, 25)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(32, 13, "PUA 4x4 complete character specification - version 0.2 (MSB-left)")
    pdf.drawRightString(PAGE_WIDTH - 32, 13, f"Page {page_number} of {TOTAL_PAGES}")


def draw_bit_grid(pdf, x, y, size, mask, fill_color=INK, labels=False):
    cell = size / 4
    for row in range(4):
        for column in range(4):
            bit = row * 4 + (3 - column)
            left = x + column * cell
            bottom = y + (3 - row) * cell
            pdf.setStrokeColor(colors.HexColor("#AEBBC9"))
            pdf.setFillColor(fill_color if mask & (1 << bit) else colors.white)
            pdf.rect(left, bottom, cell, cell, stroke=1, fill=1)
            if labels:
                pdf.setFillColor(colors.white if mask & (1 << bit) else MUTED)
                pdf.setFont("Helvetica", max(5, cell * 0.24))
                pdf.drawCentredString(left + cell / 2, bottom + cell * 0.36, str(bit))


def cover_page(pdf):
    pdf.bookmarkPage("cover")
    pdf.addOutlineEntry("Title and scope", "cover", level=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawString(54, PAGE_HEIGHT - 92, "PUA 4x4 Font Family")
    pdf.setFont("Helvetica", 20)
    pdf.setFillColor(PART0)
    pdf.drawString(54, PAGE_HEIGHT - 126, "Complete character specification - version 0.2")

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 11)
    pdf.drawString(54, PAGE_HEIGHT - 158, "All 65,536 MSB-left 4x4 bitmap patterns across two supplementary-PUA fonts")
    pdf.drawString(54, PAGE_HEIGHT - 176, "Generated 2026-08-04")

    grid_size = 260
    draw_bit_grid(pdf, 62, 155, grid_size, 0xA55A, PART0, labels=True)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(62, 135, "Representative mask A55A")

    x = 390
    y = PAGE_HEIGHT - 245
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(x, y, "Authoritative model")
    y -= 35
    lines = [
        "One Unicode character represents one complete 4x4 bitmap.",
        "Bit number = row x 4 + (3 - column); each four-bit row is written MSB-left.",
        "Grid rows are 3,2,1,0 through 15,14,13,12 from left to right.",
        "Part 0 maps masks 0000-7FFF to U+F0000-U+F7FFF.",
        "Part 1 maps masks 8000-FFFF to U+100000-U+107FFF.",
        "Each glyph occupies one fixed-width 500 x 1000 terminal cell.",
        "The catalog pages explicitly enumerate every mask and codepoint.",
    ]
    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(MUTED)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= 25

    pdf.setFillColor(PALE)
    pdf.roundRect(x, 160, PAGE_WIDTH - x - 60, 145, 10, stroke=0, fill=1)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(x + 18, 275, "Unicode status")
    pdf.setFont("Helvetica", 10)
    status = [
        "These assignments are a private mapping convention, not a Unicode standard.",
        "The fonts use Supplementary Private Use Area-A and Area-B codepoints.",
        "Correct display requires both font parts and the published mapping formula.",
    ]
    sy = 250
    for line in status:
        pdf.drawString(x + 18, sy, line)
        sy -= 23

    page_footer(pdf, 1)
    pdf.showPage()


def specification_page(pdf, manifest):
    pdf.bookmarkPage("specification")
    pdf.addOutlineEntry("Font and mapping specification", "specification", level=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(42, PAGE_HEIGHT - 55, "Font and mapping specification")

    columns_x = (42, 412, 790)
    top = PAGE_HEIGHT - 98

    sections = [
        (
            "Logical bitmap",
            [
                "Grid: 4 columns x 4 rows",
                "Pattern count: 65,536",
                "Mask range: 0000-FFFF",
                "Bit formula: row x 4 + (3 - column)",
                "Row 0 bits: 3,2,1,0",
                "Row 1 bits: 7,6,5,4",
                "Row 2 bits: 11,10,9,8",
                "Row 3 bits: 15,14,13,12",
            ],
        ),
        (
            "Font metrics",
            [
                "Units per em: 1000",
                "Advance width: 500",
                "Ascender: 800",
                "Descender: 200",
                "Line gap: 0",
                "Nominal pixel: 125 x 250 units",
                "Exterior overfill: 0 units",
                "Fixed pitch: yes",
            ],
        ),
        (
            "OpenType construction",
            [
                "Outline format: TrueType glyf",
                "Character map: cmap format 12",
                "Pattern glyphs per font: 32,768",
                "Reusable pixel components: 16",
                "Glyphs per font: 32,786",
                "Supplementary-PUA encoding",
                "U+0020 blank metric anchor",
                "Composite glyph construction",
            ],
        ),
    ]

    for x, (heading, lines) in zip(columns_x, sections):
        pdf.setFillColor(PALE)
        pdf.roundRect(x, top - 235, 335, 235, 8, stroke=0, fill=1)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(x + 16, top - 28, heading)
        pdf.setFont("Helvetica", 10)
        pdf.setFillColor(MUTED)
        y = top - 55
        for line in lines:
            pdf.drawString(x + 16, y, line)
            y -= 21

    y = top - 282
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(42, y, "Mapping formulas")
    pdf.setFont("Courier", 11)
    pdf.setFillColor(MUTED)
    formulas = [
        "if 0000 <= mask <= 7FFF: codepoint = F0000 + mask",
        "if 8000 <= mask <= FFFF: codepoint = 100000 + (mask - 8000)",
        "Part 0 decode: mask = codepoint - F0000",
        "Part 1 decode: mask = 8000 + (codepoint - 100000)",
    ]
    for formula in formulas:
        y -= 23
        pdf.drawString(58, y, formula)

    y -= 35
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(42, y, "Released v0.3 MSB-left assets")
    y -= 24
    for part in manifest["parts"]:
        pdf.setFillColor(PART0 if part["part"] == 0 else PART1)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(58, y, f"Part {part['part']}: {part['file']} - {part['family']}")
        y -= 16
        pdf.setFillColor(MUTED)
        pdf.setFont("Courier", 8.4)
        pdf.drawString(76, y, f"SHA-256 {part['sha256']}")
        y -= 24

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(620, top - 282, "Boundary examples")
    examples = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF)
    ex_y = top - 330
    for mask in examples:
        part = mask >> 15
        color = PART0 if part == 0 else PART1
        draw_bit_grid(pdf, 626, ex_y - 22, 38, mask, color)
        pdf.setFillColor(INK)
        pdf.setFont("Courier-Bold", 9)
        pdf.drawString(676, ex_y, f"mask {mask:04X}  U+{mask_to_codepoint(mask):06X}  Part {part}")
        ex_y -= 52

    page_footer(pdf, 2)
    pdf.showPage()


def index_page(pdf):
    pdf.bookmarkPage("catalog-index")
    pdf.addOutlineEntry("Catalog index", "catalog-index", level=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(42, PAGE_HEIGHT - 55, "Catalog index by mask high byte")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(42, PAGE_HEIGHT - 77, "Each indexed page enumerates all 256 low-byte values for the selected high byte.")

    left, bottom = 52, 54
    width, height = PAGE_WIDTH - 104, PAGE_HEIGHT - 155
    cell_w, cell_h = width / 16, height / 16
    for high in range(256):
        row, column = divmod(high, 16)
        x = left + column * cell_w
        y = bottom + (15 - row) * cell_h
        part = high >> 7
        pdf.setStrokeColor(GRID)
        pdf.setFillColor(colors.HexColor("#EAF6F9") if part == 0 else colors.HexColor("#F3ECF9"))
        pdf.rect(x, y, cell_w, cell_h, stroke=1, fill=1)
        pdf.setFillColor(PART0 if part == 0 else PART1)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 7, y + cell_h - 14, f"{high:02X}xx")
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7)
        pdf.drawString(x + 7, y + 7, f"page {FRONT_PAGES + high + 1}")

    page_footer(pdf, 3)
    pdf.showPage()


def catalog_page(pdf, high):
    part = high >> 7
    mask_start = high << 8
    mask_end = mask_start + 0xFF
    cp_start = mask_to_codepoint(mask_start)
    cp_end = mask_to_codepoint(mask_end)
    page_number = FRONT_PAGES + high + 1
    bookmark = f"catalog-{high:02x}"
    pdf.bookmarkPage(bookmark)
    pdf.addOutlineEntry(
        f"{high:02X}xx - Part {part}", bookmark, level=1, closed=True
    )

    accent = PART0 if part == 0 else PART1
    pdf.setFillColor(accent)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(30, PAGE_HEIGHT - 31, f"Part {part} - masks {mask_start:04X}-{mask_end:04X}")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawRightString(
        PAGE_WIDTH - 30,
        PAGE_HEIGHT - 29,
        f"U+{cp_start:06X}-U+{cp_end:06X} | high byte {high:02X}",
    )

    left, bottom = 25, 31
    grid_width, grid_height = PAGE_WIDTH - 50, PAGE_HEIGHT - 78
    cell_w, cell_h = grid_width / 16, grid_height / 16
    for low in range(256):
        row, column = divmod(low, 16)
        mask = mask_start + low
        codepoint = mask_to_codepoint(mask)
        x = left + column * cell_w
        y = bottom + (15 - row) * cell_h

        pdf.setStrokeColor(GRID)
        pdf.setFillColor(colors.white if (row + column) % 2 == 0 else PALE)
        pdf.rect(x, y, cell_w, cell_h, stroke=1, fill=1)

        diagram_size = min(24, cell_h - 9)
        draw_bit_grid(pdf, x + 4, y + (cell_h - diagram_size) / 2, diagram_size, mask, accent)
        text_x = x + diagram_size + 9
        fit_text(pdf, f"M {mask:04X}", text_x, y + cell_h * 0.57, cell_w - diagram_size - 12, 6.1, "Courier-Bold")
        fit_text(pdf, f"U+{codepoint:06X}", text_x, y + cell_h * 0.30, cell_w - diagram_size - 12, 5.8, "Courier")

    page_footer(pdf, page_number)
    pdf.showPage()


def generate(output, manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=PAGE_SIZE, pageCompression=1)
    pdf.setTitle("PUA 4x4 Font Family - Complete Character Specification v0.2")
    pdf.setAuthor("square-braille-font project")
    pdf.setSubject("Exhaustive mapping and glyph catalog for all 65,536 PUA 4x4 patterns")
    pdf.setKeywords("PUA, 4x4, terminal graphics, font specification, Unicode")
    cover_page(pdf)
    specification_page(pdf, manifest)
    index_page(pdf)
    pdf.addOutlineEntry("Complete character catalog", "catalog-00", level=0)
    for high in range(256):
        catalog_page(pdf, high)
    pdf.save()
    print(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "build-v0.3/pua4x4-manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "output/pdf/PUA-4x4-Full-Character-Specification-v0.2.pdf",
    )
    args = parser.parse_args()
    generate(args.output, args.manifest)


if __name__ == "__main__":
    main()
