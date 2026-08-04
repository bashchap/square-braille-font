#!/usr/bin/env python3
"""Generate the expanded PUA 4x4 mapping specification."""

import argparse
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from pua4x4 import mask_to_codepoint


PAGE_SIZE = landscape(A3)
W, H = PAGE_SIZE
PAGES = 17
MARGIN = 42

INK = colors.HexColor("#112640")
MUTED = colors.HexColor("#51677D")
PALE = colors.HexColor("#F2F6F9")
GRID = colors.HexColor("#C2CEDA")
P0 = colors.HexColor("#037F9F")
P1 = colors.HexColor("#7840B4")
GREEN = colors.HexColor("#15956A")
ORANGE = colors.HexColor("#D77724")
RED = colors.HexColor("#C64758")


def wrapped_lines(text, font, size, width):
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = line + " " + word
            if stringWidth(candidate, font, size) <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def paragraph(pdf, text, x, y, width, size=10, leading=14, color=MUTED, font="Helvetica"):
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    for line in wrapped_lines(text, font, size, width):
        pdf.drawString(x, y, line)
        y -= leading
    return y


def page_title(pdf, title, subtitle, page):
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(MARGIN, H - 48, title)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(MARGIN, H - 67, subtitle)
    pdf.setStrokeColor(GRID)
    pdf.line(MARGIN, H - 78, W - MARGIN, H - 78)
    footer(pdf, page)


def footer(pdf, page):
    pdf.setStrokeColor(GRID)
    pdf.line(MARGIN, 27, W - MARGIN, 27)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(MARGIN, 14, "PUA 4x4 mapping specification - version 0.8 (MSB-left)")
    pdf.drawRightString(W - MARGIN, 14, f"Page {page} of {PAGES}")


def box(pdf, x, y, width, height, heading=None, fill=PALE, stroke=GRID):
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.roundRect(x, y, width, height, 8, stroke=1, fill=1)
    if heading:
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(x + 14, y + height - 22, heading)


def arrow(pdf, x1, y1, x2, y2, color=P0):
    pdf.setStrokeColor(color)
    pdf.setFillColor(color)
    pdf.setLineWidth(1.8)
    pdf.line(x1, y1, x2, y2)
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    back_x, back_y = x2 - ux * 8, y2 - uy * 8
    pdf.line(x2, y2, back_x + px * 4, back_y + py * 4)
    pdf.line(x2, y2, back_x - px * 4, back_y - py * 4)


def bit_grid(pdf, x, y, size, mask, fill=P0, labels=True, highlight=None):
    cell = size / 4
    for row in range(4):
        for column in range(4):
            bit = row * 4 + (3 - column)
            left = x + column * cell
            bottom = y + (3 - row) * cell
            active = bool(mask & (1 << bit))
            pdf.setStrokeColor(ORANGE if bit == highlight else GRID)
            pdf.setLineWidth(2 if bit == highlight else 0.8)
            pdf.setFillColor(fill if active else colors.white)
            pdf.rect(left, bottom, cell, cell, stroke=1, fill=1)
            if labels:
                pdf.setFillColor(colors.white if active else MUTED)
                pdf.setFont("Helvetica-Bold", max(5, cell * 0.22))
                pdf.drawCentredString(left + cell / 2, bottom + cell * 0.37, str(bit))
    pdf.setLineWidth(1)


def terminal_grid(pdf, x, y, columns, rows, cell_w, cell_h, highlighted=None):
    for row in range(rows):
        for column in range(columns):
            left = x + column * cell_w
            bottom = y + (rows - 1 - row) * cell_h
            selected = highlighted == (column, row)
            pdf.setFillColor(colors.HexColor("#FFF3E6") if selected else colors.white)
            pdf.setStrokeColor(ORANGE if selected else GRID)
            pdf.setLineWidth(2 if selected else 0.8)
            pdf.rect(left, bottom, cell_w, cell_h, stroke=1, fill=1)
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica", 6.5)
            pdf.drawCentredString(left + cell_w / 2, bottom + cell_h / 2 - 2, f"{column},{row}")
    pdf.setLineWidth(1)


def terminal_mock(pdf, x, y, width, height, cursor=(3, 2), cursor_on=True, glyph_mask=0):
    """Draw a small terminal window with a cursor in a known character cell."""
    columns, rows = 8, 4
    title_height = 22
    body_height = height - title_height
    cell_w = width / columns
    cell_h = body_height / rows

    pdf.setFillColor(colors.HexColor("#24313D"))
    pdf.roundRect(x, y, width, height, 7, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#111A22"))
    pdf.rect(x, y, width, body_height, stroke=0, fill=1)
    for offset, dot_color in enumerate((RED, ORANGE, GREEN)):
        pdf.setFillColor(dot_color)
        pdf.circle(x + 13 + offset * 14, y + height - 11, 3.5, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#D7E7F3"))
    pdf.setFont("Courier-Bold", 7.5)
    pdf.drawString(x + 58, y + height - 14, "terminal - 8 columns x 4 rows")

    for row in range(rows):
        for column in range(columns):
            left = x + column * cell_w
            bottom = y + body_height - (row + 1) * cell_h
            pdf.setStrokeColor(colors.HexColor("#344553"))
            pdf.setLineWidth(0.35)
            pdf.rect(left, bottom, cell_w, cell_h, stroke=1, fill=0)

    pdf.setFillColor(colors.HexColor("#73D7DF"))
    pdf.setFont("Courier-Bold", 9)
    pdf.drawString(x + 5, y + body_height - cell_h + 7, "$ draw")

    cursor_column, cursor_row = cursor
    cursor_x = x + cursor_column * cell_w
    cursor_y = y + body_height - (cursor_row + 1) * cell_h
    pdf.setStrokeColor(ORANGE)
    pdf.setLineWidth(2)
    pdf.rect(cursor_x, cursor_y, cell_w, cell_h, stroke=1, fill=0)
    if cursor_on:
        pdf.setFillColor(colors.HexColor("#FFE09A"))
        pdf.rect(cursor_x + 2, cursor_y + 2, cell_w - 4, cell_h - 4, stroke=0, fill=1)
    sub_w = (cell_w - 4) / 4
    sub_h = (cell_h - 4) / 4
    pdf.setFillColor(colors.HexColor("#182A38") if cursor_on else colors.HexColor("#73D7DF"))
    for local_row in range(4):
        for local_column in range(4):
            bit = local_row * 4 + (3 - local_column)
            if glyph_mask & (1 << bit):
                pdf.rect(
                    cursor_x + 2 + local_column * sub_w,
                    cursor_y + 2 + (3 - local_row) * sub_h,
                    sub_w,
                    sub_h,
                    stroke=0,
                    fill=1,
                )
    pdf.setLineWidth(1)


def virtual_grid(pdf, x, y, character_columns, character_rows, pixel, points=()):
    point_set = set(points)
    total_columns = character_columns * 4
    total_rows = character_rows * 4
    for row in range(total_rows):
        for column in range(total_columns):
            left = x + column * pixel
            bottom = y + (total_rows - 1 - row) * pixel
            pdf.setFillColor(P0 if (column, row) in point_set else colors.white)
            boundary = column % 4 == 0 or row % 4 == 0
            pdf.setStrokeColor(INK if boundary else GRID)
            pdf.setLineWidth(1.2 if boundary else 0.35)
            pdf.rect(left, bottom, pixel, pixel, stroke=1, fill=1)
    pdf.setLineWidth(1)


def code_box(pdf, x, y, width, lines, heading=None):
    height = 48 + len(lines) * 17
    box(pdf, x, y, width, height, heading)
    pdf.setFillColor(INK)
    pdf.setFont("Courier", 9)
    line_y = y + height - 42
    for line in lines:
        pdf.drawString(x + 14, line_y, line)
        line_y -= 17
    return height


def page1(pdf, page_number=1):
    pdf.bookmarkPage("overview")
    pdf.addOutlineEntry("Overview and processing pipeline", "overview", 0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 31)
    pdf.drawString(MARGIN, H - 72, "PUA 4x4 Mapping Specification")
    pdf.setFillColor(P0)
    pdf.setFont("Helvetica", 18)
    pdf.drawString(MARGIN, H - 104, "Expanded educational specification - complete glyph catalog attached")

    paragraph(
        pdf,
        "The PUA 4x4 font family converts every cursor-addressable terminal character cell into a programmable 4 x 4 monochrome bitmap. This document keeps four coordinate concepts distinct: a terminal cell, the ANSI cursor address used to reach that cell, a virtual pixel in the enlarged graphical canvas, and a local pixel inside one 4 x 4 cell. The application changes a 16-bit cell mask, maps that mask to a PUA codepoint, and writes the complete replacement glyph at the terminal cursor address.",
        MARGIN,
        H - 145,
        W - 2 * MARGIN,
        12,
        18,
    )

    stages = [
        ("Virtual pixel", "(x, y)"),
        ("Terminal cell", "(cx, cy)"),
        ("Local pixel", "(lx, ly)"),
        ("Bit index", "b = 4ly + lx"),
        ("Cell mask", "m = 0000-FFFF"),
        ("PUA glyph", "P0/P1 codepoint"),
        ("Terminal write", "ANSI cursor + UTF-8"),
    ]
    start_x, stage_y = 52, 400
    stage_w, stage_h, gap = 140, 90, 18
    for index, (heading, detail) in enumerate(stages):
        x = start_x + index * (stage_w + gap)
        box(pdf, x, stage_y, stage_w, stage_h, fill=colors.white)
        pdf.setFillColor(P0 if index < 4 else P1)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(x + stage_w / 2, stage_y + 57, heading)
        pdf.setFillColor(MUTED)
        pdf.setFont("Courier", 8.5)
        pdf.drawCentredString(x + stage_w / 2, stage_y + 33, detail)
        if index < len(stages) - 1:
            arrow(pdf, x + stage_w, stage_y + stage_h / 2, x + stage_w + gap - 3, stage_y + stage_h / 2)

    box(pdf, 52, 145, W - 104, 190, "What this specification teaches")
    bullets = [
        "How terminal columns and rows become a virtual pixel coordinate system four times larger in each axis.",
        "How one virtual pixel selects one bit in one 16-bit cell mask.",
        "How mask values select Part 0 or Part 1 and map reversibly to Unicode codepoints.",
        "How OR, AND NOT and XOR implement set, clear and toggle operations.",
        "How a shadow framebuffer and dirty-cell updates turn bit operations into terminal output.",
        "Which terminal, color, aspect-ratio and font-fallback constraints remain.",
    ]
    y = 298
    for bullet in bullets:
        pdf.setFillColor(P0)
        pdf.circle(70, y + 3, 2.5, stroke=0, fill=1)
        y = paragraph(pdf, bullet, 82, y, W - 160, 10.5, 19, INK)

    footer(pdf, page_number)
    pdf.showPage()


def page_terms(pdf, page_number):
    page_title(
        pdf,
        "Terminology: from Unicode text to a visible terminal glyph",
        "These terms describe different layers. Treating codepoint, glyph, character and terminal cell as synonyms makes the mapping difficult to reason about.",
        page_number,
    )

    terms = [
        ("Unicode", "A universal coded-character standard. It defines codepoints and properties; it does not prescribe one visual drawing for every font."),
        ("Codepoint", "An integer written as U+ followed by hexadecimal digits. Examples: U+0041 and the project-private U+101669."),
        ("Character", "An abstract textual element, such as LATIN CAPITAL LETTER A. In casual terminal discussion, 'character' may also mean one cell; this document avoids that ambiguity."),
        ("Text", "An ordered sequence of encoded characters/codepoints. Example: A followed by B is the sequence U+0041 U+0042."),
        ("Font", "A resource containing glyph drawings and a cmap that associates supported codepoints with glyph identifiers. Different fonts can draw U+0041 differently."),
        ("Glyph", "The visible shape selected from a font. PUA 4x4 glyph U+101669 draws mask 0x9669: four corners plus the central 2 x 2 block."),
        ("Terminal cell", "One fixed grid position addressed by the terminal cursor. A cell stores or displays one glyph cluster plus attributes such as foreground and background color."),
        ("UTF-8", "A byte encoding for Unicode codepoints. U+0041 is byte 41; U+101669 is the four-byte sequence F4 81 99 A9."),
    ]
    card_w = (W - 2 * MARGIN - 30) / 2
    card_h = 105
    for index, (heading, detail) in enumerate(terms):
        column = index % 2
        row = index // 2
        x = MARGIN + column * (card_w + 30)
        y = 610 - row * 118
        box(pdf, x, y, card_w, card_h, heading, fill=colors.white, stroke=P0 if column == 0 else P1)
        paragraph(pdf, detail, x + 14, y + 65, card_w - 28, 8.8, 13, MUTED)

    box(pdf, 42, 88, W - 84, 92, "How the layers connect: two concrete examples", fill=colors.HexColor("#EAF6F9"), stroke=P0)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 9.2)
    pdf.drawString(66, 142, "normal text: key A -> application outputs U+0041 -> UTF-8 41 -> text font cmap -> glyph A -> terminal cell")
    pdf.setFillColor(P1)
    pdf.drawString(66, 113, "PUA graphics: mask 9669 -> U+101669 -> UTF-8 F4 81 99 A9 -> Part 1 cmap -> 4x4 glyph -> terminal cell")
    pdf.showPage()


def page_pua(pdf, page_number):
    page_title(
        pdf,
        "Unicode Private Use Areas and the 65,536-pattern boundary",
        "Private-use codepoints are valid Unicode scalar values whose meaning is defined by a private agreement - here, the published PUA 4x4 mapping convention.",
        page_number,
    )

    box(pdf, 42, 555, W - 84, 175, "The three Unicode Private Use Areas")
    headers = ("Area", "Inclusive range", "Usable codepoints", "How PUA 4x4 uses it")
    rows = [
        ("BMP Private Use Area", "U+E000-U+F8FF", "6,400", "unused"),
        ("Supplementary PUA-A", "U+F0000-U+FFFFD", "65,534", "P0 uses U+F0000-U+F7FFF"),
        ("Supplementary PUA-B", "U+100000-U+10FFFD", "65,534", "P1 uses U+100000-U+107FFF"),
        ("Total private-use capacity", "three disjoint ranges", "137,468", "65,536 assigned by this project"),
    ]
    xs = (66, 330, 610, 830)
    y = 681
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9.5)
    for x, heading in zip(xs, headers):
        pdf.drawString(x, y, heading)
    y -= 31
    for index, row in enumerate(rows):
        pdf.setStrokeColor(GRID)
        pdf.line(62, y - 9, W - 62, y - 9)
        pdf.setFillColor(P0 if index in (1, 3) else P1 if index == 2 else MUTED)
        pdf.setFont("Courier-Bold" if index == 3 else "Courier", 9)
        for x, value in zip(xs, row):
            pdf.drawString(x, y, value)
        y -= 31

    box(pdf, 42, 302, 520, 210, "Why 4 x 4 reaches a technical boundary", fill=colors.HexColor("#FFF6E9"), stroke=ORANGE)
    boundary_text = (
        "A 4 x 4 cell has 16 independently selectable positions, so it has 2^16 = 65,536 distinct masks. One supplementary PUA contains 65,534 assignable codepoints - two fewer than required. OpenType glyph indices are also 16-bit; a font must reserve at least glyph 0 for .notdef, so one ordinary font cannot safely provide all 65,536 data glyphs. The design therefore uses two codepoint ranges and two font faces, each with exactly 32,768 project glyphs."
    )
    paragraph(pdf, boundary_text, 64, 466, 475, 10, 15, INK)
    pdf.setFillColor(ORANGE)
    pdf.setFont("Courier-Bold", 12)
    pdf.drawString(72, 333, "2^16 = 65,536 masks")

    box(pdf, 600, 302, W - 642, 210, "The bit-15 split is mathematical, not arbitrary")
    pdf.setFillColor(P0)
    pdf.setFont("Courier-Bold", 11)
    pdf.drawString(624, 464, "P0 when bit 15 = 0: 0000-7FFF")
    pdf.drawString(624, 433, "cp = 0xF0000 + mask")
    pdf.setFillColor(P1)
    pdf.drawString(624, 387, "P1 when bit 15 = 1: 8000-FFFF")
    pdf.drawString(624, 356, "cp = 0x100000 + (mask - 0x8000)")
    paragraph(
        pdf,
        "Because each row is MSB-left, bit 15 is the bottom-left local pixel. Turning that pixel on crosses from P0 to P1 while every other local bit keeps the same numerical meaning.",
        624,
        326,
        W - 690,
        8.8,
        12,
        MUTED,
    )

    box(pdf, 42, 76, W - 84, 177, "Boundary examples prove continuity across P0 and P1", fill=colors.HexColor("#F7F9FB"))
    examples = [
        ("7FFE", "0F7FFE", "P0", "high bit clear; bit 15 off"),
        ("7FFF", "0F7FFF", "P0", "last P0 mask"),
        ("8000", "100000", "P1", "first P1 mask; only bit 15 on"),
        ("8001", "100001", "P1", "bits 15 and 0 on"),
        ("9669", "101669", "P1", "four corners plus central 2 x 2"),
        ("FFFF", "107FFF", "P1", "all 16 local pixels on"),
    ]
    x_positions = (65, 255, 450, 650, 885)
    headings = ("Mask", "Codepoint", "Font", "Meaning", "Round trip")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9)
    for x, heading in zip(x_positions, headings):
        pdf.drawString(x, 211, heading)
    y = 183
    pdf.setFont("Courier", 8.5)
    for mask, cp, part, meaning in examples:
        pdf.setFillColor(P0 if part == "P0" else P1)
        values = (mask, "U+" + cp, part, meaning, "cp -> mask " + mask)
        for x, value in zip(x_positions, values):
            pdf.drawString(x, y, value)
        y -= 19
    pdf.showPage()


def page2(pdf, page_number=2):
    page_title(
        pdf,
        "Start with the terminal cell, then zoom into its 4 x 4 grid",
        "A blinking text cursor identifies one whole character cell. PUA 4x4 replaces the character in that cell with one 16-bit bitmap glyph.",
        page_number,
    )

    definitions = [
        ("Terminal cell (cx, cy)", "One character position, zero-based in the application."),
        ("ANSI cursor (row, column)", "The same cell addressed one-based, with row written first."),
        ("Virtual pixel (x, y)", "One point in the 4C x 4R graphical canvas."),
        ("Local pixel (lx, ly)", "One of 16 positions inside the selected cell."),
    ]
    definition_w = (W - 2 * MARGIN - 36) / 4
    for index, (heading, detail) in enumerate(definitions):
        x = MARGIN + index * (definition_w + 12)
        box(pdf, x, 635, definition_w, 100, heading, fill=colors.white, stroke=P0 if index < 2 else P1)
        paragraph(pdf, detail, x + 12, 692, definition_w - 24, 8.5, 12, MUTED)

    box(pdf, 42, 335, 610, 255, "A text cursor blinks, but its terminal cell does not move")
    terminal_mock(pdf, 65, 390, 265, 145, cursor=(3, 2), cursor_on=True, glyph_mask=0x9669)
    terminal_mock(pdf, 365, 390, 265, 145, cursor=(3, 2), cursor_on=False, glyph_mask=0x9669)
    pdf.setFillColor(ORANGE)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(197, 370, "time t0: cursor visible over U+101669")
    pdf.drawCentredString(497, 370, "time t1: cursor hidden; glyph remains")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawCentredString(347, 349, "Both frames show U+101669 in zero-based application cell (cx, cy) = (3, 2): ANSI row 3, column 4.")

    arrow(pdf, 652, 463, 688, 463, ORANGE)
    box(pdf, 690, 335, W - 732, 255, "Zoom into that one character cell")
    bit_grid(pdf, 725, 372, 175, 0x9669, P1, labels=True)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(930, 525, "The glyph is a 16-bit mask.")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(930, 500, "Columns inside the cell: lx = 0..3")
    pdf.drawString(930, 480, "Rows inside the cell:     ly = 0..3")
    pdf.drawString(930, 460, "Bit index: b = 4 * ly + (3 - lx)")
    pdf.setFillColor(RED)
    pdf.setFont("Helvetica-Bold", 8.8)
    pdf.drawString(930, 440, "Each number printed in a square is its bit index b.")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.7)
    pdf.drawString(930, 421, "Filled squares set bits 0,3,5,6,9,10,12,15.")
    pdf.drawString(930, 406, "mask = sum(1 << b) for every filled square")
    pdf.drawString(930, 391, "= 2^0+2^3+2^5+2^6+2^9+2^10+2^12+2^15")
    pdf.drawString(930, 376, "bits 15..0 = 1001 0110 0110 1001 = hex 9 6 6 9")
    pdf.setFillColor(P0)
    pdf.setFont("Courier-Bold", 8.6)
    pdf.drawString(930, 358, "actual mask = 0x9669")
    pdf.setFillColor(P1)
    pdf.setFont("Helvetica-Bold", 7.8)
    pdf.drawString(930, 343, "That one mask selects one complete glyph: U+101669")

    box(pdf, 42, 92, W - 84, 195, "The full terminal becomes a larger virtual-pixel canvas", fill=colors.HexColor("#EAF6F9"), stroke=P0)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 13)
    pdf.drawString(70, 238, "terminal: C columns x R rows")
    pdf.drawString(70, 205, "virtual:  (4 x C) pixels x (4 x R) pixels")
    pdf.drawString(70, 172, "capacity: 16 x C x R independently addressable positions")
    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(650, 214, "80 x 24 terminal cells")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(820, 174, "becomes")
    pdf.setFillColor(P1)
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawRightString(W - 70, 150, "320 x 96 virtual pixels")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(W - 62, 112, "The logical pixels are normally rectangular because terminal character cells are taller than they are wide.")
    pdf.showPage()


def page3(pdf, page_number=3):
    page_title(
        pdf,
        "Follow one virtual pixel all the way to a cursor address and codepoint",
        "Worked example: virtual pixel (x, y) = (13, 10), measured from the top-left of a graphics region whose ANSI origin is row 1, column 1.",
        page_number,
    )

    box(pdf, 42, 405, 390, 325, "1. Locate (13, 10) in the virtual canvas")
    virtual_grid(pdf, 120, 473, 6, 4, 11, points=((13, 10),))
    grid_x, grid_y, pixel = 120, 473, 11
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillColor(ORANGE)
    pdf.drawCentredString(grid_x + 12 * pixel, grid_y + 16 * pixel + 42, "ANSI COLUMNS - ONE-BASED TERMINAL ADDRESSES")
    pdf.setFillColor(P0)
    pdf.drawCentredString(grid_x + 12 * pixel, grid_y + 16 * pixel + 17, "APPLICATION CELL COLUMNS cx - ZERO-BASED")
    for cell_column in range(6):
        centre = grid_x + (cell_column * 4 + 2) * pixel
        pdf.setFillColor(ORANGE)
        pdf.drawCentredString(centre, grid_y + 16 * pixel + 31, str(cell_column + 1))
        pdf.setFillColor(P0)
        pdf.drawCentredString(centre, grid_y + 16 * pixel + 6, str(cell_column))
    for cell_row in range(4):
        centre = grid_y + (16 - cell_row * 4 - 2) * pixel
        pdf.setFillColor(ORANGE)
        pdf.drawRightString(grid_x - 7, centre + 3, f"ANSI row {cell_row + 1}")
        pdf.setFillColor(P0)
        pdf.drawRightString(grid_x - 7, centre - 7, f"cell cy={cell_row}")
    pdf.setFillColor(P1)
    pdf.setFont("Helvetica", 6)
    for virtual_x in (0, 4, 8, 12, 16, 20, 23):
        pdf.drawCentredString(grid_x + (virtual_x + 0.5) * pixel, grid_y - 9, str(virtual_x))
    for virtual_y in (0, 4, 8, 12, 15):
        centre = grid_y + (16 - virtual_y - 0.5) * pixel
        pdf.drawString(grid_x + 24 * pixel + 4, centre - 2, str(virtual_y))
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 6.4)
    pdf.drawCentredString(grid_x + 12 * pixel, grid_y - 19, "virtual x coordinate x - zero-based")
    pdf.saveState()
    pdf.translate(grid_x + 24 * pixel + 25, grid_y + 8 * pixel)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "virtual y coordinate y - zero-based")
    pdf.restoreState()
    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(76, 438, "24 x 16 virtual pixels = 6 x 4 terminal cells")
    pdf.setFillColor(ORANGE)
    pdf.drawRightString(407, 438, "selected virtual pixel: (13, 10)")
    pdf.setFont("Helvetica-Bold", 7.2)
    pdf.drawString(76, 420, "same selected cell: application (cx, cy) = (3, 2)  |  ANSI address = row 3, column 4")

    arrow(pdf, 432, 565, 462, 565, ORANGE)
    box(pdf, 465, 405, 315, 325, "2. Divide by four: cell + local position")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 10)
    equations = [
        "cx = 13 // 4 = 3",
        "cy = 10 // 4 = 2",
        "",
        "lx = 13 % 4 = 1",
        "ly = 10 % 4 = 2",
    ]
    y = 663
    for line in equations:
        pdf.drawString(490, y, line)
        y -= 29
    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(490, 495, "terminal cell = (cx, cy) = (3, 2)")
    pdf.setFillColor(P1)
    pdf.drawString(490, 468, "local pixel  = (lx, ly) = (1, 2)")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(490, 432, "// chooses the whole terminal cell.")
    pdf.drawString(490, 416, "% chooses a position inside that cell.")

    arrow(pdf, 780, 565, 810, 565, ORANGE)
    box(pdf, 813, 405, W - 855, 325, "3. Convert the local position to a bit")
    bit_grid(pdf, 835, 485, 165, 0x9669, P1, labels=True, highlight=10)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 8.5)
    pdf.drawString(1018, 621, "b = 4 * ly + (3 - lx)")
    pdf.drawString(1018, 588, "b = 4 * 2 + (3 - 1) = 10")
    pdf.drawString(1018, 555, "bit_value = 1 << 10")
    pdf.setFillColor(P0)
    pdf.drawString(1018, 522, "bit_value = 0x0400")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(1018, 470, "MSB-left row numbering:")
    pdf.drawString(1018, 451, "row 0 is bits 3,2,1,0 (left to right);")
    pdf.drawString(1018, 432, "row 3 is bits 15,14,13,12.")

    box(pdf, 42, 238, W - 84, 125, "4. Update the cell mask, then choose the replacement glyph", fill=colors.HexColor("#EAF6F9"), stroke=P0)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 10)
    pdf.drawString(66, 315, "old_mask = 0x9269")
    pdf.drawString(310, 315, "new_mask = old_mask | 0x0400 = 0x9669")
    pdf.setFillColor(P1)
    pdf.drawString(720, 315, "0x9669 >= 0x8000 -> Part 1")
    pdf.setFont("Courier-Bold", 8.5)
    pdf.drawString(930, 318, "codepoint = 0x100000 + (0x9669 - 0x8000)")
    pdf.drawString(930, 296, "          = U+101669")
    paragraph(
        pdf,
        "The old mask already contains the four corners and three centre pixels. OR sets local bit 10 without disturbing them, producing mask 0x9669: the exact eight-pixel glyph shown under the blinking cursor on page 2.",
        66,
        269,
        W - 132,
        9.5,
        14,
        MUTED,
    )

    box(pdf, 42, 88, W - 84, 105, "5. Move the text cursor to terminal cell (3, 2) and write U+101669")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 10.5)
    pdf.drawString(66, 151, "ANSI row    = origin_row    + cy = 1 + 2 = 3")
    pdf.drawString(66, 124, "ANSI column = origin_column + cx = 1 + 3 = 4")
    pdf.setFillColor(ORANGE)
    pdf.setFont("Courier-Bold", 13)
    pdf.drawString(610, 137, "ESC[3;4H  +  UTF-8(U+101669)")
    pdf.setFillColor(RED)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawRightString(W - 62, 103, "Remember: application coordinates use (column, row); ANSI CUP syntax writes [row;column].")
    pdf.showPage()


def page_coordinates(pdf, page_number):
    page_title(
        pdf,
        "How all four coordinate systems interact",
        "The same point is described at four layers. Keep column-before-row application tuples separate from row-before-column ANSI syntax.",
        page_number,
    )

    stages = [
        ("Virtual canvas", "(x, y) = (13, 10)", "zero-based virtual pixels", P1),
        ("Terminal cell", "(cx, cy) = (3, 2)", "zero-based character cells", P0),
        ("Local 4 x 4", "(lx, ly) = (1, 2)", "zero-based inside the cell", P1),
        ("ANSI cursor", "[row;column] = [3;4]", "one-based, row written first", ORANGE),
    ]
    stage_w = (W - 2 * MARGIN - 54) / 4
    for index, (heading, value, detail, accent) in enumerate(stages):
        x = MARGIN + index * (stage_w + 18)
        box(pdf, x, 610, stage_w, 120, heading, fill=colors.white, stroke=accent)
        pdf.setFillColor(accent)
        pdf.setFont("Courier-Bold", 11)
        pdf.drawCentredString(x + stage_w / 2, 669, value)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawCentredString(x + stage_w / 2, 638, detail)
        if index < 3:
            arrow(pdf, x + stage_w, 670, x + stage_w + 15, 670, accent)

    box(pdf, 42, 300, 555, 260, "Nested geometry: canvas -> terminal cell -> local pixel")
    virtual_grid(pdf, 90, 325, 6, 4, 13, points=((13, 10),))
    pdf.setFillColor(ORANGE)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(73, 321, "Thick lines are terminal-cell boundaries; the orange point is virtual (13,10).")

    box(pdf, 635, 300, W - 677, 260, "The equations, including a non-default graphics origin")
    equations = [
        "cx, lx = divmod(x, 4)       -> divmod(13, 4) = (3, 1)",
        "cy, ly = divmod(y, 4)       -> divmod(10, 4) = (2, 2)",
        "bit = 4 * ly + (3 - lx)     -> 4 * 2 + (3 - 1) = 10",
        "",
        "ANSI row    = origin_row    + cy",
        "ANSI column = origin_column + cx",
        "",
        "origin (row 1, col 1)   -> ESC[3;4H",
        "origin (row 5, col 10)  -> ESC[7;13H",
    ]
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 9.2)
    y = 511
    for line in equations:
        pdf.drawString(660, y, line)
        y -= 22

    box(pdf, 42, 88, W - 84, 165, "Zero-based versus one-based - the practical rule", fill=colors.HexColor("#FFF6E9"), stroke=ORANGE)
    paragraph(
        pdf,
        "Graphics algorithms naturally use zero-based arrays: virtual pixel (0,0) is the top-left pixel, terminal cell (0,0) is the top-left cell, and local pixel (0,0) is the top-left subcell. ANSI CUP is a terminal protocol command and normally starts at 1,1. Therefore add the one-based graphics-region origin only when emitting output. Also reverse the tuple order: application data is written (column,row), but ESC[row;columnH writes the row first.",
        64,
        207,
        W - 128,
        10,
        15,
        INK,
    )
    pdf.setFillColor(RED)
    pdf.setFont("Courier-Bold", 11)
    pdf.drawCentredString(W / 2, 112, "(cx, cy) = (3, 2)  is emitted as  ESC[3;4H  when the region begins at ANSI (row 1, column 1)")
    pdf.showPage()


def page4(pdf, page_number=4):
    page_title(
        pdf,
        "From a 16-bit mask to Part 0 or Part 1",
        "All bit manipulation happens on the mask first. The final mask value then selects the font part and Unicode codepoint.",
        page_number,
    )

    box(pdf, 42, 565, 540, 155, "Part 0 - high bit clear", fill=colors.HexColor("#EAF6F9"), stroke=P0)
    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(64, 675, "0000 <= mask <= 7FFF")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 12)
    pdf.drawString(64, 635, "codepoint = 0xF0000 + mask")
    pdf.drawString(64, 603, "range     = U+0F0000-U+0F7FFF")

    box(pdf, 610, 565, W - 652, 155, "Part 1 - high bit set", fill=colors.HexColor("#F3ECF9"), stroke=P1)
    pdf.setFillColor(P1)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(632, 675, "8000 <= mask <= FFFF")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 12)
    pdf.drawString(632, 635, "codepoint = 0x100000 + (mask - 0x8000)")
    pdf.drawString(632, 603, "range     = U+100000-U+107FFF")

    box(pdf, 42, 290, W - 84, 225, "Why the split occurs at bit 15")
    bit_grid(pdf, 74, 322, 160, 0x8000, P1, labels=True, highlight=15)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(270, 455, "Bit 15 is the bottom-left position in MSB-left row order.")
    explanatory = (
        "A 16-bit glyph mask has 65,536 possible values, but one supplementary Private Use Area segment used here provides only 32,768 consecutive codepoints. Part 0 stores masks whose highest bit is clear. Part 1 stores masks whose highest bit is set. Therefore a glyph is in Part 1 exactly when the bottom-left logical pixel is on. The other 15 pixels may have any combination in either case."
    )
    paragraph(pdf, explanatory, 270, 425, W - 330, 10.5, 16, MUTED)

    examples = [
        (0x0000, "blank cell"),
        (0x0400, "only bit 10"),
        (0x7FFF, "all except bit 15"),
        (0x8000, "only bit 15"),
        (0xFFFF, "all 16 pixels"),
    ]
    y = 298
    pdf.setFont("Courier-Bold", 9.5)
    for mask, meaning in examples:
        color = P0 if mask < 0x8000 else P1
        pdf.setFillColor(color)
        pdf.drawString(270, y, f"mask {mask:04X} -> U+{mask_to_codepoint(mask):06X} -> Part {mask >> 15}")
        pdf.setFillColor(MUTED)
        pdf.drawString(650, y, meaning)
        y -= 24

    box(pdf, 42, 88, W - 84, 150, "Reverse mapping is equally deterministic", fill=colors.HexColor("#F7F9FB"))
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 10.5)
    reverse = [
        "Part 0: mask = codepoint - 0xF0000",
        "Part 1: mask = 0x8000 + (codepoint - 0x100000)",
        "Invariant: mask_to_codepoint(codepoint_to_mask(cp)) == cp",
    ]
    y = 190
    for line in reverse:
        pdf.drawString(68, y, line)
        y -= 31
    pdf.showPage()


def operation_panel(pdf, x, y, width, heading, before, after, formula, color):
    box(pdf, x, y, width, 185, heading, fill=colors.white, stroke=color)
    bit_grid(pdf, x + 15, y + 46, 100, before, P0 if before < 0x8000 else P1, labels=False)
    arrow(pdf, x + 127, y + 96, x + 170, y + 96, color)
    bit_grid(pdf, x + 184, y + 46, 100, after, P0 if after < 0x8000 else P1, labels=False)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 8.5)
    pdf.drawString(x + 15, y + 27, formula)
    pdf.setFillColor(MUTED)
    pdf.setFont("Courier", 8)
    pdf.drawString(x + 15, y + 10, f"{before:04X} -> {after:04X}")


def page_logic(pdf, page_number):
    page_title(
        pdf,
        "Boolean logic for setting, clearing, toggling and combining pixels",
        "A glyph mask is just a 16-bit integer. Each Boolean operation is applied independently to corresponding bit positions.",
        page_number,
    )

    box(pdf, 42, 470, 420, 260, "Single-bit truth table")
    headers = ("old A", "selector B", "A OR B", "A AND B", "A XOR B", "NOT B")
    xs = (65, 125, 210, 285, 360, 425)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 8)
    for x, heading in zip(xs, headers):
        pdf.drawCentredString(x, 679, heading)
    rows = [
        (0, 0, 0, 0, 0, 1),
        (0, 1, 1, 0, 1, 0),
        (1, 0, 1, 0, 1, 1),
        (1, 1, 1, 1, 0, 0),
    ]
    y = 642
    pdf.setFont("Courier-Bold", 11)
    for row in rows:
        pdf.setStrokeColor(GRID)
        pdf.line(58, y - 10, 446, y - 10)
        for x, value in zip(xs, row):
            pdf.setFillColor(P1 if value else MUTED)
            pdf.drawCentredString(x, y, str(value))
        y -= 38
    paragraph(
        pdf,
        "OR is 1 when either input is 1. AND is 1 only when both inputs are 1. XOR is 1 when the inputs differ. NOT reverses a bit.",
        65,
        510,
        370,
        8.7,
        12,
        MUTED,
    )

    box(pdf, 500, 470, W - 542, 260, "How one selector changes mask 0x9269")
    selector = "0000 0100 0000 0000  (0x0400, bit 10)"
    examples = [
        ("SET with OR", "1001 0010 0110 1001", "OR  " + selector, "1001 0110 0110 1001  = 0x9669", GREEN),
        ("CLEAR with AND NOT", "1001 0110 0110 1001", "AND 1111 1011 1111 1111", "1001 0010 0110 1001  = 0x9269", ORANGE),
        ("TOGGLE with XOR", "1001 0010 0110 1001", "XOR " + selector, "1001 0110 0110 1001  = 0x9669", P1),
    ]
    y = 675
    for heading, before, operator, result, accent in examples:
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(525, y, heading)
        pdf.setFillColor(INK)
        pdf.setFont("Courier", 8.3)
        pdf.drawString(690, y, before)
        pdf.drawString(690, y - 20, operator)
        pdf.drawString(690, y - 40, result)
        y -= 64

    panel_w = (W - 2 * MARGIN - 40) / 3
    operation_panel(pdf, MARGIN, 255, panel_w, "OR: set without disturbing", 0x9269, 0x9669, "mask |= 0x0400", GREEN)
    operation_panel(pdf, MARGIN + panel_w + 20, 255, panel_w, "AND NOT: force clear", 0x9669, 0x9269, "mask &= ~0x0400 & 0xFFFF", ORANGE)
    operation_panel(pdf, MARGIN + 2 * (panel_w + 20), 255, panel_w, "XOR: invert selected bit", 0x9269, 0x9669, "mask ^= 0x0400", P1)

    box(pdf, 42, 88, W - 84, 120, "Choosing the correct operation", fill=colors.HexColor("#F7F9FB"))
    choices = [
        ("OR", "Draw/add pixels or combine independent layers. Existing 1 bits remain 1."),
        ("AND NOT", "Erase selected pixels. The final & 0xFFFF keeps Python's unlimited-width complement inside 16 bits."),
        ("XOR", "Toggle cursors, selection outlines or reversible overlays. Applying the same XOR twice restores the original mask."),
        ("AND", "Clip a layer to an allowed mask or retain only the pixels shared by two masks."),
    ]
    y = 166
    for index, (name, detail) in enumerate(choices):
        x = 66 + (index % 2) * 560
        line_y = y - (index // 2) * 42
        pdf.setFillColor(P0 if index % 2 == 0 else P1)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(x, line_y, name)
        paragraph(pdf, detail, x + 70, line_y, 465, 8.8, 12, MUTED)
    pdf.showPage()


def page5(pdf, page_number=5):
    page_title(
        pdf,
        "Bit-level manipulation selects the replacement glyph",
        "The application modifies a cell mask using normal integer logic, then remaps the complete result to one PUA character.",
        page_number,
    )

    panel_w = (W - 2 * MARGIN - 40) / 3
    operation_panel(pdf, MARGIN, 520, panel_w, "Set pixel: OR", 0x0124, 0x8124, "mask |= (1 << 15)", GREEN)
    operation_panel(pdf, MARGIN + panel_w + 20, 520, panel_w, "Clear pixel: AND NOT", 0x8124, 0x8104, "mask &= ~(1 << 5)", ORANGE)
    operation_panel(pdf, MARGIN + 2 * (panel_w + 20), 520, panel_w, "Toggle pixel: XOR", 0x8104, 0x8504, "mask ^= (1 << 10)", P1)

    box(pdf, 42, 270, W - 84, 205, "Worked sequence and resulting codepoints")
    rows = [
        ("Initial", "mask = 0x0124", "U+0F0124", "Part 0"),
        ("Set bit 15", "0x0124 OR 0x8000 = 0x8124", "U+100124", "Part 1"),
        ("Clear bit 5", "0x8124 AND NOT 0x0020 = 0x8104", "U+100104", "Part 1"),
        ("Toggle bit 10", "0x8104 XOR 0x0400 = 0x8504", "U+100504", "Part 1"),
    ]
    headings = ("Operation", "Mask calculation", "Replacement glyph", "Font")
    xs = (65, 270, 760, 1010)
    y = 430
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 10)
    for x, heading in zip(xs, headings):
        pdf.drawString(x, y, heading)
    y -= 30
    for index, row in enumerate(rows):
        pdf.setStrokeColor(GRID)
        pdf.line(60, y - 8, W - 60, y - 8)
        pdf.setFillColor(P0 if index == 0 else P1)
        pdf.setFont("Courier-Bold", 9.5)
        for x, value in zip(xs, row):
            pdf.drawString(x, y, value)
        y -= 34

    box(pdf, 42, 88, W - 84, 135, "Other useful operations", fill=colors.HexColor("#F7F9FB"))
    operations = [
        "Test:     if mask & (1 << bit): pixel is on",
        "Replace:  mask = new_mask & 0xFFFF",
        "Combine:  mask = layer_a | layer_b",
        "Erase:    mask = 0x0000",
        "Fill:     mask = 0xFFFF",
    ]
    pdf.setFillColor(INK)
    pdf.setFont("Courier", 9.5)
    x, y = 70, 180
    for index, line in enumerate(operations):
        pdf.drawString(x, y, line)
        if index == 2:
            x, y = 650, 180
        else:
            y -= 27
    pdf.showPage()


def page6(pdf, page_number=6):
    page_title(
        pdf,
        "Shadow framebuffer, cursor movement and terminal output",
        "A terminal does not provide a dependable read-back API for displayed glyph state. The application owns the masks and emits changed cells.",
        page_number,
    )

    box(pdf, 42, 535, 505, 185, "Application-owned framebuffer")
    paragraph(
        pdf,
        "Store one unsigned 16-bit mask for every terminal character cell. For an 80 x 24 terminal this is an 80-column by 24-row array containing 1,920 masks, or only 3,840 bytes when stored densely. The array is the authoritative graphical state. The terminal is an output device, not the source of truth.",
        62,
        675,
        465,
        10.5,
        16,
        MUTED,
    )
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 11)
    pdf.drawString(70, 565, "uint16 masks[24][80]")

    box(pdf, 585, 535, W - 627, 185, "Dirty-cell rendering")
    paragraph(
        pdf,
        "When a virtual pixel operation changes a mask, mark that character cell dirty. At the end of the frame, compare front and back buffers or visit the dirty set. Move the ANSI cursor only to changed cells and write each replacement codepoint as UTF-8. Unchanged cells require no output.",
        605,
        675,
        W - 667,
        10.5,
        16,
        MUTED,
    )

    code_box(
        pdf,
        42,
        235,
        W - 84,
        [
            "def plot(x, y, operation='set'):",
            "    cell_col, local_col = divmod(x, 4)",
            "    cell_row, local_row = divmod(y, 4)",
            "    bit = local_row * 4 + (3 - local_col)",
            "    old = masks[cell_row][cell_col]",
            "    new = old | (1 << bit)                 # set; use AND NOT or XOR as required",
            "    if new != old:",
            "        masks[cell_row][cell_col] = new",
            "        dirty.add((cell_col, cell_row))",
            "",
            "for cell_col, cell_row in dirty:",
            "    cp = mask_to_codepoint(masks[cell_row][cell_col])",
            "    write(f'\\x1b[{origin_row+cell_row};{origin_col+cell_col}H' + chr(cp))",
        ],
        "Reference pseudocode",
    )

    box(pdf, 42, 88, W - 84, 105, "Replacement is cell-granular even though addressing is subcell-granular", fill=colors.HexColor("#FFF6E9"), stroke=ORANGE)
    paragraph(
        pdf,
        "Changing one virtual pixel does not patch part of an existing glyph in the terminal. It changes one bit in the application's mask and causes one complete PUA glyph to replace the previous character at that cursor position. All 16 visible logical pixels in that cell are therefore reconstructed from the new mask every time the cell is emitted.",
        62,
        151,
        W - 124,
        10.5,
        16,
        INK,
    )
    pdf.showPage()


def page7(pdf, page_number=7):
    page_title(
        pdf,
        "Building programmatic visualizations",
        "Drawing algorithms operate in the 4C x 4R virtual coordinate space and call the same plot operation for every covered position.",
        page_number,
    )

    box(pdf, 42, 410, 610, 310, "A diagonal crossing six character cells")
    points = []
    x0, y0, x1, y1 = 0, 1, 23, 6
    dx, dy = x1 - x0, y1 - y0
    for x in range(x0, x1 + 1):
        y = round(y0 + dy * (x - x0) / dx)
        points.append((x, y))
    virtual_grid(pdf, 70, 458, 6, 2, 21, points)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(70, 435, "24 x 8 virtual positions encoded by only 6 x 2 terminal characters")

    box(pdf, 690, 410, W - 732, 310, "Primitive-to-pixel pipeline")
    primitives = [
        ("Line", "Bresenham or DDA -> plot each point"),
        ("Circle", "midpoint circle -> symmetric points"),
        ("Polygon", "edge rasterization + scanline fill"),
        ("Sprite", "OR to add, AND NOT to erase, XOR to toggle"),
        ("3D wireframe", "project vertices -> line segments"),
        ("Chart", "map samples -> virtual x/y coordinates"),
    ]
    y = 667
    for heading, detail in primitives:
        pdf.setFillColor(P0)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(715, y, heading)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(835, y, detail)
        y -= 39

    box(pdf, 42, 215, W - 84, 145, "Why this is more flexible than ordinary terminal characters")
    benefits = [
        "Coordinates are mathematical and independent of language or text semantics.",
        "Every 4 x 4 combination exists, so adjacent pixels combine without approximation.",
        "Cell masks can be composited, diffed, animated and regenerated deterministically.",
        "Existing terminal cursor addressing, UTF-8 transport and ANSI color remain usable.",
        "The same rendering core can support charts, vector art, games, particles and telemetry.",
    ]
    y = 316
    for index, benefit in enumerate(benefits):
        column = index % 2
        row = index // 2
        bx = 66 + column * 555
        by = y - row * 39
        pdf.setFillColor(P1 if column else P0)
        pdf.circle(bx, by + 3, 2.5, stroke=0, fill=1)
        paragraph(pdf, benefit, bx + 12, by, 515, 9.5, 14, INK)

    box(pdf, 42, 87, W - 84, 92, "Animation strategy", fill=colors.HexColor("#F7F9FB"))
    paragraph(
        pdf,
        "Maintain a back buffer for the next frame, compare it with the displayed front buffer, emit only changed glyph cells, then swap buffers. A one-virtual-pixel movement may change one cell or two neighboring cells at a character boundary; the same diff process handles both cases without special terminal logic.",
        62,
        143,
        W - 124,
        10,
        15,
        MUTED,
    )
    pdf.showPage()


def page8(pdf, page_number=8):
    page_title(
        pdf,
        "Operational requirements, limits and review checklist",
        "The font extends terminal graphics capability but does not change the terminal protocol or remove renderer constraints.",
        page_number,
    )

    left_items = [
        ("Both font parts", "The terminal fallback chain must select PUA 4x4 Part 0 and Part 1 for their respective codepoint ranges."),
        ("One-column width", "Supplementary-PUA codepoints must be treated as wcwidth 1 by the locale, terminal and shaping stack."),
        ("UTF-8 and cmap 12", "The output path must preserve supplementary-plane Unicode and the fonts require a format-12 character map."),
        ("Shadow state", "The application must retain cell masks; terminal screen read-back is neither portable nor sufficient."),
        ("Resize handling", "A resize changes C, R, virtual dimensions and buffer allocation. Rebuild or remap the graphical state."),
    ]
    right_items = [
        ("Pixel aspect ratio", "The nominal 125 x 250 font-unit subcells are rectangular in a conventional terminal cell."),
        ("Color granularity", "ANSI foreground color normally applies to the whole glyph cell, not independently to its 16 logical pixels."),
        ("Update granularity", "One bit change replaces one complete character. Dirty-cell output minimizes the resulting terminal traffic."),
        ("Private mapping", "These codepoints are a published project convention, not characters standardized by the Unicode Consortium."),
        ("Renderer rasterization", "Fractional device-pixel font sizes may introduce antialiasing variation even when logical geometry is exact."),
    ]

    for x, heading, items, accent in (
        (42, "Required for correct operation", left_items, P0),
        (620, "Constraints to design around", right_items, P1),
    ):
        box(pdf, x, 315, 530, 405, heading)
        y = 665
        for item_heading, detail in items:
            pdf.setFillColor(accent)
            pdf.setFont("Helvetica-Bold", 10.5)
            pdf.drawString(x + 20, y, item_heading)
            y = paragraph(pdf, detail, x + 20, y - 17, 490, 9, 13, MUTED)
            y -= 14

    box(pdf, 42, 120, W - 84, 145, "Decisions incorporated in this complete specification", fill=colors.HexColor("#FFF6E9"), stroke=ORANGE)
    checklist = [
        "Added a terminology section separating Unicode, codepoint, character, text, font, glyph, UTF-8 and terminal cell.",
        "Added a dedicated diagram connecting zero-based graphical coordinates with one-based ANSI cursor positions.",
        "Added all three PUA ranges, capacity limits, P0/P1 boundary examples and the significance of bit 15.",
        "Added truth tables, binary calculations and practical guidance for OR, AND NOT, XOR and AND.",
        "Added the full executable standard-library reference renderer in Appendix C.",
        "The exhaustive 259-page character specification and 256-page mask catalog are appended unchanged after this section.",
    ]
    y = 226
    for index, item in enumerate(checklist):
        column = index % 2
        row = index // 2
        x = 64 + column * 560
        line_y = y - row * 35
        pdf.setFillColor(GREEN if index < 5 else colors.white)
        pdf.setStrokeColor(GREEN if index < 5 else ORANGE)
        pdf.rect(x, line_y - 2, 9, 9, stroke=1, fill=1)
        if index < 5:
            pdf.setFillColor(colors.white)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(x + 1.5, line_y - 1, "x")
        paragraph(pdf, item, x + 16, line_y, 520, 8.8, 12, INK)

    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(W / 2, 72, "End of mapping guide - the exhaustive 65,536-glyph catalog follows")
    pdf.showPage()


def page_keypress(pdf, page_number):
    page_title(
        pdf,
        "Appendix A - from a keypress to a rendered glyph in a terminal cell",
        "A key does not directly select a font glyph. Input first reaches a program; only the program's output is decoded and rendered by the terminal.",
        page_number,
    )

    stages = [
        ("1. Keyboard", "physical A key", P0),
        ("2. OS input", "key event + modifiers", P0),
        ("3. Terminal input", "encodes byte 41", P0),
        ("4. PTY", "delivers bytes to process", P0),
        ("5. Application", "shell/editor/game decides", GREEN),
        ("6. Output", "writes UTF-8 bytes", P1),
        ("7. Decoder", "bytes -> codepoint", P1),
        ("8. Cell model", "cursor + attributes", P1),
        ("9. Font fallback", "choose supporting face", P1),
        ("10. cmap", "codepoint -> glyph ID", P1),
        ("11. Rasterizer", "outline -> device pixels", ORANGE),
        ("12. Compositor", "glyph appears on screen", ORANGE),
    ]
    stage_w = 170
    stage_h = 78
    gap = 18
    start_x = 47
    for index, (heading, detail, accent) in enumerate(stages):
        row = index // 6
        column = index % 6
        display_column = column if row == 0 else 5 - column
        x = start_x + display_column * (stage_w + gap)
        y = 565 - row * 150
        box(pdf, x, y, stage_w, stage_h, fill=colors.white, stroke=accent)
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawCentredString(x + stage_w / 2, y + 50, heading)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7.6)
        pdf.drawCentredString(x + stage_w / 2, y + 27, detail)
        if row == 0 and column < 5:
            arrow(pdf, x + stage_w, y + stage_h / 2, x + stage_w + gap - 3, y + stage_h / 2, accent)
        elif row == 1 and column < 5:
            arrow(pdf, x, y + stage_h / 2, x - gap + 3, y + stage_h / 2, accent)
    last_stage_x = start_x + 5 * (stage_w + gap) + stage_w / 2
    arrow(pdf, last_stage_x, 565, last_stage_x, 493, P1)

    pdf.setFillColor(P0)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, 675, "INPUT PATH")
    pdf.setFillColor(P1)
    pdf.drawString(990, 675, "OUTPUT/RENDER PATH")

    box(pdf, 42, 238, W - 84, 125, "Normal text example: pressing A")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 9.5)
    pdf.drawString(66, 319, "keypress A -> input byte 41 -> shell/readline receives it -> echo output byte 41 -> U+0041 -> text font -> glyph A")
    paragraph(
        pdf,
        "If echo is disabled, the key can be received without anything appearing. If an application transforms the input, the displayed output may be different from the key. This is why input and rendering are separate paths.",
        66,
        282,
        W - 132,
        9.2,
        14,
        MUTED,
    )

    box(pdf, 42, 88, W - 84, 105, "PUA 4x4 example: the application renders mask 0x9669", fill=colors.HexColor("#F3ECF9"), stroke=P1)
    pdf.setFillColor(P1)
    pdf.setFont("Courier-Bold", 9.2)
    pdf.drawString(66, 151, "mask 9669 -> codepoint U+101669 -> UTF-8 F4 81 99 A9 -> terminal decoder -> Part 1 cmap -> 4x4 glyph")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.8)
    pdf.drawString(66, 118, "No keyboard key is assigned to U+101669. Graphics software computes and outputs it directly as part of the frame.")
    pdf.showPage()


def page_reference_intro(pdf, page_number):
    page_title(
        pdf,
        "Appendix B - executable reference renderer",
        "The following three listing pages are a complete standard-library Python program, not pseudocode or an excerpt.",
        page_number,
    )

    box(pdf, 42, 500, 540, 225, "What the renderer demonstrates")
    items = [
        "A C x R array of unsigned 16-bit masks acts as the framebuffer.",
        "divmod maps each virtual (x,y) to a terminal cell and local bit.",
        "OR, AND NOT and XOR implement set, clear and toggle.",
        "Bresenham draws lines in the 4C x 4R virtual coordinate space.",
        "mask_to_codepoint selects P0 or P1 deterministically.",
        "ANSI CUP positions each row and UTF-8 carries supplementary PUA codepoints.",
    ]
    y = 672
    for item in items:
        pdf.setFillColor(P0)
        pdf.circle(64, y + 3, 2.3, stroke=0, fill=1)
        y = paragraph(pdf, item, 76, y, 480, 9.3, 18, INK)

    box(pdf, 620, 500, W - 662, 225, "Run it")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 9.5)
    commands = [
        "# Linux installation used by this project:",
        "cd \"$HOME/dev/FontMaker/pua4x4\"",
        "test -f pua4x4_reference_renderer.py || exit 1",
        "./launch-linux.sh shell",
        "",
        "# Then, inside the PUA 4x4 terminal:",
        "cd \"$HOME/dev/FontMaker/pua4x4\"",
        "python3 pua4x4_reference_renderer.py \\",
        "  --columns 40 --rows 12 --seconds 2 --fps 12",
    ]
    y = 680
    for line in commands:
        pdf.drawString(645, y, line)
        y -= 18
    paragraph(
        pdf,
        "The first command block matches the verified Linux deployment path. The Git repository layout may instead use experiments/pua-4x4. In either layout, run the program only in a terminal profile selecting the PUA 4x4 Fontconfig alias. Ctrl-C exits an unbounded run.",
        645,
        526,
        W - 710,
        8.0,
        11,
        MUTED,
    )

    box(pdf, 42, 255, W - 84, 195, "Renderer architecture")
    stages = [
        ("draw_demo", "virtual primitives"),
        ("Canvas.plot", "coordinate mapping"),
        ("16-bit masks", "framebuffer state"),
        ("mask_to_codepoint", "P0/P1 selection"),
        ("ansi_frame", "cursor + Unicode"),
        ("terminal", "font + rasterizer"),
    ]
    stage_w = 165
    gap = 25
    start_x = 66
    for index, (heading, detail) in enumerate(stages):
        x = start_x + index * (stage_w + gap)
        box(pdf, x, 303, stage_w, 88, fill=colors.white, stroke=P0 if index < 3 else P1)
        pdf.setFillColor(P0 if index < 3 else P1)
        pdf.setFont("Helvetica-Bold", 8.7)
        pdf.drawCentredString(x + stage_w / 2, 359, heading)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawCentredString(x + stage_w / 2, 330, detail)
        if index < len(stages) - 1:
            arrow(pdf, x + stage_w, 347, x + stage_w + gap - 3, 347)

    box(pdf, 42, 88, W - 84, 115, "Scope and production considerations", fill=colors.HexColor("#FFF6E9"), stroke=ORANGE)
    paragraph(
        pdf,
        "This reference deliberately redraws every cell so the mapping remains easy to audit. A production renderer should retain front and back buffers, emit only dirty cells, coalesce adjacent updates, handle resize events, measure the terminal pixel aspect ratio and apply frame pacing based on actual output throughput.",
        64,
        161,
        W - 128,
        9.5,
        14,
        INK,
    )
    pdf.showPage()


def page_reference_code(pdf, page_number, lines, start_line, end_line, part, total_parts):
    page_title(
        pdf,
        f"Appendix C - complete reference renderer source ({part}/{total_parts})",
        f"pua4x4_reference_renderer.py - lines {start_line}-{end_line}; reproduce the file by concatenating these listing pages in order.",
        page_number,
    )
    box(pdf, 42, 48, W - 84, 675, fill=colors.HexColor("#111A22"), stroke=INK)
    y = 700
    for line_number, line in enumerate(lines, start=start_line):
        pdf.setFillColor(colors.HexColor("#7890A3"))
        pdf.setFont("Courier", 8)
        pdf.drawRightString(76, y, str(line_number))
        pdf.setFillColor(colors.HexColor("#D7E7F3"))
        pdf.drawString(88, y, line.expandtabs(4))
        y -= 12.5
    pdf.showPage()


def generate(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=PAGE_SIZE, pageCompression=1)
    pdf.setTitle("PUA 4x4 Mapping Specification - Version 0.8")
    pdf.setAuthor("square-braille-font project")
    pdf.setSubject("Unicode PUA capacity, terminal-to-virtual-pixel mapping, Boolean operations and executable reference renderer")
    pdf.setKeywords("PUA, Unicode, 4x4, terminal graphics, mapping, bitmask, glyph, ANSI, renderer")

    ordered_pages = (
        page1,
        page_terms,
        page2,
        page3,
        page_pua,
        page4,
        page_coordinates,
        page_logic,
        page5,
        page6,
        page7,
        page8,
        page_keypress,
        page_reference_intro,
    )
    for page_number, page in enumerate(ordered_pages, start=1):
        page(pdf, page_number)

    renderer_path = Path(__file__).parent / "pua4x4_reference_renderer.py"
    renderer_lines = renderer_path.read_text(encoding="utf-8").splitlines()
    lines_per_page = 48
    chunks = [
        renderer_lines[index:index + lines_per_page]
        for index in range(0, len(renderer_lines), lines_per_page)
    ]
    assert len(chunks) == 3, len(chunks)
    for part, lines in enumerate(chunks, start=1):
        start_line = (part - 1) * lines_per_page + 1
        end_line = start_line + len(lines) - 1
        page_reference_code(
            pdf,
            len(ordered_pages) + part,
            lines,
            start_line,
            end_line,
            part,
            len(chunks),
        )
    pdf.save()
    print(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "output/pdf/PUA-4x4-Mapping-Specification-v0.8.pdf",
    )
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
