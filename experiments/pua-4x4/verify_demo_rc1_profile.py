#!/usr/bin/env python3
"""Prove that the default demo launch path selects the packaged v0.5 RC1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROFILE_PATH = "/org/mate/terminal/profiles/pua4x4v05candidate4/"
EXPECTED_PROFILE = "PUA 4x4 v0.5 Candidate 4"
PARTS = (
    ("PUA4x4Part0V05Candidate4.ttf", "f0001", "PUA 4x4 Part 0 v0.5 Candidate 4"),
    ("PUA4x4Part1V05Candidate4.ttf", "100000", "PUA 4x4 Part 1 v0.5 Candidate 4"),
)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unquote_dconf(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def package_dir() -> Path:
    configured = os.environ.get("PUA4X4_CANDIDATE4_DIR")
    if configured:
        return Path(configured)
    packaged = ROOT.parents[1] / "fonts" / "candidates" / "pua-4x4-v0.5-rc1"
    if packaged.exists():
        return packaged
    return ROOT / "build-v0.5-candidate.4-strict"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/audit/pua4x4-v0.5-demo-launcher-profile.json",
    )
    args = parser.parse_args()

    default_launcher = (ROOT / "launch-linux.sh").read_text()
    demo_launcher = (ROOT / "demos4x4/run-demo.sh").read_text()
    assert "launch-linux-v05-candidate4.sh" in default_launcher
    assert "PUA4X4_USE_V04_RC1" in default_launcher
    assert "PUA4X4_USE_V03" in default_launcher
    assert f'PROFILE_NAME="{EXPECTED_PROFILE}"' in demo_launcher

    visible_name_raw = run("dconf", "read", f"{PROFILE_PATH}visible-name")
    font_raw = run("dconf", "read", f"{PROFILE_PATH}font")
    visible_name = unquote_dconf(visible_name_raw)
    font = unquote_dconf(font_raw)
    assert visible_name == EXPECTED_PROFILE, visible_name
    assert font.startswith(EXPECTED_PROFILE + " "), font

    source_dir = package_dir()
    installed_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "fonts"
    parts = []
    for filename, charset, expected_family in PARTS:
        source = source_dir / filename
        installed = installed_dir / filename
        source_hash = sha256(source)
        installed_hash = sha256(installed)
        assert source_hash == installed_hash, filename
        selected = run(
            "fc-match",
            "-f",
            "%{family}\t%{file}\n",
            f"{EXPECTED_PROFILE}:charset={charset}",
        )
        assert expected_family in selected, selected
        assert str(installed) in selected, selected
        parts.append(
            {
                "filename": filename,
                "charset_probe": charset,
                "expected_family": expected_family,
                "selected": selected,
                "source_sha256": source_hash,
                "installed_sha256": installed_hash,
            }
        )

    evidence = {
        "schema": "pua4x4-v0.5-demo-launcher-profile-v1",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "default_launcher": "launch-linux-v05-candidate4.sh",
        "legacy_routes": [
            "PUA4X4_USE_V04_RC1=1 -> launch-linux-v04-candidate3.sh",
            "PUA4X4_USE_V03=1 -> launch-linux-v03.sh"
        ],
        "demo_profile": visible_name,
        "profile_font": font,
        "package_dir": str(source_dir),
        "parts": parts,
        "result": "PASS",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"PASS: default demo profile is {visible_name!r}")
    print(f"PASS: profile font is {font!r}")
    print("PASS: installed P0/P1 bytes and Fontconfig selections match packaged RC1")
    print(args.output)


if __name__ == "__main__":
    main()
