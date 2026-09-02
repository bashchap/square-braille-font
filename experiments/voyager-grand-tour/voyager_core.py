#!/usr/bin/env python3
"""Small dependency-light rendering core shared by preview and live demo."""

from __future__ import annotations

import math

import numpy as np


BRAILLE_BITS = np.array(((0, 3), (1, 4), (2, 5), (6, 7)), dtype=np.uint8)
PUA4_BITS = np.array(((3, 2, 1, 0), (7, 6, 5, 4),
                      (11, 10, 9, 8), (15, 14, 13, 12)), dtype=np.uint8)
MATERIAL_COLORS = np.array(((91, 238, 255), (255, 190, 65),
                            (174, 220, 242), (112, 175, 211),
                            (205, 242, 255)), dtype=np.uint8)


def normalize(vector):
    return vector / max(float(np.linalg.norm(vector)), 1.0e-12)


def pua4_codepoint(mask):
    """Map a 16-bit MSB-left mask across the Part 0/Part 1 split."""
    return 0xF0000 + mask if mask < 0x8000 else 0x100000 + (mask-0x8000)


def terminal_picture(masks, colors, mode):
    """Encode one mask/color framebuffer as terminal text and ANSI color."""
    rows, columns = masks.shape
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
                codepoint = 0x2800+mask if mode == 2 else pua4_codepoint(mask)
                pieces.append(chr(codepoint))
            else:
                if active is not None:
                    pieces.append("\x1b[39m")
                    active = None
                pieces.append(" ")
        lines.append("".join(pieces))
    if active is not None:
        lines[-1] += "\x1b[39m"
    return "\n".join(lines)


def raster_depth(depth, points, z, rgb=None, color=None):
    """Rasterize one triangle with perspective-correct inverse-Z depth."""
    height, width = depth.shape
    min_x = max(0, int(math.floor(float(points[:, 0].min()))))
    max_x = min(width - 1, int(math.ceil(float(points[:, 0].max()))))
    min_y = max(0, int(math.floor(float(points[:, 1].min()))))
    max_y = min(height - 1, int(math.ceil(float(points[:, 1].max()))))
    if min_x > max_x or min_y > max_y:
        return
    (x0, y0), (x1, y1), (x2, y2) = points
    denominator = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
    if abs(denominator) < 1.0e-12:
        return
    yy, xx = np.ogrid[min_y:max_y+1, min_x:max_x+1]
    px, py = xx+.5, yy+.5
    weight0 = ((y1-y2)*(px-x2) + (x2-x1)*(py-y2))/denominator
    weight1 = ((y2-y0)*(px-x2) + (x0-x2)*(py-y2))/denominator
    weight2 = 1.0-weight0-weight1
    inside = ((weight0 >= -.004) & (weight1 >= -.004) &
              (weight2 >= -.004))
    inverse = weight0/z[0] + weight1/z[1] + weight2/z[2]
    tile = depth[min_y:max_y+1, min_x:max_x+1]
    visible = inside & (inverse > tile)
    tile[visible] = inverse[visible]
    if rgb is not None and color is not None:
        color_tile = rgb[min_y:max_y+1, min_x:max_x+1]
        color_tile[visible] = color
