#!/usr/bin/env python3
"""Single-virtual-pixel wireframe tunnel fly-through for PUA Square Braille."""

import argparse
import math
import shutil
import sys
import time


PUA_START = 0xE000
DOT_BIT = ((0, 3), (1, 4), (2, 5), (6, 7))
NEAR = 0.35


def clamp(value, low=0, high=255):
    return max(low, min(high, int(value)))


def shade(color, amount):
    return tuple(clamp(channel * amount) for channel in color)


def rotate_xyz(point, rx, ry, rz):
    x, y, z = point
    cy, sy = math.cos(rx), math.sin(rx)
    y, z = y * cy - z * sy, y * sy + z * cy
    cx, sx = math.cos(ry), math.sin(ry)
    x, z = x * cx + z * sx, -x * sx + z * cx
    cz, sz = math.cos(rz), math.sin(rz)
    return x * cz - y * sz, x * sz + y * cz, z


class FrameBuffer:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.width = columns * 2
        self.height = rows * 4
        self.masks = [[0] * columns for _ in range(rows)]
        self.colors = [[(0, 0, 0)] * columns for _ in range(rows)]
        self.energy = [[-1] * columns for _ in range(rows)]

    def pixel(self, x, y, color):
        x, y = int(round(x)), int(round(y))
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        cell_x, sub_x = divmod(x, 2)
        cell_y, sub_y = divmod(y, 4)
        self.masks[cell_y][cell_x] |= 1 << DOT_BIT[sub_y][sub_x]
        energy = sum(color)
        if energy >= self.energy[cell_y][cell_x]:
            self.colors[cell_y][cell_x] = color
            self.energy[cell_y][cell_x] = energy

    def clipped_line(self, x0, y0, x1, y1, color):
        """Clip, then draw a minimal 4-connected supercover Bresenham line.

        A conventional Bresenham diagonal is only 8-connected: adjacent square
        pixels can meet at one corner. Terminal antialiasing can turn that corner
        contact into a visible pinhole, especially at small font sizes. When a
        step changes both axes, add one pixel along the dominant axis before the
        diagonal destination. Exact horizontal and vertical lines are unchanged.
        """
        dx, dy = x1 - x0, y1 - y0
        p = (-dx, dx, -dy, dy)
        q = (x0, self.width - 1 - x0, y0, self.height - 1 - y0)
        u0, u1 = 0.0, 1.0
        for pi, qi in zip(p, q):
            if abs(pi) < 1e-12:
                if qi < 0:
                    return
                continue
            amount = qi / pi
            if pi < 0:
                u0 = max(u0, amount)
            else:
                u1 = min(u1, amount)
            if u0 > u1:
                return
        ax, ay = round(x0 + u0 * dx), round(y0 + u0 * dy)
        bx, by = round(x0 + u1 * dx), round(y0 + u1 * dy)
        ddx, ddy = abs(bx - ax), -abs(by - ay)
        step_x = 1 if ax < bx else -1
        step_y = 1 if ay < by else -1
        error = ddx + ddy
        while True:
            self.pixel(ax, ay, color)
            if ax == bx and ay == by:
                break
            twice = 2 * error
            move_x = twice >= ddy
            move_y = twice <= ddx
            next_x = ax + step_x if move_x else ax
            next_y = ay + step_y if move_y else ay
            if move_x and move_y:
                if -ddy > ddx:  # steep line: retain the old X for the bridge
                    self.pixel(ax, next_y, color)
                else:  # shallow line: retain the old Y for the bridge
                    self.pixel(next_x, ay, color)
            if move_x:
                error += ddy
            if move_y:
                error += ddx
            ax, ay = next_x, next_y

    def terminal_picture(self):
        lines = []
        active = None
        for row_masks, row_colors in zip(self.masks, self.colors):
            parts = []
            for mask, color in zip(row_masks, row_colors):
                if mask:
                    quantized = tuple((channel // 8) * 8 for channel in color)
                    if quantized != active:
                        parts.append("\x1b[38;2;%d;%d;%dm" % quantized)
                        active = quantized
                elif active is not None:
                    parts.append("\x1b[39m")
                    active = None
                parts.append(chr(PUA_START + mask))
            lines.append("".join(parts))
        return "\n".join(lines)


def tunnel_center(z):
    return math.sin(z * 0.105) * 1.05, math.sin(z * 0.071 + 1.1) * 0.42


def project(point, camera_z, camera_x, camera_y, width, height, roll=0.0):
    x, y, z = point[0] - camera_x, point[1] - camera_y, point[2] - camera_z
    if z <= NEAR:
        return None
    cr, sr = math.cos(roll), math.sin(roll)
    x, y = x * cr - y * sr, x * sr + y * cr
    focal = min(width * 0.88, height * 1.40)
    return width / 2 + x * focal / z, height / 2 - y * focal / z, z


def depth_color(depth, pulse=0.0):
    near = (120, 255, 235)
    far = (20, 72, 120)
    amount = max(0.0, min(1.0, 1.0 - depth / 62.0))
    color = tuple(clamp(f + (n - f) * amount) for n, f in zip(near, far))
    return tuple(clamp(c + pulse * 70) for c in color)


def tunnel_ring(z, sides=8):
    cx, cy = tunnel_center(z)
    points = []
    # An octagonal rectangular section resembles early vector hardware geometry.
    for x, y in ((-3.6, -1.65), (-2.8, -2.25), (2.8, -2.25), (3.6, -1.65),
                 (3.6, 1.65), (2.8, 2.25), (-2.8, 2.25), (-3.6, 1.65)):
        points.append((cx + x, cy + y, z))
    return points[:sides]


def vector_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vector_sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def vector_dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def draw_hidden_line_cube(frame, center, size, rotations, camera):
    """Draw only edges adjacent to camera-facing faces."""
    local = [
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    ]
    vertices = []
    for point in local:
        rotated = rotate_xyz(tuple(value * size for value in point), *rotations)
        vertices.append(tuple(center[i] + rotated[i] for i in range(3)))
    faces = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3),
             (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2))
    visible = []
    camera_point = (camera[0], camera[1], camera[2])
    for face in faces:
        a, b, c = (vertices[index] for index in face[:3])
        normal = vector_cross(vector_sub(b, a), vector_sub(c, a))
        center_face = tuple(sum(vertices[index][axis] for index in face) / 4 for axis in range(3))
        visible.append(vector_dot(normal, vector_sub(camera_point, center_face)) > 0)
    edges = set()
    for is_visible, face in zip(visible, faces):
        if is_visible:
            for index in range(4):
                edges.add(tuple(sorted((face[index], face[(index + 1) % 4]))))
    projected = [project(point, camera[2], camera[0], camera[1], frame.width, frame.height, camera[3])
                 for point in vertices]
    distance = center[2] - camera[2]
    color = shade((255, 194, 70), max(0.28, 1.15 - distance / 55.0))
    for left, right in edges:
        if projected[left] and projected[right]:
            frame.clipped_line(*projected[left][:2], *projected[right][:2], color)


def draw_ship(frame, t):
    """A thin vector cockpit and reticle; every segment is one virtual pixel."""
    w, h = frame.width, frame.height
    color = (55, 205, 170)
    frame.clipped_line(0, h - 1, w * .20, h * .78, color)
    frame.clipped_line(w * .20, h * .78, w * .34, h - 1, color)
    frame.clipped_line(w - 1, h - 1, w * .80, h * .78, color)
    frame.clipped_line(w * .80, h * .78, w * .66, h - 1, color)
    cx, cy = w / 2, h / 2
    radius = min(w, h) * .035 + math.sin(t * 2.4)
    for start, end in ((-2.0, -0.65), (0.65, 2.0)):
        frame.clipped_line(cx + start * radius, cy, cx + end * radius, cy, (120, 255, 225))
        frame.clipped_line(cx, cy + start * radius, cx, cy + end * radius, (120, 255, 225))
    # Vector gauges demonstrate shallow diagonal steps through different dot positions.
    for side in (-1, 1):
        origin_x = cx + side * w * .34
        frame.clipped_line(origin_x, h * .91, origin_x + side * w * .08, h * .87, (255, 155, 45))
        level = .5 + .45 * math.sin(t * .7 + side)
        frame.clipped_line(origin_x, h * .91, origin_x + side * w * .08 * level,
                           h * .91 - h * .04 * level, (255, 235, 110))


def draw_scene(columns, rows, t):
    frame = FrameBuffer(columns, rows)
    speed = 5.4
    camera_z = t * speed
    camera_x, camera_y = tunnel_center(camera_z + 2.2)
    camera_x *= .72
    camera_y *= .65
    roll = math.sin(t * .43) * .075
    camera = (camera_x, camera_y, camera_z, roll)

    spacing = 3.2
    first = math.floor((camera_z + NEAR) / spacing) * spacing + spacing
    rings = []
    for index in range(19):
        z = first + index * spacing
        world = tunnel_ring(z)
        screen = [project(point, camera_z, camera_x, camera_y,
                          frame.width, frame.height, roll) for point in world]
        rings.append((world, screen, z - camera_z))

    # Longitudinal rails are clipped to successive rings. Near rings overwrite far
    # lines at crossings, providing a simple painter-style visibility ordering.
    for index in range(len(rings) - 1, -1, -1):
        _, screen, depth = rings[index]
        pulse = .22 * (1 + math.sin((rings[index][2] - t * 5) * .4))
        color = depth_color(depth, pulse)
        for side in range(8):
            a, b = screen[side], screen[(side + 1) % 8]
            if a and b:
                frame.clipped_line(*a[:2], *b[:2], color)
        if index + 1 < len(rings):
            next_screen = rings[index + 1][1]
            for side in range(8):
                if screen[side] and next_screen[side]:
                    frame.clipped_line(*screen[side][:2], *next_screen[side][:2],
                                       shade(color, .72))

    # Deterministic rotating obstacles; cube face tests remove rear/internal edges.
    sector = math.floor(camera_z / 18.0)
    for number in range(sector, sector + 6):
        z = number * 18.0 + 13.0
        cx, cy = tunnel_center(z)
        cx += math.sin(number * 2.31) * 1.65
        cy += math.cos(number * 1.73) * .72
        draw_hidden_line_cube(
            frame, (cx, cy, z), .52 + .16 * ((number + 2) % 3),
            (t * .37 + number, t * .51 + number * .4, t * .29), camera,
        )

    # Sparse moving points emphasize that a single dot—not a character cell—is lit.
    for particle in range(75):
        z = camera_z + 1.0 + ((particle * 7.919 - t * 2.4) % 58.0)
        cx, cy = tunnel_center(z)
        x = cx + math.sin(particle * 12.989) * 2.75
        y = cy + math.sin(particle * 4.123 + 1.2) * 1.55
        point = project((x, y, z), camera_z, camera_x, camera_y,
                        frame.width, frame.height, roll)
        if point:
            frame.pixel(point[0], point[1], depth_color(point[2]))

    draw_ship(frame, t)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--frames", type=int, default=0,
                        help="render exactly this many deterministic frames")
    parser.add_argument("--freeze-at", type=float,
                        help="render one frame at this timeline second")
    parser.add_argument("--hold", type=float, default=10.0,
                        help="seconds to retain a --freeze-at frame")
    args = parser.parse_args()
    if (args.duration <= 0 or args.fps <= 0 or args.frames < 0 or
            args.hold < 0 or (args.freeze_at is not None and args.freeze_at < 0)):
        parser.error("duration/fps must be positive; frames/freeze-at/hold must be non-negative")
    size = shutil.get_terminal_size((100, 30))
    columns, rows = max(40, size.columns), max(16, size.lines)
    started = time.monotonic()
    frame_number = 0
    sys.stdout.write("\x1b]0;PUA Vector Flight — Hidden-Line Tunnel\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        if args.freeze_at is not None:
            scene = draw_scene(columns, rows, args.freeze_at)
            sys.stdout.write("\x1b[?2026h\x1b[H" + scene.terminal_picture() + "\x1b[?2026l")
            sys.stdout.flush()
            time.sleep(args.hold)
            return
        while True:
            if args.frames:
                if frame_number >= args.frames:
                    break
                t = frame_number / args.fps
            else:
                t = time.monotonic() - started
                if t >= args.duration:
                    break
            scene = draw_scene(columns, rows, t)
            sys.stdout.write("\x1b[?2026h\x1b[H" + scene.terminal_picture() + "\x1b[?2026l")
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
