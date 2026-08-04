#!/usr/bin/env python3
"""Two-minute procedural Defender-style attract mode for the PUA 4x4 fonts."""

import argparse
import math
import random
import shutil
import sys
import time

from vector_tunnel import FrameBuffer, clamp


DURATION = 120.0
REFERENCE_FPS = 20.0


def mix(a, b, amount):
    return a + (b - a) * amount


def pulse(value, width=.12):
    value %= 1.0
    return max(0.0, 1.0 - min(value, 1.0 - value) / width)


def hash01(value):
    value = (value ^ 61) ^ (value >> 16)
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 4
    value = (value * 0x27D4EB2D) & 0xFFFFFFFF
    value ^= value >> 15
    return (value & 0xFFFFFFFF) / 4294967296.0


def terrain_height(world_x):
    return (0.72 + .035 * math.sin(world_x * .010)
            + .055 * math.sin(world_x * .0037 + 1.2)
            + .018 * math.sin(world_x * .041 + .7))


def scale_color(color, amount):
    return tuple(clamp(channel * amount) for channel in color)


def line(frame, a, b, color):
    frame.clipped_line(a[0], a[1], b[0], b[1], color)


def polyline(frame, points, color, closed=False):
    for first, second in zip(points, points[1:]):
        line(frame, first, second, color)
    if closed and len(points) > 2:
        line(frame, points[-1], points[0], color)


def disc(frame, cx, cy, radius, color, filled=False):
    steps = max(12, int(radius * 5))
    ring = [(cx + math.cos(i * math.tau / steps) * radius,
             cy + math.sin(i * math.tau / steps) * radius)
            for i in range(steps)]
    polyline(frame, ring, color, True)
    if filled:
        for y in range(int(cy - radius), int(cy + radius + 1)):
            extent = math.sqrt(max(0.0, radius * radius - (y - cy) ** 2))
            line(frame, (cx - extent, y), (cx + extent, y), color)


FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "N": ("101", "111", "111", "111", "101"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    " ": ("000",) * 5,
}


def label(frame, x, y, text, color, scale=1):
    cursor = x
    for character in text.upper():
        rows = FONT.get(character, FONT[" "])
        for py, row in enumerate(rows):
            for px, bit in enumerate(row):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            frame.pixel(cursor + px * scale + sx,
                                        y + py * scale + sy, color)
        cursor += 4 * scale


def draw_ship(frame, x, y, bank, thrust, color=(90, 245, 255)):
    size = max(5.0, min(frame.width, frame.height) * .025)
    points = [
        (x + size * 1.7, y),
        (x + size * .35, y - size * .42),
        (x - size * .55, y - size * .30),
        (x - size * 1.15, y - size * .72),
        (x - size * .83, y),
        (x - size * 1.15, y + size * .72),
        (x - size * .55, y + size * .30),
        (x + size * .35, y + size * .42),
    ]
    if bank:
        points = [(px, y + (py - y) * bank) for px, py in points]
    polyline(frame, points, color, True)
    line(frame, (x - size * .68, y), (x + size * .72, y), color)
    flame = (255, 105 + int(100 * thrust), 30)
    line(frame, (x - size * .86, y),
         (x - size * (1.35 + .5 * thrust), y), flame)


def draw_enemy(frame, x, y, kind, phase):
    radius = max(4.0, min(frame.width, frame.height) * (.018 + .004 * kind))
    color = ((255, 95, 220), (255, 180, 45), (120, 255, 95))[kind % 3]
    if kind % 3 == 0:
        disc(frame, x, y, radius, color)
        line(frame, (x - radius * 1.5, y), (x + radius * 1.5, y), color)
        line(frame, (x, y - radius), (x, y + radius), color)
    elif kind % 3 == 1:
        polyline(frame, ((x - radius * 1.4, y), (x, y - radius),
                         (x + radius * 1.4, y), (x, y + radius)), color, True)
        disc(frame, x, y, radius * .28, (255, 255, 220), True)
    else:
        angle = phase * math.tau
        ring = [(x + math.cos(angle + i * math.tau / 6) * radius,
                 y + math.sin(angle + i * math.tau / 6) * radius)
                for i in range(6)]
        polyline(frame, ring, color, True)


def draw_explosion(frame, x, y, age, seed):
    if not 0 <= age <= 1.3:
        return
    radius = (2 + age * min(frame.width, frame.height) * .08)
    brightness = max(0.0, 1.0 - age / 1.3)
    color = scale_color((255, 205, 70), .35 + .65 * brightness)
    rng = random.Random(seed)
    for index in range(18):
        angle = rng.random() * math.tau
        length = radius * (.35 + rng.random() * .8)
        inner = radius * .12
        line(frame, (x + math.cos(angle) * inner, y + math.sin(angle) * inner),
             (x + math.cos(angle) * length, y + math.sin(angle) * length), color)
    if age < .45:
        disc(frame, x, y, radius * .24, (255, 255, 220), True)


def draw_background(frame, t, camera_x):
    horizon = frame.height * .5
    for index in range(max(90, frame.columns * 2)):
        depth = .15 + hash01(index * 19 + 5) * .85
        sx = (hash01(index * 31 + 11) * frame.width - camera_x * depth * .12) % frame.width
        sy = hash01(index * 47 + 17) * frame.height * .70
        twinkle = .50 + .50 * math.sin(t * (1.3 + depth) + index)
        color = scale_color((120, 185, 255), .18 + .48 * depth * twinkle)
        frame.pixel(sx, sy, color)

    # Parallax mountain chains.
    for layer, color in ((.20, (18, 65, 92)), (.42, (30, 105, 110))):
        points = []
        for x in range(-4, frame.width + 8, 5):
            world = camera_x * layer + x
            y = horizon + frame.height * (.13 + layer * .08)
            y += math.sin(world * .018 + layer * 4) * frame.height * .035
            y += math.sin(world * .051) * frame.height * .018
            points.append((x, y))
        polyline(frame, points, color)


def draw_ground(frame, camera_x):
    color = (60, 235, 155)
    points = []
    for x in range(-2, frame.width + 4, 2):
        world_x = camera_x + x
        points.append((x, terrain_height(world_x) * frame.height))
    polyline(frame, points, color)
    for x in range(0, frame.width, max(12, frame.width // 14)):
        world_x = camera_x + x
        y = terrain_height(world_x) * frame.height
        if hash01(int(world_x // 18)) > .70:
            polyline(frame, ((x - 3, y), (x, y - 5), (x + 3, y)),
                     (110, 255, 175))


def draw_humans(frame, t, camera_x):
    for index in range(24):
        world_x = 120 + index * 170
        x = world_x - camera_x
        if not -10 <= x < frame.width + 10:
            continue
        ground = terrain_height(world_x) * frame.height
        abduct = pulse((t - index * 1.77) / 19.0, .09)
        y = ground - 2 - abduct * frame.height * .15
        color = (255, 235, 130) if abduct < .6 else (255, 120, 190)
        disc(frame, x, y - 2, 1, color)
        line(frame, (x, y - 1), (x, y + 3), color)
        line(frame, (x - 2, y + 1), (x + 2, y + 1), color)


def render_scene(columns, rows, timeline, duration=DURATION):
    frame = FrameBuffer(columns, rows)
    t = timeline % duration
    camera_x = t * 34.0 + math.sin(t * .13) * 55.0
    draw_background(frame, t, camera_x)
    draw_ground(frame, camera_x)
    draw_humans(frame, t, camera_x)

    ship_x = frame.width * (.22 + .025 * math.sin(t * .17))
    ship_y = frame.height * (.42 + .17 * math.sin(t * .43)
                             + .045 * math.sin(t * 1.73))
    bank = .45 + .55 * abs(math.cos(t * .43))
    draw_ship(frame, ship_x, ship_y, bank, .5 + .5 * math.sin(t * 2.8))

    enemies = []
    for index in range(14):
        cycle = 10.0 + (index % 5) * 1.6
        phase = ((t + index * 2.37) % cycle) / cycle
        direction = -1 if index & 1 else 1
        x = (1.15 - phase * 1.35) * frame.width if direction == 1 else (-.15 + phase * 1.35) * frame.width
        y = frame.height * (.20 + .43 * hash01(index * 73 + 9)
                            + .08 * math.sin(t * (1.1 + index * .03) + index))
        kind = index % 3
        enemies.append((x, y, kind, phase))
        draw_enemy(frame, x, y, kind, phase)

        # Enemy fire tracks toward the player's recent position.
        fire_phase = (phase * 5.0 + index * .19) % 1.0
        if fire_phase < .28:
            amount = fire_phase / .28
            bx = mix(x, ship_x, amount)
            by = mix(y, ship_y, amount)
            line(frame, (bx - direction * 5, by), (bx + direction * 7, by),
                 (255, 70, 120))

    # Player's rapid fire: long single-pixel laser bolts.
    shot = (t * 4.8) % 1.0
    bolt_x = ship_x + 10 + shot * frame.width * .70
    line(frame, (bolt_x, ship_y), (bolt_x + frame.width * .11, ship_y),
         (255, 255, 120))
    if int(t * 2.4) % 5 == 0:
        line(frame, (ship_x + 9, ship_y + 2),
             (frame.width * .92, ship_y - frame.height * .11), (80, 255, 255))

    # Regular destruction events make the whole 120-second reel active.
    for event in range(18):
        event_time = 4.0 + event * 6.4
        age = t - event_time
        if 0 <= age <= 1.3:
            victim = enemies[(event * 5) % len(enemies)]
            draw_explosion(frame, victim[0], victim[1], age, 9000 + event)

    # Large command ship and climactic assault during the final quarter.
    if 88.0 <= t < 118.0:
        amount = (t - 88.0) / 30.0
        cx = mix(frame.width * 1.12, frame.width * .72, min(1, amount * 1.7))
        cy = frame.height * (.25 + .04 * math.sin(t * .6))
        radius = min(frame.width, frame.height) * .11
        color = (210, 90, 255)
        disc(frame, cx, cy, radius, color)
        disc(frame, cx, cy, radius * .70, (80, 180, 255))
        line(frame, (cx - radius * 1.45, cy), (cx + radius * 1.45, cy), color)
        for offset in (-.5, 0, .5):
            line(frame, (ship_x, ship_y + offset * 5),
                 (cx - radius * .55, cy + offset * radius), (255, 220, 80))
        if t > 114:
            draw_explosion(frame, cx, cy, (t - 114) * .24, 1776)

    # Vector HUD and scanner occupy genuine individual subpixels.
    radar_y = 6
    line(frame, (4, radar_y), (frame.width - 5, radar_y), (35, 95, 105))
    marker = 5 + ((camera_x * .08) % max(1, frame.width - 10))
    line(frame, (marker, radar_y - 2), (marker, radar_y + 2), (255, 210, 60))
    label(frame, 5, 10, "DEFENDER", (70, 230, 255), 1)
    score = 12500 + int(t * 137) + int(t // 6.4) * 250
    label(frame, max(5, frame.width - 4 * 8 - 6), 10,
          f"{score:08d}"[-8:], (255, 235, 120), 1)
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=DURATION,
                        help="loop length in seconds (default: 120)")
    parser.add_argument("--fps", type=float, default=REFERENCE_FPS)
    parser.add_argument("--once", action="store_true",
                        help="stop after one complete two-minute reel")
    parser.add_argument("--frames", type=int, default=0,
                        help="bounded frame count for tests; 0 is continuous")
    parser.add_argument("--freeze-at", type=float,
                        help="show one timeline position and retain it")
    parser.add_argument("--hold", type=float, default=10.0)
    args = parser.parse_args()
    if args.duration <= 0 or args.fps <= 0 or args.frames < 0:
        parser.error("duration and fps must be positive; frames cannot be negative")

    size = shutil.get_terminal_size((120, 36))
    columns, rows = max(40, size.columns), max(16, size.lines)
    sys.stdout.write("\x1b]0;PUA 4x4 — Defender: 120-second attract mode\x07"
                     "\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    started = time.monotonic()
    count = 0
    try:
        while True:
            elapsed = args.freeze_at if args.freeze_at is not None else time.monotonic() - started
            picture = render_scene(columns, rows, elapsed, args.duration).terminal_picture()
            sys.stdout.write("\x1b[?2026h\x1b[H" + picture + "\x1b[?2026l")
            sys.stdout.flush()
            count += 1
            if args.freeze_at is not None:
                time.sleep(args.hold)
                break
            if args.frames and count >= args.frames:
                break
            if args.once and elapsed >= args.duration:
                break
            deadline = started + count / args.fps
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
