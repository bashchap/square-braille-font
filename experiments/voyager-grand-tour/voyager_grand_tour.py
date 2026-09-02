#!/usr/bin/env python3
"""Voyager 2 Grand Tour rendered through Square Braille 2x4 or PUA 4x4.

The renderer uses NASA VTAD Voyager geometry, a depth-buffer hidden-line
pipeline, procedural encounter-era planetary bodies, and two interchangeable
terminal-cell encoders.  Run with exactly one of ``-2`` or ``-4``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import select
import shutil
import signal
import sys
import termios
import time
import tty
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from voyager_core import (BRAILLE_BITS, MATERIAL_COLORS, PUA4_BITS, normalize,
                          pua4_codepoint, raster_depth, terminal_picture)
from voyager_layers import render_layered_frame, terminal_picture_v2


HERE = Path(__file__).resolve().parent
DEFAULT_MESH = HERE / "assets" / "voyager-vtad-hlr.npz"
SEGMENT_SECONDS = 10.0
MISSION_SECONDS = 60.0
TITLE = "VOYAGER 2 — THE GRAND TOUR"


@dataclass(frozen=True)
class Planet:
    name: str
    equatorial_km: float
    polar_km: float
    axial_tilt: float
    base: tuple[int, int, int]
    bands: tuple[int, int, int]

    @property
    def flattening_ratio(self):
        return self.polar_km / self.equatorial_km


# NASA/JPL physical radii, kilometres.  Sources are documented in README.md.
JUPITER = Planet("JUPITER", 71492, 66854, 3.13, (190, 140, 91), (235, 202, 154))
SATURN = Planet("SATURN", 60268, 54364, 26.73, (203, 174, 111), (242, 218, 160))
URANUS = Planet("URANUS", 25559, 24973, 97.77, (104, 190, 205), (161, 225, 225))
NEPTUNE = Planet("NEPTUNE", 24764, 24341, 28.32, (29, 92, 183), (64, 155, 235))


@dataclass(frozen=True)
class Encounter:
    title: str
    date: str
    planet: Planet | None
    companion: str
    note: str
    camera_zoom: float


ENCOUNTERS = (
    Encounter("JUPITER APPROACH", "9 JUL 1979", JUPITER, "IO",
              "cloud belts, Great Red Spot and volcanic Io", .91),
    Encounter("JOVIAN DEPARTURE", "JUL 1979", JUPITER, "GANYMEDE",
              "largest moon in the Solar System", 1.06),
    Encounter("SATURN FLYBY", "25 AUG 1981", SATURN, "TITAN",
              "ring-plane crossing and Titan", .96),
    Encounter("URANUS FLYBY", "24 JAN 1986", URANUS, "MIRANDA",
              "97.77 degree axial tilt and dark rings", 1.16),
    Encounter("NEPTUNE FLYBY", "25 AUG 1989", NEPTUNE, "TRITON",
              "Great Dark Spot and retrograde Triton", 1.04),
    Encounter("INTERSTELLAR DEPARTURE", "AUG 1989 — PRESENT", None, "PALE BLUE DOT",
              "below the ecliptic and outward", .88),
)


GRAND_EYES = np.array((
    (1.22, -1.55, .78), (-1.10, -1.38, .64), (-.72, .72, 1.45),
    (.34, 1.72, .58), (1.48, .54, -.36), (.46, -.74, -1.48),
), dtype=np.float64)
GRAND_TARGETS = np.array((
    (0, -.08, -.05), (0, -.11, -.04), (0, -.02, -.04),
    (0, -.10, .01), (0, -.08, -.08), (0, -.03, -.03),
), dtype=np.float64)
GRAND_ROLLS = np.radians((0, -8, 6, 13, -10, 3)).astype(np.float64)

# Per-encounter pursuit-shot axes.  A shot begins behind and outside Voyager,
# dives toward a close lateral pass, crosses its velocity vector, then recovers
# ahead of the spacecraft.  Cuts happen only at the ten-second encounter
# boundaries; motion within a shot is smooth and continuously tracked.
SHOT_AZIMUTHS = np.radians((-32, 118, 42, -126, 18, 154)).astype(np.float64)
SHOT_ELEVATIONS = np.radians((18, 12, 30, -9, 16, -22)).astype(np.float64)
SHOT_ROLLS = np.radians((-8, 11, -14, 18, -10, 7)).astype(np.float64)

# Feature-to-feature close inspection.  Periodic Catmull-Rom tangents are
# represented and evaluated as cubic Bezier control points.
CONTOUR_EYES = np.array((
    (.50, -.48, .36), (-.48, -.42, .31), (-.44, .18, .24),
    (.18, .48, .18), (.44, .12, -.28), (.26, -.36, -.48),
    (-.28, -.40, -.34), (-.50, -.06, .02),
), dtype=np.float64)
CONTOUR_TARGETS = np.array((
    (0, -.13, -.08), (0, -.12, -.08), (0, .02, -.16),
    (0, .09, -.08), (0, -.02, -.18), (0, -.11, -.12),
    (0, -.14, -.02), (0, -.02, .10),
), dtype=np.float64)
CONTOUR_ROLLS = np.radians((0, -12, -4, 10, 15, 6, -9, -5)).astype(np.float64)


def smoothstep(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def smootherstep(value):
    value = min(1.0, max(0.0, value))
    return value**3 * (value*(value*6.0-15.0)+10.0)


def grand_tour_shot(elapsed):
    """Return cinematic camera and screen choreography for one encounter.

    The mesh remains in its physically coherent local frame.  Apparent flight
    comes from a pursuit camera translating around it, a lead-tracking screen
    position, planetary parallax and a speed-dependent star streak field.
    """
    segment = int((elapsed % MISSION_SECONDS)//SEGMENT_SECONDS)
    local = elapsed % SEGMENT_SECONDS
    u = local/SEGMENT_SECONDS
    travel = smootherstep(u)
    encounter = ENCOUNTERS[segment]
    azimuth = SHOT_AZIMUTHS[segment] + math.radians(-58+176*travel)
    elevation = (SHOT_ELEVATIONS[segment] + math.radians(17)*math.sin(math.pi*u)
                 - math.radians(7)*math.sin(math.tau*u))
    # Fast close pass around the middle, with a mild acceleration bias toward
    # the exit.  The minimum distance still remains outside the mesh envelope.
    pass_weight = math.sin(math.pi*u)**2
    distance = 2.05 - .78*pass_weight + .18*(u-.5)
    target = GRAND_TARGETS[segment].copy()
    target += np.array((.035*math.sin(math.tau*u),
                        .028*math.sin(math.pi*u),
                        .045*math.sin(math.tau*u+.7)))
    direction = np.array((math.cos(elevation)*math.cos(azimuth),
                          math.cos(elevation)*math.sin(azimuth),
                          math.sin(elevation)))
    eye = target+direction*distance
    roll = (SHOT_ROLLS[segment] + math.radians(14)*math.sin(math.pi*u)
            - math.radians(8)*math.sin(math.tau*u))
    zoom = encounter.camera_zoom*(.88+.07*pass_weight)
    ship_x = .20+.36*travel+.045*math.sin(math.pi*u)
    ship_y = .59-.16*math.sin(math.pi*u)+.045*math.sin(math.tau*u+segment*.7)
    planet_x = .80-.105*math.sin(math.pi*u)+.025*math.sin(math.tau*u)
    planet_y = .51+.070*math.sin(math.tau*u+segment*.55)
    planet_scale = .70+.34*pass_weight
    speed = .25+.75*pass_weight
    return {
        "segment": segment,
        "u": u,
        "eye": eye,
        "target": target,
        "roll": float(roll),
        "zoom": float(zoom),
        "ship_centre": (ship_x, ship_y),
        "planet_centre": (planet_x, planet_y),
        "planet_scale": planet_scale,
        "speed": speed,
    }


def cubic_bezier(p0, p1, p2, p3, amount):
    other = 1.0 - amount
    return (other**3*p0 + 3*other**2*amount*p1 +
            3*other*amount**2*p2 + amount**3*p3)


def periodic_bezier(keys, position, tangent_scale=1.0):
    count = len(keys)
    index = math.floor(position) % count
    amount = position - math.floor(position)
    previous = keys[(index-1) % count]
    current = keys[index]
    following = keys[(index+1) % count]
    after = keys[(index+2) % count]
    control1 = current + (following-previous) * (tangent_scale/6.0)
    control2 = following - (after-current) * (tangent_scale/6.0)
    return cubic_bezier(current, control1, control2, following, amount)


def load_mesh(path: Path):
    raw = np.load(path, allow_pickle=False)
    return {name: raw[name] for name in raw.files}


def enforce_mesh_clearance(eye, target, vertices, clearance=.075):
    """Keep a camera outside the mesh's directional support surface."""
    outward = eye-target
    distance = float(np.linalg.norm(outward))
    direction = normalize(outward)
    support = float(np.max((vertices-target) @ direction))
    required = support + clearance
    if distance < required:
        eye = target + direction*required
    return eye


def camera_at(elapsed, programme, vertices):
    if programme == "grand-tour":
        shot = grand_tour_shot(elapsed)
        eye, target = shot["eye"], shot["target"]
        roll, zoom = shot["roll"], shot["zoom"]
        eye = enforce_mesh_clearance(eye, target, vertices, .11)
    else:
        period = 48.0
        position = (elapsed % period) / period * len(CONTOUR_EYES)
        eye = periodic_bezier(CONTOUR_EYES, position, .82)
        target = periodic_bezier(CONTOUR_TARGETS, position, .76)
        roll = float(periodic_bezier(CONTOUR_ROLLS, position, .78))
        eye = enforce_mesh_clearance(eye, target, vertices)
        zoom = 1.0
    return eye, target, roll, zoom


def camera_basis(eye, target, roll):
    forward = normalize(target-eye)
    world_up = np.array((0., 0., 1.))
    if abs(float(np.dot(forward, world_up))) > .96:
        world_up = np.array((0., 1., 0.))
    right = normalize(np.cross(forward, world_up))
    up = normalize(np.cross(right, forward))
    cosine, sine = math.cos(roll), math.sin(roll)
    right, up = right*cosine + up*sine, up*cosine - right*sine
    return np.stack((right, up, forward))


def project_mesh(vertices, eye, target, roll, mode, width, height,
                 programme, zoom, elapsed=0.0):
    camera = camera_basis(eye, target, roll)
    transformed = (vertices-eye) @ camera.T
    z = transformed[:, 2]
    # A 4x4 virtual pixel is half as wide as a 2x4 virtual pixel in the same
    # 1:2 terminal cell.  Horizontal focal length therefore scales by mode/2.
    fov = math.radians(47 if programme == "grand-tour" else 55)
    focal_y = height / (2.0*math.tan(fov*.5)) * zoom
    focal_x = focal_y * (mode/2.0)
    safe = np.maximum(z, .025)
    if programme == "grand-tour":
        ship_centre = grand_tour_shot(elapsed)["ship_centre"]
        centre_x, centre_y = width*ship_centre[0], height*ship_centre[1]
    else:
        centre_x, centre_y = width*.50, height*.54
    projected = np.empty((len(vertices), 2), dtype=np.float32)
    projected[:, 0] = centre_x + transformed[:, 0]*focal_x/safe
    projected[:, 1] = centre_y - transformed[:, 1]*focal_y/safe
    return projected, z


def line_depth_tested(rgb, depth, p0, p1, z0, z1, color, depth_scale,
                      hidden_lines, tolerance=.023):
    height, width, _ = rgb.shape
    delta = p1-p0
    steps = max(1, int(math.ceil(float(np.max(np.abs(delta))))))
    inverse0, inverse1 = 1.0/z0, 1.0/z1
    last = None
    for step in range(steps+1):
        amount = step/steps
        x, y = np.rint(p0 + delta*amount).astype(int)
        if not (0 <= x < width and 0 <= y < height):
            continue
        if hidden_lines:
            inverse = inverse0 + (inverse1-inverse0)*amount
            sample = depth[min(depth.shape[0]-1, y//depth_scale),
                           min(depth.shape[1]-1, x//depth_scale)]
            if inverse + tolerance*max(inverse, sample) < sample:
                last = None
                continue
        rgb[y, x] = color
        if last is not None and x != last[0] and y != last[1]:
            if abs(delta[0]) >= abs(delta[1]):
                rgb[last[1], x] = color
            else:
                rgb[y, last[0]] = color
        last = (x, y)


def render_spacecraft(mesh, rgb, mode, elapsed, programme, style,
                      hidden_lines, depth_scale):
    vertices, faces = mesh["vertices"], mesh["faces"]
    height, width, _ = rgb.shape
    eye, target, roll, zoom = camera_at(elapsed, programme, vertices)
    projected, z = project_mesh(vertices, eye, target, roll, mode, width,
                                height, programme, zoom, elapsed)
    ds = max(1, depth_scale)
    depth = np.zeros(((height+ds-1)//ds, (width+ds-1)//ds), dtype=np.float32)
    tri_z, tri_p = z[faces], projected[faces]/ds
    area = np.abs((tri_p[:,1,0]-tri_p[:,0,0])*(tri_p[:,2,1]-tri_p[:,0,1]) -
                  (tri_p[:,1,1]-tri_p[:,0,1])*(tri_p[:,2,0]-tri_p[:,0,0]))
    valid = np.all(tri_z > .025, axis=1) & (area >= .018)
    valid &= np.max(tri_p[:,:,0], axis=1) >= -1
    valid &= np.min(tri_p[:,:,0], axis=1) <= depth.shape[1]
    valid &= np.max(tri_p[:,:,1], axis=1) >= -1
    valid &= np.min(tri_p[:,:,1], axis=1) <= depth.shape[0]
    face_indices = np.flatnonzero(valid)
    surface = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if hidden_lines or style == "filled":
        light = normalize(np.array((-.35, -.3, 1.0)))
        for index in face_indices[np.argsort(-area[face_indices])]:
            if style == "filled":
                material = int(mesh["materials"][index])
                base = MATERIAL_COLORS[material % len(MATERIAL_COLORS)].astype(float)
                diffuse = abs(float(np.dot(mesh["normals"][index], light)))
                color = np.clip(base*(.28+.72*diffuse), 0, 255).astype(np.uint8)
            else:
                color = None
            raster_depth(depth, tri_p[index], tri_z[index],
                         surface if style == "filled" else None, color)
    if style == "filled":
        expanded = np.repeat(np.repeat(surface, ds, axis=0), ds, axis=1)
        expanded = expanded[:height, :width]
        occupied = np.any(expanded != 0, axis=2)
        rgb[occupied] = expanded[occupied]

    facing = np.sum(mesh["normals"]*(eye-mesh["centers"]), axis=1)
    paired = mesh["face1"] >= 0
    second = np.zeros(len(mesh["edges"]), dtype=np.float64)
    second[paired] = facing[mesh["face1"][paired]] * np.where(
        mesh["normal_dot"][paired] < 0, -1.0, 1.0)
    silhouette = paired & (facing[mesh["face0"]]*second <= 0)
    selected = ((silhouette | (mesh["face1"] < 0)) if style == "filled"
                else (mesh["crease"] | silhouette))
    edge_z = z[mesh["edges"]]
    selected &= np.all(edge_z > .025, axis=1)
    edge_p = projected[mesh["edges"]]
    selected &= np.max(edge_p[:,:,0], axis=1) >= -2
    selected &= np.min(edge_p[:,:,0], axis=1) <= width+1
    selected &= np.max(edge_p[:,:,1], axis=1) >= -2
    selected &= np.min(edge_p[:,:,1], axis=1) <= height+1
    selected &= np.max(np.abs(edge_p[:,1]-edge_p[:,0]), axis=1) >= .62
    edge_indices = np.flatnonzero(selected)
    edge_indices = edge_indices[np.argsort(-edge_z[edge_indices].mean(1))]
    for index in edge_indices:
        owner = mesh["face0"][index]
        material = int(mesh["materials"][owner])
        color = (np.array((224, 248, 255), dtype=np.uint8) if style == "filled"
                 else MATERIAL_COLORS[material % len(MATERIAL_COLORS)])
        line_depth_tested(rgb, depth, edge_p[index,0], edge_p[index,1],
                          edge_z[index,0], edge_z[index,1], color, ds,
                          hidden_lines or style == "filled")
    return len(face_indices), len(edge_indices), eye, target


def physical_grid(width, height, mode):
    yy, xx = np.indices((height, width), dtype=np.float32)
    pixel_aspect = 2.0/mode
    return xx, yy, pixel_aspect


def add_stars(rgb, elapsed, mode, seed=1977):
    height, width, _ = rgb.shape
    rng = np.random.default_rng(seed)
    stars = rng.random((420, 4))
    shot = grand_tour_shot(elapsed)
    drift = elapsed*.011
    direction = -1 if shot["segment"] % 2 else 1
    trail_scale = shot["speed"]
    for u, v, brightness, phase in stars:
        x = int(((u+direction*drift*(.28+phase)) % 1.0)*width)
        y = int(((v+drift*(.08+phase*.10)) % 1.0)*height)
        level = int(65 + brightness*185)
        rgb[y, x] = (level, level, min(255, level+22))
        if brightness > .78:
            trail = int(1+(brightness-.78)*18*trail_scale)
            for offset in range(1, trail+1):
                sample_x = x-direction*offset
                sample_y = y-max(0, offset//5)
                if 0 <= sample_x < width and 0 <= sample_y < height:
                    fade = max(.18, 1-offset/(trail+1))
                    rgb[sample_y, sample_x] = (
                        int(level*fade), int(level*fade),
                        int(min(255, level+22)*fade))


def draw_ellipse_line(rgb, centre, radii, rotation, color, mode,
                      start=0.0, stop=math.tau, samples=900):
    height, width, _ = rgb.shape
    pixel_aspect = 2.0/mode
    cosine, sine = math.cos(rotation), math.sin(rotation)
    previous = None
    for angle in np.linspace(start, stop, samples):
        local_x = radii[0]*math.cos(angle)
        local_y = radii[1]*math.sin(angle)
        physical_x = local_x*cosine-local_y*sine
        physical_y = local_x*sine+local_y*cosine
        point = (int(round(centre[0]+physical_x/pixel_aspect)),
                 int(round(centre[1]+physical_y)))
        if previous is not None:
            draw_simple_line(rgb, previous, point, color)
        previous = point


def draw_simple_line(rgb, p0, p1, color):
    height, width, _ = rgb.shape
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1-x0, y1-y0
    steps = max(1, abs(dx), abs(dy))
    for step in range(steps+1):
        x = int(round(x0+dx*step/steps))
        y = int(round(y0+dy*step/steps))
        if 0 <= x < width and 0 <= y < height:
            rgb[y, x] = color


def draw_moon(rgb, mode, centre, radius, base, seed, phase=.75):
    height, width, _ = rgb.shape
    xx, yy, pixel_aspect = physical_grid(width, height, mode)
    dx = (xx-centre[0])*pixel_aspect
    dy = yy-centre[1]
    q = (dx/radius)**2+(dy/radius)**2
    mask = q <= 1
    normal_z = np.sqrt(np.clip(1-q, 0, 1))
    normal_x = dx/max(radius, 1e-6)
    light = np.clip(normal_z*.78-normal_x*.38+.20, .08, 1)
    rng = np.random.default_rng(seed)
    noise = rng.random((height, width))*.13+.93
    shade = light*noise
    color = np.asarray(base, dtype=np.float32)
    for channel in range(3):
        rgb[..., channel][mask] = np.clip(color[channel]*shade[mask], 0, 255)
    # A few deterministic crater rims.
    for offset_x, offset_y, size in ((-.24, -.12, .15), (.18, .23, .12), (.28, -.25, .08)):
        crater = (((dx/radius-offset_x)/size)**2+
                  ((dy/radius-offset_y)/size)**2 <= 1)
        rim = crater & (q <= 1)
        rgb[rim] = (np.asarray(base)*.58).astype(np.uint8)


def draw_planet(rgb, mode, planet, centre, radius, elapsed, alpha=1.0):
    height, width, _ = rgb.shape
    xx, yy, pixel_aspect = physical_grid(width, height, mode)
    equatorial = radius
    polar = radius*planet.flattening_ratio
    dx = (xx-centre[0])*pixel_aspect/equatorial
    dy = (yy-centre[1])/polar
    q = dx*dx+dy*dy
    mask = q <= 1
    normal_z = np.sqrt(np.clip(1-q, 0, 1))
    illumination = np.clip(normal_z*.72-dx*.34+.28, .06, 1)
    latitude = dy
    base = np.asarray(planet.base, dtype=np.float32)
    band_color = np.asarray(planet.bands, dtype=np.float32)
    if planet is JUPITER:
        mix = .34+.28*np.sin(latitude*28)+.13*np.sin(latitude*71)
    elif planet is SATURN:
        mix = .28+.17*np.sin(latitude*34)+.07*np.sin(latitude*83)
    elif planet is URANUS:
        mix = .34+.05*np.sin(latitude*18)
    else:
        mix = .27+.16*np.sin(latitude*22)+.06*np.sin(latitude*57)
    mix = np.clip(mix, 0, 1)[..., None]
    color = base*(1-mix)+band_color*mix
    color *= illumination[..., None]*alpha
    rgb[mask] = np.clip(color[mask], 0, 255).astype(np.uint8)
    if planet is JUPITER:
        spot = ((dx+.28)/.22)**2+((dy-.30)/.10)**2 <= 1
        rgb[spot & mask] = np.asarray((185, 62, 40))*alpha
    elif planet is NEPTUNE:
        spot = ((dx+.20)/.27)**2+((dy-.25)/.12)**2 <= 1
        rgb[spot & mask] = np.asarray((10, 37, 91))*alpha
        cloud = ((dx-.08)/.18)**2+((dy-.08)/.035)**2 <= 1
        rgb[cloud & mask] = np.asarray((145, 216, 255))*alpha


def render_encounter(rgb, mode, elapsed):
    height, width, _ = rgb.shape
    index = int((elapsed % MISSION_SECONDS)//SEGMENT_SECONDS)
    local = elapsed % SEGMENT_SECONDS
    encounter = ENCOUNTERS[index]
    fade = smoothstep(min(local/.75, (SEGMENT_SECONDS-local)/.75))
    shot = grand_tour_shot(elapsed)
    physical_width = width*(2.0/mode)
    base_radius = min(height*.31, physical_width*.23)*shot["planet_scale"]
    centre = (width*shot["planet_centre"][0],
              height*shot["planet_centre"][1])
    moon_centre = (centre[0]-width*(.18+.035*math.sin(math.pi*shot["u"])),
                   centre[1]-height*(.24+.04*math.cos(math.tau*shot["u"])))
    if encounter.planet is JUPITER:
        draw_planet(rgb, mode, JUPITER, centre, base_radius, elapsed, fade)
        if index == 0:
            draw_moon(rgb, mode, moon_centre, base_radius*.095,
                      (218, 180, 104), 501, .8)
        else:
            draw_moon(rgb, mode, moon_centre, base_radius*.14,
                      (142, 132, 121), 502, .7)
    elif encounter.planet is SATURN:
        ring_radius = base_radius*.72
        rotation = math.radians(-13)
        draw_ellipse_line(rgb, centre, (ring_radius*2.26, ring_radius*.55),
                          rotation, (92, 79, 61), mode)
        draw_ellipse_line(rgb, centre, (ring_radius*1.63, ring_radius*.40),
                          rotation, (188, 162, 112), mode)
        draw_planet(rgb, mode, SATURN, centre, ring_radius, elapsed, fade)
        # Near ring half overlays the globe.
        draw_ellipse_line(rgb, centre, (ring_radius*2.26, ring_radius*.55),
                          rotation, (222, 198, 145), mode, 0, math.pi)
        draw_ellipse_line(rgb, centre, (ring_radius*1.63, ring_radius*.40),
                          rotation, (154, 131, 92), mode, 0, math.pi)
        draw_moon(rgb, mode, moon_centre, ring_radius*.13,
                  (194, 151, 94), 601)
    elif encounter.planet is URANUS:
        radius = base_radius*.87
        draw_ellipse_line(rgb, centre, (radius*1.76, radius*.22), math.radians(82),
                          (92, 122, 124), mode)
        draw_planet(rgb, mode, URANUS, centre, radius, elapsed, fade)
        draw_ellipse_line(rgb, centre, (radius*1.76, radius*.22), math.radians(82),
                          (151, 194, 197), mode, 0, math.pi)
        draw_moon(rgb, mode, moon_centre, radius*.08,
                  (169, 165, 156), 701)
    elif encounter.planet is NEPTUNE:
        radius = base_radius*.88
        draw_planet(rgb, mode, NEPTUNE, centre, radius, elapsed, fade)
        draw_ellipse_line(rgb, centre, (radius*1.64, radius*.16), math.radians(-9),
                          (45, 76, 121), mode)
        draw_moon(rgb, mode, moon_centre, radius*.11,
                  (177, 183, 173), 801)
    else:
        # Pale Blue Dot: deliberately one subpixel at this scale, with a faint
        # scattered-light ray recalling Voyager 1's family portrait.
        for offset in range(-height, height):
            x = int(centre[0]+offset*(mode/8))
            y = int(centre[1]+offset)
            if 0 <= x < width and 0 <= y < height:
                rgb[y, x] = (45, 33, 56)
        x, y = int(centre[0]), int(centre[1])
        if 0 <= x < width and 0 <= y < height:
            rgb[y, x] = (114, 157, 244)
    return encounter, index


def encode_frame(rgb, mode, columns, rows):
    sx = mode
    bits = BRAILLE_BITS if mode == 2 else PUA4_BITS
    blocks = rgb[:rows*4, :columns*sx].reshape(rows, 4, columns, sx, 3)
    blocks = blocks.transpose(0, 2, 1, 3, 4)
    occupied = np.any(blocks != 0, axis=4)
    # Force a wide shift operand.  Shifting a NumPy uint8 by bits 8..15 would
    # otherwise wrap to zero before the result is cast to uint16.
    weights = np.left_shift(np.uint32(1), bits.astype(np.uint32)).astype(np.uint16)
    masks = np.sum(occupied*weights[None, None, :, :], axis=(2, 3),
                   dtype=np.uint32).astype(np.uint16)
    luminance = (blocks[...,0].astype(np.uint16)*3 +
                 blocks[...,1].astype(np.uint16)*6 + blocks[...,2])
    luminance[~occupied] = 0
    pick = np.argmax(luminance.reshape(rows, columns, 4*sx), axis=2)
    colors = np.take_along_axis(blocks.reshape(rows, columns, 4*sx, 3),
                                pick[..., None, None], axis=2)[:, :, 0]
    colors = (colors//8)*8
    return masks, colors


def status_line(columns, mode, encounter, programme, style, hidden_lines,
                fps_actual, elapsed):
    depth_status = ("HLR=N/A" if style == "filled" else
                    f"HLR={'ON' if hidden_lines else 'OFF'}")
    text = (f" {TITLE}  -{mode}  {programme.upper()}  {style.upper()} "
            f"{depth_status}  2CLR=ON  "
            f"{encounter.title} [{encounter.date}]  {fps_actual:4.1f} fps  "
            "q/ESC quit  f style  h HLR  c camera ")
    return "\x1b[0;30;47m" + text[:columns].ljust(columns) + "\x1b[0m"


class Keyboard:
    def __init__(self):
        self.fd = None
        self.saved = None

    def __enter__(self):
        if sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def read(self):
        if self.fd is None:
            return ""
        ready, _, _ = select.select([self.fd], [], [], 0)
        return os.read(self.fd, 16).decode("utf-8", "ignore") if ready else ""

    def __exit__(self, *unused):
        if self.fd is not None and self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)


def render_frame(mesh, mode, columns, graphic_rows, elapsed, programme,
                 style, hidden_lines, depth_scale):
    scene_started = time.perf_counter()
    width, height = columns*mode, graphic_rows*4
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    add_stars(rgb, elapsed, mode)
    encounter, index = render_encounter(rgb, mode, elapsed)
    statistics = render_spacecraft(mesh, rgb, mode, elapsed, programme, style,
                                   hidden_lines, depth_scale)
    scene_seconds = time.perf_counter()-scene_started
    encode_started = time.perf_counter()
    masks, colors = encode_frame(rgb, mode, columns, graphic_rows)
    encode_seconds = time.perf_counter()-encode_started
    statistics = (*statistics, scene_seconds, encode_seconds)
    return encounter, index, masks, colors, statistics


def add_mode_arguments(parser, required=True):
    modes = parser.add_mutually_exclusive_group(required=required)
    modes.add_argument("-2", dest="mode", action="store_const", const=2,
                       help="Square Braille 2x4; Unicode U+2800..U+28FF")
    modes.add_argument("-4", dest="mode", action="store_const", const=4,
                       help="PUA 4x4 Part 0/Part 1")


def add_render_arguments(parser):
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--style", choices=("wire", "filled"), default="wire")
    parser.add_argument("--no-hlr", action="store_true",
                        help="wireframe only: show occluded edges and skip the depth pass")
    parser.add_argument("--camera", choices=("grand-tour", "contour"),
                        default="grand-tour")
    parser.add_argument("--depth-scale", type=int, choices=(1, 2, 3, 4), default=2)


def parse_live_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_mode_arguments(parser)
    add_render_arguments(parser)
    parser.add_argument("--fps", type=float, default=4.0,
                        help="target frames per second (default: 4; rendering may adapt lower)")
    parser.add_argument("--once", action="store_true", help="stop after one 60-second tour")
    parser.add_argument("--seconds", type=float, default=0,
                        help="stop after this many seconds; zero means continuous")
    parser.add_argument("--freeze-at", type=float,
                        help="render one mission time and hold it")
    parser.add_argument("--hold", type=float, default=8.0)
    parser.add_argument("--columns", type=int, help="fixed width for tests/captures")
    parser.add_argument("--rows", type=int, help="fixed height including status row")
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--capture", type=Path,
                        help="write the last frame as self-contained UTF-8 ANSI text")
    parser.add_argument("--no-status", action="store_true")
    return parser.parse_args(argv)


def parse_capture_args(argv):
    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} capture",
        description="Render deterministic frames offline into an indexed VGR archive.")
    add_mode_arguments(parser)
    add_render_arguments(parser)
    parser.add_argument("--duration", type=float, default=60.0,
                        help="animation seconds to capture (default: 60)")
    parser.add_argument("--fps", type=float, default=4.0,
                        help="animation sampling rate (default: 4)")
    parser.add_argument("--start-time", type=float, default=0.0)
    parser.add_argument("--output", type=Path,
                        help="VGR output; default includes selected font mode")
    parser.add_argument("--columns", type=int,
                        help="captured terminal columns (default: current terminal)")
    parser.add_argument("--rows", type=int,
                        help="captured terminal rows including playback status")
    parser.add_argument("--no-status", action="store_true",
                        help="do not reserve a playback status row")
    parser.add_argument("--compression", type=int, choices=range(0, 10), default=6)
    parser.add_argument("--dashboard-hz", type=float, default=4.0)
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the capture dashboard")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing output archive")
    return parser.parse_args(argv)


def parse_play_args(argv):
    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} play",
        description="Play a VGR archive without re-rendering its 3D scene.")
    add_mode_arguments(parser, required=False)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--fps", type=float,
                        help="override the recorded playback frame rate")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--stream", action="store_true",
                        help="decode frames on demand instead of preloading")
    parser.add_argument("--no-status", action="store_true")
    parser.add_argument("--allow-small-terminal", action="store_true")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip the archive-wide CRC check")
    return parser.parse_args(argv)


def digest_files(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def capture_metadata(args, output, columns, total_rows, graphic_rows,
                     frame_count):
    source = json.loads((HERE/"assets/voyager-vtad-source.json").read_text())
    virtual_width, virtual_height = columns*args.mode, graphic_rows*4
    duration = frame_count/args.fps
    return {
        "schema": "org.square-braille.voyager-recording",
        "format_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "renderer": {
            "title": TITLE,
            "source_hash": digest_files((Path(__file__),
                                         HERE/"voyager_core.py",
                                         HERE/"voyager_recording.py")),
            "numpy": np.__version__,
            "python": sys.version.split()[0],
        },
        "model": source,
        "render": {
            "mode": args.mode,
            "style": args.style,
            "hidden_line_removal": not args.no_hlr,
            "camera": args.camera,
            "depth_scale": args.depth_scale,
            "start_time": args.start_time,
        },
        "terminal": {
            "columns": columns,
            "rows": total_rows,
            "graphic_rows": graphic_rows,
            "status_rows": total_rows-graphic_rows,
            "virtual_width": virtual_width,
            "virtual_height": virtual_height,
            "cell_grid": f"{args.mode}x4",
            "launcher_zoom": (float(os.environ["VOYAGER_TERMINAL_ZOOM"])
                              if os.environ.get("VOYAGER_TERMINAL_ZOOM") else None),
        },
        "encoding": {
            "frame_packet": "VGF1: header + little-endian masks + RGB888 cells",
            "mask_bytes": 1 if args.mode == 2 else 2,
            "codepoints": ("U+2800..U+28FF" if args.mode == 2 else
                           "Part 0 U+F0000..U+F7FFF; Part 1 U+100000..U+107FFF"),
            "bit_mapping": ("Unicode Braille" if args.mode == 2 else
                            "bit = 4*local_y + (3-local_x)"),
        },
        "capture": {
            "output": str(output),
            "requested_duration_seconds": args.duration,
            "duration_seconds": duration,
            "fps": args.fps,
            "frame_count": frame_count,
            "compression": "ZIP DEFLATE, independently indexed frames",
            "compression_level": args.compression,
        },
        "timeline": [
            {"start": index*SEGMENT_SECONDS, "stop": (index+1)*SEGMENT_SECONDS,
             "title": encounter.title, "date": encounter.date,
             "companion": encounter.companion}
            for index, encounter in enumerate(ENCOUNTERS)
        ],
    }


def validate_expected_terminal(terminal):
    """Refuse capture if MATE constrained a requested logical geometry."""
    expected_columns = os.environ.get("VOYAGER_EXPECT_TERMINAL_COLUMNS")
    expected_rows = os.environ.get("VOYAGER_EXPECT_TERMINAL_ROWS")
    if expected_columns is None and expected_rows is None:
        return
    if expected_columns is None or expected_rows is None:
        raise SystemExit("incomplete expected terminal geometry from launcher")
    expected = (int(expected_columns), int(expected_rows))
    actual = (terminal.columns, terminal.lines)
    if actual != expected:
        zoom = os.environ.get("VOYAGER_TERMINAL_ZOOM", "not set")
        raise SystemExit(
            "Capture aborted before frame 1: requested terminal "
            f"{expected[0]}x{expected[1]}, but MATE created "
            f"{actual[0]}x{actual[1]} (zoom {zoom}). Reduce "
            "--terminal-zoom, reduce the requested geometry, or enlarge the "
            "desktop. No recording was written.")


def capture_main(args):
    from voyager_recording import CaptureDashboard, CaptureMetrics, VGRWriter

    if args.duration <= 0 or args.fps <= 0:
        raise SystemExit("--duration and --fps must be positive")
    if args.dashboard_hz <= 0:
        raise SystemExit("--dashboard-hz must be positive")
    if not args.mesh.exists():
        raise SystemExit(f"Voyager mesh cache not found: {args.mesh}")
    terminal = shutil.get_terminal_size((100, 32))
    validate_expected_terminal(terminal)
    columns = max(20, args.columns or terminal.columns)
    total_rows = max(8, args.rows or terminal.lines)
    status_rows = 0 if args.no_status else 1
    graphic_rows = total_rows-status_rows
    frame_count = max(1, int(math.ceil(args.duration*args.fps-1e-12)))
    output = args.output or Path(f"voyager-grand-tour-{args.mode}x4.vgr")
    metadata = capture_metadata(args, output, columns, total_rows, graphic_rows,
                                frame_count)
    mesh = load_mesh(args.mesh)
    started = time.monotonic()
    p0_cells = p1_cells = 0
    final_metrics = None
    try:
        with CaptureDashboard(not args.quiet, args.dashboard_hz) as dashboard:
            with VGRWriter(output, metadata, args.force, args.compression) as writer:
                for index in range(frame_count):
                    animation_time = args.start_time+index/args.fps
                    frame_started = time.perf_counter()
                    encounter, _, masks, colors, statistics = render_frame(
                        mesh, args.mode, columns, graphic_rows, animation_time,
                        args.camera, args.style, not args.no_hlr, args.depth_scale)
                    render_seconds = time.perf_counter()-frame_started
                    nonzero = masks[masks != 0]
                    unique_masks = np.unique(masks)
                    unique_nonzero = np.unique(nonzero)
                    if args.mode == 4:
                        p0_values = nonzero[nonzero < 0x8000]
                        p1_values = nonzero[nonzero >= 0x8000]
                    else:
                        p0_values = nonzero
                        p1_values = np.empty(0, dtype=nonzero.dtype)
                    p0_frame_cells = int(p0_values.size)
                    p1_frame_cells = int(p1_values.size)
                    p0_unique_masks = int(np.unique(p0_values).size)
                    p1_unique_masks = int(np.unique(p1_values).size)
                    p0_cells += p0_frame_cells
                    p1_cells += p1_frame_cells
                    encoding_statistics = {
                        "total_cells": int(masks.size),
                        "occupied_cells": int(nonzero.size),
                        "blank_cells": int(masks.size-nonzero.size),
                        "unique_masks_including_blank": int(unique_masks.size),
                        "unique_nonzero_masks": int(unique_nonzero.size),
                        "p0_cells": p0_frame_cells,
                        "p1_cells": p1_frame_cells,
                        "p0_unique_masks": p0_unique_masks,
                        "p1_unique_masks": p1_unique_masks,
                    }
                    frame_record = writer.add_frame(
                        index, animation_time, masks, colors, render_seconds,
                        encounter.title, statistics)
                    frame_record["encoding"] = encoding_statistics
                    real_elapsed = time.monotonic()-started
                    completed = index+1
                    remaining = real_elapsed/completed*(frame_count-completed)
                    archive_bytes = (writer.partial.stat().st_size
                                     if writer.partial.exists() else 0)
                    final_metrics = CaptureMetrics(
                        frame_index=index, frame_count=frame_count,
                        animation_time=animation_time,
                        duration=frame_count/args.fps, target_fps=args.fps,
                        render_seconds=render_seconds, real_elapsed=real_elapsed,
                        real_remaining=remaining, raw_bytes=writer.raw_bytes,
                        compressed_bytes=writer.compressed_bytes,
                        archive_bytes=archive_bytes, p0_cells=p0_cells,
                        p1_cells=p1_cells, encounter=encounter.title,
                        frame_raw_bytes=frame_record["raw_bytes"],
                        frame_compressed_bytes=frame_record["compressed_bytes"],
                        frame_write_seconds=frame_record["write_seconds"],
                        scene_seconds=float(statistics[4]),
                        encode_seconds=float(statistics[5]),
                        packet_seconds=frame_record["packet_seconds"],
                        total_cells=encoding_statistics["total_cells"],
                        occupied_cells=encoding_statistics["occupied_cells"],
                        blank_cells=encoding_statistics["blank_cells"],
                        unique_masks=encoding_statistics["unique_masks_including_blank"],
                        unique_nonzero_masks=encoding_statistics["unique_nonzero_masks"],
                        p0_frame_cells=p0_frame_cells,
                        p1_frame_cells=p1_frame_cells,
                        p0_unique_masks=p0_unique_masks,
                        p1_unique_masks=p1_unique_masks,
                        visible_faces=int(statistics[0]),
                        visible_edges=int(statistics[1]), masks=masks,
                        colors=colors)
                    dashboard.render(metadata, final_metrics,
                                     force=(index == frame_count-1))
                real_elapsed = time.monotonic()-started
                archive_bytes = writer.finish(real_elapsed)
                final_metrics.archive_bytes = archive_bytes
                final_metrics.real_elapsed = real_elapsed
                final_metrics.real_remaining = 0
                dashboard.render(metadata, final_metrics, force=True, complete=True)
                if dashboard.enabled:
                    time.sleep(.45)
    except FileExistsError as error:
        raise SystemExit(str(error)) from error
    print(f"Captured {frame_count} frames at {args.fps:g} fps: {output} "
          f"({format(archive_bytes, ',')} bytes, {real_elapsed:.3f} s real time)")
    return output


def play_main(args):
    from voyager_recording import play_recording

    if not args.recording.exists():
        raise SystemExit(f"recording not found: {args.recording}")
    try:
        return play_recording(
            args.recording, expected_mode=args.mode, fps_override=args.fps,
            speed=args.speed, loop=args.loop, stream=args.stream,
            no_status=args.no_status,
            allow_small_terminal=args.allow_small_terminal,
            verify=not args.no_verify)
    except (ValueError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error


def live_main(args):
    if not args.mesh.exists():
        raise SystemExit(f"Voyager mesh cache not found: {args.mesh}")
    if args.fps <= 0:
        raise SystemExit("--fps must be positive")
    mesh = load_mesh(args.mesh)
    style = args.style
    hidden_lines = not args.no_hlr
    programme = args.camera
    stop = False

    def request_stop(*unused):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    started = time.monotonic()
    next_frame = started
    frame_count = 0
    recent_started = started
    recent_frames = 0
    fps_actual = 0.0
    last_output = ""
    last_size = None
    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        with Keyboard() as keyboard:
            while not stop:
                now = time.monotonic()
                elapsed = args.freeze_at if args.freeze_at is not None else now-started
                if args.once and elapsed >= MISSION_SECONDS:
                    break
                if args.seconds and now-started >= args.seconds:
                    break
                if args.frames and frame_count >= args.frames:
                    break
                key = keyboard.read()
                if "q" in key.lower() or "\x1b" in key:
                    break
                if "f" in key.lower():
                    style = "filled" if style == "wire" else "wire"
                if "h" in key.lower():
                    hidden_lines = not hidden_lines
                if "c" in key.lower():
                    programme = "contour" if programme == "grand-tour" else "grand-tour"
                terminal = shutil.get_terminal_size((100, 32))
                columns = max(20, args.columns or terminal.columns)
                total_rows = max(8, args.rows or terminal.lines)
                status_rows = 0 if args.no_status else 1
                graphic_rows = total_rows-status_rows
                # Keep scene objects separate until the terminal-cell encode.
                # This preserves a sparse, near spacecraft edge as the cell
                # foreground while retaining a planet or ring behind it as the
                # cell background.  The legacy one-colour renderer remains in
                # place for backwards-compatible VGR v1 capture/playback.
                encounter, _, cell_frame, _, _ = render_layered_frame(
                    sys.modules[__name__], mesh, args.mode, columns,
                    graphic_rows, elapsed, programme, style, hidden_lines,
                    args.depth_scale)
                picture = terminal_picture_v2(cell_frame, args.mode)
                if args.no_status:
                    output = "\x1b[H"+picture
                else:
                    header = status_line(columns, args.mode, encounter, programme,
                                         style, hidden_lines, fps_actual, elapsed)
                    output = "\x1b[H"+header+"\n"+picture
                if last_size != (columns, total_rows):
                    output = "\x1b[2J"+output
                    last_size = (columns, total_rows)
                sys.stdout.write(output)
                sys.stdout.flush()
                last_output = "\x1b[0m\x1b[2J\x1b[H"+output.removeprefix("\x1b[H")+"\x1b[0m\n"
                frame_count += 1
                recent_frames += 1
                span = now-recent_started
                if span >= 1.0:
                    fps_actual = recent_frames/span
                    recent_frames = 0
                    recent_started = now
                if args.freeze_at is not None:
                    if args.capture:
                        break
                    if now-started >= args.hold:
                        break
                next_frame += 1.0/args.fps
                delay = next_frame-time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1.0/args.fps:
                    next_frame = time.monotonic()
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
    if args.capture and last_output:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_text(last_output, encoding="utf-8")
        print(f"Captured: {args.capture}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # The Linux profile launcher naturally supplies the mode first.  Accept
    # both "capture -4" and "-4 capture" (likewise for play).
    if len(argv) >= 2 and argv[0] in ("-2", "-4") and argv[1] in ("capture", "play"):
        argv = [argv[1], argv[0], *argv[2:]]
    if argv and argv[0] == "capture":
        return capture_main(parse_capture_args(argv[1:]))
    if argv and argv[0] == "play":
        return play_main(parse_play_args(argv[1:]))
    return live_main(parse_live_args(argv))


if __name__ == "__main__":
    main()
