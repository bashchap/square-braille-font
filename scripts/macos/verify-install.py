#!/usr/bin/env python3
"""Verify the three user-installed macOS graphics fonts and one-cell widths."""

from __future__ import annotations

import ctypes
import hashlib
import platform
from pathlib import Path

from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[2]
USER_FONTS = Path.home() / "Library" / "Fonts"
SPECS = (
    (
        ROOT / "fonts/current/Square-Braille-Unicode-Text-Seamless.ttf",
        "Square Braille Unicode Text Seamless",
        ((0x2800, 0x28FF), (0xE000, 0xE0FF)),
    ),
    (
        ROOT / "fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part0V06Candidate6.ttf",
        "PUA 4x4 Part 0 v0.6 Candidate 6",
        ((0xF0000, 0xF7FFF),),
    ),
    (
        ROOT / "fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part1V06Candidate6.ttf",
        "PUA 4x4 Part 1 v0.6 Candidate 6",
        ((0x100000, 0x107FFF),),
    ),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def family_names(font: TTFont) -> set[str]:
    names = set()
    for record in font["name"].names:
        if record.nameID == 1:
            try:
                names.add(record.toUnicode())
            except UnicodeDecodeError:
                pass
    return names


def verify_font(source: Path, expected_family: str, ranges) -> None:
    installed = USER_FONTS / source.name
    if not installed.is_file():
        raise SystemExit(f"FAIL missing installed font: {installed}")
    if digest(source) != digest(installed):
        raise SystemExit(f"FAIL installed bytes differ from repository: {installed}")
    with TTFont(installed, lazy=True) as font:
        families = family_names(font)
        if expected_family not in families:
            raise SystemExit(
                f"FAIL family mismatch for {installed.name}: {sorted(families)}"
            )
        cmap = font.getBestCmap() or {}
        for first, last in ranges:
            missing = next((cp for cp in range(first, last + 1) if cp not in cmap), None)
            if missing is not None:
                raise SystemExit(f"FAIL {installed.name} lacks U+{missing:06X}")
    print(f"PASS {expected_family}: {installed}  sha256={digest(installed)[:16]}...")


def verify_widths() -> None:
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    libc.wcwidth.argtypes = [ctypes.c_wchar]
    libc.wcwidth.restype = ctypes.c_int
    for cp in (0x2800, 0x28FF, 0xF0000, 0xF7FFF, 0x100000, 0x107FFF):
        width = libc.wcwidth(chr(cp))
        if width != 1:
            raise SystemExit(f"FAIL macOS wcwidth U+{cp:06X}: expected 1, got {width}")
    print("PASS macOS libc wcwidth: Square Braille and both PUA 4x4 planes are one cell")


def main() -> int:
    if platform.system() != "Darwin":
        raise SystemExit("This verifier is for macOS.")
    for source, family, ranges in SPECS:
        verify_font(source, family, ranges)
    verify_widths()
    print("PASS complete macOS graphics-font installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
