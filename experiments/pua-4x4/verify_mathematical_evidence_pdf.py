#!/usr/bin/env python3
"""Verify the generated PUA 4x4 mathematics evidence PDF and source audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader


REQUIRED_PDF_TEXT = (
    "fedcba9876543210",
    "b = 4 * ly + (3 - lx)",
    "U+F0400",
    "U+101669",
    "30,720",
    "65,536",
    "3,145,728",
    "FAIL (recorded, not waived)",
)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        type=Path,
        default=root / "output" / "pdf" /
        "PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-mathematics-proof-v1.0.json",
    )
    args = parser.parse_args()

    report = json.loads(args.json.read_text(encoding="utf-8"))
    assert report["status"] == "PASS_MATHEMATICS_ONLY"
    assert report["authoritative_layout"] == [
        [3, 2, 1, 0],
        [7, 6, 5, 4],
        [11, 10, 9, 8],
        [15, 14, 13, 12],
    ]
    assert report["bit_label_order_msb_to_lsb"] == "fedcba9876543210"
    assert report["test_counts"]["virtual_round_trips"] == 30_720
    assert report["test_counts"]["all_masks_round_tripped"] == 65_536
    assert report["test_counts"]["unique_codepoints"] == 65_536
    assert report["test_counts"]["boolean_operation_assertions"] == 3_145_728
    assert report["test_counts"]["triangle_mapping"]["missing_after_decode"] == 0
    assert report["test_counts"]["triangle_mapping"]["unexpected_after_decode"] == 0
    assert report["observed_runtime_status"]["result"] == (
        "FAIL_NOT_EXPLAINED_BY_MATHEMATICS_GATE"
    )

    reader = PdfReader(str(args.pdf))
    assert len(reader.pages) == 16
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for required in REQUIRED_PDF_TEXT:
        assert required in text, required

    print("PASS: source audit has the authoritative MSB-left mapping")
    print("PASS: source audit records exhaustive test populations")
    print("PASS: source audit preserves the observed visual failure")
    print("PASS: PDF has 16 pages and all required conclusions")
    print(args.pdf)


if __name__ == "__main__":
    main()
