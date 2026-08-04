#!/usr/bin/env python3
"""High-detail TOS Enterprise wireframe with depth-buffer hidden-line removal.

The renderer consumes a preprocessed NPZ mesh.  It first rasterizes the complete
triangle surface into a depth buffer, then admits only boundary, crease and
silhouette edge pixels whose perspective-correct depth matches that surface.
Each resulting screen pixel is encoded through PUA 4x4 Part 0/Part 1.

TOS Enterprise model: Raul Mamoru — source: trekmeshes.eu
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from pua4x4_backend import DOT_WEIGHTS as WEIGHT_ROWS, mask_to_codepoint

DOT_WEIGHTS = np.array(WEIGHT_ROWS, dtype=np.uint16)
DEMO_TITLE = "PUA Enterprise — True Hidden-Line Wireframe"


def normalize(v):
    return v / max(float(np.linalg.norm(v)), 1.0e-12)


def prepare_mesh(source: Path, output: Path, crease_degrees: float = 24.0):
    raw = np.load(source, allow_pickle=False)
    vertices = raw["vertices"].astype(np.float64)
    faces = raw["faces"].astype(np.int32)
    groups = raw["groups"].astype(np.int32)
    names = raw["names"]
    center = (vertices.min(axis=0) + vertices.max(axis=0)) * .5
    scale = float(np.max(vertices.max(axis=0) - vertices.min(axis=0))) * .5
    vertices = ((vertices - center) / scale).astype(np.float32)

    triangles = vertices[faces].astype(np.float64)
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    good = lengths > 1.0e-11
    if not np.all(good):
        faces, groups, normals, lengths = faces[good], groups[good], normals[good], lengths[good]
    normals = (normals / lengths[:, None]).astype(np.float32)
    centers = vertices[faces].mean(axis=1).astype(np.float32)

    all_edges = np.sort(np.concatenate((faces[:, (0, 1)], faces[:, (1, 2)],
                                        faces[:, (2, 0)]), axis=0), axis=1)
    owners = np.tile(np.arange(len(faces), dtype=np.int32), 3)
    key = all_edges[:, 0].astype(np.int64) * len(vertices) + all_edges[:, 1]
    order = np.argsort(key, kind="stable")
    all_edges, owners, key = all_edges[order], owners[order], key[order]
    starts = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1]
    stops = np.r_[starts[1:], len(key)]
    edges = all_edges[starts]
    face0 = owners[starts]
    face1 = np.full(len(starts), -1, dtype=np.int32)
    paired = stops - starts >= 2
    face1[paired] = owners[starts[paired] + 1]
    normal_dot = np.ones(len(edges), dtype=np.float32)
    normal_dot[paired] = np.sum(normals[face0[paired]] * normals[face1[paired]], axis=1)
    crease = (~paired) | (np.abs(normal_dot) < math.cos(math.radians(crease_degrees)))

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, vertices=vertices, faces=faces, groups=groups,
                        names=names, normals=normals, centers=centers,
                        edges=edges.astype(np.int32), face0=face0, face1=face1,
                        normal_dot=normal_dot, crease=crease)
    print(f"prepared {len(vertices):,} vertices, {len(faces):,} triangles, "
          f"{len(edges):,} unique edges -> {output}")


def camera_at(t, duration):
    a = (t % duration) / duration * math.tau
    # Ship length is along Y and height along Z.  Unequal frequencies make the
    # path a genuine fly-around rather than a turntable rotation.
    distance = 1.82 + .23 * math.sin(a * 3.0 + .4)
    eye = np.array((distance * math.cos(a), (distance + .16) * math.sin(a),
                    .50 + .52 * math.sin(a * 2.0 + .35)), dtype=np.float64)
    target = np.array((.10 * math.sin(a * 1.7), -.08 * math.cos(a),
                       .02 + .08 * math.sin(a * 2.3)), dtype=np.float64)
    forward = normalize(target - eye)
    right = normalize(np.cross(forward, np.array((0.0, 0.0, 1.0))))
    up = normalize(np.cross(right, forward))
    roll = .055 * math.sin(a * 3.0)
    cr, sr = math.cos(roll), math.sin(roll)
    right, up = right * cr + up * sr, up * cr - right * sr
    return eye, np.stack((right, up, forward))


def raster_depth(depth, points, z):
    height, width = depth.shape
    min_x = max(0, int(math.floor(float(points[:, 0].min()))))
    max_x = min(width - 1, int(math.ceil(float(points[:, 0].max()))))
    min_y = max(0, int(math.floor(float(points[:, 1].min()))))
    max_y = min(height - 1, int(math.ceil(float(points[:, 1].max()))))
    if min_x > max_x or min_y > max_y:
        return
    (x0, y0), (x1, y1), (x2, y2) = points
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1.0e-10:
        return
    yy, xx = np.ogrid[min_y:max_y + 1, min_x:max_x + 1]
    px, py = xx + .5, yy + .5
    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -.002) & (w1 >= -.002) & (w2 >= -.002)
    inverse = w0 / z[0] + w1 / z[1] + w2 / z[2]
    tile = depth[min_y:max_y + 1, min_x:max_x + 1]
    visible = inside & (inverse > tile)
    tile[visible] = inverse[visible]


PALETTE = np.array(((74, 235, 255), (168, 224, 255), (82, 154, 255),
                    (255, 181, 67), (255, 100, 72), (150, 255, 202)), dtype=np.uint8)


def line_hidden(rgb, depth, p0, p1, z0, z1, color, depth_scale, tolerance):
    height, width, _ = rgb.shape
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    dx, dy = x1 - x0, y1 - y0
    steps = max(1, int(math.ceil(max(abs(dx), abs(dy)))))
    inv0, inv1 = 1.0 / z0, 1.0 / z1
    last = None
    for step in range(steps + 1):
        amount = step / steps
        x = int(round(x0 + dx * amount))
        y = int(round(y0 + dy * amount))
        if not (0 <= x < width and 0 <= y < height):
            continue
        inverse = inv0 + (inv1 - inv0) * amount
        sample = depth[min(depth.shape[0] - 1, y // depth_scale),
                       min(depth.shape[1] - 1, x // depth_scale)]
        if inverse + tolerance * max(inverse, sample) < sample:
            last = None
            continue
        rgb[y, x] = color
        if last is not None and x != last[0] and y != last[1]:
            # Four-connected bridge: prevents corner pinholes in square pixels.
            if abs(dx) >= abs(dy):
                rgb[last[1], x] = color
            else:
                rgb[y, last[0]] = color
        last = (x, y)


def render(mesh, width, height, t, duration, depth_scale=2,
           min_area=.025, tolerance=.018, all_edges=False):
    vertices, faces = mesh["vertices"], mesh["faces"]
    normals, centers = mesh["normals"], mesh["centers"]
    edges, face0, face1 = mesh["edges"], mesh["face0"], mesh["face1"]
    eye, camera = camera_at(t, duration)
    camera_vertices = (vertices - eye) @ camera.T
    z = camera_vertices[:, 2]
    focal = min(width * .82, height * 1.10)
    projected = np.empty((len(vertices), 2), dtype=np.float32)
    safe = np.maximum(z, .05)
    projected[:, 0] = width * .5 + camera_vertices[:, 0] * focal / safe
    projected[:, 1] = height * .5 - camera_vertices[:, 1] * focal / safe

    ds = max(1, depth_scale)
    depth = np.zeros(((height + ds - 1) // ds, (width + ds - 1) // ds), dtype=np.float32)
    dp = projected / ds
    tri_z = z[faces]
    tri_p = dp[faces]
    area = np.abs((tri_p[:, 1, 0] - tri_p[:, 0, 0]) * (tri_p[:, 2, 1] - tri_p[:, 0, 1]) -
                  (tri_p[:, 1, 1] - tri_p[:, 0, 1]) * (tri_p[:, 2, 0] - tri_p[:, 0, 0]))
    valid = np.all(tri_z > .12, axis=1) & (area >= min_area)
    valid &= np.max(tri_p[:, :, 0], axis=1) >= 0
    valid &= np.min(tri_p[:, :, 0], axis=1) < depth.shape[1]
    valid &= np.max(tri_p[:, :, 1], axis=1) >= 0
    valid &= np.min(tri_p[:, :, 1], axis=1) < depth.shape[0]
    face_indices = np.flatnonzero(valid)
    face_indices = face_indices[np.argsort(-area[face_indices])]
    for index in face_indices:
        raster_depth(depth, tri_p[index], tri_z[index])

    view = eye - centers
    facing = np.sum(normals * view, axis=1)
    paired = face1 >= 0
    aligned_second = np.zeros(len(edges), dtype=np.float32)
    aligned_second[paired] = facing[face1[paired]] * np.where(
        mesh["normal_dot"][paired] < 0, -1.0, 1.0)
    silhouette = paired & ((facing[face0] * aligned_second) <= 0)
    selected = np.ones(len(edges), dtype=bool) if all_edges else (mesh["crease"] | silhouette)
    edge_z = z[edges]
    selected &= np.all(edge_z > .12, axis=1)
    edge_p = projected[edges]
    selected &= np.max(edge_p[:, :, 0], axis=1) >= -1
    selected &= np.min(edge_p[:, :, 0], axis=1) <= width
    selected &= np.max(edge_p[:, :, 1], axis=1) >= -1
    selected &= np.min(edge_p[:, :, 1], axis=1) <= height
    length = np.max(np.abs(edge_p[:, 1] - edge_p[:, 0]), axis=1)
    selected &= length >= .65

    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    edge_indices = np.flatnonzero(selected)
    # Far edges first; exact per-pixel depth testing determines final visibility.
    edge_indices = edge_indices[np.argsort(-edge_z[edge_indices].mean(axis=1))]
    groups = mesh["groups"]
    for index in edge_indices:
        owner = face0[index]
        group = int(groups[owner])
        color = PALETTE[group % len(PALETTE)].copy()
        brightness = .58 + .42 * min(1.0, 1.0 / max(.55, edge_z[index].mean() - .35))
        color = np.clip(color.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
        line_hidden(rgb, depth, edge_p[index, 0], edge_p[index, 1],
                    edge_z[index, 0], edge_z[index, 1], color, ds, tolerance)

    return rgb, len(face_indices), len(edge_indices)


def image_to_terminal(rgb, quantization=16):
    height, width, _ = rgb.shape
    rows, columns = height // 4, width // 4
    blocks = rgb[:rows * 4, :columns * 4].reshape(rows, 4, columns, 4, 3).transpose(0, 2, 1, 3, 4)
    occupied = np.any(blocks != 0, axis=4)
    masks = np.sum(occupied * DOT_WEIGHTS[None, None, :, :], axis=(2, 3)).astype(np.uint16)
    light = blocks[..., 0].astype(np.uint16) * 3 + blocks[..., 1].astype(np.uint16) * 6 + blocks[..., 2]
    light[~occupied] = 0
    pick = np.argmax(light.reshape(rows, columns, 16), axis=2)
    colors = np.take_along_axis(blocks.reshape(rows, columns, 16, 3), pick[..., None, None], axis=2)[:, :, 0]
    colors = (colors // quantization) * quantization
    lines, active = [], None
    for row in range(rows):
        pieces = []
        for column in range(columns):
            mask = int(masks[row, column])
            if mask:
                color = tuple(int(v) for v in colors[row, column])
                if color != active:
                    pieces.append("\x1b[38;2;%d;%d;%dm" % color)
                    active = color
            elif active is not None:
                pieces.append("\x1b[39m")
                active = None
            pieces.append(chr(mask_to_codepoint(mask)))
        lines.append("".join(pieces))
    return "\n".join(lines)


def ansi_frame(picture):
    """Return a self-contained terminal frame suitable for `cat frame.ansi`."""
    return "\x1b[0m\x1b[2J\x1b[H" + picture + "\x1b[0m\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mesh", type=Path, default=Path(__file__).with_name("enterprise_tos_wire.npz"))
    ap.add_argument("--prepare-from", type=Path, help="prepare renderer cache from converted geometry NPZ")
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--freeze-at", type=float)
    ap.add_argument("--hold", type=float, default=12.0)
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--record-dir", type=Path,
                    help="write each rendered frame as a self-contained UTF-8 ANSI text file")
    ap.add_argument("--record-only", action="store_true",
                    help="render files as fast as possible without displaying or timing playback")
    ap.add_argument("--png")
    ap.add_argument("--capture")
    ap.add_argument("--columns", type=int)
    ap.add_argument("--rows", type=int)
    ap.add_argument("--max-columns", type=int, default=320)
    ap.add_argument("--max-rows", type=int, default=160)
    ap.add_argument("--depth-scale", type=int, default=3, choices=(1, 2, 3, 4))
    ap.add_argument("--min-area", type=float, default=.04)
    ap.add_argument("--depth-tolerance", type=float, default=.018)
    ap.add_argument("--all-edges", action="store_true")
    ap.add_argument("--quantization", type=int, default=16, choices=(8, 16, 32))
    args = ap.parse_args()
    if args.prepare_from:
        prepare_mesh(args.prepare_from, args.mesh)
        return
    if not args.mesh.exists():
        raise SystemExit(f"mesh cache not found: {args.mesh}")
    if args.record_only and not args.record_dir:
        ap.error("--record-only requires --record-dir")
    if args.record_only and not args.frames and args.freeze_at is None:
        ap.error("--record-only requires --frames or --freeze-at")
    if args.record_dir:
        args.record_dir.mkdir(parents=True, exist_ok=True)
    terminal = shutil.get_terminal_size((120, 36))
    columns = max(40, args.columns or min(terminal.columns, args.max_columns))
    rows = max(12, args.rows or min(terminal.lines, args.max_rows))
    mesh_file = np.load(args.mesh, allow_pickle=False)

    def make_frame(timeline):
        rgb, triangles, edges = render(mesh_file, columns * 4, rows * 4, timeline,
                                       args.duration, args.depth_scale, args.min_area,
                                       args.depth_tolerance, args.all_edges)
        if args.png:
            Image.fromarray(rgb).save(args.png)
        return image_to_terminal(rgb, args.quantization), triangles, edges

    if not args.record_only:
        sys.stdout.write(f"\x1b]0;{DEMO_TITLE}\x07"
                         "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
        sys.stdout.flush()
    started, frame = time.monotonic(), 0
    recorded_count = 0
    try:
        if args.freeze_at is not None:
            picture, _, _ = make_frame(args.freeze_at % args.duration)
            if args.record_dir:
                path = args.record_dir / f"frame_000000_t{args.freeze_at % args.duration:07.3f}.ansi"
                path.write_text(ansi_frame(picture), encoding="utf-8")
                recorded_count = 1
                if args.record_only:
                    print(path)
            if not args.record_only:
                sys.stdout.write("\x1b[?2026h\x1b[H" + picture + "\x1b[?2026l")
                sys.stdout.flush()
            if args.capture:
                time.sleep(.8)
                window_id = os.environ.get("WINDOWID")
                if not window_id:
                    raise SystemExit("MATE Terminal did not provide WINDOWID")
                subprocess.run(("import", "-window", window_id, args.capture), check=True)
            time.sleep(args.hold)
            return
        while not args.frames or frame < args.frames:
            elapsed = frame / args.fps if args.frames else time.monotonic() - started
            if args.once and elapsed >= args.duration:
                break
            picture, _, _ = make_frame(elapsed % args.duration)
            if args.record_dir:
                path = args.record_dir / f"frame_{frame:06d}.ansi"
                path.write_text(ansi_frame(picture), encoding="utf-8")
                recorded_count += 1
                if args.record_only:
                    print(path)
            if not args.record_only:
                sys.stdout.write("\x1b[?2026h\x1b[H" + picture + "\x1b[?2026l")
                sys.stdout.flush()
            frame += 1
            if not args.record_only:
                delay = started + frame / args.fps - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        if args.record_dir:
            manifest = {
                "format": "pua-ansi-frame-sequence-v1",
                "fps": args.fps,
                "duration": args.duration,
                "frames": recorded_count,
                "columns": columns,
                "rows": rows,
                "mesh": str(args.mesh),
                "frame_pattern": "frame_*.ansi",
            }
            (args.record_dir / "recording.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if not args.record_only:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
