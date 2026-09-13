#!/usr/bin/env python3
"""Verify shared Python/Rust terminal encoding across legacy glyph mappings."""

from native_terminal import (NativeTerminalEncoder, library_path,
                             python_terminal_picture)


def main():
    if not library_path().exists():
        raise SystemExit("build native/seasonal_encoder in release mode first")
    native = NativeTerminalEncoder()
    masks = [[0x0001, 0x0000, 0x0047], [0x00ff, 0x8000, 0xffff]]
    rgb = [[(248, 16, 24), (0, 0, 0), (8, 240, 248)],
           [(248, 16, 24), (40, 208, 96), (40, 208, 96)]]
    indexed = [[196, 0, 51], [196, 46, 46]]
    for mapping in ("square-alias", "braille", "pua4"):
        if mapping != "pua4":
            mode_masks = [[value & 0xff for value in row] for row in masks]
        else:
            mode_masks = masks
        for colours, colour_mode in ((rgb, "rgb"), (indexed, "indexed"),
                                     (indexed, "none"), (rgb, "none")):
            for blank_glyph in (False, True):
                options = dict(mapping=mapping, colour_mode=colour_mode,
                               blank_glyph=blank_glyph,
                               carriage_return=True, reset_at_end=True)
                expected = python_terminal_picture(
                    mode_masks, colours, 3, 2, **options)
                actual = native.encode(mode_masks, colours, 3, 2, **options)
                assert actual == expected, (mapping, colour_mode, blank_glyph)
                if colour_mode == "none":
                    assert "\x1b" not in actual

    layered = native.encode_v2(
        [[1, 0]], [[(255, 0, 0), (0, 0, 0)]],
        [[(0, 0, 255), (0, 0, 0)]], [[1, 0]], 2, 1, mapping="pua4")
    assert "\x1b[38;2;255;0;0m" in layered
    assert "\x1b[48;2;0;0;255m" in layered
    assert chr(0xF0001) in layered and layered.endswith("\x1b[0m")
    print("PASS: Rust legacy encoder matches Python for all glyph/colour modes and layered cells")


if __name__ == "__main__":
    main()
