#!/usr/bin/env python3
"""Convert NASA's official Voyager GLB into the demo's HLR mesh cache."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from render_previews import DEFAULT_MODEL, load_voyager_mesh


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "assets" / "voyager-vtad-hlr.npz"
DEFAULT_METADATA = HERE / "assets" / "voyager-vtad-source.json"
EXPECTED_SHA256 = "5338241f2e89e9cfe3ebb82f519b4cad64c97e66883cccba6fdda98667aec731"
SOURCE_PAGE = "https://science.nasa.gov/resource/voyager-3d-model/"
SOURCE_ASSET = "https://assets.science.nasa.gov/content/dam/science/psd/solar/2023/09/v/Voyager.glb"


def digest(path: Path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()
    actual = digest(args.source)
    if actual != EXPECTED_SHA256 and not args.allow_unverified:
        raise SystemExit(f"NASA model SHA-256 mismatch: {actual}")
    mesh = load_voyager_mesh(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **mesh)
    record = {
        "title": "Voyager 3D Model",
        "credit": "NASA Visualization Technology Applications and Development (VTAD)",
        "source_page": SOURCE_PAGE,
        "source_asset": SOURCE_ASSET,
        "source_sha256": actual,
        "source_format": "glTF Binary 2.0",
        "cache": args.output.name,
        "cache_vertices": int(len(mesh["vertices"])),
        "cache_triangles": int(len(mesh["faces"])),
        "cache_unique_edges": int(len(mesh["edges"])),
        "conversion": "world transform, normalization, coincident-position weld, topology and crease classification",
    }
    args.metadata.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
