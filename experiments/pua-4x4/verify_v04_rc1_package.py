#!/usr/bin/env python3
"""Verify that the packaged v0.4 RC1 is exactly generated candidate.3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD = HERE / "build-v0.4-candidate.3-seamguard100"
PACKAGE = HERE.parents[1] / "fonts" / "candidates" / "pua-4x4-v0.4-rc1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    build_manifest = json.loads(
        (BUILD / "pua4x4-v0.4-candidate.3-manifest.json").read_text()
    )
    package_manifest = json.loads((PACKAGE / "manifest.json").read_text())
    if package_manifest != build_manifest:
        raise SystemExit("FAIL: packaged manifest differs from generated manifest")

    checksum_lines = {}
    for line in (PACKAGE / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        digest, filename = line.split(maxsplit=1)
        checksum_lines[filename.strip()] = digest

    for part in build_manifest["parts"]:
        filename = part["filename"]
        generated = BUILD / filename
        packaged = PACKAGE / filename
        generated_hash = sha256(generated)
        packaged_hash = sha256(packaged)
        expected_hash = part["sha256"]
        if generated.read_bytes() != packaged.read_bytes():
            raise SystemExit(f"FAIL: packaged bytes differ: {filename}")
        if len({generated_hash, packaged_hash, expected_hash}) != 1:
            raise SystemExit(f"FAIL: manifest/hash mismatch: {filename}")
        if checksum_lines.get(filename) != expected_hash:
            raise SystemExit(f"FAIL: SHA256SUMS mismatch: {filename}")
        print(f"PASS: {filename} {expected_hash}")

    print("PASS: packaged v0.4 RC1 is byte-identical to generated candidate.3")


if __name__ == "__main__":
    main()
