#!/usr/bin/env python3
"""Continuous one-minute 3D vector space battle for PUA 4x4."""

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
import time

from vector_tunnel import FrameBuffer, clamp, rotate_xyz, shade


NEAR = 0.35


def smoothstep(edge0, edge1, value):
    if edge0 == edge1:
        return float(value >= edge1)
    x = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return x * x * (3.0 - 2.0 * x)


def hash_unit(value):
    """Deterministic 32-bit integer hash normalized to [0, 1)."""
    value &= 0xFFFFFFFF
    value = ((value ^ 61) ^ (value >> 16)) & 0xFFFFFFFF
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 4
    value = (value * 0x27D4EB2D) & 0xFFFFFFFF
    value ^= value >> 15
    return value / 4294967296.0


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


EXPLOSION_EVENTS = (
    (9.0, 1, 1001), (17.0, 4, 2003), (26.0, 0, 3007),
    (35.0, 5, 4001), (44.0, 2, 5003), (53.0, 3, 6007),
)


def look_camera(position, target, roll=0.0):
    dx, dy, dz = subtract(target, position)
    yaw = math.atan2(dx, dz)
    horizontal = math.hypot(dx, dz)
    pitch = -math.atan2(dy, horizontal)
    return position, yaw, pitch, roll


def flight_z(t):
    """Monotonically advancing distance along the one-minute trench run."""
    return t * 8.2 + 7.0 * math.sin(t * .075)


def flight_path(z):
    return (math.sin(z * .031) * 3.8 + math.sin(z * .012) * 1.7,
            .55 + math.sin(z * .023 + .7) * .72)


def camera_at(t):
    """Eight forward-facing fly-through setups on one continuous world path."""
    shot = min(7, int(t // 7.5))
    amount = smoothstep(shot * 7.5, (shot + 1) * 7.5, t)
    z = flight_z(t)
    center_x, center_y = flight_path(z)
    offsets = (
        (0.0, 1.35, .00, -.10, .12),   # centered attack approach
        (-2.2, 1.85, .00, .22, .24),   # left-wing chase view
        (1.9, -.45, .00, -.26, -.30),  # low right trench skim
        (-1.1, .25, .00, .35, .38),    # hard left bank
        (2.4, 1.25, .00, -.38, -.22),  # right-wing chase
        (-1.8, -.70, .00, .30, .34),   # low broadside run
        (0.8, .45, .00, -.22, -.42),   # target dive
        (0.0, 1.0 + amount * 4.0, .00, .18, .05),  # climb-out
    )
    off_x, off_y, off_z, roll_start, roll_end = offsets[shot]
    position = (center_x + off_x + math.sin(t * 1.7) * .16,
                center_y + off_y + math.sin(t * 2.1) * .10,
                z + off_z)
    look_distance = 18.0 + 7.0 * amount
    target_x, target_y = flight_path(z + look_distance)
    target = (target_x, target_y + (.15 if shot != 6 else -1.1), z + look_distance)
    roll = roll_start + (roll_end - roll_start) * amount + math.sin(t * .9) * .055

    # Short, decaying impact shake after each destruction.
    shake_x = shake_y = 0.0
    for event_time, _, _ in EXPLOSION_EVENTS:
        age = t - event_time
        if 0.0 <= age < .85:
            strength = (1.0 - age / .85) * .38
            shake_x += math.sin(age * 57.0) * strength
            shake_y += math.cos(age * 49.0) * strength
    position = add(position, (shake_x, shake_y, 0.0))
    return look_camera(position, target, roll)


def view_point(point, camera):
    position, yaw, pitch, roll = camera
    x, y, z = subtract(point, position)
    # Inverse camera rotation: yaw about Y, pitch about X, roll about Z.
    cy, sy = math.cos(-yaw), math.sin(-yaw)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cp, sp = math.cos(-pitch), math.sin(-pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    cr, sr = math.cos(-roll), math.sin(-roll)
    return x * cr - y * sr, x * sr + y * cr, z


def project(point, camera, width, height):
    x, y, z = view_point(point, camera)
    if z <= NEAR:
        return None
    focal = min(width * .78, height * 1.36)
    return width / 2 + x * focal / z, height / 2 - y * focal / z, z


def transform_vertices(vertices, position, rotation, scale=1.0):
    result = []
    for vertex in vertices:
        rotated = rotate_xyz(tuple(value * scale for value in vertex), *rotation)
        result.append(add(position, rotated))
    return result


def visible_edges(vertices, faces, camera_position):
    edges = set()
    for face in faces:
        a, b, c = (vertices[index] for index in face[:3])
        normal = cross(subtract(b, a), subtract(c, a))
        center = tuple(sum(vertices[index][axis] for index in face) / len(face)
                       for axis in range(3))
        if dot(normal, subtract(camera_position, center)) > 0:
            for index in range(len(face)):
                edges.add(tuple(sorted((face[index], face[(index + 1) % len(face)]))))
    return edges


def draw_mesh(frame, vertices, faces, position, rotation, camera, color, scale=1.0,
              hidden_line=True):
    world = transform_vertices(vertices, position, rotation, scale)
    screen = [project(point, camera, frame.width, frame.height) for point in world]
    if hidden_line:
        edges = visible_edges(world, faces, camera[0])
    else:
        edges = set()
        for face in faces:
            for index in range(len(face)):
                edges.add(tuple(sorted((face[index], face[(index + 1) % len(face)]))))
    depth = max(1.0, position[2] - camera[0][2])
    final_color = shade(color, max(.28, min(1.2, 1.22 - depth / 58.0)))
    for left, right in edges:
        if screen[left] and screen[right]:
            frame.clipped_line(*screen[left][:2], *screen[right][:2], final_color)


CRUISER_VERTICES = (
    (-1.8, -.8, 0), (1.8, -.8, 0), (1.8, .8, 0), (-1.8, .8, 0),
    (-1.45, -.68, 4), (1.45, -.68, 4), (1.45, .68, 4), (-1.45, .68, 4),
    (0, 0, -4.2),
)
CRUISER_FACES = (
    (8, 1, 0), (8, 2, 1), (8, 3, 2), (8, 0, 3),
    (0, 1, 5, 4), (1, 2, 6, 5), (3, 7, 6, 2), (0, 4, 7, 3),
    (4, 5, 6, 7),
)

FIGHTER_VERTICES = (
    (0, 0, -1.9), (-1.25, -.18, .55), (1.25, -.18, .55),
    (0, .48, .10), (0, -.28, 1.05),
)
FIGHTER_FACES = (
    (0, 1, 3), (0, 3, 2), (0, 2, 4), (0, 4, 1),
    (1, 4, 3), (2, 3, 4),
)

BOX_VERTICES = (
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
)
BOX_FACES = (
    (0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3),
    (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2),
)


def cruiser_state(t):
    z = flight_z(t) + 44.0 + 15.0 * math.sin(t * .16)
    path_x, path_y = flight_path(z)
    position = (path_x + 8.2 * math.sin(t * .115),
                path_y + 7.5 + 1.2 * math.sin(t * .21), z)
    rotation = (math.sin(t * .13) * .05, math.sin(t * .071) * .16,
                math.sin(t * .097) * .08)
    return position, rotation


def fighter_state(number, t):
    phase = t * (.82 + number * .031) + number * 2.15
    z = flight_z(t) + 13.0 + number * 3.7 + 5.0 * math.sin(phase * .61 + number)
    path_x, path_y = flight_path(z)
    x = path_x + math.sin(phase) * (3.2 + number * .23)
    y = path_y + 1.1 + math.cos(phase * 1.37 + number) * (1.55 + .12 * number)
    position = (x, y, z)
    rotation = (math.sin(phase * .7) * .28, -phase + math.pi,
                math.sin(phase) * .52)
    return position, rotation


def draw_ellipse(frame, cx, cy, rx, ry, color, start=0.0, end=math.tau, steps=80):
    previous = None
    for step in range(steps + 1):
        angle = start + (end - start) * step / steps
        point = (cx + math.cos(angle) * rx, cy + math.sin(angle) * ry)
        if previous:
            frame.clipped_line(*previous, *point, color)
        previous = point


def draw_moon(frame, t, camera):
    radius = min(frame.width, frame.height) * .245
    cx = (frame.width * .73 + math.sin(t * .025) * radius * .08
          - camera[1] * frame.width * .52)
    cy = (frame.height * .28 + math.cos(t * .019) * radius * .04
          + camera[2] * frame.height * .70)
    limb = (92, 123, 145)
    detail = (48, 73, 91)
    draw_ellipse(frame, cx, cy, radius, radius, limb, steps=120)
    # Terminator and craters are vector arcs, leaving the moon itself unfilled.
    draw_ellipse(frame, cx + radius * .15, cy, radius * .52, radius * .98,
                 detail, -math.pi / 2, math.pi / 2, 70)
    for ox, oy, rx, ry in ((-.32, -.30, .13, .07), (.24, -.18, .17, .09),
                           (-.12, .25, .20, .10), (.38, .27, .08, .05)):
        draw_ellipse(frame, cx + radius * ox, cy + radius * oy,
                     radius * rx, radius * ry, detail, steps=34)
    return cx, cy, radius


def draw_stars(frame, t, moon):
    cx, cy, radius = moon
    count = max(155, min(520, int(frame.width * frame.height / 115)))
    for index in range(count):
        base_x = hash_unit(index * 2 + 0x1F123BB5)
        base_y = hash_unit(index * 2 + 0x9E3779B9)
        speed = .35 + hash_unit(index + 0x85EBCA6B) * .95
        x = (base_x * frame.width + t * speed) % frame.width
        y = (base_y * frame.height + math.sin(t * .13 + index * 1.71) * 1.35) % frame.height
        if (x - cx) ** 2 + (y - cy) ** 2 < radius ** 2:
            continue
        level = 75 + int(hash_unit(index + 0xC2B2AE35) * 145)
        color = (level, level, clamp(level + 28))
        # Short radial streaks reinforce forward speed without making filled cells.
        dx, dy = x - frame.width / 2, y - frame.height / 2
        frame.clipped_line(x - dx * .018, y - dy * .018, x, y, color)


def trench_section(z):
    cx, cy = flight_path(z)
    return (
        (cx - 6.2, cy + 2.3, z), (cx - 6.2, cy - 1.25, z),
        (cx - 3.1, cy - 2.45, z), (cx + 3.1, cy - 2.45, z),
        (cx + 6.2, cy - 1.25, z), (cx + 6.2, cy + 2.3, z),
    )


def draw_trench(frame, t, camera):
    """Open fortress trench rushing continuously beneath the camera."""
    start_z = math.floor((flight_z(t) + 2.0) / 5.2) * 5.2 + 5.2
    sections = []
    for index in range(23):
        z = start_z + index * 5.2
        screen = [project(point, camera, frame.width, frame.height)
                  for point in trench_section(z)]
        sections.append((z, screen))
    for index in range(len(sections) - 1, -1, -1):
        z, screen = sections[index]
        depth = z - camera[0][2]
        strength = max(.24, min(1.0, 1.15 - depth / 105.0))
        color = shade((38, 168, 198), strength)
        # Five sides only: the trench is open to space above the flight path.
        for side in range(5):
            if screen[side] and screen[side + 1]:
                frame.clipped_line(*screen[side][:2], *screen[side + 1][:2], color)
        if index + 1 < len(sections):
            following = sections[index + 1][1]
            for rail in range(6):
                if screen[rail] and following[rail]:
                    frame.clipped_line(*screen[rail][:2], *following[rail][:2],
                                       shade(color, .76))
    # Repeating surface towers and conduits increase the sensation of speed.
    first_structure = math.floor((flight_z(t) + 8.0) / 23.0) * 23.0 + 23.0
    for index in range(6):
        z = first_structure + index * 23.0
        cx, cy = flight_path(z)
        side = -1 if index % 2 else 1
        position = (cx + side * 5.25, cy - .20, z)
        draw_mesh(frame, BOX_VERTICES, BOX_FACES, position,
                  (0.0, index * .23, 0.0), camera, (71, 138, 169),
                  .62 + .13 * (index % 3), True)


def draw_final_target(frame, t, camera):
    if not (42.0 <= t <= 57.5):
        return None
    distance = max(4.2, 70.0 - (t - 42.0) * 5.3)
    z = flight_z(t) + distance
    cx, cy = flight_path(z)
    center = (cx, cy - 1.05, z)
    radii = (3.0, 1.85, .78)
    colors = ((84, 206, 225), (255, 179, 45), (255, 72, 42))
    for radius, color in zip(radii, colors):
        points = []
        for step in range(49):
            angle = math.tau * step / 48
            point = (cx + math.cos(angle) * radius,
                     cy - 1.05 + math.sin(angle) * radius * .62, z)
            points.append(project(point, camera, frame.width, frame.height))
        for left, right in zip(points, points[1:]):
            if left and right:
                frame.clipped_line(*left[:2], *right[:2], color)
    center_screen = project(center, camera, frame.width, frame.height)
    if center_screen:
        outer = radii[0]
        for angle in (0, math.pi / 2, math.pi, math.pi * 1.5):
            edge = project((cx + math.cos(angle) * outer,
                            cy - 1.05 + math.sin(angle) * outer * .62, z),
                           camera, frame.width, frame.height)
            if edge:
                frame.clipped_line(*center_screen[:2], *edge[:2], (255, 118, 35))
    return center


def draw_laser(frame, start, end, camera, color, fraction=1.0):
    a = project(start, camera, frame.width, frame.height)
    target = tuple(start[i] + (end[i] - start[i]) * fraction for i in range(3))
    b = project(target, camera, frame.width, frame.height)
    if a and b:
        frame.clipped_line(*a[:2], *b[:2], color)


def draw_explosion(frame, location, age, camera, seed):
    if not (0 <= age <= 3.2):
        return
    rng = random.Random(seed)
    expansion = .18 + age * 1.12
    fade = max(.15, 1.0 - age / 3.2)
    colors = ((255, 242, 125), (255, 125, 30), (255, 55, 20))
    for index in range(46):
        theta = rng.random() * math.tau
        phi = math.acos(2 * rng.random() - 1)
        radius = expansion * (.35 + rng.random() * .75)
        point = (location[0] + math.sin(phi) * math.cos(theta) * radius,
                 location[1] + math.sin(phi) * math.sin(theta) * radius,
                 location[2] + math.cos(phi) * radius)
        screen = project(point, camera, frame.width, frame.height)
        if screen:
            frame.pixel(screen[0], screen[1], shade(colors[index % len(colors)], fade))
    ring = project(location, camera, frame.width, frame.height)
    if ring:
        apparent = min(frame.width, frame.height) * expansion / max(1.0, ring[2])
        draw_ellipse(frame, ring[0], ring[1], apparent, apparent * .55,
                     shade((255, 174, 55), fade), steps=30)


def draw_hud(frame, t):
    w, h = frame.width, frame.height
    green = (58, 220, 168)
    dim = (25, 106, 89)
    cx, cy = w / 2, h / 2
    radius = min(w, h) * .035
    frame.clipped_line(cx - radius * 2.2, cy, cx - radius * .55, cy, green)
    frame.clipped_line(cx + radius * .55, cy, cx + radius * 2.2, cy, green)
    frame.clipped_line(cx, cy - radius * 1.5, cx, cy - radius * .45, green)
    frame.clipped_line(cx, cy + radius * .45, cx, cy + radius * 1.5, green)
    # Lower-left scanner with orbiting contacts.
    radar_x, radar_y = w * .12, h * .84
    radar_r = min(w, h) * .09
    draw_ellipse(frame, radar_x, radar_y, radar_r, radar_r * .52, dim, steps=46)
    frame.clipped_line(radar_x - radar_r, radar_y, radar_x + radar_r, radar_y, dim)
    frame.clipped_line(radar_x, radar_y - radar_r * .52, radar_x, radar_y + radar_r * .52, dim)
    for index in range(4):
        angle = t * (.4 + index * .07) + index * 1.7
        frame.pixel(radar_x + math.cos(angle) * radar_r * (.35 + index * .12),
                    radar_y + math.sin(angle) * radar_r * .38, (255, 170, 40))
    # Energy rails.
    for side in (-1, 1):
        x0 = cx + side * w * .29
        frame.clipped_line(x0, h * .94, x0 + side * w * .17, h * .89, dim)
        level = .64 + .31 * math.sin(t * .21 + side)
        frame.clipped_line(x0, h * .94, x0 + side * w * .17 * level,
                           h * .94 - h * .05 * level, (255, 192, 50))


def render_scene(columns, rows, timeline, duration):
    frame = FrameBuffer(columns, rows)
    camera = camera_at(timeline)
    moon = draw_moon(frame, timeline, camera)
    draw_stars(frame, timeline, moon)
    draw_trench(frame, timeline, camera)
    final_target = draw_final_target(frame, timeline, camera)

    cruiser_position, cruiser_rotation = cruiser_state(timeline)
    draw_mesh(frame, CRUISER_VERTICES, CRUISER_FACES, cruiser_position,
              cruiser_rotation, camera, (98, 225, 242), 1.72, True)
    # Raised command bridge and twin rear nacelles reinforce the capital-ship
    # silhouette while remaining ordinary hidden-line meshes.
    for offset, scale, color in (
            ((0, 1.14, 1.45), .55, (142, 255, 242)),
            ((-1.82, -.38, 3.15), .52, (68, 177, 238)),
            ((1.82, -.38, 3.15), .52, (68, 177, 238))):
        attachment = add(cruiser_position, rotate_xyz(offset, *cruiser_rotation))
        draw_mesh(frame, BOX_VERTICES, BOX_FACES, attachment, cruiser_rotation,
                  camera, color, scale, True)

    fighters = []
    for number in range(6):
        position, rotation = fighter_state(number, timeline)
        fighters.append(position)
        draw_mesh(frame, FIGHTER_VERTICES, FIGHTER_FACES, position, rotation,
                  camera, (255, 169, 48) if number < 3 else (255, 75, 61),
                  .72 + number * .045, True)
        previous, _ = fighter_state(number, timeline - .28)
        draw_laser(frame, previous, position, camera,
                   (38, 116, 188) if number < 3 else (151, 43, 42), 1.0)

    # Pulsed laser exchanges. Partial beam growth makes each shot visibly travel.
    for number, fighter in enumerate(fighters):
        phase = (timeline * 3.20 + number * .77) % 2.8
        if phase < .52:
            draw_laser(frame, fighter, cruiser_position, camera,
                       (255, 68, 45), min(1.0, phase / .25))
        return_phase = (timeline * 2.80 + number * .91 + 1.8) % 3.6
        if return_phase < .50:
            draw_laser(frame, cruiser_position, fighter, camera,
                       (76, 255, 164), min(1.0, return_phase / .23))

    for event_time, fighter_number, seed in EXPLOSION_EVENTS:
        event_position, _ = fighter_state(fighter_number, event_time)
        draw_explosion(frame, event_position, timeline - event_time, camera, seed)
    if final_target:
        draw_explosion(frame, final_target, timeline - 52.0, camera, 7919)

    draw_hud(frame, timeline)
    fade = min(smoothstep(0.0, 1.4, timeline),
               1.0 - smoothstep(duration - 1.6, duration, timeline))
    if fade < .999:
        for row in range(frame.rows):
            for column in range(frame.columns):
                if frame.masks[row][column]:
                    frame.colors[row][column] = shade(frame.colors[row][column], fade)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0,
                        help="seconds in one repeating battle cycle")
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--once", action="store_true",
                        help="exit after one cycle instead of looping")
    parser.add_argument("--frames", type=int, default=0,
                        help="render exactly this many deterministic frames")
    parser.add_argument("--freeze-at", type=float,
                        help="render one timeline frame and hold it")
    parser.add_argument("--hold", type=float, default=10.0)
    parser.add_argument("--capture", help="PNG path for a --freeze-at terminal window")
    args = parser.parse_args()
    if (args.duration <= 0 or args.fps <= 0 or args.frames < 0 or args.hold < 0 or
            (args.freeze_at is not None and args.freeze_at < 0)):
        parser.error("duration/fps must be positive; frames/freeze-at/hold must be non-negative")
    size = shutil.get_terminal_size((100, 30))
    columns, rows = max(40, size.columns), max(16, size.lines)
    started = time.monotonic()
    frame_number = 0
    sys.stdout.write("\x1b]0;PUA Vector Space Battle — Moon Patrol\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        if args.freeze_at is not None:
            scene = render_scene(columns, rows, args.freeze_at % args.duration, args.duration)
            sys.stdout.write("\x1b[?2026h\x1b[H" + scene.terminal_picture() + "\x1b[?2026l")
            sys.stdout.flush()
            if args.capture:
                time.sleep(.75)
                window_id = os.environ.get("WINDOWID")
                if not window_id:
                    raise SystemExit("MATE Terminal did not provide WINDOWID")
                subprocess.run(["import", "-window", window_id, args.capture], check=True)
            time.sleep(args.hold)
            return
        while True:
            elapsed = time.monotonic() - started
            if args.frames:
                if frame_number >= args.frames:
                    break
                elapsed = frame_number / args.fps
            elif args.once and elapsed >= args.duration:
                break
            timeline = elapsed % args.duration
            scene = render_scene(columns, rows, timeline, args.duration)
            sys.stdout.write("\x1b[?2026h\x1b[H" + scene.terminal_picture() + "\x1b[?2026l")
            sys.stdout.flush()
            frame_number += 1
            deadline = started + frame_number / args.fps
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
