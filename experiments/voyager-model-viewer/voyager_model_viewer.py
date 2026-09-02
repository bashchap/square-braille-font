#!/usr/bin/env python3
"""Interactive NASA Voyager model viewer rendered with the PUA 4x4 font."""

from __future__ import annotations

import argparse
import math
import os
import re
import select
import shutil
import signal
import sys
import termios
import time
import tty
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
VOYAGER_DIR = HERE.parent / "voyager-grand-tour"
sys.path.insert(0, str(VOYAGER_DIR))

from voyager_core import MATERIAL_COLORS, normalize, raster_depth, terminal_picture
from voyager_grand_tour import camera_basis, encode_frame, load_mesh
from voyager_recording import VGRWriter


TITLE = "PUA 4x4 MODEL SPACE VIEWER"
DEFAULT_MESH = VOYAGER_DIR / "assets" / "voyager-vtad-hlr.npz"

# The encoder treats every non-zero RGB component as a set virtual pixel.
# Therefore both the page background and panel interior must be true zero;
# visual depth comes from outlines, grids, labels and data rather than a tinted
# fill that would incorrectly select every bit in every PUA 4x4 glyph.
BLACK = (0, 0, 0)
SURFACE = (0, 0, 0)
CYAN = (77, 232, 255)
CYAN_DIM = (29, 116, 143)
GRID = (13, 66, 83)
GRID_FAINT = (8, 40, 53)
AMBER = (255, 179, 46)
WHITE = (203, 246, 255)
MUTED = (104, 171, 189)
RED = (255, 103, 95)
GREEN = (104, 229, 164)
BLUE = (94, 166, 255)
HUD_SCALE = 2.0

ARROW_RE = re.compile(r"\x1b\[(?:1;([2-8]))?([ABCD])")
ARROW_NAMES = {"A": "up", "B": "down", "C": "right", "D": "left"}


def rotation_matrix(angles):
    """Return an XYZ Euler matrix for row-vector geometry."""
    x, y, z = angles
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    rx = np.array(((1, 0, 0), (0, cx, -sx), (0, sx, cx)))
    ry = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)))
    rz = np.array(((cz, -sz, 0), (sz, cz, 0), (0, 0, 1)))
    return rz @ ry @ rx


def decode_arrow(sequence):
    """Decode xterm/MATE arrow sequences and Shift/Alt/Ctrl modifiers."""
    match = ARROW_RE.fullmatch(sequence)
    if match is None:
        return None
    modifier = int(match.group(1) or 1)-1
    return {
        "direction": ARROW_NAMES[match.group(2)],
        "shift": bool(modifier & 1),
        "alt": bool(modifier & 2),
        "ctrl": bool(modifier & 4),
    }


def format_vector(vector):
    return " ".join(f"{value:+.3f}" for value in vector)


def format_angle(value):
    degrees = math.degrees(value)
    return f"{degrees:+06.1f}°"


def clamp(value, low, high):
    return min(high, max(low, value))


def hud_base(width):
    """Return the default two-times HUD text scale for this framebuffer."""
    return clamp(width/145, 8, 13)*HUD_SCALE


@dataclass
class ViewerState:
    eye: np.ndarray = field(default_factory=lambda: np.array((1.18, -1.52, .76), dtype=float))
    target: np.ndarray = field(default_factory=lambda: np.array((0., -.06, -.06), dtype=float))
    roll: float = 0.0
    camera_mode: str = "orbit"
    model_position: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    model_angles: np.ndarray = field(default_factory=lambda: np.radians((18., -31., 7.)))
    angular_velocity: np.ndarray = field(default_factory=lambda: np.radians((12., -18., 8.)))
    rotating: bool = False
    style: str = "wire"
    hidden_lines: bool = True
    grid_mode: int = 3
    show_camera_panel: bool = True
    show_model_panel: bool = True
    page: int = 0
    pages: int = 3
    quit_requested: bool = False
    recording_active: bool = False
    recording_frames: int = 0
    recording_path: str = ""
    record_toggle_requested: bool = False
    message: str = "READY"

    def reset_camera(self):
        self.eye[:] = (1.18, -1.52, .76)
        self.target[:] = (0., -.06, -.06)
        self.roll = 0.0
        self.message = "CAMERA FRAMED TO MODEL"

    def camera_distance(self):
        return float(np.linalg.norm(self.eye-self.target))

    def dolly(self, direction, model_radius):
        """Move toward/away from the target without requiring Ctrl keys."""
        right, up, forward = camera_basis(self.eye, self.target, self.roll)
        del right, up
        distance = self.camera_distance()
        amount = max(model_radius*.05, distance*.06)*direction
        if self.camera_mode == "orbit":
            new_distance = clamp(distance-amount, model_radius*.72,
                                 model_radius*12)
            self.eye[:] = self.target-forward*new_distance
        else:
            self.eye[:] += forward*amount
            self.target[:] += forward*amount
        self.message = f"DOLLY {'IN' if direction > 0 else 'OUT'} · {self.camera_distance():.3f}"

    def focus_model(self, model_radius):
        """Centre the model and move to a close inspection distance."""
        forward = normalize(self.target-self.eye)
        self.target[:] = self.model_position
        self.eye[:] = self.model_position-forward*(model_radius*1.38)
        self.message = "MODEL CENTRED · CLOSE INSPECTION"

    def step_rotation(self, seconds):
        if self.rotating:
            self.model_angles[:] = (self.model_angles +
                                    self.angular_velocity*seconds)
            self.model_angles[:] = (self.model_angles+math.pi) % math.tau-math.pi

    def stop_for_input(self):
        if self.rotating:
            self.rotating = False
            self.message = "ROTATION PAUSED BY INPUT"

    def apply_arrow(self, arrow, model_radius):
        self.stop_for_input()
        direction = arrow["direction"]
        sign = 1 if direction in ("right", "up") else -1
        rate_step = math.radians(2.0)
        if arrow["alt"]:
            if arrow["shift"] and direction in ("left", "right"):
                self.angular_velocity[2] += sign*rate_step
                axis = "Z"
            elif direction in ("left", "right"):
                self.angular_velocity[1] += sign*rate_step
                axis = "Y"
            else:
                self.angular_velocity[0] += sign*rate_step
                axis = "X"
            self.message = (f"MODEL ω{axis} "
                            f"{math.degrees(self.angular_velocity['XYZ'.index(axis)]):+.1f}°/S")
            return

        if arrow["ctrl"]:
            self.message = "CTRL COMBINATIONS ARE RESERVED"
            return

        basis = camera_basis(self.eye, self.target, self.roll)
        right, up, forward = basis
        distance = self.camera_distance()
        translation = max(model_radius*.025, distance*.025)
        if arrow["shift"]:
            vector = right*sign if direction in ("left", "right") else up*sign
            self.eye[:] += vector*translation
            self.target[:] += vector*translation
            self.message = f"CAMERA STRAFE {direction.upper()}"
            return

        if self.camera_mode == "orbit":
            relative = self.eye-self.target
            radius = max(float(np.linalg.norm(relative)), 1e-6)
            azimuth = math.atan2(relative[1], relative[0])
            elevation = math.asin(clamp(relative[2]/radius, -1, 1))
            if direction in ("left", "right"):
                azimuth += sign*math.radians(2.5)
            else:
                elevation = clamp(elevation+sign*math.radians(2.5),
                                  math.radians(-87), math.radians(87))
            self.eye[:] = self.target + radius*np.array((
                math.cos(elevation)*math.cos(azimuth),
                math.cos(elevation)*math.sin(azimuth),
                math.sin(elevation)))
            self.message = f"ORBIT {direction.upper()}"
        else:
            forward = normalize(self.target-self.eye)
            azimuth = math.atan2(forward[1], forward[0])
            elevation = math.asin(clamp(forward[2], -1, 1))
            if direction in ("left", "right"):
                azimuth += sign*math.radians(2.5)
            else:
                elevation = clamp(elevation+sign*math.radians(2.5),
                                  math.radians(-87), math.radians(87))
            new_forward = np.array((math.cos(elevation)*math.cos(azimuth),
                                    math.cos(elevation)*math.sin(azimuth),
                                    math.sin(elevation)))
            self.target[:] = self.eye+new_forward*distance
            self.message = f"FREE LOOK {direction.upper()}"

    def handle_key(self, key, model_radius):
        arrow = decode_arrow(key)
        if arrow is not None:
            self.apply_arrow(arrow, model_radius)
            return True
        if key in ("q", "Q", "\x1b"):
            self.quit_requested = True
            return True
        if key == " ":
            self.rotating = not self.rotating
            self.message = "ROTATION LOOP RUNNING" if self.rotating else "ROTATION LOOP PAUSED"
            return True
        if key.lower() == "c":
            self.record_toggle_requested = True
            self.message = "RECORDING CONTROL REQUESTED"
            return True
        if not key:
            return False
        self.stop_for_input()
        lower = key.lower()
        if key == "\t":
            self.page = (self.page+1) % self.pages
            self.message = f"PAGE {self.page+1}/{self.pages}"
        elif lower == "g":
            self.grid_mode = (self.grid_mode+1) % 4
            self.message = ("GRID OFF", "GRID FLOOR", "GRID FLOOR + VERTICAL",
                            "GRID XYZ + DEPTH")[self.grid_mode]
        elif lower == "h":
            self.hidden_lines = not self.hidden_lines
            self.message = f"HIDDEN LINE REMOVAL {'ON' if self.hidden_lines else 'OFF'}"
        elif lower == "f":
            self.style = "filled" if self.style == "wire" else "wire"
            self.message = f"STYLE {self.style.upper()}"
        elif lower == "m":
            self.camera_mode = "free" if self.camera_mode == "orbit" else "orbit"
            self.message = f"CAMERA MODE {self.camera_mode.upper()}"
        elif key in ("+", "="):
            self.dolly(1, model_radius)
        elif key in ("-", "_"):
            self.dolly(-1, model_radius)
        elif key == "[":
            self.roll -= math.radians(2.0)
            self.message = f"CAMERA ROLL {format_angle(self.roll)}"
        elif key == "]":
            self.roll += math.radians(2.0)
            self.message = f"CAMERA ROLL {format_angle(self.roll)}"
        elif lower == "z":
            self.focus_model(model_radius)
        elif key == "1":
            self.show_camera_panel = not self.show_camera_panel
            self.message = f"CAMERA PANEL {'ON' if self.show_camera_panel else 'OFF'}"
        elif key == "2":
            self.show_model_panel = not self.show_model_panel
            self.message = f"MODEL PANEL {'ON' if self.show_model_panel else 'OFF'}"
        elif lower in ("0", "r") or key in ("\x1b[H", "\x1b[1~"):
            self.reset_camera()
        elif lower == "x":
            self.model_angles[:] = 0
            self.angular_velocity[:] = 0
            self.message = "MODEL TRANSFORM RESET"
        else:
            return False
        return True


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
        if not ready:
            return ""
        first = os.read(self.fd, 64).decode("utf-8", "ignore")
        # Escape sequences can arrive split across reads.  Give the terminal a
        # tiny opportunity to deliver the remainder without delaying frames.
        if first == "\x1b":
            ready, _, _ = select.select([self.fd], [], [], .004)
            if ready:
                first += os.read(self.fd, 64).decode("utf-8", "ignore")
        return first

    def __exit__(self, *unused):
        if self.fd is not None and self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)


def project_points(points, eye, target, roll, mode, width, height, fov=53):
    basis = camera_basis(eye, target, roll)
    camera_points = (points-eye) @ basis.T
    z = camera_points[:, 2]
    safe = np.maximum(z, .012)
    focal_y = height/(2*math.tan(math.radians(fov)/2))
    focal_x = focal_y*(mode/2)
    projected = np.empty((len(points), 2), dtype=np.float32)
    projected[:, 0] = width*.5+camera_points[:, 0]*focal_x/safe
    projected[:, 1] = height*.5-camera_points[:, 1]*focal_y/safe
    return projected, z


def draw_line(rgb, p0, p1, color, opacity=1.0):
    height, width, _ = rgb.shape
    delta = np.asarray(p1)-np.asarray(p0)
    steps = max(1, int(math.ceil(float(np.max(np.abs(delta))))))
    color = np.asarray(color, dtype=float)*opacity
    for index in range(steps+1):
        x, y = np.rint(np.asarray(p0)+delta*index/steps).astype(int)
        if 0 <= x < width and 0 <= y < height:
            rgb[y, x] = np.maximum(rgb[y, x], color).astype(np.uint8)


def draw_world_line(rgb, a, b, state, mode, color, opacity=.45):
    projected, z = project_points(np.asarray((a, b), dtype=float), state.eye,
                                  state.target, state.roll, mode,
                                  rgb.shape[1], rgb.shape[0])
    if np.all(z > .012):
        draw_line(rgb, projected[0], projected[1], color, opacity)


def draw_grids(rgb, state, mode, radius):
    if state.grid_mode == 0:
        return
    extent = radius*4.2
    step = extent/8
    floor_z = -radius*.70
    for index in range(-8, 9):
        value = index*step
        draw_world_line(rgb, (-extent, value, floor_z),
                        (extent, value, floor_z), state, mode, GRID,
                        .72 if index == 0 else .38)
        draw_world_line(rgb, (value, -extent, floor_z),
                        (value, extent, floor_z), state, mode, GRID,
                        .72 if index == 0 else .38)
    if state.grid_mode >= 2:
        back_y = radius*1.65
        for index in range(-8, 9):
            value = index*step
            draw_world_line(rgb, (-extent, back_y, value),
                            (extent, back_y, value), state, mode, GRID_FAINT, .55)
            draw_world_line(rgb, (value, back_y, -extent),
                            (value, back_y, extent), state, mode, GRID_FAINT, .55)
    if state.grid_mode >= 3:
        side_x = -radius*1.65
        for index in range(-8, 9):
            value = index*step
            draw_world_line(rgb, (side_x, -extent, value),
                            (side_x, extent, value), state, mode, GRID_FAINT, .42)
            draw_world_line(rgb, (side_x, value, -extent),
                            (side_x, value, extent), state, mode, GRID_FAINT, .42)


def line_depth_tested(rgb, depth, p0, p1, z0, z1, color, depth_scale,
                      hidden_lines, tolerance=.023):
    height, width, _ = rgb.shape
    delta = p1-p0
    steps = max(1, int(math.ceil(float(np.max(np.abs(delta))))))
    inverse0, inverse1 = 1.0/z0, 1.0/z1
    last = None
    for step in range(steps+1):
        amount = step/steps
        x, y = np.rint(p0+delta*amount).astype(int)
        if not (0 <= x < width and 0 <= y < height):
            continue
        if hidden_lines:
            inverse = inverse0+(inverse1-inverse0)*amount
            sample = depth[min(depth.shape[0]-1, y//depth_scale),
                           min(depth.shape[1]-1, x//depth_scale)]
            if inverse+tolerance*max(inverse, sample) < sample:
                last = None
                continue
        rgb[y, x] = color
        if last is not None and x != last[0] and y != last[1]:
            if abs(delta[0]) >= abs(delta[1]):
                rgb[last[1], x] = color
            else:
                rgb[y, last[0]] = color
        last = (x, y)


def render_model(mesh, rgb, state, mode, depth_scale, draw_axes=True):
    rotation = rotation_matrix(state.model_angles)
    vertices = mesh["vertices"] @ rotation.T + state.model_position
    normals = mesh["normals"] @ rotation.T
    centers = mesh["centers"] @ rotation.T + state.model_position
    projected, z = project_points(vertices, state.eye, state.target, state.roll,
                                  mode, rgb.shape[1], rgb.shape[0])
    ds = max(1, depth_scale)
    depth = np.zeros(((rgb.shape[0]+ds-1)//ds,
                      (rgb.shape[1]+ds-1)//ds), dtype=np.float32)
    tri_z = z[mesh["faces"]]
    tri_p = projected[mesh["faces"]]/ds
    area = np.abs((tri_p[:, 1, 0]-tri_p[:, 0, 0])*(tri_p[:, 2, 1]-tri_p[:, 0, 1])-
                  (tri_p[:, 1, 1]-tri_p[:, 0, 1])*(tri_p[:, 2, 0]-tri_p[:, 0, 0]))
    valid = np.all(tri_z > .012, axis=1) & (area >= .012)
    valid &= np.max(tri_p[:, :, 0], axis=1) >= -1
    valid &= np.min(tri_p[:, :, 0], axis=1) <= depth.shape[1]
    valid &= np.max(tri_p[:, :, 1], axis=1) >= -1
    valid &= np.min(tri_p[:, :, 1], axis=1) <= depth.shape[0]
    face_indices = np.flatnonzero(valid)
    surface = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if state.hidden_lines or state.style == "filled":
        light = normalize(np.array((-.35, -.3, 1.0)))
        for index in face_indices[np.argsort(-area[face_indices])]:
            color = None
            if state.style == "filled":
                material = int(mesh["materials"][index])
                base = MATERIAL_COLORS[material % len(MATERIAL_COLORS)].astype(float)
                diffuse = abs(float(np.dot(normals[index], light)))
                color = np.clip(base*(.25+.75*diffuse), 0, 255).astype(np.uint8)
            raster_depth(depth, tri_p[index], tri_z[index],
                         surface if color is not None else None, color)
    if state.style == "filled":
        expanded = np.repeat(np.repeat(surface, ds, axis=0), ds, axis=1)
        expanded = expanded[:rgb.shape[0], :rgb.shape[1]]
        occupied = np.any(expanded != 0, axis=2)
        rgb[occupied] = expanded[occupied]

    facing = np.sum(normals*(state.eye-centers), axis=1)
    paired = mesh["face1"] >= 0
    second = np.zeros(len(mesh["edges"]), dtype=float)
    second[paired] = facing[mesh["face1"][paired]]*np.where(
        mesh["normal_dot"][paired] < 0, -1., 1.)
    silhouette = paired & (facing[mesh["face0"]]*second <= 0)
    selected = ((silhouette | (mesh["face1"] < 0)) if state.style == "filled"
                else (mesh["crease"] | silhouette))
    edge_z = z[mesh["edges"]]
    selected &= np.all(edge_z > .012, axis=1)
    edge_p = projected[mesh["edges"]]
    selected &= np.max(edge_p[:, :, 0], axis=1) >= -2
    selected &= np.min(edge_p[:, :, 0], axis=1) <= rgb.shape[1]+1
    selected &= np.max(edge_p[:, :, 1], axis=1) >= -2
    selected &= np.min(edge_p[:, :, 1], axis=1) <= rgb.shape[0]+1
    selected &= np.max(np.abs(edge_p[:, 1]-edge_p[:, 0]), axis=1) >= .55
    edge_indices = np.flatnonzero(selected)
    edge_indices = edge_indices[np.argsort(-edge_z[edge_indices].mean(1))]
    for index in edge_indices:
        owner = mesh["face0"][index]
        material = int(mesh["materials"][owner])
        color = (np.array(WHITE, dtype=np.uint8) if state.style == "filled"
                 else MATERIAL_COLORS[material % len(MATERIAL_COLORS)])
        line_depth_tested(rgb, depth, edge_p[index, 0], edge_p[index, 1],
                          edge_z[index, 0], edge_z[index, 1], color, ds,
                          state.hidden_lines or state.style == "filled")

    if draw_axes:
        axis_length = float(np.linalg.norm(np.ptp(mesh["vertices"], axis=0)))*.62
        origin = state.model_position
        for endpoint, color in ((origin+rotation @ np.array((axis_length, 0, 0)), RED),
                                (origin+rotation @ np.array((0, axis_length, 0)), GREEN),
                                (origin+rotation @ np.array((0, 0, axis_length)), BLUE)):
            draw_world_line(rgb, origin, endpoint, state, mode, color, .95)
    return len(face_indices), len(edge_indices)


def render_scene(mesh, state, mode, width, height, depth_scale, model_radius,
                 draw_axes=True):
    rgb = np.zeros((max(1, height), max(1, width), 3), dtype=np.uint8)
    draw_grids(rgb, state, mode, model_radius)
    faces, edges = render_model(mesh, rgb, state, mode, depth_scale, draw_axes)
    return rgb, faces, edges


class PuaGui:
    """Draw scalable HUD text into the virtual-pixel framebuffer."""

    FONT_PATHS = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSansMono.ttf"),
        Path("/Library/Fonts/DejaVuSansMono.ttf"),
    )

    def __init__(self, width, height):
        self.image = Image.new("RGB", (width, height), BLACK)
        self.draw = ImageDraw.Draw(self.image)
        self.width = width
        self.height = height
        self._fonts = {}

    def font(self, size):
        size = max(7, int(size))
        if size not in self._fonts:
            override = os.environ.get("VOYAGER_VIEWER_HUD_FONT")
            candidates = ([Path(override)] if override else [])+list(self.FONT_PATHS)
            for path in candidates:
                if path and path.exists():
                    self._fonts[size] = ImageFont.truetype(str(path), size)
                    break
            else:
                self._fonts[size] = ImageFont.load_default(size=size)
        return self._fonts[size]

    def text(self, xy, value, color=WHITE, size=11, anchor=None):
        self.draw.text(xy, str(value), font=self.font(size), fill=color,
                       anchor=anchor)

    def scaled_text(self, xy, value, color=WHITE, base_size=10, scale=1.0,
                    anchor=None):
        """Draw text at a programmable scale before PUA 4x4 encoding."""
        self.text(xy, value, color, max(7, round(base_size*scale)), anchor)

    def panel(self, box, title, size=10):
        self.draw.rectangle(box, fill=SURFACE, outline=CYAN_DIM, width=1)
        x0, y0, x1, _ = box
        self.text((x0+7, y0+4), title, CYAN, size)
        self.draw.line((x0+5, y0+size+9, x1-5, y0+size+9), fill=CYAN_DIM)

    def paste_scene(self, scene, box):
        x0, y0, x1, y1 = box
        target = Image.fromarray(scene, "RGB")
        self.image.paste(target, (x0, y0))
        self.draw.rectangle(box, outline=CYAN_DIM, width=1)

    def field(self, x, y, label, value, width, size=9, value_color=WHITE):
        self.text((x, y), label, MUTED, size)
        self.text((x+width, y), value, value_color, size, "ra")

    def array(self):
        return np.asarray(self.image, dtype=np.uint8)


def draw_compass(gui, box, state, size):
    x0, y0, x1, y1 = box
    cx, cy = (x0+x1)//2, (y0+y1)//2
    radius = max(8, min(x1-x0, y1-y0)//2-4)
    gui.draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                     outline=CYAN_DIM)
    gui.draw.ellipse((cx-radius, cy-radius//3, cx+radius, cy+radius//3),
                     outline=GRID)
    gui.draw.line((cx-radius, cy, cx+radius, cy), fill=GRID)
    gui.draw.line((cx, cy-radius, cx, cy+radius), fill=GRID)
    forward = normalize(state.target-state.eye)
    endpoint = (cx+int(forward[0]*radius), cy-int(forward[2]*radius))
    gui.draw.line((cx, cy, *endpoint), fill=AMBER, width=max(1, size//8))
    gui.text((cx+radius-3, cy), "X", RED, size, "rm")
    gui.text((cx, cy-radius+2), "Z", BLUE, size, "ma")


def render_view_page(gui, mesh, state, mode, depth_scale, model_radius,
                     render_ms, fps, full_layout):
    width, height = gui.width, gui.height
    base = hud_base(width)
    if height < 140:
        header = max(22, round(base+7))
        footer = 0
    else:
        header = max(36, round(base*2.2))
        footer = max(62, round(base*3.5))
    gui.draw.rectangle((0, 0, width-1, height-1), outline=CYAN_DIM)
    gui.scaled_text((12, 5), "NASA MODEL · VOYAGER 2", CYAN, base, 1.0)
    gui.scaled_text((width//2, 4), TITLE, CYAN, base, 1.35, "ma")
    page_status = f"PAGE 1/{state.pages} · TAB"
    if state.recording_active:
        page_status = f"● REC {state.recording_frames:06d} · "+page_status
    gui.text((width-12, 6), page_status,
             RED if state.recording_active else AMBER, base, "ra")
    gui.draw.line((8, header, width-9, header), fill=CYAN_DIM)

    if full_layout:
        left = max(270, round(width*.235)) if state.show_camera_panel else 0
        right = max(290, round(width*.245)) if state.show_model_panel else 0
        view_box = ((left+8) if left else 8, header+8,
                    (width-right-9) if right else width-9, height-footer-8)
        if left:
            left_box = (8, header+8, left, height-footer-8)
            gui.panel(left_box, "CAMERA / VIEW VECTOR · [1]", round(base))
            compass_h = min(100, (left_box[3]-left_box[1])//3)
            draw_compass(gui, (left_box[0]+12, left_box[1]+base+16,
                               left_box[2]-12, left_box[1]+base+16+compass_h),
                         state, round(base))
            y = left_box[1]+base+20+compass_h
            field_width = left_box[2]-left_box[0]-16
            for label, value, color in (
                ("MODE", state.camera_mode.upper(), WHITE),
                ("POSITION", format_vector(state.eye), AMBER),
                ("TARGET", format_vector(state.target), WHITE),
                ("DISTANCE", f"{state.camera_distance():.3f}", WHITE),
                ("GRID", ("OFF", "FLOOR", "FLOOR + VERTICAL", "XYZ + DEPTH")[state.grid_mode], WHITE),
            ):
                gui.field(left_box[0]+8, y, label, value, field_width,
                          round(base*.82), color)
                y += round(base*1.42)

        if right:
            right_box = (width-right, header+8, width-9, height-footer-8)
            gui.panel(right_box, "MODEL TRANSFORM / ROTATION · [2]", round(base))
            y = right_box[1]+base+20
            fw = right_box[2]-right_box[0]-16
            for label, value, color in (
                ("ANGLE X", format_angle(state.model_angles[0]), RED),
                ("ANGLE Y", format_angle(state.model_angles[1]), GREEN),
                ("ANGLE Z", format_angle(state.model_angles[2]), BLUE),
                ("ωX", f"{math.degrees(state.angular_velocity[0]):+.1f}°/S", RED),
                ("ωY", f"{math.degrees(state.angular_velocity[1]):+.1f}°/S", GREEN),
                ("ωZ", f"{math.degrees(state.angular_velocity[2]):+.1f}°/S", BLUE),
                ("LOOP", "RUNNING" if state.rotating else "PAUSED", AMBER),
                ("STYLE", state.style.upper(), WHITE),
                ("HLR", "ON" if state.hidden_lines else "OFF", WHITE),
            ):
                gui.field(right_box[0]+8, y, label, value, fw,
                          round(base*.82), color)
                y += round(base*1.34)
    else:
        view_box = (8, header+8, width-9, height-footer-8)

    scene_width = max(1, view_box[2]-view_box[0])
    scene_height = max(1, view_box[3]-view_box[1])
    scene, faces, edges = render_scene(mesh, state, mode, scene_width,
                                       scene_height, depth_scale, model_radius)
    gui.paste_scene(scene, view_box)
    gui.text((view_box[0]+7, view_box[1]+5),
             f"{state.style.upper()} + HLR {'ON' if state.hidden_lines else 'OFF'} · GRID {state.grid_mode}",
             CYAN, round(base*.82))
    gui.text((view_box[0]+7, view_box[3]-base-5), state.message,
             AMBER, round(base*.78))
    gui.text((view_box[2]-7, view_box[3]-base-5),
             f"FACES {faces:,} · EDGES {edges:,}", MUTED,
             round(base*.78), "ra")
    if footer:
        gui.draw.rectangle((8, height-footer+1, width-9, height-8),
                           fill=SURFACE, outline=CYAN_DIM)
        help_text = ("ARROWS ORBIT · SHIFT+ARROWS STRAFE · +/- DOLLY · [/] ROLL · "
                     "ALT+ARROWS MODEL X/Y · ALT+SHIFT+←→ MODEL Z")
        gui.text((16, height-footer+8), help_text, WHITE, round(base*.66))
        gui.text((16, height-footer+8+round(base*1.35)),
                 "1 CAMERA PANEL · 2 MODEL PANEL · Z CENTRE/ZOOM · C RECORD · SPACE ROTATE · TAB DETAILS · G GRID · Q QUIT",
                 MUTED, round(base*.66))
    return faces, edges


def render_details_page(gui, mesh, state, mode, depth_scale, model_radius,
                        render_ms, fps, terminal_cells, full_layout):
    width, height = gui.width, gui.height
    base = hud_base(width)
    header = max(24, round(base*2.2))
    gui.draw.rectangle((0, 0, width-1, height-1), outline=CYAN_DIM)
    gui.text((12, 6), "VOYAGER MODEL VIEWER · TELEMETRY / CONTROLS", CYAN,
             round(base*1.15))
    gui.text((width-12, 6), f"PAGE 2/{state.pages} · TAB", AMBER, round(base), "ra")
    gui.draw.line((8, header, width-9, header), fill=CYAN_DIM)
    gap = 8
    column = (width-gap*3)//2
    mid_y = header+(height-header)//2
    if not full_layout:
        compact_base = min(base, max(8, (height-header-24)/7))
        boxes = (
            (gap, header+gap, gap+column, height-gap),
            (gap*2+column, header+gap, width-gap, height-gap),
        )
        for box, title in zip(boxes, ("CAMERA / VIEW", "MODEL / RENDER")):
            gui.panel(box, title, round(compact_base))
        line_h = max(9, round(compact_base*1.35))
        size = max(7, round(compact_base*.74))
        basis = camera_basis(state.eye, state.target, state.roll)
        camera_rows = (
            ("MODE", state.camera_mode.upper()),
            ("EYE", format_vector(state.eye)),
            ("TARGET", format_vector(state.target)),
            ("FORWARD", format_vector(basis[2])),
            ("ROLL", format_angle(state.roll)),
            ("DISTANCE", f"{state.camera_distance():.4f}"),
        )
        model_rows = (
            ("NASA MESH", f"{len(mesh['vertices']):,} V / {len(mesh['faces']):,} F"),
            ("ANGLES", " ".join(format_angle(v) for v in state.model_angles)),
            ("ω XYZ", " ".join(f"{math.degrees(v):+.1f}" for v in state.angular_velocity)),
            ("RENDER", f"{state.style.upper()} HLR {'ON' if state.hidden_lines else 'OFF'}"),
            ("FRAME", f"{terminal_cells[0]*4}×{terminal_cells[1]*4} PX"),
            ("PERF", f"{render_ms:.1f} MS / {fps:.1f} FPS"),
        )
        for box, rows_data in zip(boxes, (camera_rows, model_rows)):
            y = box[1]+compact_base+16
            field_width = box[2]-box[0]-12
            for label, value in rows_data:
                gui.field(box[0]+6, y, label, value, field_width, size,
                          AMBER if label in ("EYE", "NASA MESH", "FRAME") else WHITE)
                y += line_h
        return
    panel_width = (width-gap*4)//3
    boxes = tuple(
        (gap+(panel_width+gap)*index, header+gap,
         gap+(panel_width+gap)*index+panel_width, height-gap)
        for index in range(3)
    )
    titles = ("CAMERA MATRIX / VIEW", "MODEL / MESH",
              "RENDER / FRAMEBUFFER")
    for box, title in zip(boxes, titles):
        gui.panel(box, title, round(base))
    line_h = round(base*1.28)
    size = round(base*.76)

    basis = camera_basis(state.eye, state.target, state.roll)
    camera_rows = [
        ("MODE", state.camera_mode.upper()),
        ("EYE", format_vector(state.eye)),
        ("TARGET", format_vector(state.target)),
        ("RIGHT", format_vector(basis[0])),
        ("UP", format_vector(basis[1])),
        ("FORWARD", format_vector(basis[2])),
        ("ROLL", format_angle(state.roll)),
        ("DISTANCE", f"{state.camera_distance():.4f}"),
    ]
    y = boxes[0][1]+base+18
    fw = boxes[0][2]-boxes[0][0]-16
    for label, value in camera_rows:
        gui.field(boxes[0][0]+8, y, label, value, fw, size,
                  AMBER if label in ("EYE", "TARGET") else WHITE)
        y += line_h

    vertices, faces = mesh["vertices"], mesh["faces"]
    extents = vertices.max(axis=0)-vertices.min(axis=0)
    model_rows = [
        ("SOURCE", "NASA VTAD VOYAGER"),
        ("VERTICES", f"{len(vertices):,}"),
        ("TRIANGLES", f"{len(faces):,}"),
        ("EDGES", f"{len(mesh['edges']):,}"),
        ("EXTENTS", format_vector(extents)),
        ("POSITION", format_vector(state.model_position)),
        ("ANGLES", " ".join(format_angle(v) for v in state.model_angles)),
        ("ANGULAR VELOCITY", " ".join(f"{math.degrees(v):+.1f}" for v in state.angular_velocity)),
        ("LOOP", "RUNNING" if state.rotating else "PAUSED"),
    ]
    y = boxes[1][1]+base+18
    fw = boxes[1][2]-boxes[1][0]-16
    for label, value in model_rows:
        gui.field(boxes[1][0]+8, y, label, value, fw, size,
                  AMBER if label in ("SOURCE", "LOOP") else WHITE)
        y += line_h

    columns, rows = terminal_cells
    render_rows = [
        ("TERMINAL", f"{columns} × {rows} CELLS"),
        ("VIRTUAL", f"{columns*4} × {rows*4} PIXELS"),
        ("STYLE", state.style.upper()),
        ("HIDDEN LINES", "ON" if state.hidden_lines else "OFF"),
        ("DEPTH SCALE", str(depth_scale)),
        ("GRID PLANES", str(state.grid_mode)),
        ("LAST RENDER", f"{render_ms:.2f} MS"),
        ("VIEW RATE", f"{fps:.2f} FPS"),
        ("RESIZE", "LIVE / FULL REPROJECT"),
        ("RECORDING", (f"ACTIVE · {state.recording_frames:,} FRAMES"
                       if state.recording_active else "IDLE")),
    ]
    y = boxes[2][1]+base+18
    fw = boxes[2][2]-boxes[2][0]-16
    for label, value in render_rows:
        gui.field(boxes[2][0]+8, y, label, value, fw, size,
                  AMBER if label in ("VIRTUAL", "RESIZE") else WHITE)
        y += line_h

def render_controls_page(gui, state, terminal_cells):
    width, height = gui.width, gui.height
    base = hud_base(width)
    header = max(22, round(base+7)) if height < 140 else max(36, round(base*2.2))
    gui.draw.rectangle((0, 0, width-1, height-1), outline=CYAN_DIM)
    gui.text((12, 6), "VOYAGER MODEL VIEWER · NAVIGATION REFERENCE", CYAN,
             round(base*1.08))
    gui.text((width-12, 6), f"PAGE 3/{state.pages} · TAB", AMBER,
             round(base), "ra")
    gui.draw.line((8, header, width-9, header), fill=CYAN_DIM)
    gap = 8
    column = (width-gap*3)//2
    left = (gap, header+gap, gap+column, height-gap)
    right = (gap*2+column, header+gap, width-gap, height-gap)
    gui.panel(left, "CAMERA / DISPLAY", round(base))
    gui.panel(right, "MODEL / SESSION", round(base))
    size = max(7, round(base*.78))
    line_h = max(9, round(base*1.46))
    groups = (
        (
            "ARROWS             ORBIT / FREE LOOK",
            "SHIFT + ARROWS     STRAFE X / Y",
            "+ / -              DOLLY IN / OUT",
            "[ / ]              CAMERA ROLL",
            "M                  ORBIT / FREE MODE",
            "HOME / 0 / R       FRAME CAMERA",
            "G                  CYCLE 3-D GRIDS",
            "H                  HIDDEN LINES",
        ),
        (
            "ALT + UP/DOWN      MODEL ωX",
            "ALT + LEFT/RIGHT   MODEL ωY",
            "ALT+SHIFT+LEFT/RIGHT MODEL ωZ",
            "SPACE              START / STOP LOOP",
            "C                  START / STOP RECORDING",
            "F                  WIRE / FILLED",
            "1 / 2              TOGGLE SIDE PANELS",
            "Z                  CENTRE / CLOSE ZOOM",
            "X                  RESET MODEL",
            "TAB                NEXT PAGE",
            "Q / ESC            QUIT",
        ),
    )
    for box, controls in zip((left, right), groups):
        y = box[1]+base+18
        for control in controls:
            gui.text((box[0]+7, y), control,
                     AMBER if control.startswith(("SPACE", "TAB")) else WHITE,
                     size)
            y += line_h
    gui.text((width//2, height-4),
             f"CURRENT {terminal_cells[0]}×{terminal_cells[1]} CELLS · "
             f"{terminal_cells[0]*4}×{terminal_cells[1]*4} VIRTUAL PIXELS · "
             "RESIZE CAUSES FULL REPROJECT",
             MUTED, size, "ms")


def render_gui(mesh, state, columns, rows, depth_scale, model_radius,
               render_ms=0.0, fps=0.0):
    width, height = columns*4, rows*4
    gui = PuaGui(width, height)
    full_layout = columns >= 155 and rows >= 42
    if state.page == 0:
        render_view_page(gui, mesh, state, 4, depth_scale, model_radius,
                         render_ms, fps, full_layout)
    elif state.page == 1:
        render_details_page(gui, mesh, state, 4, depth_scale, model_radius,
                            render_ms, fps, (columns, rows), full_layout)
    else:
        render_controls_page(gui, state, (columns, rows))
    rgb = gui.array()
    masks, colors = encode_frame(rgb, 4, columns, rows)
    return masks, colors, full_layout


def available_recording_path(requested=None):
    """Return a non-destructive output path for a new interactive recording."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = (Path(requested).expanduser() if requested else
            Path.home()/f"voyager-model-viewer-{stamp}.vgr")
    if not path.suffix:
        path = path.with_suffix(".vgr")
    suffix = path.suffix or ".vgr"
    candidate = path
    index = 1
    while (candidate.exists() or
           candidate.with_name(candidate.name+".partial").exists()):
        candidate = path.with_name(f"{path.stem}-{stamp}-{index:02d}{suffix}")
        index += 1
    return candidate


class ViewportRecorder:
    """Record only the full-screen model/grid framebuffer into VGR frames."""

    def __init__(self, output, columns, rows, target_fps, state, depth_scale,
                 mesh):
        self.path = available_recording_path(output)
        self.columns = columns
        self.rows = rows
        self.target_fps = target_fps
        self.started = time.monotonic()
        self.frames = 0
        metadata = {
            "schema": "org.square-braille.voyager-recording",
            "format_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "renderer": {
                "title": "PUA 4x4 Voyager Model Viewer — clean viewport recording",
                "python": sys.version.split()[0],
                "numpy": np.__version__,
            },
            "model": {
                "source": "NASA VTAD Voyager",
                "vertices": len(mesh["vertices"]),
                "triangles": len(mesh["faces"]),
                "edges": len(mesh["edges"]),
            },
            "render": {
                "mode": 4,
                "style": state.style,
                "hidden_line_removal": state.hidden_lines,
                "camera": "interactive",
                "depth_scale": depth_scale,
                "content": "model_and_grid_only",
                "hud": False,
                "panels": False,
                "borders": False,
                "model_axes": False,
            },
            "terminal": {
                "columns": columns,
                "rows": rows,
                "graphic_rows": rows,
                "status_rows": 0,
                "virtual_width": columns*4,
                "virtual_height": rows*4,
                "cell_grid": "4x4",
            },
            "encoding": {
                "frame_packet": "VGF1: header + little-endian masks + RGB888 cells",
                "mask_bytes": 2,
                "codepoints": "Part 0 U+F0000..U+F7FFF; Part 1 U+100000..U+107FFF",
                "bit_mapping": "bit = 4*local_y + (3-local_x)",
            },
            "capture": {
                "output": str(self.path),
                "requested_duration_seconds": None,
                "duration_seconds": 0.0,
                "fps": target_fps,
                "frame_count": 0,
                "compression": "ZIP DEFLATE, independently indexed frames",
                "compression_level": 6,
                "full_terminal_framebuffer": True,
            },
            "timeline": [],
        }
        self.writer = VGRWriter(self.path, metadata, force=False, compression=6)
        self.writer.__enter__()

    def add(self, masks, colors, render_seconds, faces, edges):
        elapsed = time.monotonic()-self.started
        self.writer.add_frame(self.frames, elapsed, masks, colors,
                              render_seconds, "INTERACTIVE MODEL VIEW",
                              (faces, edges))
        self.frames += 1

    def finish(self):
        elapsed = max(0.0, time.monotonic()-self.started)
        capture = self.writer.metadata["capture"]
        capture["frame_count"] = self.frames
        capture["duration_seconds"] = elapsed
        capture["fps"] = self.frames/elapsed if self.frames and elapsed else self.target_fps
        size = self.writer.finish(elapsed)
        return self.path, size, capture["fps"]

    def abort(self):
        self.writer.abort()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--style", choices=("wire", "filled"), default="wire")
    parser.add_argument("--no-hlr", action="store_true")
    parser.add_argument("--depth-scale", type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--hud-scale", type=float, default=2.0,
                        help="HUD text scale; default 2.0")
    parser.add_argument("--record-output", type=Path,
                        help="output used when C starts recording")
    parser.add_argument("--start-recording", action="store_true",
                        help="start clean full-screen recording immediately")
    parser.add_argument("--columns", type=int, help="fixed columns; disables live width changes")
    parser.add_argument("--rows", type=int, help="fixed rows; disables live height changes")
    parser.add_argument("--frames", type=int, default=0,
                        help="stop after N rendered frames; useful for tests")
    parser.add_argument("--start-rotating", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    global HUD_SCALE
    args = parse_args(argv)
    if args.fps <= 0:
        raise SystemExit("--fps must be positive")
    if not .75 <= args.hud_scale <= 4.0:
        raise SystemExit("--hud-scale must be between 0.75 and 4.0")
    HUD_SCALE = args.hud_scale
    if not args.mesh.exists():
        raise SystemExit(f"Voyager mesh not found: {args.mesh}")
    if bool(args.columns) != bool(args.rows):
        raise SystemExit("--columns and --rows must be supplied together")
    mesh = load_mesh(args.mesh)
    model_radius = float(np.max(np.linalg.norm(mesh["vertices"], axis=1)))
    state = ViewerState(style=args.style, hidden_lines=not args.no_hlr,
                        rotating=args.start_rotating)
    resize_pending = True
    stop = False

    def request_resize(*unused):
        nonlocal resize_pending
        resize_pending = True

    def request_stop(*unused):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGWINCH, request_resize)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    last_size = None
    render_ms = 0.0
    fps = 0.0
    recent_started = time.monotonic()
    recent_frames = 0
    frame_count = 0
    recorder = None
    recording_pending = args.start_recording
    completed_recordings = []
    recording_error = None
    previous = time.monotonic()
    deadline = previous
    dirty = True
    sys.stdout.write("\x1b]0;PUA 4x4 Voyager Model Viewer\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        with Keyboard() as keyboard:
            while not stop and not state.quit_requested:
                now = time.monotonic()
                delta = min(.1, now-previous)
                previous = now
                key = keyboard.read()
                if key and state.handle_key(key, model_radius):
                    dirty = True
                if state.rotating:
                    state.step_rotation(delta)
                    dirty = True
                terminal = shutil.get_terminal_size((120, 40))
                columns = max(40, args.columns or terminal.columns)
                rows = max(16, args.rows or terminal.lines)
                size = (columns, rows)
                if resize_pending or size != last_size:
                    last_size = size
                    resize_pending = False
                    dirty = True
                    state.message = f"RESIZED · {columns}×{rows} CELLS · {columns*4}×{rows*4} PX"
                    sys.stdout.write("\x1b[2J")
                if state.record_toggle_requested:
                    state.record_toggle_requested = False
                    if recorder is None:
                        recording_pending = True
                    else:
                        path, byte_count, recorded_fps = recorder.finish()
                        completed_recordings.append((path, byte_count, recorded_fps))
                        recorder = None
                        state.recording_active = False
                        state.message = f"RECORDED {state.recording_frames:,} FRAMES · {path.name}"
                        recording_pending = False
                        dirty = True
                if recording_pending and recorder is None:
                    recorder = ViewportRecorder(
                        args.record_output, columns, rows, args.fps, state,
                        args.depth_scale, mesh)
                    recording_pending = False
                    state.recording_active = True
                    state.recording_frames = 0
                    state.recording_path = str(recorder.path)
                    state.message = (f"RECORDING FULL SCREEN · {columns}×{rows} CELLS · "
                                     f"{columns*4}×{rows*4} PX")
                    dirty = True
                if dirty and now >= deadline:
                    started = time.perf_counter()
                    masks, colors, _ = render_gui(
                        mesh, state, columns, rows, args.depth_scale,
                        model_radius, render_ms, fps)
                    picture = terminal_picture(masks, colors, 4)
                    render_ms = (time.perf_counter()-started)*1000
                    sys.stdout.write("\x1b[H"+picture+"\x1b[J")
                    sys.stdout.flush()
                    if recorder is not None:
                        capture_started = time.perf_counter()
                        clean_scene, clean_faces, clean_edges = render_scene(
                            mesh, state, 4, recorder.columns*4,
                            recorder.rows*4, args.depth_scale, model_radius,
                            draw_axes=False)
                        clean_masks, clean_colors = encode_frame(
                            clean_scene, 4, recorder.columns, recorder.rows)
                        capture_seconds = time.perf_counter()-capture_started
                        recorder.add(clean_masks, clean_colors, capture_seconds,
                                     clean_faces, clean_edges)
                        state.recording_frames = recorder.frames
                    frame_count += 1
                    recent_frames += 1
                    span = now-recent_started
                    if span >= 1.0:
                        fps = recent_frames/span
                        recent_started = now
                        recent_frames = 0
                    dirty = state.rotating or recorder is not None
                    deadline = now+1/args.fps
                    if args.frames and frame_count >= args.frames:
                        break
                else:
                    time.sleep(.006)
    finally:
        if recorder is not None:
            try:
                path, byte_count, recorded_fps = recorder.finish()
                completed_recordings.append((path, byte_count, recorded_fps))
            except Exception as error:
                recorder.abort()
                recording_error = error
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
    if recording_error is not None:
        raise recording_error
    for path, byte_count, recorded_fps in completed_recordings:
        print(f"Recorded: {path} · {byte_count:,} bytes · {recorded_fps:.2f} fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
