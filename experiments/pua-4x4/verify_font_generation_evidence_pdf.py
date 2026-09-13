#!/usr/bin/env python3
"""Verify the font-generation evidence PDF's structure and key claims."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=root / "output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf")
    args = parser.parse_args()
    reader = PdfReader(str(args.pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) >= 12, len(reader.pages)
    for phrase in (
        "bit = 4 × local_y + (3 − local_x)",
        "4,095",
        "5,632",
        "Candidate.3",
        "100 font units",
        "byte-for-byte",
        "checked-in directory",
        "zero unknown glyphs",
        "pua4x4-v0.4-rc1-packaged-linux-runtime.json",
        "pua4x4-v0.4-demo-launcher-profile.json",
        "PUA4X4_USE_V03=1",
        "94847138178994d016d3a0e315be0aa10604c1ea85e01b6d98eb8f41421ac9d8",
        "a979a9568dbe5c0b90bb54eb6bc0e4a70caf536bd4c2e791d589796a984f0ec1",
    ):
        assert phrase in text, phrase
    print(f"PASS: {len(reader.pages)} pages; required claims and both hashes present")
    print(args.pdf)


if __name__ == "__main__":
    main()
