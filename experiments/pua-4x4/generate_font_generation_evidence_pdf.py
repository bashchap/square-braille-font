#!/usr/bin/env python3
"""Generate the audited PUA 4x4 v0.4 font-generation evidence PDF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)


NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#147D92")
CYAN = colors.HexColor("#D9F4F7")
GREEN = colors.HexColor("#147D64")
PALE_GREEN = colors.HexColor("#E3F6EF")
AMBER = colors.HexColor("#B26A00")
PALE_AMBER = colors.HexColor("#FFF3D6")
RED = colors.HexColor("#A61B1B")
PALE_RED = colors.HexColor("#FCE8E8")
GRAY = colors.HexColor("#52606D")
LIGHT = colors.HexColor("#EEF2F6")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=25, leading=29, textColor=NAVY, spaceAfter=8 * mm),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName="Helvetica", fontSize=12, leading=17, textColor=GRAY, spaceAfter=6 * mm),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=4 * mm),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=BLUE, spaceBefore=3 * mm, spaceAfter=2 * mm),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=colors.HexColor("#243B53"), spaceAfter=2.5 * mm),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=GRAY),
        "mono": ParagraphStyle("Mono", parent=base["Code"], fontName="Courier", fontSize=7.7, leading=10.5, textColor=colors.HexColor("#102A43"), backColor=LIGHT, borderPadding=6, spaceAfter=3 * mm),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=10.3, leading=14.2, textColor=NAVY, backColor=CYAN, borderColor=BLUE, borderWidth=0.7, borderPadding=8, spaceAfter=4 * mm),
        "center": ParagraphStyle("Center", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=GRAY),
    }


def para(text, style):
    return Paragraph(text, style)


def status_box(title, expectation, observation, result, palette, s):
    color, pale = palette
    table = Table([
        [para(title, s["h2"])],
        [para(f"<b>Expectation.</b> {expectation}", s["body"])],
        [para(f"<b>Observation.</b> {observation}", s["body"])],
        [para(f"<b>Outcome.</b> {result}", s["body"])],
    ], colWidths=[172 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), 0.8, color),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def crop(source: Path, output: Path, box):
    output.parent.mkdir(parents=True, exist_ok=True)
    PILImage.open(source).convert("RGB").crop(box).save(output)
    return output


def fit_image(path: Path, width: float, height: float):
    image = PILImage.open(path)
    ratio = min(width / image.width, height / image.height)
    return Image(str(path), width=image.width * ratio, height=image.height * ratio)


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(20 * mm, 10.5 * mm, "PUA 4×4 v0.4 font-generation evidence")
    canvas.drawRightString(190 * mm, 10.5 * mm, f"page {doc.page}")
    canvas.restoreState()


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf")
    args = parser.parse_args()
    audit = root / "output/audit"
    math = load(audit / "pua4x4-mathematics-proof-v1.0.json")
    root_cause = load(audit / "pua4x4-horizontal-placement-root-cause.json")
    stored = load(audit / "pua4x4-v0.4-candidate-font-audit.json")
    freetype = load(audit / "pua4x4-v0.4-candidate-freetype-raster.json")
    c1_pango = load(audit / "pua4x4-v0.4-candidate-pango-raster.json")
    c2 = load(audit / "pua4x4-v0.4-candidate.2-derivation.json")
    c2_pango = load(audit / "pua4x4-v0.4-candidate2-final-diagnostic-pango-raster.json")
    threshold = load(audit / "fullmask-overfill-probes/measurements.json")
    c3 = load(audit / "pua4x4-v0.4-candidate.3-derivation.json")
    c3_pango = load(audit / "pua4x4-v0.4-candidate3-pango-raster.json")
    terminal = load(audit / "pua4x4-v0.4-terminal-triangle-comparison.json")
    overhang = load(audit / "pua4x4-v0.4-candidate3-onebit-overhang.json")

    assert math["status"] == "PASS_MATHEMATICS_ONLY"
    assert root_cause["status"] == "ROOT_CAUSE_CONFIRMED_AND_CANDIDATE_CORRECTED"
    assert stored["patterns_verified"] == 65536 and stored["effective_position_mismatches"] == 0
    assert freetype["mismatched_pixels"] == 0 and freetype["partially_covered_pixels"] == 0
    assert c2["status"] == "PASS_CONTROLLED_HINT_ONLY_DIFFERENCE"
    assert c3["status"] == "PASS_EXACT_DECLARED_TRANSFORM" and c3["codepoints_compared"] == 65536
    assert terminal["outcome"]["candidate3_pass"] is True
    assert all(item["status"] == "PASS" for item in c3_pango["candidate_terminal_point_seam_matrix"])

    assets = audit / "pdf-assets-v0.4"
    c1_crop = crop(Path(terminal["candidate1_exact_core"]["image"]), assets / "triangle-candidate1.png", (700, 175, 1205, 825))
    c3_crop = crop(Path(terminal["candidate3_seam_guard_100"]["image"]), assets / "triangle-candidate3.png", (700, 175, 1205, 825))
    s = styles()
    story = []

    story += [Spacer(1, 18 * mm), para("PUA 4×4", s["title"]), para("Font-generation evidence · v0.4 release candidate 1", s["title"]),
              para("From approved mathematics to stored TrueType data, Linux selection, fractional raster behavior and a real terminal capture", s["subtitle"]),
              Spacer(1, 8 * mm), para("RESULT", s["h2"]),
              para("Candidate.3 preserves the approved mapping for all 65,536 masks, corrects the v0.3 effective-placement defect and removes the measured terminal grid. It remains installed under an isolated name; v0.3 is preserved.", s["callout"]),
              Table([[para("Part 0 SHA-256", s["small"]), para(c3["parts"][0]["candidate_sha256"], s["small"])],
                     [para("Part 1 SHA-256", s["small"]), para(c3["parts"][1]["candidate_sha256"], s["small"])]], colWidths=[35 * mm, 137 * mm], style=TableStyle([("BACKGROUND", (0, 0), (0, -1), LIGHT), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)])),
              Spacer(1, 12 * mm), para("Scope boundary", s["h2"]), para("This report treats each stage as a separate gate. A stored outline PASS never claims a terminal PASS. A failed or excluded launch is retained rather than silently discarded.", s["body"]), PageBreak()]

    bit_table = Table([[para(str(bit), s["center"]) for bit in row] for row in [[3,2,1,0],[7,6,5,4],[11,10,9,8],[15,14,13,12]]], colWidths=[25 * mm] * 4, rowHeights=[16 * mm] * 4)
    bit_table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 1.2, BLUE), ("BACKGROUND", (0,0), (-1,-1), CYAN), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story += [para("1 · Fixed mathematical oracle", s["h1"]), para("Virtual x increases left-to-right, but bit significance inside every row increases right-to-left. The number in each square is the bit index.", s["body"]), bit_table, Spacer(1, 5 * mm),
              para("terminal_cell_x = vx // 4<br/>terminal_cell_y = vy // 4<br/>local_x = vx % 4; local_y = vy % 4<br/><b>bit = 4 × local_y + (3 − local_x)</b><br/>bit_value = 1 &lt;&lt; bit", s["mono"]),
              para("Part 0: mask 0000–7FFF → U+F0000 + mask<br/>Part 1: mask 8000–FFFF → U+100000 + (mask − 0x8000)", s["callout"]),
              para(f"Machine oracle: {math['test_counts']['all_masks_round_tripped']:,} masks, {math['test_counts']['unique_codepoints']:,} unique codepoints, zero round-trip failures.", s["body"]), PageBreak()]

    gate_rows = [["Gate", "Requirement", "Observed result"],
                 ["A", "Mathematics", "PASS · approved separately"],
                 ["B", "Stored cmap/outlines/hmtx", "PASS · 65,536/65,536"],
                 ["C", "Integer-grid FreeType", "PASS · 0 mismatches"],
                 ["D", "Linux selection and shaping", "PASS · no unknown glyphs"],
                 ["E", "8–20 pt / 96 DPI solid field", "C1/C2 FAIL · C3 PASS"],
                 ["F", "14 pt real MATE Terminal", "C1 5,632 low pixels · C3 0"],
                 ["G", "Independent Linux rebuild", "PASS · byte-identical"]]
    gate_table = Table([[para(str(v), s["small"]) for v in row] for row in gate_rows], colWidths=[14*mm, 83*mm, 75*mm], repeatRows=1)
    gate_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0,1), (-1,-1), colors.white), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    story += [para("2 · Evidence gates", s["h1"]), para("Each gate states what it proves and, equally importantly, what it does not prove.", s["body"]), gate_table, Spacer(1, 6*mm),
              status_box("Why the old conclusion changed", "A raw outline at x=375 should render at x=375.", "The earlier verifier inspected raw components but did not apply the TrueType hmtx placement formula.", "The gap in the verifier is now a permanent regression test.", (AMBER, PALE_AMBER), s), PageBreak()]

    root_rows = [["mask", "required x", "raw xMin", "v0.3 LSB", "effective xMin"], ["0008","0","0","0","0"], ["0004","1","125","0","0"], ["0002","2","250","0","0"], ["0001","3","375","0","0"]]
    root_table = Table([[para(v, s["small"]) for v in row] for row in root_rows], colWidths=[25*mm,28*mm,30*mm,30*mm,39*mm])
    root_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0,2), (-1,-1), PALE_RED), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story += [para("3 · Reproduced v0.3 root cause", s["h1"]), para("TrueType positions a simple glyph with:", s["body"]), para("effective_x = raw_x − (xMin − leftSideBearing)<br/><b>effective_xMin = leftSideBearing</b>", s["mono"]), root_table, Spacer(1,4*mm),
              para("Exactly <b>4,095</b> nonempty Part 0 masks have xMin &gt; 0 and therefore shift left in v0.3. Part 1 always includes bit 15 in the leftmost column, so its xMin is zero.", s["callout"]),
              status_box("Root-cause gate", "Effective placement equals approved local x.", "v0.3 fails 4,095 masks; candidate.1 fails zero.", "ROOT CAUSE CONFIRMED.", (RED, PALE_RED), s), PageBreak()]

    story += [para("4 · Candidate.1: corrected exact core", s["h1"]), para("Candidate.1 removes composites, writes the selected-cell union as simple contours and assigns each nonempty glyph an LSB equal to its xMin.", s["body"]),
              para("500 × 1000 unit cell<br/>125 × 250 unit subcells<br/>0 units overfill<br/>simple union contours<br/>fixed 500-unit advance", s["mono"]),
              status_box("Stored-font proof", "Every cmap, contour edge, decoded mask and metric matches an independent oracle.", f"{stored['patterns_verified']:,} patterns; zero outline, mask, metric or effective-position mismatches.", "PASS · stored data only.", (GREEN, PALE_GREEN), s),
              Spacer(1,4*mm), fit_image(root / freetype["comparison_image"], 165*mm, 65*mm),
              para(f"Integer-grid raster: {freetype['raster_cases']} cases at {', '.join(map(str, freetype['integer_grid_sizes_ppem']))} ppem; zero mismatched or partially covered pixels.", s["center"]), PageBreak()]

    comparison = Table([[fit_image(c1_crop, 80*mm, 95*mm), fit_image(c3_crop, 80*mm, 95*mm)], [para("Candidate.1 · exact vector core", s["center"]), para("Candidate.3 · 100-unit seam guard", s["center"])]], colWidths=[84*mm,84*mm])
    comparison.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("BOX", (0,0), (0,0), .5, colors.HexColor("#CBD5E1")), ("BOX", (1,0), (1,0), .5, colors.HexColor("#CBD5E1"))]))
    c1b = terminal["candidate1_exact_core"]["boundary"]
    c3b = terminal["candidate3_seam_guard_100"]["boundary"]
    story += [para("5 · The real fractional-raster failure", s["h1"]), para("The integer-grid result did not predict a 14-point, 96-DPI terminal. The nominal 18.666… pixel em is placed in a 19-pixel terminal row, leaving partially covered cached glyph edges.", s["body"]), comparison, Spacer(1,4*mm),
              Table([[para("Candidate.1 boundary pixels", s["small"]), para(f"{c1b['low_coverage_pixels']:,} below 90% coverage ({100*c1b['low_coverage_fraction']:.3f}%)", s["small"])], [para("Candidate.3 boundary pixels", s["small"]), para(f"{c3b['low_coverage_pixels']:,} below 90% coverage", s["small"])]], colWidths=[65*mm,107*mm], style=TableStyle([("GRID", (0,0), (-1,-1), .5, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0,0), (0,-1), LIGHT), ("LEFTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)])),
              para("The low-coverage pixels concentrate at character boundaries, proving a raster-edge problem rather than a bit-mask problem.", s["callout"]), PageBreak()]

    c2_counts = [(item["size_points"], item["nonwhite_pixels"]) for item in c2_pango["candidate_terminal_point_seam_matrix"]]
    story += [para("6 · Candidate.2: controlled hinting test", s["h1"]), para("Candidate.2 differs from candidate.1 only in names, native point-grid instruction programs, integer-ppem metadata, the gasp table and maxp instruction maxima. All 65,536 cmap entries, raw contours and hmtx records compare equal.", s["body"]),
              para("Expected: native grid execution removes fractional edge coverage.<br/>Observed: " + " · ".join(f"{size}pt={count:,}" for size,count in c2_counts), s["mono"]),
              status_box("Candidate.2 decision", "Zero nonwhite seam pixels at each point size.", "Every measured count is identical to candidate.1.", "FAIL · retained as a negative result; not selected.", (RED, PALE_RED), s),
              para("This test is tied to the final candidate.2 SHA-256 file and a separate Pango JSON. It is not inferred from a screenshot.", s["body"]), PageBreak()]

    threshold_rows = [["guard units", "8", "9", "10", "11", "12", "13", "14", "16", "18", "20", "all"]]
    for record in threshold["records"]:
        threshold_rows.append([str(record["overfill_font_units"])] + [("0" if item["nonwhite_pixels"] == 0 else "×") for item in record["sizes"]] + [("PASS" if record["all_sizes_solid_white"] else "—")])
    threshold_table = Table([[para(v, s["small"]) for v in row] for row in threshold_rows], colWidths=[22*mm]+[12*mm]*10+[18*mm])
    threshold_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CBD5E1")), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("BACKGROUND", (0,-1), (-1,-1), PALE_GREEN), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    story += [para("7 · Measured seam-guard threshold", s["h1"]), para("Each probe changed only U+107FFF and its matching bearing. ‘0’ means zero nonwhite pixels; ‘×’ means a partially covered seam remained.", s["body"]), threshold_table, Spacer(1,5*mm),
              para("100 font units is the first tested value that passes all ten point sizes. At 14 pt, 40 units already passes; the selected value covers the full 8–20 pt test range.", s["callout"]), PageBreak()]

    transform_table = Table([[para("candidate.1 coordinate", s["small"]), para("candidate.3 coordinate", s["small"])], ["x = 0", "x = −100"], ["x = 500", "x = 600"], ["y = −200", "y = −300"], ["y = 800", "y = 900"], ["all other x/y", "unchanged"]], colWidths=[80*mm,80*mm])
    transform_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#CBD5E1")), ("ALIGN", (0,1), (-1,-1), "CENTER"), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story += [para("8 · Candidate.3: selected transform", s["h1"]), para("Candidate.3 retains the exact 4×4 core and expands only outline coordinates already lying on a terminal-cell exterior edge.", s["body"]), transform_table, Spacer(1,5*mm),
              status_box("Exhaustive derivation proof", "Every candidate.3 coordinate equals the declared transform of candidate.1; cmap and formula never change.", f"{c3['codepoints_compared']:,} codepoints compared; zero unexpected outline changes; zero formula/cmap changes.", "PASS.", (GREEN, PALE_GREEN), s),
              para(f"Guarded glyphs: Part 0 = {c3['parts'][0]['guarded_glyphs']:,}; Part 1 = {c3['parts'][1]['guarded_glyphs']:,}.", s["body"]), PageBreak()]

    c3_sizes = c3_pango["candidate_terminal_point_seam_matrix"]
    c3_table = Table([["size", "black", "nonwhite", "status"]] + [[str(x["size_points"]), str(x["black_pixels"]), str(x["nonwhite_pixels"]), x["status"]] for x in c3_sizes], colWidths=[30*mm,35*mm,45*mm,45*mm])
    c3_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0,1), (-1,-1), PALE_GREEN), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    story += [para("9 · Candidate.3 raster and terminal result", s["h1"]), para("The isolated point-unit renderer and the real terminal now agree.", s["body"]), c3_table, Spacer(1,5*mm),
              fit_image(Path(terminal["candidate3_seam_guard_100"]["image"]), 170*mm, 88*mm),
              para("Actual 1920×990 MATE Terminal capture · 211×50 cells · 14 pt · 96 DPI", s["center"]),
              para("Measured full-mask boundary pixels below 90% expected coverage: <b>0</b>.", s["callout"]), PageBreak()]

    b = overhang["candidate1_exact_core"]
    g = overhang["candidate3_seam_guard_100"]
    over_rows = [["mask", "candidate.1 run", "candidate.3 run", "difference"]]
    for base, guarded in zip(b, g):
        br, gr = base["ink_runs"][0], guarded["ink_runs"][0]
        over_rows.append([base["mask"], str(br), str(gr), f"left {br[0]-gr[0]}, right {gr[1]-br[1]}"])
    over_table = Table([[para(str(v), s["small"]) for v in row] for row in over_rows], colWidths=[30*mm,45*mm,45*mm,45*mm])
    over_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .5, colors.HexColor("#CBD5E1")), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("BACKGROUND", (0,1), (-1,1), PALE_AMBER), ("BACKGROUND", (0,-1), (-1,-1), PALE_AMBER), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story += [para("10 · Declared cost: exterior one-bit overhang", s["h1"]), para("A seamless guard is not mathematically free. The exact difference is measured with one tested glyph in the middle of three cells at a 40-pixel em.", s["body"]), over_table, Spacer(1,5*mm),
              para("The two interior x positions are unchanged. The exterior positions overhang into the neighboring terminal cell. This is the deliberate implementation difference from the ideal 4×4 core and must be considered by applications drawing isolated boundary pixels.", s["callout"]),
              status_box("Trade-off", "Exact isolated subcell bounds and universal fractional-size seams would both pass.", "The tested raster stack cannot satisfy both with unhinted cached glyphs. Embedded hinting did not change the result; 100-unit overlap does.", "Candidate.3 prioritizes the user’s seamless solid-mass requirement and records the overhang exactly.", (AMBER, PALE_AMBER), s), PageBreak()]

    story += [para("11 · Reproducibility and preserved assets", s["h1"]), para("Candidate.3 was regenerated independently on Linux with Python 3.12.3 and FontTools 4.46.0. Both Linux files compare byte-for-byte with the macOS-generated files.", s["body"]),
              para(f"Part 0  {c3['parts'][0]['candidate_sha256']}<br/>Part 1  {c3['parts'][1]['candidate_sha256']}", s["mono"]),
              para("The repository package was then installed on Linux from its checked-in directory rather than from a build tree. Installed bytes matched the package; wcwidth was one throughout both ranges; Fontconfig selected both candidate parts; and Pango shaped text plus P0/P1 with zero unknown glyphs.", s["body"]),
              para("The unversioned launcher and every named demo now select the candidate-specific profile. Linux readback proved `PUA 4x4 v0.4 Candidate 3 12`; installed P0/P1 hashes and Fontconfig selections matched RC1. Demo masks, Boolean operations and codepoint formulas were not changed. `PUA4X4_USE_V03=1` retains an explicit legacy route.", s["body"]),
              para("v0.3, candidate.1, candidate.2 and candidate.3 all have distinct files/families. The current `PUA 4x4` alias was not overwritten.", s["callout"]),
              para("Recorded procedural exception", s["h2"]), para("The first candidate.3 launch inherited `visible-name='Default'`; MATE reported `No such profile \"(null)\", using default profile`. That window was excluded. The name was corrected and read back with font `PUA 4x4 v0.4 Candidate 3 14` before the accepted capture. Both logs are retained.", s["body"]), PageBreak()]

    commands = """cd experiments/pua-4x4
python3 verify_mathematical_mapping.py
python3 generate_pua4x4_v04_candidate.py
python3 verify_pua4x4_v04_candidate.py
python3 audit_horizontal_placement.py
python3 verify_candidate_freetype_raster.py
python3 make_v04_candidate2_hinted.py
python3 verify_v04_candidate2_derivation.py
python3 make_fullmask_overfill_probes.py
python3 make_v04_candidate3_seamguard.py
python3 verify_v04_candidate3_derivation.py
python3 verify_v04_rc1_package.py
./install-linux-v04-candidate3.sh
./launch-linux-v04-candidate3.sh triangle"""
    story += [para("12 · Reproduce and inspect", s["h1"]), para(commands.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), s["mono"]),
              para("Primary machine-readable evidence", s["h2"]), para("pua4x4-horizontal-placement-root-cause.json<br/>pua4x4-v0.4-candidate-font-audit.json<br/>pua4x4-v0.4-candidate-freetype-raster.json<br/>pua4x4-v0.4-candidate2-final-diagnostic-pango-raster.json<br/>fullmask-overfill-probes/measurements.json<br/>pua4x4-v0.4-candidate.3-derivation.json<br/>pua4x4-v0.4-candidate3-pango-raster.json<br/>pua4x4-v0.4-terminal-triangle-comparison.json<br/>pua4x4-v0.4-candidate3-onebit-overhang.json<br/>pua4x4-v0.4-rc1-packaged-linux-runtime.json<br/>pua4x4-v0.4-demo-launcher-profile.json<br/>cross-environment/candidate3-linux-hashes.txt", s["mono"]),
              para("Decision state", s["h2"]), para("Candidate.3 is the recommended v0.4 release candidate for visual acceptance. Promotion to the unversioned `PUA 4x4` alias is intentionally separate from this proof so the preserved v0.3 environment cannot be mistaken for the tested candidate.", s["callout"])]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(args.output), pagesize=A4, leftMargin=19*mm, rightMargin=19*mm, topMargin=18*mm, bottomMargin=22*mm, title="PUA 4x4 Font Generation Evidence v0.4 RC1", author="Square Braille Font project")
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(args.output)


if __name__ == "__main__":
    main()
