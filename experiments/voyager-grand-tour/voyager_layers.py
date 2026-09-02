#!/usr/bin/env python3
"""Depth-ordered two-colour terminal compositor for the Voyager demo.

The original Voyager renderer flattened the whole scene into one RGB raster
before terminal-cell encoding.  A filled planet and a sparse spacecraft edge
could therefore become one fully occupied glyph in one selected foreground
colour.  This module keeps semantic scene layers separate until the final
terminal-cell encode.  The nearest visible layer becomes the glyph foreground;
the visible layer immediately behind it may become the ANSI cell background.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from voyager_core import BRAILLE_BITS, PUA4_BITS, pua4_codepoint


BACKGROUND_VALID = np.uint8(1)


@dataclass(frozen=True)
class CellFrame:
    """One encoded terminal frame with explicit foreground/background planes."""

    masks: np.ndarray
    foreground: np.ndarray
    background: np.ndarray
    flags: np.ndarray


def _blank(height: int, width: int) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _representative_colour(colours: np.ndarray) -> np.ndarray:
    """Return the RGB888 mean, minimizing squared reconstruction error."""
    if not len(colours):
        return np.zeros(3, dtype=np.uint8)
    return np.rint(np.asarray(colours, dtype=np.float64).mean(axis=0)).astype(
        np.uint8
    )


def encode_layers(layers, mode: int, columns: int, rows: int) -> CellFrame:
    """Encode ordered ``(priority, RGB)`` layers into two-colour cells.

    Higher numeric priority is nearer.  RGB (0, 0, 0) is transparent.  A set
    glyph bit selects the nearest layer's representative foreground colour; an
    unset bit selects an optional representative background colour.  The
    background is enabled only when it lowers measured RGB reconstruction
    error, which avoids flooding cells whose rear content is merely sparse.
    """
    if mode not in (2, 4):
        raise ValueError("mode must be 2 or 4")
    width, height = columns * mode, rows * 4
    normalized = []
    for priority, rgb in layers:
        array = np.asarray(rgb, dtype=np.uint8)
        if array.shape != (height, width, 3):
            raise ValueError(
                f"layer priority {priority} has shape {array.shape}; "
                f"expected {(height, width, 3)}"
            )
        normalized.append((int(priority), array))
    if not normalized:
        raise ValueError("at least one layer is required")
    normalized.sort(key=lambda item: item[0])

    bits = BRAILLE_BITS if mode == 2 else PUA4_BITS
    weights = np.left_shift(np.uint32(1), bits.astype(np.uint32)).astype(
        np.uint16
    )
    masks = np.zeros((rows, columns), dtype=np.uint16)
    foreground = np.zeros((rows, columns, 3), dtype=np.uint8)
    background = np.zeros((rows, columns, 3), dtype=np.uint8)
    flags = np.zeros((rows, columns), dtype=np.uint8)
    layer_blocks = [
        (
            priority,
            rgb.reshape(rows, 4, columns, mode, 3).transpose(0, 2, 1, 3, 4),
        )
        for priority, rgb in normalized
    ]

    for row in range(rows):
        for column in range(columns):
            visible = []
            for priority, blocks in layer_blocks:
                pixels = blocks[row, column]
                occupied = np.any(pixels != 0, axis=2)
                if np.any(occupied):
                    visible.append((priority, pixels, occupied))
            if not visible:
                continue

            _, front_pixels, front_occupied = visible[-1]
            front_colour = _representative_colour(front_pixels[front_occupied])
            masks[row, column] = np.uint16(
                np.sum(front_occupied * weights, dtype=np.uint32)
            )
            foreground[row, column] = front_colour

            if len(visible) < 2 or np.all(front_occupied):
                continue

            rear_composite = np.zeros_like(front_pixels)
            for _, rear_pixels, rear_occupied in visible[:-1]:
                rear_composite[rear_occupied] = rear_pixels[rear_occupied]
            rear_visible = np.any(rear_composite != 0, axis=2) & ~front_occupied
            if not np.any(rear_visible):
                continue

            rear_colour = _representative_colour(rear_composite[rear_visible])
            exact = rear_composite.astype(np.int32)
            exact[front_occupied] = front_pixels[front_occupied]
            without_background = np.zeros_like(exact)
            without_background[front_occupied] = front_colour
            with_background = np.empty_like(exact)
            with_background[:] = rear_colour
            with_background[front_occupied] = front_colour
            error_without = np.square(
                exact - without_background, dtype=np.int64
            ).sum()
            error_with = np.square(exact - with_background, dtype=np.int64).sum()
            if error_with < error_without:
                background[row, column] = rear_colour
                flags[row, column] |= BACKGROUND_VALID

    if mode == 2:
        masks = masks.astype(np.uint8)
    return CellFrame(masks, foreground, background, flags)


def expand_frame(frame: CellFrame, mode: int, default_background=(0, 0, 0)):
    """Expand an encoded cell frame back to virtual pixels for evidence tests."""
    rows, columns = frame.masks.shape
    bits = BRAILLE_BITS if mode == 2 else PUA4_BITS
    output = np.empty((rows * 4, columns * mode, 3), dtype=np.uint8)
    default = np.asarray(default_background, dtype=np.uint8)
    for local_y in range(4):
        for local_x in range(mode):
            bit = int(bits[local_y, local_x])
            selected = (frame.masks & (1 << bit)) != 0
            rear = np.where(
                (frame.flags & BACKGROUND_VALID)[..., None] != 0,
                frame.background,
                default,
            )
            output[local_y::4, local_x::mode] = np.where(
                selected[..., None], frame.foreground, rear
            )
    return output


def terminal_picture_v2(frame: CellFrame, mode: int) -> str:
    """Emit true-colour ANSI text using both colour planes and the real glyph."""
    rows, columns = frame.masks.shape
    lines = []
    active_foreground = None
    active_background = None
    for row in range(rows):
        pieces = []
        for column in range(columns):
            mask = int(frame.masks[row, column])
            foreground = tuple(
                int(value) for value in frame.foreground[row, column]
            )
            background_valid = bool(
                frame.flags[row, column] & BACKGROUND_VALID
            )
            cell_background = (
                tuple(int(value) for value in frame.background[row, column])
                if background_valid
                else None
            )

            if mask:
                if foreground != active_foreground:
                    pieces.append("\x1b[38;2;%d;%d;%dm" % foreground)
                    active_foreground = foreground
            elif active_foreground is not None:
                pieces.append("\x1b[39m")
                active_foreground = None

            if cell_background != active_background:
                if cell_background is None:
                    pieces.append("\x1b[49m")
                else:
                    pieces.append("\x1b[48;2;%d;%d;%dm" % cell_background)
                active_background = cell_background

            if mask:
                codepoint = 0x2800 + mask if mode == 2 else pua4_codepoint(mask)
                pieces.append(chr(codepoint))
            else:
                pieces.append(" ")
        pieces.append("\x1b[0m")
        lines.append("".join(pieces))
        active_foreground = None
        active_background = None
    return "\n".join(lines)


def draw_occluded_ring(scene, rear, near, mode, centre, ring_radii, rotation,
                       planet_radii, rear_colour, near_colour, samples=1800):
    """Classify every ring sample geometrically as behind/in front of planet."""
    height, width, _ = rear.shape
    pixel_aspect = 2.0 / mode
    major, minor = map(float, ring_radii)
    equatorial, polar = map(float, planet_radii)
    cosine, sine = math.cos(rotation), math.sin(rotation)
    inclination_cosine = math.sqrt(max(0.0, 1.0 - (minor / major) ** 2))
    previous = None

    for angle in np.linspace(0.0, math.tau, samples, endpoint=True):
        local_x = major * math.cos(angle)
        local_y = minor * math.sin(angle)
        physical_x = local_x * cosine - local_y * sine
        physical_y = local_x * sine + local_y * cosine
        point = (
            int(round(centre[0] + physical_x / pixel_aspect)),
            int(round(centre[1] + physical_y)),
        )
        current = (
            point[0],
            point[1],
            major * math.sin(angle) * inclination_cosine,
        )
        if previous is not None:
            x0, y0, z0 = previous
            x1, y1, z1 = current
            steps = max(1, abs(x1 - x0), abs(y1 - y0))
            for step in range(steps + 1):
                fraction = step / steps
                x = int(round(x0 + (x1 - x0) * fraction))
                y = int(round(y0 + (y1 - y0) * fraction))
                if not (0 <= x < width and 0 <= y < height):
                    continue
                z_ring = z0 + (z1 - z0) * fraction
                dx = (x - centre[0]) * pixel_aspect
                dy = y - centre[1]
                q = (dx / equatorial) ** 2 + (dy / polar) ** 2
                if q <= 1.0:
                    z_planet = equatorial * math.sqrt(max(0.0, 1.0 - q))
                    is_near = z_ring > z_planet
                else:
                    is_near = z_ring > 0.0
                (near if is_near else rear)[y, x] = (
                    near_colour if is_near else rear_colour
                )
        previous = current


def render_encounter_layers(scene, mode, elapsed, height, width):
    """Render encounter objects into explicit back-to-front depth layers."""
    index = int((elapsed % scene.MISSION_SECONDS) // scene.SEGMENT_SECONDS)
    local = elapsed % scene.SEGMENT_SECONDS
    encounter = scene.ENCOUNTERS[index]
    fade = scene.smoothstep(
        min(local / 0.75, (scene.SEGMENT_SECONDS - local) / 0.75)
    )
    shot = scene.grand_tour_shot(elapsed)
    physical_width = width * (2.0 / mode)
    base_radius = min(height * 0.31, physical_width * 0.23) * shot["planet_scale"]
    centre = (
        width * shot["planet_centre"][0],
        height * shot["planet_centre"][1],
    )
    moon_centre = (
        centre[0] - width * (0.18 + 0.035 * math.sin(math.pi * shot["u"])),
        centre[1] - height * (0.24 + 0.04 * math.cos(math.tau * shot["u"])),
    )
    layers = []

    if encounter.planet is scene.JUPITER:
        planet, moon = _blank(height, width), _blank(height, width)
        scene.draw_planet(
            planet, mode, scene.JUPITER, centre, base_radius, elapsed, fade
        )
        if index == 0:
            scene.draw_moon(
                moon, mode, moon_centre, base_radius * 0.095,
                (218, 180, 104), 501, 0.8
            )
        else:
            scene.draw_moon(
                moon, mode, moon_centre, base_radius * 0.14,
                (142, 132, 121), 502, 0.7
            )
        layers.extend(((20, planet), (26, moon)))
    elif encounter.planet is scene.SATURN:
        radius = base_radius * 0.72
        rotation = math.radians(-13)
        rear, planet = _blank(height, width), _blank(height, width)
        near, moon = _blank(height, width), _blank(height, width)
        draw_occluded_ring(
            scene, rear, near, mode, centre,
            (radius * 2.26, radius * 0.55), rotation,
            (radius, radius * scene.SATURN.flattening_ratio),
            (92, 79, 61), (222, 198, 145)
        )
        draw_occluded_ring(
            scene, rear, near, mode, centre,
            (radius * 1.63, radius * 0.40), rotation,
            (radius, radius * scene.SATURN.flattening_ratio),
            (188, 162, 112), (154, 131, 92)
        )
        scene.draw_planet(planet, mode, scene.SATURN, centre, radius, elapsed, fade)
        scene.draw_moon(moon, mode, moon_centre, radius * 0.13,
                        (194, 151, 94), 601)
        layers.extend(((15, rear), (20, planet), (24, near), (26, moon)))
    elif encounter.planet is scene.URANUS:
        radius = base_radius * 0.87
        rear, planet = _blank(height, width), _blank(height, width)
        near, moon = _blank(height, width), _blank(height, width)
        draw_occluded_ring(
            scene, rear, near, mode, centre,
            (radius * 1.76, radius * 0.22), math.radians(82),
            (radius, radius * scene.URANUS.flattening_ratio),
            (92, 122, 124), (151, 194, 197)
        )
        scene.draw_planet(planet, mode, scene.URANUS, centre, radius, elapsed, fade)
        scene.draw_moon(moon, mode, moon_centre, radius * 0.08,
                        (169, 165, 156), 701)
        layers.extend(((15, rear), (20, planet), (24, near), (26, moon)))
    elif encounter.planet is scene.NEPTUNE:
        radius = base_radius * 0.88
        planet, rear = _blank(height, width), _blank(height, width)
        near, moon = _blank(height, width), _blank(height, width)
        scene.draw_planet(planet, mode, scene.NEPTUNE, centre, radius, elapsed, fade)
        draw_occluded_ring(
            scene, rear, near, mode, centre,
            (radius * 1.64, radius * 0.16), math.radians(-9),
            (radius, radius * scene.NEPTUNE.flattening_ratio),
            (28, 52, 83), (72, 121, 184)
        )
        scene.draw_moon(moon, mode, moon_centre, radius * 0.11,
                        (177, 183, 173), 801)
        layers.extend(((15, rear), (20, planet), (24, near), (26, moon)))
    else:
        pale_dot = _blank(height, width)
        for offset in range(-height, height):
            x = int(centre[0] + offset * (mode / 8))
            y = int(centre[1] + offset)
            if 0 <= x < width and 0 <= y < height:
                pale_dot[y, x] = (45, 33, 56)
        x, y = int(centre[0]), int(centre[1])
        if 0 <= x < width and 0 <= y < height:
            pale_dot[y, x] = (114, 157, 244)
        layers.append((20, pale_dot))
    return encounter, index, layers


def render_layered_frame(scene, mesh, mode, columns, graphic_rows, elapsed,
                         programme, style, hidden_lines, depth_scale):
    """Render distinct semantic layers and encode a two-colour cell frame."""
    started = time.perf_counter()
    width, height = columns * mode, graphic_rows * 4
    stars = _blank(height, width)
    spacecraft = _blank(height, width)
    scene.add_stars(stars, elapsed, mode)
    encounter, encounter_index, encounter_layers = render_encounter_layers(
        scene, mode, elapsed, height, width
    )
    statistics = scene.render_spacecraft(
        mesh, spacecraft, mode, elapsed, programme, style,
        hidden_lines, depth_scale
    )
    scene_seconds = time.perf_counter() - started
    encode_started = time.perf_counter()
    ordered_layers = [(10, stars), *encounter_layers, (30, spacecraft)]
    frame = encode_layers(ordered_layers, mode, columns, graphic_rows)
    encode_seconds = time.perf_counter() - encode_started
    statistics = (*statistics, scene_seconds, encode_seconds)
    return encounter, encounter_index, frame, statistics, tuple(
        rgb for _, rgb in ordered_layers
    )
