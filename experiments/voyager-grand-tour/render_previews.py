#!/usr/bin/env python3
"""Render matched Voyager preview frames through the real 2x4 and 4x4 fonts.

This is deliberately a preview generator, not the animation requested by the
user.  Both output images use the same NASA mesh, camera, scene coordinates,
hidden-line algorithm and terminal dimensions.  Only the virtual framebuffer
width and the final pixel-to-glyph encoder differ.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from voyager_core import (BRAILLE_BITS, MATERIAL_COLORS, PUA4_BITS, normalize,
                          pua4_codepoint, raster_depth)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "local-assets" / "nasa-voyager" / "Voyager.glb"
OUTPUT_DIR = ROOT / "outputs" / "voyager-grand-tour-previews"
FONT_2X4 = ROOT / "fonts" / "current" / "Square-Braille-Unicode-Text-Seamless.ttf"
FONT_4X4_P0 = ROOT / "fonts" / "candidates" / "pua-4x4-v0.4-rc1" / "PUA4x4Part0V04Candidate3.ttf"
FONT_4X4_P1 = ROOT / "fonts" / "candidates" / "pua-4x4-v0.4-rc1" / "PUA4x4Part1V04Candidate3.ttf"

COMPONENT_DTYPES = {
    5120: np.dtype("i1"), 5121: np.dtype("u1"),
    5122: np.dtype("<i2"), 5123: np.dtype("<u2"),
    5125: np.dtype("<u4"), 5126: np.dtype("<f4"),
}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
               "MAT2": 4, "MAT3": 9, "MAT4": 16}


def read_glb(path: Path):
    """Read the subset of glTF 2 needed by NASA's Voyager GLB."""
    with path.open("rb") as handle:
        magic, version, total = struct.unpack("<4sII", handle.read(12))
        if magic != b"glTF" or version != 2:
            raise ValueError(f"not a glTF 2 binary: {path}")
        chunks = {}
        while handle.tell() < total:
            length, kind = struct.unpack("<II", handle.read(8))
            chunks[kind] = handle.read(length)
    document = json.loads(chunks[0x4E4F534A].decode("utf-8"))
    return document, chunks[0x004E4942]


def accessor_array(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = COMPONENT_DTYPES[accessor["componentType"]]
    width = TYPE_WIDTHS[accessor["type"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    count = accessor["count"]
    if stride == dtype.itemsize * width:
        values = np.frombuffer(binary, dtype=dtype, count=count * width, offset=offset)
        return values.reshape(count, width) if width > 1 else values.copy()
    rows = np.ndarray((count, width), dtype=dtype, buffer=binary,
                      offset=offset, strides=(stride, dtype.itemsize))
    return rows.copy()


def quaternion_matrix(q):
    x, y, z, w = q
    length = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / length, y / length, z / length, w / length
    return np.array((
        (1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w, 0),
        (2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w, 0),
        (2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y, 0),
        (0, 0, 0, 1)), dtype=np.float64)


def node_matrix(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    translation = np.eye(4)
    translation[:3, 3] = node.get("translation", (0, 0, 0))
    rotation = quaternion_matrix(node.get("rotation", (0, 0, 0, 1)))
    scale = np.eye(4)
    scale[np.arange(3), np.arange(3)] = node.get("scale", (1, 1, 1))
    return translation @ rotation @ scale


def load_voyager_mesh(path: Path):
    document, binary = read_glb(path)
    vertices_out, faces_out, material_out = [], [], []

    def visit(node_index, parent):
        node = document["nodes"][node_index]
        world = parent @ node_matrix(node)
        if "mesh" in node:
            mesh = document["meshes"][node["mesh"]]
            for primitive in mesh["primitives"]:
                material = primitive.get("material", -1)
                material_name = (document.get("materials", [{}])[material].get("name", "")
                                 if material >= 0 else "")
                # The NASA file contains a transparent helper cube named clear.
                if material_name == "clear":
                    continue
                points = accessor_array(document, binary, primitive["attributes"]["POSITION"])
                hom = np.c_[points.astype(np.float64), np.ones(len(points))]
                points = (hom @ world.T)[:, :3]
                indices = accessor_array(document, binary, primitive["indices"]).reshape(-1, 3)
                base = sum(len(part) for part in vertices_out)
                vertices_out.append(points)
                faces_out.append(indices.astype(np.int32) + base)
                material_out.append(np.full(len(indices), material, dtype=np.int16))
        for child in node.get("children", ()):
            visit(child, world)

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    vertices = np.concatenate(vertices_out)
    faces = np.concatenate(faces_out)
    materials = np.concatenate(material_out)
    center = (vertices.min(0) + vertices.max(0)) * .5
    extent = float(np.max(vertices.max(0) - vertices.min(0)))
    vertices = (vertices - center) / extent
    return prepare_edges(vertices.astype(np.float32), faces, materials)


def prepare_edges(vertices, faces, materials, crease_degrees=23.0):
    # glTF commonly splits one geometric vertex at UV, normal and material
    # seams.  Hidden-line topology must use position-welded vertices or those
    # harmless splits are misclassified as thousands of open boundary edges.
    quantized = np.rint(vertices.astype(np.float64) * 10_000_000).astype(np.int64)
    _, first, inverse = np.unique(quantized, axis=0, return_index=True,
                                  return_inverse=True)
    vertices = vertices[first]
    faces = inverse[faces]
    nondegenerate = ((faces[:, 0] != faces[:, 1]) &
                     (faces[:, 1] != faces[:, 2]) &
                     (faces[:, 2] != faces[:, 0]))
    faces, materials = faces[nondegenerate], materials[nondegenerate]
    triangles = vertices[faces].astype(np.float64)
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    good = lengths > 1.0e-10
    faces, materials, normals, lengths = (faces[good], materials[good],
                                           normals[good], lengths[good])
    normals = normals / lengths[:, None]
    centers = vertices[faces].mean(1)
    edge_list = np.sort(np.concatenate((faces[:, (0, 1)], faces[:, (1, 2)],
                                        faces[:, (2, 0)])), axis=1)
    owners = np.tile(np.arange(len(faces), dtype=np.int32), 3)
    keys = edge_list[:, 0].astype(np.int64) * len(vertices) + edge_list[:, 1]
    order = np.argsort(keys, kind="stable")
    edge_list, owners, keys = edge_list[order], owners[order], keys[order]
    starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1]
    stops = np.r_[starts[1:], len(keys)]
    edges = edge_list[starts]
    face0 = owners[starts]
    face1 = np.full(len(starts), -1, dtype=np.int32)
    paired = stops - starts >= 2
    face1[paired] = owners[starts[paired] + 1]
    dot = np.ones(len(edges))
    dot[paired] = np.sum(normals[face0[paired]] * normals[face1[paired]], axis=1)
    crease = (~paired) | (np.abs(dot) < math.cos(math.radians(crease_degrees)))
    return dict(vertices=vertices, faces=faces, materials=materials,
                normals=normals, centers=centers, edges=edges,
                face0=face0, face1=face1, normal_dot=dot, crease=crease)


def draw_line(rgb, depth, p0, p1, z0, z1, color, tolerance=.025):
    height, width, _ = rgb.shape
    delta = p1 - p0
    steps = max(1, int(math.ceil(float(np.max(np.abs(delta))))))
    last = None
    for step in range(steps + 1):
        amount = step / steps
        x, y = np.rint(p0 + delta * amount).astype(int)
        if not (0 <= x < width and 0 <= y < height):
            continue
        inverse = (1.0 / z0) + ((1.0 / z1) - (1.0 / z0)) * amount
        if inverse + tolerance * max(inverse, depth[y, x]) < depth[y, x]:
            last = None
            continue
        rgb[y, x] = color
        if last is not None and x != last[0] and y != last[1]:
            if abs(delta[0]) >= abs(delta[1]):
                rgb[last[1], x] = color
            else:
                rgb[y, last[0]] = color
        last = (x, y)


def add_neptune_scene(rgb, seed=1977):
    """Add a stylized but dimensionally proportioned Neptune and Triton."""
    height, width, _ = rgb.shape
    rng = np.random.default_rng(seed)
    # Stars are defined over the full normalized screen, not a tunnel region.
    for u, v, b in rng.random((260, 3)):
        x, y = min(width-1, int(u*width)), min(height-1, int(v*height))
        level = int(70 + b*170)
        rgb[y, x] = (level, level, min(255, level+25))

    yy, xx = np.indices((height, width))
    u, v = (xx + .5) / width, (yy + .5) / height
    cx, cy = .79, .51
    rx, ry = .205, .315 * .9829  # Neptune polar/equatorial-radius ratio.
    radius = ((u-cx)/rx)**2 + ((v-cy)/ry)**2
    body = radius <= 1.0
    limb = np.clip(1.0 - radius, 0.0, 1.0) ** .28
    band = .82 + .12*np.cos((v-cy)/ry*18.0) + .035*np.cos((v-cy)/ry*51.0)
    light = np.clip((.43 + .57*limb) * band, 0, 1)
    rgb[body, 0] = (16 + 30*light[body]).astype(np.uint8)
    rgb[body, 1] = (62 + 92*light[body]).astype(np.uint8)
    rgb[body, 2] = (122 + 125*light[body]).astype(np.uint8)
    # Voyager-era Great Dark Spot, centred in Neptune's southern hemisphere.
    spot = (((u-(cx-.035))/(rx*.31))**2 + ((v-(cy+.085))/(ry*.12))**2) <= 1
    rgb[spot & body] = (13, 45, 101)
    cloud = (((u-(cx+.022))/(rx*.20))**2 + ((v-(cy+.025))/(ry*.025))**2) <= 1
    rgb[cloud & body] = (120, 202, 255)
    # Triton: small, pale and offset from Neptune.  It is not drawn to distance scale.
    triton = ((u-.535)/.018)**2 + ((v-.27)/.027)**2 <= 1
    rgb[triton] = (176, 184, 177)


def render_spacecraft(mesh, rgb, mode, eye=None, zoom=1.9,
                      style="wire", hidden_lines=True):
    height, width, _ = rgb.shape
    vertices, faces = mesh["vertices"], mesh["faces"]
    # A three-quarter view exposes the dish, bus, RTGs and long instrument booms.
    if eye is None:
        eye = np.array((0., -2., .8), dtype=np.float64)
    else:
        eye = np.asarray(eye, dtype=np.float64)
    target = np.array((0.0, .01, -.02), dtype=np.float64)
    forward = normalize(target-eye)
    right = normalize(np.cross(forward, np.array((0., 0., 1.))))
    up = normalize(np.cross(right, forward))
    camera = np.stack((right, up, forward))
    camera_vertices = (vertices-eye) @ camera.T
    z = camera_vertices[:, 2]
    q = camera_vertices[:, :2] / np.maximum(z[:, None], .05)
    finite = z > .05
    qmin, qmax = q[finite].min(0), q[finite].max(0)
    span = qmax-qmin
    # Fit in physical screen fractions, then convert to this mode's virtual pixels.
    target_w, target_h = .69*width, .81*height
    # A 2x4 subpixel is physically square in a 1:2 terminal cell.  A 4x4
    # subpixel is half as wide, so the 4x4 framebuffer needs twice as many
    # horizontal samples to represent the same physical projected distance.
    virtual_x_per_square_pixel = mode / 2.0
    scale = min(target_w/max(span[0]*virtual_x_per_square_pixel, 1e-9),
                target_h/max(span[1], 1e-9))
    # This preview is a close fly-by shot: centre the dense spacecraft bus and
    # allow the very long booms to leave the frame.  The final animation will
    # also include full-craft establishing shots.
    qcenter = np.median(q[finite], axis=0)
    projected = np.empty_like(q)
    projected[:, 0] = ((q[:, 0]-qcenter[0])*scale*zoom *
                       virtual_x_per_square_pixel + width*.38)
    projected[:, 1] = -(q[:, 1]-qcenter[1])*scale*zoom + height*.55

    depth = np.zeros((height, width), dtype=np.float32)
    tri_z, tri_p = z[faces], projected[faces]
    area = np.abs((tri_p[:,1,0]-tri_p[:,0,0])*(tri_p[:,2,1]-tri_p[:,0,1]) -
                  (tri_p[:,1,1]-tri_p[:,0,1])*(tri_p[:,2,0]-tri_p[:,0,0]))
    valid = np.all(tri_z > .05, axis=1) & (area > .02)
    face_indices = np.flatnonzero(valid)[np.argsort(-area[valid])]
    if hidden_lines or style == "filled":
        light_direction = normalize(np.array((-.35, -.25, 1.0)))
        for index in face_indices:
            if style == "filled":
                material = int(mesh["materials"][index])
                base = MATERIAL_COLORS[material % len(MATERIAL_COLORS)].astype(float)
                diffuse = abs(float(np.dot(mesh["normals"][index], light_direction)))
                color = np.clip(base * (.32 + .68*diffuse), 0, 255).astype(np.uint8)
            else:
                color = None
            raster_depth(depth, tri_p[index], tri_z[index],
                         rgb if style == "filled" else None, color)

    facing = np.sum(mesh["normals"] * (eye-mesh["centers"]), axis=1)
    paired = mesh["face1"] >= 0
    second = np.zeros(len(mesh["edges"]))
    second[paired] = facing[mesh["face1"][paired]] * np.where(
        mesh["normal_dot"][paired] < 0, -1.0, 1.0)
    silhouette = paired & (facing[mesh["face0"]] * second <= 0)
    if style == "filled":
        selected = silhouette | (mesh["face1"] < 0)
    else:
        selected = mesh["crease"] | silhouette
    edge_z = z[mesh["edges"]]
    selected &= np.all(edge_z > .05, axis=1)
    edge_p = projected[mesh["edges"]]
    selected &= np.max(np.abs(edge_p[:, 1]-edge_p[:, 0]), axis=1) >= .7
    indices = np.flatnonzero(selected)
    indices = indices[np.argsort(-edge_z[indices].mean(1))]
    for index in indices:
        owner = mesh["face0"][index]
        material = int(mesh["materials"][owner])
        color = (np.array((218, 247, 255), dtype=np.uint8) if style == "filled"
                 else MATERIAL_COLORS[material % len(MATERIAL_COLORS)])
        draw_line(rgb, depth, edge_p[index,0], edge_p[index,1],
                  edge_z[index,0], edge_z[index,1], color)
    return len(face_indices), len(indices)


def encode_cells(rgb, mode):
    height, width, _ = rgb.shape
    sx = mode
    bits = BRAILLE_BITS if mode == 2 else PUA4_BITS
    rows, columns = height//4, width//sx
    cells = []
    for row in range(rows):
        output_row = []
        for column in range(columns):
            block = rgb[row*4:(row+1)*4, column*sx:(column+1)*sx]
            occupied = np.any(block != 0, axis=2)
            mask = 0
            for ly in range(4):
                for lx in range(sx):
                    if occupied[ly, lx]:
                        mask |= 1 << int(bits[ly, lx])
            if mask:
                colors = block[occupied]
                # One ANSI foreground per terminal cell; use the brightest source pixel.
                pick = np.argmax(colors[:,0]*3 + colors[:,1]*6 + colors[:,2])
                color = tuple(int(value) for value in colors[pick])
            else:
                color = (0, 0, 0)
            cp = 0x2800 + mask if mode == 2 else pua4_codepoint(mask)
            output_row.append((cp, color))
        cells.append(output_row)
    return cells


def render_font_cells(cells, mode, output, style, hidden_lines, font_size=24):
    font_paths = ((FONT_2X4,) if mode == 2 else (FONT_4X4_P0, FONT_4X4_P1))
    fonts = tuple(ImageFont.truetype(str(path), font_size) for path in font_paths)
    cell_w = int(round(fonts[0].getlength("M")))
    cell_h = font_size
    rows, columns = len(cells), len(cells[0])
    image = Image.new("RGB", (columns*cell_w, rows*cell_h), "black")
    for row, values in enumerate(cells):
        for column, (cp, color) in enumerate(values):
            if color == (0, 0, 0):
                continue
            font = fonts[0] if mode == 2 or cp < 0x100000 else fonts[1]
            # Crop every font raster to its terminal cell, like a terminal renderer.
            mask = Image.new("L", (cell_w, cell_h), 0)
            draw = ImageDraw.Draw(mask)
            draw.text((0, fonts[0].getmetrics()[0]), chr(cp), font=font,
                      fill=255, anchor="ls")
            tile = Image.new("RGB", (cell_w, cell_h), color)
            image.paste(tile, (column*cell_w, row*cell_h), mask)
    label_font = ImageFont.load_default(size=17)
    draw = ImageDraw.Draw(image)
    title = ("-2  SQUARE BRAILLE 2x4  |  " if mode == 2 else
             "-4  PUA 4x4 v0.4 RC1  |  ")
    title += (f"{style.upper()}  HLR {'ON' if hidden_lines else 'OFF'}  |  "
              f"{columns}x{rows} cells = {columns*mode}x{rows*4} virtual pixels")
    draw.rectangle((0, 0, min(image.width, 850), 25), fill=(0, 0, 0))
    draw.text((8, 5), title, font=label_font, fill=(225, 240, 255))
    image.save(output)


def render_mode(mesh, mode, columns, rows, style, hidden_lines, output):
    rgb = np.zeros((rows*4, columns*mode, 3), dtype=np.uint8)
    add_neptune_scene(rgb)
    faces, edges = render_spacecraft(mesh, rgb, mode, style=style,
                                     hidden_lines=hidden_lines)
    render_font_cells(encode_cells(rgb, mode), mode, output, style, hidden_lines)
    print(f"-{mode} {style} HLR={'on' if hidden_lines else 'off'}: "
          f"{columns*mode}x{rows*4} virtual pixels, {faces:,} faces, "
          f"{edges:,} candidate edges -> {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--columns", type=int, default=120)
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--styles", nargs="+", choices=("wire", "filled"),
                        default=("wire", "filled"))
    parser.add_argument("--no-hlr", action="store_true",
                        help="do not depth-test wireframe edges")
    args = parser.parse_args()
    if not args.model.exists():
        raise SystemExit(f"NASA Voyager model not found: {args.model}")
    for path in (FONT_2X4, FONT_4X4_P0, FONT_4X4_P1):
        if not path.exists():
            raise SystemExit(f"font not found: {path}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mesh = load_voyager_mesh(args.model)
    for style in args.styles:
        hidden_lines = not args.no_hlr or style == "filled"
        suffix = "hlr" if hidden_lines else "no-hlr"
        for mode in (2, 4):
            render_mode(mesh, mode, args.columns, args.rows, style, hidden_lines,
                        OUTPUT_DIR / f"voyager-neptune-{mode}x4-{style}-{suffix}-font-preview.png")


if __name__ == "__main__":
    main()
