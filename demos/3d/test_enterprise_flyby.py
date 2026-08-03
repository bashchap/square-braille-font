#!/usr/bin/env python3
"""Deterministic checks for the Enterprise mesh, z-buffer and PUA mapping."""

import numpy as np

import enterprise_flyby as demo


def test_mesh():
    vertices, faces, materials, normals = demo.build_enterprise(1)
    assert len(vertices) > 10000
    assert len(faces) > 20000
    assert faces.max() < len(vertices)
    assert len(materials) == len(faces) == len(normals)
    assert np.all(np.isfinite(vertices))
    assert np.ptp(vertices[:, 0]) > 10
    assert np.ptp(vertices[:, 2]) > 9


def test_depth_order():
    points = np.array(((3, 3), (14, 3), (8, 14)), dtype=np.float32)
    near = np.array((2., 2., 2.), dtype=np.float32)
    far = np.array((6., 6., 6.), dtype=np.float32)
    for order in (("far", "near"), ("near", "far")):
        rgb = np.zeros((18, 18, 3), dtype=np.uint8)
        depth = np.zeros((18, 18), dtype=np.float32)
        for layer in order:
            if layer == "near":
                demo.raster_triangle(rgb, depth, points, near, (0, 170, 255))
            else:
                demo.raster_triangle(rgb, depth, points, far, (255, 30, 0))
        assert tuple(rgb[8, 8]) == (0, 170, 255)


def test_render_and_pua():
    mesh = demo.build_enterprise(1)
    rgb, depth, triangles = demo.render_frame(mesh, 240, 144, 8, 60)
    assert triangles > 1000
    assert np.count_nonzero(depth) > 1500
    picture = demo.image_to_terminal(rgb)
    assert len(picture.splitlines()) == 36
    assert any(ord(character) > demo.PUA_START for character in picture
               if character not in "\n\x1b")


if __name__ == "__main__":
    test_mesh()
    test_depth_order()
    test_render_and_pua()
    print("PASS: mesh, hidden-surface depth, render, and PUA mapping")
