#!/usr/bin/env python3
"""Animated vector-flight demonstration for the two PUA 4x4 fonts."""

import argparse
import math
import random
import select
import shutil
import sys
import termios
import time
import tty

from pua4x4 import mask_to_codepoint
from pua4x4_demo import Canvas


PALETTE = {
    0: (95, 215, 255),
    1: (50, 255, 185),
    2: (255, 195, 65),
    3: (255, 85, 155),
    4: (180, 140, 255),
    5: (235, 245, 255),
    6: (20, 38, 70),
    7: (28, 58, 96),
    8: (34, 82, 122),
    9: (42, 110, 148),
    10: (52, 144, 176),
    11: (70, 180, 205),
    12: (115, 215, 232),
    13: (215, 245, 255),
}


class ColorCanvas(Canvas):
    def __init__(self, width, height):
        super().__init__(width, height)
        character_rows = (height + 3) // 4
        character_columns = (width + 3) // 4
        self.colors = [[0] * character_columns for _ in range(character_rows)]
        self.priorities = [[-1] * character_columns for _ in range(character_rows)]

    def set(self, x, y, color=0, priority=0):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        super().set(x, y)
        character_row, _ = divmod(y, 4)
        character_column, _ = divmod(x, 4)
        if priority >= self.priorities[character_row][character_column]:
            self.colors[character_row][character_column] = color
            self.priorities[character_row][character_column] = priority

    def line(self, x0, y0, x1, y1, color=0, priority=0):
        clipped = self.clip_line(x0, y0, x1, y1)
        if clipped is None:
            return
        x0, y0, x1, y1 = clipped
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.set(x0, y0, color, priority)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy

    def clip_line(self, x0, y0, x1, y1):
        """Liang-Barsky clip, allowing near rings to pass the viewpoint."""
        dx, dy = x1 - x0, y1 - y0
        lower, upper = 0.0, 1.0
        for p, q in (
            (-dx, x0),
            (dx, self.width - 1 - x0),
            (-dy, y0),
            (dy, self.height - 1 - y0),
        ):
            if p == 0:
                if q < 0:
                    return None
                continue
            ratio = q / p
            if p < 0:
                if ratio > upper:
                    return None
                lower = max(lower, ratio)
            else:
                if ratio < lower:
                    return None
                upper = min(upper, ratio)
        return (
            round(x0 + lower * dx),
            round(y0 + lower * dy),
            round(x0 + upper * dx),
            round(y0 + upper * dy),
        )

    def polyline(self, points, color=0, priority=0, closed=False):
        if closed and points:
            points = points + points[:1]
        for start, end in zip(points, points[1:]):
            self.line(*start, *end, color=color, priority=priority)


def rotate(x, y, angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    return x * cosine - y * sine, x * sine + y * cosine


def project(x, y, z, width, height, roll=0.0, yaw=0.0):
    x += yaw * z
    x, y = rotate(x, y, roll)
    if z <= 0.08:
        return None
    scale = min(width / 7.5, height / 3.2) / z
    # One virtual pixel is half as wide as it is tall. Doubling projected X
    # produces geometrically correct shapes in a normal 1:2 terminal cell.
    return round(width / 2 + x * scale * 2), round(height / 2 + y * scale)


VORTEX_NEAR = 0.09
VORTEX_DEPTH = 5.6
VORTEX_RADIUS = 1.34


def centreline(z, phase):
    """Curved camera-relative tunnel axis at depth z."""
    x = (
        0.78 * math.sin(phase * 0.43 + z * 0.47)
        + 0.29 * math.sin(-phase * 0.19 + z * 1.03)
    )
    y = (
        0.58 * math.cos(phase * 0.36 + z * 0.41)
        + 0.23 * math.sin(phase * 0.27 - z * 0.89)
    )
    return x, y


def vortex_twist(z, phase):
    return phase * 0.17 + z * 0.31 + 0.25 * math.sin(phase * 0.29 + z * 0.72)


def vortex_point(canvas, z, angle, radius, phase):
    centre_x, centre_y = centreline(z, phase)
    angle += vortex_twist(z, phase)
    # Multiplying the centreline displacement by depth makes its projected
    # screen displacement independent of perspective shrinkage. Each ring can
    # therefore follow a visibly curved path through the viewport.
    x = z * centre_x + radius * math.cos(angle)
    y = z * centre_y + radius * math.sin(angle)
    roll = 0.10 * math.sin(phase * 0.21)
    return project(x, y, z, canvas.width, canvas.height, roll=roll)


def depth_color(z):
    proximity = 1.0 - (z - VORTEX_NEAR) / (VORTEX_DEPTH - VORTEX_NEAR)
    proximity = max(0.0, min(1.0, proximity))
    return 6 + round(proximity * 7)


def vortex(canvas, phase):
    sides = 18
    ring_count = 19
    depth_span = VORTEX_DEPTH - VORTEX_NEAR
    rings = []
    for ring_number in range(ring_count):
        z = VORTEX_NEAR + (
            (ring_number * depth_span / ring_count - phase * 0.72) % depth_span
        )
        radius = VORTEX_RADIUS * (1.0 + 0.07 * math.sin(z * 1.5 - phase * 0.6))
        points = [
            vortex_point(canvas, z, math.tau * side / sides, radius, phase)
            for side in range(sides)
        ]
        points = [point for point in points if point is not None]
        if len(points) == sides:
            color = depth_color(z)
            canvas.polyline(points, color=color, priority=2, closed=True)
            rings.append((z, points))

    # Joining identical side indices while the cross-section rotates with
    # depth creates spiral ribs following the curved centreline.
    rings.sort(key=lambda item: item[0])
    for (near_z, near), (far_z, far) in zip(rings, rings[1:]):
        for side in range(sides):
            color = depth_color((near_z + far_z) / 2)
            canvas.line(*near[side], *far[side], color=color, priority=1)


def wall_particles(canvas, phase, particles):
    depth_span = VORTEX_DEPTH - VORTEX_NEAR
    for angle, depth_seed, speed, radius, brightness in particles:
        z = VORTEX_NEAR + (
            (depth_seed * depth_span - phase * speed) % depth_span
        )
        point = vortex_point(canvas, z, angle, radius, phase)
        if point is not None:
            base = depth_color(z)
            color = min(13, base + (1 if brightness > 0.55 else 0))
            canvas.set(*point, color=color, priority=0)


def background_stars(canvas, phase, stars):
    """Slow parallax field covering the viewport, independent of the tube."""
    for x_seed, y_seed, drift, twinkle in stars:
        x = (x_seed + phase * drift * 0.003) % 1.0
        y = (y_seed + phase * drift * 0.0013) % 1.0
        x = round(x * (canvas.width - 1))
        y = round(y * (canvas.height - 1))
        pulse = 0.5 + 0.5 * math.sin(phase * (0.7 + drift) + twinkle)
        canvas.set(x, y, color=5 if pulse > 0.82 else 8, priority=0)


def build_frame(columns, rows, phase, particles, stars=None):
    canvas = ColorCanvas(columns * 4, rows * 4)
    if stars is not None:
        background_stars(canvas, phase, stars)
    wall_particles(canvas, phase, particles)
    vortex(canvas, phase)
    return canvas


def make_particles(count=260, seed=0x4A4A):
    randomizer = random.Random(seed)
    return [
        (
            randomizer.random() * math.tau,
            randomizer.random(),
            0.28 + randomizer.random() * 0.62,
            0.18 + randomizer.random() * VORTEX_RADIUS * 0.92,
            randomizer.random(),
        )
        for _ in range(count)
    ]


def make_stars(count=520, seed=0x51A7):
    randomizer = random.Random(seed)
    return [
        (
            randomizer.random(),
            randomizer.random(),
            0.15 + randomizer.random() * 1.6,
            randomizer.random() * math.tau,
        )
        for _ in range(count)
    ]


def ansi_frame(canvas, color=True):
    part0 = part1 = blank = 0
    lines = []
    for masks, colors in zip(canvas.masks, canvas.colors):
        output = []
        current_color = None
        for mask, color_index in zip(masks, colors):
            if mask == 0:
                blank += 1
            elif mask < 0x8000:
                part0 += 1
            else:
                part1 += 1
            if color and color_index != current_color:
                red, green, blue = PALETTE[color_index]
                output.append(f"\x1b[38;2;{red};{green};{blue}m")
                current_color = color_index
            output.append(chr(mask_to_codepoint(mask)))
        if color:
            output.append("\x1b[0m")
        lines.append("".join(output))
    return "\n".join(lines), part0, part1, blank


class Keyboard:
    def __enter__(self):
        self.enabled = sys.stdin.isatty()
        if self.enabled:
            self.settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def pressed(self):
        if not self.enabled:
            return None
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        return sys.stdin.read(1) if readable else None

    def __exit__(self, *_):
        if self.enabled:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="0 runs continuously")
    parser.add_argument("--columns", type=int)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--max-columns", type=int, default=0,
                        help="optional live-resize column cap; 0 is unlimited")
    parser.add_argument("--max-rows", type=int, default=0,
                        help="optional live-resize row cap; 0 is unlimited")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps must be greater than zero")

    particles = make_particles()
    stars = make_stars()
    started = time.monotonic()
    frame_number = 0
    last_size = None

    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[?25l")
    sys.stdout.flush()
    try:
        with Keyboard() as keyboard:
            while True:
                frame_started = time.monotonic()
                elapsed = frame_started - started
                if args.seconds and elapsed >= args.seconds:
                    break
                if keyboard.pressed() in ("q", "Q", "\x1b"):
                    break

                terminal = shutil.get_terminal_size((100, 32))
                columns = args.columns or max(24, terminal.columns)
                rows = args.rows or max(8, terminal.lines - 2)
                if args.max_columns > 0:
                    columns = min(columns, args.max_columns)
                if args.max_rows > 0:
                    rows = min(rows, args.max_rows)
                size = (columns, rows)
                if size != last_size:
                    sys.stdout.write("\x1b[2J")
                    last_size = size

                canvas = build_frame(columns, rows, elapsed, particles, stars)
                picture, part0, part1, blank = ansi_frame(
                    canvas, not args.no_color
                )
                heading = (
                    f"PUA 4x4 CURVED VORTEX  {canvas.width}x{canvas.height} virtual pixels  "
                    f"active P0:{part0} P1:{part1}  blank:{blank}  "
                    f"{args.fps:g} fps  q/ESC quits"
                )
                heading = heading[:terminal.columns].ljust(terminal.columns)
                sys.stdout.write("\x1b[H" + heading + "\n" + picture)
                sys.stdout.flush()

                frame_number += 1
                deadline = started + frame_number / args.fps
                time.sleep(max(0.0, deadline - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
