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

from christmas_snow_native import load_native_analyser

try:
    import resource
except ImportError:  # Windows does not provide the Unix resource module.
    resource = None


RESET = "\x1b[0m"

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
        (0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0),
        (0, -1), (0, 1), (0, -2), (0, 2),
    ),
    "large": (
        (0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0), (-3, 0), (3, 0),
        (0, -1), (0, 1), (0, -2), (0, 2), (0, -3), (0, 3),
        (-1, -2), (1, -2), (-1, 2), (1, 2),
        (-2, -1), (2, -1), (-2, 1), (2, 1),
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

DEFAULT_FLAKE_WEIGHTS = {
    "tiny": 55.0,
    "small": 28.0,
    "medium": 13.0,
    "large": 4.0,
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
    branch_thickness_ratio: float
    thickness_exponent: float
    conifer_colour_variation: float


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
    kind: str = "snow"
    layer: str = "foreground"
    bounces: int = 0


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
    depth: float = 1.0
    abduction_x: float = 0.0
    abduction_y: float = 0.0
    abduction_scale: float = 1.0
    abduction_origin_x: float = 0.0
    abduction_origin_y: float = 0.0


@dataclass
class Postman:
    x: float
    y: float
    direction: int
    state: str
    timer: float
    phase: float
    target_cabin: int = -1
    target_x: float = 0.0
    door_x: float = 0.0
    door_y: float = 0.0
    road_x: float = 0.0
    road_y: float = 0.0
    turn_progress: float = 0.0
    figure_height: float = 12.0
    road_figure_height: float = 12.0
    door_figure_height: float = 12.0
    handed_over: bool = False
    last_collapse_x: float = -1000000.0
    crate_id: int = -1
    route: tuple = ()
    route_index: int = 0
    route_progress: float = 0.0
    route_length: float = 1.0


@dataclass
class Parachutist:
    x: float
    y: float
    vx: float
    vy: float
    timer: float
    canopy_open: bool
    phase: float


@dataclass
class AircraftCrash:
    event_index: int
    aircraft_type: str
    direction: int
    x: float
    y: float
    start_y: float
    vx: float
    vy: float
    rotation: float
    angular_velocity: float
    scale: float
    target_scale: float
    target_y: float
    depth_mode: str
    age: float = 0.0


@dataclass
class CrashParticle:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    maximum_ttl: float
    kind: str


@dataclass
class GroundExplosion:
    x: float
    y: float
    kind: str
    duration: float
    scale: float
    seed: int
    foreground: bool = False
    age: float = 0.0


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
class PresentDrop:
    x: float
    y: float
    target_x: float
    target_y: float
    speed: float
    colour_index: int
    event_index: int


@dataclass
class SupplyCrate:
    crate_id: int
    x: float
    y: float
    state: str = "sealed"
    timer: float = 0.0


@dataclass
class CrateDebris:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    maximum_ttl: float


@dataclass
class DownwashParticle:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    maximum_ttl: float
    depth: float = 1.0


@dataclass
class SnowPlough:
    active: bool
    x: float
    direction: int
    timer: float
    y: float = 0.0
    path_y: float = 0.0


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
        return ("aeroplane", "helicopter", "airwolf", "kite", "ufo", "santa",
                "superman")
    return choice_list(value, ("aeroplane", "helicopter", "airwolf", "kite", "ufo",
                               "santa", "superman"),
                       "sky events")


def aeroplane_type_list(value):
    if value.strip().lower() in ("auto", "all"):
        return ("commuter", "airliner")
    return choice_list(value, ("commuter", "airliner"), "aeroplane types")


def ufo_type_list(value):
    if value.strip().lower() in ("auto", "all"):
        return ("saucer", "orb", "delta")
    return choice_list(value, ("saucer", "orb", "delta"),
                       "space-vehicle types")


def explosion_type_list(value):
    if value.strip().lower() in ("auto", "all"):
        return ("fiery", "nuclear")
    return choice_list(value, ("fiery", "nuclear"), "explosion types")


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
                  branch_thickness_ratio=0.42, conifer_colour_variation=28.0,
                  sway=0.0, segment_budget=None):
    height = max(8, int(height))
    profile_width = {"pine": 0.28, "fir": 0.34, "spruce": 0.22}[tree_type]
    half = max(3, int(height * profile_width))
    species_colours = {
        "pine": ((8, 52, 67), (8, 73, 75), (8, 99, 75),
                 (10, 127, 74), (12, 151, 72)),
        "fir": ((10, 49, 61), (9, 70, 67), (10, 95, 67),
                (12, 119, 65), (15, 143, 65)),
        "spruce": ((7, 56, 74), (7, 78, 83), (8, 101, 82),
                   (9, 123, 78), (11, 145, 73)),
    }
    base_colour = species_colours[tree_type][min(4, layer)]
    # Seeded per-tree tinting avoids a flat wall of identical green while
    # preserving repeatability and cached-raster reuse.
    tint = rng.uniform(-conifer_colour_variation, conifer_colour_variation)
    # Move green most strongly, red moderately and blue in the opposite
    # direction so variation remains visibly chromatic after 4x4 sampling.
    colour = (
        max(0, min(255, int(round(base_colour[0] + tint * 0.35)))),
        max(0, min(255, int(round(base_colour[1] + tint)))),
        max(0, min(255, int(round(base_colour[2] - tint * 0.42)))),
    )
    priority = 10 + layer * 4
    trunk_half = max(1, int(round(trunk_thickness * (0.45 + layer * 0.10))))
    # Only the naturally exposed foot is brown. The old full-height stationary
    # rectangle became visible behind a wind-bent narrow spruce crown.
    surface.rectangle(centre_x - trunk_half, base_y - height * 0.16,
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
    for tier_index, (start, tier_height, width_scale) in enumerate(tiers):
        shade = (-7, 3, -2, 6)[tier_index % 4]
        tier_colour = tuple(max(0, min(255, channel + shade))
                            for channel in colour)
        triangle(surface, centre_x, base_y - height + int(height * start),
                 half * width_scale, height * tier_height, tier_colour, priority,
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
                           max(1.0, trunk_thickness * branch_thickness_ratio),
                           colour, priority + 1)
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
                   trunk_thickness, branch_thickness_ratio,
                   thickness_exponent, sway=0.0,
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
            max(0.5, trunk_thickness * branch_thickness_ratio),
            thickness_exponent, branch, snow, priority + 1,
            segment_budget)


def draw_tree(surface, rng, centre_x, base_y, height, layer, lights,
              tree_type, args, sway=0.0, segment_budget=None):
    if tree_type in ("pine", "fir", "spruce"):
        draw_conifer(surface, rng, centre_x, base_y, height, layer, lights,
                     tree_type, args.tree_branches, args.tree_branch_angle,
                     args.tree_trunk_thickness, args.tree_branch_thickness_ratio,
                     args.conifer_colour_variation, sway, segment_budget)
    else:
        draw_broadleaf(
            surface, rng, centre_x, base_y, height, layer, tree_type,
            args.tree_branches, args.tree_branch_levels,
            args.tree_branch_angle, args.tree_length_ratio,
            args.tree_trunk_thickness, args.tree_branch_thickness_ratio,
            args.tree_thickness_exponent,
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
        tree_branch_thickness_ratio=settings.branch_thickness_ratio,
        tree_thickness_exponent=settings.thickness_exponent,
        conifer_colour_variation=settings.conifer_colour_variation,
    )
    draw_tree(surface, rng, centre, base, height, layer, lights, tree_type,
              tree_args, sway=0.0, segment_budget=[segment_allowance])
    return tuple(
        (index % width - centre, index // width - base,
         pixel[0], pixel[1])
        for index, pixel in enumerate(surface.pixels) if pixel is not None
    )


def draw_cached_tree(surface, centre, base, height, sway, pixels, force=False):
    """Apply cheap height-weighted sway while compositing cached geometry."""
    inverse_height = 1.0 / max(1.0, height)
    width = surface.width
    surface_height = surface.height
    surface_pixels = surface.pixels
    column_bits = surface._column_bits
    centre = int(centre)
    base = int(base)
    # Geometry contains many pixels at each y. Compute the height-weighted
    # displacement once per scanline rather than repeating min/max, multiply
    # and round for every painted pixel. At a 303-column viewport this removes
    # roughly one million Python operations from each scenery rebuild.
    offsets = {}
    for dy in range(-int(height) - 24, 9):
        crown_fraction = -dy * inverse_height
        if crown_fraction <= 0.0:
            offsets[dy] = 0
        elif crown_fraction >= 1.0:
            offsets[dy] = int(round(sway))
        else:
            offsets[dy] = int(round(
                sway * crown_fraction * crown_fraction))
    for dx, dy, colour, priority in pixels:
        offset = offsets.get(dy, 0)
        x = centre + dx + offset
        y = base + dy
        if not (0 <= x < width and 0 <= y < surface_height):
            continue
        index = y * width + x
        current = surface_pixels[index]
        if force or current is None or priority >= current[1]:
            surface_pixels[index] = (colour, priority)
            column_bits[x] |= 1 << y


def cabin_layout(args, width, height, snow_line):
    """Return perspective-scaled cabins, including deterministic distant homes."""
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
    distant_indices = {
        index for index in range(count)
        if random.Random(args.seed + 4817 + index * 193).random() <
        args.cabin_depth_share
    }
    if count >= 2 and args.cabin_depth_share > 0 and not distant_indices:
        distant_indices.add((args.seed + 1) % count)
    distant_indices = frozenset(distant_indices)
    for index in range(count):
        centre = margin + usable * (index + 0.5) / count
        variation_rng = random.Random(args.seed + 4109 + index * 97)
        variation = 1.0 + variation_rng.uniform(-args.cabin_size_variation,
                                                 args.cabin_size_variation)
        perspective = 1.0
        if index in distant_indices:
            perspective = args.cabin_depth_scale * variation_rng.uniform(0.90, 1.08)
            perspective = max(0.25, min(0.95, perspective))
        local_height = max(8, int(round(cabin_height * variation * perspective)))
        horizon_lift = int(round((1.0 - perspective) * height * 0.36))
        base = min(height - 1, snow_line - horizon_lift + max(2, local_height // 5))
        cabin_type = args.cabin_types[index % len(args.cabin_types)]
        placements.append((centre, base, local_height, index, cabin_type))
    return placements


def cabin_chimney_targets(args, width, height, snow_line):
    """Return chimney openings using the exact geometry used by draw_cabin."""
    targets = []
    for cabin_index, (centre, base, cabin_height, variant, cabin_type) in enumerate(
            cabin_layout(args, width, height, snow_line)):
        if cabin_type == "a-frame":
            continue
        aspect = {"cottage": 1.72, "lodge": 2.18}[cabin_type]
        cabin_width = max(16, int(round(cabin_height * aspect)))
        left = int(round(centre - cabin_width / 2))
        top = base - cabin_height
        chimney_width = max(2, cabin_width // 10)
        targets.append((cabin_index,
                        left + cabin_width * 0.72 + chimney_width * 0.5,
                        top - cabin_height * 0.54))
    return targets


def cabin_door_targets(args, width, height, snow_line):
    """Return cabin door centres and heights from the shared cabin layout."""
    targets = []
    for cabin_index, (centre, base, cabin_height, variant, cabin_type) in enumerate(
            cabin_layout(args, width, height, snow_line)):
        door_left, door_top, door_right, door_bottom = cabin_door_rect(
            centre, base, cabin_height, cabin_type)
        targets.append((cabin_index, (door_left + door_right) * 0.5,
                        door_bottom, door_bottom - door_top))
    return targets


def cabin_path_network(args, width, height, snow_line):
    """Shared dirt route with perspective-split diagonal, curved or curly spurs."""
    doors = cabin_door_targets(args, width, height, snow_line)
    road_y = min(height - 2, snow_line + max(1, int(height * 0.035)))
    spurs = []
    for cabin_index, door_x, door_y, _ in doors:
        side = -1.0 if door_x < width * 0.5 else 1.0
        if abs(door_x - width * 0.5) < 1.0:
            side = -1.0 if cabin_index % 2 == 0 else 1.0
        perspective = max(6.0, abs(road_y - door_y) * 0.42 + height * 0.035)
        junction_x = max(2.0, min(width - 3.0, door_x + side * perspective))
        requested = args.cabin_path_style
        style = (("diagonal", "curve", "curly")[cabin_index % 3]
                 if requested == "auto" else requested)
        samples = 2 if style == "diagonal" else 18
        points = []
        control_x = (junction_x + door_x) * 0.5 - side * perspective * 0.55
        control_y = road_y + (door_y - road_y) * 0.40
        for sample in range(samples):
            amount = sample / max(1, samples - 1)
            inverse = 1.0 - amount
            x = (inverse * inverse * junction_x +
                 2 * inverse * amount * control_x + amount * amount * door_x)
            y = (inverse * inverse * road_y +
                 2 * inverse * amount * control_y + amount * amount * door_y)
            if style == "curly":
                envelope = math.sin(math.pi * amount)
                x += (math.sin(amount * math.tau * 1.55 + cabin_index * 0.7) *
                      args.cabin_path_curl * perspective * 0.42 * envelope)
            points.append((x, y))
        spurs.append((cabin_index, tuple(points)))
    return road_y, tuple(spurs)


def helicopter_landing_x(args, width, height, snow_line, event_index=0):
    """Choose any repeatable viewport region rather than a centre-locked pad."""
    rng = random.Random(args.seed + 88301 + event_index * 211)
    return rng.uniform(width * 0.14, width * 0.86)


def safe_helicopter_landing_x(args, engine, event_index):
    """Keep a repeatable landing point clear of live people and rabbits.

    The target is chosen once at the beginning of an event. Downwash exclusion
    prevents a late actor crossing without ever moving the committed craft.
    """
    # Once an event has selected a pad it must never choose again. Previously
    # a rabbit or postman entering the exclusion test could replace this value
    # mid-flight; the craft visibly teleported to the opposite side before its
    # departure. The live exclusion zone now moves actors, not the aircraft.
    if event_index in engine.helicopter_landing_targets:
        return engine.helicopter_landing_targets[event_index]
    proposed = helicopter_landing_x(
        args, engine.width, engine.height,
        int(round(engine.scenery_ground_y)), event_index)
    blockers = [rabbit.x for rabbit in engine.rabbits
                if rabbit.state not in ("hidden", "abducting")]
    if engine.postman.state != "hidden":
        blockers.append(engine.postman.x)
    clearance = max(28.0, engine.width * 0.055)
    if not blockers or all(abs(proposed - x) >= clearance for x in blockers):
        chosen = proposed
    else:
        rng = random.Random(args.seed + 88711 + event_index * 223)
        candidates = [proposed]
        candidates.extend(rng.uniform(engine.width * 0.12, engine.width * 0.88)
                          for _ in range(18))
        chosen = max(
            candidates,
            key=lambda candidate: min(abs(candidate - x) for x in blockers),
        )
    chosen = max(engine.width * 0.10, min(engine.width * 0.90, chosen))
    engine.helicopter_landing_targets[event_index] = chosen
    if len(engine.helicopter_landing_targets) > 16:
        del engine.helicopter_landing_targets[
            min(engine.helicopter_landing_targets)]
    return chosen


def helicopter_landing_depth(engine, event_index):
    """Return one persistent perspective lane for a helicopter event."""
    if event_index not in engine.helicopter_landing_depths:
        rng = random.Random(engine.args.seed + 89101 + event_index * 227)
        # The range spans distant cabin paths through the foreground road.
        engine.helicopter_landing_depths[event_index] = rng.uniform(0.38, 0.98)
        if len(engine.helicopter_landing_depths) > 16:
            del engine.helicopter_landing_depths[
                min(engine.helicopter_landing_depths)]
    return engine.helicopter_landing_depths[event_index]


def cabin_door_rect(centre_x, base, cabin_height, cabin_type):
    """Return the exact door rectangle, kept inside every cabin silhouette."""
    aspect = {"cottage": 1.72, "lodge": 2.18, "a-frame": 1.48}[cabin_type]
    cabin_width = max(16, int(round(cabin_height * aspect)))
    left = int(round(centre_x - cabin_width / 2))
    door_width = max(3, cabin_width // 7)
    door_height = max(5, cabin_height // 2)
    if cabin_type == "a-frame":
        # The inset wall reaches 44% of the nominal width at the base. Keep
        # the complete door comfortably inside that triangular wall instead
        # of reusing the rectangular cabin's far-right placement.
        centre = centre_x + cabin_width * 0.19
        door_left = centre - door_width * 0.5
        door_right = centre + door_width * 0.5
    else:
        door_right = left + cabin_width - 3
        door_left = door_right - door_width
    return door_left, base - door_height, door_right, base


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
        apex = top - cabin_height * 0.46
        total_height = base - apex
        # A filled roof shell with an inset wall produces continuous eaves and
        # clean diagonals after 4x4 cell quantisation. The former one-pixel
        # outline broke into isolated edge fragments at small terminal sizes.
        triangle(surface, centre_x, apex, cabin_width * 0.56,
                 total_height, roof, 33)
        inset = max(2.0, cabin_height * 0.08)
        triangle(surface, centre_x, apex + inset, cabin_width * 0.44,
                 max(1.0, total_height - inset - 1), wall, 34)
        surface.line(left - 2, base - 1, left + cabin_width + 2, base - 1,
                     roof, 35)
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
    door_left, door_top, door_right, door_bottom = cabin_door_rect(
        centre_x, base, cabin_height, cabin_type)
    surface.rectangle(door_left, door_top, door_right, door_bottom,
                      (57, 34, 27), 34)
    surface.pixel(door_right - 2, (door_top + door_bottom) * 0.5,
                  (246, 191, 74), 37)
    if cabin_type == "lodge":
        second_left = left + cabin_width // 2
        surface.rectangle(second_left, wtop, second_left + wsize,
                          wtop + wsize, window, 35)
        surface.line(second_left + wsize // 2, wtop,
                     second_left + wsize // 2, wtop + wsize - 1,
                     (255, 236, 157), 36)


def reindeer_scale(width, height):
    return max(0.70, min(1.50, (width // 140) / 3.0,
                          (height // 48) / 3.0))


def reindeer_apparent_height(width, height):
    return 37.0 * reindeer_scale(width, height)


def draw_reindeer(surface, width, height, snow_line):
    # A readable left-facing seasonal reindeer: four depth-separated legs,
    # chest/neck/head anatomy, muzzle and eye, branching antlers, scarf, spots,
    # and small antler ornaments. It is deliberately original pixel geometry,
    # merely informed by the visual vocabulary of the supplied references.
    # Earlier versions reached scale 4 on large PUA canvases, occupying a
    # disproportionate third of the scene. Retain sub-pixel scaling here so
    # the same artwork is approximately one third of that linear footprint.
    scale = reindeer_scale(width, height)
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


def draw_horizon_structure(surface, args, snow_line):
    """Add lowEd sparse earth and miniature huts below an artificial horizon."""
    if args.horizon_structure == "none":
        return
    horizon = max(1, min(snow_line - 2,
                         int(round(surface.height * args.horizon_height))))
    rng = random.Random(args.seed + 77177)
    if args.horizon_structure in ("dirt", "both"):
        colours = ((52, 42, 34), (73, 52, 37), (91, 66, 43), (43, 47, 39))
        for y in range(horizon, snow_line):
            depth = (y - horizon) / max(1, snow_line - horizon)
            chance = args.horizon_dirt_density * (0.22 + depth * 0.78)
            stride = max(1, int(3 - depth * 2))
            for x in range((y + args.seed) % stride, surface.width, stride):
                if rng.random() < chance:
                    jitter = int(round(args.horizon_randomness * rng.uniform(-2, 2)))
                    surface.pixel(x + jitter, y, colours[rng.randrange(len(colours))], 7)
    if args.horizon_structure in ("huts", "both"):
        count = int(round(surface.width * args.horizon_hut_density / 18.0))
        for index in range(count):
            local = random.Random(args.seed + 78101 + index * 101)
            depth = local.uniform(0.08, 0.88)
            base = horizon + depth * max(2, snow_line - horizon - 2)
            scale = 0.20 + depth * 0.34
            width = max(3, int(surface.height * 0.10 * scale))
            height = max(3, int(width * local.uniform(0.72, 1.05)))
            x = local.uniform(2, surface.width - 3)
            x += local.uniform(-1, 1) * args.horizon_randomness * width
            wall = ((91, 61, 43), (106, 72, 47), (78, 61, 49))[index % 3]
            roof = ((75, 31, 43), (56, 45, 67), (72, 55, 45))[index % 3]
            surface.rectangle(x - width, base - height,
                              x + width, base, wall, 9)
            filled_polygon(surface, ((x - width * 1.2, base - height),
                                     (x, base - height * 1.65),
                                     (x + width * 1.2, base - height)), roof, 10)
            surface.pixel(x, base - height * 0.45, (244, 187, 72), 11)


def build_scenery(args, width, height, ground_y, elapsed=0.0):
    """Draw scenery against immutable terrain, never the accumulating bank."""
    surface = Surface(width, height)
    rng = random.Random(args.seed + 7331)
    snow_line = max(0, min(height - 1, int(round(ground_y))))
    draw_horizon_structure(surface, args, snow_line)
    plans = []
    tree_cache_context = None
    if ("trees" in args.scenery_set and args.tree_density > 0 and
            args.max_trees > 0):
        # Formula branches share a frame-wide budget. Filled conifer canopies
        # still render after it is exhausted, so extreme inputs degrade in
        # botanical detail rather than frame rate.
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
            args.tree_trunk_thickness, args.tree_branch_thickness_ratio,
            args.tree_thickness_exponent, args.conifer_colour_variation)
        per_tree_budget = (args.tree_segment_budget // len(plans)
                           if plans else 0)
        tree_cache_context = (settings, per_tree_budget)
        for tree_seed, centre, base, tree_height, layer, lights, tree_type, sway in plans:
            pixels = cached_tree_pixels(
                tree_seed, int(round(tree_height)), layer, lights, tree_type,
                settings, per_tree_budget)
            draw_cached_tree(surface, centre, base, tree_height, sway, pixels)
    if "cabin" in args.scenery_set:
        cabins = cabin_layout(args, width, height, snow_line)
        for centre, base, cabin_height, variant, cabin_type in cabins:
            draw_cabin(surface, centre, base, cabin_height, variant, cabin_type)
        # Re-composite only trees whose ground contact is visually nearer than
        # at least one cabin. This makes depth follow base position instead of
        # the old fixed "cabins always win" draw order.
        if tree_cache_context:
            settings, per_tree_budget = tree_cache_context
            for (tree_seed, centre, base, tree_height, layer, lights,
                 tree_type, sway) in plans:
                occludes_cabin = any(
                    base >= cabin_base and
                    abs(centre - cabin_centre) <
                    max(tree_height * 0.48, cabin_height * 1.15)
                    for cabin_centre, cabin_base, cabin_height, _, _ in cabins)
                if not occludes_cabin:
                    continue
                pixels = cached_tree_pixels(
                    tree_seed, int(round(tree_height)), layer, lights,
                    tree_type, settings, per_tree_budget)
                draw_cached_tree(surface, centre, base, tree_height, sway,
                                 pixels, force=True)
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
    normal_scale = rabbit_scene_scale(engine, rabbit)
    scale = (rabbit.abduction_scale if rabbit.state == "abducting"
             else normal_scale)
    direction = rabbit.direction
    hop = 0.0
    if rabbit.state in ("hopping", "startled"):
        amplitude = 5.0 if rabbit.state == "startled" else 3.2
        hop = abs(math.sin(rabbit.phase)) * amplitude * scale
    base = (rabbit.abduction_y if rabbit.state == "abducting"
            else rabbit_scene_ground_y(engine, rabbit) - hop)
    x = int(round(rabbit.abduction_x if rabbit.state == "abducting" else rabbit.x))
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


def rabbit_scene_scale(engine, rabbit):
    """Perspective scale retained for the rabbit's complete appearance."""
    viewport_scale = max(1.0, min(2.0, engine.height // 80))
    return viewport_scale * (0.42 + 0.58 * rabbit.depth)


def rabbit_scene_ground_y(engine, rabbit):
    """Project far rabbits toward the horizon while preserving terrain motion."""
    terrain = engine.surface_y(rabbit.x) - 1
    perspective_lift = (1.0 - rabbit.depth) * engine.height * 0.11
    projected = terrain - perspective_lift
    if rabbit.depth < 0.68 and "cabin" in engine.args.scenery_set:
        snow_line = max(0, min(
            engine.height - 1, int(round(engine.scenery_ground_y))))
        aspects = {"cottage": 1.72, "lodge": 2.18, "a-frame": 1.48}
        for centre, base, cabin_height, _, cabin_type in cabin_layout(
                engine.args, engine.width, engine.height, snow_line):
            cabin_width = max(16, int(round(
                cabin_height * aspects[cabin_type])))
            half_width = cabin_width * (0.54 if cabin_type == "a-frame" else 0.5)
            if centre - half_width <= rabbit.x <= centre + half_width:
                # Keep the complete far rabbit inside the cabin's vertical
                # occlusion footprint; feet must not leak below its base.
                projected = min(projected, base - 2)
    return projected


@functools.lru_cache(maxsize=192)
def cached_postman_pixels(figure_height, direction, gait_frame, pose, delivering):
    """Pre-rasterize gait and smooth side/back/front turning poses."""
    figure_height = max(9, int(round(figure_height)))
    scale = figure_height / 16.0
    width = max(18, int(round(figure_height * 1.4)))
    local_height = figure_height + 8
    centre = width // 2
    base = local_height - 2
    surface = Surface(width, local_height)
    phase = math.tau * (gait_frame % 8) / 8.0
    backness = max(0.0, min(1.0, pose / 4.0))
    frontness = max(0.0, min(1.0, -pose / 4.0))
    profile = 1.0 - backness - frontness
    bob = 0.0 if delivering else abs(math.sin(phase)) * 0.55 * scale
    hip_y = base - 6.0 * scale - bob
    shoulder_y = base - 11.0 * scale - bob
    skin = (224, 174, 126)
    uniform = tuple(int(side * profile + back * backness + front * frontness)
                    for side, back, front in zip(
                        (194, 42, 47), (119, 25, 35), (211, 49, 52)))
    uniform_light = tuple(
        int(side * profile + back * backness + front * frontness)
        for side, back, front in zip(
            (226, 59, 57), (157, 36, 43), (239, 74, 67)))
    trousers = (42, 55, 80)
    boot = (43, 34, 31)
    bag = (112, 67, 38)
    bag_light = (157, 98, 53)
    letter = (249, 243, 218)
    postal_gold = (255, 202, 61)

    # Opposed arm and leg phases follow the contact/passing relationship in
    # Muybridge's public-domain human locomotion sequence.
    for side, depth in ((-1, 87), (1, 91)):
        leg_phase = phase + (math.pi if side < 0 else 0.0)
        swing = (0.0 if delivering else
                 math.sin(leg_phase) * 2.7 * scale * (0.62 + profile * 0.38))
        hip_x = centre + side * (1.4 + backness * 0.35) * scale
        knee_x = hip_x + direction * swing * 0.55
        knee_y = hip_y + 3.0 * scale
        foot_x = hip_x + direction * swing
        foot_y = base - max(0.0, math.cos(leg_phase)) * 0.8 * scale
        thick_line(surface, hip_x, hip_y, knee_x, knee_y,
                   max(1.0, scale * 1.2), trousers, depth)
        thick_line(surface, knee_x, knee_y, foot_x, foot_y,
                   max(1.0, scale), trousers, depth)
        surface.line(foot_x - direction * scale, foot_y,
                     foot_x + direction * 1.7 * scale, foot_y, boot, depth + 1)

    torso_half = (2.8 + max(backness, frontness) * 0.55) * scale
    surface.rectangle(centre - torso_half, shoulder_y,
                      centre + torso_half, hip_y + scale,
                      uniform, 92)
    surface.rectangle(centre - 2.2 * scale, shoulder_y + scale,
                      centre + 2.2 * scale, hip_y,
                      uniform_light, 93)
    surface.line(centre - torso_half, hip_y - 0.4 * scale,
                 centre + torso_half, hip_y - 0.4 * scale,
                 trousers, 94)
    if frontness > 0.35:
        surface.line(centre, shoulder_y + scale, centre, hip_y - scale,
                     uniform, 94)
        surface.pixel(centre - scale, shoulder_y + 2 * scale,
                      postal_gold, 96)
        surface.pixel(centre, shoulder_y + 3 * scale,
                      postal_gold, 96)
    strap_start_x = centre - direction * 2.2 * scale * (profile + frontness * 0.4)
    strap_end_x = centre + direction * 2.2 * scale * (profile + frontness * 0.4)
    surface.line(strap_start_x, shoulder_y + scale,
                 strap_end_x, hip_y, bag, 94)
    bag_x = centre - direction * 3.2 * scale * (profile + frontness * 0.42)
    bag_half = (1.8 + 0.5 * backness) * scale
    surface.rectangle(bag_x - bag_half, hip_y - 2.4 * scale,
                      bag_x + bag_half, hip_y + 0.8 * scale, bag, 95)
    surface.line(bag_x - bag_half, hip_y - 1.5 * scale,
                 bag_x + bag_half, hip_y - 1.5 * scale, bag_light, 96)
    surface.pixel(bag_x, hip_y - 1.1 * scale, postal_gold, 97)

    for side, depth in ((-1, 90), (1, 95)):
        arm_phase = phase + (0.0 if side < 0 else math.pi)
        swing = (0.0 if delivering else
                 math.sin(arm_phase) * 2.5 * scale * (0.60 + profile * 0.40))
        shoulder_x = centre + side * (2.4 + backness * 0.35) * scale
        if delivering and side == direction:
            hand_x = centre + direction * 5.2 * scale
            hand_y = shoulder_y + 2.7 * scale
        else:
            hand_x = shoulder_x + direction * swing
            hand_y = shoulder_y + 4.2 * scale
        thick_line(surface, shoulder_x, shoulder_y + scale,
                   hand_x, hand_y, max(1.0, scale), uniform, depth)
        filled_ellipse(surface, hand_x, hand_y, max(0.7, scale),
                       max(0.7, scale), skin, depth + 1)
        if delivering and side == direction:
            letter_left, letter_right = sorted(
                (hand_x, hand_x + direction * 2.0 * scale))
            surface.rectangle(letter_left, hand_y - scale,
                              letter_right,
                              hand_y + scale, letter, 98)
            surface.line(letter_left, hand_y - scale,
                         letter_right, hand_y, (202, 62, 62), 99)

    head_y = shoulder_y - 2.3 * scale
    hair = (71, 47, 38)
    head_colour = tuple(int(front * (profile + frontness) + back * backness)
                        for front, back in zip(skin, hair))
    filled_ellipse(surface, centre, head_y, 2.1 * scale, 2.3 * scale,
                   head_colour, 96)
    surface.rectangle(centre - 2.7 * scale, head_y - 2.8 * scale,
                      centre + 2.5 * scale, head_y - 1.5 * scale,
                      uniform, 97)
    brim_left, brim_right = sorted((
        centre + direction * profile * 1.8 * scale,
        centre + direction * profile * 3.5 * scale))
    if profile > 0.2:
        surface.rectangle(brim_left, head_y - 2.0 * scale,
                          brim_right, head_y - 1.3 * scale, uniform, 98)
    if frontness > 0.45:
        surface.pixel(centre - scale, head_y - 0.4 * scale,
                      (32, 28, 27), 99)
        surface.pixel(centre + scale, head_y - 0.4 * scale,
                      (32, 28, 27), 99)
    elif pose < 3:
        surface.pixel(centre + direction * max(0.5, 1.4 * profile) * scale,
                      head_y - 0.5 * scale, (32, 28, 27), 99)
    return tuple(
        (index % width - centre, index // width - base, pixel)
        for index, pixel in enumerate(surface.pixels) if pixel is not None
    )


def draw_postman(surface, engine):
    postman = engine.postman
    if postman.state == "hidden":
        return
    gait_frame = int(postman.phase / math.tau * 8) % 8
    if postman.state == "turning_in":
        pose = int(round(postman.turn_progress * 4))
    elif postman.state in ("turning_from_house", "turning_out"):
        pose = int(round(postman.turn_progress * 4))
    elif postman.state in ("approaching", "posting", "waiting"):
        pose = 4
    elif postman.state == "returning":
        pose = -4
    else:
        pose = 0
    delivering = postman.state in ("posting", "opening_crate", "taking_mail")
    pixels = cached_postman_pixels(
        int(round(postman.figure_height)), postman.direction,
        gait_frame, pose, delivering)
    base = int(round(postman.y))
    centre = int(round(postman.x))
    for dx, dy, (colour, priority) in pixels:
        surface.pixel(centre + dx, base + dy, colour, priority)


def sky_event_margin(engine):
    """Off-screen runway wide enough for the richest flyby silhouette."""
    return max(104.0, engine.width * 0.08)


def compact_flyby_unit(engine, height_divisor):
    """One-third of the former scale, with a legibility floor for tiny grids."""
    former = max(1.0, min(3.0, engine.height // height_divisor))
    return max(0.65, former / 3.0)


def aeroplane_flyby_unit(engine):
    """Half the previous aeroplane scale so it reads as more distant."""
    return compact_flyby_unit(engine, 60) * 0.5


def santa_flyby_unit(engine, scale=None):
    former = max(1.0, min(2.0, engine.height // 60))
    # The very small floor intentionally permits a nearly point-like distant
    # formation while keeping the maximum a true configured linear scale.
    scale = engine.args.santa_scale_max if scale is None else scale
    return max(0.03, former * scale)


def ufo_target_x(engine, event_index, rng):
    """Freeze one rabbit-aligned destination for a complete UFO encounter."""
    if event_index not in engine.ufo_target_x_by_event:
        visible = [(index, rabbit.x) for index, rabbit in enumerate(engine.rabbits)
                   if rabbit.state != "hidden" and 4 <= rabbit.x < engine.width - 4]
        if visible:
            rabbit_index, target = min(
                visible, key=lambda item: abs(item[1] - engine.width * 0.5))
            engine.ufo_target_rabbit_by_event[event_index] = rabbit_index
        else:
            target = rng.uniform(engine.width * 0.24, engine.width * 0.76)
        engine.ufo_target_x_by_event[event_index] = target
        if len(engine.ufo_target_x_by_event) > 12:
            oldest = min(engine.ufo_target_x_by_event)
            del engine.ufo_target_x_by_event[oldest]
            engine.ufo_target_rabbit_by_event.pop(oldest, None)
    return engine.ufo_target_x_by_event[event_index]


def sky_event_speed(args, kind):
    return args.superman_speed if kind == "superman" else args.flyby_speed


def sky_event_quiet_time(args, kind):
    if kind == "superman":
        return 60.0 / max(0.01, args.superman_frequency)
    return args.flyby_interval


def sky_event_slot_duration(args, kind, travel_distance):
    """Reserve enough schedule time for every phase of one sky event."""
    travel = travel_distance / sky_event_speed(args, kind)
    quiet = sky_event_quiet_time(args, kind)
    if kind in ("helicopter", "airwolf"):
        hover = args.helicopter_hover_seconds
        descent = max(1.0, hover * 0.72)
        ascent = max(1.0, hover * 0.72)
        turn = max(0.8, hover * 0.85)
        return (travel * 0.68 + quiet + hover + descent +
                args.helicopter_wait_max + ascent + turn)
    if kind == "ufo" and args.ufo_abduction:
        return travel + quiet + args.ufo_hover_seconds
    return travel + quiet


def highest_cabin_silhouette_y(args, width, height, snow_line):
    """Topmost roof/chimney pixel used as a helicopter clearance plane."""
    tops = []
    for _, base, cabin_height, _, cabin_type in cabin_layout(
            args, width, height, snow_line):
        # A-frame apexes reach 1.46 cabin heights above the base. Rectangular
        # cabins have a chimney whose top reaches 1.54 heights above the base.
        silhouette_height = 1.46 if cabin_type == "a-frame" else 1.54
        tops.append(base - cabin_height * silhouette_height)
    return min(tops) if tops else None


def current_sky_event_state(args, engine, elapsed):
    """Return flyby geometry plus phase data used by interactive events."""
    if not args.sky_events:
        return None
    initial_quiet = sky_event_quiet_time(args, args.sky_events[0])
    shifted = elapsed - initial_quiet * 0.35
    if shifted < 0:
        return None
    margin = sky_event_margin(engine)
    travel_distance = engine.width + margin * 2
    durations = [sky_event_slot_duration(args, kind, travel_distance)
                 for kind in args.sky_events]
    rotation_duration = sum(durations)
    rotations = int(shifted / rotation_duration)
    local = shifted - rotations * rotation_duration
    event_offset = 0
    for event_offset, duration in enumerate(durations):
        if local < duration:
            break
        local -= duration
    event_index = rotations * len(args.sky_events) + event_offset
    rng = random.Random(args.seed + 51001 + event_index * 113)
    kind = args.sky_events[event_index % len(args.sky_events)]
    travel_time = travel_distance / sky_event_speed(args, kind)
    direction = -1 if rng.random() < 0.5 else 1
    phase = "flight"
    phase_progress = local / max(0.001, travel_time)
    ufo_encounter = kind == "ufo" and args.ufo_abduction
    scale = 1.0
    if ufo_encounter:
        approach = travel_time * 0.5
        hover = args.ufo_hover_seconds
        departure = travel_time * 0.5
        if local > approach + hover + departure:
            return None
        if local < approach:
            progress = 0.5 * local / max(0.001, approach)
            phase = "approach"
            phase_progress = progress * 2.0
        elif local < approach + hover:
            progress = 0.5
            phase = "abduction"
            phase_progress = (local - approach) / max(0.001, hover)
        else:
            progress = 0.5 + 0.5 * (local - approach - hover) / max(0.001, departure)
            phase = "departure"
            phase_progress = (progress - 0.5) * 2.0
    else:
        if local > travel_time and kind not in ("helicopter", "airwolf"):
            return None
        progress = min(1.0, local / max(0.001, travel_time))
    if ufo_encounter:
        target_x = ufo_target_x(engine, event_index, rng)
        distant_x = -margin if direction > 0 else engine.width + margin
        exit_x = engine.width + margin if direction > 0 else -margin
        if phase == "approach":
            ease = phase_progress * phase_progress * (3.0 - 2.0 * phase_progress)
            x = distant_x * (1.0 - ease) + target_x * ease
            scale = 0.06 + 0.94 * ease
        elif phase == "departure":
            ease = phase_progress * phase_progress * (3.0 - 2.0 * phase_progress)
            x = target_x * (1.0 - ease) + exit_x * ease
            scale = 1.0 - 0.94 * ease
        else:
            x = target_x
    else:
        x = -margin + progress * (engine.width + margin * 2)
        if direction < 0:
            x = engine.width - x
    if kind == "aeroplane":
        if (engine.args.aircraft_crash and
                event_index in engine.ejection_events):
            return
        unit = aeroplane_flyby_unit(engine)
        minimum_y, maximum_y = 19 * unit, engine.height - 18 * unit
    elif kind in ("helicopter", "airwolf"):
        unit = compact_flyby_unit(engine, 70) * 2.30
        minimum_y, maximum_y = 14 * unit, engine.height - 22 * unit
    elif kind == "kite":
        unit = compact_flyby_unit(engine, 72) * 0.72
        minimum_y, maximum_y = 10 * unit, engine.height - 24 * unit
    elif kind == "ufo":
        unit = compact_flyby_unit(engine, 65)
        minimum_y, maximum_y = 9 * unit, engine.height - 27 * unit
    elif kind == "superman":
        unit = compact_flyby_unit(engine, 78) * 0.66
        minimum_y, maximum_y = 12 * unit, engine.height - 20 * unit
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
    elif kind == "superman":
        y = rng.uniform(minimum_y, maximum_y)
        if args.superman_path == "curve":
            y += math.sin(progress * math.tau + event_index * 0.71) * engine.height * 0.10
        elif args.superman_path == "arc":
            y -= math.sin(math.pi * progress) * engine.height * 0.18
        y = max(minimum_y, min(maximum_y, y))
    elif kind in ("helicopter", "airwolf"):
        # A complete cinematic pass: point-like nose-on approach, hover,
        # descent, configurable ground wait, vertical roof-clearance lift,
        # thirteen-frame stationary turn and rear recession. The landing
        # location and perspective lane are stable for this event.
        wait_rng = random.Random(args.seed + 82001 + event_index * 179)
        wait_seconds = wait_rng.uniform(args.helicopter_wait_min,
                                        args.helicopter_wait_max)
        approach = travel_time * 0.34
        hover = args.helicopter_hover_seconds
        descent = max(1.0, hover * 0.72)
        ascent = max(1.0, hover * 0.72)
        turn = max(0.8, hover * 0.85)
        departure = travel_time * 0.34
        boundaries = (approach, approach + hover,
                      approach + hover + descent,
                      approach + hover + descent + wait_seconds,
                      approach + hover + descent + wait_seconds + ascent,
                      approach + hover + descent + wait_seconds + ascent + turn)
        landing_x = safe_helicopter_landing_x(args, engine, event_index)
        landing_depth = helicopter_landing_depth(engine, event_index)
        landing_scale = 0.42 + 0.58 * landing_depth
        distant_x = landing_x - direction * engine.width * 0.16
        horizon_y = max(engine.height * 0.42,
                        engine.scenery_ground_y - engine.height * 0.36)
        ground_contact_y = (horizon_y * (1.0 - landing_depth) +
                            engine.scenery_ground_y * landing_depth)
        ground_y = min(engine.height - 8 * unit * landing_scale,
                       ground_contact_y - 7 * unit * landing_scale)
        hover_y = max(minimum_y * landing_scale,
                      ground_y - engine.height * 0.20 * landing_scale)
        sky_y = max(minimum_y * 0.08, hover_y - engine.height * 0.13)
        snow_line = max(0, min(
            engine.height - 1, int(round(engine.scenery_ground_y))))
        cabin_roof_y = highest_cabin_silhouette_y(
            args, engine.width, engine.height, snow_line)
        if cabin_roof_y is None:
            clearance_y = hover_y
        else:
            # Gear/stores end about twelve model units below the craft centre.
            # Thirteen units plus raster rounding keeps the complete silhouette
            # above every roof before yaw begins.
            clearance_y = min(
                hover_y,
                cabin_roof_y - 13 * unit * landing_scale,
            )
            clearance_y = max(minimum_y * landing_scale, clearance_y)
        if local < boundaries[0]:
            phase = "heli_approach"
            phase_progress = local / max(0.001, approach)
            ease = phase_progress ** 2 * (3 - 2 * phase_progress)
            x = distant_x * (1 - ease) + landing_x * ease
            y = sky_y * (1 - ease) + hover_y * ease
            scale = 0.04 + (landing_scale - 0.04) * ease
            orientation = 0
        elif local < boundaries[1]:
            phase = "heli_hover"
            phase_progress = (local - boundaries[0]) / max(0.001, hover)
            x, y, scale, orientation = landing_x, hover_y, landing_scale, 0
        elif local < boundaries[2]:
            phase = "heli_descent"
            phase_progress = (local - boundaries[1]) / max(0.001, descent)
            ease = phase_progress ** 2 * (3 - 2 * phase_progress)
            x, y, scale = (landing_x, hover_y * (1 - ease) + ground_y * ease,
                           landing_scale)
            orientation = 0
        elif local < boundaries[3]:
            phase = "heli_landed"
            phase_progress = (local - boundaries[2]) / max(0.001, wait_seconds)
            x, y, scale, orientation = landing_x, ground_y, landing_scale, 0
        elif local < boundaries[4]:
            phase = "heli_takeoff"
            phase_progress = (local - boundaries[3]) / max(0.001, ascent)
            ease = phase_progress ** 2 * (3 - 2 * phase_progress)
            x, y, scale = (landing_x,
                           ground_y * (1 - ease) + clearance_y * ease,
                           landing_scale)
            orientation = 0
        elif local < boundaries[5]:
            phase = "heli_turn"
            phase_progress = (local - boundaries[4]) / max(0.001, turn)
            x, y, scale = landing_x, clearance_y, landing_scale
            orientation = min(12, int(round(phase_progress * 12.0)))
        else:
            depart_local = local - boundaries[5]
            if depart_local > departure:
                return None
            phase = "heli_departure"
            phase_progress = depart_local / max(0.001, departure)
            ease = phase_progress ** 2 * (3 - 2 * phase_progress)
            x = landing_x + direction * engine.width * 0.18 * ease
            # Recede toward a low horizon instead of climbing into the same
            # high lane used by ordinary flybys.
            departure_y = min(
                ground_y - 3 * unit * landing_scale,
                max(hover_y + engine.height * 0.06,
                    engine.height * 0.46))
            scale = landing_scale * (1.0 - 0.98 * ease)
            desired_y = clearance_y * (1 - ease) + departure_y * ease
            if cabin_roof_y is None:
                y = desired_y
            else:
                # Permit the receding craft to settle toward its low horizon,
                # but never let its lower silhouette cross a cabin roof while
                # it is still large enough to overlap one on screen.
                safe_y = cabin_roof_y - 13 * unit * scale
                y = min(desired_y, safe_y)
            orientation = 12
        progress = min(1.0, local / max(0.001, boundaries[5] + departure))
    else:
        y = rng.uniform(minimum_y, maximum_y)
        if kind == "kite":
            y += (math.sin(progress * math.tau * 3.7 + event_index) *
                  engine.height * 0.055)
            y += math.sin(progress * math.tau * 9.0) * engine.height * 0.018
            y = max(minimum_y, min(maximum_y, y))
    if kind == "santa":
        depth_curve = math.sin(math.pi * progress)
        depth_curve = depth_curve * depth_curve * (3.0 - 2.0 * depth_curve)
        scale = (args.santa_scale_min +
                 (args.santa_scale_max - args.santa_scale_min) * depth_curve)
    if ufo_encounter and phase in ("approach", "departure"):
        ease = phase_progress * phase_progress * (3.0 - 2.0 * phase_progress)
        if phase == "departure":
            ease = 1.0 - ease
        distant_y = max(minimum_y, engine.height * 0.055)
        target_y = y
        y = distant_y * (1.0 - ease) + target_y * ease
        y -= math.sin(math.pi * ease) * engine.height * 0.10
        y = max(minimum_y * max(0.2, scale), y)
    return {
        "kind": kind, "x": x, "y": y, "direction": direction,
        "event_index": event_index, "phase": phase,
        "phase_progress": max(0.0, min(1.0, phase_progress)),
        "scale": scale,
        "scene_depth": (landing_depth
                         if kind in ("helicopter", "airwolf") else None),
        "ground_contact_y": (ground_contact_y
                             if kind in ("helicopter", "airwolf") else None),
        "cabin_roof_y": (cabin_roof_y
                         if kind in ("helicopter", "airwolf") else None),
        "roof_clearance_y": (clearance_y
                             if kind in ("helicopter", "airwolf") else None),
        "orientation": orientation if kind in ("helicopter", "airwolf") else None,
        "aircraft_type": (
            args.aeroplane_types[event_index % len(args.aeroplane_types)]
            if kind == "aeroplane" else None),
        "vehicle_type": (args.ufo_types[event_index % len(args.ufo_types)]
                          if kind == "ufo" else None),
    }


def current_sky_event(args, engine, elapsed):
    """Compatibility tuple for callers that only need visible flyby geometry."""
    state = current_sky_event_state(args, engine, elapsed)
    if state is None:
        return None
    return (state["kind"], state["x"], state["y"],
            state["direction"], state["event_index"])


def draw_lightning(surface, engine):
    """Paint one deterministic branched bolt and a short-lived sky flash."""
    if (engine.args.weather == "none" or not engine.args.lightning or
            engine.lightning_remaining <= 0):
        return
    fraction = min(1.0, engine.lightning_remaining /
                   max(0.001, engine.args.lightning_flash))
    lift = 0.16 + fraction * 0.30
    for index, pixel in enumerate(surface.pixels):
        if pixel is None:
            continue
        colour, priority = pixel
        surface.pixels[index] = (
            tuple(min(255, int(channel + (255 - channel) * lift))
                  for channel in colour), priority)
    rng = random.Random(engine.lightning_seed)
    x = rng.uniform(engine.width * 0.16, engine.width * 0.84)
    y = -2.0
    points = [(x, y)]
    segment_height = max(3.0, engine.height * 0.055)
    target = engine.height * rng.uniform(0.45, 0.78)
    while y < target:
        x += rng.uniform(-segment_height * 0.48, segment_height * 0.48)
        y += segment_height * rng.uniform(0.72, 1.18)
        points.append((x, y))
    bolt_colour = tuple(int(205 + 50 * fraction) for _ in range(3))
    edge_colour = (36, 92, 255)
    glow_colour = (95, 205, 255)
    for left, right in zip(points, points[1:]):
        thick_line(surface, *left, *right, 4.0, edge_colour, 56)
        thick_line(surface, *left, *right, 2.3, glow_colour, 57)
        surface.line(*left, *right, bolt_colour, 58)
    candidates = list(range(1, max(2, len(points) - 2)))
    rng.shuffle(candidates)
    for point_index in candidates[:engine.args.lightning_branches]:
        start_x, start_y = points[point_index]
        direction = rng.choice((-1, 1))
        length = segment_height * rng.uniform(1.8, 4.2)
        end_x = start_x + direction * length
        end_y = start_y + length * rng.uniform(0.55, 0.95)
        mid_x = (start_x + end_x) * 0.5 + rng.uniform(-3, 3)
        mid_y = (start_y + end_y) * 0.5
        thick_line(surface, start_x, start_y, mid_x, mid_y,
                   2.7, edge_colour, 56)
        thick_line(surface, mid_x, mid_y, end_x, end_y,
                   2.7, edge_colour, 56)
        surface.line(start_x, start_y, mid_x, mid_y, glow_colour, 57)
        surface.line(mid_x, mid_y, end_x, end_y, bolt_colour, 58)


def draw_clouds(surface, engine, elapsed, near):
    """Draw deterministic depth lanes with scale and speed parallax."""
    args = engine.args
    if not args.clouds or args.cloud_count <= 0:
        return
    viewport = max(0.55, min(1.8, engine.height / 120.0))
    travel_margin = engine.width * 0.18 + 24
    track = engine.width + travel_margin * 2
    wind_direction = -1 if args.wind < 0 else 1
    for index in range(args.cloud_count):
        rng = random.Random(args.seed + 63011 + index * 149)
        depth = args.cloud_depths[index % len(args.cloud_depths)]
        if (depth >= 0.62) != near:
            continue
        scale = viewport * (0.34 + depth * 0.78) * rng.uniform(0.78, 1.18)
        parallax = 0.18 + depth * max(0.0, args.cloud_parallax)
        speed = args.cloud_speed * parallax
        start = rng.random() * track
        x = ((start + wind_direction * elapsed * speed + travel_margin) % track -
             travel_margin)
        y_band = engine.height * (0.08 + (1.0 - depth) * 0.26)
        y = y_band + rng.uniform(-engine.height * 0.045, engine.height * 0.045)
        colour = args.cloud_colours[index % len(args.cloud_colours)]
        shade = tuple(max(0, int(channel * 0.82)) for channel in colour)
        priority = 76 if near else 42
        filled_ellipse(surface, x, y, 15 * scale, 5.2 * scale,
                       shade, priority)
        filled_ellipse(surface, x - 8 * scale, y - 2 * scale,
                       8 * scale, 6 * scale, colour, priority + 1)
        filled_ellipse(surface, x + 2 * scale, y - 4 * scale,
                       10 * scale, 8 * scale, colour, priority + 1)
        filled_ellipse(surface, x + 11 * scale, y - scale,
                       7 * scale, 5 * scale, colour, priority + 1)


def draw_ufo_beam(surface, engine, elapsed, event):
    """Draw only the transporter so render_surface can assign its depth lane."""
    if (event is None or event["kind"] != "ufo" or
            not engine.ufo_beam_active or
            engine.abduction_event_index != event["event_index"]):
        return
    x, y = event["x"], event["y"]
    unit = compact_flyby_unit(engine, 65) * event.get("scale", 1.0)
    target_y = engine.ufo_beam_target_y
    top_y = y + 7 * unit
    beam_depth = max(2.0, target_y - top_y)
    beam_palette = ((44, 236, 255), (51, 121, 255),
                    (184, 75, 255), (255, 205, 54),
                    (224, 255, 249))
    segments = max(12, int(beam_depth / max(1.0, 2.8 * unit)))
    motion = int(elapsed * 14)
    style = engine.args.ufo_beam_style
    if style == "spiral":
        for ribbon in range(2):
            previous = None
            phase = elapsed * (5.2 + ribbon * 0.55) + ribbon * math.pi
            for segment in range(segments + 1):
                fraction = segment / segments
                ribbon_y = top_y + beam_depth * fraction
                span = (2.0 + 5.0 * fraction) * unit
                ribbon_x = x + math.sin(
                    phase + fraction * math.tau * 2.0) * span
                if previous is not None and (segment + motion + ribbon * 2) % 5 < 2:
                    surface.line(*previous, ribbon_x, ribbon_y,
                                 beam_palette[ribbon], 53)
                previous = (ribbon_x, ribbon_y)
    elif style == "lattice":
        spacing = max(5.0, 8.0 * unit)
        offset = (elapsed * 11.0) % spacing
        beam_y = top_y + offset
        while beam_y < target_y:
            fraction = (beam_y - top_y) / beam_depth
            span = (3.0 + 6.0 * fraction) * unit
            next_y = min(target_y, beam_y + spacing * 0.72)
            surface.line(x - span, beam_y, x + span, next_y,
                         beam_palette[int(beam_y) % len(beam_palette)], 53)
            surface.line(x + span, beam_y, x - span, next_y,
                         beam_palette[(int(beam_y) + 2) % len(beam_palette)], 53)
            beam_y += spacing
    elif style == "stargate":
        for shaft in (-1, 0, 1):
            shaft_x = x + shaft * 4.2 * unit
            phase = int(elapsed * 18 + shaft * 2)
            for segment in range(segments):
                if (segment + phase) % 6 < 2:
                    y0 = top_y + beam_depth * segment / segments
                    y1 = top_y + beam_depth * (segment + 1) / segments
                    surface.line(shaft_x, y0, shaft_x, y1,
                                 beam_palette[(segment + shaft) % 5], 54)
    ring_spacing = max(6.0, beam_depth / 4.0)
    scan_y = top_y + (elapsed * 14.0) % ring_spacing
    ring_index = 0
    while scan_y < target_y and style in ("spiral", "rings", "stargate"):
        fraction = (scan_y - top_y) / beam_depth
        span = (3.0 + 5.0 * fraction) * unit
        colour = beam_palette[(ring_index + int(elapsed * 5)) % len(beam_palette)]
        surface.line(x - span, scan_y, x + span, scan_y, colour, 55)
        scan_y += ring_spacing
        ring_index += 1
    spark_rng = random.Random(event["event_index"] * 1009 + int(elapsed * 12))
    for _ in range(4):
        fraction = spark_rng.random()
        spark_y = top_y + beam_depth * fraction
        span = (4.0 + 8.0 * fraction) * unit
        spark_x = x + spark_rng.uniform(-span, span)
        surface.pixel(spark_x, spark_y,
                      beam_palette[spark_rng.randrange(len(beam_palette))], 56)


def draw_ah64_helicopter(surface, engine, elapsed, event):
    """Render a yawed AH-64 or Airwolf-style craft from one production model.

    The longitudinal profile, tandem canopy, nacelles, stores, gear, sensors,
    tail and rotor are projected independently. This avoids morphing one oval
    into the old front-view egg/side-view sausage while keeping all thirteen
    turn frames geometrically continuous.
    """
    x, y = event["x"], event["y"]
    direction = event["direction"]
    unit = compact_flyby_unit(engine, 70) * 2.30 * event.get("scale", 1.0)
    orientation = max(0, min(12, int(event.get("orientation", 0))))
    airwolf = event.get("kind") == "airwolf"
    yaw = math.pi * orientation / 12.0
    sine, cosine = math.sin(yaw), math.cos(yaw)
    axial = abs(cosine)
    rear = cosine < 0

    if airwolf:
        outline = (7, 9, 11)
        shadow = (22, 25, 28)
        olive = (39, 42, 44)
        olive_mid = (63, 67, 69)
        olive_light = (155, 160, 161)
        panel = (16, 18, 20)
        glass = (38, 55, 62)
        glass_light = (157, 191, 198)
        metal = (116, 122, 124)
    else:
        outline = (17, 22, 18)
        shadow = (38, 48, 29)
        olive = (62, 76, 39)
        olive_mid = (82, 96, 48)
        olive_light = (116, 126, 66)
        panel = (48, 59, 37)
        glass = (27, 54, 61)
        glass_light = (88, 139, 143)
        metal = (113, 119, 105)

    def project(lateral, vertical, longitudinal):
        # A small elevation component makes the rotor a projected disc rather
        # than two lines occupying the same row.
        return (
            x + direction * (lateral * cosine + longitudinal * sine) * unit,
            y + (vertical + longitudinal * cosine * 0.045) * unit,
        )

    def profile_polygon(stations, colour, priority, inset=0.0):
        upper = []
        lower = []
        for longitudinal, top, bottom, half_width in stations:
            centre_x, centre_y = project(0, 0, longitudinal)
            visible_half = half_width * (0.18 + 0.82 * axial) * unit
            upper.append((centre_x - visible_half + inset,
                          centre_y + top * unit))
            lower.append((centre_x + visible_half - inset,
                          centre_y + bottom * unit))
        filled_polygon(surface, upper + list(reversed(lower)), colour, priority)

    # Tail and fin remain narrow in side view, instead of being inflated to
    # the same thickness as the crew/engine compartment.
    profile_polygon(((-43, -4, 2, 1.6), (-35, -4, 3, 2.1),
                     (-13, -6, 5, 4.5)), outline, 63)
    profile_polygon(((-42, -3, 1, 1.0), (-34, -3, 2, 1.3),
                     (-12, -5, 4, 3.4)), olive, 64)
    tail_x, tail_y = project(0, 0, -40)
    fin_side = max(0.18, abs(sine))
    filled_polygon(surface, (
        (tail_x - direction * 4 * unit * fin_side, tail_y),
        (tail_x - direction * 2 * unit * fin_side, tail_y - 14 * unit),
        (tail_x + direction * 4 * unit * fin_side, tail_y - 6 * unit),
        (tail_x + direction * 5 * unit * fin_side, tail_y + 2 * unit),
    ), outline, 65)
    filled_polygon(surface, (
        (tail_x - direction * 2.8 * unit * fin_side, tail_y - unit),
        (tail_x - direction * 1.4 * unit * fin_side, tail_y - 11 * unit),
        (tail_x + direction * 2.8 * unit * fin_side, tail_y - 5 * unit),
        (tail_x + direction * 3.4 * unit * fin_side, tail_y + unit),
    ), olive_mid, 66)

    # Angular armoured fuselage: narrow nose, stepped cockpit, broad engines,
    # then a compact aft taper. A dark outer pass keeps the silhouette crisp.
    body = (((-16, -5, 5, 4.2), (-5, -8, 7, 7.4),
             (7, -9, 7, 7.1), (17, -6, 5, 4.7),
             (28, -1, 3, 1.5)) if airwolf else
            ((-14, -7, 6, 5.0), (-5, -10, 8, 8.5),
             (6, -10, 8, 8.0), (14, -7, 6, 5.0),
             (23, -2, 4, 2.0)))
    profile_polygon(body, outline, 65)
    body_inner = tuple((z, top + 0.9, bottom - 0.7,
                        max(0.8, width - 1.0))
                       for z, top, bottom, width in body)
    profile_polygon(body_inner, olive, 66)

    # Tandem gunner/pilot canopy: the rear cockpit is taller and visibly
    # stepped above the forward cockpit in oblique and side projections.
    canopy = (((1, -8.1, -3.4, 5.4), (8, -12.0, -3.5, 5.1),
               (16, -9.0, -2.9, 3.8), (23, -2.7, -1.0, 1.4))
              if airwolf else
              ((2, -10.1, -4.0, 5.5), (8, -13.2, -4.1, 5.0),
               (14, -9.4, -3.3, 4.1), (20, -3.0, -1.2, 1.7)))
    profile_polygon(canopy, outline, 67)
    canopy_inner = tuple((z, top + 1.0, bottom - 0.8,
                          max(0.7, width - 1.2))
                         for z, top, bottom, width in canopy)
    profile_polygon(canopy_inner, glass, 68)
    rear_screen = project(0, -8.1, 7.8)
    front_screen = project(0, -5.8, 14.2)
    surface.line(rear_screen[0] - 4 * axial * unit, rear_screen[1],
                 rear_screen[0] + 4 * axial * unit, rear_screen[1],
                 glass_light, 69)
    surface.line(front_screen[0], front_screen[1] - 3 * unit,
                 front_screen[0], front_screen[1] + 2 * unit,
                 glass_light, 69)
    if abs(sine) > 0.28:
        for longitudinal in (8.2, 14.0):
            surface.line(*project(0, -11.0, longitudinal),
                         *project(0, -3.5, longitudinal), outline, 70)
        for longitudinal in (9.7, 15.7):
            crew_x, crew_y = project(0, -5.4, longitudinal)
            surface.pixel(crew_x, crew_y, (202, 174, 96), 70)

    # Axial views otherwise collapse most longitudinal detail into the same
    # PUA4 cells. Reassert the paired canopy panes, frames and engine mouths
    # after projection so the nose-on AH-64 and Airwolf faces remain readable.
    if abs(sine) < 0.24 and not rear:
        pane_offset = 3.3 * unit
        pane_width = 3.0 * unit
        pane_top, pane_bottom = y - 11.0 * unit, y - 4.0 * unit
        for side in (-1, 1):
            pane_x = x + side * pane_offset
            filled_polygon(surface, (
                (pane_x - pane_width, pane_bottom),
                (pane_x - pane_width * 0.72, pane_top),
                (pane_x + pane_width * 0.72, pane_top),
                (pane_x + pane_width, pane_bottom),
            ), outline, 70)
            filled_polygon(surface, (
                (pane_x - pane_width * 0.66, pane_bottom - unit),
                (pane_x - pane_width * 0.45, pane_top + unit),
                (pane_x + pane_width * 0.45, pane_top + unit),
                (pane_x + pane_width * 0.66, pane_bottom - unit),
            ), glass_light if airwolf else glass, 71)
            surface.line(pane_x - pane_width * 0.30, pane_top + 1.3 * unit,
                         pane_x + pane_width * 0.25, pane_bottom - 1.3 * unit,
                         glass_light, 72)
        surface.line(x, pane_top - unit, x, pane_bottom + unit, outline, 72)

    # Twin engine nacelles remain visually separate from the central fuselage.
    for lateral in (-9.5, 9.5):
        engine_x, engine_y = project(lateral, -5.5, -2)
        if abs(sine) < 0.35:
            nacelle_width = (3.6 + 2.7 * axial) * unit
            filled_ellipse(surface, engine_x, engine_y,
                           nacelle_width, 4.4 * unit, outline, 68)
            filled_ellipse(surface, engine_x, engine_y,
                           max(unit, nacelle_width - unit), 3.2 * unit,
                           shadow if rear else olive_mid, 69)
        else:
            housing = (
                project(lateral, -9.1, -7),
                project(lateral, -9.1, 4),
                project(lateral, -2.2, 5.5),
                project(lateral, -1.5, -6),
            )
            filled_polygon(surface, housing, outline, 68)
            inner = (
                project(lateral, -8.0, -6),
                project(lateral, -8.0, 3),
                project(lateral, -3.0, 4.2),
                project(lateral, -2.6, -5),
            )
            filled_polygon(surface, inner,
                           shadow if rear else olive_mid, 69)
        intake_x, intake_y = project(lateral, -5.6, 2.1)
        filled_ellipse(surface, intake_x, intake_y,
                       max(unit, 2.5 * axial * unit), 2.2 * unit,
                       shadow, 70)

    if abs(sine) < 0.24 and not rear:
        for side in (-1, 1):
            intake_x = x + side * 9.5 * unit
            filled_ellipse(surface, intake_x, y - 4.8 * unit,
                           3.0 * unit, 3.7 * unit, outline, 72)
            filled_ellipse(surface, intake_x, y - 4.8 * unit,
                           1.8 * unit, 2.5 * unit, panel, 73)
        filled_ellipse(surface, x, y + 0.8 * unit,
                       2.8 * unit, 2.2 * unit, outline, 73)
        surface.pixel(x - unit, y + 0.5 * unit, glass_light, 74)
        surface.pixel(x + unit, y + 0.5 * unit, glass_light, 74)

    # Stub wings, four pylons, rocket pods and Hellfire-like rails.
    wing_left = project(-21, 1.5, -1)
    wing_right = project(21, 1.5, -1)
    thick_line(surface, *wing_left, *wing_right,
               max(1.4, 2.8 * unit), outline, 68)
    surface.line(*project(-20, 0.7, -1), *project(20, 0.7, -1),
                 olive_light, 69)
    if airwolf and abs(sine) > 0.18:
        # The supplied Airwolf reference is defined by a near-black body and
        # one continuous red lower accent from tail boom to pointed nose.
        surface.line(*project(0, 2.3, -39), *project(0, 2.8, 25),
                     (210, 34, 39), 72)
        surface.line(*project(0, 1.2, -36), *project(0, 1.7, 21),
                     (238, 82, 72), 73)
    for lateral in (-20, -14, 14, 20):
        pylon_top = project(lateral, 2.0, -1)
        pylon_bottom = project(lateral, 6.4, -1)
        thick_line(surface, *pylon_top, *pylon_bottom,
                   max(1.0, 1.2 * unit), outline, 69)
        store_x, store_y = pylon_bottom
        if abs(lateral) > 17:
            filled_ellipse(surface, store_x, store_y,
                           3.0 * unit, 2.3 * unit, outline, 70)
            filled_ellipse(surface, store_x, store_y,
                           2.1 * unit, 1.5 * unit, panel, 71)
            for port in (-1, 0, 1):
                surface.pixel(store_x + port * unit, store_y,
                              metal, 72)
        else:
            surface.line(store_x - 2.4 * unit, store_y,
                         store_x + 2.4 * unit, store_y,
                         olive_light, 71)
            surface.line(store_x - 2.0 * unit, store_y + unit,
                         store_x + 2.0 * unit, store_y + unit,
                         outline, 71)

    # Nose sensor, chin turret and articulated 30 mm chain gun.
    sensor_x, sensor_y = project(0, 1.3, 23)
    filled_ellipse(surface, sensor_x, sensor_y,
                   (2.4 + axial * 1.3) * unit, 2.8 * unit, outline, 70)
    filled_ellipse(surface, sensor_x, sensor_y,
                   (1.4 + axial) * unit, 1.8 * unit, shadow, 71)
    gun_x, gun_y = project(0, 5.2, 16)
    filled_ellipse(surface, gun_x, gun_y, 2.2 * unit, 2.0 * unit,
                   outline, 71)
    gun_tip = project(0, 8.8, 20)
    thick_line(surface, gun_x, gun_y, *gun_tip,
               max(1.0, 1.1 * unit), metal, 72)

    # Three-point landing gear is visibly independent from the fuselage.
    for lateral, longitudinal in ((-7, -5), (7, -5), (0, 14)):
        gear_top = project(lateral, 5.0, longitudinal)
        gear_bottom = project(lateral, 11.2, longitudinal)
        surface.line(*gear_top, *gear_bottom, outline, 70)
        wheel_x, wheel_y = gear_bottom
        filled_ellipse(surface, wheel_x, wheel_y,
                       1.6 * unit, 1.2 * unit, outline, 71)

    # Panel breaks and a tail-rotor disc add readable mechanical detail in the
    # oblique/side views without turning the axial silhouette back into a blob.
    if abs(sine) > 0.24:
        surface.line(*project(0, -2, -10), *project(0, 3, 11), panel, 70)
        surface.line(*project(0, 2, -32), *project(0, 2, -17), olive_light, 68)
        tail_radius = (1.2 + 5.5 * abs(sine)) * unit
        rotor_phase = elapsed * 19.0
        for blade in range(4):
            angle = rotor_phase + blade * math.pi / 2
            surface.line(tail_x, tail_y - 4 * unit,
                         tail_x + math.cos(angle) * tail_radius,
                         tail_y - 4 * unit + math.sin(angle) * tail_radius,
                         outline, 72)
        filled_ellipse(surface, tail_x, tail_y - 4 * unit,
                       1.2 * unit, 1.2 * unit, metal, 73)

    # Mast, Longbow radar and four tapered rotor blades. Each blade is a filled
    # projected quadrilateral, so rotation reads as a disc instead of an X.
    mast_bottom = project(0, -10, -1)
    mast_top = project(0, -17, -1)
    thick_line(surface, *mast_bottom, *mast_top,
               max(1.0, 1.8 * unit), metal, 72)
    rotor_phase = elapsed * 12.0 + 0.55
    hub_x, hub_y = mast_top
    for blade in range(4):
        angle = rotor_phase + blade * math.pi / 2
        root = 3.0
        span = 38.0
        root_lateral = math.cos(angle) * root
        root_longitudinal = -1 + math.sin(angle) * root
        tip_lateral = math.cos(angle) * span
        tip_longitudinal = -1 + math.sin(angle) * span
        root_point = (
            x + direction * (root_lateral * cosine +
                             root_longitudinal * sine) * unit,
            y + (-17 + root_longitudinal * cosine * 0.20) * unit,
        )
        tip_point = (
            x + direction * (tip_lateral * cosine +
                             tip_longitudinal * sine) * unit,
            y + (-17 + tip_longitudinal * cosine * 0.20) * unit,
        )
        vx, vy = tip_point[0] - root_point[0], tip_point[1] - root_point[1]
        length = max(0.001, math.hypot(vx, vy))
        nx, ny = -vy / length, vx / length
        root_half, tip_half = 1.30 * unit, 0.42 * unit
        filled_polygon(surface, (
            (root_point[0] + nx * root_half, root_point[1] + ny * root_half),
            (tip_point[0] + nx * tip_half, tip_point[1] + ny * tip_half),
            (tip_point[0] - nx * tip_half, tip_point[1] - ny * tip_half),
            (root_point[0] - nx * root_half, root_point[1] - ny * root_half),
        ), shadow if airwolf else olive_mid, 73)
        surface.line(*root_point,
                     root_point[0] + vx * 0.62,
                     root_point[1] + vy * 0.62, olive_light, 74)
    filled_ellipse(surface, hub_x, hub_y, 2.4 * unit, 1.8 * unit,
                   metal, 75)
    radar_x, radar_y = project(0, -21, -1)
    if airwolf:
        filled_ellipse(surface, radar_x, radar_y,
                       2.5 * unit, 1.4 * unit, outline, 74)
        filled_ellipse(surface, radar_x, radar_y,
                       1.5 * unit, 0.8 * unit, metal, 75)
    else:
        filled_ellipse(surface, radar_x, radar_y,
                       5.0 * unit, 2.2 * unit, outline, 74)
        filled_ellipse(surface, radar_x, radar_y,
                       4.0 * unit, 1.4 * unit, olive_mid, 75)

    warning = ((255, 45, 30) if int(elapsed * 5) % 2 else (60, 255, 132))
    for lateral in (-21, 21):
        light_x, light_y = project(lateral, 0.2, -1)
        filled_ellipse(surface, light_x, light_y,
                       max(0.8, unit), max(0.8, unit), warning, 76)


def draw_sky_event(surface, engine, elapsed, include_beam=True):
    plasma_colours = ((39, 244, 255), (80, 114, 255), (202, 66, 255),
                      (255, 77, 193), (181, 255, 247))
    for particle in engine.ufo_trail:
        fraction = max(0.0, min(1.0, particle.ttl / particle.maximum_ttl))
        base = plasma_colours[particle.colour_index % len(plasma_colours)]
        colour = tuple(int(channel * (0.20 + fraction * 0.80)) for channel in base)
        filled_ellipse(surface, particle.x, particle.y,
                       max(0.5, fraction * 1.3), max(0.5, fraction),
                       colour, 54)
    trail_colours = ((255, 48, 72), (54, 145, 255), (255, 231, 64),
                     (255, 132, 38), (55, 222, 105))
    for particle in engine.santa_trail:
        fraction = max(0.0, min(1.0, particle.ttl / particle.maximum_ttl))
        base = trail_colours[particle.colour_index % len(trail_colours)]
        colour = tuple(int(channel * (0.28 + fraction * 0.72)) for channel in base)
        filled_ellipse(surface, particle.x, particle.y,
                       max(1.0, fraction * 1.8), max(1.0, fraction * 1.2),
                       colour, 55)
    event = current_sky_event_state(engine.args, engine, elapsed)
    if event is None:
        return
    kind = event["kind"]
    x, y = event["x"], event["y"]
    direction, event_index = event["direction"], event["event_index"]
    if kind == "aeroplane" and event_index in engine.ejection_events:
        return

    def point(dx, dy):
        return x + direction * dx, y + dy

    if kind == "aeroplane":
        unit = aeroplane_flyby_unit(engine)
        body = (239, 248, 250)
        shade = (151, 187, 204)
        accent = (245, 111, 70)
        deep_accent = (197, 49, 60)
        window = (40, 94, 177)
        if event.get("aircraft_type") == "airliner":
            # Long red-and-cream scheduled airliner: narrow fuselage, repeated
            # windows, swept wing, underslung engine and tall branded tail.
            filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
                (-48, -4), (30, -4), (43, -1), (48, 1), (42, 4),
                (-43, 5), (-50, 2),
            )], body, 65)
            filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
                (-45, 2), (42, 2), (42, 5), (-45, 5),
            )], deep_accent, 67)
            filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
                (-37, -4), (-45, -19), (-35, -19), (-22, -4),
            )], deep_accent, 68)
            filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
                (-2, 3), (-24, 16), (-9, 17), (19, 3),
            )], shade, 64)
            filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
                (2, -3), (-16, -14), (-5, -14), (21, -3),
            )], body, 64)
            engine_x, engine_y = point(-5 * unit, 10 * unit)
            filled_ellipse(surface, engine_x, engine_y, 5 * unit, 3 * unit,
                           deep_accent, 69)
            for dx in range(-28, 31, 5):
                wx, wy = point(dx * unit, -1.5 * unit)
                surface.rectangle(wx - unit, wy - unit,
                                  wx + unit, wy + unit, window, 70)
            cockpit_x, cockpit_y = point(38 * unit, -unit)
            surface.rectangle(cockpit_x - unit, cockpit_y - unit,
                              cockpit_x + 2 * unit, cockpit_y + unit,
                              window, 70)
            return
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
    elif kind in ("helicopter", "airwolf"):
        draw_ah64_helicopter(surface, engine, elapsed, event)
    elif kind == "kite":
        unit = compact_flyby_unit(engine, 72) * 0.72
        red, gold, blue, dark = ((235, 52, 68), (255, 198, 55),
                                 (63, 150, 232), (57, 43, 64))
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (0, -10), (-8, 0), (0, 12), (8, 0),
        )], red, 66)
        filled_polygon(surface, [point(dx * unit, dy * unit) for dx, dy in (
            (0, -10), (0, 12), (8, 0),
        )], gold, 67)
        surface.line(*point(0, -10 * unit), *point(0, 12 * unit), dark, 69)
        surface.line(*point(-8 * unit, 0), *point(8 * unit, 0), dark, 69)
        previous = point(0, 12 * unit)
        effective_wind = max(-40.0, min(
            40.0, engine.args.wind + gust_at(engine.args, elapsed)))
        wind_energy = min(1.0, abs(effective_wind) / 18.0)
        for tail_index in range(1, 8):
            fraction = tail_index / 7.0
            flutter = math.sin(
                elapsed * (5.0 + wind_energy * 6.0) + tail_index * 1.18)
            local_x = flutter * (2.0 + wind_energy * 2.5) * unit
            tail_x, tail_y = point(local_x, (12 + tail_index * 5) * unit)
            # The tail is flexible: cumulative wind and the live sinusoidal
            # gust bend its lower sections downwind much more than its root.
            tail_x += effective_wind * unit * 0.13 * tail_index * fraction
            tail_y += math.cos(elapsed * 4.2 + tail_index) * wind_energy * unit
            surface.line(*previous, tail_x, tail_y, dark, 65)
            bow_colour = blue if tail_index % 2 else gold
            surface.line(tail_x - 2 * unit, tail_y - unit,
                         tail_x + 2 * unit, tail_y + unit, bow_colour, 67)
            surface.line(tail_x - 2 * unit, tail_y + unit,
                         tail_x + 2 * unit, tail_y - unit, bow_colour, 67)
            previous = (tail_x, tail_y)
    elif kind == "superman":
        unit = compact_flyby_unit(engine, 78) * 0.66
        blue, blue_shade = (34, 92, 205), (24, 55, 143)
        red, gold = (218, 38, 52), (255, 202, 49)
        skin, hair = (234, 174, 132), (28, 24, 29)
        flap = math.sin(elapsed * 8.0 + event_index) * 3.0 * unit
        def spoint(dx, dy):
            # Deliberately stretch the recognisable horizontal pose without
            # doubling height: it survives small fonts as a flying person.
            return point(dx * unit * 1.85, dy * unit)

        filled_polygon(surface, [spoint(dx, dy) for dx, dy in (
            (-4, -4), (-20, -9 + flap / unit), (-18, 4 + flap / unit * 0.28),
            (-3, 4), (5, 2), (5, -3),
        )], red, 65)
        thick_line(surface, *spoint(-7, 0), *spoint(12, 0),
                   6 * unit, blue, 67)
        filled_ellipse(surface, *spoint(12, -3),
                       4 * unit, 4 * unit, skin, 69)
        filled_polygon(surface, [spoint(dx, dy) for dx, dy in (
            (9, -7), (15, -7), (17, -4), (10, -4),
        )], hair, 70)
        surface.pixel(*spoint(15, -3), (25, 24, 28), 72)
        thick_line(surface, *spoint(11, -1), *spoint(27, -3),
                   3 * unit, blue, 68)
        filled_ellipse(surface, *spoint(29, -3),
                       2.5 * unit, 2 * unit, skin, 70)
        thick_line(surface, *spoint(2, 1), *spoint(-11, 6),
                   3 * unit, blue_shade, 66)
        thick_line(surface, *spoint(-4, 2), *spoint(-21, 4),
                   3 * unit, blue, 67)
        filled_polygon(surface, [spoint(dx, dy) for dx, dy in (
            (1, -4), (6, 0), (1, 4), (-4, 0),
        )], red, 69)
        surface.line(*spoint(-2, 0), *spoint(4, 0), gold, 70)
        surface.line(*spoint(0, -2), *spoint(3, 1), gold, 71)
        surface.line(*spoint(3, 1), *spoint(5, -2), gold, 71)
        filled_polygon(surface, [spoint(dx, dy) for dx, dy in (
            (-18, 1), (-29, 2), (-29, 6), (-16, 5),
        )], red, 69)
        filled_polygon(surface, [spoint(dx, dy) for dx, dy in (
            (-9, 2), (-23, 7), (-28, 7), (-20, 3),
        )], red, 68)
    elif kind == "ufo":
        unit = compact_flyby_unit(engine, 65) * event.get("scale", 1.0)
        metal = (132, 194, 216)
        dark = (26, 48, 62)
        glass = (122, 222, 245)
        alien = (22, 164, 70)
        glow = (83, 255, 211)
        vehicle_type = event.get("vehicle_type", "saucer")
        if vehicle_type == "orb":
            filled_ellipse(surface, x, y - 2 * unit, 13 * unit, 13 * unit,
                           dark, 64)
            filled_ellipse(surface, x, y - 3 * unit, 10 * unit, 10 * unit,
                           glass, 67)
            filled_ellipse(surface, x, y - 4 * unit, 5 * unit, 6 * unit,
                           alien, 69)
            surface.line(x - 17 * unit, y + 4 * unit,
                         x + 17 * unit, y + 4 * unit, metal, 68)
        elif vehicle_type == "delta":
            filled_polygon(surface, (
                (x, y - 14 * unit), (x - 24 * unit, y + 7 * unit),
                (x - 5 * unit, y + 3 * unit), (x, y + 8 * unit),
                (x + 5 * unit, y + 3 * unit), (x + 24 * unit, y + 7 * unit),
            ), dark, 64)
            filled_polygon(surface, (
                (x, y - 10 * unit), (x - 15 * unit, y + 4 * unit),
                (x, y), (x + 15 * unit, y + 4 * unit),
            ), metal, 67)
            filled_ellipse(surface, x, y - 3 * unit, 5 * unit, 4 * unit,
                           glass, 69)
        else:
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
        # The beam is separable because its depth belongs to the target rabbit,
        # while the craft itself always remains in the distant flight layer.
        if include_beam:
            draw_ufo_beam(surface, engine, elapsed, event)
    else:  # Santa's sleigh and reindeer team.
        unit = santa_flyby_unit(engine, event.get("scale"))
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


def draw_present_drops(surface, engine):
    """Paint Santa's tumbling parcels while scenery remains able to occlude them."""
    colours = ((239, 54, 67), (48, 132, 226), (49, 173, 92),
               (255, 151, 38), (145, 77, 190))
    for index, present in enumerate(engine.present_drops):
        size = max(1.0, santa_flyby_unit(engine) * 2.2)
        colour = colours[present.colour_index % len(colours)]
        phase = int(engine.elapsed * 9 + index) % 2
        if phase:
            surface.rectangle(present.x - size, present.y - size * 0.7,
                              present.x + size, present.y + size * 0.7,
                              colour, 60)
        else:
            surface.rectangle(present.x - size * 0.7, present.y - size,
                              present.x + size * 0.7, present.y + size,
                              colour, 60)
        surface.line(present.x, present.y - size,
                     present.x, present.y + size, (255, 225, 82), 61)
        surface.line(present.x - size, present.y,
                     present.x + size, present.y, (255, 225, 82), 61)


def draw_parachutists(surface, engine):
    """Draw pilots entirely within the far-distance flight layer."""
    scale = max(0.68, min(1.25, engine.height / 185.0))
    for pilot in engine.parachutists:
        pendulum = (math.sin(pilot.phase) * 2.4 * scale
                    if pilot.canopy_open else 0.0)
        x, y = pilot.x + pendulum, pilot.y
        if pilot.canopy_open:
            canopy = (231, 72, 66)
            canopy_light = (247, 222, 174)
            billow = 1.0 + 0.10 * math.sin(pilot.phase * 1.7)
            canopy_x = pilot.x - pendulum * 0.20
            canopy_y = y - 10 * scale
            filled_ellipse(surface, canopy_x, canopy_y,
                           8.5 * scale * billow, 3.8 * scale, canopy, 58)
            surface.line(canopy_x - 7.5 * scale, canopy_y,
                         x - scale, y - 2 * scale, canopy_light, 57)
            surface.line(canopy_x + 7.5 * scale, canopy_y,
                         x + scale, y - 2 * scale, canopy_light, 57)
            surface.line(canopy_x, canopy_y - 2.5 * scale,
                         canopy_x, canopy_y + 2.5 * scale,
                         canopy_light, 59)
        body = (56, 67, 83)
        helmet = (239, 181, 83)
        filled_ellipse(surface, x, y - scale, 1.1 * scale,
                       1.1 * scale, helmet, 60)
        thick_line(surface, x, y, x, y + 3.5 * scale,
                   max(1.0, scale), body, 59)
        swing = math.sin(pilot.phase) * 1.5 * scale
        surface.line(x, y + 2.5 * scale,
                     x - 2 * scale + swing, y + 5 * scale, body, 59)
        surface.line(x, y + 2.5 * scale,
                     x + 2 * scale + swing, y + 5 * scale, body, 59)


def draw_aircraft_crashes(surface, engine):
    """Draw spinning disabled aircraft, layered fire/smoke and impacts."""
    for particle in engine.crash_particles:
        fraction = max(0.0, particle.ttl / particle.maximum_ttl)
        if particle.kind == "fire":
            colour = (255, int(70 + 150 * fraction), 18)
            radius = 0.8 + 2.2 * fraction
        else:
            shade = int(42 + 92 * fraction)
            colour = (shade, shade, min(150, shade + 13))
            radius = 1.2 + 4.0 * (1.0 - fraction)
        filled_ellipse(surface, particle.x, particle.y, radius, radius * 0.72,
                       colour, 58 if particle.kind == "smoke" else 60)

    for crash in engine.aircraft_crashes:
        unit = aeroplane_flyby_unit(engine) * max(0.12, crash.scale)
        cosine, sine = math.cos(crash.rotation), math.sin(crash.rotation)

        def point(dx, dy):
            dx *= crash.direction
            return (crash.x + (dx * cosine - dy * sine) * unit,
                    crash.y + (dx * sine + dy * cosine) * unit)

        body = (220, 226, 218)
        shade = (110, 128, 137)
        accent = (215, 55, 42)
        filled_polygon(surface, [point(dx, dy) for dx, dy in (
            (-30, -3), (20, -4), (31, 0), (20, 4), (-30, 3),
        )], body, 62)
        filled_polygon(surface, [point(dx, dy) for dx, dy in (
            (-5, -2), (-20, -16), (-8, -17), (11, -2),
        )], accent, 63)
        filled_polygon(surface, [point(dx, dy) for dx, dy in (
            (-3, 2), (-18, 15), (-5, 16), (13, 2),
        )], shade, 61)
        filled_polygon(surface, [point(dx, dy) for dx, dy in (
            (-25, -2), (-30, -14), (-22, -14), (-13, -2),
        )], accent, 64)
        flame_base = point(-31, 0)
        flame_tip = point(-43 - 5 * math.sin(engine.elapsed * 17), 0)
        thick_line(surface, *flame_base, *flame_tip,
                   max(1.0, 4 * unit), (255, 67, 18), 63)
        surface.line(*point(-31, 0), *point(-40, 0), (255, 231, 74), 64)

    for explosion in engine.ground_explosions:
        fraction = min(1.0, explosion.age / max(0.001, explosion.duration))
        scale = max(0.2, explosion.scale)
        rng = random.Random(explosion.seed + int(explosion.age * 12))
        fade_progress = max(0.0, min(1.0, (fraction - 0.62) / 0.38))
        fade = 1.0 - fade_progress * fade_progress * (3.0 - 2.0 * fade_progress)

        def faded(colour, floor=0.04):
            strength = floor + (1.0 - floor) * fade
            return tuple(int(channel * strength) for channel in colour)

        if explosion.kind == "nuclear":
            flash = max(0.0, 1.0 - fraction * 8.0)
            if flash > 0:
                filled_ellipse(surface, explosion.x, explosion.y,
                               (8 + 36 * (1 - flash)) * scale,
                               (5 + 21 * (1 - flash)) * scale,
                               (255, 248, 206), 66)
            rise = min(1.0, fraction * 2.9)
            pulse = 1.0 + 0.07 * math.sin(explosion.age * 7.0)
            stem_height = (12 + 58 * rise) * scale
            stem_width = (3 + 8 * rise) * scale
            # Ground fireball and lateral shock front establish the huge hot
            # base before the stem/cap rise above it.
            ground_radius = (12 + 48 * rise) * scale
            for lobe in range(18):
                angle = math.tau * lobe / 18
                distance = ground_radius * rng.uniform(0.20, 0.92)
                palette = ((255, 30, 8), (255, 79, 8), (255, 151, 17),
                           (255, 225, 63))
                filled_ellipse(
                    surface,
                    explosion.x + math.cos(angle) * distance,
                    explosion.y - abs(math.sin(angle)) * distance * 0.25,
                    ground_radius * rng.uniform(0.09, 0.21),
                    ground_radius * rng.uniform(0.05, 0.13),
                    faded(palette[lobe % len(palette)]), 63)
            ring_radius = ground_radius * (0.65 + 0.55 * fraction)
            surface.line(explosion.x - ring_radius, explosion.y + scale,
                         explosion.x + ring_radius, explosion.y + scale,
                         faded((255, 190, 44)), 64)
            surface.rectangle(explosion.x - stem_width,
                              explosion.y - stem_height,
                              explosion.x + stem_width, explosion.y,
                              faded((218, 44, 12)), 63)
            surface.rectangle(explosion.x - stem_width * 0.52,
                              explosion.y - stem_height,
                              explosion.x + stem_width * 0.52, explosion.y,
                              faded((255, 151, 19)), 64)
            surface.rectangle(explosion.x - stem_width * 0.20,
                              explosion.y - stem_height,
                              explosion.x + stem_width * 0.20, explosion.y,
                              faded((255, 240, 128)), 65)
            cap_y = explosion.y - stem_height
            cap_width = (14 + 54 * rise) * scale * pulse
            hot_palette = ((198, 20, 9), (255, 48, 8), (255, 103, 10),
                           (255, 174, 28), (255, 229, 85))
            for lobe in range(23):
                angle = math.tau * lobe / 23
                lx = explosion.x + math.cos(angle) * cap_width * 0.62
                ly = cap_y + math.sin(angle) * cap_width * 0.25
                filled_ellipse(surface, lx, ly,
                               cap_width * rng.uniform(0.18, 0.32),
                               cap_width * rng.uniform(0.12, 0.24),
                               faded(hot_palette[lobe % len(hot_palette)]), 64)
            filled_ellipse(surface, explosion.x, cap_y,
                           cap_width * 0.72, cap_width * 0.29,
                           faded((255, 65, 8)), 65)
            filled_ellipse(surface, explosion.x, cap_y - cap_width * 0.06,
                           cap_width * 0.50, cap_width * 0.19,
                           faded((255, 166, 23)), 66)
            filled_ellipse(surface, explosion.x, cap_y - cap_width * 0.10,
                           cap_width * 0.25, cap_width * 0.10,
                           faded((255, 247, 168)), 67)
            for ember in range(16):
                ex = explosion.x + rng.uniform(-cap_width, cap_width)
                ey = cap_y + rng.uniform(-cap_width * 0.38, stem_height * 0.72)
                surface.pixel(ex, ey,
                              faded(hot_palette[(ember + 2) % len(hot_palette)]),
                              68)
        else:
            expansion = min(1.0, fraction * 4.0)
            radius = (7 + 38 * expansion) * scale
            for lobe in range(24):
                angle = math.tau * lobe / 24 + fraction * 2.0
                distance = radius * rng.uniform(0.15, 0.78)
                colour = ((255, 242, 126), (255, 201, 42), (255, 111, 13),
                          (238, 42, 12), (128, 22, 18))[lobe % 5]
                filled_ellipse(
                    surface,
                    explosion.x + math.cos(angle) * distance,
                    explosion.y - abs(math.sin(angle)) * distance * 0.72,
                    radius * rng.uniform(0.12, 0.27),
                    radius * rng.uniform(0.09, 0.20), faded(colour), 64)
            filled_ellipse(surface, explosion.x,
                           explosion.y - radius * 0.30,
                           radius * 0.34, radius * 0.28,
                           faded((255, 235, 112)), 66)


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
        self.native_analyser = load_native_analyser(
            required=args.native_encoder == "on") if args.native_encoder != "off" else None
        if args.size_weights is None:
            args.size_weights = tuple(DEFAULT_FLAKE_WEIGHTS[name]
                                      for name in args.flake_sizes)
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
        preload = (0 if args.weather == "none" else
                   min(self.max_flakes, int(self.snow_rate * args.preload_seconds)))
        self.flakes = [self.new_flake(initial=True) for _ in range(preload)]
        self.flake_distribution = (tuple(args.flake_sizes),
                                   tuple(args.size_weights))
        self.weather_distribution = (
            args.weather, args.rain_share, args.hail_share, args.rain_speed,
            args.weather_foreground_share)
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
        self.ufo_trail = []
        self.ufo_trail_credit = 0.0
        self.ufo_target_x_by_event = {}
        self.ufo_target_rabbit_by_event = {}
        self.parachutists = []
        self.ejection_events = set()
        self.pilot_ejection_count = 0
        self.aircraft_crashes = []
        self.crash_particles = []
        self.crash_particle_credit = 0.0
        self.ground_explosions = []
        self.aircraft_impact_count = 0
        self.present_drops = []
        self.present_drop_keys = set()
        self.present_delivery_count = 0
        self.last_santa_event_index = -1
        self.last_santa_sleigh_x = None
        self.supply_crates = []
        self.crate_debris = []
        self.helicopter_crate_events = set()
        self.helicopter_landing_targets = {}
        self.helicopter_landing_depths = {}
        self.helicopter_exclusion_active = False
        self.helicopter_exclusion_x = 0.0
        self.helicopter_exclusion_radius = 0.0
        self.downwash_particles = []
        self.downwash_credit = 0.0
        self.downwash_snow_events = 0
        self.lightning_timer = args.lightning_interval * self.rng.uniform(0.25, 0.85)
        self.lightning_remaining = 0.0
        self.lightning_seed = self.rng.randrange(0, 2 ** 31)
        self.lightning_count = 0
        self.lightning_interval_setting = args.lightning_interval
        self.abducted_rabbit_index = None
        self.abduction_event_index = -1
        self.ufo_target_rabbit_index = None
        self.ufo_target_event_index = -1
        self.ufo_beam_active = False
        self.ufo_beam_target_y = 0.0
        self.ufo_abduction_count = 0
        self.spawn_credit = 0.0
        self.shedding = None
        self.shed_count = 0
        self.shed_cooldown = 0.0
        self.tower_ages = [0.0] * width
        self.mass_fallaway_ages = [0.0] * width
        self.tower_collapses = []
        self.tower_collapse_count = 0
        self.rabbits = []
        self.rabbit_reactions = 0
        self.postman = Postman(
            x=-20.0, y=height - 1, direction=1, state="hidden",
            timer=(args.postman_interval / max(0.01, args.postman_delivery_frequency) *
                   self.rng.uniform(0.25, 0.65)),
            phase=0.0,
        )
        self.postman_delivery_count = 0
        self.postman_snow_collapses = 0
        self.postman_next_cabin = 0
        self.sync_rabbits(initial=True)
        self.sync_tumbleweeds(initial=True)
        self.plough = SnowPlough(
            active=False, x=-20.0, direction=1,
            timer=args.plough_interval * self.rng.uniform(0.35, 0.75),
            path_y=height * (1.0 - args.plough_clear_to) - 1,
        )
        self.plough_count = 0
        self.telemetry_wall = time.monotonic()
        self.telemetry_cpu = time.process_time()
        self.cpu_percent = 0.0
        self.render_ms = 0.0
        self.pipeline_ms = 0.0
        self.present_ms = 0.0
        self.frame_output_bytes = 0
        self.frame_overruns = 0
        self.maximum_frame_lag_ms = 0.0
        self.dashboard_tab = 0
        self.glyphs_seen = set()

    def resize(self, width, height):
        """Rescale live particles and bank depth into a changed terminal grid."""
        if width == self.width and height == self.height:
            return
        old_width, old_height = self.width, self.height
        old_depths = self.depths
        old_tower_ages = self.tower_ages
        old_mass_ages = self.mass_fallaway_ages
        scale_x = width / old_width
        scale_y = height / old_height
        depths = []
        tower_ages = []
        mass_ages = []
        for x in range(width):
            source = (x + 0.5) * old_width / width - 0.5
            left = max(0, min(old_width - 1, int(math.floor(source))))
            right = max(0, min(old_width - 1, left + 1))
            fraction = max(0.0, min(1.0, source - left))
            value = old_depths[left] * (1.0 - fraction) + old_depths[right] * fraction
            depths.append(min(height * 0.86, value * scale_y))
            tower_ages.append(old_tower_ages[left] * (1.0 - fraction) +
                              old_tower_ages[right] * fraction)
            mass_ages.append(old_mass_ages[left] * (1.0 - fraction) +
                             old_mass_ages[right] * fraction)
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
        for particle in self.ufo_trail:
            particle.x *= scale_x
            particle.y *= scale_y
        for pilot in self.parachutists:
            pilot.x *= scale_x
            pilot.y *= scale_y
            pilot.vx *= scale_x
            pilot.vy *= scale_y
        for crash in self.aircraft_crashes:
            crash.x *= scale_x
            crash.y *= scale_y
            crash.vx *= scale_x
            crash.vy *= scale_y
            crash.target_y *= scale_y
        for particle in self.crash_particles:
            particle.x *= scale_x
            particle.y *= scale_y
            particle.vx *= scale_x
            particle.vy *= scale_y
        for explosion in self.ground_explosions:
            explosion.x *= scale_x
            explosion.y *= scale_y
        for present in self.present_drops:
            present.x *= scale_x
            present.y *= scale_y
            present.target_x *= scale_x
            present.target_y *= scale_y
        for crate in self.supply_crates:
            crate.x *= scale_x
            crate.y *= scale_y
        for piece in self.crate_debris:
            piece.x *= scale_x
            piece.y *= scale_y
            piece.vx *= scale_x
            piece.vy *= scale_y
        for particle in self.downwash_particles:
            particle.x *= scale_x
            particle.y *= scale_y
            particle.vx *= scale_x
            particle.vy *= scale_y
        for crate in self.supply_crates:
            crate.x *= scale_x
            crate.y *= scale_y
        for debris in self.crate_debris:
            debris.x *= scale_x
            debris.y *= scale_y
            debris.vx *= scale_x
            debris.vy *= scale_y
        for particle in self.downwash_particles:
            particle.x *= scale_x
            particle.y *= scale_y
            particle.vx *= scale_x
            particle.vy *= scale_y
        self.plough.x *= scale_x
        self.plough.y *= scale_y
        self.postman.x *= scale_x
        self.postman.y *= scale_y
        self.postman.target_x *= scale_x
        self.postman.door_x *= scale_x
        self.postman.door_y *= scale_y
        self.postman.road_x *= scale_x
        self.postman.road_y *= scale_y
        self.postman.route = tuple((x * scale_x, y * scale_y)
                                   for x, y in self.postman.route)
        self.postman.route_length *= math.hypot(scale_x, scale_y) / math.sqrt(2.0)
        if self.postman.last_collapse_x > -100000:
            self.postman.last_collapse_x *= scale_x
        self.postman.figure_height *= scale_y
        self.postman.road_figure_height *= scale_y
        self.postman.door_figure_height *= scale_y
        self.ufo_target_x_by_event = {
            key: value * scale_x for key, value in self.ufo_target_x_by_event.items()
        }
        self.helicopter_landing_targets = {
            key: value * scale_x
            for key, value in self.helicopter_landing_targets.items()
        }
        self.helicopter_exclusion_x *= scale_x
        self.helicopter_exclusion_radius *= scale_x
        self.width = width
        self.height = height
        self.plough.path_y = self.height * (1.0 - self.args.plough_clear_to) - 1
        if self.plough.active:
            self.plough.y = self.plough.path_y
        self.depths = depths
        self.tower_ages = tower_ages
        self.mass_fallaway_ages = mass_ages
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
        if self.args.weather == "rain":
            kind = "rain"
        elif self.args.weather == "hail":
            kind = "hail"
        elif self.args.weather == "storm":
            kind = "hail" if self.rng.random() < self.args.hail_share else "rain"
        elif self.args.weather == "mixed":
            choice = self.rng.random()
            if choice < self.args.hail_share:
                kind = "hail"
            elif choice < self.args.hail_share + self.args.rain_share:
                kind = "rain"
            else:
                kind = "snow"
        else:
            kind = "snow"
        if kind == "rain":
            speed *= self.args.rain_speed
            colour = self.args.rain_colour
        elif kind == "hail":
            speed *= 1.35
            colour = self.args.hail_colour
        else:
            colour = self.rng.choice(self.palette["snow"])
        return Flake(
            x=self.rng.uniform(0, max(0, self.width - 1)),
            y=self.rng.uniform(-self.height * 0.95, -1) if initial else self.rng.uniform(-10, -1),
            speed=speed,
            drift=self.rng.uniform(-self.args.drift, self.args.drift),
            phase=self.rng.uniform(0, math.tau),
            wobble=self.rng.uniform(0.55, 2.1),
            shape=shape,
            colour=colour,
            kind=kind,
            layer=("foreground" if self.rng.random() <
                   self.args.weather_foreground_share else "background"),
        )

    def step_lightning(self, dt):
        self.lightning_remaining = max(0.0, self.lightning_remaining - dt)
        if not self.args.lightning or self.args.weather == "none":
            self.lightning_remaining = 0.0
            return
        self.lightning_timer -= dt
        if self.lightning_timer <= 0:
            self.lightning_remaining = self.args.lightning_flash
            self.lightning_seed = self.rng.randrange(0, 2 ** 31)
            self.lightning_timer = self.args.lightning_interval * self.rng.uniform(0.65, 1.35)
            self.lightning_count += 1

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

    def mass_fallaway_deadline(self, x):
        mixed = (self.args.seed * 2246822519 + x * 3266489917) & 0xFFFFFFFF
        fraction = mixed / 0xFFFFFFFF
        return (self.args.snow_fallaway_min_seconds +
                (self.args.snow_fallaway_max_seconds -
                 self.args.snow_fallaway_min_seconds) * fraction)

    def detect_mass_fallaways(self, dt):
        """Count down sustained local mass, then release that complete area."""
        threshold = self.args.snow_fallaway_threshold
        if not self.args.accumulate or threshold <= 0:
            self.mass_fallaway_ages = [0.0] * self.width
            return
        candidates = []
        sample_step = max(1, int(self.width * 0.008))
        for x in range(0, self.width, sample_step):
            if self.depths[x] / self.height >= threshold:
                self.mass_fallaway_ages[x] += dt
                if self.mass_fallaway_ages[x] >= self.mass_fallaway_deadline(x):
                    candidates.append((self.mass_fallaway_ages[x], x))
            else:
                self.mass_fallaway_ages[x] = 0.0
        span = max(3, int(self.width * self.args.snow_fallaway_width))
        for _, centre in sorted(candidates, reverse=True):
            if len(self.tower_collapses) >= 8 or self.collapse_near(centre, span):
                continue
            shoulder = max(span, int(self.width * 0.035))
            target = min(
                self.depths[centre],
                (self.depths[(centre - shoulder) % self.width] +
                 self.depths[(centre + shoulder) % self.width]) * 0.25,
                self.height * threshold * 0.58)
            self.tower_collapses.append(
                BankCollapse(centre, span, max(0.0, target), generation=3))
            self.tower_collapse_count += 1
            for offset in range(-span * 2, span * 2 + 1):
                self.mass_fallaway_ages[(centre + offset) % self.width] = 0.0

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
        distribution = (tuple(self.args.flake_sizes),
                        tuple(self.args.size_weights))
        if distribution != self.flake_distribution:
            # A saturated storm may otherwise spawn no replacement flakes for
            # several seconds, making a successful live size change invisible.
            for flake in self.flakes:
                flake.shape = weighted_choice(
                    self.rng, self.args.flake_sizes, self.args.size_weights)
            self.flake_distribution = distribution
        weather_distribution = (
            self.args.weather, self.args.rain_share,
            self.args.hail_share, self.args.rain_speed,
            self.args.weather_foreground_share)
        if weather_distribution != self.weather_distribution:
            # Rebuild the current population as well as future spawns. This
            # makes changes to precipitation mix and rain velocity visible
            # immediately even when --max-flakes has already been reached.
            self.flakes = ([] if self.args.weather == "none" else
                           [self.new_flake(initial=True) for _ in self.flakes])
            self.weather_distribution = weather_distribution
        if self.args.lightning_interval != self.lightning_interval_setting:
            self.lightning_timer = min(
                self.lightning_timer, self.args.lightning_interval)
            self.lightning_interval_setting = self.args.lightning_interval
        for particle in self.flakes:
            if particle.kind == "rain":
                particle.colour = self.args.rain_colour
            elif particle.kind == "hail":
                particle.colour = self.args.hail_colour
        if len(self.resting_snow) > self.args.object_snow_max:
            self.resting_snow = self.resting_snow[-self.args.object_snow_max:]
        if not self.physics.object_enabled:
            self.resting_snow = []
        self.sync_rabbits()
        self.sync_tumbleweeds()
        if not self.args.snow_plough:
            self.plough.active = False
        elif self.plough.active:
            self.plough.path_y = self.height * (1.0 - self.args.plough_clear_to) - 1
            self.plough.y = self.plough.path_y
        if not self.args.santa_presents or "cabin" not in self.args.scenery_set:
            self.present_drops = []

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
            if (self.helicopter_exclusion_active and
                    abs(proposed_x - self.helicopter_exclusion_x) <
                    self.helicopter_exclusion_radius + weed.radius):
                weed.direction = (-1 if weed.x <= self.helicopter_exclusion_x
                                  else 1)
                weed.blocked_time = 0.0
                weed.vertical_speed = 0.0
                continue
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
        state = current_sky_event_state(self.args, self, elapsed)
        if (state is None or state["kind"] != "santa" or
                self.args.santa_trail_seconds <= 0):
            self.santa_trail_credit = 0.0
            return
        x, y = state["x"], state["y"]
        direction, event_index = state["direction"], state["event_index"]
        unit = santa_flyby_unit(self, state.get("scale"))
        sleigh_x = x - direction * 29 * unit
        trail_length = max(0.1, self.args.santa_trail_length)
        self.santa_trail_credit += dt * 18.0 * min(4.0, trail_length)
        count = min(12, int(self.santa_trail_credit))
        self.santa_trail_credit -= count
        for index in range(count):
            ttl = self.args.santa_trail_seconds * self.rng.uniform(0.65, 1.0)
            self.santa_trail.append(CometParticle(
                x=sleigh_x - direction * self.rng.uniform(
                    13, 19 * trail_length) * unit,
                y=y + self.rng.uniform(-2.0, 3.0) * unit,
                ttl=ttl, maximum_ttl=ttl,
                colour_index=(event_index + index + len(self.santa_trail)) % 5))
        self.santa_trail = self.santa_trail[-int(240 * max(1.0, trail_length)):]

    def step_helicopter(self, dt, elapsed):
        """Create landed cargo and couple rotor energy into air and loose snow."""
        state = current_sky_event_state(self.args, self, elapsed)
        active = (state is not None and
                  state["kind"] in ("helicopter", "airwolf"))
        intensity = 0.0
        self.helicopter_exclusion_active = False
        if active:
            phase = state["phase"]
            intensity = {
                "heli_approach": 0.12,
                "heli_hover": 0.32,
                "heli_descent": 0.45 + state["phase_progress"] * 0.55,
                "heli_landed": 1.0,
                "heli_takeoff": 1.0 - state["phase_progress"] * 0.58,
                "heli_turn": 0.30,
                "heli_departure": 0.18,
            }.get(phase, 0.0) * self.args.helicopter_downwash
            if (phase == "heli_landed" and state["phase_progress"] >= 0.34 and
                    state["event_index"] not in self.helicopter_crate_events):
                self.helicopter_crate_events.add(state["event_index"])
                snow_line = max(0, min(
                    self.height - 1, int(round(self.scenery_ground_y))))
                road_y, _ = cabin_path_network(
                    self.args, self.width, self.height, snow_line)
                self.supply_crates.append(SupplyCrate(
                    crate_id=state["event_index"],
                    x=state["x"] + state["direction"] * 17,
                    y=state.get("ground_contact_y", road_y)))
                self.supply_crates = self.supply_crates[-8:]

            radius = max(10.0, min(
                self.width * 0.42,
                34.0 * state.get("scale", 1.0) *
                self.args.helicopter_downwash_width))
            if phase in ("heli_hover", "heli_descent", "heli_landed",
                         "heli_takeoff"):
                # A landed rotor disc is a hard dynamic exclusion zone. The
                # site was selected clear of people/rabbits; this guard keeps
                # all ground actors from walking or rolling back underneath.
                self.helicopter_exclusion_active = True
                self.helicopter_exclusion_x = state["x"]
                self.helicopter_exclusion_radius = max(22.0, radius * 0.82)
                for rabbit in self.rabbits:
                    if (rabbit.state not in ("hidden", "abducting") and
                            abs(rabbit.x - state["x"]) <
                            self.helicopter_exclusion_radius):
                        rabbit.direction = -1 if rabbit.x <= state["x"] else 1
                        rabbit.x = (state["x"] + rabbit.direction *
                                    self.helicopter_exclusion_radius)
                        rabbit.state = "startled"
                        rabbit.timer = max(rabbit.timer, 1.4)
                if (self.postman.state != "hidden" and
                        abs(self.postman.x - state["x"]) <
                        self.helicopter_exclusion_radius):
                    side = -1 if self.postman.x <= state["x"] else 1
                    self.postman.x = (state["x"] + side *
                                      self.helicopter_exclusion_radius)
                for weed in self.tumbleweeds:
                    limit = self.helicopter_exclusion_radius + weed.radius
                    if abs(weed.x - state["x"]) < limit:
                        weed.direction = -1 if weed.x <= state["x"] else 1
                        weed.x = state["x"] + weed.direction * limit
            # Airborne precipitation is pushed radially away and slightly up.
            if intensity > 0.02:
                for particle in self.flakes:
                    dx = particle.x - state["x"]
                    dy = particle.y - state["y"]
                    distance = math.hypot(dx, dy)
                    if 0.5 < distance < radius * 2.4:
                        coupling = (1.0 - distance / (radius * 2.4)) * intensity
                        particle.x += dx / distance * coupling * 58.0 * dt
                        particle.y -= coupling * 24.0 * dt
                        particle.drift += dx / distance * coupling * 3.5
                for chunk in self.chunks:
                    dx = chunk.x - state["x"]
                    distance = abs(dx)
                    if distance < radius * 1.5:
                        coupling = (1.0 - distance / (radius * 1.5)) * intensity
                        chunk.drift += (1 if dx >= 0 else -1) * coupling * 18.0
                        chunk.speed += coupling * 9.0
                retained = []
                for patch in self.resting_snow:
                    dx = patch.x - state["x"]
                    if abs(dx) < radius * 1.25 and intensity > 0.35:
                        self.chunks.append(FallingChunk(
                            x=patch.x, y=patch.y,
                            speed=self.args.fall_speed * self.rng.uniform(0.8, 1.5),
                            drift=(1 if dx >= 0 else -1) *
                                  self.rng.uniform(8.0, 24.0) * intensity,
                            shape=patch.shape, colour=patch.colour))
                    else:
                        retained.append(patch)
                self.resting_snow = retained
                self.downwash_credit += dt * 46.0 * intensity
                count = min(18, int(self.downwash_credit))
                self.downwash_credit -= count
                for _ in range(count):
                    angle = self.rng.uniform(0.12, math.pi - 0.12)
                    speed = self.rng.uniform(16.0, 42.0) * intensity
                    visual_unit = (compact_flyby_unit(self, 70) * 2.30 *
                                   state.get("scale", 1.0))
                    # Begin below and outside the fuselage silhouette. The
                    # rotor stream used to be emitted at (x,y+4..10), which
                    # visibly painted snow through the centre of the craft.
                    side = self.rng.choice((-1, 1))
                    inner = max(10.5 * visual_unit, radius * 0.22)
                    outer = max(inner + 1.0, radius * 0.72)
                    outward = ((0.45 + 0.55 * abs(math.cos(angle))) *
                               speed * side)
                    self.downwash_particles.append(DownwashParticle(
                        x=state["x"] + side * self.rng.uniform(inner, outer),
                        y=state["y"] + self.rng.uniform(
                            11.5, 15.5) * visual_unit,
                        vx=outward,
                        vy=abs(math.sin(angle)) * speed * 0.45,
                        ttl=self.rng.uniform(0.55, 1.35),
                        maximum_ttl=1.35,
                        depth=state.get("scene_depth", 1.0)))
                # Near-ground downwash scours a shallow bowl and ejects snow.
                if phase in ("heli_descent", "heli_landed", "heli_takeoff"):
                    centre = int(round(state["x"]))
                    span = max(4, int(radius * 0.72))
                    for offset in range(-span, span + 1):
                        index = max(0, min(self.width - 1, centre + offset))
                        taper = max(0.0, 1.0 - abs(offset) / span)
                        removed = min(self.depths[index],
                                      dt * intensity * taper * 8.5)
                        self.depths[index] -= removed
                    self.downwash_snow_events += 1
        else:
            self.downwash_credit = 0.0

        particles = []
        for particle in self.downwash_particles:
            particle.ttl -= dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vx *= max(0.0, 1.0 - dt * 1.2)
            if particle.ttl > 0 and -8 < particle.x < self.width + 8:
                particles.append(particle)
        self.downwash_particles = particles[-360:]

        debris = []
        for piece in self.crate_debris:
            piece.ttl -= dt
            piece.x += piece.vx * dt
            piece.y += piece.vy * dt
            piece.vy += SeasonalPhysics.GRAVITY * 0.28 * dt
            if piece.ttl > 0:
                debris.append(piece)
        self.crate_debris = debris

    def step_ufo_trail(self, dt, elapsed):
        survivors = []
        for particle in self.ufo_trail:
            particle.ttl -= dt
            if particle.ttl > 0:
                survivors.append(particle)
        self.ufo_trail = survivors
        state = current_sky_event_state(self.args, self, elapsed)
        if (state is None or state["kind"] != "ufo" or
                state["phase"] == "abduction" or self.args.ufo_trail_seconds <= 0):
            self.ufo_trail_credit = 0.0
            return
        scale = state.get("scale", 1.0)
        unit = compact_flyby_unit(self, 65) * max(0.12, scale)
        self.ufo_trail_credit += dt * 13.0 * self.args.ufo_trail_length
        count = min(8, int(self.ufo_trail_credit))
        self.ufo_trail_credit -= count
        for index in range(count):
            ttl = self.args.ufo_trail_seconds * self.rng.uniform(0.55, 1.0)
            self.ufo_trail.append(CometParticle(
                x=state["x"] - state["direction"] * self.rng.uniform(
                    5.0, 14.0 * self.args.ufo_trail_length) * unit,
                y=state["y"] + self.rng.uniform(-3.0, 3.0) * unit,
                ttl=ttl, maximum_ttl=ttl,
                colour_index=(state["event_index"] + index +
                              len(self.ufo_trail)) % 5,
            ))
        self.ufo_trail = self.ufo_trail[-240:]

    def step_santa_presents(self, dt, elapsed):
        """Drop parcels vertically into chimney openings as Santa crosses them."""
        survivors = []
        for present in self.present_drops:
            present.speed += SeasonalPhysics.GRAVITY * 0.45 * dt
            present.y += present.speed * dt
            present.x += (present.target_x - present.x) * min(1.0, dt * 4.5)
            if present.y >= present.target_y:
                self.present_delivery_count += 1
            else:
                survivors.append(present)
        self.present_drops = survivors

        state = current_sky_event_state(self.args, self, elapsed)
        enabled = (self.args.santa_presents and state is not None and
                   state["kind"] == "santa" and "cabin" in self.args.scenery_set)
        if not enabled:
            self.last_santa_event_index = -1
            self.last_santa_sleigh_x = None
            return
        unit = santa_flyby_unit(self, state.get("scale"))
        sleigh_x = state["x"] - state["direction"] * 29 * unit
        event_index = state["event_index"]
        if self.last_santa_event_index != event_index:
            self.last_santa_event_index = event_index
            self.last_santa_sleigh_x = sleigh_x
            return
        previous_x = self.last_santa_sleigh_x
        self.last_santa_sleigh_x = sleigh_x
        if previous_x is None:
            return
        left, right = sorted((previous_x, sleigh_x))
        targets = cabin_chimney_targets(
            self.args, self.width, self.height,
            max(0, min(self.height - 1, int(round(self.scenery_ground_y)))))
        for cabin_index, chimney_x, chimney_y in targets:
            key = (event_index, cabin_index)
            if key in self.present_drop_keys or not left <= chimney_x <= right:
                continue
            self.present_drop_keys.add(key)
            drop_rng = random.Random(
                self.args.seed + event_index * 4001 + cabin_index * 131)
            parcel_count = drop_rng.randint(
                self.args.santa_presents_min, self.args.santa_presents_max)
            # Every parcel leaves the sleigh on this exact frame, while its
            # initial velocity and tiny horizontal offset remain individual.
            for parcel in range(parcel_count):
                self.present_drops.append(PresentDrop(
                    x=chimney_x,
                    y=state["y"] - 3 * unit,
                    target_x=chimney_x, target_y=chimney_y,
                    speed=self.args.present_fall_speed *
                    drop_rng.uniform(0.62, 1.46),
                    colour_index=(event_index + cabin_index + parcel) % 5,
                    event_index=event_index,
                ))

    def sync_rabbits(self, initial=False):
        while len(self.rabbits) < self.args.rabbit_count:
            index = len(self.rabbits)
            rng = random.Random(self.args.seed + 32003 + index * 79)
            self.rabbits.append(Rabbit(
                x=-20.0, direction=1, state="hidden",
                timer=rng.uniform(2.0, max(2.1, self.args.rabbit_interval)),
                phase=rng.uniform(0, math.tau),
                hops_before_pause=rng.randint(3, 8),
                # Alternate near and far lanes before adding a middle lane.
                # This guarantees useful cabin occlusion with two rabbits
                # while keeping each rabbit's perspective stable over time.
                depth=max(0.42, min(1.0,
                    (0.92, 0.52, 0.72)[index % 3] + rng.uniform(-0.035, 0.035))),
            ))
        if len(self.rabbits) > self.args.rabbit_count:
            self.rabbits = self.rabbits[:self.args.rabbit_count]
            if (self.abducted_rabbit_index is not None and
                    self.abducted_rabbit_index >= len(self.rabbits)):
                self.abducted_rabbit_index = None
                self.ufo_beam_active = False

    def hide_rabbit(self, rabbit):
        rabbit.state = "hidden"
        rabbit.timer = self.rng.uniform(self.args.rabbit_interval * 0.65,
                                        self.args.rabbit_interval * 1.35)

    def step_rabbits(self, dt, elapsed):
        tumbleweeds = tumbleweed_states(self.args, self, elapsed)
        for rabbit in self.rabbits:
            if rabbit.state in ("abducting", "ufo_waiting"):
                continue
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
            parallax = 0.55 + 0.45 * rabbit.depth
            pace = (self.args.rabbit_speed * parallax *
                    (1.85 if rabbit.state == "startled" else 1.0))
            if rabbit.state != "eating":
                proposed_x = rabbit.x + rabbit.direction * pace * dt
                if (self.helicopter_exclusion_active and
                        abs(proposed_x - self.helicopter_exclusion_x) <
                        self.helicopter_exclusion_radius):
                    rabbit.direction = (-1 if rabbit.x <=
                                        self.helicopter_exclusion_x else 1)
                    rabbit.state = "startled"
                    rabbit.timer = max(rabbit.timer, 1.2)
                else:
                    rabbit.x = proposed_x
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

    def collapse_postman_path(self, postman):
        """Compact and slump fresh bank snow under spaced delivery footsteps."""
        if not self.physics.ground_enabled or not self.args.accumulate:
            return
        spacing = max(1.5, postman.figure_height * 0.16)
        if abs(postman.x - postman.last_collapse_x) < spacing:
            return
        centre = max(0, min(self.width - 1, int(round(postman.x))))
        radius = max(1, int(round(postman.figure_height * 0.10)))
        strength = max(0.35, postman.figure_height * 0.075)
        removed = []
        for offset in range(-radius, radius + 1):
            x = max(0, min(self.width - 1, centre + offset))
            taper = 1.0 - 0.55 * abs(offset) / max(1, radius)
            old = self.depths[x]
            self.depths[x] = max(0.0, old - strength * taper)
            self.tower_ages[x] = 0.0
            if old - self.depths[x] > 0.2:
                removed.append((x, self.height - old))
        if removed:
            x, y = removed[len(removed) // 2]
            self.chunks.append(FallingChunk(
                x=x, y=y, speed=self.args.fall_speed * 0.45,
                drift=self.rng.uniform(-0.8, 0.8), shape="tiny",
                colour=self.rng.choice(self.palette["bank"][:2])))
            self.postman_snow_collapses += 1
        postman.last_collapse_x = postman.x

    def step_postman(self, dt):
        """Leave the road, post at a cabin, return, turn and continue."""
        postman = self.postman
        enabled = (self.args.postman and self.args.postman_delivery_frequency > 0 and
                   "cabin" in self.args.scenery_set)
        snow_line = max(0, min(
            self.height - 1, int(round(self.scenery_ground_y))))
        targets = cabin_door_targets(
            self.args, self.width, self.height, snow_line)
        path_road_y, path_spurs = cabin_path_network(
            self.args, self.width, self.height, snow_line)
        if not enabled or not targets:
            postman.state = "hidden"
            return
        if postman.state == "hidden":
            postman.timer -= dt
            if postman.timer > 0:
                return
            target = targets[self.postman_next_cabin % len(targets)]
            self.postman_next_cabin += 1
            cabin_index, door_x, door_bottom, door_height = target
            postman.direction = self.rng.choice((-1, 1))
            postman.x = (-18.0 if postman.direction > 0
                         else self.width + 18.0)
            postman.y = path_road_y
            postman.target_cabin = cabin_index
            postman.door_x = door_x
            rabbit_height = 11.0 * max(
                1.0, min(2.0, self.height // 80))
            former_height = max(
                9.0, min(door_height * 0.94, rabbit_height * 1.12))
            postman.road_figure_height = former_height * 1.70
            postman.door_figure_height = min(
                postman.road_figure_height, door_height * 0.88)
            postman.figure_height = postman.road_figure_height
            route = next(points for index, points in path_spurs
                         if index == cabin_index)
            postman.route = route
            postman.route_index = 0
            postman.route_progress = 0.0
            postman.road_x, postman.road_y = route[0]
            postman.target_x = postman.road_x
            # A distant cabin's actual elevated door is the destination. The
            # road remains on the foreground terrain, producing a genuinely
            # long perspective walk and continuous scale change.
            postman.door_y = min(postman.road_y - 2.0, door_bottom)
            if postman.route:
                postman.route = (*postman.route[:-1],
                                 (postman.door_x, postman.door_y))
            postman.route_length = max(1.0, sum(
                math.hypot(right[0] - left[0], right[1] - left[1])
                for left, right in zip(postman.route, postman.route[1:])))
            postman.phase = 0.0
            postman.turn_progress = 0.0
            postman.handed_over = False
            postman.last_collapse_x = -1000000.0
            sealed = next((crate for crate in self.supply_crates
                           if crate.state == "sealed"), None)
            if sealed is not None:
                postman.crate_id = sealed.crate_id
                postman.target_x = sealed.x
                postman.state = "walking_to_crate"
            else:
                postman.crate_id = -1
                postman.state = "walking_to"
            return

        if postman.state in ("opening_crate", "taking_mail", "breaking_crate"):
            postman.timer -= dt
            postman.phase += dt * (4.0 if postman.state == "breaking_crate" else 2.0)
            crate = next((item for item in self.supply_crates
                          if item.crate_id == postman.crate_id), None)
            if crate is None:
                postman.state = "walking_to"
                postman.target_x = postman.road_x
                return
            if postman.state == "opening_crate":
                crate.state = "open"
                if postman.timer <= 0:
                    postman.state = "taking_mail"
                    postman.timer = 1.25
            elif postman.state == "taking_mail":
                if postman.timer <= 0:
                    crate.state = "empty"
                    postman.state = "breaking_crate"
                    postman.timer = 1.0
            elif postman.timer <= 0:
                crate.state = "removed"
                for piece in range(9):
                    angle = math.tau * piece / 9.0 + self.rng.uniform(-0.25, 0.25)
                    ttl = self.rng.uniform(2.5, 5.0)
                    self.crate_debris.append(CrateDebris(
                        x=crate.x, y=crate.y - 2,
                        vx=math.cos(angle) * self.rng.uniform(2.0, 7.0),
                        vy=-abs(math.sin(angle)) * self.rng.uniform(2.0, 7.0),
                        ttl=ttl, maximum_ttl=ttl))
                postman.state = "walking_to"
                postman.target_x = postman.road_x
                postman.crate_id = -1
            return

        turn_seconds = 0.72
        if postman.state == "turning_in":
            postman.turn_progress = min(
                1.0, postman.turn_progress + dt / turn_seconds)
            if postman.turn_progress >= 1.0:
                postman.state = "approaching"
                postman.route_index = min(1, len(postman.route) - 1)
                postman.route_progress = 0.0
                postman.phase = 0.0
            return

        if postman.state == "turning_out":
            postman.turn_progress = min(
                0.0, postman.turn_progress + dt / turn_seconds)
            if postman.turn_progress >= 0.0:
                postman.state = "walking_on"
                postman.phase = 0.0
            return

        if postman.state == "turning_from_house":
            postman.turn_progress = max(
                -1.0, postman.turn_progress - dt / (turn_seconds * 1.35))
            if postman.turn_progress <= -1.0:
                postman.state = "returning"
                postman.route_index = max(0, len(postman.route) - 2)
                postman.route_progress = 1.0
                postman.phase = 0.0
            return

        if postman.state in ("approaching", "returning"):
            destination_x, destination_y = postman.route[postman.route_index]
            dx, dy = destination_x - postman.x, destination_y - postman.y
            distance = math.hypot(dx, dy)
            speed = self.args.postman_speed * (
                0.46 if postman.state == "approaching" else 0.56)
            movement = speed * dt
            postman.phase += dt * speed * 0.70
            if distance <= max(0.25, movement):
                postman.x, postman.y = destination_x, destination_y
                if postman.state == "approaching":
                    if postman.route_index < len(postman.route) - 1:
                        postman.route_index += 1
                    else:
                        postman.figure_height = postman.door_figure_height
                        postman.state = "posting"
                        postman.timer = max(
                            0.65, min(1.2, self.args.postman_stop_seconds * 0.25))
                        postman.phase = 0.0
                else:
                    if postman.route_index > 0:
                        postman.route_index -= 1
                    else:
                        postman.figure_height = postman.road_figure_height
                        postman.state = "turning_out"
                        postman.turn_progress = -1.0
                return
            proposed_x = postman.x + dx / distance * movement
            proposed_y = postman.y + dy / distance * movement
            if (self.helicopter_exclusion_active and
                    abs(proposed_x - self.helicopter_exclusion_x) <
                    self.helicopter_exclusion_radius):
                return
            postman.x = proposed_x
            postman.y = proposed_y
            if postman.state == "approaching":
                self.collapse_postman_path(postman)
            if postman.state == "approaching":
                postman.route_progress = min(
                    1.0, postman.route_progress + movement / postman.route_length)
                progress = postman.route_progress
                start_height = postman.road_figure_height
                end_height = postman.door_figure_height
            else:
                postman.route_progress = max(
                    0.0, postman.route_progress - movement / postman.route_length)
                progress = postman.route_progress
                start_height = postman.road_figure_height
                end_height = postman.door_figure_height
            progress = max(0.0, min(1.0, progress))
            postman.figure_height = (
                start_height + (end_height - start_height) * progress)
            return

        if postman.state == "posting":
            postman.timer -= dt
            if (not postman.handed_over and
                    postman.timer <= 0.35):
                postman.handed_over = True
                self.postman_delivery_count += 1
            if postman.timer <= 0:
                postman.state = "waiting"
                postman.timer = self.args.postman_stop_seconds
            return

        if postman.state == "waiting":
            postman.timer -= dt
            if postman.timer <= 0:
                postman.state = "turning_from_house"
                postman.turn_progress = 1.0
            return

        old_x = postman.x
        proposed_x = postman.x + postman.direction * self.args.postman_speed * dt
        if (self.helicopter_exclusion_active and
                abs(proposed_x - self.helicopter_exclusion_x) <
                self.helicopter_exclusion_radius):
            return
        postman.x = proposed_x
        postman.y = path_road_y
        postman.phase += dt * self.args.postman_speed * 0.62
        if postman.state in ("walking_to", "walking_to_crate"):
            crossed = ((postman.direction > 0 and
                        old_x <= postman.target_x <= postman.x) or
                       (postman.direction < 0 and
                        postman.x <= postman.target_x <= old_x))
            if crossed:
                if postman.state == "walking_to_crate":
                    postman.x = postman.target_x
                    postman.y = path_road_y
                    postman.state = "opening_crate"
                    postman.timer = 1.1
                else:
                    postman.x = postman.road_x
                    postman.y = postman.road_y
                    postman.state = "turning_in"
                    postman.turn_progress = 0.0
                    postman.phase = 0.0
                return
        if postman.x < -24 or postman.x > self.width + 24:
            postman.state = "hidden"
            postman.timer = (
                self.args.postman_interval /
                max(0.01, self.args.postman_delivery_frequency) *
                self.rng.uniform(0.75, 1.25))

    def step_ufo_abduction(self, elapsed):
        """Stage a rabbit under a swooping UFO, then lift it vertically."""
        state = current_sky_event_state(self.args, self, elapsed)
        encounter = (self.args.ufo_abduction and state is not None and
                     state["kind"] == "ufo" and bool(self.rabbits))
        if not encounter:
            self.ufo_beam_active = False
            if self.abducted_rabbit_index is not None:
                self.hide_rabbit(self.rabbits[self.abducted_rabbit_index])
                self.abducted_rabbit_index = None
            if self.ufo_target_rabbit_index is not None:
                target = self.rabbits[self.ufo_target_rabbit_index]
                if target.state == "ufo_waiting":
                    self.hide_rabbit(target)
            self.ufo_target_rabbit_index = None
            self.ufo_target_event_index = -1
            return

        event_index = state["event_index"]
        target_x = self.ufo_target_x_by_event[event_index]
        if self.ufo_target_event_index != event_index:
            rabbit_index = self.ufo_target_rabbit_by_event.get(event_index)
            if (rabbit_index is None or rabbit_index >= len(self.rabbits) or
                    self.rabbits[rabbit_index].state == "hidden"):
                self.ufo_beam_active = False
                self.ufo_target_rabbit_index = None
                self.ufo_target_event_index = event_index
                return
            rabbit = self.rabbits[rabbit_index]
            # Freeze the same already-visible rabbit which established the
            # destination; never create or move a hidden stand-in for capture.
            target_x = rabbit.x
            self.ufo_target_x_by_event[event_index] = target_x
            rabbit.state = "ufo_waiting"
            self.ufo_target_rabbit_index = rabbit_index
            self.ufo_target_event_index = event_index

        if state["phase"] == "approach":
            self.ufo_beam_active = False
            return
        if state["phase"] == "departure":
            self.ufo_beam_active = False
            if self.ufo_target_rabbit_index is not None:
                rabbit = self.rabbits[self.ufo_target_rabbit_index]
                if rabbit.state == "ufo_waiting":
                    self.hide_rabbit(rabbit)
            return
        if state["phase"] != "abduction":
            return

        if self.abduction_event_index != event_index:
            rabbit_index = self.ufo_target_rabbit_index
            if rabbit_index is None:
                return
            rabbit = self.rabbits[rabbit_index]
            rabbit.x = target_x
            rabbit.abduction_origin_x = rabbit.x
            rabbit.abduction_origin_y = rabbit_scene_ground_y(self, rabbit)
            rabbit.abduction_x = rabbit.abduction_origin_x
            rabbit.abduction_y = rabbit.abduction_origin_y
            rabbit.abduction_scale = rabbit_scene_scale(self, rabbit)
            rabbit.state = "abducting"
            self.abducted_rabbit_index = rabbit_index
            self.abduction_event_index = event_index
        elif self.abducted_rabbit_index is None:
            # This event already completed; do not abduct a second rabbit
            # during the same stationary hover.
            return

        rabbit = self.rabbits[self.abducted_rabbit_index]
        raw_progress = state["phase_progress"]
        progress = raw_progress * raw_progress * (3.0 - 2.0 * raw_progress)
        unit = compact_flyby_unit(self, 65)
        target_y = state["y"] + 7 * unit
        rabbit.abduction_x = state["x"]
        rabbit.abduction_y = (rabbit.abduction_origin_y * (1.0 - progress) +
                              target_y * progress)
        normal_scale = rabbit_scene_scale(self, rabbit)
        # The rabbit silhouette is about ten scale units wide. A target scale
        # of 0.5 UFO units therefore makes it 10% of the 50-unit saucer width.
        target_scale = max(0.25, unit * 0.5)
        rabbit.abduction_scale = (normal_scale * (1.0 - progress) +
                                   target_scale * progress)
        self.ufo_beam_target_y = rabbit.abduction_y
        self.ufo_beam_active = raw_progress < 0.98
        if raw_progress >= 0.98:
            self.hide_rabbit(rabbit)
            self.abducted_rabbit_index = None
            self.ufo_beam_active = False
            self.ufo_abduction_count += 1

    def step_parachutists(self, dt, elapsed):
        """Animate rare far-layer ejections through freefall and canopy drift."""
        survivors = []
        landing_y = self.height * 0.88
        for pilot in self.parachutists:
            pilot.timer -= dt
            pilot.phase += dt * (7.0 if not pilot.canopy_open else 2.5)
            if not pilot.canopy_open:
                pilot.vy += SeasonalPhysics.GRAVITY * 0.55 * dt
                if pilot.timer <= 0:
                    pilot.canopy_open = True
                    pilot.vy = min(pilot.vy, self.args.parachute_fall_speed)
            else:
                pilot.vy += ((self.args.parachute_fall_speed - pilot.vy) *
                             min(1.0, dt * 2.5))
                pilot.vx += ((self.args.wind * 0.06 - pilot.vx) *
                             min(1.0, dt * 1.4))
            pilot.x += pilot.vx * dt
            pilot.y += pilot.vy * dt
            if pilot.y < landing_y and -20 < pilot.x < self.width + 20:
                survivors.append(pilot)
        self.parachutists = survivors

        state = current_sky_event_state(self.args, self, elapsed)
        if (not self.args.pilot_ejection or state is None or
                state["kind"] != "aeroplane" or
                not 0.46 <= state["phase_progress"] <= 0.72 or
                state["event_index"] in self.ejection_events):
            return
        self.ejection_events.add(state["event_index"])
        event_rng = random.Random(
            self.args.seed + 94009 + state["event_index"] * 137)
        if event_rng.random() > self.args.ejection_chance:
            return
        unit = aeroplane_flyby_unit(self)
        self.parachutists.append(Parachutist(
            x=state["x"] - state["direction"] * 5 * unit,
            y=state["y"] + 5 * unit,
            vx=-state["direction"] * self.args.flyby_speed * 0.07,
            vy=-3.0, timer=event_rng.uniform(0.55, 0.95),
            canopy_open=False, phase=0.0,
        ))
        self.pilot_ejection_count += 1
        if self.args.aircraft_crash:
            depth_mode = self.args.aircraft_crash_depth
            if depth_mode == "auto":
                depth_mode = event_rng.choice(("away", "toward"))
            target_y = (self.height * event_rng.uniform(0.48, 0.62)
                        if depth_mode == "away" else
                        self.surface_y(state["x"]) - 1.0)
            self.aircraft_crashes.append(AircraftCrash(
                event_index=state["event_index"],
                aircraft_type=state.get("aircraft_type") or "commuter",
                direction=state["direction"],
                x=state["x"], y=state["y"], start_y=state["y"],
                vx=state["direction"] * self.args.flyby_speed * 0.48,
                vy=-self.args.aircraft_crash_descent *
                   self.args.aircraft_crash_arc,
                rotation=0.0,
                angular_velocity=(state["direction"] * math.tau *
                                  self.args.aircraft_crash_spin),
                scale=1.0,
                target_scale=0.22 if depth_mode == "away" else 1.75,
                target_y=target_y, depth_mode=depth_mode,
            ))

    def step_aircraft_crashes(self, dt):
        """Advance disabled aircraft, persistent trails and ground impacts."""
        survivors = []
        for crash in self.aircraft_crashes:
            crash.age += dt
            crash.vy += self.args.aircraft_crash_descent * 1.28 * dt
            crash.vx *= max(0.0, 1.0 - dt * 0.12)
            crash.x += crash.vx * dt
            crash.y += crash.vy * dt
            crash.rotation += crash.angular_velocity * dt
            progress = max(0.0, min(
                1.0, (crash.y - crash.start_y) /
                max(1.0, crash.target_y - crash.start_y)))
            ease = progress * progress * (3.0 - 2.0 * progress)
            crash.scale = 1.0 + (crash.target_scale - 1.0) * ease
            self.crash_particle_credit += (
                dt * 28.0 * self.args.aircraft_crash_smoke)
            count = min(10, int(self.crash_particle_credit))
            self.crash_particle_credit -= count
            for index in range(count):
                maximum = self.rng.uniform(1.4, 4.8)
                self.crash_particles.append(CrashParticle(
                    x=crash.x - crash.vx * dt * self.rng.uniform(1.0, 3.2),
                    y=crash.y + self.rng.uniform(-2.0, 2.0) * crash.scale,
                    vx=-crash.vx * self.rng.uniform(0.02, 0.08) +
                       self.rng.uniform(-2.5, 2.5),
                    vy=self.rng.uniform(-4.0, 1.0), ttl=maximum,
                    maximum_ttl=maximum,
                    kind="fire" if index % 4 == 0 else "smoke",
                ))
            if crash.y >= crash.target_y:
                explosion_kind = self.args.explosion_types[
                    crash.event_index % len(self.args.explosion_types)]
                self.ground_explosions.append(GroundExplosion(
                    x=crash.x, y=crash.target_y, kind=explosion_kind,
                    duration=self.args.explosion_seconds,
                    scale=self.args.explosion_size * crash.scale,
                    seed=self.args.seed + crash.event_index * 991,
                    foreground=crash.depth_mode == "toward",
                ))
                self.aircraft_impact_count += 1
            elif -100 < crash.x < self.width + 100:
                survivors.append(crash)
        self.aircraft_crashes = survivors

        particles = []
        for particle in self.crash_particles:
            particle.ttl -= dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vy -= 1.4 * dt
            particle.vx *= max(0.0, 1.0 - dt * 0.25)
            if particle.ttl > 0:
                particles.append(particle)
        self.crash_particles = particles[-900:]
        explosions = []
        for explosion in self.ground_explosions:
            explosion.age += dt
            if explosion.age < explosion.duration:
                if explosion.foreground and self.physics.ground_enabled:
                    fraction = explosion.age / max(0.001, explosion.duration)
                    heat = max(0.0, 1.0 - fraction) ** 0.55
                    base_radius = 52.0 if explosion.kind == "nuclear" else 32.0
                    radius = max(7, int(base_radius * explosion.scale *
                                        (0.45 + 0.55 * min(1.0, fraction * 4))))
                    centre = int(round(explosion.x))
                    for x in range(max(0, centre - radius),
                                   min(self.width, centre + radius + 1)):
                        taper = max(0.0, 1.0 - abs(x - centre) / radius)
                        melt = dt * (15.0 if explosion.kind == "nuclear" else 9.0)
                        self.depths[x] = max(
                            0.0, self.depths[x] - melt * heat * taper)
                        self.tower_ages[x] = 0.0
                        self.mass_fallaway_ages[x] = 0.0
                    self.resting_snow = [
                        patch for patch in self.resting_snow
                        if abs(patch.x - explosion.x) >= radius
                    ]
                explosions.append(explosion)
        self.ground_explosions = explosions[-12:]

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
            # The vehicle rides on the shallow surface it leaves behind. The
            # six-revision-old implementation sampled the *uncleared* bank
            # before cutting it, which visually stranded the vehicle above the
            # road after that same frame removed the snow beneath it.
            plough.path_y = self.height * (1.0 - self.args.plough_clear_to) - 1
            plough.y = plough.path_y

        old_x = plough.x
        plough.x += plough.direction * self.args.plough_speed * dt
        # The vehicle follows the road datum, not the changing top of the bank
        # it is clearing. Snow depth therefore cannot make it climb or bob.
        plough.y = plough.path_y
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
            # Do not run a second full-width cleanup here. The blade already
            # cleared every crossed column; snow deposited behind it during
            # the pass is newer than the blade and must remain visible.
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
            if flake.kind == "hail" and flake.speed < self.args.fall_speed * 1.35:
                flake.speed += SeasonalPhysics.GRAVITY * 2.4 * dt
            flake.y += flake.speed * dt
            flutter = (math.sin(elapsed * flake.wobble + flake.phase) *
                       self.args.wobble)
            if flake.kind == "rain":
                flutter *= 0.12
            flake.x += (self.args.wind + gust + flake.drift + flutter) * dt
            flake.x %= self.width
            lowest = (max(1, int(round(self.args.hail_size))) if flake.kind == "hail"
                      else 0 if flake.kind == "rain"
                      else max(y for _, y in SHAPES[flake.shape]))
            scenery_y = self.scenery_hit(flake.x, old_y + lowest,
                                          flake.y + lowest)
            if (flake.kind == "snow" and scenery_y is not None and
                    self.catch_object_snow(flake, scenery_y)):
                continue
            ground_y = self.surface_y(flake.x)
            collision_y = scenery_y if flake.kind != "snow" else None
            if collision_y is None and flake.y + lowest >= ground_y:
                collision_y = ground_y
            if collision_y is not None:
                if (flake.kind == "hail" and flake.bounces < 2 and
                        self.rng.random() < self.args.hail_bounce):
                    flake.y = collision_y - lowest - 1
                    flake.speed = -max(5.0, abs(flake.speed) * 0.42)
                    flake.bounces += 1
                    survivors.append(flake)
                elif flake.kind == "snow":
                    self.deposit(flake)
            elif flake.y < self.height + 5:
                survivors.append(flake)
        self.flakes = survivors
        if self.args.weather == "none":
            self.flakes = []
            self.spawn_credit = 0.0
        else:
            self.spawn_credit += self.snow_rate * dt
        spawn = (0 if self.args.weather == "none" else
                 min(int(self.spawn_credit), self.max_flakes - len(self.flakes)))
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
        # Establish the live rotor exclusion before any ground actor advances.
        self.step_helicopter(dt, elapsed)
        self.step_tumbleweeds(dt, elapsed)
        self.step_santa_trail(dt, elapsed)
        self.step_ufo_trail(dt, elapsed)
        self.step_santa_presents(dt, elapsed)
        self.step_parachutists(dt, elapsed)
        self.step_aircraft_crashes(dt)
        self.step_lightning(dt)
        self.step_rabbits(dt, elapsed)
        self.step_postman(dt)
        self.step_ufo_abduction(elapsed)
        if self.physics.ground_enabled:
            self.detect_tower_collapses(dt)
            self.detect_mass_fallaways(dt)
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
    "drift", "wobble", "palette", "sky", "sky_colours", "sky_stops",
    "sky_blend", "clouds", "cloud_count", "cloud_speed", "cloud_depths",
    "cloud_parallax", "cloud_colours", "weather", "weather_foreground_share",
    "rain_share", "hail_share", "rain_speed",
    "rain_length", "rain_colour", "hail_size", "hail_bounce", "hail_colour",
    "lightning", "lightning_interval", "lightning_flash",
    "lightning_branches", "accumulation", "accumulate",
    "snow_repose_slope", "snow_relaxation",
    "shed_threshold", "shed_to", "shed_width", "shed_rate",
    "tower_collapse", "tower_age", "tower_age_jitter", "tower_prominence",
    "tower_collapse_rate", "tower_cascade_chance", "tower_cascade_radius",
    "snow_fallaway_threshold", "snow_fallaway_min_seconds",
    "snow_fallaway_max_seconds", "snow_fallaway_width",
    "scenery", "cabin", "reindeer", "no_trees", "tree_density", "max_trees",
    "tree_sway", "tree_types", "tree_branches", "tree_branch_levels",
    "tree_branch_angle", "tree_length_ratio", "tree_trunk_thickness",
    "tree_branch_thickness_ratio", "conifer_colour_variation",
    "tree_thickness_exponent", "tree_segment_budget", "lights",
    "object_snow", "object_snow_capture", "object_snow_max",
    "object_snow_hold", "object_snow_hold_jitter", "object_snow_adhesion",
    "cabin_count", "max_cabins", "cabin_scale",
    "cabin_types", "cabin_size_variation", "cabin_depth_share",
    "cabin_depth_scale", "cabin_path_style", "cabin_path_curl",
    "horizon_structure", "horizon_dirt_density", "horizon_randomness",
    "horizon_height", "horizon_hut_density",
    "ambient", "leaf_count", "tumbleweed_count", "ambient_speed",
    "tumbleweed_climb", "tumbleweed_collapse_pressure",
    "rabbit_count", "rabbit_interval", "rabbit_speed", "sky_events",
    "postman", "postman_interval", "postman_speed", "postman_stop_seconds",
    "postman_delivery_frequency", "flyby_interval", "flyby_speed",
    "superman_path", "superman_frequency", "superman_speed",
    "helicopter_hover_seconds", "helicopter_wait_min",
    "helicopter_wait_max", "helicopter_downwash",
    "helicopter_downwash_width",
    "aeroplane_types", "pilot_ejection",
    "ejection_chance", "parachute_fall_speed",
    "aircraft_crash", "aircraft_crash_depth", "aircraft_crash_descent",
    "aircraft_crash_arc", "aircraft_crash_spin", "aircraft_crash_smoke",
    "explosion_types", "explosion_size", "explosion_seconds",
    "ufo_beam_style",
    "ufo_types", "ufo_trail_seconds", "ufo_trail_length",
    "snow_plough", "plough_interval",
    "santa_scale_min", "santa_scale_max", "santa_arc_height", "santa_trail_seconds",
    "santa_trail_length", "santa_presents", "santa_presents_min",
    "santa_presents_max", "present_fall_speed",
    "ufo_abduction", "ufo_hover_seconds",
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
        self.restart_token = None
        self.restart_requested = False
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
            restart_token = int(payload.get("restart", 0))
            if self.restart_token is None:
                self.restart_token = restart_token
            elif restart_token != self.restart_token:
                self.restart_token = restart_token
                self.restart_requested = True
            self.last_revision = revision
            self.status = f"R{revision}"
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError, SystemExit):
            self.status = "ERROR"
            return False


def draw_shape(surface, shape, x, y, colour, priority):
    for dx, dy in SHAPES[shape]:
        surface.pixel(x + dx, y + dy, colour, priority)


def gradient_fraction(value, method):
    value = max(0.0, min(1.0, value))
    if method == "smooth":
        return value * value * (3.0 - 2.0 * value)
    if method == "cosine":
        return (1.0 - math.cos(math.pi * value)) * 0.5
    return value


def draw_sky_gradient(surface, args):
    """Fill the distant background with a configurable vertical RGB gradient."""
    if not args.sky:
        return
    colours = args.sky_colours
    stops = args.sky_stops
    for y in range(surface.height):
        position = y / max(1, surface.height - 1)
        interval = next(
            (index for index, stop in enumerate(stops[1:]) if position <= stop),
            len(stops) - 2)
        interval = min(interval, len(stops) - 2)
        left_stop, right_stop = stops[interval], stops[interval + 1]
        amount = gradient_fraction(
            (position - left_stop) / max(1e-9, right_stop - left_stop),
            args.sky_blend)
        left, right = colours[interval], colours[interval + 1]
        colour = tuple(int(round(a + (b - a) * amount))
                       for a, b in zip(left, right))
        start = y * surface.width
        surface.pixels[start:start + surface.width] = [(colour, 1)] * surface.width


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


def draw_cabin_paths(surface, engine):
    """Expose an irregular, non-obstructing dirt route through the snow."""
    if "cabin" not in engine.args.scenery_set:
        return
    snow_line = max(0, min(engine.height - 1,
                          int(round(engine.scenery_ground_y))))
    road_y, spurs = cabin_path_network(
        engine.args, engine.width, engine.height, snow_line)
    segments = [((0.0, road_y), (engine.width - 1.0, road_y))]
    for _, points in spurs:
        segments.extend(zip(points, points[1:]))
    colours = ((79, 57, 40), (104, 73, 47), (57, 47, 39))
    for segment_index, (start, end) in enumerate(segments):
        distance = max(1, int(math.ceil(math.hypot(
            end[0] - start[0], end[1] - start[1]))))
        rng = random.Random(engine.args.seed + 71011 + segment_index * 313)
        for step in range(distance + 1):
            if rng.random() > 0.64:
                continue
            amount = step / distance
            x = start[0] + (end[0] - start[0]) * amount
            y = start[1] + (end[1] - start[1]) * amount
            spread = 1.0 + 1.8 * math.sin(math.pi * amount)
            x += rng.uniform(-spread, spread)
            y += rng.uniform(-1.0, 1.0)
            surface.pixel(x, y, colours[rng.randrange(len(colours))], 74)


def draw_crates(surface, engine):
    """Draw landed supplies and short-lived broken timber without collision."""
    for crate in engine.supply_crates:
        if crate.state == "removed":
            continue
        size = max(3.0, min(7.0, engine.height / 28.0))
        wood, edge, straw = (151, 93, 43), (79, 48, 31), (220, 173, 72)
        surface.rectangle(crate.x - size, crate.y - size * 1.45,
                          crate.x + size, crate.y, wood, 88)
        surface.line(crate.x - size, crate.y - size * 1.45,
                     crate.x + size, crate.y, edge, 90)
        surface.line(crate.x + size, crate.y - size * 1.45,
                     crate.x - size, crate.y, edge, 90)
        surface.rectangle(crate.x - size, crate.y - size * 0.85,
                          crate.x + size, crate.y - size * 0.62, edge, 89)
        if crate.state in ("open", "empty"):
            surface.line(crate.x - size, crate.y - size * 1.45,
                         crate.x - size * 1.55, crate.y - size * 2.15,
                         edge, 91)
            surface.line(crate.x + size, crate.y - size * 1.45,
                         crate.x + size * 1.55, crate.y - size * 2.15,
                         edge, 91)
            if crate.state == "open":
                surface.rectangle(crate.x - size * 0.45, crate.y - size * 1.3,
                                  crate.x + size * 0.45, crate.y - size * 0.85,
                                  straw, 92)
    for debris in engine.crate_debris:
        fade = max(0.0, debris.ttl / debris.maximum_ttl)
        colour = tuple(int(channel * (0.25 + 0.75 * fade))
                       for channel in (132, 79, 39))
        surface.line(debris.x - 2 * fade, debris.y,
                     debris.x + 2 * fade, debris.y + debris.vy * 0.2,
                     colour, 86)


def draw_downwash(surface, engine, near=None):
    for particle in engine.downwash_particles:
        particle_near = particle.depth >= 0.68
        if near is not None and particle_near != near:
            continue
        fade = max(0.0, particle.ttl / particle.maximum_ttl)
        colour = tuple(int(channel * (0.28 + 0.72 * fade))
                       for channel in (215, 239, 246))
        surface.line(particle.x, particle.y,
                     particle.x - particle.vx * 0.06,
                     particle.y - particle.vy * 0.06, colour, 84)


def draw_object_snow(surface, engine):
    for patch in engine.resting_snow:
        shape = "small" if patch.mass >= 1.8 else patch.shape
        draw_shape(surface, shape, patch.x, patch.y, patch.colour, 78)


def draw_precipitation(surface, engine, layer=None):
    for particle in engine.flakes:
        if layer is not None and particle.layer != layer:
            continue
        if particle.kind == "rain":
            length = engine.args.rain_length
            slant = max(-length * 0.65, min(length * 0.65,
                        (engine.args.wind + gust_at(
                            engine.args, getattr(engine, "elapsed", 0.0))) * 0.10))
            surface.line(particle.x - slant, particle.y - length,
                         particle.x, particle.y, particle.colour, 90)
        elif particle.kind == "hail":
            filled_ellipse(surface, particle.x, particle.y,
                           engine.args.hail_size, engine.args.hail_size,
                           particle.colour, 91)
        else:
            draw_shape(surface, particle.shape, particle.x, particle.y,
                       particle.colour, 90)


def render_surface(background, engine):
    # Distant flybys are painted first and deliberately normalized to the
    # lowest depth. Scenery then replaces them pixel-for-pixel, so trees,
    # cabins, animals, banks and falling snow always occlude the sky objects.
    surface = Surface(background.width, background.height)
    draw_sky_gradient(surface, engine.args)
    draw_lightning(surface, engine)
    elapsed = getattr(engine, "elapsed", 0.0)
    draw_clouds(surface, engine, elapsed, near=False)
    event = current_sky_event_state(engine.args, engine, elapsed)
    helicopter_near = bool(
        event is not None and
        event["kind"] in ("helicopter", "airwolf") and
        event.get("scene_depth", 0.0) >= 0.68)
    # In distant phases the wake shares the flight layer and is painted first,
    # so the aircraft always occludes it rather than wearing it as a texture.
    draw_downwash(surface, engine, near=False)
    if not helicopter_near:
        draw_sky_event(surface, engine, elapsed, include_beam=False)
    draw_clouds(surface, engine, elapsed, near=True)
    draw_parachutists(surface, engine)
    draw_aircraft_crashes(surface, engine)
    draw_present_drops(surface, engine)
    surface.pixels = [(pixel[0], 3) if pixel is not None else None
                      for pixel in surface.pixels]
    draw_precipitation(surface, engine, "background")
    # A capture retains the rabbit's original lane. Its transporter is painted
    # in that same lane, immediately before the rabbit, so neither can jump
    # behind or in front of a cabin when the capture state begins.
    for rabbit in engine.rabbits:
        if rabbit.state == "abducting" and rabbit.depth < 0.68:
            draw_ufo_beam(surface, engine, elapsed, event)
            draw_rabbit(surface, engine, rabbit)
    # Far-lane rabbits occupy the scenery layer: cabins and trees overwrite
    # them naturally, which lets them pass behind buildings without masks.
    for rabbit in engine.rabbits:
        if rabbit.state not in ("abducting", "hidden") and rabbit.depth < 0.68:
            draw_rabbit(surface, engine, rabbit)
    for index, pixel in enumerate(background.pixels):
        if pixel is not None:
            surface.pixels[index] = pixel
    draw_accumulation(surface, engine)
    draw_cabin_paths(surface, engine)
    draw_downwash(surface, engine, near=True)
    if helicopter_near:
        # A helicopter owns one perspective lane for its entire event. Near
        # craft are composited over scenery from approach through departure;
        # distant craft were painted before scenery above and stay occluded
        # even after descending. Phase can no longer flip the depth order.
        landing_layer = Surface(surface.width, surface.height)
        draw_sky_event(landing_layer, engine, elapsed, include_beam=False)
        for index, pixel in enumerate(landing_layer.pixels):
            if pixel is not None:
                surface.pixels[index] = (pixel[0], max(85, pixel[1]))
    draw_object_snow(surface, engine)
    draw_ambient(surface, engine, getattr(engine, "elapsed", 0.0))
    draw_crates(surface, engine)
    for rabbit in engine.rabbits:
        if rabbit.state == "abducting" and rabbit.depth >= 0.68:
            draw_ufo_beam(surface, engine, elapsed, event)
            draw_rabbit(surface, engine, rabbit)
    for rabbit in engine.rabbits:
        if (rabbit.state not in ("abducting", "hidden") and
                rabbit.depth >= 0.68):
            draw_rabbit(surface, engine, rabbit)
    draw_postman(surface, engine)
    if ("reindeer" in engine.args.scenery_set and
            engine.postman.state != "hidden" and
            engine.postman.figure_height <
            reindeer_apparent_height(engine.width, engine.height)):
        # Apparent height is the depth proxy shared by the two figures. A
        # smaller postman is behind the reindeer; a taller one remains in
        # front. Copy only the animal at promoted priority, not all scenery.
        animal_layer = Surface(surface.width, surface.height)
        draw_reindeer(animal_layer, engine.width, engine.height,
                      int(round(engine.scenery_ground_y)))
        for index, pixel in enumerate(animal_layer.pixels):
            if pixel is not None:
                surface.pixels[index] = (pixel[0], max(106, pixel[1]))
    for chunk in engine.chunks:
        draw_shape(surface, chunk.shape, chunk.x, chunk.y, chunk.colour, 82)
    draw_precipitation(surface, engine, "foreground")
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
    blank_cells = populated_cells = background_cells = seam_guard_cells = 0
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
                reset_codes = []
                if active_colour is not None:
                    reset_codes.append("39")
                if active_background is not None:
                    reset_codes.append("49")
                if reset_codes:
                    parts.append("\x1b[" + ";".join(reset_codes) + "m")
                active_colour = None
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
            # A strict cell-owned font deliberately has no horizontal
            # overhang. At some CoreText/WezTerm pixel sizes that leaves a
            # device-pixel rounding gap at the glyph/line-box boundary. A
            # full-mask glyph has no transparent samples, so painting the same
            # colour behind it is visually exact while keeping the real PUA
            # full-mask glyph in the terminal cell. This prevents the terminal
            # default black from leaking through as a grid.
            seam_guard = mask == full_mask and background is None
            if seam_guard:
                background = colour
            quantized_background = (tuple((channel // 4) * 4 for channel in background)
                                    if background is not None else None)
            populated_cells += 1
            masks_used.add(mask)
            coloured_cells.add((mask, quantized, quantized_background))
            if seam_guard:
                seam_guard_cells += 1
            elif quantized_background is not None:
                background_cells += 1
            if codec.name == "pua4":
                if mask < 0x8000:
                    part0_cells += 1
                else:
                    part1_cells += 1
            # WezTerm flushes its printable-codepoint buffer at every control
            # sequence. Combine foreground and background changes into one SGR
            # so a two-colour cell creates one shaping boundary, not two.
            sgr_codes = []
            if quantized != active_colour:
                sgr_codes.append("38;2;%d;%d;%d" % quantized)
            if quantized_background != active_background:
                sgr_codes.append(
                    "49" if quantized_background is None else
                    "48;2;%d;%d;%d" % quantized_background)
            if sgr_codes:
                parts.append("\x1b[" + ";".join(sgr_codes) + "m")
            active_colour = quantized
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
            "seam_guard_cells": seam_guard_cells,
            "unique_masks": len(masks_used),
            "reused_masks": max(0, populated_cells - len(masks_used)),
            "unique_coloured_cells": len(coloured_cells),
            "part0_cells": part0_cells,
            "part1_cells": part1_cells,
            "mask_values": masks_used,
        })
    return "\n".join(lines)


def encode_surface_native(surface, codec, columns, rows, analyser, stats=None):
    """Build ANSI from Rust-analysed cell records; output semantics match Python."""
    records = analyser.analyse(surface, codec, columns, rows)
    lines = []
    blank_cells = populated_cells = background_cells = seam_guard_cells = 0
    masks_used, coloured_cells = set(), set()
    part0_cells = part1_cells = 0
    active_colour = active_background = None
    full_mask = (1 << (codec.cell_width * codec.cell_height)) - 1
    for cell_y in range(rows):
        parts = []
        for cell_x in range(columns):
            index = (cell_y * columns + cell_x) * 10
            record = records[index:index + 10]
            if not record[9]:
                blank_cells += 1
                reset_codes = []
                if active_colour is not None:
                    reset_codes.append("39")
                if active_background is not None:
                    reset_codes.append("49")
                if reset_codes:
                    parts.append("\x1b[" + ";".join(reset_codes) + "m")
                active_colour = None
                active_background = None
                parts.append(" ")
                continue
            mask = record[0] | record[1] << 8
            colour = tuple(record[2:5])
            background = tuple(record[5:8]) if record[8] else None
            seam_guard = mask == full_mask and background is None
            if seam_guard:
                background = colour
            populated_cells += 1
            masks_used.add(mask)
            coloured_cells.add((mask, colour, background))
            if seam_guard:
                seam_guard_cells += 1
            elif background is not None:
                background_cells += 1
            if codec.name == "pua4":
                if mask < 0x8000:
                    part0_cells += 1
                else:
                    part1_cells += 1
            sgr_codes = []
            if colour != active_colour:
                sgr_codes.append("38;2;%d;%d;%d" % colour)
            if background != active_background:
                sgr_codes.append("49" if background is None else
                                 "48;2;%d;%d;%d" % background)
            if sgr_codes:
                parts.append("\x1b[" + ";".join(sgr_codes) + "m")
            active_colour = colour
            active_background = background
            parts.append(chr(codec.codepoint(mask)))
        parts.append(RESET)
        active_colour = active_background = None
        lines.append("".join(parts))
    if stats is not None:
        stats.update({
            "cells": columns * rows, "blank_cells": blank_cells,
            "populated_cells": populated_cells,
            "background_cells": background_cells,
            "seam_guard_cells": seam_guard_cells,
            "unique_masks": len(masks_used),
            "reused_masks": max(0, populated_cells - len(masks_used)),
            "unique_coloured_cells": len(coloured_cells),
            "part0_cells": part0_cells, "part1_cells": part1_cells,
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


DASHBOARD_TABS = ("font", "snow", "sky", "weather", "trees", "animals", "flights", "process")


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
        flake_mix = ",".join(
            f"{name.upper()}:{weight:g}"
            for name, weight in zip(args.flake_sizes, args.size_weights))
        page = [
            (f" ❄ AIRBORNE {len(engine.flakes):,}/{engine.max_flakes:,} | RATE {engine.snow_rate:.1f}/s | "
             f"FALL {args.fall_speed:.1f} VPX/s | MIX {flake_mix}"),
            (f" ⚙ PHYSICS {args.physics.upper()} | WIND {args.wind:+.1f} GUST {args.gust_strength:.1f} | "
             f"GROUND MAX {engine.maximum_depth_fraction:.1%} AVG {engine.average_depth_fraction:.1%} | "
             f"ACCUMULATION {args.accumulation:.2f} | REPOSE {args.snow_repose_slope:.2f} RELAX {args.snow_relaxation:.1f}"),
            (f" ⇣ BROAD SHEDS {engine.shed_count} | LOCAL TOWERS {engine.tower_collapse_count} | "
             f"ACTIVE SLUMPS {len(engine.tower_collapses)} | FALLING CHUNKS {len(engine.chunks)}"),
            (f" ❅ OBJECT PATCHES {len(engine.resting_snow):,}/{args.object_snow_max:,} | "
             f"CAUGHT {engine.object_snow_caught:,} SHED {engine.object_snow_shed:,} | "
             f"CAPTURE {args.object_snow_capture:.0%} ADHESION {args.object_snow_adhesion:.2f}"),
        ]
    elif tab == "sky":
        colours = " → ".join(
            f"#{red:02X}{green:02X}{blue:02X}"
            for red, green, blue in args.sky_colours)
        stops = " → ".join(f"{stop:.0%}" for stop in args.sky_stops)
        page = [
            f" ◒ SKY {'ON' if args.sky else 'OFF'} | BLEND {args.sky_blend.upper()} | FULL-SCENE DISTANT LAYER",
            f" ◈ COLOURS {colours}",
            f" ↕ STOPS {stops}",
            (f" ☁ CLOUDS {'ON' if args.clouds else 'OFF'} ×{args.cloud_count} | "
             f"DEPTH {','.join(f'{depth:.2f}' for depth in args.cloud_depths)} | "
             f"SPEED {args.cloud_speed:.1f} PARALLAX {args.cloud_parallax:.1f}"),
        ]
    elif tab == "weather":
        kinds = {kind: sum(particle.kind == kind for particle in engine.flakes)
                 for kind in ("snow", "rain", "hail")}
        layers = {layer: sum(particle.layer == layer for particle in engine.flakes)
                  for layer in ("foreground", "background")}
        page = [
            (f" ☂ MODE {args.weather.upper()} | SNOW {kinds['snow']} RAIN {kinds['rain']} "
             f"HAIL {kinds['hail']} | PARTICLES {len(engine.flakes)}/{engine.max_flakes}"),
            (f" ◩ DEPTH FOREGROUND {layers['foreground']} / BACKGROUND {layers['background']} | "
             f"NEW FOREGROUND SHARE {args.weather_foreground_share:.0%}"),
            (f" ● HAIL {args.hail_size:.2f} VPX | BOUNCE {args.hail_bounce:.0%} | "
             f"RAIN ×{args.rain_speed:.2f}/{args.rain_length} VPX | MIX R{args.rain_share:.0%} H{args.hail_share:.0%}"),
            (f" ϟ LIGHTNING {'ON' if args.lightning else 'OFF'} | STRIKES {engine.lightning_count} | "
             f"INTERVAL {args.lightning_interval:.1f}s FLASH {args.lightning_flash:.2f}s"),
        ]
    elif tab == "trees":
        page = [
            f" ♣ TYPES {','.join(args.tree_types).upper()} | DENSITY {args.tree_density:.2f} MAX TREES {args.max_trees}",
            (f" Y PRIMARY/WHORLS {args.tree_branches} | RECURSION {args.tree_branch_levels} | "
             f"ANGLE {args.tree_branch_angle:.1f}° | CHILD LENGTH {args.tree_length_ratio:.2f}"),
            (f" ┃ TRUNK {args.tree_trunk_thickness:.2f} VPX | PRIMARY BRANCH "
             f"{args.tree_branch_thickness_ratio:.0%} | TAPER EXPONENT {args.tree_thickness_exponent:.2f} | "
             f"SEGMENT BUDGET {args.tree_segment_budget:,}"),
            (f" 〰 SWAY {args.tree_sway:.2f} | LIGHTS {args.lights:.2f} | "
             f"COLOUR Δ{args.conifer_colour_variation:.0f} | "
             f"OBJECT SNOW {'ON' if args.object_snow else 'OFF'} (SPARSE, MASS-SHED)"),
        ]
    elif tab == "animals":
        visible_rabbits = sum(r.state != "hidden" for r in engine.rabbits)
        states = ",".join(r.state for r in engine.rabbits if r.state != "hidden") or "hidden"
        depth_lanes = ",".join(f"{rabbit.depth:.2f}" for rabbit in engine.rabbits) or "none"
        page = [
            f" ♙ RABBITS {visible_rabbits}/{len(engine.rabbits)} | STATES {states} | DEPTH {depth_lanes}",
            f" ↔ SPEED {args.rabbit_speed:.1f} VPX/s | PERSPECTIVE SCALE/PARALLAX ON | REACTIONS {engine.rabbit_reactions}",
            (f" ✉ POSTMAN {engine.postman.state.upper()} | DELIVERIES {engine.postman_delivery_count} | "
             f"SPEED {args.postman_speed:.1f} | INTERVAL {args.postman_interval:.1f}s "
             f"×{args.postman_delivery_frequency:.1f} | FOOT SLUMPS {engine.postman_snow_collapses}"),
            (f" ✺ TUMBLEWEEDS {len(engine.tumbleweeds)} | BLOCKS {engine.tumbleweed_blocks} | "
             f"PRESSURE COLLAPSES {engine.tumbleweed_collapses} | CLIMB {args.tumbleweed_climb:.2f}")
        ]
    elif tab == "flights":
        event = current_sky_event(args, engine, getattr(engine, "elapsed", 0.0))
        current = "NONE" if event is None else f"{event[0].upper()} #{event[4]}"
        page = [
            (f" ✈ ROTATION {','.join(args.sky_events).upper() or 'NONE'} | CURRENT {current} | "
             f"AIRCRAFT {','.join(args.aeroplane_types).upper()}"),
            (f" → SPEED {args.flyby_speed:.1f} VPX/s | QUIET {args.flyby_interval:.1f}s | "
             f"EJECTIONS {engine.pilot_ejection_count} / ACTIVE {len(engine.parachutists)} | "
             f"HELI WAIT {args.helicopter_wait_min:.1f}–{args.helicopter_wait_max:.1f}s "
             f"DOWNWASH ×{args.helicopter_downwash:.1f}/W{args.helicopter_downwash_width:.1f} "
             f"CRATES {len(engine.supply_crates)}"),
            (f" ◆ SUPERMAN {args.superman_path.upper()} {args.superman_speed:.1f} VPX/s "
             f"{args.superman_frequency:.1f}/min | SANTA SCALE "
             f"{args.santa_scale_min:.2f}↔{args.santa_scale_max:.2f} | "
             f"TRAIL ×{args.santa_trail_length:.1f}, {args.santa_trail_seconds:.1f}s / "
             f"{len(engine.santa_trail)} SPARKS | GIFTS {args.santa_presents_min}–"
             f"{args.santa_presents_max}/DROP, {engine.present_delivery_count} DELIVERED"),
            (f" ⌁ UFO {','.join(args.ufo_types).upper()} | "
             f"BEAM {args.ufo_beam_style.upper()}/"
             f"{'ACTIVE' if engine.ufo_beam_active else 'HIDDEN'} | "
             f"CAPTURES {engine.ufo_abduction_count} PLASMA {len(engine.ufo_trail)} | "
             f"CRASHES {engine.aircraft_impact_count} "
             f"EXPLOSIONS {len(engine.ground_explosions)}"),
        ]
    else:
        cache = cached_tree_pixels.cache_info()
        postman_cache = cached_postman_pixels.cache_info()
        page = [
            (f" ◆ PROCESS CPU {cpu_percent:5.1f}% {graph_bar(cpu_percent, 100)} | "
             f"PIPELINE {engine.pipeline_ms:6.1f} + TTY {engine.present_ms:5.1f} ms / "
             f"{frame_budget:5.1f} {graph_bar(engine.pipeline_ms + engine.present_ms, frame_budget)}"),
            (f" ◆ MEMORY {memory} | GRID CELLS {stats['cells']:,} | ACTIVE {populated:,} | "
             f"OUTPUT {engine.frame_output_bytes / 1024.0:,.1f} KiB"),
            (f" ◆ LOAD: FLAKES {len(engine.flakes):,} TREES≤{args.max_trees} | "
             f"TREE CACHE {cache.hits:,}H/{cache.misses:,}M | POSTMAN {postman_cache.hits:,}H/{postman_cache.misses:,}M"),
            (f" ◆ ENCODER {'RUST NATIVE' if engine.native_analyser else 'PYTHON'} | "
             f"MISSED DEADLINES {engine.frame_overruns:,} MAX LAG {engine.maximum_frame_lag_ms:.1f} ms | "
             f"SEAM GUARDS {stats.get('seam_guard_cells', 0):,}"),
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
                f"WX {args.weather.upper()} | "
                f"MAX {engine.maximum_depth_fraction:5.1%} AVG {engine.average_depth_fraction:5.1%} | "
                f"FLAKES {len(engine.flakes):4d} | WIND {args.wind:+.1f} GUST {args.gust_strength:.1f} | "
                f"SCENE {codes} | {state} | "
                f"SHEDS {engine.shed_count} TOWERS {engine.tower_collapse_count} | F {frame}")
    elif columns >= 92:
        text = (f" SNOW {args.mode.upper()} | GRID {columns}x{total_rows} | 2CLR GND=FIXED | "
                f"{control} | WX {args.weather.upper()} | "
                f"DEPTH {engine.maximum_depth_fraction:.0%}/{engine.average_depth_fraction:.0%} | "
                f"FLK {len(engine.flakes)} W {args.wind:+.1f} G {args.gust_strength:.1f} | "
                f"{state} S{engine.shed_count} T{engine.tower_collapse_count} F{frame}")
    else:
        live_short = args.control_status if args.listen else "OFF"
        text = (f" SNOW {args.mode.upper()} {columns}x{total_rows} | 2CLR GND | "
                f"L:{live_short} WX:{args.weather[:1].upper()} | "
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
    rendered = render_surface(background, engine)
    if engine.native_analyser is not None:
        picture = encode_surface_native(rendered, codec, columns,
                                        scene_rows, engine.native_analyser, stats)
    else:
        picture = encode_surface(rendered, codec, columns, scene_rows, stats)
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
    descriptor = sys.stdin.fileno()
    ready, _, _ = select.select([descriptor], [], [], 0)
    if not ready:
        return None
    data = os.read(descriptor, 1)
    if data != b"\x1b":
        return data.decode("utf-8", errors="ignore")
    # Cursor/function keys begin with ESC too. Give the remaining bytes a tiny
    # arrival window so only a standalone Escape key exits the viewer.
    deadline = time.monotonic() + 0.025
    while len(data) < 12:
        timeout = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([descriptor], [], [], timeout)
        if not ready:
            break
        data += os.read(descriptor, 1)
        if len(data) >= 3 and 0x40 <= data[-1] <= 0x7E:
            break
    return data.decode("ascii", errors="ignore")


def viewer_quit_key(key):
    return key in ("q", "Q", "\x1b")


def settle_frame_deadline(deadline, now):
    """Return sleep, next schedule base and lag without catch-up bursts."""
    delay = deadline - now
    if delay > 0:
        return delay, deadline, 0.0
    return 0.0, now, -delay


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
            frame_started = time.perf_counter()
            key = poll_terminal_key()
            if key == "\t" and args.detailed_dashboard:
                engine.dashboard_tab = (engine.dashboard_tab + 1) % len(DASHBOARD_TABS)
            elif viewer_quit_key(key):
                break
            if args.frames and frame >= args.frames:
                break
            if args.duration and elapsed >= args.duration:
                break
            if listener:
                listener.poll(args, engine)
                args.control_status = listener.status
                if listener.restart_requested:
                    # Recreate simulation state in this process and terminal.
                    # The OS window, font, live position and dimensions remain
                    # untouched while restart-only options take effect.
                    columns, rows = terminal_size(args)
                    codec, scene_rows, engine, background = make_runtime(
                        args, columns, rows)
                    listener.restart_requested = False
                    elapsed = 0.0
                    frame = 0
                    deadline = time.monotonic()
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
            engine.pipeline_ms = (time.perf_counter() - frame_started) * 1000.0
            clear = "\x1b[2J" if resized else ""
            payload = "\x1b[?2026h" + clear + "\x1b[H" + output + "\x1b[?2026l"
            engine.frame_output_bytes = len(payload.encode("utf-8"))
            present_started = time.perf_counter()
            sys.stdout.write(payload)
            sys.stdout.flush()
            engine.present_ms = (time.perf_counter() - present_started) * 1000.0
            frame += 1
            elapsed += dt
            delay, deadline, lag = settle_frame_deadline(
                deadline, time.monotonic())
            if delay > 0:
                time.sleep(delay)
            else:
                # Never attempt to catch up a missed presentation deadline by
                # bursting several complete frames at the terminal. Those
                # frames cannot all be painted and appear as motion jumps.
                lag_ms = lag * 1000.0
                engine.frame_overruns += 1
                engine.maximum_frame_lag_ms = max(
                    engine.maximum_frame_lag_ms, lag_ms)
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


def rgb_colour(value):
    """Parse RRGGBB or #RRGGBB into one immutable RGB triplet."""
    cleaned = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", cleaned):
        raise argparse.ArgumentTypeError("colour must be six hexadecimal digits (RRGGBB)")
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def colour_list(value):
    colours = tuple(rgb_colour(item) for item in value.split(",") if item.strip())
    if not 2 <= len(colours) <= 8:
        raise argparse.ArgumentTypeError("sky colours need 2 to 8 comma-separated RRGGBB values")
    return colours


def fraction_list(value):
    try:
        fractions = tuple(float(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("sky stops must be comma-separated fractions") from error
    if (not 2 <= len(fractions) <= 8 or
            any(not 0.0 <= item <= 1.0 for item in fractions) or
            any(left >= right for left, right in zip(fractions, fractions[1:]))):
        raise argparse.ArgumentTypeError("sky stops need 2 to 8 increasing fractions in [0,1]")
    return fractions


def depth_list(value):
    try:
        depths = tuple(float(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "cloud depths must be comma-separated fractions") from error
    if (not 1 <= len(depths) <= 8 or
            any(not 0.05 <= item <= 1.0 for item in depths)):
        raise argparse.ArgumentTypeError(
            "cloud depths need 1 to 8 fractions in [0.05,1]")
    return depths


def window_position(value):
    if not re.fullmatch(r"(?:(?:screen|main|active):)?-?\d+,-?\d+", value):
        raise argparse.ArgumentTypeError("window position must look like 80,40 or active:80,40")
    return value


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
                         help="reserve six rows for keyboard-tabbed font, sky, weather, scenery and process telemetry")
    display.add_argument("--physics", choices=("none", "ground", "full"),
                         default="full",
                         help="none: legacy simple snow; ground: bank slumping and terrain bodies; full: also retain snow on scenery")
    display.add_argument("--native-encoder", choices=("auto", "off", "on"),
                         default="auto",
                         help="use the optional Rust cell analyser when built; ON requires it")

    window = parser.add_argument_group("launcher window reproduction")
    window.add_argument("--terminal-columns", type=int,
                        help="saved launcher width; the launcher consumes this before Python")
    window.add_argument("--terminal-rows", type=int,
                        help="saved launcher height; the launcher consumes this before Python")
    window.add_argument("--font-size", type=float,
                        help="saved terminal font size in points; consumed by the launcher")
    window.add_argument("--window-position", type=window_position,
                        help="saved initial window position X,Y or active:X,Y; consumed by the launcher")

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
                      help="relative weights corresponding to --flake-sizes; omitted values use the built-in profile")
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

    sky = parser.add_argument_group("sky and atmosphere")
    sky.add_argument("--sky", action=argparse.BooleanOptionalAction, default=True,
                     help="paint a full-scene gradient behind distant flights and foreground scenery")
    sky.add_argument("--sky-colours", type=colour_list,
                     default=colour_list("07152F,315A82,B9D8E8"),
                     help="top-to-bottom comma list of 2 to 8 hexadecimal RGB colours")
    sky.add_argument("--sky-stops", type=fraction_list,
                     default=fraction_list("0,0.58,1"),
                     help="increasing 0..1 vertical positions corresponding to --sky-colours")
    sky.add_argument("--sky-blend", choices=("linear", "smooth", "cosine"),
                     default="smooth",
                     help="method used to merge each adjacent pair of gradient colours")

    clouds = parser.add_argument_group("clouds and parallax")
    clouds.add_argument("--clouds", action=argparse.BooleanOptionalAction,
                        default=False,
                        help="move layered procedural clouds through the distant sky")
    clouds.add_argument("--cloud-count", type=int, default=7,
                        help="number of continuously wrapping cloud bodies")
    clouds.add_argument("--cloud-speed", type=float, default=4.0,
                        help="base cloud movement in virtual pixels per second")
    clouds.add_argument("--cloud-depths", type=depth_list,
                        default=depth_list("0.22,0.48,0.78"),
                        help="comma-separated perspective lanes from far 0.05 to near 1")
    clouds.add_argument("--cloud-parallax", type=float, default=1.0,
                        help="depth-to-speed multiplier; 0 makes every lane move similarly")
    clouds.add_argument("--cloud-colours", type=colour_list,
                        default=colour_list("A9C9DD,DCECF2,FFF5E1"),
                        help="comma-separated RRGGBB cloud colours cycled across lanes")

    weather = parser.add_argument_group("rain hail and lightning")
    weather.add_argument("--weather", choices=("none", "snow", "rain", "hail", "mixed", "storm"),
                         default="snow",
                         help="precipitation family; none disables precipitation and lightning")
    weather.add_argument("--weather-foreground-share", type=float, default=0.45,
                         help="fraction of new precipitation assigned in front of scenery")
    weather.add_argument("--rain-share", type=float, default=0.35,
                         help="rain fraction in mixed precipitation")
    weather.add_argument("--hail-share", type=float, default=0.10,
                         help="hail fraction in mixed/storm precipitation")
    weather.add_argument("--rain-speed", type=float, default=2.6,
                         help="rain fall-speed multiplier")
    weather.add_argument("--rain-length", type=int, default=5,
                         help="rain streak length in virtual pixels")
    weather.add_argument("--rain-colour", type=rgb_colour, default=rgb_colour("78C8F0"),
                         help="rain RGB colour as six hexadecimal digits")
    weather.add_argument("--hail-size", type=float, default=1.4,
                         help="hailstone radius in virtual pixels")
    weather.add_argument("--hail-bounce", type=float, default=0.55,
                         help="probability that hail bounces on the ground")
    weather.add_argument("--hail-colour", type=rgb_colour, default=rgb_colour("DDF7FF"),
                         help="hail RGB colour as six hexadecimal digits")
    weather.add_argument("--lightning", action=argparse.BooleanOptionalAction, default=False,
                         help="enable occasional branched lightning and a sky flash")
    weather.add_argument("--lightning-interval", type=float, default=18.0,
                         help="average seconds between lightning strikes")
    weather.add_argument("--lightning-flash", type=float, default=0.34,
                         help="seconds that each lightning flash remains visible")
    weather.add_argument("--lightning-branches", type=int, default=4,
                         help="side branches drawn from the main lightning bolt")

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
    banks.add_argument("--shed-threshold", type=float, default=0.82,
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
    banks.add_argument("--snow-fallaway-threshold", type=float, default=0.50,
                       help="local depth fraction that starts a mass/countdown fall-away")
    banks.add_argument("--snow-fallaway-min-seconds", type=float, default=8.0,
                       help="minimum countdown after local snow reaches the trigger height")
    banks.add_argument("--snow-fallaway-max-seconds", type=float, default=22.0,
                       help="maximum deterministic countdown before local snow falls away")
    banks.add_argument("--snow-fallaway-width", type=float, default=0.06,
                       help="display-width fraction removed around a triggered area")

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
    scenery.add_argument("--tree-trunk-thickness", type=float, default=4.2,
                         help="base procedural trunk thickness in virtual pixels")
    scenery.add_argument("--tree-branch-thickness-ratio", type=float, default=0.42,
                         help="primary branch thickness as a fraction of main trunk thickness")
    scenery.add_argument("--conifer-colour-variation", type=float, default=28.0,
                         help="maximum seeded pine/fir/spruce colour separation in RGB levels")
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
    scenery.add_argument("--cabin-depth-share", type=float, default=0.34,
                         help="fraction of cabins placed in a smaller elevated distance lane")
    scenery.add_argument("--cabin-depth-scale", type=float, default=0.56,
                         help="perspective scale applied to distant cabins")
    scenery.add_argument("--cabin-path-style",
                         choices=("auto", "diagonal", "curve", "curly"),
                         default="auto",
                         help="shape of the shared postman/dirt approach paths")
    scenery.add_argument("--cabin-path-curl", type=float, default=0.72,
                         help="lateral amplitude multiplier for curly paths")
    scenery.add_argument("--horizon-structure",
                         choices=("none", "dirt", "huts", "both"),
                         default="none",
                         help="add sparse earth and/or receding huts behind foreground scenery")
    scenery.add_argument("--horizon-dirt-density", type=float, default=0.28,
                         help="fraction of background horizon samples painted as earth")
    scenery.add_argument("--horizon-randomness", type=float, default=0.55,
                         help="horizontal/vertical disorder in distant earth and huts")
    scenery.add_argument("--horizon-height", type=float, default=0.48,
                         help="vertical scene fraction at the artificial horizon")
    scenery.add_argument("--horizon-hut-density", type=float, default=0.18,
                         help="small distant huts per nominal background area")
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
    events.add_argument("--postman", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="occasionally send a walking postman to a cabin door")
    events.add_argument("--postman-interval", type=float, default=55.0,
                        help="approximate quiet seconds between postal visits")
    events.add_argument("--postman-speed", type=float, default=10.0,
                        help="postman walking speed in virtual pixels per second")
    events.add_argument("--postman-stop-seconds", type=float, default=4.0,
                        help="seconds spent waiting at the door after posting")
    events.add_argument("--postman-delivery-frequency", type=float, default=1.0,
                        help="visit-frequency factor across every cabin; 0 disables deliveries")
    events.add_argument("--sky-events", type=sky_event_list,
                        default=sky_event_list("auto"),
                        help="none, auto/all, or comma list: aeroplane,helicopter,airwolf,kite,ufo,santa,superman")
    events.add_argument("--flyby-interval", type=float, default=48.0,
                        help="quiet seconds between occasional sky crossings")
    events.add_argument("--flyby-speed", type=float, default=32.0,
                        help="sky-event horizontal virtual pixels per second")
    events.add_argument("--superman-path", choices=("straight", "curve", "arc"),
                        default="arc",
                        help="flight geometry used by each Superman crossing")
    events.add_argument("--superman-frequency", type=float, default=1.0,
                        help="Superman appearances per minute within the event rotation")
    events.add_argument("--superman-speed", type=float, default=46.0,
                        help="Superman horizontal virtual pixels per second")
    events.add_argument("--helicopter-hover-seconds", type=float, default=3.0,
                        help="seconds spent hovering before descent and before departure")
    events.add_argument("--helicopter-wait-min", type=float, default=4.0,
                        help="minimum seconds landed before leaving the supply crate")
    events.add_argument("--helicopter-wait-max", type=float, default=8.0,
                        help="maximum seconds landed before leaving the supply crate")
    events.add_argument("--helicopter-downwash", type=float, default=1.0,
                        help="rotor coupling into precipitation and loose ground snow")
    events.add_argument("--helicopter-downwash-width", type=float, default=1.0,
                        help="horizontal/radial multiplier for rotor disturbance")
    events.add_argument("--aeroplane-types", type=aeroplane_type_list,
                        default=aeroplane_type_list("all"),
                        help="auto/all or comma list: commuter,airliner")
    events.add_argument("--pilot-ejection", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="allow occasional distant pilots to eject and parachute down")
    events.add_argument("--ejection-chance", type=float, default=0.18,
                        help="repeatable chance [0,1] of ejection during each aeroplane pass")
    events.add_argument("--parachute-fall-speed", type=float, default=5.0,
                        help="opened-parachute descent speed in virtual pixels per second")
    events.add_argument("--aircraft-crash", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="turn an ejected aircraft into a rotating, burning ground impact")
    events.add_argument("--aircraft-crash-depth",
                        choices=("auto", "away", "toward"), default="auto",
                        help="whether the disabled aircraft recedes or grows while descending")
    events.add_argument("--aircraft-crash-descent", type=float, default=22.0,
                        help="base vertical descent speed after ejection")
    events.add_argument("--aircraft-crash-arc", type=float, default=0.55,
                        help="initial upward arc before the steep descent, 0 to 2")
    events.add_argument("--aircraft-crash-spin", type=float, default=2.4,
                        help="aircraft rotations per second while falling")
    events.add_argument("--aircraft-crash-smoke", type=float, default=1.0,
                        help="fire/smoke trail density multiplier")
    events.add_argument("--explosion-types", type=explosion_type_list,
                        default=explosion_type_list("all"),
                        help="auto/all or comma list: fiery,nuclear")
    events.add_argument("--explosion-size", type=float, default=1.0,
                        help="impact explosion linear scale")
    events.add_argument("--explosion-seconds", type=float, default=12.0,
                        help="lifetime of fiery or mushroom-cloud impact animation")
    events.add_argument("--ufo-beam-style",
                        choices=("spiral", "rings", "lattice", "stargate"),
                        default="spiral",
                        help="transporter beam animation design")
    events.add_argument("--santa-scale-max", "--santa-scale",
                        dest="santa_scale_max", type=float, default=0.50,
                        help="nearest Santa formation scale; --santa-scale remains an alias")
    events.add_argument("--santa-scale-min", type=float, default=0.02,
                        help="furthest Santa formation scale at entry and exit")
    events.add_argument("--santa-arc-height", type=float, default=0.16,
                        help="Santa arc rise as a fraction of scene height")
    events.add_argument("--santa-trail-seconds", type=float, default=5.6,
                        help="seconds before each Santa comet-trail spark fades")
    events.add_argument("--santa-trail-length", type=float, default=3.0,
                        help="spatial trail multiplier; 3 is three times the original length")
    events.add_argument("--santa-presents", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="drop simultaneous parcels vertically into each crossed chimney")
    events.add_argument("--santa-presents-min", type=int, default=2,
                        help="minimum simultaneous parcels dropped at each chimney")
    events.add_argument("--santa-presents-max", type=int, default=5,
                        help="maximum simultaneous parcels dropped at each chimney")
    events.add_argument("--present-fall-speed", type=float, default=12.0,
                        help="initial parcel fall speed in virtual pixels per second")
    events.add_argument("--ufo-abduction", action=argparse.BooleanOptionalAction,
                        default=False,
                        help="allow a hovering UFO to raise and shrink one rabbit through a temporary beam")
    events.add_argument("--ufo-hover-seconds", type=float, default=6.0,
                        help="seconds a UFO remains stationary while abducting a rabbit")
    events.add_argument("--ufo-types", type=ufo_type_list,
                        default=ufo_type_list("all"),
                        help="auto/all or comma list: saucer,orb,delta")
    events.add_argument("--ufo-trail-seconds", type=float, default=2.6,
                        help="seconds before each UFO plasma spark fades")
    events.add_argument("--ufo-trail-length", type=float, default=1.6,
                        help="spatial and emission multiplier for the UFO plasma trail")
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
        "  --window-position X,Y  initial macOS WezTerm pixel position",
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
        "  --sky-events aeroplane,helicopter,airwolf,kite,ufo,santa --flyby-interval 12 --flyby-speed 40",
        paint("amber", "  Twilight sky   ") +
        "  --sky-colours 07152F,315A82,B9D8E8 --sky-stops 0,.58,1 --sky-blend smooth",
        paint("amber", "  Rain shower    ") +
        "  --weather rain --weather-foreground-share .65 --snow-rate 90 --rain-speed 3 --rain-length 7",
        paint("amber", "  Wintry mix     ") +
        "  --weather mixed --rain-share .35 --hail-share .15 --hail-bounce .6",
        paint("amber", "  Thunderstorm   ") +
        "  --weather storm --lightning --lightning-interval 8 --lightning-branches 6",
        paint("amber", "  Clear sky      ") +
        "  --weather none    (sky, scenery, animals and flights remain active)",
        paint("amber", "  Santa arc      ") +
        "  --sky-events santa --santa-scale .5 --santa-arc-height .16 --santa-trail-length 3 --santa-trail-seconds 5.6",
        paint("amber", "  UFO capture    ") +
        "  --sky-events ufo --ufo-abduction --ufo-hover-seconds 6 --rabbit-count 2",
        paint("amber", "  Plough test    ") +
        "  --plough-interval 5 --plough-speed 60 --plough-clear-to .02",
        paint("amber", "  Font telemetry ") +
        "  --detailed-dashboard",
        paint("amber", "  Fast buildup   ") +
        "  --initial-snow 0.40 --accumulation 5 --shed-threshold 0.50",
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
        "  With --detailed-dashboard, press Tab for FONT/SNOW/SKY/WEATHER/TREES/ANIMALS/FLIGHTS/PROCESS.",
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
    if args.size_weights is None:
        args.size_weights = tuple(DEFAULT_FLAKE_WEIGHTS[name]
                                  for name in args.flake_sizes)
    if len(args.flake_sizes) != len(args.size_weights):
        parser.error("--flake-sizes and --size-weights must contain the same number of values")
    positive = (("fps", args.fps), ("fall-speed", args.fall_speed),
                ("gust-period", args.gust_period), ("shed-rate", args.shed_rate),
                ("tower-collapse-rate", args.tower_collapse_rate),
                ("control-poll", args.control_poll),
                ("rabbit-interval", args.rabbit_interval),
                ("rabbit-speed", args.rabbit_speed),
                ("postman-interval", args.postman_interval),
                ("postman-speed", args.postman_speed),
                ("postman-stop-seconds", args.postman_stop_seconds),
                ("flyby-interval", args.flyby_interval),
                ("flyby-speed", args.flyby_speed),
                ("superman-frequency", args.superman_frequency),
                ("superman-speed", args.superman_speed),
                ("helicopter-hover-seconds", args.helicopter_hover_seconds),
                ("parachute-fall-speed", args.parachute_fall_speed),
                ("aircraft-crash-descent", args.aircraft_crash_descent),
                ("explosion-seconds", args.explosion_seconds),
                ("rain-speed", args.rain_speed),
                ("lightning-interval", args.lightning_interval),
                ("ufo-hover-seconds", args.ufo_hover_seconds),
                ("present-fall-speed", args.present_fall_speed),
                ("plough-interval", args.plough_interval),
                ("plough-speed", args.plough_speed))
    if any(value <= 0 for _, value in positive):
        parser.error("timing, polling, movement, shed and collapse rates must be positive")
    nonnegative = (
        args.duration, args.frames, args.preload_seconds, args.drift, args.wobble,
        args.gust_strength, args.accumulation, args.tree_density, args.tree_sway,
        args.lights, args.conifer_colour_variation, args.ambient_speed, args.max_cabins,
        args.tower_age, args.tower_age_jitter, args.rabbit_count,
        args.snow_repose_slope, args.snow_relaxation, args.object_snow_max,
        args.object_snow_hold, args.object_snow_hold_jitter,
        args.object_snow_adhesion,
        args.tumbleweed_climb, args.tumbleweed_collapse_pressure,
        args.cloud_count, args.cloud_speed, args.cloud_parallax,
        args.postman_delivery_frequency,
        args.santa_scale_min, args.santa_scale_max,
        args.santa_arc_height, args.santa_trail_seconds,
        args.santa_trail_length,
        args.helicopter_wait_min, args.helicopter_wait_max,
        args.helicopter_downwash, args.helicopter_downwash_width,
        args.cabin_path_curl,
        args.aircraft_crash_arc, args.aircraft_crash_spin,
        args.aircraft_crash_smoke, args.explosion_size,
        args.horizon_dirt_density, args.horizon_randomness,
        args.horizon_hut_density,
        args.snow_fallaway_min_seconds, args.snow_fallaway_max_seconds,
        args.ufo_trail_seconds, args.ufo_trail_length,
        args.lightning_flash,
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
    if args.cloud_count < 0:
        parser.error("cloud-count cannot be negative")
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
    if not 0.1 <= args.tree_branch_thickness_ratio <= 1:
        parser.error("tree-branch-thickness-ratio must be in [0.1, 1]")
    if args.conifer_colour_variation > 100:
        parser.error("conifer-colour-variation must be in [0, 100]")
    if not 1.2 <= args.tree_thickness_exponent <= 4:
        parser.error("tree-thickness-exponent must be in [1.2, 4]")
    if not 0 <= args.tree_segment_budget <= 100000:
        parser.error("tree-segment-budget must be in [0, 100000]")
    if args.rabbit_count < 0:
        parser.error("rabbit-count cannot be negative")
    if not 0 <= args.ejection_chance <= 1:
        parser.error("ejection-chance must be in [0, 1]")
    if args.cabin_scale <= 0:
        parser.error("cabin-scale must be positive")
    if not 0.01 <= args.santa_scale_min <= 2:
        parser.error("santa-scale-min must be in [0.01, 2]")
    if not 0.01 <= args.santa_scale_max <= 2:
        parser.error("santa-scale-max must be in [0.01, 2]")
    if args.santa_scale_min > args.santa_scale_max:
        parser.error("santa-scale-min cannot exceed santa-scale-max")
    if args.santa_presents_min < 1 or args.santa_presents_max < 1:
        parser.error("santa present counts must be at least 1")
    if args.santa_presents_min > args.santa_presents_max:
        parser.error("santa-presents-min cannot exceed santa-presents-max")
    if args.helicopter_wait_min > args.helicopter_wait_max:
        parser.error("helicopter-wait-min cannot exceed helicopter-wait-max")
    if args.helicopter_downwash > 4:
        parser.error("helicopter-downwash must be in [0, 4]")
    if not 0.25 <= args.helicopter_downwash_width <= 4:
        parser.error("helicopter-downwash-width must be in [0.25, 4]")
    if not 0 <= args.cabin_path_curl <= 2:
        parser.error("cabin-path-curl must be in [0, 2]")
    if not 0 <= args.aircraft_crash_arc <= 2:
        parser.error("aircraft-crash-arc must be in [0, 2]")
    if not 0 <= args.aircraft_crash_spin <= 12:
        parser.error("aircraft-crash-spin must be in [0, 12]")
    if not 0 <= args.aircraft_crash_smoke <= 6:
        parser.error("aircraft-crash-smoke must be in [0, 6]")
    if not 0.1 <= args.explosion_size <= 8:
        parser.error("explosion-size must be in [0.1, 8]")
    if not 0 <= args.horizon_dirt_density <= 1:
        parser.error("horizon-dirt-density must be in [0, 1]")
    if not 0 <= args.horizon_randomness <= 1:
        parser.error("horizon-randomness must be in [0, 1]")
    if not 0 <= args.horizon_hut_density <= 2:
        parser.error("horizon-hut-density must be in [0, 2]")
    if not 0.15 <= args.horizon_height <= 0.85:
        parser.error("horizon-height must be in [0.15, 0.85]")
    if not 0 <= args.snow_fallaway_threshold <= 1:
        parser.error("snow-fallaway-threshold must be in [0, 1]")
    if args.snow_fallaway_min_seconds > args.snow_fallaway_max_seconds:
        parser.error("snow-fallaway-min-seconds cannot exceed its maximum")
    if not 0.01 <= args.snow_fallaway_width <= 0.5:
        parser.error("snow-fallaway-width must be in [0.01, 0.5]")
    if not 0 <= args.santa_arc_height <= 0.5:
        parser.error("santa-arc-height must be in [0, 0.5]")
    if not 1 <= args.rain_length <= 40:
        parser.error("rain-length must be in [1, 40]")
    if not 0.5 <= args.hail_size <= 6:
        parser.error("hail-size must be in [0.5, 6]")
    if not 0 <= args.rain_share <= 1 or not 0 <= args.hail_share <= 1:
        parser.error("rain-share and hail-share must be in [0, 1]")
    if not 0 <= args.weather_foreground_share <= 1:
        parser.error("weather-foreground-share must be in [0, 1]")
    if args.rain_share + args.hail_share > 1:
        parser.error("rain-share plus hail-share cannot exceed 1")
    if not 0 <= args.hail_bounce <= 1:
        parser.error("hail-bounce must be in [0, 1]")
    if not 0 <= args.lightning_branches <= 16:
        parser.error("lightning-branches must be in [0, 16]")
    if args.terminal_columns is not None and args.terminal_columns < 24:
        parser.error("terminal-columns must be at least 24")
    if args.terminal_rows is not None and args.terminal_rows < 8:
        parser.error("terminal-rows must be at least 8")
    if (args.terminal_columns is None) != (args.terminal_rows is None):
        parser.error("terminal-columns and terminal-rows must be supplied together")
    if args.font_size is not None and args.font_size <= 0:
        parser.error("font-size must be positive")
    if len(args.sky_colours) != len(args.sky_stops):
        parser.error("sky-colours and sky-stops must contain the same number of values")
    if args.sky_stops[0] != 0.0 or args.sky_stops[-1] != 1.0:
        parser.error("sky-stops must begin at 0 and end at 1")
    if not 0 <= args.cabin_size_variation <= 0.75:
        parser.error("cabin-size-variation must be in [0, 0.75]")
    if not 0 <= args.cabin_depth_share <= 1:
        parser.error("cabin-depth-share must be in [0, 1]")
    if not 0.25 <= args.cabin_depth_scale <= 0.95:
        parser.error("cabin-depth-scale must be in [0.25, 0.95]")
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
