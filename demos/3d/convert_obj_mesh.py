#!/usr/bin/env python3
"""Convert a Wavefront OBJ mesh into the renderer's portable geometry NPZ.

The loader intentionally depends only on NumPy.  It accepts positive and
negative OBJ indices, triangulates polygon faces, preserves object/group names,
and ignores materials because the terminal renderer assigns its own palette.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def load_obj(path: Path):
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    groups: list[int] = []
    names = ["default"]
    group_ids = {"default": 0}
    current = 0

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if fields[0] == "v" and len(fields) >= 4:
                vertices.append(tuple(float(value) for value in fields[1:4]))
            elif fields[0] in {"o", "g"}:
                name = " ".join(fields[1:]).strip() or f"group_{len(names)}"
                if name not in group_ids:
                    group_ids[name] = len(names)
                    names.append(name)
                current = group_ids[name]
            elif fields[0] == "f" and len(fields) >= 4:
                polygon: list[int] = []
                for token in fields[1:]:
                    head = token.split("/", 1)[0]
                    if not head:
                        raise ValueError(f"missing vertex index at line {line_number}")
                    index = int(head)
                    index = index - 1 if index > 0 else len(vertices) + index
                    if not 0 <= index < len(vertices):
                        raise ValueError(f"vertex index out of range at line {line_number}")
                    polygon.append(index)
                for corner in range(1, len(polygon) - 1):
                    faces.append((polygon[0], polygon[corner], polygon[corner + 1]))
                    groups.append(current)

    if not vertices or not faces:
        raise ValueError("OBJ contains no usable triangle mesh")
    return (np.asarray(vertices, dtype=np.float64),
            np.asarray(faces, dtype=np.int32),
            np.asarray(groups, dtype=np.int32),
            np.asarray(names))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    vertices, faces, groups, names = load_obj(args.source)
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, vertices=vertices, faces=faces,
                        groups=groups, names=names)
    print(f"objects={len(names):,} vertices={len(vertices):,} triangles={len(faces):,}")
    print(f"bounds min={lo.tolist()} max={hi.tolist()} extent={(hi - lo).tolist()}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
