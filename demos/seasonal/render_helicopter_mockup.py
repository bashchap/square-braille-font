#!/usr/bin/env python3
"""Render all production helicopter yaw frames as a PNG review contact sheet."""

import argparse
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

from christmas_snow import (CODECS, PUA4_BITS, SnowEngine, Surface,
                            draw_ah64_helicopter, encode_surface, parse_args)


def surface_image(surface, scale):
    """Round-trip through the production PUA4/ANSI encoder before preview."""
    columns, rows = surface.width // 4, surface.height // 4
    encoded = encode_surface(surface, CODECS["pua4"], columns, rows)
    image = Image.new("RGB", (surface.width, surface.height), (3, 7, 10))
    pixels = image.load()
    foreground = None
    background = None
    cell_x = cell_y = 0
    index = 0
    while index < len(encoded):
        if encoded[index] == "\x1b":
            match = re.match(r"\x1b\[([0-9;]*)m", encoded[index:])
            if not match:
                index += 1
                continue
            parameters = match.group(1)
            values = [int(value) for value in parameters.split(";") if value]
            if values[:2] == [38, 2] and len(values) == 5:
                foreground = tuple(values[2:5])
            elif values[:2] == [48, 2] and len(values) == 5:
                background = tuple(values[2:5])
            elif values == [39]:
                foreground = None
            elif values == [49]:
                background = None
            elif not values or values == [0]:
                foreground = background = None
            index += match.end()
            continue
        character = encoded[index]
        index += 1
        if character == "\n":
            cell_x = 0
            cell_y += 1
            continue
        if cell_y >= rows:
            continue
        codepoint = ord(character)
        if 0xF0000 <= codepoint <= 0xF7FFF:
            mask = codepoint - 0xF0000
        elif 0x100000 <= codepoint <= 0x107FFF:
            mask = 0x8000 + codepoint - 0x100000
        else:
            mask = 0
        for local_y in range(4):
            for local_x in range(4):
                colour = background or (3, 7, 10)
                bit = PUA4_BITS[local_y][local_x]
                if mask & (1 << bit) and foreground is not None:
                    colour = foreground
                pixels[cell_x * 4 + local_x,
                       cell_y * 4 + local_y] = colour
        cell_x += 1
    return image.resize((surface.width * scale, surface.height * scale),
                        Image.Resampling.NEAREST)


def render(output, pixel_scale=3, style="helicopter"):
    frame_width, frame_height = 140, 88
    label_height = 20
    columns, rows = 5, 3
    sheet = Image.new(
        "RGB",
        (columns * frame_width * pixel_scale,
         rows * (frame_height * pixel_scale + label_height)),
        (11, 18, 22),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    args = parse_args([
        "--mode", "pua4", "--scenery", "none", "--weather", "none",
        "--sky-events", style, "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    engine = SnowEngine(args, frame_width, frame_height)
    for orientation in range(13):
        surface = Surface(frame_width, frame_height)
        event = {
            "kind": style, "x": frame_width / 2,
            "y": frame_height * 0.58, "direction": 1,
            "event_index": 0, "phase": "heli_takeoff",
            "phase_progress": orientation / 12,
            "scale": 0.88, "orientation": orientation,
        }
        # Offset time makes rotor phase change between adjacent yaw frames.
        draw_ah64_helicopter(surface, engine, orientation * 0.075, event)
        frame = surface_image(surface, pixel_scale)
        column, row = orientation % columns, orientation // columns
        left = column * frame_width * pixel_scale
        top = row * (frame_height * pixel_scale + label_height)
        sheet.paste(frame, (left, top))
        degrees = orientation * 15
        label = ("FRONT" if orientation == 0 else
                 "REAR" if orientation == 12 else f"YAW {degrees:03d}°")
        draw.text((left + 6, top + frame_height * pixel_scale + 3),
                  f"FRAME {orientation:02d}  {label}",
                  fill=(114, 229, 238), font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=None)
    parser.add_argument("--style", choices=("helicopter", "airwolf"),
                        default="helicopter")
    parser.add_argument("--pixel-scale", type=int, default=3)
    options = parser.parse_args()
    if not 1 <= options.pixel_scale <= 8:
        parser.error("--pixel-scale must be in [1,8]")
    output = options.output or Path(
        "outputs/christmas-snow-airwolf-rotation-mockup.png"
        if options.style == "airwolf" else
        "outputs/christmas-snow-ah64-rotation-mockup.png")
    print(render(output, options.pixel_scale, options.style).resolve())


if __name__ == "__main__":
    main()
