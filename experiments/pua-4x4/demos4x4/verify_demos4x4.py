#!/usr/bin/env python3
"""Fast, noninteractive structural verification for the PUA 4x4 demo suite."""

import importlib
import sys

import numpy as np

from pua4x4_backend import codepoint_to_mask, mask_to_codepoint


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    boundaries = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF)
    for mask in boundaries:
        check(codepoint_to_mask(mask_to_codepoint(mask)) == mask,
              f"mapping round trip failed for 0x{mask:04X}")

    for name in (
        "geometry_test", "snow", "starfield", "trail", "glyph_editor", "triangle",
        "vertical_probe", "vector_tunnel", "elite_battle", "doom_demo",
        "enterprise_flyby", "enterprise_wireframe", "space_ship_flyby",
        "defender",
    ):
        importlib.import_module(name)

    from glyph_editor import current_font_bit, mapping_details, requested_bit
    check(requested_bit(1, 2) == 10, "requested MSB-left bit calculation failed")
    detail = mapping_details(3, 2, 1, 2, 0x0400)
    check(detail["virtual_column"] == 13 and detail["virtual_row"] == 10,
          "editor virtual-coordinate calculation failed")
    check(detail["terminal_column"] == 4 and detail["terminal_row"] == 3,
          "editor ANSI-coordinate calculation failed")
    check(detail["bit"] == 10 and detail["value"] == 1024,
          "editor bit/value calculation failed")
    check(detail["codepoint"] == 0xF0400,
          "editor codepoint calculation failed")
    check(current_font_bit(1, 2) == requested_bit(1, 2) == 10,
          "editor/font MSB-left mapping agreement failed")

    from vector_tunnel import FrameBuffer
    frame = FrameBuffer(2, 1)
    for y in range(4):
        for x in range(8):
            frame.pixel(x, y, (255, 255, 255))
    check(frame.width == 8 and frame.height == 4, "wrong virtual dimensions")
    check(frame.masks == [[0xFFFF, 0xFFFF]], "4x4 cell packing failed")
    check(frame.terminal_picture().count(chr(0x107FFF)) == 2,
          "Part 1 full-cell glyph not emitted")

    from defender import render_scene
    defender = render_scene(40, 16, 95.0)
    check(defender.width == 160 and defender.height == 64,
          "Defender virtual dimensions are not 4x4")
    check(any(any(row) for row in defender.masks), "Defender frame is blank")

    import enterprise_flyby
    import enterprise_wireframe
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    rgb[:4, :4] = 255
    for renderer in (enterprise_flyby, enterprise_wireframe):
        check(chr(0x107FFF) in renderer.image_to_terminal(rgb),
              f"{renderer.__name__} did not pack a full 4x4 Part 1 cell")

    print("PASS: all PUA 4x4 demo modules, mappings and packers verified")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise
