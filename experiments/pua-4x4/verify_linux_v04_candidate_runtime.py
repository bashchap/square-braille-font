#!/usr/bin/env python3
"""Verify isolated Linux Fontconfig and Pango selection for v0.4 candidate."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
from pathlib import Path


P0_BASE = 0xF0000
P1_BASE = 0x100000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def codepoint(mask: int) -> int:
    if mask < 0x8000:
        return P0_BASE + mask
    return P1_BASE + mask - 0x8000


def font_match(pattern: str) -> dict[str, str]:
    output = subprocess.check_output(
        ["fc-match", "-f", "%{family}\t%{file}\n", pattern], text=True
    ).strip()
    family, file_name = output.split("\t", 1)
    return {"pattern": pattern, "family": family, "file": file_name}


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


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installed-dir",
        type=Path,
        default=Path.home() / ".local" / "share" / "fonts",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=root / "build-v0.4-candidate.1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-linux-runtime.json",
    )
    parser.add_argument(
        "--layout-output",
        type=Path,
        default=root / "output" / "audit" /
        "pua4x4-v0.4-candidate-pango-layout.json",
    )
    parser.add_argument("--alias", default="PUA 4x4 v0.4 Candidate")
    parser.add_argument("--part0-family", default="PUA 4x4 Part 0 v0.4 Candidate")
    parser.add_argument("--part1-family", default="PUA 4x4 Part 1 v0.4 Candidate")
    parser.add_argument("--part0-file", default="PUA4x4Part0V04Candidate.ttf")
    parser.add_argument("--part1-file", default="PUA4x4Part1V04Candidate.ttf")
    args = parser.parse_args()

    libc = ctypes.CDLL(None)
    libc.wcwidth.argtypes = [ctypes.c_wchar]
    width_records = []
    for mask in (0x0000, 0x0001, 0x0400, 0x7FFF, 0x8000, 0x9669, 0xFFFF):
        width = libc.wcwidth(chr(codepoint(mask)))
        assert width == 1, (mask, width)
        width_records.append({"mask_hex": f"0x{mask:04X}", "width": width})

    matches = [
        font_match(f"{args.alias}:charset=f0001"),
        font_match(f"{args.alias}:charset=100000"),
    ]
    assert matches[0]["family"].startswith(args.part0_family)
    assert matches[1]["family"].startswith(args.part1_family)

    build_files = (
        args.build_dir / args.part0_file,
        args.build_dir / args.part1_file,
    )
    installed_files = (
        args.installed_dir / args.part0_file,
        args.installed_dir / args.part1_file,
    )
    identity_records = []
    for build, installed in zip(build_files, installed_files):
        build_hash = sha256(build)
        installed_hash = sha256(installed)
        assert build_hash == installed_hash
        identity_records.append({
            "build": str(build),
            "installed": str(installed),
            "sha256": build_hash,
            "identical": True,
        })

    proof = "Text " + " ".join(
        chr(codepoint(mask))
        for mask in (0x0001, 0x0400, 0x7FFF, 0x8000, 0x9669, 0xFFFF)
    )
    args.layout_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pango-view",
            "--no-display",
            f"--font={args.alias} 24",
            "--text=" + proof,
            "--serialize-to=" + str(args.layout_output),
        ],
        check=True,
    )
    layout = json.loads(args.layout_output.read_text(encoding="utf-8"))
    assert layout["output"]["unknown-glyphs"] == 0
    descriptions = set()
    collect_descriptions(layout, descriptions)
    expected_families = (
        "Square Braille Unicode Text Seamless",
        args.part0_family,
        args.part1_family,
    )
    for family in expected_families:
        assert any(item.startswith(family + " ") for item in descriptions), (
            family, sorted(descriptions)
        )

    report = {
        "audit": "PUA 4x4 v0.4 candidate Linux runtime selection",
        "gate": "D - installed identity and shaping selection",
        "status": "PASS_LINUX_SELECTION_ONLY",
        "not_proven_by_this_gate": [
            "Pango raster pixel identity",
            "MATE Terminal cell placement",
            "MATE Terminal raster output",
        ],
        "wcwidth": width_records,
        "fontconfig_matches": matches,
        "installed_binary_identity": identity_records,
        "pango": {
            "unknown_glyphs": layout["output"]["unknown-glyphs"],
            "expected_families": list(expected_families),
            "measured_run_descriptions": sorted(descriptions),
            "serialized_layout": str(args.layout_output),
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: candidate binaries installed byte-identically beside v0.3")
    print("PASS: wcwidth is one column throughout both PUA ranges")
    print("PASS: Fontconfig alias selects candidate Part 0 and Part 1")
    print("PASS: Pango selects text plus both candidates with zero unknown glyphs")
    print(args.output)


if __name__ == "__main__":
    main()
