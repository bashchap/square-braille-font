#!/usr/bin/env python3
"""Verify curved-vortex motion and two-part font exercise."""

from pua4x4_motion_demo import (
    ColorCanvas,
    VORTEX_DEPTH,
    VORTEX_NEAR,
    ansi_frame,
    background_stars,
    build_frame,
    centreline,
    depth_color,
    make_particles,
    make_stars,
    project,
)


def opening_position(width, height, phase, depth=5.4):
    x, y = centreline(depth, phase)
    return project(depth * x, depth * y, depth, width, height)


def main():
    columns, rows = 238, 54
    width, height = columns * 4, rows * 4
    particles = make_particles()
    stars = make_stars()
    positions = []

    for phase in (0.0, 2.0, 4.0, 6.0, 8.0):
        canvas = build_frame(columns, rows, phase, particles, stars)
        _, part0, part1, blank = ansi_frame(canvas, color=False)
        assert part0 > 0 and part1 > 0
        assert part0 + part1 + blank == columns * rows
        positions.append(opening_position(width, height, phase))

    xs = [point[0] for point in positions]
    ys = [point[1] for point in positions]
    assert max(xs) - min(xs) > width * 0.12
    assert max(ys) - min(ys) > height * 0.12
    assert depth_color(VORTEX_NEAR) == 13
    assert depth_color(VORTEX_DEPTH) == 6

    star_canvas = ColorCanvas(width, height)
    background_stars(star_canvas, 0.0, stars)
    quadrants = [0, 0, 0, 0]
    for character_row, row in enumerate(star_canvas.masks):
        for character_column, mask in enumerate(row):
            if mask:
                quadrant = (character_row >= rows // 2) * 2 + (
                    character_column >= columns // 2
                )
                quadrants[quadrant] += mask.bit_count()
    assert all(count > 80 for count in quadrants), quadrants

    clip_canvas = ColorCanvas(width, height)
    clip_canvas.line(-width, height // 2, width * 2, height // 2)
    assert sum(mask.bit_count() for row in clip_canvas.masks for mask in row) == width

    wide_columns, wide_rows = 320, 70
    wide_canvas = build_frame(wide_columns, wide_rows, 1.0, particles, stars)
    assert len(wide_canvas.masks) == wide_rows
    assert all(len(row) == wide_columns for row in wide_canvas.masks)
    _, wide_part0, wide_part1, wide_blank = ansi_frame(wide_canvas, color=False)
    assert wide_part0 + wide_part1 + wide_blank == wide_columns * wide_rows

    print("PASS: curved vortex moves its opening in both axes")
    print("  opening positions:", positions)
    print("PASS: every sampled frame exercises active Part 0 and Part 1 glyphs")
    print("PASS: near/far brightness gradient and viewport line clipping")
    print("PASS: full-screen starfield covers all four quadrants", quadrants)
    print("PASS: uncapped 320 x 70 character frame (1280 x 280 virtual pixels)")


if __name__ == "__main__":
    main()
