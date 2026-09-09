#!/usr/bin/env python3
"""Seasonal layered snowfall for Square Braille 2x4 and PUA 4x4 fonts.

The renderer emits one glyph with a foreground colour and, when it improves
whole-cell reconstruction, a second visible depth as the terminal background.
It does not use reverse video or treat a full mask as a terminal background.
Complete-frame rendering restores lower-priority scenery after moving objects.
"""

import argparse
import contextlib
import functools
import io
import json
import math
import os
import random
import re
import shutil
import signal
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import resource
except ImportError:  # Windows does not provide the Unix resource module.
    resource = None


RESET = "\x1b[0m"
FG_DEFAULT = "\x1b[39m"

SQUARE_BITS = (
    (0, 3),
    (1, 4),
    (2, 5),
    (6, 7),
)

PUA4_BITS = (
    (3, 2, 1, 0),
    (7, 6, 5, 4),
    (11, 10, 9, 8),
    (15, 14, 13, 12),
)

SHAPES = {
    "tiny": ((0, 0),),
    "small": ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)),
    "medium": (
        (0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
    ),
    "large": (
        (0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0),
        (0, -1), (0, 1), (0, -2), (0, 2),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
        (-2, -1), (2, -1), (-2, 1), (2, 1),
        (-1, -2), (1, -2), (-1, 2), (1, 2),
    ),
}

PALETTES = {
    "winter": {
        "snow": ((236, 250, 255), (164, 224, 255), (102, 188, 255), (205, 184, 255)),
        "bank": ((244, 252, 255), (188, 225, 255), (112, 169, 232)),
    },
    "christmas": {
        "snow": ((255, 255, 255), (178, 236, 255), (108, 198, 240), (226, 196, 255)),
        "bank": ((250, 255, 255), (191, 231, 247), (111, 174, 216)),
    },
    "aurora": {
        "snow": ((236, 255, 250), (112, 255, 224), (103, 204, 255), (204, 142, 255)),
        "bank": ((226, 255, 249), (137, 226, 221), (91, 154, 207)),
    },
    "monochrome": {
        "snow": ((255, 255, 255), (220, 220, 220), (184, 184, 184), (240, 240, 240)),
        "bank": ((248, 248, 248), (207, 207, 207), (150, 150, 150)),
    },
}


@dataclass(frozen=True)
class CellCodec:
    name: str
    cell_width: int
    cell_height: int
    bits: tuple

    def codepoint(self, mask):
        if self.name == "square":
            return 0x2800 + mask
        if mask < 0x8000:
            return 0xF0000 + mask
        return 0x100000 + mask - 0x8000


CODECS = {
    "square": CellCodec("square", 2, 4, SQUARE_BITS),
    "pua4": CellCodec("pua4", 4, 4, PUA4_BITS),
}


@dataclass(frozen=True)
class TreeSettings:
    branches: int
    branch_levels: int
    branch_angle: float
    length_ratio: float
    trunk_thickness: float
    thickness_exponent: float


class Surface:
    """A small virtual-pixel surface with explicit painter priority."""

    def __init__(self, width, height, pixels=None):
        self.width = width
        self.height = height
        self.pixels = pixels if pixels is not None else [None] * (width * height)
        # Each integer is a vertical occupancy bitset for one x coordinate.
        # Scenery collision can therefore find exposed surfaces without a
        # second width*height raster scan after drawing.
        self._column_bits = [0] * width
        if pixels is not None:
            for index, value in enumerate(pixels):
                if value is not None:
                    y, x = divmod(index, width)
                    self._column_bits[x] |= 1 << y

    def copy(self):
        duplicate = Surface(self.width, self.height)
        duplicate.pixels = self.pixels.copy()
        duplicate._column_bits = self._column_bits.copy()
        return duplicate

    def exposed_top_edges(self):
        """Return occupied runs' top edges using draw-time occupancy bits."""
        columns = []
        for bits in self._column_bits:
            starts = bits & ~(bits << 1)
            edges = []
            while starts:
                lowest = starts & -starts
                edges.append(lowest.bit_length() - 1)
                starts ^= lowest
            columns.append(edges)
        return columns

    def pixel(self, x, y, colour, priority):
        x, y = int(round(x)), int(round(y))
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        index = y * self.width + x
        current = self.pixels[index]
        if current is None or priority >= current[1]:
            self.pixels[index] = (colour, priority)
            self._column_bits[x] |= 1 << y

    def rectangle(self, left, top, right, bottom, colour, priority):
        left = max(0, int(left))
        top = max(0, int(top))
        right = min(self.width, int(right))
        bottom = min(self.height, int(bottom))
        for y in range(top, bottom):
            start = y * self.width
            for x in range(left, right):
                index = start + x
                current = self.pixels[index]
                if current is None or priority >= current[1]:
                    self.pixels[index] = (colour, priority)
                    self._column_bits[x] |= 1 << y

    def line(self, x0, y0, x1, y1, colour, priority):
        x0, y0, x1, y1 = map(lambda value: int(round(value)), (x0, y0, x1, y1))
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.pixel(x0, y0, colour, priority)
            if x0 == x1 and y0 == y1:
                break
            twice = error * 2
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy


def filled_ellipse(surface, centre_x, centre_y, radius_x, radius_y, colour, priority):
    """Draw a clipped filled ellipse in integer virtual pixels."""
    radius_x = max(1, int(round(radius_x)))
    radius_y = max(1, int(round(radius_y)))
    centre_x = int(round(centre_x))
    centre_y = int(round(centre_y))
    for offset_y in range(-radius_y, radius_y + 1):
        fraction = 1.0 - (offset_y / radius_y) ** 2
        half_width = int(round(radius_x * math.sqrt(max(0.0, fraction))))
        surface.rectangle(centre_x - half_width, centre_y + offset_y,
                          centre_x + half_width + 1, centre_y + offset_y + 1,
                          colour, priority)


def filled_polygon(surface, points, colour, priority):
    """Fill a simple polygon using deterministic horizontal scan lines."""
    points = [(int(round(x)), int(round(y))) for x, y in points]
    if len(points) < 3:
        return
    minimum_y = min(y for _, y in points)
    maximum_y = max(y for _, y in points)
    for y in range(minimum_y, maximum_y + 1):
        intersections = []
        for index, (x0, y0) in enumerate(points):
            x1, y1 = points[(index + 1) % len(points)]
            if y0 == y1 or not (min(y0, y1) <= y < max(y0, y1)):
                continue
            intersections.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        intersections.sort()
        for index in range(0, len(intersections) - 1, 2):
            surface.rectangle(math.floor(intersections[index]), y,
                              math.ceil(intersections[index + 1]) + 1, y + 1,
                              colour, priority)


def thick_line(surface, x0, y0, x1, y1, thickness, colour, priority):
    """Draw a line with enough weight to survive small terminal cell sizes."""
    radius = max(0, int(round(thickness)) // 2)
    for offset_y in range(-radius, radius + 1):
        for offset_x in range(-radius, radius + 1):
            if offset_x * offset_x + offset_y * offset_y <= radius * radius + 1:
                surface.line(x0 + offset_x, y0 + offset_y,
                             x1 + offset_x, y1 + offset_y, colour, priority)


@dataclass
class Flake:
    x: float
    y: float
    speed: float
    drift: float
    phase: float
    wobble: float
    shape: str
    colour: tuple


@dataclass
class FallingChunk:
    x: float
    y: float
    speed: float
    drift: float
    shape: str
    colour: tuple


@dataclass
class RestingSnow:
    """A sparse flake temporarily retained by a scenery top edge."""

    x: float
    y: float
    ttl: float
    shape: str
    colour: tuple
    mass: float
    adhesion: float


@dataclass
class BankCollapse:
    """One local snow-tower slump, independent of the broad 50% shed."""

    centre: int
    span: int
    target: float
    generation: int = 0


@dataclass
class Rabbit:
    x: float
    direction: int
    state: str
    timer: float
    phase: float
    hops_before_pause: int


@dataclass
class Tumbleweed:
    x: float
    y: float
    direction: int
    speed: float
    radius: float
    rotation: float
    vertical_speed: float
    blocked_time: float
    collapse_cooldown: float
    irregularity: tuple


@dataclass
class CometParticle:
    x: float
    y: float
    ttl: float
    maximum_ttl: float
    colour_index: int


@dataclass
class SnowPlough:
    active: bool
    x: float
    direction: int
    timer: float
    y: float = 0.0


class SeasonalPhysics:
    """Small deterministic physics layer for snow mass, gravity and slumping.

    This is deliberately a purpose-built 2-D virtual-pixel model rather than a
    general rigid-body engine. It owns the physical rules shared by ground snow
    and snow retained by scenery; rendering remains elsewhere.
    """

    GRAVITY = 9.81

    def __init__(self, args):
        self.args = args

    @property
    def ground_enabled(self):
        return self.args.physics in ("ground", "full")

    @property
    def object_enabled(self):
        return self.args.physics == "full" and self.args.object_snow

    def object_is_stable(self, patch):
        return patch.mass * self.GRAVITY < patch.adhesion

    def relax_bank(self, depths, dt):
        """Move excess adjacent depth downhill toward an angle of repose."""
        if (not self.ground_enabled or len(depths) < 2 or
                self.args.snow_relaxation <= 0):
            return
        maximum_transfer = self.args.snow_relaxation * dt
        slope = self.args.snow_repose_slope
        delta = [0.0] * len(depths)
        for left in range(len(depths)):
            right = (left + 1) % len(depths)
            difference = depths[left] - depths[right]
            excess = abs(difference) - slope
            if excess <= 0:
                continue
            transfer = min(excess * 0.5, maximum_transfer)
            source, destination = ((left, right) if difference > 0 else
                                   (right, left))
            delta[source] -= transfer
            delta[destination] += transfer
        for index, change in enumerate(delta):
            depths[index] = max(0.0, depths[index] + change)


CONTROL_FORMAT = "christmas-snow-control-v1"
DEFAULT_CONTROL_PATH = Path(tempfile.gettempdir()) / "font-demo-christmas-snow-control.json"


def weighted_choice(rng, names, weights):
    marker = rng.random() * sum(weights)
    total = 0.0
    for name, weight in zip(names, weights):
        total += weight
        if marker <= total:
            return name
    return names[-1]


def parse_scenery(value, cabin=False, reindeer=False, no_trees=False):
    tokens = {item.strip().lower() for item in value.split(",") if item.strip()}
    valid = {"none", "trees", "cabin", "reindeer", "all"}
    unknown = tokens - valid
    if unknown:
        raise ValueError("unknown scenery item(s): " + ", ".join(sorted(unknown)))
    if "none" in tokens and len(tokens) > 1:
        raise ValueError("scenery 'none' cannot be combined with other items")
    if "all" in tokens:
        tokens = {"trees", "cabin", "reindeer"}
    elif "none" in tokens:
        tokens = set()
    if cabin:
        tokens.add("cabin")
    if reindeer:
        tokens.add("reindeer")
    if no_trees:
        tokens.discard("trees")
    return frozenset(tokens)


def parse_ambient(value):
    tokens = {item.strip().lower() for item in value.split(",") if item.strip()}
    valid = {"auto", "none", "leaves", "tumbleweed", "all"}
    unknown = tokens - valid
    if unknown:
        raise ValueError("unknown ambient item(s): " + ", ".join(sorted(unknown)))
    if not tokens:
        return frozenset(("auto",))
    if ("none" in tokens or "auto" in tokens) and len(tokens) > 1:
        raise ValueError("ambient 'none' and 'auto' cannot be combined with other items")
    if "all" in tokens:
        return frozenset(("leaves", "tumbleweed"))
    if "none" in tokens:
        return frozenset()
    return frozenset(tokens)


def choice_list(value, valid, label):
    values = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    unknown = set(values) - set(valid)
    if not values or unknown:
        raise argparse.ArgumentTypeError(
            f"{label} must be a comma list drawn from {','.join(valid)}")
    return values


def cabin_type_list(value):
    return choice_list(value, ("cottage", "lodge", "a-frame"), "cabin types")


TREE_TYPES = ("pine", "fir", "spruce", "oak", "maple", "birch")


def tree_type_list(value):
    if value.strip().lower() in ("auto", "all"):
        return TREE_TYPES
    return choice_list(value, TREE_TYPES, "tree types")


def sky_event_list(value):
    if value.strip().lower() == "none":
        return ()
    if value.strip().lower() in ("auto", "all"):
        return ("aeroplane", "ufo", "santa")
    return choice_list(value, ("aeroplane", "ufo", "santa"), "sky events")


def triangle(surface, centre_x, top, half_width, height, colour, priority,
             bend_top=0.0, bend_bottom=0.0):
    height = max(1, int(height))
    for offset in range(height):
        width = max(0, int(half_width * (offset + 1) / height))
        amount = offset / max(1, height - 1)
        bend = int(round(bend_top + (bend_bottom - bend_top) * amount))
        surface.rectangle(centre_x + bend - width, top + offset,
                          centre_x + bend + width + 1, top + offset + 1,
                          colour, priority)


def branch_endpoint(x, y, length, angle_degrees):
    """Return a branch tip using the usual turtle-graphics polar formula.

    Zero degrees points upward. Positive angles turn clockwise. Keeping this
    small equation explicit makes the procedural-tree controls auditable.
    """
    angle = math.radians(angle_degrees)
    return x + math.sin(angle) * length, y - math.cos(angle) * length


def draw_formula_branch(surface, rng, x, y, length, angle, levels,
                        child_angle, length_ratio, thickness,
                        thickness_exponent, colour, snow_colour, priority,
                        segment_budget):
    """Draw one recursively bifurcating limb within a shared segment budget.

    Diameter follows the generalized Leonardo area rule:
    child = parent / 2**(1/exponent). The conventional area-preserving case is
    exponent 2. The cap prevents exponential work at ambitious settings.
    """
    if levels <= 0 or length < 1.2 or segment_budget[0] <= 0:
        return
    tip_x, tip_y = branch_endpoint(x, y, length, angle)
    thick_line(surface, x, y, tip_x, tip_y, thickness, colour, priority)
    segment_budget[0] -= 1
    if levels == 1:
        filled_ellipse(surface, tip_x, tip_y,
                       max(1.0, thickness * 0.85),
                       max(1.0, thickness * 0.50), snow_colour, priority + 2)
        return
    child_thickness = thickness / (2.0 ** (1.0 / thickness_exponent))
    child_length = length * length_ratio
    asymmetry = rng.uniform(-4.0, 4.0)
    draw_formula_branch(
        surface, rng, tip_x, tip_y, child_length * rng.uniform(0.93, 1.04),
        angle - child_angle + asymmetry, levels - 1, child_angle,
        length_ratio, child_thickness, thickness_exponent, colour,
        snow_colour, priority + 1, segment_budget)
    draw_formula_branch(
        surface, rng, tip_x, tip_y, child_length * rng.uniform(0.93, 1.04),
        angle + child_angle + asymmetry, levels - 1, child_angle,
        length_ratio, child_thickness, thickness_exponent, colour,
        snow_colour, priority + 1, segment_budget)


def draw_conifer(surface, rng, centre_x, base_y, height, layer, lights,
                  tree_type, branch_count, branch_angle, trunk_thickness,
                  sway=0.0, segment_budget=None):
    height = max(8, int(height))
    profile_width = {"pine": 0.28, "fir": 0.34, "spruce": 0.22}[tree_type]
    half = max(3, int(height * profile_width))
    colours = (
        (10, 55, 78), (9, 76, 91), (8, 101, 91),
        (10, 126, 83), (11, 151, 74),
    )
    colour = colours[min(len(colours) - 1, layer)]
    priority = 10 + layer * 4
    trunk_half = max(1, int(round(trunk_thickness * (0.45 + layer * 0.10))))
    surface.rectangle(centre_x - trunk_half, base_y - height * 0.82,
                      centre_x + trunk_half + 1, base_y,
                      (82, 61, 45), priority - 1)
    tiers_by_type = {
        "pine": ((0.00, 0.43, 0.48), (0.22, 0.52, 0.66), (0.45, 0.55, 0.88)),
        "fir": ((0.00, 0.35, 0.42), (0.17, 0.42, 0.62),
                (0.36, 0.43, 0.82), (0.57, 0.40, 1.00)),
        "spruce": ((0.00, 0.58, 0.50), (0.30, 0.52, 0.78),
                   (0.56, 0.40, 0.96)),
    }
    tiers = tiers_by_type[tree_type]
    for start, tier_height, width_scale in tiers:
        triangle(surface, centre_x, base_y - height + int(height * start),
                 half * width_scale, height * tier_height, colour, priority,
                 sway * (1.0 - start),
                 sway * max(0.0, 1.0 - start - tier_height))
    # Explicit branch whorls vary independently of the filled silhouette.
    # Endpoints use the same polar formula as the recursive broadleaf trees.
    if segment_budget is None:
        segment_budget = [10_000]
    if layer >= 3:
        for whorl in range(max(1, branch_count)):
            fraction = 0.18 + 0.68 * whorl / max(1, branch_count - 1)
            origin_y = base_y - height + height * fraction
            origin_x = centre_x + sway * (1.0 - fraction)
            branch_length = half * (0.34 + fraction * 0.66)
            droop = max(4.0, min(28.0, branch_angle * 0.42))
            for side in (-1, 1):
                if segment_budget[0] <= 0:
                    break
                angle = side * (90.0 + droop)
                tip_x, tip_y = branch_endpoint(origin_x, origin_y, branch_length, angle)
                thick_line(surface, origin_x, origin_y, tip_x, tip_y,
                           max(1.0, trunk_thickness * 0.45), colour, priority + 1)
                segment_budget[0] -= 1
    if layer >= 3:
        snow = (205, 237, 255)
        for fraction in (0.29, 0.52, 0.72):
            y = base_y - height + int(height * fraction)
            span = max(2, int(half * fraction * 0.65))
            bend = int(round(sway * (1.0 - fraction)))
            surface.line(centre_x + bend - span, y,
                         centre_x + bend + span, y, snow, priority + 1)
        light_colours = ((255, 69, 58), (255, 205, 45), (67, 230, 103), (68, 180, 255))
        light_count = int(height * max(0.0, lights) * 0.45)
        for _ in range(light_count):
            relative_y = rng.uniform(0.22, 0.86)
            y = base_y - height + int(height * relative_y)
            available = half * relative_y * 0.72
            bend = int(round(sway * (1.0 - relative_y)))
            x = centre_x + bend + int(rng.uniform(-available, available))
            surface.pixel(x, y, rng.choice(light_colours), priority + 3)


def draw_broadleaf(surface, rng, centre_x, base_y, height, layer, tree_type,
                   branch_count, branch_levels, branch_angle, length_ratio,
                   trunk_thickness, thickness_exponent, sway=0.0,
                   segment_budget=None):
    """Draw a bare oak, maple, or birch using bounded parametric branching."""
    height = max(10, int(height))
    priority = 10 + layer * 4
    if segment_budget is None:
        segment_budget = [10_000]
    is_birch = tree_type == "birch"
    is_maple = tree_type == "maple"
    trunk = ((202, 211, 203) if is_birch else
             (105, 68, 54) if is_maple else (90, 60, 43))
    branch = ((143, 135, 116) if is_birch else
              (123, 75, 58) if is_maple else (104, 69, 48))
    snow = (210, 240, 250)
    trunk_length = height * (0.48 if is_birch else 0.42)
    crown_y = base_y - trunk_length
    thick_line(surface, centre_x, base_y, centre_x + sway * 0.30, crown_y,
               trunk_thickness * (1.25 if is_birch else 1.55), trunk,
               priority, )
    if is_birch:
        for mark in (0.18, 0.31, 0.48, 0.64, 0.79):
            y = base_y - trunk_length * mark
            surface.line(centre_x - trunk_thickness, y,
                         centre_x + trunk_thickness * 0.4, y,
                         (62, 58, 52), priority + 1)
    if layer <= 2:
        # Distant trees need a stable species silhouette, not hundreds of
        # sub-cell twigs that disappear during terminal quantisation.
        canopy = ((76, 88, 70) if is_birch else
                  (91, 72, 63) if is_maple else (69, 76, 60))
        filled_ellipse(surface, centre_x + sway * 0.45,
                       crown_y - height * 0.18,
                       height * (0.18 if is_birch else 0.24),
                       height * 0.24, canopy, priority)
        filled_ellipse(surface, centre_x + sway * 0.25,
                       crown_y - height * 0.36,
                       height * 0.13, height * 0.18,
                       (92, 104, 86), priority + 1)
        return
    crown_span = 112.0 if is_birch else 148.0 if is_maple else 132.0
    count = max(1, branch_count)
    base_length = height * (0.34 if is_birch else 0.35 if is_maple else 0.38)
    for index in range(count):
        angle = (-crown_span / 2.0 + crown_span * (index + 0.5) / count +
                 rng.uniform(-5.0, 5.0))
        draw_formula_branch(
            surface, rng, centre_x + sway * 0.30, crown_y,
            base_length * rng.uniform(0.82, 1.08), angle,
            max(1, min(branch_levels, 2 if layer == 3 else branch_levels)),
            branch_angle, length_ratio,
            trunk_thickness, thickness_exponent, branch, snow, priority + 1,
            segment_budget)


def draw_tree(surface, rng, centre_x, base_y, height, layer, lights,
              tree_type, args, sway=0.0, segment_budget=None):
    if tree_type in ("pine", "fir", "spruce"):
        draw_conifer(surface, rng, centre_x, base_y, height, layer, lights,
                     tree_type, args.tree_branches, args.tree_branch_angle,
                     args.tree_trunk_thickness, sway, segment_budget)
    else:
        draw_broadleaf(
            surface, rng, centre_x, base_y, height, layer, tree_type,
            args.tree_branches, args.tree_branch_levels,
            args.tree_branch_angle, args.tree_length_ratio,
            args.tree_trunk_thickness, args.tree_thickness_exponent,
            sway, segment_budget)


@functools.lru_cache(maxsize=384)
def cached_tree_pixels(tree_seed, height, layer, lights, tree_type, settings,
                       segment_allowance):
    """Rasterize immutable procedural tree geometry once per layout/species."""
    height = max(10, int(round(height)))
    width = max(40, height * 3 + 24)
    local_height = height + 28
    centre = width // 2
    base = local_height - 8
    surface = Surface(width, local_height)
    rng = random.Random(tree_seed)
    tree_args = argparse.Namespace(
        tree_branches=settings.branches,
        tree_branch_levels=settings.branch_levels,
        tree_branch_angle=settings.branch_angle,
        tree_length_ratio=settings.length_ratio,
        tree_trunk_thickness=settings.trunk_thickness,
        tree_thickness_exponent=settings.thickness_exponent,
    )
    draw_tree(surface, rng, centre, base, height, layer, lights, tree_type,
              tree_args, sway=0.0, segment_budget=[segment_allowance])
    return tuple(
        (index % width - centre, index // width - base, pixel)
        for index, pixel in enumerate(surface.pixels) if pixel is not None
    )


def draw_cached_tree(surface, centre, base, height, sway, pixels):
    """Apply cheap height-weighted sway while compositing cached geometry."""
    inverse_height = 1.0 / max(1.0, height)
    width = surface.width
    surface_pixels = surface.pixels
    column_bits = surface._column_bits
    centre = int(centre)
    base = int(base)
    for dx, dy, (colour, priority) in pixels:
        crown_fraction = max(0.0, min(1.0, -dy * inverse_height))
        offset = int(round(sway * crown_fraction * crown_fraction))
        x = centre + dx + offset
        y = base + dy
        if not (0 <= x < width and 0 <= y < surface.height):
            continue
        index = y * width + x
        current = surface_pixels[index]
        if current is None or priority >= current[1]:
            surface_pixels[index] = (colour, priority)
            column_bits[x] |= 1 << y


def cabin_layout(args, width, height, snow_line):
    """Return fixed-aspect cabins whose count, not width, grows with viewport."""
    scale = args.cabin_scale
    cabin_height = max(10, int(round(height * 0.22 * scale)))
    cabin_width = max(18, int(round(cabin_height * 1.95)))
    cabin_width = min(cabin_width, max(8, width - 6))
    if args.cabin_count is None:
        count = max(1, int(width / max(1, cabin_width * 6.5)))
        count = min(args.max_cabins, count)
    else:
        count = args.cabin_count
    if count == 0:
        return []
    margin = max(cabin_width * 0.65, width * 0.055)
    usable = max(1.0, width - margin * 2)
    placements = []
    for index in range(count):
        centre = margin + usable * (index + 0.5) / count
        variation_rng = random.Random(args.seed + 4109 + index * 97)
        variation = 1.0 + variation_rng.uniform(-args.cabin_size_variation,
                                                 args.cabin_size_variation)
        local_height = max(10, int(round(cabin_height * variation)))
        base = min(height - 1, snow_line + max(2, local_height // 5))
        cabin_type = args.cabin_types[index % len(args.cabin_types)]
        placements.append((centre, base, local_height, index, cabin_type))
    return placements


def draw_cabin(surface, centre_x, base, cabin_height, variant=0, cabin_type="cottage"):
    aspect = {"cottage": 1.72, "lodge": 2.18, "a-frame": 1.48}[cabin_type]
    cabin_width = max(16, int(round(cabin_height * aspect)))
    left = int(round(centre_x - cabin_width / 2))
    top = base - cabin_height
    wall_colours = ((111, 67, 38), (126, 73, 40), (101, 61, 37))
    wall = wall_colours[variant % len(wall_colours)]
    timber = (65, 38, 29)
    roof_colours = ((102, 35, 40), (74, 49, 82), (45, 83, 94))
    roof = roof_colours[variant % len(roof_colours)]
    if cabin_type == "a-frame":
        triangle(surface, centre_x, top - cabin_height * 0.42,
                 cabin_width * 0.52, cabin_height * 1.42, wall, 30)
        surface.line(left - 1, base - 1, centre_x, top - cabin_height * 0.48,
                     roof, 34)
        surface.line(centre_x, top - cabin_height * 0.48,
                     left + cabin_width + 1, base - 1, roof, 34)
    else:
        surface.rectangle(left, top, left + cabin_width, base, wall, 30)
        roof_height = cabin_height * (0.52 if cabin_type == "cottage" else 0.36)
        triangle(surface, left + cabin_width // 2, top - roof_height * 0.75,
                 cabin_width * 0.62, roof_height, roof, 33)
    if cabin_type == "a-frame":
        surface.line(centre_x, top, centre_x, base - 1, timber, 31)
    else:
        for x in range(left + 3, left + cabin_width, max(4, cabin_width // 5)):
            surface.line(x, top, x, base - 1, timber, 31)
    chimney_width = max(2, cabin_width // 10)
    if cabin_type != "a-frame":
        surface.rectangle(left + cabin_width * 0.72, top - cabin_height * 0.54,
                          left + cabin_width * 0.72 + chimney_width, top,
                          (75, 49, 42), 32)
    window = (255, 191, 62)
    wleft = left + cabin_width // 4
    wtop = top + cabin_height // 3
    wsize = max(3, cabin_height // 3)
    surface.rectangle(wleft, wtop, wleft + wsize, wtop + wsize, window, 35)
    surface.line(wleft + wsize // 2, wtop, wleft + wsize // 2,
                 wtop + wsize - 1, (255, 236, 157), 36)
    surface.line(wleft, wtop + wsize // 2, wleft + wsize - 1,
                 wtop + wsize // 2, (255, 236, 157), 36)
    door_width = max(3, cabin_width // 7)
    surface.rectangle(left + cabin_width - door_width - 3,
                      base - max(5, cabin_height // 2),
                      left + cabin_width - 3, base, (57, 34, 27), 34)
    surface.pixel(left + cabin_width - 5,
                  base - max(3, cabin_height // 4), (246, 191, 74), 37)
    if cabin_type == "lodge":
        second_left = left + cabin_width // 2
        surface.rectangle(second_left, wtop, second_left + wsize,
                          wtop + wsize, window, 35)
        surface.line(second_left + wsize // 2, wtop,
                     second_left + wsize // 2, wtop + wsize - 1,
                     (255, 236, 157), 36)


def draw_reindeer(surface, width, height, snow_line):
    # A readable left-facing seasonal reindeer: four depth-separated legs,
    # chest/neck/head anatomy, muzzle and eye, branching antlers, scarf, spots,
    # and small antler ornaments. It is deliberately original pixel geometry,
    # merely informed by the visual vocabulary of the supplied references.
    # Earlier versions reached scale 4 on large PUA canvases, occupying a
    # disproportionate third of the scene. Retain sub-pixel scaling here so
    # the same artwork is approximately one third of that linear footprint.
    scale = max(0.70, min(1.50, (width // 140) / 3.0,
                              (height // 48) / 3.0))
    x = int(width * 0.81)
    base = min(height - 1, snow_line + 2 * scale)
    body_y = base - 9 * scale
    chest_x = x - 9 * scale
    head_x = x - 15 * scale
    head_y = base - 19 * scale
    brown = (169, 91, 52)
    warm = (192, 108, 59)
    shade = (105, 48, 43)
    deep = (64, 35, 35)
    cream = (246, 218, 178)
    scarf = (222, 43, 57)
    scarf_light = (255, 235, 225)
    antler = (91, 48, 38)

    # Rear legs are darker and slightly shorter, creating readable depth.
    for leg_x in (x - 3 * scale, x + 8 * scale):
        surface.rectangle(leg_x, base - 8 * scale,
                          leg_x + 2 * scale, base - scale, shade, 32)
        surface.rectangle(leg_x - scale, base - 2 * scale,
                          leg_x + 2 * scale, base, deep, 33)

    filled_ellipse(surface, x, body_y, 13 * scale, 7 * scale, brown, 35)
    filled_polygon(surface, (
        (chest_x - 2 * scale, base - 8 * scale),
        (chest_x - 4 * scale, base - 18 * scale),
        (chest_x + 2 * scale, base - 22 * scale),
        (chest_x + 5 * scale, base - 8 * scale),
    ), warm, 36)
    # Pale chest and belly edging make the silhouette less block-like.
    filled_polygon(surface, (
        (chest_x - 3 * scale, base - 17 * scale),
        (chest_x, base - 9 * scale),
        (x + 8 * scale, base - 4 * scale),
        (x - 5 * scale, base - 5 * scale),
    ), cream, 37)
    filled_ellipse(surface, x + 12 * scale, body_y - scale,
                   3 * scale, 4 * scale, shade, 36)
    filled_polygon(surface, (
        (x + 12 * scale, body_y - 3 * scale),
        (x + 18 * scale, body_y - 6 * scale),
        (x + 15 * scale, body_y),
    ), cream, 37)

    # Near legs sit over the body and carry brighter knees/ankles.
    for leg_x in (x - 8 * scale, x + 5 * scale):
        surface.rectangle(leg_x, base - 8 * scale,
                          leg_x + 2 * scale, base - scale, warm, 38)
        surface.rectangle(leg_x - scale, base - 2 * scale,
                          leg_x + 2 * scale, base, deep, 39)

    # Head, pointed muzzle, nostril, directional eye and ear.
    filled_ellipse(surface, head_x, head_y, 6 * scale, 5 * scale, warm, 39)
    filled_ellipse(surface, head_x - 5 * scale, head_y + 2 * scale,
                   5 * scale, 3 * scale, cream, 40)
    surface.pixel(head_x - 9 * scale, head_y + 2 * scale, deep, 43)
    filled_ellipse(surface, head_x - 2 * scale, head_y - scale,
                   2 * scale, 2 * scale, cream, 41)
    surface.pixel(head_x - 2 * scale, head_y - scale, (35, 25, 23), 44)
    surface.pixel(head_x - 3 * scale, head_y - 2 * scale, (255, 255, 255), 45)
    filled_polygon(surface, (
        (head_x + 3 * scale, head_y - 3 * scale),
        (head_x + 8 * scale, head_y - 7 * scale),
        (head_x + 7 * scale, head_y - scale),
    ), cream, 40)

    # A striped scarf wraps the neck and hangs freely in front of the body.
    surface.rectangle(chest_x - 5 * scale, base - 15 * scale,
                      chest_x + 4 * scale, base - 12 * scale, scarf, 42)
    surface.rectangle(chest_x - 5 * scale, base - 14 * scale,
                      chest_x + 4 * scale, base - 13 * scale, scarf_light, 43)
    surface.rectangle(chest_x - 2 * scale, base - 12 * scale,
                      chest_x + scale, base - 5 * scale, scarf, 42)
    for stripe_y in (base - 10 * scale, base - 7 * scale):
        surface.line(chest_x - 2 * scale, stripe_y,
                     chest_x + scale, stripe_y, scarf_light, 43)

    # Branching antlers are thick enough to survive cell quantisation.
    roots = (head_x - 2 * scale, head_x + 2 * scale)
    for branch, root_x in enumerate(roots):
        outer = -1 if branch == 0 else 1
        thick_line(surface, root_x, head_y - 4 * scale,
                   root_x + outer * 4 * scale, head_y - 13 * scale,
                   scale, antler, 42)
        thick_line(surface, root_x + outer * 2 * scale, head_y - 8 * scale,
                   root_x - outer * 3 * scale, head_y - 12 * scale,
                   scale, antler, 42)
        thick_line(surface, root_x + outer * 3 * scale, head_y - 10 * scale,
                   root_x + outer * 7 * scale, head_y - 14 * scale,
                   scale, antler, 42)

    # Snowy spots and coloured baubles add depth and seasonal identity.
    for spot_x, spot_y in ((-5, -11), (0, -8), (5, -11), (9, -8)):
        surface.pixel(x + spot_x * scale, base + spot_y * scale, cream, 40)
    ornaments = ((head_x - 8 * scale, head_y - 14 * scale, (255, 199, 45)),
                 (head_x + 8 * scale, head_y - 14 * scale, (234, 57, 70)),
                 (head_x + 4 * scale, head_y - 11 * scale, (80, 220, 220)))
    for ornament_x, ornament_y, colour in ornaments:
        surface.line(ornament_x, ornament_y - scale,
                     ornament_x, ornament_y + scale, cream, 43)
        filled_ellipse(surface, ornament_x, ornament_y + 2 * scale,
                       2 * scale, 2 * scale, colour, 44)


def gust_at(args, elapsed):
    if not args.gust_strength or not args.gust_period:
        return 0.0
    return args.gust_strength * math.sin(math.tau * elapsed / args.gust_period)


def build_scenery(args, width, height, ground_y, elapsed=0.0):
    """Draw scenery against immutable terrain, never the accumulating bank."""
    surface = Surface(width, height)
    rng = random.Random(args.seed + 7331)
    snow_line = max(0, min(height - 1, int(round(ground_y))))
    if ("trees" in args.scenery_set and args.tree_density > 0 and
            args.max_trees > 0):
        # Formula branches share a frame-wide budget. Filled conifer canopies
        # still render after it is exhausted, so extreme inputs degrade in
        # botanical detail rather than frame rate.
        plans = []
        tree_serial = 0
        for layer, scale in enumerate((0.34, 0.44, 0.59, 0.76), start=1):
            layer_cap = args.max_trees // 4 + (layer <= args.max_trees % 4)
            if layer_cap == 0:
                continue
            count = max(2, int(width * args.tree_density / (42 - layer * 5)))
            count = min(count, layer_cap)
            for index in range(count):
                spacing = width / count
                centre = int((index + rng.uniform(-0.30, 0.30)) * spacing)
                tree_height = height * scale * rng.uniform(0.62, 1.0)
                base = snow_line + rng.randint(-2, 3)
                phase = rng.uniform(0, math.tau)
                tree_seed = rng.randrange(0, 2 ** 31)
                wind_bias = (args.wind + gust_at(args, elapsed)) * 0.10
                sway = args.tree_sway * (math.sin(elapsed * 0.72 + phase) + wind_bias)
                tree_type = args.tree_types[tree_serial % len(args.tree_types)]
                tree_serial += 1
                plans.append((tree_seed, centre, base, tree_height, min(4, layer),
                              args.lights if layer >= 3 else 0.0,
                              tree_type, sway))
        settings = TreeSettings(
            args.tree_branches, args.tree_branch_levels,
            args.tree_branch_angle, args.tree_length_ratio,
            args.tree_trunk_thickness, args.tree_thickness_exponent)
        per_tree_budget = (args.tree_segment_budget // len(plans)
                           if plans else 0)
        for tree_seed, centre, base, tree_height, layer, lights, tree_type, sway in plans:
            pixels = cached_tree_pixels(
                tree_seed, int(round(tree_height)), layer, lights, tree_type,
                settings, per_tree_budget)
            draw_cached_tree(surface, centre, base, tree_height, sway, pixels)
    if "cabin" in args.scenery_set:
        for centre, base, cabin_height, variant, cabin_type in cabin_layout(
                args, width, height, snow_line):
            draw_cabin(surface, centre, base, cabin_height, variant, cabin_type)
    if "reindeer" in args.scenery_set:
        draw_reindeer(surface, width, height, snow_line)
    return surface


def effective_ambient(args, width):
    if "auto" not in args.ambient_set:
        return args.ambient_set
    selected = {"leaves"}
    if width >= 720:
        selected.add("tumbleweed")
    return frozenset(selected)


def tumbleweed_states(args, engine, elapsed):
    """Return stateful rolling bodies shared by drawing and rabbit reactions."""
    ambient = effective_ambient(args, engine.width)
    if "tumbleweed" not in ambient:
        return []
    engine.sync_tumbleweeds()
    return [
        (index, weed.x, weed.y, weed.radius, weed.rotation,
         max(0.0, engine.surface_y(weed.x) - weed.radius - weed.y),
         engine.surface_y(weed.x) - 1, weed.irregularity)
        for index, weed in enumerate(engine.tumbleweeds)
    ]


def draw_rabbit(surface, engine, rabbit):
    if rabbit.state == "hidden":
        return
    scale = max(1, min(2, engine.height // 80))
    direction = rabbit.direction
    hop = 0.0
    if rabbit.state in ("hopping", "startled"):
        amplitude = 5.0 if rabbit.state == "startled" else 3.2
        hop = abs(math.sin(rabbit.phase)) * amplitude * scale
    base = engine.surface_y(rabbit.x) - 1 - hop
    x = int(round(rabbit.x))
    y = int(round(base))
    fur = (174, 155, 135)
    shade = (116, 96, 84)
    pale = (236, 226, 214)
    body_left = x - 4 * scale if direction > 0 else x - 2 * scale
    surface.rectangle(body_left, y - 4 * scale,
                      body_left + 6 * scale, y, fur, 86)
    head_x = x + 2 * scale * direction
    surface.rectangle(head_x - scale, y - 7 * scale,
                      head_x + 2 * scale, y - 3 * scale, fur, 87)
    ear_lean = direction if rabbit.state == "startled" else 0
    surface.line(head_x, y - 7 * scale,
                 head_x - scale + ear_lean, y - 11 * scale, fur, 88)
    surface.line(head_x + scale, y - 7 * scale,
                 head_x + scale + ear_lean, y - 10 * scale, shade, 88)
    surface.pixel(head_x + (2 * scale if direction > 0 else -scale),
                  y - 6 * scale, (30, 24, 28), 91)
    tail_x = body_left - scale if direction > 0 else body_left + 6 * scale
    surface.rectangle(tail_x, y - 4 * scale, tail_x + 2 * scale,
                      y - 2 * scale, pale, 89)
    leg_offset = int(round(math.sin(rabbit.phase) * 2 * scale))
    surface.line(x - direction * scale, y - scale,
                 x - direction * (3 * scale + leg_offset), y, shade, 88)
    if rabbit.state == "eating":
        surface.pixel(head_x + direction * 2 * scale, y - 3 * scale,
                      (88, 138, 62), 90)


def sky_event_margin(engine):
    """Off-screen runway wide enough for the richest flyby silhouette."""
    return max(104.0, engine.width * 0.08)


def compact_flyby_unit(engine, height_divisor):
    """One-third of the former scale, with a legibility floor for tiny grids."""
    former = max(1.0, min(3.0, engine.height // height_divisor))
    return max(0.65, former / 3.0)


def santa_flyby_unit(engine):
    former = max(1.0, min(2.0, engine.height // 60))
    # Honour the configured linear scale even in short terminals; unlike the
    # compact aircraft/UFO helper, 0.50 must remain a true half-scale Santa.
    return max(0.20, former * engine.args.santa_scale)


def current_sky_event(args, engine, elapsed):
    if not args.sky_events:
        return None
    interval = args.flyby_interval
    shifted = elapsed - interval * 0.35
    if shifted < 0:
        return None
    margin = sky_event_margin(engine)
    travel_time = (engine.width + margin * 2) / args.flyby_speed
    cycle = travel_time + interval
    event_index = int(shifted / cycle)
    local = shifted - event_index * cycle
    if local > travel_time:
        return None
    rng = random.Random(args.seed + 51001 + event_index * 113)
    kind = args.sky_events[event_index % len(args.sky_events)]
    direction = -1 if rng.random() < 0.5 else 1
    progress = local / max(0.001, travel_time)
    x = -margin + progress * (engine.width + margin * 2)
    if direction < 0:
        x = engine.width - x
    if kind == "aeroplane":
        unit = compact_flyby_unit(engine, 60)
        minimum_y, maximum_y = 19 * unit, engine.height - 18 * unit
    elif kind == "ufo":
        unit = compact_flyby_unit(engine, 65)
        minimum_y, maximum_y = 9 * unit, engine.height - 27 * unit
    else:
        unit = santa_flyby_unit(engine)
        minimum_y, maximum_y = 22 * unit, engine.height - 10 * unit
    maximum_y = max(minimum_y, min(maximum_y, engine.height * 0.42))
    if kind == "santa":
        arc_rise = engine.height * args.santa_arc_height
        base_minimum = min(maximum_y, minimum_y + arc_rise)
        y = rng.uniform(base_minimum, maximum_y)
        y -= math.sin(math.pi * progress) * arc_rise
        y = max(minimum_y, y)
    else:
        y = rng.uniform(minimum_y, maximum_y)
    return kind, x, y, direction, event_index


def draw_sky_event(surface, engine, elapsed):
    trail_colours = ((255, 244, 184), (255, 196, 60),
                     (123, 210, 240), (68, 105, 138))
    for particle in engine.santa_trail:
        fraction = max(0.0, min(1.0, particle.ttl / particle.maximum_ttl))
        base = trail_colours[particle.colour_index % len(trail_colours)]
        colour = tuple(int(channel * (0.28 + fraction * 0.72)) for channel in base)
        filled_ellipse(surface, particle.x, particle.y,
                       max(1.0, fraction * 1.8), max(1.0, fraction * 1.2),
                       colour, 55)
    event = current_sky_event(engine.args, engine, elapsed)
    if event is None:
        return
    kind, x, y, direction, event_index = event

    def point(dx, dy):
        return x + direction * dx, y + dy

    if kind == "aeroplane":
        unit = compact_flyby_unit(engine, 60)
        body = (239, 248, 250)
        shade = (151, 187, 204)
        accent = (245, 111, 70)
        deep_accent = (197, 49, 60)
        window = (40, 94, 177)
        fuselage = [point(dx * unit, dy * unit) for dx, dy in (
            (-31, -3), (-18, -5), (18, -5), (27, -3), (33, 0),
            (27, 3), (-21, 5), (-31, 2),
        )]
        filled_polygon(surface, fuselage, body, 65)
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (-29, 1), (28, 1), (23, 5), (-21, 5),
        )], shade, 66)
        # Swept wings, lower engine and tall tail make direction unmistakable.
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (-3, -4), (-20, -18), (-10, -18), (13, -4),
        )], accent, 64)
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (-1, 3), (-17, 16), (-7, 17), (14, 3),
        )], body, 64)
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (-23, -4), (-29, -16), (-22, -17), (-12, -4),
        )], accent, 67)
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (-31, -2), (-8, -3), (-13, 4), (-27, 3),
        )], deep_accent, 67)
        engine_x, engine_y = point(-5 * unit, 10 * unit)
        filled_ellipse(surface, engine_x, engine_y, 5 * unit, 3 * unit,
                       deep_accent, 68)
        filled_ellipse(surface, engine_x + direction * 2 * unit, engine_y,
                       3 * unit, 2 * unit, accent, 69)
        for window_index, dx in enumerate(range(-10, 22, 4)):
            wx, wy = point(dx * unit, -2 * unit)
            surface.rectangle(wx - unit, wy - unit,
                              wx + unit, wy + unit, window, 70)
        cockpit_x, cockpit_y = point(25 * unit, -2 * unit)
        surface.rectangle(cockpit_x - unit, cockpit_y - unit,
                          cockpit_x + 2 * unit, cockpit_y + unit, window, 70)
        for trail in range(3):
            start_x, start_y = point((-34 - trail * 3) * unit,
                                     (trail - 1) * unit)
            end_x, end_y = point((-50 - trail * 4) * unit,
                                 (trail - 1) * unit)
            surface.line(start_x, start_y, end_x, end_y,
                         (143, 164, 180), 54)
    elif kind == "ufo":
        unit = compact_flyby_unit(engine, 65)
        metal = (132, 194, 216)
        dark = (26, 48, 62)
        glass = (122, 222, 245)
        alien = (22, 164, 70)
        glow = (83, 255, 211)
        pulse = 0.5 + 0.5 * math.sin(elapsed * 7.0 + event_index)
        filled_ellipse(surface, x, y + 2 * unit, 25 * unit, 7 * unit,
                       dark, 64)
        filled_ellipse(surface, x, y, 22 * unit, 6 * unit, metal, 66)
        filled_ellipse(surface, x, y - 5 * unit, 11 * unit, 7 * unit,
                       dark, 65)
        filled_ellipse(surface, x, y - 6 * unit, 9 * unit, 6 * unit,
                       glass, 68)
        # A visible passenger silhouette turns a generic saucer into a UFO.
        filled_ellipse(surface, x, y - 7 * unit, 3 * unit, 3 * unit,
                       alien, 70)
        surface.pixel(x - 2 * unit, y - 8 * unit, (9, 42, 24), 71)
        surface.pixel(x + 2 * unit, y - 8 * unit, (9, 42, 24), 71)
        surface.rectangle(x - 23 * unit, y, x + 24 * unit,
                          y + 2 * unit, (48, 112, 139), 69)
        for lamp_index, lamp in enumerate((-18, -12, -6, 0, 6, 12, 18)):
            lamp_colour = glow if (lamp_index + int(elapsed * 6)) % 2 else (68, 180, 252)
            filled_ellipse(surface, x + lamp * unit, y + 4 * unit,
                           max(1, unit), max(1, unit), lamp_colour, 71)
        beam_colour = (42, int(120 + 80 * pulse), int(128 + 90 * pulse))
        for beam in (-9, -4, 4, 9):
            surface.line(x + beam * unit, y + 7 * unit,
                         x + beam * 2 * unit, y + 25 * unit,
                         beam_colour, 52)
        for scan_y in range(12, 25, 4):
            span = int(scan_y * 0.70)
            surface.line(x - span * unit, y + scan_y * unit,
                         x + span * unit, y + scan_y * unit,
                         (37, 105, 103), 51)
    else:  # Santa's sleigh and reindeer team.
        unit = santa_flyby_unit(engine)
        red, deep_red = (218, 42, 53), (139, 25, 42)
        gold, brown, dark_brown = (255, 198, 54), (166, 92, 48), (83, 48, 38)
        cream, white = (250, 226, 194), (247, 249, 244)
        far_brown = (111, 61, 43)
        sleigh_x = x - direction * 29 * unit
        # Gift sack and parcels sit behind a recognisable seated Santa.
        filled_ellipse(surface, sleigh_x - direction * 8 * unit,
                       y - 9 * unit, 7 * unit, 7 * unit, deep_red, 64)
        for gift_dx, gift_dy, gift_colour in (
                (-10, -12, (46, 147, 84)), (-5, -15, (65, 122, 204)),
                (-13, -7, (226, 164, 45))):
            gift_x = sleigh_x + direction * gift_dx * unit
            surface.rectangle(gift_x - 2 * unit, y + gift_dy * unit,
                              gift_x + 2 * unit, y + (gift_dy + 4) * unit,
                              gift_colour, 65)
            surface.line(gift_x, y + gift_dy * unit,
                         gift_x, y + (gift_dy + 3) * unit, gold, 66)
        filled_ellipse(surface, sleigh_x, y - 8 * unit,
                       5 * unit, 7 * unit, red, 68)
        filled_ellipse(surface, sleigh_x + direction * 2 * unit,
                       y - 15 * unit, 3 * unit, 3 * unit, cream, 70)
        # Beard, eye, hat trim, belt and mitten separate the figure from sack.
        filled_ellipse(surface, sleigh_x + direction * 4 * unit,
                       y - 13 * unit, 3 * unit, 4 * unit, white, 71)
        surface.pixel(sleigh_x + direction * 3 * unit,
                      y - 16 * unit, (34, 28, 29), 73)
        thick_line(surface, sleigh_x - direction * unit, y - 11 * unit,
                   sleigh_x + direction * 4 * unit, y - 11 * unit,
                   unit, (42, 39, 37), 71)
        filled_polygon(surface, (
            (sleigh_x - direction * unit, y - 17 * unit),
            (sleigh_x + direction * 7 * unit, y - 20 * unit),
            (sleigh_x + direction * 4 * unit, y - 14 * unit),
        ), red, 69)
        thick_line(surface, sleigh_x, y - 17 * unit,
                   sleigh_x + direction * 5 * unit, y - 18 * unit,
                   unit, white, 72)
        surface.pixel(sleigh_x + direction * 8 * unit,
                      y - 20 * unit, white, 73)
        mitten_x = sleigh_x + direction * 7 * unit
        thick_line(surface, sleigh_x + direction * 3 * unit, y - 10 * unit,
                   mitten_x, y - 7 * unit, unit, red, 72)
        filled_ellipse(surface, mitten_x, y - 7 * unit,
                       unit, unit, white, 73)

        # High-backed sleigh with a contrasting panel and curled gold runners.
        filled_polygon(surface, (
            (sleigh_x - direction * 14 * unit, y - 6 * unit),
            (sleigh_x + direction * 10 * unit, y - 6 * unit),
            (sleigh_x + direction * 14 * unit, y + 3 * unit),
            (sleigh_x - direction * 10 * unit, y + 3 * unit),
        ), red, 67)
        filled_polygon(surface, (
            (sleigh_x - direction * 11 * unit, y - 4 * unit),
            (sleigh_x + direction * 8 * unit, y - 4 * unit),
            (sleigh_x + direction * 10 * unit, y + unit),
            (sleigh_x - direction * 8 * unit, y + unit),
        ), deep_red, 68)
        surface.line(sleigh_x - direction * 10 * unit, y - 2 * unit,
                     sleigh_x + direction * 9 * unit, y - 2 * unit,
                     gold, 69)
        thick_line(surface, sleigh_x - direction * 14 * unit, y + 4 * unit,
                   sleigh_x + direction * 16 * unit, y + 4 * unit,
                   unit, gold, 70)
        surface.line(sleigh_x - direction * 10 * unit, y + 5 * unit,
                     sleigh_x - direction * 7 * unit, y + 8 * unit, gold, 69)
        surface.line(sleigh_x - direction * 7 * unit, y + 8 * unit,
                     sleigh_x + direction * 14 * unit, y + 8 * unit,
                     gold, 69)
        surface.line(sleigh_x + direction * 13 * unit, y + 4 * unit,
                     sleigh_x + direction * 17 * unit, y + 2 * unit, gold, 69)
        filled_ellipse(surface, sleigh_x + direction * 17 * unit,
                       y + unit, 2 * unit, 2 * unit, gold, 69)

        phase = elapsed * 9.0
        deer_centres = []
        for deer in range(4):
            deer_x = x + direction * (2 + deer * 18) * unit
            gait = phase + deer * 0.72
            deer_y = y - abs(math.sin(gait)) * 1.5 * unit
            deer_centres.append((deer_x, deer_y))
            # Four jointed legs: far pair first, then body, then near pair.
            # Paired phase offsets produce a suspended gallop rather than two
            # rigid sticks swinging through one another.
            leg_specs = (
                (-3.5, gait + math.pi * 0.85, far_brown, 65),
                (3.0, gait + math.pi * 1.85, far_brown, 65),
                (-2.5, gait, dark_brown, 70),
                (3.5, gait + math.pi, dark_brown, 70),
            )
            for hip_offset, leg_phase, leg_colour, priority in leg_specs[:2]:
                swing = math.sin(leg_phase) * 3.0 * unit
                lift = max(0.0, math.cos(leg_phase)) * 2.0 * unit
                hip_x = deer_x + direction * hip_offset * unit
                knee_x = hip_x + direction * swing * 0.45
                knee_y = deer_y + 4.5 * unit - lift * 0.35
                hoof_x = hip_x + direction * swing
                hoof_y = deer_y + 8.0 * unit - lift
                thick_line(surface, hip_x, deer_y + unit, knee_x, knee_y,
                           unit, leg_colour, priority)
                surface.line(knee_x, knee_y, hoof_x, hoof_y,
                             leg_colour, priority)
            filled_ellipse(surface, deer_x, deer_y, 6 * unit, 3 * unit,
                           brown, 67)
            # Pale belly, dark tail and shoulder establish body orientation.
            surface.line(deer_x - direction * 3 * unit, deer_y + 2 * unit,
                         deer_x + direction * 3 * unit, deer_y + 2 * unit,
                         cream, 68)
            filled_polygon(surface, (
                (deer_x - direction * 6 * unit, deer_y - unit),
                (deer_x - direction * 10 * unit, deer_y - 3 * unit),
                (deer_x - direction * 7 * unit, deer_y + unit),
            ), far_brown, 68)
            head_x = deer_x + direction * 7 * unit
            head_y = deer_y - 5 * unit
            thick_line(surface, deer_x + direction * 4 * unit, deer_y - unit,
                       head_x - direction * unit, head_y + unit,
                       unit, brown, 68)
            filled_ellipse(surface, head_x, head_y, 3 * unit, 3 * unit,
                           brown, 69)
            filled_polygon(surface, (
                (head_x - direction * unit, head_y - 2 * unit),
                (head_x - direction * 4 * unit, head_y - 5 * unit),
                (head_x - direction * 3 * unit, head_y),
            ), cream, 70)
            muzzle_x = head_x + direction * 3 * unit
            filled_ellipse(surface, muzzle_x, head_y + unit,
                           2 * unit, unit, cream, 70)
            nose_colour = (246, 52, 60) if deer == 3 else dark_brown
            surface.pixel(head_x + direction * 4 * unit, head_y + unit,
                          nose_colour, 72)
            surface.pixel(head_x + direction * unit, head_y - unit,
                          (25, 22, 20), 73)
            # Branched antlers remain separate from the ears and harness.
            thick_line(surface, head_x, head_y - 2 * unit,
                       head_x - direction * unit, head_y - 7 * unit,
                       unit, gold, 70)
            surface.line(head_x - direction * unit, head_y - 6 * unit,
                         head_x + direction * 3 * unit, head_y - 8 * unit,
                         gold, 70)
            surface.line(head_x - direction * unit, head_y - 5 * unit,
                         head_x - direction * 4 * unit, head_y - 7 * unit,
                         gold, 70)
            for hip_offset, leg_phase, leg_colour, priority in leg_specs[2:]:
                swing = math.sin(leg_phase) * 3.0 * unit
                lift = max(0.0, math.cos(leg_phase)) * 2.0 * unit
                hip_x = deer_x + direction * hip_offset * unit
                knee_x = hip_x + direction * swing * 0.45
                knee_y = deer_y + 4.5 * unit - lift * 0.35
                hoof_x = hip_x + direction * swing
                hoof_y = deer_y + 8.0 * unit - lift
                thick_line(surface, hip_x, deer_y + unit, knee_x, knee_y,
                           unit, leg_colour, priority)
                surface.line(knee_x, knee_y, hoof_x, hoof_y,
                             leg_colour, priority)
        lead_x, lead_y = deer_centres[-1]
        surface.line(sleigh_x + direction * 14 * unit, y - 2 * unit,
                     lead_x + direction * 5 * unit, lead_y - 2 * unit,
                     gold, 63)
        surface.line(mitten_x, y - 7 * unit,
                     lead_x + direction * 5 * unit, lead_y - 2 * unit,
                     (205, 170, 92), 64)


def draw_plough(surface, engine):
    plough = engine.plough
    if not plough.active:
        return
    scale = max(1, min(3, engine.height // 70))
    x, y, direction = int(plough.x), int(plough.y), plough.direction
    orange = (239, 124, 36)
    dark = (52, 59, 65)
    surface.rectangle(x - 7 * scale, y - 6 * scale,
                      x + 5 * scale, y - 2 * scale, orange, 94)
    surface.rectangle(x - 3 * scale, y - 11 * scale,
                      x + 4 * scale, y - 6 * scale, orange, 94)
    surface.rectangle(x - scale, y - 10 * scale,
                      x + 3 * scale, y - 7 * scale, (118, 212, 235), 95)
    for wheel in (-4, 3):
        surface.rectangle(x + wheel * scale, y - 3 * scale,
                          x + (wheel + 2) * scale, y, dark, 96)
    blade_x = x + direction * 7 * scale
    surface.line(blade_x, y - 6 * scale,
                 blade_x + direction * 5 * scale, y, (247, 202, 58), 97)
    surface.line(blade_x + direction * 5 * scale, y,
                 blade_x + direction * 6 * scale, y - 8 * scale,
                 (210, 220, 224), 97)


def draw_ambient(surface, engine, elapsed):
    args = engine.args
    ambient = effective_ambient(args, engine.width)
    if "leaves" in ambient:
        count = (args.leaf_count if args.leaf_count is not None
                 else max(4, engine.width * engine.height // 10500))
        colours = ((201, 107, 42), (232, 167, 45), (134, 153, 52),
                   (170, 70, 38), (74, 139, 69))
        for index in range(count):
            rng = random.Random(args.seed + 10007 + index * 37)
            speed = args.ambient_speed * rng.uniform(0.65, 1.35)
            direction = -1.0 if args.wind < 0 else 1.0
            x = (rng.random() * engine.width +
                 direction * (speed + abs(args.wind)) * elapsed) % engine.width
            centre_y = engine.height * rng.uniform(0.08, 0.72)
            y = centre_y + math.sin(elapsed * rng.uniform(1.1, 2.8) +
                                    rng.uniform(0, math.tau)) * engine.height * 0.035
            colour = colours[index % len(colours)]
            surface.pixel(x, y, colour, 58)
            surface.pixel(x - direction, y + (index % 3 - 1), colour, 58)

    if "tumbleweed" in ambient:
        for (index, x, y, radius, rotation, _bounce, _ground_y,
             irregularity) in tumbleweed_states(args, engine, elapsed):
            # Stable irregular radii rotate with the body, so it rolls rather
            # than looking like a translating circle with static cross-hairs.
            outer = []
            inner = []
            samples = len(irregularity)
            for sample in range(samples):
                angle = math.tau * sample / samples + rotation
                outer_radius = radius * irregularity[sample]
                inner_radius = radius * (0.42 + 0.10 * irregularity[(sample * 3) % samples])
                outer.append((x + math.cos(angle) * outer_radius,
                              y + math.sin(angle) * outer_radius))
                inner.append((x + math.cos(angle) * inner_radius,
                              y + math.sin(angle) * inner_radius))
            for left, right in zip(outer, outer[1:] + outer[:1]):
                surface.line(*left, *right, (169, 116, 60), 77)
            for left, right in zip(inner, inner[1:] + inner[:1]):
                surface.line(*left, *right, (111, 72, 41), 78)
            for spoke in (1, 4, 8, 12, 16):
                surface.line(*inner[(spoke + 7) % samples], *outer[spoke],
                             (137, 88, 44), 79)
                tip = outer[spoke]
                angle = math.tau * spoke / samples + rotation
                surface.line(*tip,
                             tip[0] + math.cos(angle + 0.55) * radius * 0.34,
                             tip[1] + math.sin(angle + 0.55) * radius * 0.34,
                             (190, 137, 70), 79)


class SnowEngine:
    def __init__(self, args, width, height):
        self.args = args
        self.physics = SeasonalPhysics(args)
        self.width = width
        self.height = height
        self.rng = random.Random(args.seed)
        self.palette = PALETTES[args.palette]
        base = height * args.initial_snow
        amplitude = height * args.bank_drift
        self.depths = []
        for x in range(width):
            wave = 0.58 * math.sin(x * 0.037 + 0.4) + 0.42 * math.sin(x * 0.091 + 2.1)
            self.depths.append(max(0.0, min(height * 0.82, base + amplitude * wave)))
        self.scenery_ground_fraction = (
            height - sum(self.depths) / max(1, len(self.depths))) / height
        self.max_flakes = (args.max_flakes if args.max_flakes is not None
                           else max(120, width * height // 100))
        self.snow_rate = args.snow_rate if args.snow_rate is not None else max(24.0, width / 5.0)
        preload = min(self.max_flakes, int(self.snow_rate * args.preload_seconds))
        self.flakes = [self.new_flake(initial=True) for _ in range(preload)]
        self.chunks = []
        self.resting_snow = []
        self.scenery_surfaces = [[] for _ in range(width)]
        self.object_snow_caught = 0
        self.object_snow_shed = 0
        self.tumbleweeds = []
        self.tumbleweed_blocks = 0
        self.tumbleweed_collapses = 0
        self.santa_trail = []
        self.santa_trail_credit = 0.0
        self.spawn_credit = 0.0
        self.shedding = None
        self.shed_count = 0
        self.shed_cooldown = 0.0
        self.tower_ages = [0.0] * width
        self.tower_collapses = []
        self.tower_collapse_count = 0
        self.rabbits = []
        self.rabbit_reactions = 0
        self.sync_rabbits(initial=True)
        self.sync_tumbleweeds(initial=True)
        self.plough = SnowPlough(
            active=False, x=-20.0, direction=1,
            timer=args.plough_interval * self.rng.uniform(0.35, 0.75),
        )
        self.plough_count = 0
        self.telemetry_wall = time.monotonic()
        self.telemetry_cpu = time.process_time()
        self.cpu_percent = 0.0
        self.render_ms = 0.0
        self.dashboard_tab = 0
        self.glyphs_seen = set()

    def resize(self, width, height):
        """Rescale live particles and bank depth into a changed terminal grid."""
        if width == self.width and height == self.height:
            return
        old_width, old_height = self.width, self.height
        old_depths = self.depths
        old_tower_ages = self.tower_ages
        scale_x = width / old_width
        scale_y = height / old_height
        depths = []
        tower_ages = []
        for x in range(width):
            source = (x + 0.5) * old_width / width - 0.5
            left = max(0, min(old_width - 1, int(math.floor(source))))
            right = max(0, min(old_width - 1, left + 1))
            fraction = max(0.0, min(1.0, source - left))
            value = old_depths[left] * (1.0 - fraction) + old_depths[right] * fraction
            depths.append(min(height * 0.86, value * scale_y))
            tower_ages.append(old_tower_ages[left] * (1.0 - fraction) +
                              old_tower_ages[right] * fraction)
        for flake in self.flakes:
            flake.x *= scale_x
            flake.y *= scale_y
        for chunk in self.chunks:
            chunk.x *= scale_x
            chunk.y *= scale_y
        for patch in self.resting_snow:
            patch.x *= scale_x
            patch.y *= scale_y
        for rabbit in self.rabbits:
            rabbit.x *= scale_x
        for weed in self.tumbleweeds:
            weed.x *= scale_x
            weed.y *= scale_y
            weed.radius *= min(scale_x, scale_y)
        for particle in self.santa_trail:
            particle.x *= scale_x
            particle.y *= scale_y
        self.plough.x *= scale_x
        self.plough.y *= scale_y
        self.width = width
        self.height = height
        self.depths = depths
        self.tower_ages = tower_ages
        self.shedding = None
        self.tower_collapses = []
        self.scenery_surfaces = [[] for _ in range(width)]
        if self.args.max_flakes is None:
            self.max_flakes = max(120, width * height // 100)
        if len(self.flakes) > self.max_flakes:
            self.flakes = self.flakes[:self.max_flakes]

    def new_flake(self, initial=False):
        shape = weighted_choice(self.rng, self.args.flake_sizes, self.args.size_weights)
        variation = self.args.speed_variation
        speed = self.args.fall_speed * self.rng.uniform(max(0.05, 1.0 - variation), 1.0 + variation)
        return Flake(
            x=self.rng.uniform(0, max(0, self.width - 1)),
            y=self.rng.uniform(-self.height * 0.95, -1) if initial else self.rng.uniform(-10, -1),
            speed=speed,
            drift=self.rng.uniform(-self.args.drift, self.args.drift),
            phase=self.rng.uniform(0, math.tau),
            wobble=self.rng.uniform(0.55, 2.1),
            shape=shape,
            colour=self.rng.choice(self.palette["snow"]),
        )

    def surface_y(self, x):
        return self.height - self.depths[int(x) % self.width]

    def update_scenery_collision(self, surface):
        """Index exposed top edges so flakes may sparsely settle on objects."""
        if not self.physics.object_enabled:
            self.scenery_surfaces = []
            return
        self.scenery_surfaces = surface.exposed_top_edges()

    def scenery_hit(self, x, old_y, new_y):
        """Return the first crossed scenery top edge, excluding the ground bank."""
        if not self.physics.object_enabled or not self.scenery_surfaces:
            return None
        lower, upper = sorted((old_y, new_y))
        ground = self.surface_y(x)
        for y in self.scenery_surfaces[int(x) % self.width]:
            if lower <= y <= upper + 1 and y < ground - 1:
                return y
        return None

    def catch_object_snow(self, flake, y):
        """Retain only a sparse, non-uniform fraction of object impacts."""
        if self.rng.random() >= self.args.object_snow_capture:
            return False
        x = int(round(flake.x)) % self.width
        impact_mass = 0.45 + math.sqrt(len(SHAPES[flake.shape])) * 0.18
        for patch in self.resting_snow[-100:]:
            if abs(patch.x - x) <= 1 and abs(patch.y - y) <= 1:
                patch.mass += impact_mass
                patch.ttl = min(patch.ttl, self.args.object_snow_hold)
                self.object_snow_caught += 1
                return True
        if len(self.resting_snow) >= self.args.object_snow_max:
            return False
        lifetime = max(0.15, self.args.object_snow_hold + self.rng.uniform(
            -self.args.object_snow_hold_jitter,
            self.args.object_snow_hold_jitter))
        shape = "small" if flake.shape in ("medium", "large") else "tiny"
        self.resting_snow.append(RestingSnow(
            x=x, y=y - 1, ttl=lifetime, shape=shape,
            colour=self.rng.choice(self.palette["bank"][:2]),
            mass=impact_mass,
            adhesion=(self.args.object_snow_adhesion * SeasonalPhysics.GRAVITY *
                      self.rng.uniform(0.65, 1.35))))
        self.object_snow_caught += 1
        return True

    def step_object_snow(self, dt):
        """Age retained patches and return expired ones to visible snowfall."""
        if not self.physics.object_enabled:
            self.resting_snow = []
            return
        survivors = []
        for patch in self.resting_snow:
            patch.ttl -= dt
            if patch.ttl > 0 and self.physics.object_is_stable(patch):
                survivors.append(patch)
                continue
            chunk_count = max(1, min(3, int(math.ceil(patch.mass / 1.5))))
            for chunk_index in range(chunk_count):
                self.chunks.append(FallingChunk(
                    x=patch.x + self.rng.uniform(-1.2, 1.2),
                    y=patch.y + chunk_index,
                    speed=self.args.fall_speed * self.rng.uniform(0.55, 1.05),
                    drift=self.rng.uniform(-self.args.drift, self.args.drift),
                    shape=patch.shape, colour=patch.colour))
            self.object_snow_shed += 1
        self.resting_snow = survivors

    @property
    def scenery_ground_y(self):
        """Terrain anchor scaled by height but unaffected by snow accumulation."""
        return self.height * self.scenery_ground_fraction

    def deposit(self, flake):
        if not self.args.accumulate:
            return
        extent = max(abs(x) for x, _ in SHAPES[flake.shape])
        radius = max(3, extent * 2 + 2)
        amount = self.args.accumulation * (1.0 + extent * 0.45)
        centre = int(round(flake.x))
        weights = [math.exp(-0.5 * (offset / max(1.0, radius * 0.52)) ** 2)
                   for offset in range(-radius, radius + 1)]
        weight_total = sum(weights)
        for offset in range(-radius, radius + 1):
            x = (centre + offset) % self.width
            weight = weights[offset + radius] / weight_total
            self.depths[x] = min(
                self.height * 0.86,
                self.depths[x] + amount * weight * (1.6 + extent * 0.8))

    def begin_shed(self):
        peak = max(range(self.width), key=self.depths.__getitem__)
        span = max(4, int(self.width * self.args.shed_width))
        self.shedding = (peak, span)
        self.shed_count += 1

    def step_shed(self, dt):
        if not self.shedding:
            return
        centre, span = self.shedding
        target = self.height * self.args.shed_to
        reduction = self.height * self.args.shed_rate * dt
        removed = []
        complete = True
        for offset in range(-span // 2, span // 2 + 1):
            x = (centre + offset) % self.width
            edge = abs(offset) / max(1, span / 2)
            local_target = target * (0.82 + edge * 0.18)
            if self.depths[x] > local_target + 0.25:
                complete = False
                old = self.depths[x]
                self.depths[x] = max(local_target, old - reduction)
                if old - self.depths[x] > 0.1:
                    removed.append((x, self.height - old))
        sample_step = max(1, len(removed) // 8)
        for x, y in removed[::sample_step][:10]:
            self.chunks.append(FallingChunk(
                x=x,
                y=y,
                speed=self.args.fall_speed * self.rng.uniform(1.0, 1.8),
                drift=self.rng.uniform(-self.args.drift, self.args.drift),
                shape=self.rng.choice(("tiny", "small", "medium")),
                colour=self.rng.choice(self.palette["bank"][:2]),
            ))
        if complete:
            self.shedding = None
            self.shed_cooldown = 2.0

    def tower_deadline(self, x):
        """Return a repeatable, locally varied lifetime for an unstable tower."""
        mixed = (self.args.seed * 1103515245 + x * 2654435761) & 0xFFFFFFFF
        fraction = mixed / 0xFFFFFFFF
        return self.args.tower_age + self.args.tower_age_jitter * fraction

    def tower_prominence(self, x):
        """Height above nearby shoulders, using a scale that follows viewport width."""
        radius = max(3, int(self.width * 0.015))
        shoulders = (
            self.depths[(x - radius * 2) % self.width],
            self.depths[(x - radius) % self.width],
            self.depths[(x + radius) % self.width],
            self.depths[(x + radius * 2) % self.width],
        )
        return self.depths[x] - sum(shoulders) / len(shoulders)

    def collapse_near(self, centre, radius):
        for collapse in self.tower_collapses:
            distance = abs(collapse.centre - centre)
            distance = min(distance, self.width - distance)
            if distance <= radius:
                return True
        return False

    def begin_tower_collapse(self, centre, generation=0):
        span = max(3, int(self.width * 0.022))
        shoulder = max(span + 1, int(self.width * 0.035))
        left = self.depths[(centre - shoulder) % self.width]
        right = self.depths[(centre + shoulder) % self.width]
        target = min(self.depths[centre], (left + right) * 0.5 + self.height * 0.015)
        self.tower_collapses.append(BankCollapse(centre, span, target, generation))
        self.tower_collapse_count += 1
        reset_radius = span * 2
        for offset in range(-reset_radius, reset_radius + 1):
            self.tower_ages[(centre + offset) % self.width] = 0.0

    def detect_tower_collapses(self, dt):
        if not self.args.accumulate or not self.args.tower_collapse:
            self.tower_ages = [0.0] * self.width
            return
        minimum = self.height * max(0.18, self.args.shed_to * 0.72)
        required = self.height * self.args.tower_prominence
        candidates = []
        for x in range(self.width):
            prominent = self.tower_prominence(x)
            unstable = self.depths[x] >= minimum and prominent >= required
            if unstable:
                self.tower_ages[x] += dt
                if self.tower_ages[x] >= self.tower_deadline(x):
                    candidates.append((self.tower_ages[x], prominent, x))
            else:
                self.tower_ages[x] = max(0.0, self.tower_ages[x] - dt * 0.65)

        # Start separated failures first. Limiting each scan prevents a dense
        # blizzard from turning every adjacent peak into the same event.
        exclusion = max(5, int(self.width * 0.045))
        for _, _, x in sorted(candidates, reverse=True):
            if len(self.tower_collapses) >= 6:
                break
            if not self.collapse_near(x, exclusion):
                self.begin_tower_collapse(x)

    def step_tower_collapses(self, dt):
        survivors = []
        completed = []
        reduction = self.height * self.args.tower_collapse_rate * dt
        for collapse in self.tower_collapses:
            removed = []
            complete = True
            half = max(1, collapse.span // 2)
            for offset in range(-half, half + 1):
                x = (collapse.centre + offset) % self.width
                edge = abs(offset) / half
                local_target = collapse.target + self.height * 0.012 * edge
                if self.depths[x] > local_target + 0.20:
                    complete = False
                    old = self.depths[x]
                    taper = max(0.30, 1.0 - edge * 0.62)
                    self.depths[x] = max(local_target, old - reduction * taper)
                    if old - self.depths[x] > 0.08:
                        removed.append((x, self.height - old))
            sample_step = max(1, len(removed) // 5)
            for x, y in removed[::sample_step][:6]:
                self.chunks.append(FallingChunk(
                    x=x, y=y,
                    speed=self.args.fall_speed * self.rng.uniform(1.0, 1.7),
                    drift=self.rng.uniform(-self.args.drift, self.args.drift),
                    shape=self.rng.choice(("tiny", "small", "medium")),
                    colour=self.rng.choice(self.palette["bank"][:2]),
                ))
            if complete:
                completed.append(collapse)
            else:
                survivors.append(collapse)
        self.tower_collapses = survivors

        # A finished slump can destabilise one nearby prominent tower. The
        # generation cap gives visible chain reactions without an endless wave.
        for collapse in completed:
            if collapse.generation >= 2 or self.rng.random() > self.args.tower_cascade_chance:
                continue
            radius = max(4, int(self.width * self.args.tower_cascade_radius))
            nearby = []
            for offset in range(-radius, radius + 1):
                if abs(offset) <= collapse.span:
                    continue
                x = (collapse.centre + offset) % self.width
                prominence = self.tower_prominence(x)
                if prominence >= self.height * self.args.tower_prominence * 0.70:
                    nearby.append((prominence, x))
            if nearby:
                _, x = max(nearby)
                if not self.collapse_near(x, max(3, collapse.span)):
                    self.begin_tower_collapse(x, collapse.generation + 1)

    def sync_runtime_options(self):
        """Apply mutable command options after a live-control update."""
        self.palette = PALETTES[self.args.palette]
        self.max_flakes = (self.args.max_flakes if self.args.max_flakes is not None
                           else max(120, self.width * self.height // 100))
        self.snow_rate = (self.args.snow_rate if self.args.snow_rate is not None
                          else max(24.0, self.width / 5.0))
        if len(self.flakes) > self.max_flakes:
            self.flakes = self.flakes[:self.max_flakes]
        if len(self.resting_snow) > self.args.object_snow_max:
            self.resting_snow = self.resting_snow[-self.args.object_snow_max:]
        if not self.physics.object_enabled:
            self.resting_snow = []
        self.sync_rabbits()
        self.sync_tumbleweeds()
        if not self.args.snow_plough:
            self.plough.active = False

    def sync_tumbleweeds(self, initial=False):
        ambient = effective_ambient(self.args, self.width)
        count = 0
        if "tumbleweed" in ambient:
            count = (self.args.tumbleweed_count
                     if self.args.tumbleweed_count is not None
                     else max(1, self.width // 700))
        while len(self.tumbleweeds) < count:
            index = len(self.tumbleweeds)
            rng = random.Random(self.args.seed + 20011 + index * 71)
            radius = max(4.0, min(13.0, self.height // 16 + index % 3))
            track = self.width + radius * 4
            x = rng.random() * track - radius * 2
            self.tumbleweeds.append(Tumbleweed(
                x=x, y=self.surface_y(x) - radius,
                direction=-1 if self.args.wind < 0 else 1,
                speed=self.args.ambient_speed * rng.uniform(0.42, 0.76),
                radius=radius, rotation=rng.uniform(0, math.tau),
                vertical_speed=0.0, blocked_time=0.0, collapse_cooldown=0.0,
                irregularity=tuple(rng.uniform(0.78, 1.16) for _ in range(20))))
        if len(self.tumbleweeds) > count:
            self.tumbleweeds = self.tumbleweeds[:count]

    def step_tumbleweeds(self, dt, elapsed):
        """Roll along reachable terrain; high snow faces block and load-collapse."""
        self.sync_tumbleweeds()
        gust = gust_at(self.args, elapsed)
        for weed in self.tumbleweeds:
            if abs(self.args.wind + gust) > 0.25:
                weed.direction = -1 if self.args.wind + gust < 0 else 1
            speed = max(0.0, weed.speed + abs(self.args.wind + gust) * 0.55)
            proposed_x = weed.x + weed.direction * speed * dt
            track = self.width + weed.radius * 4
            proposed_x = ((proposed_x + weed.radius * 2) % track) - weed.radius * 2
            current_support = self.surface_y(weed.x) - weed.radius
            next_support = self.surface_y(proposed_x) - weed.radius
            if not self.physics.ground_enabled:
                weed.x = proposed_x
                weed.y = next_support
                weed.rotation += weed.direction * speed * dt / max(1.0, weed.radius)
                weed.blocked_time = 0.0
                weed.vertical_speed = 0.0
                continue
            rise = current_support - next_support
            climb_limit = weed.radius * self.args.tumbleweed_climb
            weed.collapse_cooldown = max(0.0, weed.collapse_cooldown - dt)
            if rise > climb_limit:
                weed.blocked_time += dt
                self.tumbleweed_blocks += 1
                barrier_x = int(round(proposed_x)) % self.width
                pressure = self.args.tumbleweed_collapse_pressure
                radius = max(2, int(weed.radius * 0.65))
                for offset in range(-radius, radius + 1):
                    index = (barrier_x + offset) % self.width
                    self.tower_ages[index] += dt * pressure
                deadline = max(0.35, self.args.tower_age / max(1.0, pressure))
                if (self.args.tower_collapse and weed.collapse_cooldown <= 0 and
                        weed.blocked_time >= deadline and
                        not self.collapse_near(barrier_x, radius)):
                    self.begin_tower_collapse(barrier_x, generation=1)
                    self.tumbleweed_collapses += 1
                    weed.collapse_cooldown = max(1.0, self.args.tower_age)
                    weed.blocked_time = 0.0
                elif weed.blocked_time > deadline * 4:
                    weed.direction *= -1
                    weed.blocked_time = 0.0
                weed.vertical_speed = 0.0
                weed.y = current_support
                continue

            actual_dx = proposed_x - weed.x
            if abs(actual_dx) > self.width * 0.5:
                actual_dx = weed.direction * speed * dt
            weed.x = proposed_x
            weed.rotation += actual_dx / max(1.0, weed.radius)
            weed.blocked_time = max(0.0, weed.blocked_time - dt * 2.0)
            if next_support < weed.y:
                # A reachable uphill slope lifts the rolling contact point.
                weed.y = next_support
                weed.vertical_speed = 0.0
            else:
                # Downhill travel is gravity-limited instead of teleporting to
                # an arbitrarily lower surface at the new horizontal position.
                weed.vertical_speed += SeasonalPhysics.GRAVITY * 2.2 * dt
                weed.y += weed.vertical_speed * dt
                if weed.y >= next_support:
                    impact = weed.vertical_speed
                    weed.y = next_support
                    weed.vertical_speed = (-impact * 0.22
                                           if impact > 5.0 else 0.0)

    def step_santa_trail(self, dt, elapsed):
        survivors = []
        for particle in self.santa_trail:
            particle.ttl -= dt
            particle.y += SeasonalPhysics.GRAVITY * 0.018 * dt
            if particle.ttl > 0:
                survivors.append(particle)
        self.santa_trail = survivors
        event = current_sky_event(self.args, self, elapsed)
        if event is None or event[0] != "santa" or self.args.santa_trail_seconds <= 0:
            self.santa_trail_credit = 0.0
            return
        _, x, y, direction, event_index = event
        unit = santa_flyby_unit(self)
        sleigh_x = x - direction * 29 * unit
        self.santa_trail_credit += dt * 18.0
        count = min(4, int(self.santa_trail_credit))
        self.santa_trail_credit -= count
        for index in range(count):
            ttl = self.args.santa_trail_seconds * self.rng.uniform(0.65, 1.0)
            self.santa_trail.append(CometParticle(
                x=sleigh_x - direction * self.rng.uniform(13, 19) * unit,
                y=y + self.rng.uniform(-2.0, 3.0) * unit,
                ttl=ttl, maximum_ttl=ttl,
                colour_index=(event_index + index + len(self.santa_trail)) % 4))
        self.santa_trail = self.santa_trail[-240:]

    def sync_rabbits(self, initial=False):
        while len(self.rabbits) < self.args.rabbit_count:
            index = len(self.rabbits)
            rng = random.Random(self.args.seed + 32003 + index * 79)
            self.rabbits.append(Rabbit(
                x=-20.0, direction=1, state="hidden",
                timer=rng.uniform(2.0, max(2.1, self.args.rabbit_interval)),
                phase=rng.uniform(0, math.tau),
                hops_before_pause=rng.randint(3, 8),
            ))
        if len(self.rabbits) > self.args.rabbit_count:
            self.rabbits = self.rabbits[:self.args.rabbit_count]

    def hide_rabbit(self, rabbit):
        rabbit.state = "hidden"
        rabbit.timer = self.rng.uniform(self.args.rabbit_interval * 0.65,
                                        self.args.rabbit_interval * 1.35)

    def step_rabbits(self, dt, elapsed):
        tumbleweeds = tumbleweed_states(self.args, self, elapsed)
        for rabbit in self.rabbits:
            if rabbit.state == "hidden":
                rabbit.timer -= dt
                if rabbit.timer <= 0:
                    rabbit.direction = self.rng.choice((-1, 1))
                    rabbit.x = -12.0 if rabbit.direction > 0 else self.width + 12.0
                    rabbit.state = "hopping"
                    rabbit.phase = 0.0
                    rabbit.hops_before_pause = self.rng.randint(3, 8)
                continue

            old_cycle = int(rabbit.phase / math.tau)
            pace = self.args.rabbit_speed * (1.85 if rabbit.state == "startled" else 1.0)
            if rabbit.state != "eating":
                rabbit.x += rabbit.direction * pace * dt
                rabbit.phase += dt * (7.5 if rabbit.state == "startled" else 5.0)
            if int(rabbit.phase / math.tau) > old_cycle and rabbit.state == "hopping":
                rabbit.hops_before_pause -= 1
                if rabbit.hops_before_pause <= 0:
                    rabbit.state = "eating"
                    rabbit.timer = self.rng.uniform(2.0, 5.5)

            if rabbit.state == "eating":
                rabbit.timer -= dt
                if rabbit.timer <= 0:
                    rabbit.state = "hopping"
                    rabbit.hops_before_pause = self.rng.randint(3, 9)
            elif rabbit.state == "startled":
                rabbit.timer -= dt
                if rabbit.timer <= 0:
                    rabbit.state = "hopping"
                    rabbit.hops_before_pause = self.rng.randint(4, 8)

            threat_x = None
            for _, weed_x, _, radius, *_ in tumbleweeds:
                if abs(rabbit.x - weed_x) <= radius + 15:
                    threat_x = weed_x
                    break
            if self.plough.active and abs(rabbit.x - self.plough.x) < 30:
                threat_x = self.plough.x
            if threat_x is not None and rabbit.state != "startled":
                rabbit.state = "startled"
                rabbit.timer = self.rng.uniform(1.2, 2.4)
                rabbit.direction = -1 if threat_x > rabbit.x else 1
                self.rabbit_reactions += 1

            if rabbit.x < -20 or rabbit.x > self.width + 20:
                self.hide_rabbit(rabbit)

    def step_plough(self, dt):
        if not self.args.snow_plough:
            return
        plough = self.plough
        if not plough.active:
            plough.timer -= dt
            if plough.timer > 0:
                return
            plough.active = True
            plough.direction = self.rng.choice((-1, 1))
            plough.x = -24.0 if plough.direction > 0 else self.width + 24.0

        old_x = plough.x
        plough.x += plough.direction * self.args.plough_speed * dt
        plough.y = self.surface_y(plough.x) - 1
        start, end = sorted((int(old_x), int(plough.x + plough.direction * 8)))
        target = self.height * self.args.plough_clear_to
        for x in range(max(0, start), min(self.width, end + 1)):
            old = self.depths[x]
            self.depths[x] = min(old, target)
            if old - self.depths[x] > 2 and self.rng.random() < 0.08:
                self.chunks.append(FallingChunk(
                    x=x, y=self.height - old,
                    speed=self.args.fall_speed * self.rng.uniform(1.1, 2.0),
                    drift=-plough.direction * self.rng.uniform(2.0, 7.0),
                    shape=self.rng.choice(("small", "medium")),
                    colour=self.rng.choice(self.palette["bank"][:2]),
                ))
        if plough.x < -30 or plough.x > self.width + 30:
            # Finish the sweep cleanly: snow that fell behind the moving blade
            # during the pass must not leave an unexplained uncleared strip.
            self.depths = [min(depth, target) for depth in self.depths]
            plough.active = False
            plough.timer = self.rng.uniform(self.args.plough_interval * 0.75,
                                             self.args.plough_interval * 1.25)
            self.plough_count += 1

    def step(self, dt, elapsed):
        gust = 0.0
        if self.args.gust_strength and self.args.gust_period:
            gust = self.args.gust_strength * math.sin(math.tau * elapsed / self.args.gust_period)
        survivors = []
        for flake in self.flakes:
            old_y = flake.y
            flake.y += flake.speed * dt
            flake.x += (self.args.wind + gust + flake.drift +
                        math.sin(elapsed * flake.wobble + flake.phase) * self.args.wobble) * dt
            flake.x %= self.width
            lowest = max(y for _, y in SHAPES[flake.shape])
            scenery_y = self.scenery_hit(flake.x, old_y + lowest,
                                          flake.y + lowest)
            if scenery_y is not None and self.catch_object_snow(flake, scenery_y):
                continue
            if flake.y + lowest >= self.surface_y(flake.x):
                self.deposit(flake)
            elif flake.y < self.height + 5:
                survivors.append(flake)
        self.flakes = survivors
        self.spawn_credit += self.snow_rate * dt
        spawn = min(int(self.spawn_credit), self.max_flakes - len(self.flakes))
        if spawn > 0:
            self.flakes.extend(self.new_flake() for _ in range(spawn))
            self.spawn_credit -= spawn

        moved_chunks = []
        for chunk in self.chunks:
            chunk.y += chunk.speed * dt
            chunk.x = (chunk.x + (self.args.wind * 0.4 + chunk.drift) * dt) % self.width
            if chunk.y < self.height + 4:
                moved_chunks.append(chunk)
        self.chunks = moved_chunks[-180:]
        self.step_object_snow(dt)
        self.physics.relax_bank(self.depths, dt)

        self.shed_cooldown = max(0.0, self.shed_cooldown - dt)
        self.step_plough(dt)
        self.step_tumbleweeds(dt, elapsed)
        self.step_santa_trail(dt, elapsed)
        self.step_rabbits(dt, elapsed)
        if self.physics.ground_enabled:
            self.detect_tower_collapses(dt)
            self.step_tower_collapses(dt)
        else:
            self.tower_collapses = []
        if (self.args.accumulate and self.shedding is None and self.shed_cooldown == 0.0 and
                max(self.depths) / self.height >= self.args.shed_threshold):
            self.begin_shed()
        self.step_shed(dt)

    @property
    def maximum_depth_fraction(self):
        return max(self.depths) / self.height

    @property
    def average_depth_fraction(self):
        return sum(self.depths) / (self.width * self.height)


LIVE_OPTION_DESTS = frozenset({
    "fps", "physics", "snow_rate", "max_flakes", "flake_sizes", "size_weights",
    "fall_speed", "speed_variation", "wind", "gust_strength", "gust_period",
    "drift", "wobble", "palette", "accumulation", "accumulate",
    "snow_repose_slope", "snow_relaxation",
    "shed_threshold", "shed_to", "shed_width", "shed_rate",
    "tower_collapse", "tower_age", "tower_age_jitter", "tower_prominence",
    "tower_collapse_rate", "tower_cascade_chance", "tower_cascade_radius",
    "scenery", "cabin", "reindeer", "no_trees", "tree_density", "max_trees",
    "tree_sway", "tree_types", "tree_branches", "tree_branch_levels",
    "tree_branch_angle", "tree_length_ratio", "tree_trunk_thickness",
    "tree_thickness_exponent", "tree_segment_budget", "lights",
    "object_snow", "object_snow_capture", "object_snow_max",
    "object_snow_hold", "object_snow_hold_jitter", "object_snow_adhesion",
    "cabin_count", "max_cabins", "cabin_scale",
    "cabin_types", "cabin_size_variation",
    "ambient", "leaf_count", "tumbleweed_count", "ambient_speed",
    "tumbleweed_climb", "tumbleweed_collapse_pressure",
    "rabbit_count", "rabbit_interval", "rabbit_speed", "sky_events",
    "flyby_interval", "flyby_speed", "snow_plough", "plough_interval",
    "santa_scale", "santa_arc_height", "santa_trail_seconds",
    "plough_speed", "plough_clear_to",
    "scenery_set", "ambient_set",
})


class ControlListener:
    """Poll a versioned JSON file and atomically apply validated live options."""

    def __init__(self, path, poll_seconds):
        self.path = Path(path)
        self.poll_seconds = poll_seconds
        self.last_check = 0.0
        self.last_revision = None
        self.status = "WAIT"

    def poll(self, args, engine, force=False):
        now = time.monotonic()
        if not force and now - self.last_check < self.poll_seconds:
            return False
        self.last_check = now
        if not self.path.exists():
            self.status = "WAIT"
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("format") != CONTROL_FORMAT:
                raise ValueError(f"expected {CONTROL_FORMAT}")
            revision = payload.get("revision")
            if revision == self.last_revision:
                return False
            argv = payload.get("argv")
            if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
                raise ValueError("argv must be a list of strings")
            if any(item in ("-h", "--help") for item in argv):
                raise ValueError("help is not a live-control setting")
            with contextlib.redirect_stderr(io.StringIO()):
                controlled = parse_args(argv)
            if controlled.mode != args.mode:
                self.status = "RESTART:MODE"
                self.last_revision = revision
                return False
            for name in LIVE_OPTION_DESTS:
                setattr(args, name, getattr(controlled, name))
            engine.sync_runtime_options()
            self.last_revision = revision
            self.status = f"R{revision}"
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError, SystemExit):
            self.status = "ERROR"
            return False


def draw_shape(surface, shape, x, y, colour, priority):
    for dx, dy in SHAPES[shape]:
        surface.pixel(x + dx, y + dy, colour, priority)


def draw_accumulation(surface, engine):
    bank = engine.palette["bank"]
    for x, depth_value in enumerate(engine.depths):
        depth = max(0, min(engine.height, int(round(depth_value))))
        top = engine.height - depth
        for y in range(top, engine.height):
            below = y - top
            if below < 2:
                colour = bank[0]
            elif below < max(4, depth * 0.45):
                colour = bank[1]
            else:
                colour = bank[2]
            surface.pixel(x, y, colour, 70)


def draw_object_snow(surface, engine):
    for patch in engine.resting_snow:
        shape = "small" if patch.mass >= 1.8 else patch.shape
        draw_shape(surface, shape, patch.x, patch.y, patch.colour, 78)


def render_surface(background, engine):
    # Distant flybys are painted first and deliberately normalized to the
    # lowest depth. Scenery then replaces them pixel-for-pixel, so trees,
    # cabins, animals, banks and falling snow always occlude the sky objects.
    surface = Surface(background.width, background.height)
    draw_sky_event(surface, engine, getattr(engine, "elapsed", 0.0))
    surface.pixels = [(pixel[0], 3) if pixel is not None else None
                      for pixel in surface.pixels]
    for index, pixel in enumerate(background.pixels):
        if pixel is not None:
            surface.pixels[index] = pixel
    draw_accumulation(surface, engine)
    draw_object_snow(surface, engine)
    draw_ambient(surface, engine, getattr(engine, "elapsed", 0.0))
    for rabbit in engine.rabbits:
        draw_rabbit(surface, engine, rabbit)
    for chunk in engine.chunks:
        draw_shape(surface, chunk.shape, chunk.x, chunk.y, chunk.colour, 82)
    for flake in engine.flakes:
        draw_shape(surface, flake.shape, flake.x, flake.y, flake.colour, 90)
    draw_plough(surface, engine)
    return surface


def encode_surface(surface, codec, columns, rows, stats=None):
    """Encode visible depth samples as a foreground mask plus optional rear colour.

    The greatest per-pixel priority in a cell is its nearest layer. Those
    samples become the glyph foreground mask. A representative colour from the
    visible pixels behind it becomes the ANSI background only when doing so
    lowers the complete cell's RGB reconstruction error. Full cells remain
    ordinary foreground glyphs and reverse video is never emitted.
    """
    lines = []
    blank_cells = populated_cells = background_cells = 0
    masks_used = set()
    coloured_cells = set()
    part0_cells = part1_cells = 0
    active_colour = None
    active_background = None
    flat_bits = tuple(bit for row in codec.bits for bit in row)
    cell_sample_count = codec.cell_width * codec.cell_height
    full_mask = (1 << cell_sample_count) - 1
    pixels = surface.pixels
    surface_width = surface.width
    for cell_y in range(rows):
        parts = []
        for cell_x in range(columns):
            cell_pixels = []
            for local_y in range(codec.cell_height):
                y = cell_y * codec.cell_height + local_y
                start = y * surface_width + cell_x * codec.cell_width
                cell_pixels.extend(pixels[start:start + codec.cell_width])
            if not any(cell_pixels):
                blank_cells += 1
                if active_colour is not None:
                    parts.append(FG_DEFAULT)
                    active_colour = None
                if active_background is not None:
                    parts.append("\x1b[49m")
                    active_background = None
                parts.append(" ")
                continue

            first_pixel = cell_pixels[0]
            uniform = (first_pixel is not None and
                       all(pixel == first_pixel for pixel in cell_pixels[1:]))
            if uniform:
                mask = full_mask
                front_priority = first_pixel[1]
                colour = first_pixel[0]
                front_count = cell_sample_count
                rear_count = 0
            else:
                front_priority = max(pixel[1] for pixel in cell_pixels
                                     if pixel is not None)
                mask = 0
                front_count = rear_count = 0
                front_red = front_green = front_blue = 0
                rear_red = rear_green = rear_blue = 0
                for bit, pixel in zip(flat_bits, cell_pixels):
                    if pixel is None:
                        continue
                    sample_colour, priority = pixel
                    if priority == front_priority:
                        mask |= 1 << bit
                        front_count += 1
                        front_red += sample_colour[0]
                        front_green += sample_colour[1]
                        front_blue += sample_colour[2]
                    else:
                        rear_count += 1
                        rear_red += sample_colour[0]
                        rear_green += sample_colour[1]
                        rear_blue += sample_colour[2]
                colour = (round(front_red / front_count),
                          round(front_green / front_count),
                          round(front_blue / front_count))

            background = None
            if rear_count and front_count < cell_sample_count:
                rear_colour = (round(rear_red / rear_count),
                               round(rear_green / rear_count),
                               round(rear_blue / rear_count))
                error_without = 0
                error_with = 0
                for pixel in cell_pixels:
                    expected = (0, 0, 0) if pixel is None else pixel[0]
                    if pixel is not None and pixel[1] == front_priority:
                        actual_without = actual_with = colour
                    else:
                        actual_without = (0, 0, 0)
                        actual_with = rear_colour
                    red = expected[0] - actual_without[0]
                    green = expected[1] - actual_without[1]
                    blue = expected[2] - actual_without[2]
                    error_without += red * red + green * green + blue * blue
                    red = expected[0] - actual_with[0]
                    green = expected[1] - actual_with[1]
                    blue = expected[2] - actual_with[2]
                    error_with += red * red + green * green + blue * blue
                if error_with < error_without:
                    background = rear_colour

            quantized = tuple((channel // 4) * 4 for channel in colour)
            if quantized != active_colour:
                parts.append("\x1b[38;2;%d;%d;%dm" % quantized)
                active_colour = quantized
            quantized_background = (tuple((channel // 4) * 4 for channel in background)
                                    if background is not None else None)
            populated_cells += 1
            masks_used.add(mask)
            coloured_cells.add((mask, quantized, quantized_background))
            if quantized_background is not None:
                background_cells += 1
            if codec.name == "pua4":
                if mask < 0x8000:
                    part0_cells += 1
                else:
                    part1_cells += 1
            if quantized_background != active_background:
                if quantized_background is None:
                    parts.append("\x1b[49m")
                else:
                    parts.append("\x1b[48;2;%d;%d;%dm" % quantized_background)
                active_background = quantized_background
            parts.append(chr(codec.codepoint(mask)))
        parts.append(RESET)
        active_colour = None
        active_background = None
        lines.append("".join(parts))
    if stats is not None:
        stats.update({
            "cells": columns * rows,
            "blank_cells": blank_cells,
            "populated_cells": populated_cells,
            "background_cells": background_cells,
            "unique_masks": len(masks_used),
            "reused_masks": max(0, populated_cells - len(masks_used)),
            "unique_coloured_cells": len(coloured_cells),
            "part0_cells": part0_cells,
            "part1_cells": part1_cells,
            "mask_values": masks_used,
        })
    return "\n".join(lines)


def dashboard_rows(args):
    if args.no_dashboard:
        return 0
    return 6 if args.detailed_dashboard else 1


def graph_bar(value, total, width=16):
    fraction = 0.0 if total <= 0 else max(0.0, min(1.0, value / total))
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


def process_telemetry(engine):
    """Return low-overhead process CPU and peak-resident-memory telemetry."""
    now = time.monotonic()
    cpu_now = time.process_time()
    wall_delta = now - engine.telemetry_wall
    if wall_delta >= 0.25:
        engine.cpu_percent = max(
            0.0, 100.0 * (cpu_now - engine.telemetry_cpu) / wall_delta)
        engine.telemetry_wall = now
        engine.telemetry_cpu = cpu_now
    peak_mib = None
    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
        peak_mib = usage / divisor
    return engine.cpu_percent, peak_mib


DASHBOARD_TABS = ("font", "snow", "trees", "animals", "flights", "process")


def dashboard_tab_strip(engine):
    labels = []
    for index, name in enumerate(DASHBOARD_TABS):
        label = name.upper()
        labels.append(f"[{label}]" if index == engine.dashboard_tab else label)
    return " ↹ TAB  " + "  ·  ".join(labels)


def detailed_dashboard_lines(args, engine, codec, stats, columns):
    defined = 256 if codec.name == "square" else 65536
    populated = stats["populated_cells"]
    unique_masks = stats["unique_masks"]
    cpu_percent, peak_mib = process_telemetry(engine)
    frame_budget = 1000.0 / max(0.001, args.fps)
    memory = f"{peak_mib:,.1f} MiB PEAK RSS" if peak_mib is not None else "UNAVAILABLE"
    tab = DASHBOARD_TABS[engine.dashboard_tab]
    if tab == "font":
        page = [
            (f" ◆ FONT {'UNICODE BRAILLE U+2800..U+28FF' if codec.name == 'square' else 'PUA4 PART0+PART1'} | "
             f"SOURCE STATIC/PREBUILT | AVAILABLE {defined:,}"),
            (f" ◆ RUNTIME REDEFINED 0/{defined:,} {graph_bar(0, defined)} | "
             "DYNAMICALLY CREATED FOR THIS ANIMATION 0"),
            (f" ◆ UNIQUE GLYPHS CURRENT FRAME {unique_masks:,} | SEEN SINCE START {len(engine.glyphs_seen):,} | "
             f"STATIC UNUSED THIS FRAME {defined - unique_masks:,} {graph_bar(unique_masks, defined)}"),
            (f" ◆ CELLS {stats['cells']:,} ACTIVE {populated:,} BLANK {stats['blank_cells']:,} | "
             f"DEDUP/REUSED {stats['reused_masks']:,} "
             f"{graph_bar(stats['reused_masks'], max(1, populated))} | "
             f"COLOURED COMBINATIONS {stats['unique_coloured_cells']:,}"),
        ]
    elif tab == "snow":
        page = [
            (f" ⚙ PHYSICS {args.physics.upper()} | ❄ AIRBORNE {len(engine.flakes):,}/{engine.max_flakes:,} | RATE {engine.snow_rate:.1f}/s | "
             f"FALL {args.fall_speed:.1f} VPX/s | WIND {args.wind:+.1f} GUST {args.gust_strength:.1f}"),
            (f" ▂ GROUND MAX {engine.maximum_depth_fraction:.1%} AVG {engine.average_depth_fraction:.1%} | "
             f"ACCUMULATION {args.accumulation:.2f} | REPOSE {args.snow_repose_slope:.2f} RELAX {args.snow_relaxation:.1f}"),
            (f" ⇣ BROAD SHEDS {engine.shed_count} | LOCAL TOWERS {engine.tower_collapse_count} | "
             f"ACTIVE SLUMPS {len(engine.tower_collapses)} | FALLING CHUNKS {len(engine.chunks)}"),
            (f" ❅ OBJECT PATCHES {len(engine.resting_snow):,}/{args.object_snow_max:,} | "
             f"CAUGHT {engine.object_snow_caught:,} SHED {engine.object_snow_shed:,} | "
             f"CAPTURE {args.object_snow_capture:.0%} ADHESION {args.object_snow_adhesion:.2f}"),
        ]
    elif tab == "trees":
        page = [
            f" ♣ TYPES {','.join(args.tree_types).upper()} | DENSITY {args.tree_density:.2f} MAX TREES {args.max_trees}",
            (f" Y PRIMARY/WHORLS {args.tree_branches} | RECURSION {args.tree_branch_levels} | "
             f"ANGLE {args.tree_branch_angle:.1f}° | CHILD LENGTH {args.tree_length_ratio:.2f}"),
            (f" ┃ TRUNK {args.tree_trunk_thickness:.2f} VPX | TAPER EXPONENT {args.tree_thickness_exponent:.2f} | "
             f"SEGMENT BUDGET {args.tree_segment_budget:,}"),
            (f" 〰 SWAY {args.tree_sway:.2f} | LIGHTS {args.lights:.2f} | "
             f"OBJECT SNOW {'ON' if args.object_snow else 'OFF'} (SPARSE, MASS-SHED)"),
        ]
    elif tab == "animals":
        visible_rabbits = sum(r.state != "hidden" for r in engine.rabbits)
        states = ",".join(r.state for r in engine.rabbits if r.state != "hidden") or "hidden"
        page = [
            f" ♙ RABBITS {visible_rabbits}/{len(engine.rabbits)} | STATES {states} | REACTIONS {engine.rabbit_reactions}",
            f" ↔ INTERVAL {args.rabbit_interval:.1f}s | SPEED {args.rabbit_speed:.1f} VPX/s | TERRAIN FOLLOWING ON",
            (f" ♞ FOREGROUND REINDEER {'ON' if 'reindeer' in args.scenery_set else 'OFF'} | "
             "NEAR/FAR DEPTH SHADING | SCENERY OCCLUSION ON"),
            (f" ✺ TUMBLEWEEDS {len(engine.tumbleweeds)} | BLOCKS {engine.tumbleweed_blocks} | "
             f"PRESSURE COLLAPSES {engine.tumbleweed_collapses} | CLIMB {args.tumbleweed_climb:.2f}")
        ]
    elif tab == "flights":
        event = current_sky_event(args, engine, getattr(engine, "elapsed", 0.0))
        current = "NONE" if event is None else f"{event[0].upper()} #{event[4]}"
        page = [
            f" ✈ ROTATION {','.join(args.sky_events).upper() or 'NONE'} | CURRENT {current}",
            f" → FLYBY SPEED {args.flyby_speed:.1f} VPX/s | QUIET INTERVAL {args.flyby_interval:.1f}s",
            (f" ☄ SANTA SCALE {args.santa_scale:.2f} | ARC {args.santa_arc_height:.0%} HEIGHT | "
             f"TRAIL {args.santa_trail_seconds:.1f}s / {len(engine.santa_trail)} SPARKS"),
            (f" ◇ DISTANT/OCCLUDED BY SCENERY AND SNOW | PLOUGH "
             f"{'ACTIVE' if engine.plough.active else 'WAITING'} / {engine.plough_count} COMPLETE"),
        ]
    else:
        cache = cached_tree_pixels.cache_info()
        page = [
            (f" ◆ PROCESS CPU {cpu_percent:5.1f}% {graph_bar(cpu_percent, 100)} | "
             f"FRAME {engine.render_ms:6.1f} ms / {frame_budget:5.1f} ms "
             f"{graph_bar(engine.render_ms, frame_budget)}"),
            f" ◆ MEMORY {memory} | GRID CELLS {stats['cells']:,} | ACTIVE {populated:,}",
            (f" ◆ LOAD: FLAKES {len(engine.flakes):,} TREES≤{args.max_trees} "
             f"TREE CACHE {cache.hits:,} HIT/{cache.misses:,} MISS | OBJECT PATCHES {len(engine.resting_snow):,}"),
            " ◆ PERFORMANCE: LOWER FPS/PARTICLES/BRANCH DEPTH/BUDGET OR TERMINAL DIMENSIONS IF OVER BUDGET",
        ]
    lines = [dashboard_tab_strip(engine), *page]
    colours = ("\x1b[38;2;75;225;240m", "\x1b[38;2;255;182;72m",
               "\x1b[38;2;120;190;255m", "\x1b[38;2;255;105;190m",
               "\x1b[38;2;88;220;168m")
    return [colour + line[:columns].ljust(columns) + RESET
            for colour, line in zip(colours, lines)]


def status_line(args, engine, columns, frame):
    codes = "".join(code for name, code in (("trees", "T"), ("cabin", "C"),
                                              ("reindeer", "R"))
                    if name in args.scenery_set) or "-"
    if engine.shedding:
        state = "SHED"
    elif engine.tower_collapses:
        state = f"SLUMP×{len(engine.tower_collapses)}"
    else:
        state = "ACCUM"
    control = f"LIVE {args.control_status}" if args.listen else "LIVE OFF"
    total_rows = engine.height // CODECS[args.mode].cell_height
    total_rows += dashboard_rows(args)
    if columns >= 150:
        text = (f" CHRISTMAS SNOW [{args.mode.upper()}] | 2CLR=ON GROUND=FIXED | "
                f"GRID {columns}x{total_rows} | {control} | "
                f"MAX {engine.maximum_depth_fraction:5.1%} AVG {engine.average_depth_fraction:5.1%} | "
                f"FLAKES {len(engine.flakes):4d} | WIND {args.wind:+.1f} GUST {args.gust_strength:.1f} | "
                f"SCENE {codes} | {state} | "
                f"SHEDS {engine.shed_count} TOWERS {engine.tower_collapse_count} | F {frame}")
    elif columns >= 92:
        text = (f" SNOW {args.mode.upper()} | GRID {columns}x{total_rows} | 2CLR GND=FIXED | "
                f"{control} | DEPTH {engine.maximum_depth_fraction:.0%}/{engine.average_depth_fraction:.0%} | "
                f"FLK {len(engine.flakes)} W {args.wind:+.1f} G {args.gust_strength:.1f} | "
                f"{state} S{engine.shed_count} T{engine.tower_collapse_count} F{frame}")
    else:
        live_short = args.control_status if args.listen else "OFF"
        text = (f" SNOW {args.mode.upper()} {columns}x{total_rows} | 2CLR GND | L:{live_short} | "
                f"D {engine.maximum_depth_fraction:.0%}/{engine.average_depth_fraction:.0%} "
                f"FLK{len(engine.flakes)} W{args.wind:+.1f} | "
                f"S{engine.shed_count} T{engine.tower_collapse_count} F{frame}")
    return "\x1b[38;2;75;225;240m" + text[:columns].ljust(columns) + RESET


def terminal_size(args):
    actual = shutil.get_terminal_size((100, 30))
    columns = args.columns or actual.columns
    rows = args.rows or actual.lines
    if columns < 24 or rows < 8:
        raise SystemExit("terminal must be at least 24 columns by 8 rows")
    return columns, rows


def make_runtime(args, columns, rows):
    codec = CODECS[args.mode]
    scene_rows = rows - dashboard_rows(args)
    width = columns * codec.cell_width
    height = scene_rows * codec.cell_height
    engine = SnowEngine(args, width, height)
    background = build_scenery(args, width, height, engine.scenery_ground_y)
    engine.update_scenery_collision(background)
    return codec, scene_rows, engine, background


def complete_frame(args, codec, scene_rows, engine, background, columns, frame,
                   elapsed=0.0):
    engine.elapsed = elapsed
    stats = {}
    render_started = time.perf_counter()
    picture = encode_surface(render_surface(background, engine), codec, columns,
                             scene_rows, stats)
    engine.glyphs_seen.update(stats["mask_values"])
    engine.render_ms = (time.perf_counter() - render_started) * 1000.0
    if args.no_dashboard:
        return picture
    dashboard = [status_line(args, engine, columns, frame)]
    if args.detailed_dashboard:
        dashboard.extend(detailed_dashboard_lines(args, engine, codec, stats, columns))
    return "\n".join(dashboard) + "\n" + picture


@contextlib.contextmanager
def terminal_keyboard_mode():
    """Temporarily enable immediate keys without persisting terminal changes."""
    if os.name == "nt" or not sys.stdin.isatty():
        yield
        return
    import termios
    import tty
    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def poll_terminal_key():
    if not sys.stdin.isatty():
        return None
    if os.name == "nt":
        import msvcrt
        return msvcrt.getwch() if msvcrt.kbhit() else None
    import select
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    return sys.stdin.read(1) if ready else None


def animate(args):
    columns, rows = terminal_size(args)
    codec, scene_rows, engine, background = make_runtime(args, columns, rows)
    if args.snapshot:
        sys.stdout.write(complete_frame(args, codec, scene_rows, engine, background,
                                        columns, 0, 0.0) + RESET + "\n")
        return

    listener = ControlListener(args.listen, args.control_poll) if args.listen else None
    args.control_status = "WAIT"
    if listener:
        listener.poll(args, engine, force=True)
        args.control_status = listener.status
    elapsed = 0.0
    deadline = time.monotonic()
    frame = 0
    sys.stdout.write("\x1b]0;Christmas Snow Lab\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    keyboard_context = terminal_keyboard_mode()
    keyboard_context.__enter__()
    try:
        while True:
            key = poll_terminal_key()
            if key == "\t" and args.detailed_dashboard:
                engine.dashboard_tab = (engine.dashboard_tab + 1) % len(DASHBOARD_TABS)
            elif key in ("q", "Q", "\x1b"):
                break
            if args.frames and frame >= args.frames:
                break
            if args.duration and elapsed >= args.duration:
                break
            if listener:
                listener.poll(args, engine)
                args.control_status = listener.status
            dt = 1.0 / args.fps
            deadline += dt
            resized = False
            next_columns, next_rows = terminal_size(args)
            if (next_columns, next_rows) != (columns, rows):
                columns, rows = next_columns, next_rows
                scene_rows = rows - dashboard_rows(args)
                engine.resize(columns * codec.cell_width,
                              scene_rows * codec.cell_height)
                resized = True
            engine.step(dt, elapsed)
            background = build_scenery(args, engine.width, engine.height,
                                       engine.scenery_ground_y, elapsed)
            engine.update_scenery_collision(background)
            output = complete_frame(args, codec, scene_rows, engine, background,
                                    columns, frame, elapsed)
            clear = "\x1b[2J" if resized else ""
            sys.stdout.write("\x1b[?2026h" + clear + "\x1b[H" + output + "\x1b[?2026l")
            sys.stdout.flush()
            frame += 1
            elapsed += dt
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1.0:
                # A large resize or live FPS change should not leave scheduling
                # permanently behind the wall clock.
                deadline = time.monotonic()
    finally:
        keyboard_context.__exit__(*sys.exc_info())
        sys.stdout.write(RESET + "\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def comma_list(value):
    values = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    unknown = set(values) - set(SHAPES)
    if not values or unknown:
        raise argparse.ArgumentTypeError(
            "flake sizes must be a comma list drawn from tiny,small,medium,large")
    return values


def weight_list(value):
    try:
        weights = tuple(float(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("size weights must be comma-separated numbers") from error
    if not weights or any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise argparse.ArgumentTypeError("size weights must be non-negative and not all zero")
    return weights


def count_or_auto(value):
    if value.lower() == "auto":
        return None
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected 'auto' or a whole number") from error
    if count < 0:
        raise argparse.ArgumentTypeError("count cannot be negative")
    return count


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=False,
    )
    display = parser.add_argument_group("display and reproducibility")
    display.add_argument("-h", "--help", action="store_true",
                         help="show this illustrated guide and every option")
    display.add_argument("--mode", choices=tuple(CODECS), default="pua4",
                         help="glyph technology: Square Braille 2x4 or PUA 4x4")
    display.add_argument("--fps", type=float, default=20.0,
                         help="requested animation frames per second; reduce for huge grids")
    display.add_argument("--duration", type=float, default=0.0,
                         help="seconds to run; 0 runs until interrupted")
    display.add_argument("--frames", type=int, default=0,
                         help="exact frame count; 0 uses duration/unlimited")
    display.add_argument("--columns", type=int,
                         help="fixed internal cell width; omit to follow live terminal width")
    display.add_argument("--rows", type=int,
                         help="fixed internal cell height; omit to follow live terminal height")
    display.add_argument("--seed", type=int, default=1225,
                         help="repeatable random seed for scenery, flakes and ambient motion")
    display.add_argument("--snapshot", action="store_true",
                         help="print one frame and exit; macOS launcher holds it for inspection")
    display.add_argument("--no-dashboard", action="store_true",
                         help="give the status row back to the rendered scene")
    display.add_argument("--detailed-dashboard", action="store_true",
                         help="reserve six rows for keyboard-tabbed font, snow, tree, animal, flight and process telemetry")
    display.add_argument("--physics", choices=("none", "ground", "full"),
                         default="full",
                         help="none: legacy simple snow; ground: bank slumping and terrain bodies; full: also retain snow on scenery")

    live = parser.add_argument_group("live control")
    live.add_argument("--listen", nargs="?", const=str(DEFAULT_CONTROL_PATH),
                      metavar="JSON_PATH",
                      help="watch a TUI-written JSON control file; omit the path for the shared default")
    live.add_argument("--control-poll", type=float, default=0.20,
                      help="seconds between checks of the live-control file")

    snow = parser.add_argument_group("falling snow")
    snow.add_argument("--snow-rate", type=float,
                      help="new flakes per second; default scales with width")
    snow.add_argument("--max-flakes", type=int,
                      help="active-particle ceiling; default scales with area")
    snow.add_argument("--preload-seconds", type=float, default=4.0,
                      help="initial on-screen snowfall population")
    snow.add_argument("--flake-sizes", type=comma_list,
                      default=comma_list("tiny,small,medium,large"),
                      help="comma list of geometric flake shapes to use")
    snow.add_argument("--size-weights", type=weight_list,
                      default=weight_list("55,28,13,4"),
                      help="relative weights corresponding to --flake-sizes")
    snow.add_argument("--fall-speed", type=float, default=18.0,
                      help="mean vertical virtual pixels per second")
    snow.add_argument("--speed-variation", type=float, default=0.35,
                      help="fractional random speed variation")
    snow.add_argument("--wind", type=float, default=0.8,
                      help="steady horizontal virtual pixels per second")
    snow.add_argument("--gust-strength", type=float, default=2.4,
                      help="sinusoidal gust amplitude in virtual pixels/second")
    snow.add_argument("--gust-period", type=float, default=7.0,
                      help="seconds per gust cycle")
    snow.add_argument("--drift", type=float, default=1.5,
                      help="per-flake random horizontal drift range")
    snow.add_argument("--wobble", type=float, default=1.1,
                      help="per-flake sideways flutter amplitude")
    snow.add_argument("--palette", choices=tuple(PALETTES), default="christmas",
                      help="true-colour snow and accumulated-bank colour family")

    banks = parser.add_argument_group("accumulation and shedding")
    banks.add_argument("--initial-snow", type=float, default=0.12,
                       help="initial bank depth as fraction of scene height")
    banks.add_argument("--bank-drift", type=float, default=0.035,
                       help="initial uneven-bank amplitude as fraction of height")
    banks.add_argument("--accumulation", "--accumulation-rate",
                       dest="accumulation", type=float, default=2.4,
                       help="virtual-pixel deposit multiplier per settled flake")
    banks.add_argument("--snow-repose-slope", type=float, default=1.15,
                       help="maximum adjacent bank-height difference before snow slumps")
    banks.add_argument("--snow-relaxation", type=float, default=9.0,
                       help="maximum virtual pixels of excess bank slope moved per second")
    banks.add_argument("--no-accumulation", dest="accumulate", action="store_false",
                       help="let flakes fall without adding them to the snow bank")
    banks.set_defaults(accumulate=True)
    banks.add_argument("--shed-threshold", type=float, default=0.50,
                       help="maximum bank fraction that triggers a fall-away")
    banks.add_argument("--shed-to", type=float, default=0.36,
                       help="local bank fraction after a fall-away")
    banks.add_argument("--shed-width", type=float, default=0.28,
                       help="fraction of display width affected by a fall-away")
    banks.add_argument("--shed-rate", type=float, default=0.22,
                       help="fraction of scene height removed per second")
    banks.add_argument("--tower-collapse", action=argparse.BooleanOptionalAction,
                       default=True,
                       help="age and collapse narrow local snow towers")
    banks.add_argument("--tower-age", type=float, default=4.0,
                       help="minimum seconds an unstable tower survives before collapsing")
    banks.add_argument("--tower-age-jitter", type=float, default=3.0,
                       help="repeatable random seconds added to each tower lifetime")
    banks.add_argument("--tower-prominence", type=float, default=0.08,
                       help="height above nearby snow, as scene fraction, considered a tower")
    banks.add_argument("--tower-collapse-rate", type=float, default=0.55,
                       help="scene-height fraction removed per second during a local collapse")
    banks.add_argument("--tower-cascade-chance", type=float, default=0.38,
                       help="chance that a completed collapse destabilises a nearby tower")
    banks.add_argument("--tower-cascade-radius", type=float, default=0.10,
                       help="display-width fraction searched for a cascading collapse")

    scenery = parser.add_argument_group("seasonal scenery")
    scenery.add_argument("--scenery", default="trees",
                         help="none, trees, cabin, reindeer, all, or a comma list")
    scenery.add_argument("--cabin", action="store_true",
                         help="add a warm cabin to any scenery selection")
    scenery.add_argument("--reindeer", action="store_true",
                         help="add a reindeer to any scenery selection")
    scenery.add_argument("--no-trees", action="store_true",
                         help="remove trees from the selected scenery")
    scenery.add_argument("--tree-density", type=float, default=0.72,
                         help="trees per unit of virtual width; 0 leaves other scenery intact")
    scenery.add_argument("--max-trees", type=int, default=96,
                         help="total animated-tree ceiling for very wide terminals")
    scenery.add_argument("--tree-sway", type=float, default=1.4,
                         help="maximum still-air treetop bend in virtual pixels")
    scenery.add_argument("--tree-types", type=tree_type_list,
                         default=tree_type_list("all"),
                         help="auto/all or comma list: pine,fir,spruce,oak,maple,birch")
    scenery.add_argument("--tree-branches", type=int, default=5,
                         help="primary crown branches or conifer branch whorls per tree")
    scenery.add_argument("--tree-branch-levels", type=int, default=3,
                         help="recursive daughter-branch generations for oak, maple and birch")
    scenery.add_argument("--tree-branch-angle", type=float, default=27.0,
                         help="daughter-branch divergence angle in degrees")
    scenery.add_argument("--tree-length-ratio", type=float, default=0.68,
                         help="daughter length divided by parent length")
    scenery.add_argument("--tree-trunk-thickness", type=float, default=2.2,
                         help="base procedural trunk thickness in virtual pixels")
    scenery.add_argument("--tree-thickness-exponent", type=float, default=2.0,
                         help="branch area exponent; 2 applies Leonardo area preservation")
    scenery.add_argument("--tree-segment-budget", type=int, default=12000,
                         help="frame-wide cap on formula branch segments for predictable cost")
    scenery.add_argument("--lights", type=float, default=0.32,
                         help="decorative lights per foreground-tree height")
    scenery.add_argument("--object-snow", action=argparse.BooleanOptionalAction,
                         default=True,
                         help="let a sparse fraction of flakes rest temporarily on scenery")
    scenery.add_argument("--object-snow-capture", type=float, default=0.08,
                         help="chance [0,1] that a scenery-surface impact is retained")
    scenery.add_argument("--object-snow-max", type=int, default=240,
                         help="maximum separate resting-snow patches on scenery")
    scenery.add_argument("--object-snow-hold", type=float, default=7.0,
                         help="mean seconds before retained snow loses its hold")
    scenery.add_argument("--object-snow-hold-jitter", type=float, default=5.0,
                         help="random plus/minus variation in scenery-snow hold time")
    scenery.add_argument("--object-snow-adhesion", type=float, default=3.2,
                         help="flake-equivalent supported mass before gravity sheds a patch")
    scenery.add_argument("--cabin-count", type=count_or_auto, default=None,
                         metavar="AUTO|N",
                         help="cabins to distribute across the scene; auto responds to width")
    scenery.add_argument("--max-cabins", type=int, default=4,
                         help="upper limit used only by automatic cabin distribution")
    scenery.add_argument("--cabin-scale", type=float, default=1.0,
                         help="fixed-aspect cabin size relative to scene height")
    scenery.add_argument("--cabin-types", type=cabin_type_list,
                         default=cabin_type_list("cottage,lodge,a-frame"),
                         help="comma list of deterministic cabin archetypes")
    scenery.add_argument("--cabin-size-variation", type=float, default=0.28,
                         help="fractional size variation among complete cabins")
    scenery.add_argument("--ambient", default="auto",
                         help="auto, none, leaves, tumbleweed, all, or a comma list")
    scenery.add_argument("--leaf-count", type=int,
                         help="moving leaf count; default scales with viewport area")
    scenery.add_argument("--tumbleweed-count", type=int,
                         help="rolling tumbleweed count; default scales with width")
    scenery.add_argument("--ambient-speed", type=float, default=8.0,
                         help="base leaf/tumbleweed virtual pixels per second")
    scenery.add_argument("--tumbleweed-climb", type=float, default=0.72,
                         help="maximum climb as a fraction of tumbleweed radius")
    scenery.add_argument("--tumbleweed-collapse-pressure", type=float, default=4.0,
                         help="tower-age multiplier while a tumbleweed presses a snow wall")

    events = parser.add_argument_group("wildlife and occasional events")
    events.add_argument("--rabbit-count", type=int, default=1,
                        help="terrain-following rabbits; 0 disables them")
    events.add_argument("--rabbit-interval", type=float, default=28.0,
                        help="approximate hidden time between rabbit appearances")
    events.add_argument("--rabbit-speed", type=float, default=13.0,
                        help="rabbit travel speed in virtual pixels per second")
    events.add_argument("--sky-events", type=sky_event_list,
                        default=sky_event_list("auto"),
                        help="none, auto/all, or comma list: aeroplane,ufo,santa")
    events.add_argument("--flyby-interval", type=float, default=48.0,
                        help="quiet seconds between occasional sky crossings")
    events.add_argument("--flyby-speed", type=float, default=32.0,
                        help="sky-event horizontal virtual pixels per second")
    events.add_argument("--santa-scale", type=float, default=0.50,
                        help="Santa formation scale relative to its original design")
    events.add_argument("--santa-arc-height", type=float, default=0.16,
                        help="Santa arc rise as a fraction of scene height")
    events.add_argument("--santa-trail-seconds", type=float, default=2.8,
                        help="seconds before each Santa comet-trail spark fades")
    events.add_argument("--snow-plough", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="occasionally drive across and clear the accumulated bank")
    events.add_argument("--plough-interval", type=float, default=95.0,
                        help="approximate quiet seconds between snow-plough passes")
    events.add_argument("--plough-speed", type=float, default=22.0,
                        help="snow-plough virtual pixels per second")
    events.add_argument("--plough-clear-to", type=float, default=0.025,
                        help="snow depth fraction left after a complete plough pass")

    return parser


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def help_snow_preview(mode, count, columns=30, rows=5):
    """Render an exact number of live Flake objects with the production codec."""
    codec = CODECS[mode]
    width = columns * codec.cell_width
    height = rows * codec.cell_height
    surface = Surface(width, height)
    per_row = max(1, min(count, int(math.ceil(math.sqrt(count * width / height)))))
    row_count = max(1, int(math.ceil(count / per_row)))
    colours = PALETTES["christmas"]["snow"]
    names = ("tiny", "small", "medium", "large")
    flakes = []
    for index in range(count):
        column = index % per_row
        row = index // per_row
        x = (column + 0.5) * width / per_row
        y = (row + 0.5) * height / row_count
        flakes.append(Flake(x, y, 0.0, 0.0, 0.0, 0.0,
                            names[index % len(names)],
                            colours[index % len(colours)]))
    for flake in flakes:
        draw_shape(surface, flake.shape, flake.x, flake.y, flake.colour, 90)
    return encode_surface(surface, codec, columns, rows)


def help_scene_preview(parser, mode, scenery, ambient, elapsed=0.0,
                       columns=30, rows=7, cabin_count=None):
    """Render a real deterministic scene panel for the illustrated help."""
    args = parser.parse_args(["--mode", mode])
    args.scenery_set = frozenset(scenery)
    args.ambient_set = frozenset(ambient)
    args.cabin_count = cabin_count
    args.snow_rate = 0
    args.max_flakes = 0
    args.preload_seconds = 0
    if ambient:
        args.tumbleweed_count = 1
        args.wind = 6.0
        args.gust_strength = 5.0
        args.ambient_speed = 12.0
    codec = CODECS[mode]
    engine = SnowEngine(args, columns * codec.cell_width, rows * codec.cell_height)
    background = build_scenery(args, engine.width, engine.height,
                               engine.scenery_ground_y, elapsed)
    engine.elapsed = elapsed
    return encode_surface(render_surface(background, engine), codec, columns, rows)


def action_usage(action):
    label = ", ".join(action.option_strings)
    if action.nargs == 0:
        return label
    if action.choices:
        value = "{" + ",".join(str(choice) for choice in action.choices) + "}"
    else:
        value = action.metavar or action.dest.upper()
    return f"{label} {value}"


def pretty_help(parser, mode, colour=True):
    """Build colourful, self-updating help from the parser's real actions."""
    tone = {
        "cyan": "\x1b[38;2;40;220;240m",
        "green": "\x1b[38;2;70;230;145m",
        "amber": "\x1b[38;2;255;190;60m",
        "pink": "\x1b[38;2;255;105;190m",
        "white": "\x1b[38;2;235;240;245m",
        "dim": "\x1b[38;2;135;165;180m",
    }

    def paint(name, value):
        return (tone[name] + value + RESET) if colour else value

    width = max(78, min(118, shutil.get_terminal_size((100, 30)).columns))
    lines = [
        paint("cyan", "╭" + "─" * (width - 2) + "╮"),
        paint("cyan", "│") + paint("white", " CHRISTMAS SNOW · ILLUSTRATED COMMAND GUIDE".ljust(width - 2)) + paint("cyan", "│"),
        paint("cyan", "╰" + "─" * (width - 2) + "╯"),
        "",
        paint("green", "PURPOSE"),
        "  Animate layered seasonal graphics through the Square 2x4 or PUA4 4x4 font.",
        "  Resize the terminal while it runs; the scene, flakes and snow bank adapt live.",
        "",
        paint("amber", "RECOMMENDED LAUNCH"),
        "  macOS  ./scripts/macos/run-demo.sh pua4 christmas-snow [options]",
        "  Linux ./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow [options]",
        "  Direct python3 demos/seasonal/christmas_snow.py --mode pua4 [options]",
        "",
        paint("pink", "LAUNCHER-ONLY WINDOW OPTIONS"),
        "  --terminal-columns N   initial window width in cursor cells",
        "  --terminal-rows N      initial window height in cursor cells",
        "  --font-size POINTS     font size for the isolated demo terminal",
        "  These select the initial window; unlike --columns/--rows they do not disable live resizing.",
        "",
        paint("pink", f"LIVE {mode.upper()} RENDER · EXACT PARTICLE COUNTS"),
    ]
    small = help_snow_preview(mode, 8).splitlines()
    large = help_snow_preview(mode, 24).splitlines()
    lines.append("  " + paint("amber", "8 FLAKES".center(30)) + "   " +
                 paint("amber", "24 FLAKES".center(30)))
    lines.append("  " + paint("dim", "┌" + "─" * 30 + "┐") + "   " +
                 paint("dim", "┌" + "─" * 30 + "┐"))
    for left, right in zip(small, large):
        lines.append("  " + paint("dim", "│") + left + paint("dim", "│") + "   " +
                     paint("dim", "│") + right + paint("dim", "│"))
    lines.append("  " + paint("dim", "└" + "─" * 30 + "┘") + "   " +
                 paint("dim", "└" + "─" * 30 + "┘"))
    lines.extend([
        "  The exact Flake objects cycle through tiny, small, medium and large geometry.",
        "  Each panel was produced by the same virtual-pixel → glyph encoder as the animation.",
        "",
        paint("pink", f"LIVE {mode.upper()} RENDER · CABIN DISTRIBUTION WITHOUT STRETCHING"),
    ])
    one_cabin = help_scene_preview(parser, mode, ("cabin",), (),
                                   cabin_count=1).splitlines()
    three_cabins = help_scene_preview(parser, mode, ("cabin",), (),
                                      cabin_count=3).splitlines()
    lines.append("  " + paint("amber", "1 CABIN".center(30)) + "   " +
                 paint("amber", "3 CABINS".center(30)))
    lines.append("  " + paint("dim", "┌" + "─" * 30 + "┐") + "   " +
                 paint("dim", "┌" + "─" * 30 + "┐"))
    for left, right in zip(one_cabin, three_cabins):
        lines.append("  " + paint("dim", "│") + left + paint("dim", "│") + "   " +
                     paint("dim", "│") + right + paint("dim", "│"))
    lines.append("  " + paint("dim", "└" + "─" * 30 + "┘") + "   " +
                 paint("dim", "└" + "─" * 30 + "┘"))
    lines.extend([
        "  Width changes distribution/count; cabin height controls a stable 1.72:1 body aspect.",
        "",
        paint("pink", f"LIVE {mode.upper()} RENDER · ONE TUMBLEWEED ROLLING THROUGH TIME"),
    ])
    tumble_frames = [
        help_scene_preview(parser, mode, (), ("tumbleweed",), elapsed,
                           columns=20, rows=5).splitlines()
        for elapsed in (0.0, 0.8, 1.6)
    ]
    lines.append("  " + "   ".join(
        paint("amber", label.center(20)) for label in ("0.0 SECONDS", "0.8 SECONDS", "1.6 SECONDS")))
    lines.append("  " + "   ".join(
        paint("dim", "┌" + "─" * 20 + "┐") for _ in tumble_frames))
    for frame_lines in zip(*tumble_frames):
        lines.append("  " + "   ".join(
            paint("dim", "│") + frame + paint("dim", "│") for frame in frame_lines))
    lines.append("  " + "   ".join(
        paint("dim", "└" + "─" * 20 + "┘") for _ in tumble_frames))
    lines.extend([
        "  Its branches rotate by distance; high snow blocks it and gains collapse pressure.",
        "",
        paint("green", "USE-CASE RECIPES"),
        paint("amber", "  Gentle snowfall") +
        "  --snow-rate 20 --flake-sizes tiny,small --fall-speed 10 --wind 0.2",
        paint("amber", "  Dense blizzard ") +
        "  --snow-rate 180 --max-flakes 900 --wind 8 --gust-strength 10 --fps 8",
        paint("amber", "  Christmas card ") +
        "  --scenery all --cabin-count 1 --lights 0.55 --palette christmas",
        paint("amber", "  Wide village   ") +
        "  --scenery all --cabin-count auto --max-cabins 4 --ambient all --fps 4",
        paint("amber", "  Cabin variety  ") +
        "  --cabin-count 3 --cabin-types cottage,lodge,a-frame --cabin-size-variation .35",
        paint("amber", "  Wildlife       ") +
        "  --rabbit-count 2 --rabbit-interval 18 --ambient tumbleweed",
        paint("amber", "  Sky parade     ") +
        "  --sky-events aeroplane,ufo,santa --flyby-interval 12 --flyby-speed 40",
        paint("amber", "  Santa arc      ") +
        "  --sky-events santa --santa-scale .5 --santa-arc-height .16 --santa-trail-seconds 2.8",
        paint("amber", "  Plough test    ") +
        "  --plough-interval 5 --plough-speed 60 --plough-clear-to .02",
        paint("amber", "  Font telemetry ") +
        "  --detailed-dashboard",
        paint("amber", "  Fast buildup   ") +
        "  --initial-snow 0.40 --accumulation-rate 5 --shed-threshold 0.50",
        paint("amber", "  Stable capture ") +
        "  --snapshot --columns 120 --rows 36 --seed 1225",
        paint("amber", "  Live tuning    ") +
        "  --listen    (then open christmas-snow-control in a second terminal)",
        "",
        paint("green", "EVERY PROGRAM OPTION"),
    ])

    for group in parser._action_groups:
        if not group._group_actions:
            continue
        lines.append("")
        lines.append(paint("cyan", "  " + group.title.upper()))
        for action in group._group_actions:
            usage = action_usage(action)
            description = action.help or ""
            if (action.default is not None and action.default is not False and
                    action.dest not in ("help", "accumulate")):
                default = action.default
                if isinstance(default, tuple):
                    default = ",".join(str(item) for item in default)
                description += f" [default: {default}]"
            wrapped = textwrap.wrap(description, width=max(30, width - 37)) or [""]
            lines.append("    " + paint("pink", usage.ljust(31)) + "  " + wrapped[0])
            lines.extend(" " * 37 + continuation for continuation in wrapped[1:])

    lines.extend([
        "",
        paint("green", "WHILE RUNNING"),
        "  Drag the window or use the terminal's font zoom controls to change the live grid.",
        "  With --detailed-dashboard, press Tab for FONT/SNOW/TREES/ANIMALS/FLIGHTS/PROCESS.",
        "  On FONT, SEEN SINCE START is the cumulative unique glyph-pattern requirement.",
        "  With --listen, the companion TUI applies validated revisions from a shared JSON file.",
        "  Press q, Esc, or Control-C to quit and restore the previous terminal screen.",
        "",
        paint("dim", "Detailed guide: demos/seasonal/README.md"),
    ])
    output = "\n".join(lines) + "\n"
    return output if colour else ANSI_ESCAPE.sub("", output)


def parse_args(argv=None):
    parser = build_parser()

    args = parser.parse_args(argv)
    if args.help:
        use_colour = "NO_COLOR" not in os.environ
        sys.stdout.write(pretty_help(parser, args.mode, use_colour))
        raise SystemExit(0)
    if len(args.flake_sizes) != len(args.size_weights):
        parser.error("--flake-sizes and --size-weights must contain the same number of values")
    positive = (("fps", args.fps), ("fall-speed", args.fall_speed),
                ("gust-period", args.gust_period), ("shed-rate", args.shed_rate),
                ("tower-collapse-rate", args.tower_collapse_rate),
                ("control-poll", args.control_poll),
                ("rabbit-interval", args.rabbit_interval),
                ("rabbit-speed", args.rabbit_speed),
                ("flyby-interval", args.flyby_interval),
                ("flyby-speed", args.flyby_speed),
                ("plough-interval", args.plough_interval),
                ("plough-speed", args.plough_speed))
    if any(value <= 0 for _, value in positive):
        parser.error("timing, polling, movement, shed and collapse rates must be positive")
    nonnegative = (
        args.duration, args.frames, args.preload_seconds, args.drift, args.wobble,
        args.gust_strength, args.accumulation, args.tree_density, args.tree_sway,
        args.lights, args.ambient_speed, args.max_cabins,
        args.tower_age, args.tower_age_jitter, args.rabbit_count,
        args.snow_repose_slope, args.snow_relaxation, args.object_snow_max,
        args.object_snow_hold, args.object_snow_hold_jitter,
        args.object_snow_adhesion,
        args.tumbleweed_climb, args.tumbleweed_collapse_pressure,
        args.santa_scale, args.santa_arc_height, args.santa_trail_seconds,
    )
    if any(value < 0 for value in nonnegative):
        parser.error("duration, frames, rates, drift, scenery density and lights cannot be negative")
    if args.snow_rate is not None and args.snow_rate < 0:
        parser.error("snow-rate cannot be negative")
    if args.max_flakes is not None and args.max_flakes < 0:
        parser.error("max-flakes cannot be negative")
    if args.leaf_count is not None and args.leaf_count < 0:
        parser.error("leaf-count cannot be negative")
    if args.tumbleweed_count is not None and args.tumbleweed_count < 0:
        parser.error("tumbleweed-count cannot be negative")
    if not 0 <= args.tumbleweed_climb <= 2:
        parser.error("tumbleweed-climb must be in [0, 2]")
    if args.max_trees < 0:
        parser.error("max-trees cannot be negative")
    if not 1 <= args.tree_branches <= 16:
        parser.error("tree-branches must be in [1, 16]")
    if not 1 <= args.tree_branch_levels <= 7:
        parser.error("tree-branch-levels must be in [1, 7]")
    if not 1 <= args.tree_branch_angle <= 75:
        parser.error("tree-branch-angle must be in [1, 75] degrees")
    if not 0.35 <= args.tree_length_ratio <= 0.90:
        parser.error("tree-length-ratio must be in [0.35, 0.90]")
    if not 0.5 <= args.tree_trunk_thickness <= 12:
        parser.error("tree-trunk-thickness must be in [0.5, 12]")
    if not 1.2 <= args.tree_thickness_exponent <= 4:
        parser.error("tree-thickness-exponent must be in [1.2, 4]")
    if not 0 <= args.tree_segment_budget <= 100000:
        parser.error("tree-segment-budget must be in [0, 100000]")
    if args.rabbit_count < 0:
        parser.error("rabbit-count cannot be negative")
    if args.cabin_scale <= 0:
        parser.error("cabin-scale must be positive")
    if not 0.2 <= args.santa_scale <= 2:
        parser.error("santa-scale must be in [0.2, 2]")
    if not 0 <= args.santa_arc_height <= 0.5:
        parser.error("santa-arc-height must be in [0, 0.5]")
    if not 0 <= args.cabin_size_variation <= 0.75:
        parser.error("cabin-size-variation must be in [0, 0.75]")
    if not 0 <= args.object_snow_capture <= 1:
        parser.error("object-snow-capture must be in [0, 1]")
    if not 0 <= args.speed_variation < 1:
        parser.error("speed-variation must be in [0, 1)")
    fractions = (args.initial_snow, args.bank_drift, args.shed_threshold,
                 args.shed_to, args.shed_width, args.tower_prominence,
                 args.tower_cascade_chance, args.tower_cascade_radius,
                 args.plough_clear_to)
    if any(not 0 <= value <= 1 for value in fractions):
        parser.error("snow-bank fractions must be in [0, 1]")
    if args.shed_to >= args.shed_threshold:
        parser.error("shed-to must be lower than shed-threshold")
    try:
        args.scenery_set = parse_scenery(args.scenery, args.cabin,
                                         args.reindeer, args.no_trees)
    except ValueError as error:
        parser.error(str(error))
    try:
        args.ambient_set = parse_ambient(args.ambient)
    except ValueError as error:
        parser.error(str(error))
    return args


def main(argv=None):
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        animate(parse_args(argv))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
