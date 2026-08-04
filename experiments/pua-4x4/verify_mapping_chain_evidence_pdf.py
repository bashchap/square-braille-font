#!/usr/bin/env python3
"""Verify the final PUA 4x4 mapping-chain evidence PDF and audit artifacts."""

import argparse
import json
from pathlib import Path

from pypdf import PdfReader


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="?",
                        default=base / "output/pdf/PUA-4x4-Mapping-Chain-MSB-Left-Evidence-v1.2.pdf")
    parser.add_argument("--audit", type=Path,
                        default=base / "output/audit/installed-pua4x4-v0.3-audit.json")
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["edge_overfill"] == 0
    assert audit["patterns_verified"] == 65536
    assert audit["unique_codepoints_verified"] == 65536
    assert audit["geometry_test"]["phase_cases_verified"] == 2197
    assert audit["geometry_test"]["decode_mismatches"] == 0
    assert len(audit["geometry_test"]["unique_masks"]) == 9

    reader = PdfReader(args.pdf)
    assert len(reader.pages) == 12
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = " ".join(text.split())
    required = (
        "Font v0.3 implements the intended MSB-left mapping",
        "The user's character-editor calculation supplied that missing semantic requirement",
        "16, 10, 10, 16 pixels",
        "10, 10, 10, 10 pixels",
        "Every one-bit glyph must have identical 125 x 250 outline bounds",
        "bit b = 4 x local_y + (3 - local_x)",
        "OR total = 0x36C8",
        "U+104631",
        "format 12",
        "All 65,536 v0.3 pattern glyphs were parsed",
        "unknown-glyphs=0",
        "only the following nine masks",
        "Decode mismatches: 0",
        "zero black seam pixels",
        "Appendix A - reproducible commands and artifacts",
        "Trail left-step regression: PASS",
    )
    for phrase in required:
        assert phrase in normalized, phrase
    for number, page in enumerate(reader.pages, 1):
        assert f"Page {number}" in (page.extract_text() or "")
    print(f"PASS: {args.pdf}")
    print("PASS: 12 pages, correction evidence, page labels and audit invariants")


if __name__ == "__main__":
    main()
