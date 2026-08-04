#!/usr/bin/env python3
"""High-detail, depth-buffered TOS Enterprise fly-around for PUA 4x4.

The mesh is generated procedurally so the demo is reproducible and can select
an appropriate geometric density for the terminal.  Every terminal character
addresses a 4 x 4 array of virtual pixels using PUA 4x4 Part 0/Part 1.
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image

from pua4x4_backend import DOT_WEIGHTS as WEIGHT_ROWS, mask_to_codepoint

DOT_WEIGHTS = np.array(WEIGHT_ROWS, dtype=np.uint16)
MATERIALS = np.array((
    (132, 158, 166),  # 0 hull
    (154, 178, 181),  # 1 light hull panel
    (80, 105, 114),   # 2 dark structural detail
    (30, 194, 215),   # 3 cyan edge/detail
    (218, 61, 43),    # 4 red
    (255, 144, 34),   # 5 orange
    (45, 145, 255),   # 6 deflector blue
    (240, 247, 229),  # 7 windows
    (30, 39, 44),     # 8 registry/dark marking
    (221, 184, 87),   # 9 gold
), dtype=np.float32)
EMISSIVE = np.array((False, False, False, False, True, True, True, True, False, True))


def normalize(vector):
    length = np.linalg.norm(vector)
    return vector / max(length, 1.0e-12)


def smoothstep(a, b, value):
    x = np.clip((value - a) / max(b - a, 1.0e-12), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def hash_unit(value):
    value = int(value) & 0xFFFFFFFF
    value = ((value ^ 61) ^ (value >> 16)) & 0xFFFFFFFF
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 4
    value = (value * 0x27D4EB2D) & 0xFFFFFFFF
    value ^= value >> 15
    return value / 4294967296.0


class MeshBuilder:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.materials = []

    def vertex(self, point):
        self.vertices.append(tuple(float(v) for v in point))
        return len(self.vertices) - 1

    def triangle(self, a, b, c, material=0):
        self.faces.append((a, b, c))
        self.materials.append(int(material))

    def quad(self, a, b, c, d, material=0):
        self.triangle(a, b, c, material)
        self.triangle(a, c, d, material)

    def arrays(self):
        vertices = np.asarray(self.vertices, dtype=np.float32)
        faces = np.asarray(self.faces, dtype=np.int32)
        materials = np.asarray(self.materials, dtype=np.int16)
        tri = vertices[faces]
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        normals /= np.maximum(lengths[:, None], 1.0e-12)
        return vertices, faces, materials, normals


def add_grid(builder, rows, columns, point_fn, material_fn, close_columns=True):
    grid = []
    for row in range(rows + 1):
        line = []
        for column in range(columns if close_columns else columns + 1):
            line.append(builder.vertex(point_fn(row / rows, column / columns)))
        grid.append(line)
    width = columns if close_columns else columns + 1
    for row in range(rows):
        for column in range(columns):
            nxt = (column + 1) % width
            material = material_fn(row, column)
            builder.quad(grid[row][column], grid[row][nxt],
                         grid[row + 1][nxt], grid[row + 1][column], material)


def add_ellipsoid_x(builder, center, radii, around, along, material=0,
                    material_fn=None):
    cx, cy, cz = center
    rx, ry, rz = radii

    def point(v, u):
        longitude = math.pi * v
        angle = math.tau * u
        ring = math.sin(longitude)
        return (cx + rx * math.cos(longitude),
                cy + ry * ring * math.cos(angle),
                cz + rz * ring * math.sin(angle))

    add_grid(builder, along, around, point,
             material_fn or (lambda _r, _c: material))


def add_ellipsoid_y(builder, center, radii, around, along, material=0,
                    upper_only=False):
    cx, cy, cz = center
    rx, ry, rz = radii
    latitude_end = math.pi / 2 if upper_only else math.pi

    def point(v, u):
        latitude = latitude_end * v
        angle = math.tau * u
        ring = math.sin(latitude)
        return (cx + rx * ring * math.cos(angle),
                cy + ry * math.cos(latitude),
                cz + rz * ring * math.sin(angle))

    add_grid(builder, along, around, point, lambda _r, _c: material)


def add_saucer(builder, segments, rings):
    cx, cy, radius = 3.1, 1.72, 5.05

    def surface(top):
        def point(v, u):
            r = radius * v
            angle = math.tau * u
            crown = (1.0 - v) ** 2
            height = .17 + .34 * crown if top else -.17 - .50 * crown
            return (cx + r * math.cos(angle), cy + height,
                    r * math.sin(angle))

        def material(row, column):
            if row >= rings - 2:
                return 1
            return (0, 1, 0, 0)[(column // max(1, segments // 32) + row) % 4]

        add_grid(builder, rings, segments, point, material)

    surface(True)
    surface(False)

    top = []
    bottom = []
    for index in range(segments):
        angle = math.tau * index / segments
        x, z = cx + radius * math.cos(angle), radius * math.sin(angle)
        top.append(builder.vertex((x, cy + .17, z)))
        bottom.append(builder.vertex((x, cy - .17, z)))
    for index in range(segments):
        nxt = (index + 1) % segments
        builder.quad(top[index], top[nxt], bottom[nxt], bottom[index], 2)


def add_cylinder_x(builder, x0, x1, center_y, center_z, radius_y, radius_z,
                   around, length_segments, material_fn):
    grid = []
    for along in range(length_segments + 1):
        x = x0 + (x1 - x0) * along / length_segments
        line = []
        for side in range(around):
            angle = math.tau * side / around
            line.append(builder.vertex((x,
                                        center_y + radius_y * math.cos(angle),
                                        center_z + radius_z * math.sin(angle))))
        grid.append(line)
    for along in range(length_segments):
        for side in range(around):
            nxt = (side + 1) % around
            builder.quad(grid[along][side], grid[along + 1][side],
                         grid[along + 1][nxt], grid[along][nxt],
                         material_fn(along, side))


def add_extruded_xy(builder, polygon, half_z, material):
    front = [builder.vertex((x, y, half_z)) for x, y in polygon]
    back = [builder.vertex((x, y, -half_z)) for x, y in polygon]
    for index in range(1, len(polygon) - 1):
        builder.triangle(front[0], front[index], front[index + 1], material)
        builder.triangle(back[0], back[index + 1], back[index], material)
    for index in range(len(polygon)):
        nxt = (index + 1) % len(polygon)
        builder.quad(front[index], back[index], back[nxt], front[nxt], material)


def add_beam(builder, start, end, width, material):
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    direction = normalize(end - start)
    reference = np.array((0.0, 1.0, 0.0))
    if abs(np.dot(direction, reference)) > .88:
        reference = np.array((1.0, 0.0, 0.0))
    side = normalize(np.cross(direction, reference)) * width * .5
    up = normalize(np.cross(side, direction)) * width * .5
    corners = []
    for point in (start, end):
        corners.append([builder.vertex(point + sx * side + sy * up)
                        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    builder.quad(*corners[0], material)
    builder.quad(corners[1][3], corners[1][2], corners[1][1], corners[1][0], material)
    for index in range(4):
        nxt = (index + 1) % 4
        builder.quad(corners[0][index], corners[1][index],
                     corners[1][nxt], corners[0][nxt], material)


def add_pylon(builder, side):
    inner0 = np.array((-3.5, .05, side * .78))
    inner1 = np.array((-1.2, .20, side * .78))
    outer0 = np.array((-3.9, 1.22, side * 3.18))
    outer1 = np.array((-1.6, 1.22, side * 3.18))
    thickness = .13
    vertices = []
    for offset in (-thickness, thickness):
        vertices.append([builder.vertex(point + np.array((0, offset, 0)))
                         for point in (inner0, inner1, outer1, outer0)])
    builder.quad(*vertices[0], 1)
    builder.quad(vertices[1][3], vertices[1][2], vertices[1][1], vertices[1][0], 0)
    for index in range(4):
        nxt = (index + 1) % 4
        builder.quad(vertices[0][index], vertices[1][index],
                     vertices[1][nxt], vertices[0][nxt], 2)


STROKES = {
    "N": (((0, 0), (0, 1)), ((0, 1), (1, 0)), ((1, 0), (1, 1))),
    "C": (((1, 0), (0, 0)), ((0, 0), (0, 1)), ((0, 1), (1, 1))),
    "1": (((.5, 0), (.5, 1)),),
    "7": (((0, 0), (1, 0)), ((1, 0), (.35, 1))),
    "0": (((0, 0), (1, 0)), ((1, 0), (1, 1)),
          ((1, 1), (0, 1)), ((0, 1), (0, 0))),
    "-": (((0, .5), (1, .5)),),
}


def add_registry(builder):
    text = "NCC-1701"
    scale_x, scale_z = .72, .39
    total = len(text) * (scale_z * 1.35)
    z_origin = -total / 2
    for index, character in enumerate(text):
        for (a, b) in STROKES[character]:
            p0 = (5.18 + (a[1] - .5) * scale_x, 2.07,
                  z_origin + index * scale_z * 1.35 + a[0] * scale_z)
            p1 = (5.18 + (b[1] - .5) * scale_x, 2.07,
                  z_origin + index * scale_z * 1.35 + b[0] * scale_z)
            add_beam(builder, p0, p1, .045, 8)


def build_enterprise(detail):
    builder = MeshBuilder()
    segments = 96 * detail
    rings = 14 * detail
    add_saucer(builder, segments, rings)
    add_ellipsoid_y(builder, (3.10, 2.05, 0), (1.28, .56, 1.28),
                    48 * detail, 9 * detail, 1, upper_only=True)
    add_ellipsoid_y(builder, (3.10, 1.42, 0), (.65, .48, .65),
                    36 * detail, 7 * detail, 3, upper_only=False)

    def hull_material(row, column):
        return 0 if (row + column // max(1, 8 * detail)) % 3 else 1

    add_ellipsoid_x(builder, (-2.45, -.32, 0), (3.55, 1.18, 1.35),
                    64 * detail, 22 * detail, material_fn=hull_material)
    add_extruded_xy(builder, ((-.7, .05), (1.65, 1.55), (2.28, 1.55),
                              (.05, -.05)), .32, 0)

    # Forward deflector dish, concentric coloured rings.
    dish_segments = 64 * detail
    dish_rings = 8 * detail
    def dish_point(v, u):
        radius = 1.02 * v
        angle = math.tau * u
        return (.96 - .36 * v * v, -.32 + radius * math.cos(angle),
                radius * math.sin(angle))
    add_grid(builder, dish_rings, dish_segments, dish_point,
             lambda row, _col: 6 if row < dish_rings * .72 else 9)
    add_beam(builder, (.88, -.32, 0), (1.42, -.32, 0), .13, 9)

    for side in (-1, 1):
        add_pylon(builder, side)
        z = side * 3.48
        add_cylinder_x(builder, -6.05, -.55, 1.28, z, .51, .56,
                       48 * detail, 18 * detail,
                       lambda along, ring: 1 if (along + ring // (6 * detail)) % 4 else 0)
        add_ellipsoid_x(builder, (-.48, 1.28, z), (.43, .50, .55),
                        48 * detail, 12 * detail, 4)
        add_ellipsoid_x(builder, (-6.08, 1.28, z), (.30, .50, .55),
                        40 * detail, 10 * detail, 2)
        add_beam(builder, (-5.6, 1.58, z + side * .34),
                 (-1.1, 1.58, z + side * .34), .09, 4)

    # Running lights and saucer windows are real geometry, not screen overlays.
    for index in range(40):
        angle = math.tau * index / 40
        center = (3.1 + 4.88 * math.cos(angle), 1.73,
                  4.88 * math.sin(angle))
        add_ellipsoid_x(builder, center, (.075, .045, .045), 6, 4, 7)
    for side in (-1, 1):
        add_ellipsoid_x(builder, (2.4, 1.94, side * 4.35),
                        (.11, .08, .08), 8, 5, 4 if side < 0 else 3)
    add_registry(builder)
    return builder.arrays()


def catmull_rom(points, t):
    count = len(points)
    position = (t % 1.0) * count
    index = int(position)
    u = position - index
    p0 = np.asarray(points[(index - 1) % count], dtype=float)
    p1 = np.asarray(points[index % count], dtype=float)
    p2 = np.asarray(points[(index + 1) % count], dtype=float)
    p3 = np.asarray(points[(index + 2) % count], dtype=float)
    return .5 * ((2 * p1) + (-p0 + p2) * u +
                 (2*p0 - 5*p1 + 4*p2 - p3) * u*u +
                 (-p0 + 3*p1 - 3*p2 + p3) * u*u*u)


CAMERA_POINTS = (
    (17, 5.5, 11), (10, -4.0, 13), (2, -1.3, 17),
    (-10, 2.5, 12), (-13, 4.2, 2), (-10, 1.0, -10),
    (-1, 5.0, -15), (8, 7.5, -11), (15, 1.2, -4),
    (10, -5.0, 4), (3, 8.5, 8), (-7, 5.0, 13),
)
TARGET_POINTS = (
    (2.2, .7, 0), (3.2, 1.3, 0), (0, .2, 0),
    (-1.8, .5, 0), (-2.8, .7, 0), (-2.0, .8, 0),
    (1.5, 1.4, 0), (3.5, 1.3, 0), (2.3, .7, 0),
    (.5, .1, 0), (3.2, 1.6, 0), (-.5, .7, 0),
)


def camera_at(timeline, duration):
    amount = (timeline % duration) / duration
    eye = catmull_rom(CAMERA_POINTS, amount)
    target = catmull_rom(TARGET_POINTS, amount)
    forward = normalize(target - eye)
    world_up = np.array((0.0, 1.0, 0.0))
    right = normalize(np.cross(forward, world_up))
    up = normalize(np.cross(right, forward))
    roll = math.sin(amount * math.tau * 3) * .06
    cr, sr = math.cos(roll), math.sin(roll)
    right, up = right * cr + up * sr, up * cr - right * sr
    return eye, np.stack((right, up, forward))


def stars_image(width, height, timeline):
    image = np.zeros((height, width, 3), dtype=np.uint8)
    count = max(120, min(2400, width * height // 280))
    for index in range(count):
        x = int((hash_unit(index * 2 + 0x9E3779B9) * width + timeline *
                 (.12 + hash_unit(index + 17) * .28)) % width)
        y = int(hash_unit(index * 2 + 0x85EBCA6B) * height)
        level = 65 + int(hash_unit(index + 0xC2B2AE35) * 150)
        image[y, x] = (level, level, min(255, level + 30))
    return image


def raster_triangle(rgb, inv_depth, points, depths, color):
    height, width = inv_depth.shape
    min_x = max(0, int(math.floor(np.min(points[:, 0]))))
    max_x = min(width - 1, int(math.ceil(np.max(points[:, 0]))))
    min_y = max(0, int(math.floor(np.min(points[:, 1]))))
    max_y = min(height - 1, int(math.ceil(np.max(points[:, 1]))))
    if min_x > max_x or min_y > max_y:
        return
    x0, y0 = points[0]
    x1, y1 = points[1]
    x2, y2 = points[2]
    denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denominator) < 1.0e-8:
        return
    yy, xx = np.ogrid[min_y:max_y + 1, min_x:max_x + 1]
    px, py = xx + .5, yy + .5
    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denominator
    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denominator
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -.001) & (w1 >= -.001) & (w2 >= -.001)
    if not np.any(inside):
        return
    inverse = w0 / depths[0] + w1 / depths[1] + w2 / depths[2]
    target = inv_depth[min_y:max_y + 1, min_x:max_x + 1]
    visible = inside & (inverse > target)
    if not np.any(visible):
        return
    target[visible] = inverse[visible]
    tile = rgb[min_y:max_y + 1, min_x:max_x + 1]
    tile[visible] = color


def enhance_visible_edges(rgb, inv_depth):
    occupied = inv_depth > 0
    edges = np.zeros_like(occupied)
    for axis in (0, 1):
        shifted = np.roll(occupied, 1, axis=axis)
        edges |= occupied & ~shifted
        shifted_depth = np.roll(inv_depth, 1, axis=axis)
        relative = np.abs(inv_depth - shifted_depth) / np.maximum(inv_depth, 1.0e-6)
        edges |= occupied & shifted & (relative > .075)
    if np.any(edges):
        original = rgb[edges].astype(np.uint16)
        edge_color = np.empty_like(original)
        edge_color[:, 0] = np.minimum(255, original[:, 0] + 22)
        edge_color[:, 1] = np.minimum(255, original[:, 1] + 74)
        edge_color[:, 2] = np.minimum(255, original[:, 2] + 82)
        rgb[edges] = edge_color.astype(np.uint8)


def render_frame(mesh, width, height, timeline, duration):
    vertices, faces, material_ids, normals = mesh
    rgb = stars_image(width, height, timeline)
    inv_depth = np.zeros((height, width), dtype=np.float32)
    eye, camera = camera_at(timeline, duration)
    camera_vertices = (vertices - eye) @ camera.T
    z = camera_vertices[:, 2]
    focal = min(width * 1.05, height * 1.68)
    projected = np.empty((len(vertices), 2), dtype=np.float32)
    safe_z = np.maximum(z, .08)
    projected[:, 0] = width / 2 + camera_vertices[:, 0] * focal / safe_z
    projected[:, 1] = height / 2 - camera_vertices[:, 1] * focal / safe_z

    tri_z = z[faces]
    valid = np.all(tri_z > .25, axis=1)
    tri_points = projected[faces]
    twice_area = ((tri_points[:, 1, 0] - tri_points[:, 0, 0]) *
                  (tri_points[:, 2, 1] - tri_points[:, 0, 1]) -
                  (tri_points[:, 1, 1] - tri_points[:, 0, 1]) *
                  (tri_points[:, 2, 0] - tri_points[:, 0, 0]))
    valid &= np.abs(twice_area) > .35
    valid &= np.max(tri_points[:, :, 0], axis=1) >= 0
    valid &= np.min(tri_points[:, :, 0], axis=1) < width
    valid &= np.max(tri_points[:, :, 1], axis=1) >= 0
    valid &= np.min(tri_points[:, :, 1], axis=1) < height
    indices = np.flatnonzero(valid)

    centers = vertices[faces].mean(axis=1)
    view = eye - centers
    view /= np.maximum(np.linalg.norm(view, axis=1)[:, None], 1.0e-8)
    light = normalize(np.array((.38, .82, .42)))
    diffuse = np.abs(normals @ light)
    rim = (1.0 - np.abs(np.sum(normals * view, axis=1))) ** 2
    factor = .32 + .68 * diffuse
    base = MATERIALS[material_ids]
    colors = base * factor[:, None]
    colors += rim[:, None] * np.array((12, 42, 48))
    colors[EMISSIVE[material_ids]] = base[EMISSIVE[material_ids]]
    colors = np.clip(colors, 0, 255).astype(np.uint8)

    # Large triangles first improves early depth rejection while preserving the
    # exact z-buffer result.  Subpixel triangles are intentionally discarded.
    indices = indices[np.argsort(-np.abs(twice_area[indices]))]
    for face_index in indices:
        raster_triangle(rgb, inv_depth, tri_points[face_index],
                        tri_z[face_index], colors[face_index])
    enhance_visible_edges(rgb, inv_depth)
    return rgb, inv_depth, len(indices)


def image_to_terminal(rgb, quantization=16):
    height, width, _ = rgb.shape
    rows, columns = height // 4, width // 4
    rgb = rgb[:rows * 4, :columns * 4]
    blocks = rgb.reshape(rows, 4, columns, 4, 3).transpose(0, 2, 1, 3, 4)
    occupied = np.any(blocks != 0, axis=4)
    masks = np.sum(occupied * DOT_WEIGHTS[None, None, :, :], axis=(2, 3)).astype(np.uint16)
    luminance = blocks[..., 0].astype(np.uint16) * 3 + blocks[..., 1].astype(np.uint16) * 6 + blocks[..., 2]
    luminance[~occupied] = 0
    flat_index = np.argmax(luminance.reshape(rows, columns, 16), axis=2)
    flat_colors = blocks.reshape(rows, columns, 16, 3)
    colors = np.take_along_axis(flat_colors, flat_index[..., None, None], axis=2)[:, :, 0]
    colors = (colors // quantization) * quantization

    lines = []
    active = None
    for row in range(rows):
        pieces = []
        for column in range(columns):
            mask = int(masks[row, column])
            if mask:
                color = tuple(int(value) for value in colors[row, column])
                if color != active:
                    pieces.append("\x1b[38;2;%d;%d;%dm" % color)
                    active = color
            elif active is not None:
                pieces.append("\x1b[39m")
                active = None
            pieces.append(chr(mask_to_codepoint(mask)))
        lines.append("".join(pieces))
    return "\n".join(lines)


def choose_detail(columns, rows, requested):
    if requested:
        return requested
    cells = columns * rows
    if cells < 60000:
        return 1
    if cells < 180000:
        return 2
    if cells < 750000:
        return 3
    if cells < 2000000:
        return 4
    return 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--frames", type=int, default=0,
                        help="render exactly this many deterministic frames")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--freeze-at", type=float)
    parser.add_argument("--hold", type=float, default=12.0)
    parser.add_argument("--capture", help="capture the configured terminal window")
    parser.add_argument("--png", help="write the rendered virtual-pixel image")
    parser.add_argument("--columns", type=int, help="force character columns")
    parser.add_argument("--rows", type=int, help="force character rows")
    parser.add_argument("--max-columns", type=int, default=320,
                        help="automatic safety cap; use 2048 to permit a 2048-column pane")
    parser.add_argument("--max-rows", type=int, default=160,
                        help="automatic safety cap; use 2048 to permit a 2048-row pane")
    parser.add_argument("--detail", type=int, choices=(1, 2, 3, 4, 5),
                        help="force mesh density; automatic by default")
    parser.add_argument("--quantization", type=int, choices=(8, 16, 32), default=16)
    args = parser.parse_args()
    if args.duration <= 0 or args.fps <= 0 or args.frames < 0 or args.hold < 0:
        parser.error("duration/fps must be positive; frames/hold must be non-negative")
    terminal = shutil.get_terminal_size((120, 36))
    columns = args.columns or min(terminal.columns, args.max_columns)
    rows = args.rows or min(max(12, terminal.lines), args.max_rows)
    columns, rows = max(40, columns), max(12, rows)
    detail = choose_detail(columns, rows, args.detail)
    mesh = build_enterprise(detail)

    def draw(timeline):
        rgb, _depth, triangles = render_frame(mesh, columns * 4, rows * 4,
                                               timeline, args.duration)
        if args.png:
            Image.fromarray(rgb, "RGB").save(args.png)
        picture = image_to_terminal(rgb, args.quantization)
        return picture, triangles

    sys.stdout.write("\x1b]0;PUA Enterprise NCC-1701 — Depth-Buffered Fly-Around\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    started = time.monotonic()
    frame_number = 0
    try:
        if args.freeze_at is not None:
            picture, _ = draw(args.freeze_at % args.duration)
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
        while True:
            if args.frames and frame_number >= args.frames:
                break
            elapsed = time.monotonic() - started
            if args.frames:
                elapsed = frame_number / args.fps
            elif args.once and elapsed >= args.duration:
                break
            picture, _ = draw(elapsed % args.duration)
            sys.stdout.write("\x1b[?2026h\x1b[H" + picture + "\x1b[?2026l")
            sys.stdout.flush()
            frame_number += 1
            delay = started + frame_number / args.fps - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
