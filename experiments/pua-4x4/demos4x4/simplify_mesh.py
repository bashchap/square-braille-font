#!/usr/bin/env python3
"""Deterministic vertex-cluster simplifier for renderer geometry NPZ files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--grid", type=int, default=180,
                        help="cluster divisions across the model's longest extent")
    args = parser.parse_args()
    if args.grid < 8:
        parser.error("--grid must be at least 8")

    raw = np.load(args.source, allow_pickle=False)
    vertices = raw["vertices"].astype(np.float64)
    faces = raw["faces"].astype(np.int32)
    groups = raw["groups"].astype(np.int32)
    names = raw["names"]
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    cell = float(np.max(hi - lo)) / args.grid
    keys = np.floor((vertices - lo) / cell + .5).astype(np.int32)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)

    counts = np.bincount(inverse)
    merged = np.column_stack([
        np.bincount(inverse, weights=vertices[:, axis]) / counts
        for axis in range(3)
    ])
    remapped = inverse[faces].astype(np.int32)
    good = ((remapped[:, 0] != remapped[:, 1]) &
            (remapped[:, 1] != remapped[:, 2]) &
            (remapped[:, 2] != remapped[:, 0]))
    remapped, groups = remapped[good], groups[good]

    # Remove coincident triangles within the same source object. Winding is
    # retained from the first occurrence so outward normals remain consistent.
    canonical = np.sort(remapped, axis=1)
    identity = np.column_stack((groups, canonical)).astype(np.int64)
    _, keep = np.unique(identity, axis=0, return_index=True)
    keep.sort()
    remapped, groups = remapped[keep], groups[keep]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, vertices=merged.astype(np.float32),
                        faces=remapped, groups=groups, names=names)
    print(f"grid={args.grid} cell={cell:.6g}")
    print(f"vertices {len(vertices):,} -> {len(merged):,}")
    print(f"triangles {len(faces):,} -> {len(remapped):,}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
