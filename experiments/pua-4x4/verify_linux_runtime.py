#!/usr/bin/env python3
"""Verify Linux width, Fontconfig, and Pango fallback behavior."""

import ctypes
import json
import subprocess
import tempfile
from pathlib import Path

from pua4x4 import mask_to_codepoint


def font_match(pattern):
    return subprocess.check_output(
        ["fc-match", "-f", "%{family}\t%{file}\n", pattern], text=True
    ).strip()


def collect_descriptions(value, result):
    if isinstance(value, dict):
        description = value.get("description")
        if isinstance(description, str):
            result.add(description)
        for child in value.values():
            collect_descriptions(child, result)
    elif isinstance(value, list):
        for child in value:
            collect_descriptions(child, result)


def main():
    libc = ctypes.CDLL(None)
    libc.wcwidth.argtypes = [ctypes.c_wchar]
    for mask in (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF):
        character = chr(mask_to_codepoint(mask))
        width = libc.wcwidth(character)
        assert width == 1, "mask %04X has wcwidth %d, expected 1" % (mask, width)

    assert font_match("PUA 4x4:charset=f0001").startswith("PUA 4x4 Part 0\t")
    assert font_match("PUA 4x4:charset=100000").startswith("PUA 4x4 Part 1\t")

    proof = "Text " + " ".join(
        chr(mask_to_codepoint(mask))
        for mask in (0x0001, 0x7FFF, 0x8000, 0xFFFF)
    )
    with tempfile.TemporaryDirectory(prefix="pua4x4-") as directory:
        serialized = Path(directory) / "layout.json"
        subprocess.run(
            [
                "pango-view",
                "--no-display",
                "--font=PUA 4x4 24",
                "--text=" + proof,
                "--serialize-to=" + str(serialized),
            ],
            check=True,
        )
        layout = json.loads(serialized.read_text(encoding="utf-8"))

    assert layout["output"]["unknown-glyphs"] == 0
    descriptions = set()
    collect_descriptions(layout, descriptions)
    for family in (
        "Square Braille Unicode Text Seamless",
        "PUA 4x4 Part 0",
        "PUA 4x4 Part 1",
    ):
        assert any(item.startswith(family + " ") for item in descriptions), (
            "%s missing from Pango runs: %r" % (family, descriptions)
        )
    print("PASS Linux wcwidth: both PUA 4x4 ranges occupy one column")
    print("PASS Fontconfig: explicit alias selects Part 0 and Part 1")
    print("PASS Pango: text + both graphics parts, zero unknown glyphs")


if __name__ == "__main__":
    main()
