#!/usr/bin/env python3
"""Thirty-second original retro-FPS sequence for the PUA 4x4 framebuffer."""

import argparse
import math
import random
import shutil
import sys
import time


from pua4x4_backend import DOT_BIT, mask_to_codepoint
FOV = math.radians(66)
WORLD = (
    "################",
    "#..............#",
    "#..##......##..#",
    "#..............#",
    "#..............#",
    "######..D.######",
    "#..............#",
    "#..............#",
    "#..............#",
    "#..............#",
    "################",
)


def clamp(value, low=0, high=255):
    return max(low, min(high, int(value)))


def rgb_scale(color, amount):
    return tuple(clamp(channel * amount) for channel in color)


def blend(a, b, amount):
    return tuple(clamp(x + (y - x) * amount) for x, y in zip(a, b))


def smoothstep(edge0, edge1, value):
    if edge0 == edge1:
        return float(value >= edge1)
    x = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return x * x * (3.0 - 2.0 * x)


def camera_at(t):
    """Scripted camera: approach, door pause, entry, then a cautious turn."""
    if t < 2.0:
        return 8.5, 9.25, -math.pi / 2
    if t < 7.0:
        amount = smoothstep(2.0, 7.0, t)
        return 8.5, 9.25 - 2.55 * amount, -math.pi / 2
    if t < 10.0:
        return 8.5, 6.70, -math.pi / 2
    if t < 16.0:
        amount = smoothstep(10.0, 16.0, t)
        return 8.5, 6.70 - 3.00 * amount, -math.pi / 2 + 0.08 * math.sin(t * 1.5)
    if t < 22.0:
        return 8.5, 3.70, -math.pi / 2 + 0.05 * math.sin(t * 1.2)
    amount = smoothstep(22.0, 27.5, t)
    return 8.5 + 1.15 * amount, 3.70, -math.pi / 2 + 0.52 * amount


def door_open_at(t):
    return smoothstep(7.2, 9.6, t)


def solid_at(map_x, map_y, door_open):
    if map_y < 0 or map_y >= len(WORLD) or map_x < 0 or map_x >= len(WORLD[0]):
        return "#"
    tile = WORLD[map_y][map_x]
    if tile == "D" and door_open > 0.82:
        return "."
    return tile


def raycast(px, py, angle, door_open, max_depth=24.0):
    ray_x, ray_y = math.cos(angle), math.sin(angle)
    map_x, map_y = int(px), int(py)
    delta_x = abs(1.0 / ray_x) if abs(ray_x) > 1e-9 else 1e30
    delta_y = abs(1.0 / ray_y) if abs(ray_y) > 1e-9 else 1e30
    step_x = -1 if ray_x < 0 else 1
    step_y = -1 if ray_y < 0 else 1
    side_x = (px - map_x) * delta_x if ray_x < 0 else (map_x + 1.0 - px) * delta_x
    side_y = (py - map_y) * delta_y if ray_y < 0 else (map_y + 1.0 - py) * delta_y
    side = 0
    for _ in range(40):
        if side_x < side_y:
            side_x += delta_x
            map_x += step_x
            side = 0
        else:
            side_y += delta_y
            map_y += step_y
            side = 1
        tile = solid_at(map_x, map_y, door_open)
        if tile != ".":
            if side == 0:
                depth = (map_x - px + (1 - step_x) / 2) / ray_x
                wall_pos = (py + depth * ray_y) % 1.0
            else:
                depth = (map_y - py + (1 - step_y) / 2) / ray_y
                wall_pos = (px + depth * ray_x) % 1.0
            return min(max_depth, max(0.001, depth)), tile, side, wall_pos
    return max_depth, "#", side, 0.0


def set_pixel(canvas, width, height, x, y, color):
    x, y = int(x), int(y)
    if 0 <= x < width and 0 <= y < height:
        canvas[y * width + x] = color


def fill_polygon(canvas, width, height, points, color):
    min_y = max(0, int(min(y for _, y in points)))
    max_y = min(height - 1, int(max(y for _, y in points)))
    count = len(points)
    for y in range(min_y, max_y + 1):
        intersections = []
        scan_y = y + 0.5
        for i in range(count):
            x0, y0 = points[i]
            x1, y1 = points[(i + 1) % count]
            if (y0 <= scan_y < y1) or (y1 <= scan_y < y0):
                intersections.append(x0 + (scan_y - y0) * (x1 - x0) / (y1 - y0))
        intersections.sort()
        for i in range(0, len(intersections) - 1, 2):
            for x in range(max(0, int(math.ceil(intersections[i]))),
                           min(width, int(math.floor(intersections[i + 1])) + 1)):
                set_pixel(canvas, width, height, x, y, color)


def draw_disc(canvas, width, height, cx, cy, radius, color):
    radius = max(1, int(radius))
    for y in range(max(0, int(cy - radius)), min(height, int(cy + radius) + 1)):
        extent = int(math.sqrt(max(0, radius * radius - (y - cy) ** 2)))
        for x in range(max(0, int(cx - extent)), min(width, int(cx + extent) + 1)):
            set_pixel(canvas, width, height, x, y, color)


def draw_enemy(canvas, zbuffer, width, height, px, py, angle, t):
    if t < 13.5 or t > 23.0:
        return
    ex, ey = 8.45, 2.15
    dx, dy = ex - px, ey - py
    distance = math.hypot(dx, dy)
    relative = (math.atan2(dy, dx) - angle + math.pi) % (2 * math.pi) - math.pi
    if abs(relative) > FOV * 0.58:
        return
    screen_x = width * (0.5 + relative / FOV)
    size = min(height * 0.72, height * 0.92 / max(distance, 0.2))
    if not (0 <= int(screen_x) < width) or distance > zbuffer[int(screen_x)] + 0.2:
        return
    death = smoothstep(20.1, 21.4, t)
    size *= 1.0 - 0.55 * death
    base_y = height * 0.52 + size * 0.53 + death * height * 0.12
    flash = any(abs(t - shot) < 0.10 for shot in (18.2, 18.85, 19.55, 20.15))
    body = (225, 205, 166) if flash else (138, 47, 32)
    shade = rgb_scale(body, max(0.35, 1.0 - distance / 12.0))
    # Legs, torso, head, horns, and eyes form an original low-resolution creature.
    fill_polygon(canvas, width, height, [
        (screen_x - size * .27, base_y), (screen_x - size * .12, base_y - size * .52),
        (screen_x + size * .12, base_y - size * .52), (screen_x + size * .28, base_y),
    ], rgb_scale(shade, .72))
    fill_polygon(canvas, width, height, [
        (screen_x - size * .34, base_y - size * .31), (screen_x - size * .23, base_y - size * .72),
        (screen_x + size * .23, base_y - size * .72), (screen_x + size * .35, base_y - size * .31),
    ], shade)
    draw_disc(canvas, width, height, screen_x, base_y - size * .78, size * .20, rgb_scale(shade, 1.08))
    fill_polygon(canvas, width, height, [
        (screen_x - size * .18, base_y - size * .88), (screen_x - size * .34, base_y - size * 1.03),
        (screen_x - size * .08, base_y - size * .94),
    ], rgb_scale(shade, .65))
    fill_polygon(canvas, width, height, [
        (screen_x + size * .18, base_y - size * .88), (screen_x + size * .34, base_y - size * 1.03),
        (screen_x + size * .08, base_y - size * .94),
    ], rgb_scale(shade, .65))
    eye_color = (255, 235, 48) if not flash else (255, 255, 255)
    draw_disc(canvas, width, height, screen_x - size * .075, base_y - size * .81, size * .025, eye_color)
    draw_disc(canvas, width, height, screen_x + size * .075, base_y - size * .81, size * .025, eye_color)


def draw_weapon(canvas, width, height, t, moving):
    bob = math.sin(t * 8.5) * height * 0.012 * moving
    sway = math.sin(t * 4.2) * width * 0.012 * moving
    cx, bottom = width * 0.5 + sway, height - 3 + bob
    metal = (92, 98, 91)
    dark = (38, 42, 39)
    fill_polygon(canvas, width, height, [
        (cx - width * .12, bottom), (cx - width * .075, bottom - height * .16),
        (cx - width * .035, bottom - height * .26), (cx + width * .035, bottom - height * .26),
        (cx + width * .075, bottom - height * .16), (cx + width * .12, bottom),
    ], dark)
    fill_polygon(canvas, width, height, [
        (cx - width * .055, bottom - height * .08), (cx - width * .032, bottom - height * .25),
        (cx + width * .032, bottom - height * .25), (cx + width * .055, bottom - height * .08),
    ], metal)
    for shot in (18.2, 18.85, 19.55, 20.15):
        pulse = 1.0 - abs(t - shot) / 0.13
        if pulse > 0:
            cy = bottom - height * .29
            radius = height * (.035 + .075 * pulse)
            draw_disc(canvas, width, height, cx, cy, radius, (255, 245, 185))
            fill_polygon(canvas, width, height, [
                (cx, cy - radius * 1.8), (cx - radius * .42, cy), (cx, cy + radius * .6),
                (cx + radius * .42, cy),
            ], (255, 138, 18))


def draw_hud(canvas, width, height, t):
    hud_top = height - max(4, height // 13)
    for y in range(hud_top, height):
        for x in range(width):
            canvas[y * width + x] = (38, 31, 25) if (x // 6 + y // 3) % 2 else (49, 39, 29)
    health = 100 if t < 19.5 else 87
    ammo = max(0, 50 - 4 * sum(t >= shot for shot in (18.2, 18.85, 19.55, 20.15)))
    bar_y = hud_top + 1
    for x in range(3, 3 + int((width * .22) * health / 100)):
        set_pixel(canvas, width, height, x, bar_y, (50, 226, 69) if health > 35 else (238, 45, 32))
    for x in range(width - 3 - int((width * .22) * ammo / 50), width - 3):
        set_pixel(canvas, width, height, x, bar_y, (252, 194, 37))


def render_scene(columns, rows, t, duration):
    width, height = columns * 4, rows * 4
    canvas = [(0, 0, 0)] * (width * height)
    px, py, angle = camera_at(t)
    opening = door_open_at(t)
    zbuffer = [24.0] * width
    horizon = int(height * 0.49 + math.sin(t * 8.5) * (0.8 if 2 < t < 16 else 0.0))

    # Sparse ceiling lights and a perspective floor establish depth before walls.
    for y in range(height):
        if y < horizon:
            base = 8 + int(12 * y / max(1, horizon))
            for x in range(width):
                if ((x // 18) + (y // 7)) % 11 == 0 and y > horizon * .45:
                    canvas[y * width + x] = (base + 10, base + 7, base + 2)
        else:
            depth = (y - horizon) / max(1, height - horizon)
            for x in range(width):
                checker = ((int((x - width / 2) / max(.18, depth * 8)) + int(1 / max(.03, depth) * 1.7)) & 1)
                shade = 16 + int(depth * 24) + checker * 6
                canvas[y * width + x] = (shade, shade - 2, shade - 4)

    for x in range(width):
        ray_angle = angle - FOV / 2 + FOV * (x + 0.5) / width
        depth, tile, side, wall_pos = raycast(px, py, ray_angle, opening)
        corrected = max(0.08, depth * math.cos(ray_angle - angle))
        zbuffer[x] = corrected
        wall_height = min(height * 2.0, height * 0.80 / corrected)
        top, bottom = int(horizon - wall_height / 2), int(horizon + wall_height / 2)
        base_color = (142, 88, 52) if tile == "#" else (116, 121, 116)
        distance_light = max(0.27, 1.28 - corrected / 10.5)
        if side:
            distance_light *= 0.78
        for y in range(max(0, top), min(height, bottom + 1)):
            texture_y = (y - top) / max(1, bottom - top)
            mortar = (int(wall_pos * 8) % 4 == 0) or (int(texture_y * 12) % 4 == 0)
            amount = distance_light * (0.62 if mortar else 1.0)
            if tile == "D":
                stripe = int(wall_pos * 12) % 3 == 0
                amount *= .66 if stripe else 1.0
                base_color = blend((82, 83, 79), (135, 48, 30), opening * .45)
            canvas[y * width + x] = rgb_scale(base_color, amount)

    draw_enemy(canvas, zbuffer, width, height, px, py, angle, t)
    moving = 1.0 if (2.0 < t < 7.0 or 10.0 < t < 16.0 or 22.0 < t < 27.5) else 0.15
    draw_weapon(canvas, width, height, t, moving)
    draw_hud(canvas, width, height, t)

    # Fade-in, door warning glow, and fade-out/title-card red wash.
    fade = smoothstep(0.0, 1.5, t) * (1.0 - smoothstep(duration - 2.0, duration, t))
    warning = max(0.0, math.sin((t - 7.0) * math.pi * 2)) * (1.0 - opening) if 7.0 < t < 10.0 else 0.0
    for i, color in enumerate(canvas):
        color = blend(color, (65, 3, 0), warning * .16)
        canvas[i] = rgb_scale(color, fade)
    return canvas, width, height


def quantize(color):
    # Six-bit channels keep ANSI output compact while retaining gritty shading.
    return tuple((channel // 8) * 8 for channel in color)


def to_terminal(canvas, width, height, columns, rows):
    lines = []
    active = None
    for cell_y in range(rows):
        parts = []
        for cell_x in range(columns):
            mask = 0
            colors = []
            for sub_y in range(4):
                y = cell_y * 4 + sub_y
                if y >= height:
                    continue
                for sub_x in range(4):
                    x = cell_x * 4 + sub_x
                    if x >= width:
                        continue
                    color = canvas[y * width + x]
                    if max(color) > 2:
                        mask |= 1 << DOT_BIT[sub_y][sub_x]
                        colors.append(color)
            if colors:
                color = quantize(tuple(sum(c[i] for c in colors) // len(colors) for i in range(3)))
                if color != active:
                    parts.append("\x1b[38;2;%d;%d;%dm" % color)
                    active = color
            elif active is not None:
                parts.append("\x1b[39m")
                active = None
            parts.append(chr(mask_to_codepoint(mask)))
        lines.append("".join(parts))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--fps", type=float, default=6.0,
                        help="frame rate (6 is tuned for a maximized software-rendered terminal)")
    parser.add_argument("--frames", type=int, default=0,
                        help="render exactly this many frames; 0 uses duration")
    parser.add_argument("--seed", type=int, default=1993)
    args = parser.parse_args()
    if args.duration <= 0 or args.fps <= 0 or args.frames < 0:
        parser.error("duration and fps must be positive; frames must be non-negative")
    random.seed(args.seed)
    size = shutil.get_terminal_size((100, 30))
    columns, rows = max(40, size.columns), max(16, size.lines)
    started = time.monotonic()
    sys.stdout.write("\x1b]0;PUA Pixel FPS — Hangar Breach\x07\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()
    try:
        frame = 0
        while True:
            if args.frames:
                if frame >= args.frames:
                    break
                t = frame / args.fps
            else:
                t = time.monotonic() - started
                if t >= args.duration:
                    break
            canvas, width, height = render_scene(columns, rows, t, args.duration)
            picture = to_terminal(canvas, width, height, columns, rows)
            sys.stdout.write("\x1b[?2026h\x1b[H" + picture + "\x1b[?2026l")
            sys.stdout.flush()
            deadline = started + (frame + 1) / args.fps
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            frame += 1
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
