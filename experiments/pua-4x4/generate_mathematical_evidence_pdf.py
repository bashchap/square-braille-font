#!/usr/bin/env python3
"""Generate the mathematics-only PUA 4x4 evidentiary proof document."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#10233f")
BLUE = colors.HexColor("#1e64c8")
CYAN = colors.HexColor("#18a7b5")
GREEN = colors.HexColor("#248a55")
LIGHT_GREEN = colors.HexColor("#e8f5ed")
RED = colors.HexColor("#b42318")
LIGHT_RED = colors.HexColor("#fff0ee")
AMBER = colors.HexColor("#a15c00")
LIGHT_AMBER = colors.HexColor("#fff5df")
INK = colors.HexColor("#19202a")
MUTED = colors.HexColor("#52606d")
GRID = colors.HexColor("#b8c2cc")
PALE = colors.HexColor("#f3f6f9")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class NumberedCanvasMixin:
    pass


class BitGrid(Flowable):
    def __init__(self, width=150 * mm, cell=22 * mm, highlight=None):
        super().__init__()
        self.width = width
        self.cell = cell
        self.height = 4 * cell + 22 * mm
        self.highlight = highlight

    def draw(self):
        c = self.canv
        ox = (self.width - 4 * self.cell) / 2
        oy = 8 * mm
        palette = [
            colors.HexColor("#dceafe"),
            colors.HexColor("#d9f3ef"),
            colors.HexColor("#fff0cf"),
            colors.HexColor("#f6dfec"),
        ]
        for y in range(4):
            for x in range(4):
                bit = 4 * y + (3 - x)
                selected = (
                    self.highlight == (x, y)
                    or isinstance(self.highlight, set)
                    and (x, y) in self.highlight
                )
                c.setFillColor(colors.HexColor("#b8e3c9") if selected else palette[y])
                c.setStrokeColor(GREEN if selected else GRID)
                c.setLineWidth(2 if selected else 0.8)
                c.rect(ox + x * self.cell, oy + (3 - y) * self.cell,
                       self.cell, self.cell, fill=1, stroke=1)
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 13)
                c.drawCentredString(
                    ox + (x + 0.5) * self.cell,
                    oy + (3 - y + 0.56) * self.cell,
                    f"bit {bit}",
                )
                c.setFont("Courier", 8)
                c.setFillColor(MUTED)
                c.drawCentredString(
                    ox + (x + 0.5) * self.cell,
                    oy + (3 - y + 0.28) * self.cell,
                    f"value 0x{1 << bit:04X}",
                )
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(ox, oy + 4 * self.cell + 5 * mm, "local x:  0                 1                 2                 3")
        c.saveState()
        c.translate(ox - 7 * mm, oy)
        c.rotate(90)
        c.drawString(0, 0, "local y: 3                 2                 1                 0")
        c.restoreState()


class CoordinateZoom(Flowable):
    def __init__(self, width=165 * mm):
        super().__init__()
        self.width = width
        self.height = 78 * mm

    def draw(self):
        c = self.canv
        left_x, bottom_y = 5 * mm, 14 * mm
        cw, ch = 15 * mm, 12 * mm
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(NAVY)
        c.drawString(left_x, bottom_y + 4 * ch + 7 * mm, "Terminal cells (application coordinates, zero-based)")
        for row in range(4):
            for col in range(6):
                selected = (col, row) == (3, 2)
                c.setFillColor(colors.HexColor("#dff4ff") if selected else colors.white)
                c.setStrokeColor(BLUE if selected else GRID)
                c.setLineWidth(2 if selected else 0.6)
                y = bottom_y + (3 - row) * ch
                c.rect(left_x + col * cw, y, cw, ch, fill=1, stroke=1)
                c.setFillColor(INK)
                c.setFont("Courier-Bold" if selected else "Courier", 7.5)
                c.drawCentredString(left_x + (col + 0.5) * cw, y + 5 * mm, f"({col},{row})")
        c.setFillColor(BLUE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(left_x + 3 * cw, bottom_y - 5 * mm, "ANSI cursor: column 4, row 3")

        arrow_x = left_x + 6 * cw + 5 * mm
        c.setStrokeColor(CYAN)
        c.setFillColor(CYAN)
        c.setLineWidth(2)
        c.line(arrow_x, bottom_y + 2 * ch, arrow_x + 15 * mm, bottom_y + 2 * ch)
        c.line(arrow_x + 15 * mm, bottom_y + 2 * ch,
               arrow_x + 11 * mm, bottom_y + 2 * ch + 3 * mm)
        c.line(arrow_x + 15 * mm, bottom_y + 2 * ch,
               arrow_x + 11 * mm, bottom_y + 2 * ch - 3 * mm)

        zx = arrow_x + 20 * mm
        zcell = 11 * mm
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(zx, bottom_y + 4 * zcell + 7 * mm, "One selected terminal cell")
        for y in range(4):
            for x in range(4):
                bit = 4 * y + (3 - x)
                selected = (x, y) == (1, 2)
                c.setFillColor(LIGHT_AMBER if selected else PALE)
                c.setStrokeColor(AMBER if selected else GRID)
                c.setLineWidth(2 if selected else 0.6)
                py = bottom_y + (3 - y) * zcell
                c.rect(zx + x * zcell, py, zcell, zcell, fill=1, stroke=1)
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 8)
                c.drawCentredString(zx + (x + 0.5) * zcell, py + 4.5 * mm, str(bit))
        c.setFillColor(AMBER)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(zx, bottom_y - 5 * mm, "virtual (13,10) -> local (1,2) -> bit 10")


class RoundTripDiagram(Flowable):
    def __init__(self, width=170 * mm):
        super().__init__()
        self.width = width
        self.height = 52 * mm

    def draw(self):
        c = self.canv
        labels = [
            "virtual\n(vx,vy)",
            "cell + local\n(cx,cy,lx,ly)",
            "bit b\nvalue 1<<b",
            "mask M",
            "P0/P1\ncodepoint",
        ]
        box_w, box_h, gap = 28 * mm, 18 * mm, 5 * mm
        total = len(labels) * box_w + (len(labels) - 1) * gap
        x0 = (self.width - total) / 2
        y0 = 24 * mm
        for index, label in enumerate(labels):
            x = x0 + index * (box_w + gap)
            c.setFillColor(colors.HexColor("#eaf2ff") if index < 4 else LIGHT_GREEN)
            c.setStrokeColor(BLUE if index < 4 else GREEN)
            c.setLineWidth(1.2)
            c.roundRect(x, y0, box_w, box_h, 2 * mm, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8)
            for line_index, line in enumerate(label.split("\n")):
                c.drawCentredString(x + box_w / 2, y0 + 11 * mm - line_index * 4 * mm, line)
            if index < len(labels) - 1:
                ax = x + box_w
                c.setStrokeColor(CYAN)
                c.setFillColor(CYAN)
                c.line(ax + 1 * mm, y0 + box_h / 2, ax + gap - 1 * mm, y0 + box_h / 2)
                c.line(ax + gap - 1 * mm, y0 + box_h / 2,
                       ax + gap - 3 * mm, y0 + box_h / 2 + 2 * mm)
                c.line(ax + gap - 1 * mm, y0 + box_h / 2,
                       ax + gap - 3 * mm, y0 + box_h / 2 - 2 * mm)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(self.width / 2, 14 * mm, "Forward translation")
        c.setStrokeColor(AMBER)
        c.setLineWidth(1.5)
        c.line(x0 + total, 10 * mm, x0, 10 * mm)
        c.line(x0, 10 * mm, x0 + 3 * mm, 12 * mm)
        c.line(x0, 10 * mm, x0 + 3 * mm, 8 * mm)
        c.setFillColor(AMBER)
        c.drawCentredString(self.width / 2, 4 * mm, "Inverse translation must return the identical virtual coordinate")


class ExpectedTriangle(Flowable):
    def __init__(self, width=155 * mm):
        super().__init__()
        self.width = width
        self.height = 74 * mm

    def draw(self):
        c = self.canv
        x0, y0 = 36 * mm, 7 * mm
        w, h = 86 * mm, 60 * mm
        c.setFillColor(colors.HexColor("#d9f3ef"))
        path = c.beginPath()
        path.moveTo(x0 + w / 2, y0 + h)
        path.lineTo(x0, y0)
        path.lineTo(x0 + w, y0)
        path.close()
        c.drawPath(path, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#9db8bd"))
        c.setLineWidth(0.25)
        for x in range(0, 46):
            px = x0 + x * w / 45
            c.line(px, y0, px, y0 + h)
        for y in range(0, 31):
            py = y0 + y * h / 30
            c.line(x0, py, x0 + w, py)
        c.setStrokeColor(GREEN)
        c.setLineWidth(2)
        c.line(x0 + w / 2, y0 + h, x0, y0)
        c.line(x0 + w / 2, y0 + h, x0 + w, y0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(2 * mm, y0 + 49 * mm, "Expected:")
        c.setFont("Helvetica", 8)
        c.drawString(2 * mm, y0 + 43 * mm, "one connected")
        c.drawString(2 * mm, y0 + 39 * mm, "filled set")
        c.drawString(2 * mm, y0 + 35 * mm, "with no detached")
        c.drawString(2 * mm, y0 + 31 * mm, "edge pixels")


def make_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=25, leading=29, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=6 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=12, leading=17, textColor=MUTED, spaceAfter=5 * mm,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=NAVY, spaceAfter=5 * mm,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=BLUE, spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.2, leading=13, textColor=INK, spaceAfter=2.5 * mm,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.4, leading=10, textColor=MUTED,
        ),
        "hash": ParagraphStyle(
            "Hash", parent=base["BodyText"], fontName="Courier",
            fontSize=6.2, leading=7.2, textColor=INK,
        ),
        "mono": ParagraphStyle(
            "Mono", parent=base["Code"], fontName="Courier",
            fontSize=8.2, leading=11, textColor=INK, backColor=PALE,
            borderColor=GRID, borderWidth=0.5, borderPadding=3 * mm,
            spaceAfter=3 * mm,
        ),
        "pass": ParagraphStyle(
            "Pass", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=10, leading=14, textColor=GREEN, backColor=LIGHT_GREEN,
            borderColor=GREEN, borderWidth=0.8, borderPadding=3 * mm,
            spaceAfter=3 * mm,
        ),
        "fail": ParagraphStyle(
            "Fail", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=10, leading=14, textColor=RED, backColor=LIGHT_RED,
            borderColor=RED, borderWidth=0.8, borderPadding=3 * mm,
            spaceAfter=3 * mm,
        ),
        "note": ParagraphStyle(
            "Note", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.8, leading=12, textColor=INK, backColor=LIGHT_AMBER,
            borderColor=AMBER, borderWidth=0.6, borderPadding=3 * mm,
            spaceAfter=3 * mm,
        ),
    }
    return styles


def p(text, style):
    return Paragraph(text, style)


def formula(text, styles):
    return p(text.replace("\n", "<br/>"), styles["mono"])


def status_table(rows, widths):
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LEADING", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))
    return table


def scaled_image(path: Path, max_width: float, max_height: float):
    with PILImage.open(path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def page_header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#d9e0e7"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, height - 10 * mm, "PUA 4x4 mathematical mapping evidence - review gate")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_story(report, json_path, csv_path, full_image, detail_image, styles):
    story = []
    body, h1, h2 = styles["body"], styles["h1"], styles["h2"]

    def hash_cell(path):
        digest = sha256(path)
        return p(f"{digest[:32]}<br/>{digest[32:]}", styles["hash"])

    story += [
        Spacer(1, 13 * mm),
        p("PUA 4x4 Mathematical Mapping", styles["title"]),
        p("Evidentiary proof of coordinates, bit positions, masks and P0/P1 codepoints", styles["subtitle"]),
        Spacer(1, 4 * mm),
        p("MATHEMATICS GATE: PASS", styles["pass"]),
        p("OBSERVED TERMINAL OUTPUT: FAIL - NOT WAIVED", styles["fail"]),
        p(
            "This document proves only the agreed mathematics and its implementation in the current encoder functions. "
            "It does <b>not</b> certify the generated font, font fallback, terminal shaping, fixed-cell placement, "
            "antialiasing or repaint behaviour. The supplied triangle image remains rejected visual evidence.",
            body,
        ),
        Spacer(1, 8 * mm),
        status_table([
            ["Gate", "Expected", "Measured result", "Status"],
            ["Coordinate mathematics", "Exact reversible mapping", "30,720/30,720 virtual coordinates", "PASS"],
            ["Mask/codepoint bijection", "65,536 unique reversible values", "65,536 unique; 32,768 per part", "PASS"],
            ["Project mapping code", "Match independent oracle", "65,536/65,536 masks", "PASS"],
            ["Triangle mask pipeline", "No missing or additional virtual pixels", "10,860 pixels; 0 missing; 0 additional", "PASS"],
            ["Observed Linux rendering", "Connected edge; no cell grid", "Detached edge marks and visible seams", "FAIL"],
        ], [35 * mm, 48 * mm, 58 * mm, 24 * mm]),
        Spacer(1, 8 * mm),
        p("Decision rule", h2),
        p("No further production-font generation is authorized by this document. Mathematics approval is a prerequisite, not a substitute, for later font and runtime evidence.", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("1. Terms and coordinate systems", h1),
        p("A <b>terminal cell</b> is one addressable text position. Application coordinates use zero-based column <b>cx</b> and row <b>cy</b>. ANSI cursor escape sequences use one-based column and row numbers.", body),
        p("A <b>virtual pixel</b> is one of sixteen independently selected positions inside a terminal cell. Its global zero-based coordinate is <b>(vx, vy)</b>. Its local coordinate inside one cell is <b>(lx, ly)</b>, where both values are 0 through 3.", body),
        CoordinateZoom(),
        p("Coordinate conventions", h2),
        status_table([
            ["Space", "Origin", "Horizontal direction", "Vertical direction", "Range/example"],
            ["Virtual canvas", "top-left", "vx increases right", "vy increases down", "80x24 terminal -> 320x96"],
            ["Application terminal cells", "top-left", "cx increases right", "cy increases down", "cell (3,2)"],
            ["ANSI cursor", "top-left", "column increases right", "row increases down", "column 4, row 3"],
            ["Local 4x4 grid", "cell top-left", "lx increases right", "ly increases down", "local (1,2)"],
            ["Bit number", "MSB-left per row", "decreases left-to-right", "adds 4 per row", "bit 10"],
        ], [33 * mm, 27 * mm, 38 * mm, 38 * mm, 31 * mm]),
        p("The phrase <b>fedcba9876543210</b> names bit positions from the numeric most-significant bit to the least-significant bit. It is not a hexadecimal number and is not a string placed directly in Unicode.", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("2. Authoritative 4x4 bit layout", h1),
        p("Every row is MSB-first. Consequently local x values 0,1,2,3 map to descending bit numbers within that row.", body),
        BitGrid(),
        formula("top row:       3  2  1  0\nsecond row:    7  6  5  4\nthird row:    11 10  9  8\nbottom row:   15 14 13 12\n\nMSB-to-LSB bit labels:  f e d c b a 9 8 7 6 5 4 3 2 1 0", styles),
        p("Authoritative formula", h2),
        formula("b = 4 * ly + (3 - lx)\nbit_value = 1 << b", styles),
        p("The subtraction <b>3 - lx</b> is essential. Omitting it would make bit 0 appear at the left, horizontally reflecting every four-pixel row.", styles["fail"]),
        PageBreak(),
    ]

    story += [
        p("3. Forward translation", h1),
        p("The forward path begins with one virtual pixel and ends with the Unicode codepoint whose glyph must represent the complete 16-bit cell mask.", body),
        RoundTripDiagram(),
        formula(
            "cx = vx // 4                 cy = vy // 4\n"
            "ANSI_column = cx + 1         ANSI_row = cy + 1\n"
            "lx = vx % 4                  ly = vy % 4\n"
            "b = 4 * ly + (3 - lx)\n"
            "v = 1 << b\n"
            "M = OR of every v set in the same terminal cell",
            styles,
        ),
        p("Integer division selects the containing terminal cell. Modulo selects the position inside that cell. The bit formula changes only the representation of that local position; it does not change the visual coordinate.", body),
        p("A cell mask is state", h2),
        p("One codepoint represents one complete cell state, not one drawing operation. Setting a virtual pixel ORs its bit value into the current mask. Clearing uses AND NOT. Toggling uses XOR. The resulting complete mask selects the replacement codepoint.", body),
        PageBreak(),
    ]

    worked = report["worked_example_v13_v10"]
    story += [
        p("4. Worked example: virtual pixel (13,10)", h1),
        p("The graphics origin is ANSI row 1, column 1. Virtual and application coordinates remain zero-based; only the cursor escape is one-based.", body),
        CoordinateZoom(),
        formula(
            "vx = 13, vy = 10\n"
            "cx = 13 // 4 = 3           cy = 10 // 4 = 2\n"
            "ANSI column = 3 + 1 = 4    ANSI row = 2 + 1 = 3\n"
            "lx = 13 % 4 = 1            ly = 10 % 4 = 2\n"
            "b = 4 * 2 + (3 - 1) = 10\n"
            "v = 1 << 10 = 1024 = 0x0400",
            styles,
        ),
        p("If this is the only selected position, the complete mask is 0x0400. Because 0x0400 is below 0x8000, it belongs to Part 0.", body),
        formula("codepoint = U+F0000 + 0x0400 = U+F0400", styles),
        p(f"Measured reverse result: codepoint {worked['codepoint_hex']} -> mask {worked['reverse_mask_hex']} -> virtual coordinate {tuple(worked['reverse_virtual'])}.", styles["pass"]),
        PageBreak(),
    ]

    multi = report["worked_example_corners_and_center"]
    story += [
        p("5. Multiple selected pixels form one mask", h1),
        p("This example selects all four corners and the four central positions. It demonstrates aggregation rather than a one-pixel-only codepoint.", body),
        BitGrid(highlight={
            (0, 0), (3, 0), (1, 1), (2, 1),
            (1, 2), (2, 2), (0, 3), (3, 3),
        }),
        formula(
            "selected bits = {15, 12, 10, 9, 6, 5, 3, 0}\n"
            "M = (1<<15) | (1<<12) | (1<<10) | (1<<9) |\n"
            "    (1<<6)  | (1<<5)  | (1<<3)  | (1<<0)\n"
            f"M = {multi['mask_hex']} = binary {multi['binary_msb_to_lsb']}\n"
            f"codepoint = {multi['codepoint_hex']}",
            styles,
        ),
        status_table([
            ["Local row", "Selected pattern", "Contributing bits", "Hex contribution"],
            ["0", "#..#", "3 and 0", "0x0009"],
            ["1", ".##.", "6 and 5", "0x0060"],
            ["2", ".##.", "10 and 9", "0x0600"],
            ["3", "#..#", "15 and 12", "0x9000"],
            ["OR total", "#..# / .##. / .##. / #..#", "all eight", "0x9669"],
        ], [28 * mm, 55 * mm, 45 * mm, 36 * mm]),
        PageBreak(),
    ]

    story += [
        p("6. P0/P1 codepoint mapping", h1),
        p("A 4x4 binary cell has 2^16 = 65,536 masks. Each supplementary Private Use Area range used here contains 32,768 assigned slots, so the mapping is split exactly at mask bit 15.", body),
        formula(
            "Part 0, 0x0000 <= M <= 0x7FFF:\n"
            "    cp = 0xF0000 + M\n\n"
            "Part 1, 0x8000 <= M <= 0xFFFF:\n"
            "    cp = 0x100000 + (M - 0x8000)",
            styles,
        ),
        status_table([
            ["Mask", "Part", "Calculation", "Codepoint", "Reverse mask"],
            ["0x0000", "P0", "0xF0000 + 0x0000", "U+0F0000", "0x0000"],
            ["0x0400", "P0", "0xF0000 + 0x0400", "U+0F0400", "0x0400"],
            ["0x7FFF", "P0", "0xF0000 + 0x7FFF", "U+0F7FFF", "0x7FFF"],
            ["0x8000", "P1", "0x100000 + 0", "U+100000", "0x8000"],
            ["0x9669", "P1", "0x100000 + 0x1669", "U+101669", "0x9669"],
            ["0xFFFF", "P1", "0x100000 + 0x7FFF", "U+107FFF", "0xFFFF"],
        ], [27 * mm, 17 * mm, 57 * mm, 35 * mm, 30 * mm]),
        p("The codepoint is an encoding address. It is not the mask itself in Part 1; the 0x8000 split offset must be removed before adding the P1 base.", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("7. Reverse translation", h1),
        p("The reverse proof starts from a P0 or P1 codepoint, reconstructs the complete mask, locates every set bit and then reconstructs local and global coordinates.", body),
        formula(
            "P0 reverse: M = cp - 0xF0000\n"
            "P1 reverse: M = 0x8000 + (cp - 0x100000)\n\n"
            "for each set bit b:\n"
            "    ly = b // 4\n"
            "    lx = 3 - (b % 4)\n"
            "    vx = 4 * cx + lx\n"
            "    vy = 4 * cy + ly",
            styles,
        ),
        RoundTripDiagram(),
        p("Round-trip identity", h2),
        formula(
            "inverse(forward(vx,vy)) = (vx,vy)\n"
            "mask(codepoint(M)) = M\n"
            "mask(local_pixels(M)) = M",
            styles,
        ),
        p("The terminal cell is required to recover a global virtual coordinate. A glyph codepoint contains the sixteen local on/off states, but it does not encode where that glyph was printed on the terminal.", styles["note"]),
        PageBreak(),
    ]

    one_bits = report["one_bit_records"]
    rows = [["local", "bit", "value/mask", "part", "codepoint", "reverse local"]]
    for record in one_bits:
        rows.append([
            f"({record['local_x']},{record['local_y']})",
            str(record["bit_position"]),
            record["mask_hex"],
            f"P{record['part']}",
            record["codepoint_hex"],
            f"({record['reverse_local_x']},{record['reverse_local_y']})",
        ])
    story += [
        p("8. All sixteen one-bit cases", h1),
        p("Every local coordinate was translated to one bit, one mask and one codepoint, then reversed to the original local coordinate.", body),
        status_table(rows, [24 * mm, 18 * mm, 30 * mm, 18 * mm, 40 * mm, 34 * mm]),
        Spacer(1, 4 * mm),
        p("Result: 16 of 16 cases returned the original local coordinate.", styles["pass"]),
        p("Part 1 first appears at bit 15 because its one-bit value is 0x8000. Bits 0 through 14 are all Part 0 masks.", body),
        PageBreak(),
    ]

    story += [
        p("9. Bitwise state manipulation", h1),
        p("The renderer stores a complete 16-bit mask for each terminal cell. Logical operations change exactly one selected bit while preserving all other bits.", body),
        status_table([
            ["Operation", "Formula", "Meaning", "Required invariant"],
            ["Set", "M' = M OR (1<<b)", "force bit b to 1", "all other bits unchanged"],
            ["Clear", "M' = M AND NOT (1<<b)", "force bit b to 0", "all other bits unchanged"],
            ["Toggle", "M' = M XOR (1<<b)", "invert bit b", "all other bits unchanged"],
        ], [25 * mm, 49 * mm, 43 * mm, 48 * mm]),
        formula(
            "example bit b = 10, value = 0x0400\n"
            "set:    0x0000 OR      0x0400 = 0x0400\n"
            "clear:  0x9669 AND NOT 0x0400 = 0x9269\n"
            "toggle: 0x9269 XOR     0x0400 = 0x9669",
            styles,
        ),
        p("The verifier tested set, clear and toggle for every one of 16 bits in every one of 65,536 masks. For each operation it also asserted that the other fifteen bits were unchanged.", body),
        p("3,145,728 Boolean assertions passed.", styles["pass"]),
        PageBreak(),
    ]

    counts = report["test_counts"]
    implementation = counts["project_implementation"]
    triangle = counts["triangle_mapping"]
    story += [
        p("10. Exhaustive evidence and independence", h1),
        p("The test program contains an independent oracle. It does not import the project mapping functions when calculating expected values. Only after the oracle passes are the project functions loaded and compared against it.", body),
        status_table([
            ["Test", "Population", "Expected", "Measured", "Status"],
            ["Local one-bit round trip", "16", "16 identities", str(counts["local_one_bit_round_trips"]), "PASS"],
            ["80x24 virtual canvas", "320x96", "30,720 identities", f"{counts['virtual_round_trips']:,}", "PASS"],
            ["Mask -> codepoint -> mask", "65,536", "all identities", f"{counts['all_masks_round_tripped']:,}", "PASS"],
            ["Unique Unicode addresses", "65,536", "no collisions", f"{counts['unique_codepoints']:,}", "PASS"],
            ["Part populations", "2 parts", "32,768 each", f"{counts['codepoints_per_part']:,} each", "PASS"],
            ["Project mapping comparison", "65,536 masks", "all match oracle", f"{implementation['complete_mask_cases']:,}", "PASS"],
            ["Boolean assertions", "all masks and bits", "all invariants", f"{counts['boolean_operation_assertions']:,}", "PASS"],
            ["Triangle encode/decode", f"{triangle['triangle_virtual_pixels']:,} pixels", "0 missing/additional", f"{triangle['missing_after_decode']} / {triangle['unexpected_after_decode']}", "PASS"],
        ], [38 * mm, 30 * mm, 37 * mm, 34 * mm, 23 * mm]),
        p("What this establishes", h2),
        p("For the agreed convention, the formulas are internally consistent, reversible and collision-free. The current Python mapping functions and triangle mask construction produce the same mathematical masks as the independent oracle.", styles["pass"]),
        p("What this does not establish", h2),
        p("It does not establish that a particular codepoint is connected to the correct stored outline, that the correct face is selected at runtime, or that the terminal paints that outline correctly inside its fixed cell.", styles["fail"]),
        PageBreak(),
    ]

    story += [
        p("11. Expected triangle result at the mathematics gate", h1),
        p("The triangle test builds one analytic set of virtual pixels, encodes those pixels into per-cell masks and independently decodes the masks back to virtual coordinates.", body),
        ExpectedTriangle(),
        status_table([
            ["Quantity", "Expected", "Measured"],
            ["Analytic triangle virtual pixels", "10,860", f"{triangle['triangle_virtual_pixels']:,}"],
            ["Nonempty terminal cells", "derived, not assumed", f"{triangle['nonempty_terminal_cells']:,}"],
            ["Missing after mask decode", "0", str(triangle["missing_after_decode"])],
            ["Unexpected after mask decode", "0", str(triangle["unexpected_after_decode"])],
        ], [60 * mm, 50 * mm, 50 * mm]),
        p("Mathematical outcome: the decoded virtual-pixel set is exactly equal to the original analytic set.", styles["pass"]),
        p("Therefore detached rendered marks are not accepted as part of the intended triangle. They arise after the tested mask/codepoint calculation stage or from an as-yet-unmodelled terminal presentation stage.", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("12. Real observed terminal outcome", h1),
        p("The following image is the user-supplied Linux result from 2026-08-08, using the dedicated PUA 4x4 profile and the triangle demonstration.", body),
        scaled_image(full_image, 158 * mm, 147 * mm),
        Spacer(1, 3 * mm),
        p("Observed result: visible horizontal and vertical cell boundaries and periodic detached/discontinuous marks along the left edge.", styles["fail"]),
        p(f"Source image SHA-256: <font name='Courier'>{sha256(full_image)}</font>", styles["small"]),
        PageBreak(),
        p("13. Magnified failure evidence", h1),
        scaled_image(detail_image, 150 * mm, 150 * mm),
        Spacer(1, 4 * mm),
        p("The magnified edge is visually inconsistent with the connected set proved by the mathematical triangle round trip. The image is therefore a failed end-to-end result even though the mathematics gate passes.", styles["fail"]),
        p(f"Detail image SHA-256: <font name='Courier'>{sha256(detail_image)}</font>", styles["small"]),
        p("No inference is made here about which later layer is responsible. Candidate causes to test only after mathematics approval include cmap-to-glyph association, outline orientation, fallback selection, shaping, cell metrics, antialiasing, clipping and repaint behaviour.", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("14. Evidence gates and stopping rule", h1),
        status_table([
            ["Gate", "Required evidence", "Current result", "May advance?"],
            ["A. Mathematical convention", "reviewed formulas and diagrams", "awaiting user approval", "NO"],
            ["B. Exhaustive arithmetic", "machine evidence for all masks", "PASS", "only after A"],
            ["C. Source implementation", "independent oracle comparison", "PASS", "only after A"],
            ["D. Font cmap", "every codepoint links to expected mask", "not accepted in this document", "NO"],
            ["E. Glyph outline", "each bit occupies expected physical quadrant", "not accepted in this document", "NO"],
            ["F. Runtime selection", "installed face proven for both parts", "not accepted in this document", "NO"],
            ["G. Terminal raster", "pixel capture equals expected bitmap", "FAIL", "NO"],
        ], [37 * mm, 61 * mm, 43 * mm, 25 * mm]),
        Spacer(1, 5 * mm),
        p("Stopping rule", h2),
        p("Font generation and font-level corrective work remain paused until Gate A is explicitly confirmed. Later gates must be evidenced independently and linked end-to-end; a pass at an earlier gate cannot override visible failure at a later gate.", styles["fail"]),
        p("Required approval question", h2),
        p("Is the authoritative layout, forward formula, P0/P1 mapping and inverse formula in this document exactly the intended mathematical convention?", styles["note"]),
        PageBreak(),
    ]

    story += [
        p("Appendix A. Reproduction and evidence files", h1),
        p("Run from the repository root:", body),
        formula(
            "cd experiments/pua-4x4\n"
            "python3 verify_mathematical_mapping.py",
            styles,
        ),
        p("Expected console summary", h2),
        formula(
            "PASS: authoritative 16-position MSB-left table\n"
            "PASS: 30,720 virtual-coordinate round trips\n"
            "PASS: 65,536 mask/codepoint/mask round trips\n"
            "PASS: 65,536 unique codepoints (32,768 per part)\n"
            "PASS: 3,145,728 OR/AND-NOT/XOR assertions\n"
            "PASS: project mapping functions match the independent oracle\n"
            "PASS: triangle masks decode to the same 10,860 virtual pixels\n"
            "FAIL (recorded, not waived): observed terminal triangle output",
            styles,
        ),
        status_table([
            ["Artifact", "Purpose", "SHA-256"],
            [json_path.name, "machine-readable complete proof", hash_cell(json_path)],
            [csv_path.name, "all sixteen one-bit cases", hash_cell(csv_path)],
            [full_image.name, "full observed failure", hash_cell(full_image)],
            [detail_image.name, "magnified observed failure", hash_cell(detail_image)],
        ], [50 * mm, 50 * mm, 66 * mm]),
        Spacer(1, 5 * mm),
        p("Document conclusion", h2),
        p("The agreed mathematics is exhaustively self-consistent and matches the current Python address/mask/codepoint implementation. The current terminal rendering is visibly wrong and remains an unresolved failed gate. Approval of this document authorizes only progression to font-level evidence, not acceptance of the existing font.", styles["note"]),
    ]
    return story


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=root / "output" / "audit" / "pua4x4-mathematics-proof-v1.0.json",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=root / "output" / "audit" / "pua4x4-one-bit-table-v1.0.csv",
    )
    parser.add_argument(
        "--observed-full",
        type=Path,
        default=root / "evidence" / "observed-triangle-2026-08-08-full.png",
    )
    parser.add_argument(
        "--observed-detail",
        type=Path,
        default=root / "evidence" / "observed-triangle-2026-08-08-detail.png",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "pdf" / "PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf",
    )
    args = parser.parse_args()
    for path in (args.json, args.csv, args.observed_full, args.observed_detail):
        if not path.is_file():
            parser.error(f"missing required evidence: {path}")

    report = json.loads(args.json.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(args.output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=19 * mm,
        bottomMargin=17 * mm,
        title="PUA 4x4 Mathematical Mapping Evidence v1.0",
        author="Square Braille Font Project",
        subject="Mathematics-only proof and observed terminal failure record",
    )
    doc.build(
        build_story(
            report, args.json, args.csv, args.observed_full,
            args.observed_detail, styles
        ),
        onFirstPage=page_header_footer,
        onLaterPages=page_header_footer,
    )
    print(args.output)
    print("sha256", sha256(args.output))


if __name__ == "__main__":
    main()
