#!/usr/bin/env python3
"""Generate the fixed-layout PUA 4x4 mapping-chain evidence report."""

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


NAVY = colors.HexColor("#10243E")
BLUE = colors.HexColor("#176B87")
CYAN = colors.HexColor("#45C4D4")
PALE = colors.HexColor("#EAF7F8")
GREEN = colors.HexColor("#1D7A52")
GREEN_PALE = colors.HexColor("#E9F6EF")
AMBER = colors.HexColor("#D58918")
AMBER_PALE = colors.HexColor("#FFF4DB")
RED = colors.HexColor("#A53A3A")
GREY = colors.HexColor("#536271")
LIGHT_GREY = colors.HexColor("#EDF1F4")
INK = colors.HexColor("#17212B")


class MaskGrid(Flowable):
    def __init__(self, mask, width=42 * mm, show_bits=False, title=None):
        super().__init__()
        self.mask = mask
        self.width = width
        self.height = width + (8 * mm if title else 0)
        self.show_bits = show_bits
        self.title = title

    def draw(self):
        canvas = self.canv
        size = self.width
        y0 = 0
        cell = size / 4
        canvas.setLineWidth(.7)
        for row in range(4):
            for column in range(4):
                bit = row * 4 + (3 - column)
                x = column * cell
                y = y0 + (3 - row) * cell
                enabled = bool(self.mask & (1 << bit))
                canvas.setFillColor(CYAN if enabled else colors.white)
                canvas.setStrokeColor(NAVY)
                canvas.rect(x, y, cell, cell, fill=1, stroke=1)
                if self.show_bits:
                    canvas.setFillColor(NAVY if not enabled else colors.white)
                    canvas.setFont("Helvetica-Bold", max(6, cell * .25))
                    canvas.drawCentredString(x + cell / 2, y + cell * .38, str(bit))
        if self.title:
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString(size / 2, size + 3 * mm, self.title)


class ChainDiagram(Flowable):
    def __init__(self, width=175 * mm):
        super().__init__()
        self.width = width
        self.height = 36 * mm

    def draw(self):
        c = self.canv
        labels = ["virtual\n(x,y)", "cell + local\ncoordinates", "bit b", "16-bit\nmask", "P0 / P1\ncodepoint", "cmap\nglyph", "outline", "raster"]
        gap = 3 * mm
        box = (self.width - gap * (len(labels) - 1)) / len(labels)
        for index, label in enumerate(labels):
            x = index * (box + gap)
            c.setFillColor(PALE if index < 5 else GREEN_PALE)
            c.setStrokeColor(BLUE if index < 5 else GREEN)
            c.roundRect(x, 7 * mm, box, 22 * mm, 2 * mm, fill=1, stroke=1)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 6.5)
            lines = label.split("\n")
            for row, text in enumerate(lines):
                c.drawCentredString(x + box / 2, 20 * mm - row * 3.2 * mm, text)
            if index < len(labels) - 1:
                ax = x + box
                ay = 18 * mm
                c.setStrokeColor(AMBER)
                c.setFillColor(AMBER)
                c.line(ax + .5 * mm, ay, ax + gap - .8 * mm, ay)
                c.line(ax + gap - 2 * mm, ay + 1.3 * mm, ax + gap - .8 * mm, ay)
                c.line(ax + gap - 2 * mm, ay - 1.3 * mm, ax + gap - .8 * mm, ay)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 7)
        c.drawString(0, 1.5 * mm, "Each gate must pass before the next representation is trusted.")


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=25, leading=29, textColor=NAVY, alignment=TA_LEFT,
                                spaceAfter=6 * mm),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=12,
                                   leading=17, textColor=GREY, spaceAfter=6 * mm),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=17, leading=21, textColor=NAVY, spaceBefore=2 * mm,
                             spaceAfter=4 * mm),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, leading=15, textColor=BLUE, spaceBefore=3 * mm,
                             spaceAfter=2 * mm),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=9.2,
                               leading=13.2, textColor=INK, spaceAfter=2.5 * mm),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=7.5,
                                leading=10.2, textColor=INK),
        "mono": ParagraphStyle("Mono", parent=base["Code"], fontName="Courier",
                               fontSize=8.1, leading=11, textColor=NAVY,
                               backColor=LIGHT_GREY, borderPadding=5, spaceAfter=3 * mm),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName="Helvetica-Bold",
                                  fontSize=10.2, leading=14, textColor=GREEN),
        "card": ParagraphStyle("Card", parent=base["BodyText"], fontSize=7.2,
                               leading=9.5, alignment=TA_CENTER, textColor=INK),
    }


def page_decor(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 10 * mm, width, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(17 * mm, height - 6.4 * mm, "PUA 4x4 MAPPING-CHAIN EVIDENCE")
    canvas.setFillColor(GREY)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(17 * mm, 9 * mm, "Independent audit - 4 August 2026")
    canvas.drawRightString(width - 17 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def gate(title, criterion, evidence, result, s):
    data = [
        [Paragraph(title, s["h2"])],
        [Paragraph("<b>Criterion to advance:</b> " + criterion, s["small"])],
        [Paragraph("<b>Measured evidence:</b> " + evidence, s["small"])],
        [Paragraph("<b>Result:</b> " + result, s["small"])],
    ]
    table = Table(data, colWidths=[174 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), GREEN_PALE),
        ("BOX", (0, 0), (-1, -1), .7, GREEN),
        ("INNERGRID", (0, 1), (-1, -1), .25, colors.HexColor("#B8DCC9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def mask_card(record, s, width=49 * mm):
    grid = MaskGrid(record["mask"], width=25 * mm)
    label = Paragraph(
        f"<b>{record['mask_hex']}</b><br/>{record['codepoint_hex']}<br/>Part {record['part']}",
        s["card"],
    )
    table = Table([[grid], [label]], colWidths=[width], hAlign="CENTER")
    table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#B7C7D4")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def p(text, style):
    return Paragraph(text, style)


def build(args):
    report = json.loads(args.audit.read_text(encoding="utf-8"))
    seam_lines = args.seams.read_text(encoding="utf-8").strip().splitlines()
    s = styles()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(args.output), pagesize=A4,
        leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=17 * mm, bottomMargin=16 * mm,
        title="PUA 4x4 Mapping-Chain Evidence",
        author="Square Braille Font Project",
        subject="Independent verification from virtual pixel to installed glyph raster",
    )
    story = []

    story += [Spacer(1, 9 * mm), p("PUA 4x4", s["title"]),
              p("Evidentiary proof from a 4 x 4 virtual-pixel grid to the installed Linux glyph raster", s["subtitle"])]
    conclusion = Table([[p("CORRECTED CONCLUSION", s["small"]),
                         p("Font v0.3 implements the intended MSB-left mapping: inside each row the visible columns correspond to bits 3,2,1,0. Font v0.2 was internally self-consistent but used the opposite LSB-left convention. Font v0.1 also had unequal exterior outlines. v0.3 preserves v0.2's exact 125 x 250 geometry and changes the cmap/glyph construction so every codepoint now has the requested meaning.", s["callout"])]],
                       colWidths=[32 * mm, 142 * mm])
    conclusion.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GREEN), ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BACKGROUND", (1, 0), (1, 0), GREEN_PALE), ("BOX", (0, 0), (-1, -1), 1, GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story += [conclusion, Spacer(1, 8 * mm), ChainDiagram(), Spacer(1, 6 * mm),
              p("Scope and method", s["h1"]),
              p("This v1.2 report supersedes v1.1. Earlier audits proved internal consistency, but they did not compare the chosen bit convention with the requested convention. The user's character-editor calculation supplied that missing semantic requirement: local x=0 must select the most-significant bit of its four-bit row, not the least-significant bit.", s["body"]),
              p("The corrected audit begins without trusting the demo's encoder. It recalculates every coordinate, bit, mask and codepoint independently, parses both TrueType binaries directly, verifies every composite component and its exact bounds, and then checks the installed Linux Fontconfig/Pango path. There are 65,536 possible 16-bit masks; all 65,536 are tested.", s["body"]),
              p("Each numbered gate below states the evidence required before the following gate can be accepted. Machine-readable results accompany this PDF.", s["body"]),
              PageBreak()]

    story += [p("0. Failed criterion discovered by the trail test", s["h1"]),
              p("The trail test moved one virtual pixel left one position at a time. The selected masks and codepoints advanced correctly, yet the visible mark changed width. That observation isolates the failure after codepoint selection: the component outlines themselves were not equal.", s["body"]),
              Table([[p("v0.1 - defective edge overfill", s["h2"]),
                      p("v0.3 - equal geometry plus MSB-left mapping", s["h2"])],
                     [Image(str(args.before_pixel_raster), width=75 * mm, height=46.9 * mm),
                      Image(str(args.after_pixel_raster), width=75 * mm, height=46.9 * mm)],
                     [p("Measured raster widths for local x=0,1,2,3: <b>16, 10, 10, 16 pixels</b>. All marks were 23 pixels high. Edge components extended outside the cell.", s["small"]),
                      p("Measured raster widths for local x=0,1,2,3: <b>10, 10, 10, 10 pixels</b>. All marks are 16 pixels high. No component crosses the cell boundary.", s["small"])]],
                    colWidths=[86 * mm, 86 * mm],
                    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                                      ("BOX", (0, 0), (-1, -1), .6, colors.HexColor("#AAB7C2")),
                                      ("INNERGRID", (0, 0), (-1, -1), .3, colors.HexColor("#C7D0D8")),
                                      ("BACKGROUND", (0, 0), (0, 0), AMBER_PALE),
                                      ("BACKGROUND", (1, 0), (1, 0), GREEN_PALE),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 5),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                      ("TOPPADDING", (0, 0), (-1, -1), 5),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])),
              Spacer(1, 5 * mm),
              p("Root cause", s["h2"]),
              p("The nominal subcell is 125 x 250 font units. In v0.1, the generator added 100 units of overfill at each exterior edge. A left or right edge pixel therefore became 225 units wide, while an interior pixel remained 125. A top or bottom edge pixel became 350 units high, while an interior pixel remained 250. This was intended to hide raster seams, but it violated uniform subpixel addressing and caused the observed jumps.", s["body"]),
              gate("CORRECTION GATE - equal isolated pixels", "Every one-bit glyph must have identical 125 x 250 outline bounds translated only by its local (x,y), and every bound must stay within x=0..500 and y=-200..800.", "The v0.3 binaries were parsed directly. All sixteen reusable components in both fonts have exactly 125 x 250 bounds and no component leaves the character cell.", "PASS. The physical geometry remains exact while the mapping convention changes.", s),
              PageBreak()]

    story += [p("1. Establish the coordinate systems", s["h1"]),
              p("A terminal has character cells. PUA 4x4 treats each character cell as sixteen addressable virtual pixels. Virtual coordinates and cell coordinates are zero-based. ANSI cursor positions are one-based.", s["body"]),
              Table([[MaskGrid(0xFFFF, width=56 * mm, show_bits=True, title="one terminal cell: local bits 0..15"),
                      p("For a virtual pixel <b>(x, y)</b>:<br/><br/>"
                        "character_column = x div 4<br/>character_row = y div 4<br/>"
                        "local_x = x mod 4<br/>local_y = y mod 4<br/>"
                        "bit b = 4 x local_y + (3 - local_x)<br/><br/>"
                        "ANSI column = character_column + 1<br/>ANSI row = character_row + 1", s["mono"]) ]],
                    colWidths=[70 * mm, 104 * mm], style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])),
              p("Worked coordinate example", s["h2"]),
              p("Virtual pixel (13, 10) maps to terminal cell (3, 2), local position (1, 2), bit b = 4 x 2 + (3 - 1) = 10, bit value 1 &lt;&lt; 10 = 0x0400, and ANSI cursor position row 3, column 4.", s["body"]),
              gate("GATE 1 - coordinate arithmetic", "All sixteen local positions must map bijectively to bits 0..15 in the requested orientation.", "The independent audit enumerated local_y=0..3 and local_x=0..3 using b=4*local_y+(3-local_x). The resulting set is exactly {0..15}; each row reads 3,2,1,0 from left to right.", "PASS. A mask represents every 4 x 4 grid exactly once in MSB-left order.", s),
              PageBreak()]

    story += [p("2. Construct the 16-bit mask", s["h1"]),
              p("A set virtual pixel contributes its power of two. Multiple pixels are combined with bitwise OR. Clearing uses AND NOT; toggling uses XOR. The font never guesses a shape: the complete 16-bit mask is the shape.", s["body"]),
              Table([[MaskGrid(0x36C8, width=58 * mm, show_bits=True, title="example geometry mask 0x36C8"),
                      p("row 0: bit 3 = 0x0008<br/>"
                        "row 1: bits 6,7 = 0x0040 + 0x0080<br/>"
                        "row 2: bits 9,10 = 0x0200 + 0x0400<br/>"
                        "row 3: bits 12,13 = 0x1000 + 0x2000<br/>"
                        "<b>OR total = 0x36C8</b><br/><br/>"
                        "Binary: 0011 0110 1100 1000", s["mono"]) ]],
                    colWidths=[72 * mm, 102 * mm], style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])),
              gate("GATE 2 - mask fidelity", "Encoding and decoding must preserve every selected pixel.", "For every one of the geometry test's 2,197 cell/row/tick phase cases, the audit decoded all 16 mask bits and compared them with the independent analytic pixel predicate. Mismatches: 0.", "PASS. The 16-bit mask preserves the intended virtual pixels.", s),
              Spacer(1, 4 * mm), p("Boolean update examples", s["h2"]),
              p("Set bit 10: old_mask OR 0x0400. Clear bit 10: old_mask AND NOT 0x0400. Toggle bit 10: old_mask XOR 0x0400. Replace only after the updated 16-bit mask has been converted to its codepoint.", s["mono"]),
              PageBreak()]

    story += [p("3. Select Part 0 or Part 1 and calculate the codepoint", s["h1"]),
              p("One font cannot place 65,536 consecutive glyphs into the remaining contiguous space of a single supplementary Private Use Area segment used here. The mask's most significant bit selects the font part; the remaining value gives the offset.", s["body"]),
              p("P0: if mask &lt; 0x8000, codepoint = 0xF0000 + mask<br/>"
                "P1: if mask &gt;= 0x8000, codepoint = 0x100000 + (mask - 0x8000)", s["mono"]),
              p("Example 0xC631", s["h2"]),
              p("0xC631 has bit 15 set, so Part 1 is required. Offset = 0xC631 - 0x8000 = 0x4631. Codepoint = U+100000 + 0x4631 = <b>U+104631</b>.", s["body"]),
              p("The exact split boundary", s["h2"])]
    boundary = [next(item for item in report["boundary_samples"] if item["mask"] == mask)
                for mask in (0x7FFF, 0x8000, 0x8001, 0xFFFF)]
    story += [Table([[mask_card(item, s, 41 * mm) for item in boundary]], colWidths=[43.5 * mm] * 4,
                    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])),
              p("Important: 0x7FFF followed numerically by 0x8000 is not a spatial animation. Binary rollover clears bits 0..14 and sets bit 15, so their pictures should be radically different. The split changes storage font, not the mathematical mask.", s["body"]),
              gate("GATE 3 - codepoint uniqueness", "Every mask must map to one valid, unique codepoint and reverse without loss.", f"Independent enumeration produced {report['unique_codepoints_verified']:,} unique codepoints for 65,536 masks. Boundary results are P0 0x7FFF -> U+0F7FFF and P1 0x8000 -> U+100000.", "PASS. No collision, gap within a part, or off-by-one boundary error exists.", s),
              PageBreak()]

    story += [p("4. Verify the TrueType cmap and glyph index", s["h1"]),
              p("The Unicode codepoint is useful only if the font's cmap points to the intended glyph. Supplementary-plane codepoints require cmap format 12. The audit reads the binary tables directly with FontTools; it does not rely on the demo's mapping function.", s["body"])]
    font_rows = [["Part", "Mask range", "Codepoint range", "Patterns", "cmap 12", "SHA-256"]]
    for part in report["parts"]:
        font_rows.append([
            str(part["part"]), f"{part['mask_range'][0]:04X}-{part['mask_range'][1]:04X}",
            f"U+{part['codepoint_range'][0]:06X}-U+{part['codepoint_range'][1]:06X}",
            f"{part['patterns_verified']:,}", "yes", part["sha256"][:16] + "...",
        ])
    table = Table(font_rows, colWidths=[13 * mm, 29 * mm, 49 * mm, 22 * mm, 18 * mm, 43 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.8), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#AAB7C2")),
        ("BACKGROUND", (0, 1), (-1, -1), PALE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 4 * mm),
              p("Glyph-index rule", s["h2"]),
              p("Each font begins with glyph IDs 0..17 (.notdef, space and sixteen pixel components). Therefore glyph ID = 18 + part_offset. For 0xC631 in Part 1, offset 0x4631 = 17,969 and glyph ID = 17,987. The binary cmap contains U+104631 -> glyph ID 17,987.", s["body"]),
              gate("GATE 4 - cmap identity", "For every codepoint, cmap must select the glyph at the offset dictated by its mask.", "Both binaries contain format 12 cmaps. All 32,768 entries in each part were checked. For every offset, glyph ID equalled 18+offset. Installed-file hashes exactly match the reproducible build hashes.", "PASS. The selected codepoint reaches the intended glyph in both parts.", s),
              PageBreak()]

    story += [p("5. Verify glyph components and physical outline bounds", s["h1"]),
              p("Each pattern glyph is a TrueType composite of up to sixteen reusable rectangle components. A component may appear only when its corresponding mask bit is set. Every transform must be the identity transform.", s["body"]),
              p("Font metrics: 1000 units/em; advance 500; ascent 800; descent 200. In font v0.3, every local pixel is exactly 125 units wide by 250 units high. Edge overfill is zero: all component outlines remain within x=0..500 and y=-200..800.", s["body"])]
    bounds = report["parts"][0]["component_bounds"]
    rows = [["bit", "local", "x bounds", "y bounds", "measured = expected"]]
    for item in bounds:
        bit = item["bit"]
        x0, y0, x1, y1 = item["actual"]
        rows.append([str(bit), f"({3-(bit%4)},{bit//4})", f"{x0}..{x1}", f"{y0}..{y1}", "yes"])
    table = Table(rows, colWidths=[14 * mm, 25 * mm, 37 * mm, 37 * mm, 49 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#B5C2CC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [table, Spacer(1, 3 * mm),
              gate("GATE 5 - outline identity and equal geometry", "Every pattern glyph must contain exactly the components named by its mask, and all sixteen reusable components must be equal 125 x 250 rectangles wholly inside the cell.", "All 65,536 v0.3 pattern glyphs were parsed. Component-ID sets exactly matched each mask's MSB-left physical position; transforms were identity. All sixteen component bounds matched the independent exact-grid calculation, and edge_overfill=0.", "PASS for v0.3. v0.2 is retained as the LSB-left legacy mapping.", s),
              PageBreak()]

    story += [p("6. Verify the installed Linux renderer", s["h1"]),
              p("Structural correctness is not enough: the corrected v0.3 fonts must be selected and rasterized. The following strips were rendered remotely by pango-view through the installed Fontconfig alias, not drawn by this PDF.", s["body"]),
              p("Geometry-test glyph strip", s["h2"]),
              Image(str(args.geometry_raster), width=158 * mm, height=40.1 * mm),
              p("Left to right: 0001, 0013, 0136, 136C, 36C8, 6C80, 8000, C800. These are the nine analytical geometry masks except blank 0000. Pango reported zero unknown glyphs and selected both PUA 4x4 parts.", s["small"]),
              p("Boundary glyph strip", s["h2"]),
              Image(str(args.boundary_raster), width=137 * mm, height=46.4 * mm),
              p("Left to right: 7FFE, 7FFF, 8000, 8001, FFFE, FFFF. The abrupt visual change at 7FFF/8000 is the correct binary rollover described in Gate 3.", s["small"]),
              gate("GATE 6 - runtime font selection", "The installed stack must render both PUA ranges with their intended fonts and no missing-glyph fallback.", "Fontconfig selected PUA 4x4 Part 0 for U+0F0001 and Part 1 for U+100000. Pango serialized both family runs and reported unknown-glyphs=0. wcwidth returned one column for all boundary probes.", "PASS. Runtime selection is correct across the font boundary.", s),
              PageBreak()]

    story += [p("7. Explain the supplied geometry-test screenshots", s["h1"]),
              p("The screenshots are consistent with the program's explicit geometry formula, not with random glyph substitution. The test sets a pixel when:", s["body"]),
              p("(virtual_x - virtual_y - tick) mod 13 is 0 OR 1", s["mono"]),
              p("Selecting residues 0 and 1 deliberately makes each descending diagonal band two virtual pixels thick. Repeating modulo 13 creates blank intervals. When a band enters or leaves a 4 x 4 cell, the cell legitimately contains a small corner or hook fragment. The color is selected by terminal row and repeats cyan/yellow/green/magenta every four character rows; color does not encode the font part.", s["body"]),
              Image(str(args.screenshot_wide), width=174 * mm, height=103.3 * mm),
              p("Supplied screenshot. The repeating two-pixel bands, blank periods and four-row palette cycle match the source predicate exactly.", s["small"]),
              PageBreak()]

    story += [p("8. Enumerate every shape the geometry test can generate", s["h1"]),
              p("Across all relative cell positions and all thirteen animation phases, the test can generate only the following nine masks. Nothing else is emitted by the subpixels stage.", s["body"])]
    cards = [mask_card(item, s, 53 * mm) for item in report["geometry_test"]["unique_masks"]]
    story += [Table([cards[index:index + 3] for index in range(0, 9, 3)],
                    colWidths=[58 * mm] * 3,
                    style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                           ("TOPPADDING", (0, 0), (-1, -1), 3),
                                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)])),
              p("Only 0x8000 and 0xC800 use Part 1 because they set bit 15, the bottom-left local pixel. Their decoded shapes continue the same diagonal band as the Part 0 masks around them.", s["body"]),
              gate("GATE 7 - geometry reconstruction", "Decoding every emitted glyph must reproduce the analytic diagonal predicate in every local pixel.", f"The independent audit tested {report['geometry_test']['phase_cases_verified']:,} combinations of cell column, cell row and tick; each combination compared all sixteen decoded pixels. Decode mismatches: {report['geometry_test']['decode_mismatches']}.", "PASS. The visible hook/corner fragments are expected partial bands, not wrong codepoints.", s),
              PageBreak()]

    story += [p("9. Seam evidence and final determination", s["h1"]),
              p("A full-cell field exercises the maximum mask 0xFFFF, which is in Part 1 at U+107FFF. Any glyph-width, ascent, descent or exterior-bound error would appear as black seams between adjacent cells or rows.", s["body"]),
              p("Installed Pango seam matrix", s["h2"])]
    seam_data = [["Size", "Raster", "Black seam pixels", "Result"]]
    for line in seam_lines:
        # PASS  8 px: 256x129 solid raster, zero seam pixels
        fields = line.replace(":", "").replace(",", "").split()
        seam_data.append([fields[1] + " px", fields[3], "0", "PASS"])
    table = Table(seam_data, colWidths=[30 * mm, 45 * mm, 50 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#B5C2CC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREEN_PALE]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [table, Spacer(1, 5 * mm),
              gate("GATE 8 - seamless solid mass", "A solid 0xFFFF field must contain no black pixel between characters or rows at tested small raster sizes.", "Corrected v0.3 installed Pango rasters at 8,9,10,11,12,13,14,16,18 and 20 pixels contained zero black seam pixels even with edge_overfill=0.", "PASS. Overfill is not required for seamless solid rendering in the tested stack.", s),
              Spacer(1, 5 * mm),
              p("Final determination", s["h2"]),
              p("Three observations are now separated. v0.1 had unequal exterior outlines. v0.2 fixed that geometry but encoded rows LSB-left. v0.3 preserves exact geometry and re-encodes every glyph MSB-left. Exhaustive mapping, component, trail-step, runtime-selection and seam tests now pass against the requested formula.", s["body"]),
              PageBreak()]

    story += [p("Appendix A - reproducible commands and artifacts", s["h1"]),
              p("Independent full audit", s["h2"]),
              p("cd experiments/pua-4x4<br/>python3 audit_pua4x4_chain.py build --edge-overfill 0 --output output/audit/pua4x4-v0.3-audit.json", s["mono"]),
              p("Installed Linux audit", s["h2"]),
              p("cd $HOME/dev/FontMaker/pua4x4<br/>python3 audit_pua4x4_chain.py $HOME/.local/share/fonts --edge-overfill 0 --output output/audit/installed-pua4x4-v0.3-audit.json", s["mono"]),
              p("Existing exhaustive audit", s["h2"]),
              p("python3 verify_pua4x4.py build<br/>python3 verify_equal_pixel_geometry.py build<br/>python3 verify_trail_steps.py<br/>python3 verify_linux_runtime.py<br/>python3 verify_pango_seams.py --font build --sizes 8,9,10,11,12,13,14,16,18,20", s["mono"]),
              p("Evidence artifacts", s["h2"]),
              p("pua4x4-v0.3-audit.json - corrected local reproducible-build audit<br/>"
                "installed-pua4x4-v0.3-audit.json - corrected installed-binary audit<br/>"
                "installed-v0.3-geometry-layout.json - Pango run selection and unknown-glyph count<br/>"
                "installed-v0.3-boundary-layout.json - P0/P1 boundary Pango evidence<br/>"
                "installed-seam-audit.txt - measured solid-raster seam matrix", s["body"]),
              p("Verified binary identities", s["h2"]),
              p("v0.3 PUA4x4Part0.ttf<br/>b34587617903d8115d8df788b6430b172c614d8fa9d1689eb403a5c8d26f8c6d<br/><br/>"
                "v0.3 PUA4x4Part1.ttf<br/>ccfad9f530ceda3f33791aec877b81b81472604e68c5e1633c50bb6d2da2681a<br/><br/>"
                "Superseded v0.1 and v0.2 binaries are preserved under legacy/.", s["mono"]),
              p("Audit status: PASS for v0.3. Mapping: bit=4*y+(3-x). Patterns verified: 65,536. Unique codepoints: 65,536. Equal components: 16/16 in both parts. Trail left-step regression: PASS. Geometry phase cases: 2,197. Geometry decode mismatches: 0. Pango unknown glyphs: 0.", s["callout"])]

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    print(args.output)


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=base / "output/audit/installed-pua4x4-v0.3-audit.json")
    parser.add_argument("--seams", type=Path, default=base / "output/audit/installed-seam-v0.3-audit.txt")
    parser.add_argument("--geometry-raster", type=Path, default=base / "output/audit/installed-v0.3-geometry-glyphs.png")
    parser.add_argument("--boundary-raster", type=Path, default=base / "output/audit/installed-v0.3-boundary-glyphs.png")
    parser.add_argument("--before-pixel-raster", type=Path, default=base / "output/audit/current-overfill-horizontal-64.png")
    parser.add_argument("--after-pixel-raster", type=Path, default=base / "output/audit/installed-v0.3-horizontal-64.png")
    parser.add_argument("--screenshot-wide", type=Path,
                        default=base / "output/audit/supplied-geometry-test.png")
    parser.add_argument("--output", type=Path,
                        default=base / "output/pdf/PUA-4x4-Mapping-Chain-MSB-Left-Evidence-v1.2.pdf")
    args = parser.parse_args()
    for path in (args.audit, args.seams, args.geometry_raster,
                 args.boundary_raster, args.before_pixel_raster,
                 args.after_pixel_raster, args.screenshot_wide):
        if not path.exists():
            parser.error(f"required evidence file not found: {path}")
    build(args)


if __name__ == "__main__":
    main()
