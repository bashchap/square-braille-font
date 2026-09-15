#!/usr/bin/env python3
"""Deterministic structural checks for the Christmas snow demo."""

import json
import math
import os
import random
import tempfile
from pathlib import Path

from christmas_snow import (
    CONTROL_FORMAT,
    CODECS,
    SHAPES,
    CometParticle,
    ControlListener,
    GroundExplosion,
    SnowEngine,
    Surface,
    build_parser,
    build_scenery,
    cached_postman_pixels,
    npc_figure_height,
    npc_ground_y,
    cabin_door_targets,
    cabin_path_network,
    cabin_door_rect,
    cabin_layout,
    complete_frame,
    compact_flyby_unit,
    current_sky_event,
    current_sky_event_state,
    dashboard_rows,
    draw_ambient,
    draw_ah64_helicopter,
    draw_aircraft_crashes,
    draw_conifer,
    draw_cabin,
    draw_cabin_paths,
    draw_cached_tree,
    draw_clouds,
    draw_npc,
    draw_postman,
    draw_rabbit,
    draw_reindeer,
    draw_sky_event,
    draw_sky_gradient,
    draw_lightning,
    draw_parachutists,
    draw_precipitation,
    draw_tree,
    encode_surface,
    encode_surface_native,
    make_runtime,
    helicopter_landing_x,
    safe_helicopter_landing_x,
    settle_frame_deadline,
    parse_args,
    parse_ambient,
    parse_scenery,
    pretty_help,
    render_surface,
    reindeer_apparent_height,
    sky_event_margin,
    tumbleweed_states,
    viewer_quit_key,
)
from christmas_snow_control import Controller, namespace_to_argv, tui_parser
from christmas_snow_native import load_native_analyser


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def filled_surface(codec):
    surface = Surface(codec.cell_width, codec.cell_height)
    for y in range(codec.cell_height):
        for x in range(codec.cell_width):
            surface.pixel(x, y, (255, 255, 255), 10)
    return surface


def painted_bounds(surface):
    points = [(index % surface.width, index // surface.width)
              for index, pixel in enumerate(surface.pixels) if pixel is not None]
    if not points:
        return 0, 0
    return (max(x for x, _ in points) - min(x for x, _ in points) + 1,
            max(y for _, y in points) - min(y for _, y in points) + 1)


def main():
    check(parse_scenery("all") == frozenset(("trees", "cabin", "reindeer")),
          "the all-scenery preset is incomplete")
    check(parse_scenery("trees", reindeer=True) == frozenset(("trees", "reindeer")),
          "the additive reindeer flag is not honoured")
    check(parse_ambient("all") == frozenset(("leaves", "tumbleweed")),
          "the all-ambient preset is incomplete")
    large_only = parse_args(["--flake-sizes", "large"])
    check(large_only.flake_sizes == ("large",) and
          len(large_only.size_weights) == 1,
          "a flake-size-only CLI change did not derive matching weights")
    sky_args = parse_args([
        "--sky-colours", "000000,808080,FFFFFF",
        "--sky-stops", "0,0.5,1", "--sky-blend", "linear",
    ])
    sky_surface = Surface(2, 5)
    draw_sky_gradient(sky_surface, sky_args)
    sky_rows = [sky_surface.pixels[row * 2][0] for row in range(5)]
    check(sky_rows == [(0, 0, 0), (64, 64, 64), (128, 128, 128),
                       (192, 192, 192), (255, 255, 255)],
          "configurable linear sky did not honour colours and stops")
    defaults = parse_args([])
    check(defaults.santa_trail_length == 3.0 and
          defaults.santa_trail_seconds == 5.6,
          "Santa trail defaults are not 3x spatial and 2x persistence")
    check(defaults.tree_trunk_thickness == 4.2 and
          defaults.tree_branch_thickness_ratio == 0.42,
          "tree trunk and independently tapered branch defaults regressed")
    for name, points in SHAPES.items():
        occupied = set(points)
        solid_square = any(
            {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)} <= occupied
            for x, y in occupied)
        check(not solid_square, f"{name} snow geometry still contains a big square block")
    check(not viewer_quit_key("\x1b[B") and viewer_quit_key("\x1b"),
          "Down-arrow escape sequence is still treated as viewer Escape")
    delay, schedule_base, lag = settle_frame_deadline(10.0, 10.2)
    check(delay == 0 and schedule_base == 10.2 and abs(lag - 0.2) < 1e-9,
          "missed frame deadline still retains a stale catch-up schedule")

    rain_args = parse_args([
        "--weather", "rain", "--snow-rate", "20", "--max-flakes", "12",
        "--preload-seconds", "1", "--rain-length", "7",
    ])
    rain_engine = SnowEngine(rain_args, 80, 40)
    check(rain_engine.flakes and all(item.kind == "rain" for item in rain_engine.flakes),
          "rain mode created a non-rain particle")
    for index, particle in enumerate(rain_engine.flakes):
        particle.x = 5 + index * 5
        particle.y = 12 + index % 5
    rain_surface = Surface(80, 40)
    draw_precipitation(rain_surface, rain_engine)
    check(sum(pixel is not None for pixel in rain_surface.pixels) > len(rain_engine.flakes),
          "rain did not render visible streak geometry")

    background_args = parse_args([
        "--weather", "rain", "--weather-foreground-share", "0",
        "--snow-rate", "20", "--max-flakes", "12", "--preload-seconds", "1",
    ])
    foreground_args = parse_args([
        "--weather", "rain", "--weather-foreground-share", "1",
        "--snow-rate", "20", "--max-flakes", "12", "--preload-seconds", "1",
    ])
    background_engine = SnowEngine(background_args, 80, 40)
    foreground_engine = SnowEngine(foreground_args, 80, 40)
    check(all(item.layer == "background" for item in background_engine.flakes) and
          all(item.layer == "foreground" for item in foreground_engine.flakes),
          "precipitation was not assigned to its configured depth at creation")
    cover = Surface(80, 40)
    cover_colour = (24, 88, 42)
    cover.rectangle(0, 0, 80, 40, cover_colour, 14)
    for layered_engine in (background_engine, foreground_engine):
        layered_engine.flakes = layered_engine.flakes[:1]
        layered_engine.flakes[0].x = 40
        layered_engine.flakes[0].y = 20
    background_pixel = render_surface(cover, background_engine).pixels[20 * 80 + 40]
    foreground_pixel = render_surface(cover, foreground_engine).pixels[20 * 80 + 40]
    check(background_pixel[0] == cover_colour and
          foreground_pixel[0] == foreground_args.rain_colour,
          "precipitation layers did not render behind/in front of scenery")

    clear_args = parse_args([
        "--weather", "none", "--lightning", "--snow-rate", "100",
        "--max-flakes", "100", "--preload-seconds", "4",
    ])
    clear_engine = SnowEngine(clear_args, 80, 40)
    clear_engine.lightning_remaining = 1.0
    clear_engine.step(0.1, 0.1)
    check(not clear_engine.flakes and clear_engine.lightning_remaining == 0,
          "weather none did not suppress precipitation and lightning")

    hail_args = parse_args([
        "--weather", "hail", "--hail-bounce", "1", "--hail-size", "2",
        "--snow-rate", "0", "--max-flakes", "1", "--preload-seconds", "0",
        "--initial-snow", "0",
    ])
    hail_engine = SnowEngine(hail_args, 80, 40)
    hailstone = hail_engine.new_flake()
    hailstone.x = 30
    hailstone.y = hail_engine.surface_y(30) - 2
    hailstone.speed = 20
    hail_engine.flakes = [hailstone]
    hail_engine.step(0.1, 0.0)
    check(hailstone.kind == "hail" and hailstone.bounces == 1 and hailstone.speed < 0,
          "hailstone did not bounce from the terrain")

    lightning_args = parse_args([
        "--lightning", "--lightning-branches", "5", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    lightning_engine = SnowEngine(lightning_args, 120, 60)
    lightning_engine.lightning_remaining = lightning_args.lightning_flash
    lightning_surface = Surface(120, 60)
    draw_sky_gradient(lightning_surface, lightning_args)
    draw_lightning(lightning_surface, lightning_engine)
    check(any(pixel is not None and pixel[1] >= 57
              for pixel in lightning_surface.pixels) and
          any(pixel is not None and pixel[0] == (36, 92, 255)
              for pixel in lightning_surface.pixels),
          "lightning created no white/cyan bolt with a strong blue edge")

    spruce = Surface(100, 100)
    draw_conifer(spruce, random.Random(4), 50, 90, 80, 4, 0,
                 "spruce", 5, 27, 2.2, sway=8)
    trunk_pixels = [index // spruce.width
                    for index, pixel in enumerate(spruce.pixels)
                    if pixel is not None and pixel[0] == (82, 61, 45)]
    check(trunk_pixels and min(trunk_pixels) >= 77,
          "spruce still paints a full-height stationary trunk behind its crown")

    square = CODECS["square"]
    pua4 = CODECS["pua4"]
    check(chr(0x28FF) in encode_surface(filled_surface(square), square, 1, 1),
          "Square Braille full mask did not map to U+28FF")
    full_stats = {}
    full_cell = encode_surface(filled_surface(pua4), pua4, 1, 1, full_stats)
    check(chr(0x107FFF) in full_cell,
          "PUA 4x4 full mask did not map to U+107FFF")
    check("\x1b[38;2;252;252;252;48;2;252;252;252m" in full_cell and
          full_stats["seam_guard_cells"] == 1 and
          full_stats["background_cells"] == 0,
          "full-mask glyph lacks its same-colour terminal seam guard")

    single = Surface(4, 4)
    single.pixel(0, 0, (255, 255, 255), 10)
    check(chr(0xF0008) in encode_surface(single, pua4, 1, 1),
          "PUA 4x4 top-left pixel did not use MSB-left mask 0x0008")

    indexed = Surface(3, 6)
    indexed.rectangle(0, 1, 1, 4, (1, 2, 3), 1)
    indexed.pixel(0, 5, (1, 2, 3), 1)
    indexed.rectangle(2, 0, 3, 6, (1, 2, 3), 1)
    check(indexed.exposed_top_edges() == [[1, 5], [], [0]],
          "draw-time scenery occupancy index disagrees with exposed runs")

    no_physics_args = parse_args([
        "--physics", "none", "--columns", "24", "--rows", "8",
        "--object-snow", "--snow-rate", "0", "--max-flakes", "0",
    ])
    _, _, no_physics_engine, no_physics_background = make_runtime(
        no_physics_args, 24, 8)
    check(not no_physics_engine.scenery_surfaces and
          not no_physics_engine.physics.ground_enabled and
          not no_physics_engine.physics.object_enabled,
          "physics=none retained a collision index or physical subsystem")

    ground_args = parse_args([
        "--physics", "ground", "--columns", "24", "--rows", "8",
        "--object-snow", "--snow-rate", "0", "--max-flakes", "0",
    ])
    _, _, ground_engine, _ = make_runtime(ground_args, 24, 8)
    check(ground_engine.physics.ground_enabled and
          not ground_engine.physics.object_enabled,
          "physics=ground did not isolate bank/body physics from object snow")

    ownership = Surface(4, 4)
    for y in range(4):
        for x in range(4):
            ownership.pixel(x, y, (0, 120, 70), 20)
    ownership.pixel(3, 3, (255, 255, 255), 90)
    encoded = encode_surface(ownership, pua4, 1, 1)
    check(chr(0xF1000) in encoded,
          "the high-priority bottom-right flake did not own the overlapping cell")
    check("48;2;" in encoded,
          "the dense rear tree was not retained as the cell background")
    check("\x1b[7m" not in encoded,
          "renderer introduced reverse video")

    args = parse_args([
        "--mode", "pua4", "--columns", "160", "--rows", "14",
        "--scenery", "all", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--initial-snow", "0.51",
        "--shed-threshold", "0.50", "--shed-to", "0.36", "--seed", "4",
        "--tree-sway", "6", "--ambient", "all",
    ])
    codec, rows, engine, background = make_runtime(args, 40, 14)
    check(codec is pua4 and rows == 13, "dashboard row was not reserved correctly")
    check(any(pixel is not None for pixel in background.pixels),
          "all-scenery preset rendered a blank background")
    before = max(engine.depths)
    engine.step(1.0 / args.fps, 0.0)
    check(engine.shed_count == 1 and max(engine.depths) < before,
          "50-percent accumulation did not start a fall-away")
    frame = encode_surface(render_surface(background, engine), codec, 40, rows)
    check(len(frame.splitlines()) == rows, "rendered frame has the wrong row count")
    check("\x1b[7m" not in frame,
          "rendered frame introduced forbidden reverse-video semantics")

    old_fraction = engine.maximum_depth_fraction
    engine.resize(engine.width * 2, engine.height * 2)
    check(engine.width == 320 and engine.height == 104,
          "live resize did not adopt the new virtual dimensions")
    check(abs(engine.maximum_depth_fraction - old_fraction) < 0.02,
          "live resize did not preserve relative bank depth")

    _, _, motion_engine, still = make_runtime(args, 40, 14)
    from christmas_snow import build_scenery
    fixed_ground = motion_engine.scenery_ground_y
    motion_engine.depths = [motion_engine.height * 0.75] * motion_engine.width
    anchored = build_scenery(args, still.width, still.height, fixed_ground, 0.0)
    check(anchored.pixels == still.pixels,
          "accumulated snow changed the immutable scenery baseline")
    swayed = build_scenery(args, still.width, still.height,
                           motion_engine.scenery_ground_y, 1.7)
    check(still.pixels != swayed.pixels, "tree wind animation did not alter the scenery")

    # The scanline sway cache is an optimization only: it must remain exactly
    # equivalent to the former height calculation in the per-pixel loop.
    tree_pixels = tuple(
        (dx, dy, (40 + (dx % 4) * 15, 90 + (dy % 5) * 8, 55), 20 + dy % 3)
        for dy in range(-66, 7) for dx in range(-18, 19)
        if (dx * 3 + dy * 5) % 7 < 3
    )
    cached_sway_surface = Surface(100, 90)
    reference_sway_surface = Surface(100, 90)
    draw_cached_tree(cached_sway_surface, 50, 80, 66, 5.75, tree_pixels)
    for dx, dy, colour, priority in tree_pixels:
        crown_fraction = max(0.0, min(1.0, -dy / 66.0))
        offset = int(round(5.75 * crown_fraction * crown_fraction))
        reference_sway_surface.pixel(50 + dx + offset, 80 + dy,
                                     colour, priority)
    check(cached_sway_surface.pixels == reference_sway_surface.pixels,
          "scanline-cached tree sway differs from the per-pixel reference")

    cabin_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "auto",
        "--snow-rate", "0", "--max-flakes", "0", "--ambient", "none",
    ])
    narrow_cabins = cabin_layout(cabin_args, 400, 100, 86)
    wide_cabins = cabin_layout(cabin_args, 1600, 100, 86)
    check(len(narrow_cabins) == 1 and len(wide_cabins) > len(narrow_cabins),
          "automatic cabin distribution did not add cabins as width increased")
    check(narrow_cabins[0][2] == wide_cabins[0][2],
          "cabin geometry stretched when only viewport width changed")
    varied_cabins = cabin_layout(cabin_args, 1600, 100, 86)
    check({item[4] for item in varied_cabins}.issubset({"cottage", "lodge", "a-frame"}),
          "cabin layout emitted an unknown archetype")
    cabin_args.cabin_count = 3
    three_types = cabin_layout(cabin_args, 1600, 100, 86)
    check(len({item[4] for item in three_types}) == 3 and
          len({item[2] for item in three_types}) > 1,
          "cabins did not vary both archetype and size")
    cabin_args.cabin_depth_share = 1.0
    cabin_args.cabin_depth_scale = 0.42
    distant_cabins = cabin_layout(cabin_args, 1600, 100, 86)
    check(all(item[2] < 18 and item[1] < 80 for item in distant_cabins),
          "distant cabins were not scaled and elevated toward the horizon")
    cabin_args.cabin_depth_share = 0.34
    cabin_args.cabin_depth_scale = 0.56
    aframe_surface = Surface(120, 100)
    draw_cabin(aframe_surface, 60, 92, 44, cabin_type="a-frame")
    roof_colour = (102, 35, 40)
    painted_rows = []
    for y in range(25, 92):
        xs = [x for x in range(120)
              if aframe_surface.pixels[y * 120 + x] is not None]
        if xs:
            painted_rows.append((y, min(xs), max(xs)))
    check(len(painted_rows) >= 55 and
          all(right - left >= 1 for _, left, right in painted_rows[1:]) and
          any(pixel is not None and pixel[0] == roof_colour
              for pixel in aframe_surface.pixels),
          "A-frame cabin did not retain continuous clean filled edges")
    door_left, door_top, door_right, door_bottom = cabin_door_rect(
        60, 92, 44, "a-frame")
    aframe_width = max(16, int(round(44 * 1.48)))
    check(door_left > 60 - aframe_width * 0.44 and
          door_right < 60 + aframe_width * 0.44 and
          door_top < door_bottom <= 92,
          "A-frame door escaped the inset triangular wall bounds")

    reindeer_surface = Surface(320, 130)
    draw_reindeer(reindeer_surface, 320, 130, 112)
    reindeer_pixels = [pixel for pixel in reindeer_surface.pixels if pixel is not None]
    reindeer_colours = {pixel[0] for pixel in reindeer_pixels}
    check(len(reindeer_pixels) > 200 and len(reindeer_colours) >= 9,
          "foreground reindeer lacks anatomical and seasonal detail")

    large_reindeer = Surface(672, 216)
    draw_reindeer(large_reindeer, 672, 216, 194)
    deer_width, deer_height = painted_bounds(large_reindeer)
    check(deer_width <= 70 and deer_height <= 65,
          "foreground reindeer regressed to its oversized former footprint")

    tree_args = parse_args([
        "--mode", "pua4", "--tree-types", "all", "--tree-branches", "6",
        "--tree-branch-levels", "4", "--tree-branch-angle", "31",
        "--tree-length-ratio", "0.66", "--tree-trunk-thickness", "2.8",
        "--snow-rate", "0", "--max-flakes", "0", "--ambient", "none",
    ])
    tree_signatures = []
    for tree_index, tree_type in enumerate(tree_args.tree_types):
        tree_surface = Surface(180, 130)
        draw_tree(tree_surface, random.Random(900 + tree_index), 90, 124, 102,
                  4, 0.25, tree_type, tree_args, sway=2.0,
                  segment_budget=[2000])
        pixels = [pixel for pixel in tree_surface.pixels if pixel is not None]
        tree_signatures.append((len(pixels), len({pixel[0] for pixel in pixels})))
    check("maple" in tree_args.tree_types and len(set(tree_signatures)) >= 5 and
          all(count > 50 for count, _ in tree_signatures),
          "procedural tree families are missing or visually indistinct")
    branch_counts = []
    for ratio in (0.20, 0.90):
        ratio_args = parse_args([
            "--tree-types", "oak", "--tree-trunk-thickness", "4.2",
            "--tree-branch-thickness-ratio", str(ratio),
            "--tree-branches", "5", "--tree-branch-levels", "3",
        ])
        ratio_surface = Surface(180, 130)
        draw_tree(ratio_surface, random.Random(88), 90, 124, 102, 4, 0,
                  "oak", ratio_args, segment_budget=[2000])
        colours = [pixel[0] for pixel in ratio_surface.pixels if pixel is not None]
        branch_counts.append(colours.count((104, 69, 48)))
    check(branch_counts[1] > branch_counts[0] * 1.35,
          "branch thickness is not independently adjustable from main trunk thickness")
    conifer_colours = []
    for variation in (0, 60):
        variation_args = parse_args([
            "--tree-types", "pine", "--conifer-colour-variation", str(variation),
        ])
        variation_surface = Surface(180, 130)
        draw_tree(variation_surface, random.Random(188), 90, 124, 102, 4, 0,
                  "pine", variation_args, segment_budget=[2000])
        conifer_colours.append({pixel[0] for pixel in variation_surface.pixels
                                if pixel is not None})
    check(conifer_colours[0] != conifer_colours[1],
          "configurable conifer colour separation did not alter pine rendering")

    tumble_args = parse_args([
        "--mode", "pua4", "--columns", "80", "--rows", "20",
        "--scenery", "none", "--ambient", "tumbleweed",
        "--tumbleweed-count", "1", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--wind", "5", "--gust-strength", "4",
    ])
    _, _, tumble_engine, tumble_background = make_runtime(tumble_args, 80, 20)
    at_rest = tumble_background.copy()
    draw_ambient(at_rest, tumble_engine, 0.0)
    for step in range(13):
        tumble_engine.step_tumbleweeds(0.1, step * 0.1)
    rolling = tumble_background.copy()
    draw_ambient(rolling, tumble_engine, 1.3)
    check(at_rest.pixels != rolling.pixels,
          "tumbleweed geometry did not translate and rotate over time")
    check(sum(pixel is not None and pixel[1] >= 77 for pixel in rolling.pixels) >= 12,
          "tumbleweed body lacks enough visible structure")
    check(all(pixel is None or pixel[0] != (96, 112, 111)
              for pixel in rolling.pixels),
          "tumbleweed contact shadow was unexpectedly rendered")

    barrier_args = parse_args([
        "--mode", "pua4", "--ambient", "tumbleweed",
        "--tumbleweed-count", "1", "--ambient-speed", "10", "--wind", "3",
        "--tumbleweed-climb", "0.5", "--tumbleweed-collapse-pressure", "12",
        "--tower-age", "0.2", "--tower-age-jitter", "0",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    barrier_engine = SnowEngine(barrier_args, 100, 60)
    barrier_engine.depths = [2.0] * 100
    for x in range(50, 58):
        barrier_engine.depths[x] = 24.0
    weed = barrier_engine.tumbleweeds[0]
    weed.x, weed.y, weed.direction, weed.speed = 49.0, 54.0, 1, 10.0
    for step in range(8):
        barrier_engine.step_tumbleweeds(0.1, step * 0.1)
    check(weed.x < 50 and barrier_engine.tumbleweed_blocks > 0 and
          barrier_engine.tumbleweed_collapses >= 1,
          "over-height snow did not block the tumbleweed and load a collapse")

    smooth_args = parse_args([
        "--mode", "pua4", "--snow-relaxation", "20",
        "--snow-repose-slope", "1", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    smooth_engine = SnowEngine(smooth_args, 41, 40)
    smooth_engine.depths = [0.0] * 41
    smooth_engine.depths[20] = 20.0
    before_slope = max(abs(left - right) for left, right in zip(
        smooth_engine.depths, smooth_engine.depths[1:]))
    for _ in range(20):
        smooth_engine.physics.relax_bank(smooth_engine.depths, 0.05)
    after_slope = max(abs(left - right) for left, right in zip(
        smooth_engine.depths, smooth_engine.depths[1:]))
    check(after_slope < before_slope * 0.45,
          "angle-of-repose relaxation did not smooth a narrow ground spike")

    object_args = parse_args([
        "--mode", "pua4", "--object-snow-capture", "1",
        "--object-snow-adhesion", "0", "--object-snow-hold", "30",
        "--object-snow-hold-jitter", "0", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    object_engine = SnowEngine(object_args, 80, 50)
    object_flake = object_engine.new_flake()
    object_flake.x = 20
    check(object_engine.catch_object_snow(object_flake, 18),
          "scenery impact was not retained at forced capture probability")
    object_engine.step_object_snow(0.1)
    check(not object_engine.resting_snow and object_engine.object_snow_shed == 1 and
          object_engine.chunks,
          "overweight object snow did not shed under gravity")

    rabbit_args = parse_args([
        "--mode", "pua4", "--ambient", "tumbleweed", "--tumbleweed-count", "1",
        "--rabbit-count", "1", "--rabbit-interval", "10", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0", "--wind", "5",
    ])
    rabbit_engine = SnowEngine(rabbit_args, 240, 100)
    weed = tumbleweed_states(rabbit_args, rabbit_engine, 1.0)[0]
    rabbit = rabbit_engine.rabbits[0]
    rabbit.x, rabbit.state, rabbit.timer = weed[1], "eating", 5.0
    rabbit_engine.step_rabbits(0.1, 1.0)
    check(rabbit.state == "startled" and rabbit_engine.rabbit_reactions == 1,
          "rabbit did not react to a nearby tumbleweed")
    rabbit_surface = Surface(rabbit_engine.width, rabbit_engine.height)
    draw_rabbit(rabbit_surface, rabbit_engine, rabbit)
    check(any(pixel is not None and pixel[1] >= 86 for pixel in rabbit_surface.pixels),
          "active rabbit produced no visible terrain-following geometry")

    depth_args = parse_args([
        "--mode", "pua4", "--rabbit-count", "2", "--rabbit-speed", "20",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
        "--scenery", "none", "--no-snow-plough", "--no-postman",
    ])
    depth_engine = SnowEngine(depth_args, 200, 100)
    near, far = depth_engine.rabbits
    check(near.depth > 0.68 > far.depth,
          "rabbit creation did not provide persistent near and far lanes")
    for rabbit in (near, far):
        rabbit.x, rabbit.state, rabbit.phase = 80.0, "hopping", 0.0
    depth_engine.step_rabbits(0.25, 0.0)
    check(near.x - 80.0 > far.x - 80.0,
          "far rabbit did not move more slowly under perspective parallax")
    near.x = far.x = 80.0
    near_surface = Surface(200, 100)
    far_surface = Surface(200, 100)
    draw_rabbit(near_surface, depth_engine, near)
    draw_rabbit(far_surface, depth_engine, far)
    check(painted_bounds(near_surface)[1] > painted_bounds(far_surface)[1],
          "far rabbit was not smaller than a near rabbit")
    cover = Surface(200, 100)
    cover.rectangle(72, 65, 90, 100, (9, 81, 44), 20)
    far.x, far.state = 80.0, "eating"
    near.state = "hidden"
    layered_far = render_surface(cover, depth_engine)
    far_centre = layered_far.pixels[85 * 200 + 80]
    check(far_centre is not None and far_centre[0] == (9, 81, 44),
          "far rabbit was not occluded by foreground scenery")
    far.state, near.state, near.x = "hidden", "eating", 80.0
    layered_near = render_surface(cover, depth_engine)
    check(any(pixel is not None and pixel[0] == (174, 155, 135)
              for pixel in layered_near.pixels),
          "near rabbit was not rendered in front of scenery")

    cabin_depth_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "1",
        "--cabin-types", "cottage", "--rabbit-count", "2",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
        "--no-snow-plough", "--no-postman",
    ])
    cabin_depth_engine = SnowEngine(cabin_depth_args, 240, 100)
    cabin_background = build_scenery(
        cabin_depth_args, 240, 100, cabin_depth_engine.scenery_ground_y, 0.0)
    cabin_centre = cabin_layout(
        cabin_depth_args, 240, 100,
        int(round(cabin_depth_engine.scenery_ground_y)))[0][0]
    cabin_depth_engine.rabbits[0].state = "hidden"
    far_cabin_rabbit = cabin_depth_engine.rabbits[1]
    far_cabin_rabbit.x, far_cabin_rabbit.state = cabin_centre, "eating"
    cabin_layered = render_surface(cabin_background, cabin_depth_engine)
    rabbit_colours = {(174, 155, 135), (116, 96, 84), (236, 226, 214)}
    check(not any(pixel is not None and pixel[0] in rabbit_colours
                  for pixel in cabin_layered.pixels),
          "far rabbit feet leaked below the cabin occlusion footprint")

    npc_args = parse_args([
        "--mode", "pua4", "--scenery", "none", "--rabbit-count", "0",
        "--npc-count", "3", "--npc-speed-min", "10",
        "--npc-speed-max", "10", "--npc-decision-min-seconds", "0.1",
        "--npc-decision-max-seconds", "0.1", "--npc-response-seconds", "0.05",
        "--npc-object-awareness", "0", "--npc-avoidance-strength", "0",
        "--npc-crossing-motivation-min", "0",
        "--npc-crossing-motivation-max", "0", "--npc-wander-angle", "180",
        "--npc-reversal-chance", "0", "--npc-side-spawn-share", "1",
        "--npc-respawn-seconds", "0.1", "--npc-depth-min", "0.2",
        "--npc-depth-max", "1", "--npc-social-factor", "0",
        "--npc-social-distance", "0", "--npc-track-id", "1",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
        "--no-snow-plough", "--no-postman",
    ])
    npc_engine = SnowEngine(npc_args, 240, 100)
    check(len(npc_engine.npcs) == 3 and
          len({npc.colour for npc in npc_engine.npcs}) == 3,
          "npc population did not receive distinct configured colours")
    postal_pixels = cached_postman_pixels(24, 1, 3, 0, False)
    cached_postman_pixels(24, 1, 3, 0, False, (46, 134, 171))
    check(cached_postman_pixels(24, 1, 3, 0, False) == postal_pixels,
          "NPC colour rasterization changed the postman's cached gait")
    near_npc, far_npc = npc_engine.npcs[:2]
    near_npc.x, near_npc.depth = 60.0, 1.0
    far_npc.x, far_npc.depth = 140.0, 0.25
    for npc in (near_npc, far_npc):
        npc.heading = npc.desired_heading = 0.0
        npc.decision_timer = 10.0
        npc.state = "walking"
    npc_engine.step_npcs(0.5)
    check(near_npc.x - 60.0 > far_npc.x - 140.0,
          "npc speed did not use perspective parallax")
    check(npc_figure_height(npc_engine, near_npc) >
          npc_figure_height(npc_engine, far_npc) and
          npc_ground_y(npc_engine, near_npc) >
          npc_ground_y(npc_engine, far_npc),
          "npc depth did not control both scale and projected terrain position")

    # Ground actors must not use the particle system's cyclic x lookup. With
    # very different edge banks, the old modulo sample jumped an NPC between
    # the right and left terrain heights while it crossed x=0.
    edge_args = parse_args([
        "--mode", "pua4", "--scenery", "none", "--rabbit-count", "0",
        "--npc-count", "1", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--no-snow-plough", "--no-postman",
    ])
    edge_engine = SnowEngine(edge_args, 120, 80)
    edge_engine.depths = [0.0] * edge_engine.width
    edge_engine.depths[-5:] = [edge_engine.height * 0.80] * 5
    edge_npc = edge_engine.npcs[0]
    edge_npc.depth = 0.75
    edge_npc.x = -0.20
    before_edge = npc_ground_y(edge_engine, edge_npc)
    edge_npc.x = 0.20
    after_edge = npc_ground_y(edge_engine, edge_npc)
    check(abs(after_edge - before_edge) < 1.0,
          "npc terrain projection wrapped to the opposite viewport edge")

    edge_engine.depths = [edge_engine.height * 0.86] * edge_engine.width
    edge_npc.depth = edge_args.npc_depth_min
    horizon_y = edge_engine.height * edge_args.horizon_height
    check(npc_ground_y(edge_engine, edge_npc) >= horizon_y + 0.5,
          "distant NPC feet projected above the artificial horizon")
    normal_height = npc_figure_height(npc_engine, near_npc)
    npc_args.npc_depth_max = 1.4
    npc_args.npc_viewport_respawn_chance = 0.0
    near_npc.depth = 1.39
    near_npc.heading = near_npc.desired_heading = math.pi * 0.5
    near_npc.decision_timer = 10.0
    npc_engine.step_npcs(0.1)
    check(near_npc.state == "viewport_turn" and
          math.sin(near_npc.heading) < 0 and
          npc_figure_height(npc_engine, near_npc) > normal_height * 1.35 and
          npc_engine.npc_viewport_turns == 1,
          "near NPC did not enlarge and immediately turn at the viewport")
    old_depth, old_x = far_npc.depth, far_npc.x
    far_npc.heading = far_npc.desired_heading = math.pi * 0.5
    far_npc.decision_timer = 10.0
    npc_engine.step_npcs(0.25)
    check(far_npc.depth > old_depth and abs(far_npc.x - old_x) < 0.1,
          "a 90-degree npc heading was not projected as pure depth movement")
    npc_args.npc_reversal_chance = 1.0
    old_direction = near_npc.crossing_direction
    near_npc.decision_timer = 0.0
    npc_engine.step_npcs(0.01)
    check(near_npc.crossing_direction == -old_direction and
          npc_engine.npc_direction_changes > 0,
          "npc reversal and decision timing controls were not applied")
    old_generation = near_npc.generation
    near_npc.x = npc_engine.width + 100
    npc_engine.step_npcs(0.01)
    check(near_npc.state == "hidden",
          "out-of-bounds npc did not leave its active slot")
    npc_engine.step_npcs(0.2)
    check(near_npc.state != "hidden" and
          near_npc.generation == old_generation + 1,
          "out-of-bounds npc slot did not spawn a replacement identity")
    far_npc.x, far_npc.depth = 90.0, 0.30
    far_npc.heading = far_npc.desired_heading = 0.0
    far_npc.state = "walking"
    cover = Surface(240, 100)
    cover.rectangle(70, 0, 110, 100, (9, 81, 44), 20)
    far_composite = render_surface(cover, npc_engine)
    check(not any(pixel is not None and pixel[0] == far_npc.colour
                  for pixel in far_composite.pixels),
          "distant npc was not occluded by foreground scenery")
    far_npc.depth = 0.90
    near_composite = render_surface(cover, npc_engine)
    check(any(pixel is not None and pixel[0] == far_npc.colour
              for pixel in near_composite.pixels),
          "near npc did not render in front of foreground scenery")
    tracked_surface = Surface(240, 100)
    tracked = npc_engine.npcs[1]
    tracked.x, tracked.depth, tracked.state = 120.0, 0.9, "walking"
    draw_npc(tracked_surface, npc_engine, tracked)
    check(any(pixel is not None and pixel[0] == (54, 235, 240)
              for pixel in tracked_surface.pixels),
          "tracked npc did not receive its visible locator marker")

    social_args = parse_args([
        "--mode", "pua4", "--scenery", "none", "--rabbit-count", "0",
        "--npc-count", "2", "--npc-object-awareness", "0",
        "--npc-social-factor", "1", "--npc-social-distance", "80",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
        "--no-postman", "--no-snow-plough",
    ])
    social_engine = SnowEngine(social_args, 240, 100)
    first_social, second_social = social_engine.npcs
    first_social.x, first_social.depth = 80.0, 0.6
    second_social.x, second_social.depth = 110.0, 0.6
    steering = social_engine.npc_steering(first_social)
    check(steering[2] > 0 and not steering[4],
          "positive npc social factor did not attract a neighbour")

    postman_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "1",
        "--postman", "--postman-interval", "1", "--postman-speed", "80",
        "--postman-stop-seconds", "0.5", "--rabbit-count", "0",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    postman_engine = SnowEngine(postman_args, 240, 100)
    postman_engine.postman.timer = 0
    postman_engine.step_postman(0.01)
    road_height = postman_engine.postman.road_figure_height
    door_height = postman_engine.postman.door_figure_height
    check(postman_engine.postman.state == "walking_to" and
          road_height >= door_height * 1.45,
          "postman did not enter at the enlarged road scale")
    visited_states = {postman_engine.postman.state}
    linear_scale_error = 0.0
    for _ in range(1600):
        postman_engine.step_postman(0.02)
        postman = postman_engine.postman
        visited_states.add(postman.state)
        if postman.state in ("approaching", "returning"):
            if postman.state == "approaching":
                progress = postman.route_progress
                expected = road_height + (door_height - road_height) * progress
            else:
                progress = 1.0 - postman.route_progress
                expected = door_height + (road_height - door_height) * progress
            linear_scale_error = max(
                linear_scale_error, abs(postman.figure_height - expected))
        if postman_engine.postman_delivery_count and postman.state == "walking_on":
            break
    expected_states = {"turning_in", "approaching", "posting", "waiting",
                       "turning_from_house", "returning", "turning_out",
                       "walking_on"}
    check(postman_engine.postman_delivery_count == 1 and
          expected_states.issubset(visited_states) and
          linear_scale_error < 1e-6 and
          abs(postman_engine.postman.figure_height - road_height) < 1e-6 and
          postman_engine.postman_snow_collapses > 0,
          "postman did not turn, scale, post, wait, return and resume smoothly")
    side_pose = cached_postman_pixels(17, 1, 2, 0, False)
    back_pose = cached_postman_pixels(17, 1, 2, 4, False)
    front_pose = cached_postman_pixels(17, 1, 2, -4, False)
    check(side_pose != back_pose != front_pose,
          "postman turn poses did not change silhouette and depth colours")
    cache_before = cached_postman_pixels.cache_info().hits
    postman_engine.postman.state = "walking_on"
    draw_postman(Surface(240, 100), postman_engine)
    draw_postman(Surface(240, 100), postman_engine)
    check(cached_postman_pixels.cache_info().hits > cache_before,
          "postman gait frames were not served by the graphical cache")
    route_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "3",
        "--cabin-depth-share", "1", "--cabin-depth-scale", "0.4",
        "--postman", "--postman-delivery-frequency", "2",
        "--rabbit-count", "0", "--snow-rate", "0", "--max-flakes", "0",
    ])
    route_engine = SnowEngine(route_args, 360, 120)
    route_engine.postman.timer = 0
    route_engine.step_postman(0.01)
    first_target = route_engine.postman.target_cabin
    check(route_engine.postman.road_y - route_engine.postman.door_y > 10,
          "distant cabin did not produce a long postman delivery path")
    route_engine.postman.state = "hidden"
    route_engine.postman.timer = 0
    route_engine.step_postman(0.01)
    check(route_engine.postman.target_cabin != first_target,
          "postman did not rotate deliveries across every cabin")

    event_args = parse_args([
        "--mode", "pua4", "--sky-events", "aeroplane,ufo,santa",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    event_engine = SnowEngine(event_args, 200, 100)
    travel = (event_engine.width + sky_event_margin(event_engine) * 2) / 100
    sampled_kinds = []
    for index in range(3):
        elapsed = 0.35 + index * (travel + 1) + 0.1
        sampled_kinds.append(current_sky_event(event_args, event_engine, elapsed)[0])
    check(sampled_kinds == ["aeroplane", "ufo", "santa"],
          "sky event scheduler did not rotate through all requested flybys")
    event_complexities = []
    for index in range(3):
        event_surface = Surface(event_engine.width, event_engine.height)
        elapsed = 0.35 + index * (travel + 1) + travel * 0.5
        draw_sky_event(event_surface, event_engine, elapsed)
        pixels = [pixel for pixel in event_surface.pixels if pixel is not None]
        event_complexities.append((len(pixels), len({pixel[0] for pixel in pixels})))
    check(all(pixel_count >= 80 and colours >= 4
              for pixel_count, colours in event_complexities),
          "one or more sky flybys lacks rich multi-colour geometry")

    variety_args = parse_args([
        "--mode", "pua4",
        "--sky-events", "aeroplane,helicopter,kite,ufo,santa",
        "--aeroplane-types", "commuter,airliner",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    variety_engine = SnowEngine(variety_args, 240, 120)
    variety_kinds = []
    elapsed = 0.0
    last_kind = None
    while len(variety_kinds) < 5 and elapsed < 180:
        state = current_sky_event_state(variety_args, variety_engine, elapsed)
        if state is not None and state["kind"] != last_kind:
            variety_kinds.append(state["kind"])
            last_kind = state["kind"]
        elif state is None:
            last_kind = None
        elapsed += 0.1
    check(variety_kinds == ["aeroplane", "helicopter", "kite", "ufo", "santa"],
          "extended sky rotation omitted an aircraft or lost kite")

    kite_args = parse_args([
        "--mode", "pua4", "--sky-events", "kite",
        "--flyby-interval", "1", "--flyby-speed", "60",
        "--gust-strength", "16", "--gust-period", "4",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    kite_engine = SnowEngine(kite_args, 300, 140)
    kite_travel = ((kite_engine.width + sky_event_margin(kite_engine) * 2) /
                   kite_args.flyby_speed)
    kite_elapsed = 0.35 + kite_travel * 0.5
    tail_centres = []
    for wind in (-20.0, 20.0):
        kite_args.wind = wind
        state = current_sky_event_state(kite_args, kite_engine, kite_elapsed)
        kite_surface = Surface(kite_engine.width, kite_engine.height)
        draw_sky_event(kite_surface, kite_engine, kite_elapsed)
        tail_points = [(index % kite_surface.width, index // kite_surface.width)
                       for index, pixel in enumerate(kite_surface.pixels)
                       if pixel is not None and
                       index // kite_surface.width > state["y"] + 13]
        tail_centres.append(sum(x - state["x"] for x, _ in tail_points) /
                            max(1, len(tail_points)))
    check(tail_centres[1] > tail_centres[0] + 6,
          "kite tail did not bend downwind under the shared wind/gust field")

    ejection_args = parse_args([
        "--mode", "pua4", "--sky-events", "aeroplane",
        "--pilot-ejection", "--ejection-chance", "1",
        "--aircraft-crash-depth", "toward", "--explosion-types", "nuclear",
        "--explosion-seconds", "20",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    ejection_engine = SnowEngine(ejection_args, 240, 120)
    ejection_travel = ((ejection_engine.width + sky_event_margin(ejection_engine) * 2) /
                       ejection_args.flyby_speed)
    ejection_elapsed = 0.35 + ejection_travel * 0.55
    ejection_engine.step_parachutists(0.05, ejection_elapsed)
    check(len(ejection_engine.parachutists) == 1 and
          not ejection_engine.parachutists[0].canopy_open and
          len(ejection_engine.aircraft_crashes) == 1,
          "forced aeroplane ejection did not create a distant freefalling pilot")
    for _ in range(20):
        ejection_engine.step_parachutists(0.05, ejection_elapsed + 0.1)
    check(ejection_engine.parachutists and
          ejection_engine.parachutists[0].canopy_open,
          "ejected pilot's parachute did not open")
    parachute_a = Surface(ejection_engine.width, ejection_engine.height)
    draw_parachutists(parachute_a, ejection_engine)
    ejection_engine.parachutists[0].phase += 1.4
    parachute_b = Surface(ejection_engine.width, ejection_engine.height)
    draw_parachutists(parachute_b, ejection_engine)
    check(painted_bounds(parachute_a)[0] >= 11 and
          parachute_a.pixels != parachute_b.pixels,
          "parachute canopy was not enlarged with obvious pendulum/billow motion")
    for _ in range(400):
        ejection_engine.step_aircraft_crashes(0.025)
        if ejection_engine.ground_explosions:
            break
    check(ejection_engine.aircraft_impact_count == 1 and
          ejection_engine.ground_explosions[0].kind == "nuclear" and
          ejection_engine.ground_explosions[0].duration == 20,
          "disabled aircraft did not spin, trail and create configured impact")
    ejection_engine.ground_explosions[0].age = 5.0
    crash_surface = Surface(ejection_engine.width, ejection_engine.height)
    draw_aircraft_crashes(crash_surface, ejection_engine)
    check(sum(pixel is not None for pixel in crash_surface.pixels) > 80,
          "persistent mushroom-cloud explosion lacks animated geometry")

    intact_args = parse_args([
        "--mode", "pua4", "--sky-events", "aeroplane",
        "--pilot-ejection", "--ejection-chance", "0",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    intact_engine = SnowEngine(intact_args, 240, 120)
    intact_engine.step_parachutists(0.05, ejection_elapsed)
    intact_state = current_sky_event_state(
        intact_args, intact_engine, ejection_elapsed)
    check(intact_state is not None and
          intact_state["event_index"] in intact_engine.ejection_attempted_events and
          intact_state["event_index"] not in intact_engine.ejection_events and
          not intact_engine.parachutists and not intact_engine.aircraft_crashes,
          "failed ejection probability roll incorrectly removed the intact plane")

    superman_base = [
        "--mode", "pua4", "--sky-events", "superman",
        "--superman-frequency", "60", "--superman-speed", "80",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ]
    superman_straight_args = parse_args([*superman_base, "--superman-path", "straight"])
    superman_arc_args = parse_args([*superman_base, "--superman-path", "arc"])
    superman_engine = SnowEngine(superman_straight_args, 320, 160)
    superman_travel = ((superman_engine.width + sky_event_margin(superman_engine) * 2) /
                       superman_straight_args.superman_speed)
    superman_midpoint = 0.35 + superman_travel * 0.5
    straight_state = current_sky_event_state(
        superman_straight_args, superman_engine, superman_midpoint)
    superman_engine.args = superman_arc_args
    arc_state = current_sky_event_state(
        superman_arc_args, superman_engine, superman_midpoint)
    superhero_surface = Surface(320, 160)
    draw_sky_event(superhero_surface, superman_engine, superman_midpoint)
    check(straight_state["kind"] == arc_state["kind"] == "superman" and
          arc_state["y"] < straight_state["y"] and
          any(pixel is not None and pixel[0] == (218, 38, 52)
              for pixel in superhero_surface.pixels),
          "Superman path controls or animated red cape were not rendered")

    cloud_args = parse_args([
        "--mode", "pua4", "--clouds", "--cloud-count", "6",
        "--cloud-speed", "8", "--cloud-depths", "0.2,0.5,0.85",
        "--cloud-parallax", "1.5", "--cloud-colours", "8899AA,CCDDEE",
        "--snow-rate", "0", "--max-flakes", "0",
    ])
    cloud_engine = SnowEngine(cloud_args, 320, 160)
    clouds_start = Surface(320, 160)
    draw_clouds(clouds_start, cloud_engine, 0.0, near=False)
    draw_clouds(clouds_start, cloud_engine, 0.0, near=True)
    clouds_later = Surface(320, 160)
    draw_clouds(clouds_later, cloud_engine, 6.0, near=False)
    draw_clouds(clouds_later, cloud_engine, 6.0, near=True)
    cloud_priorities = {pixel[1] for pixel in clouds_start.pixels if pixel is not None}
    check({42, 43, 76, 77}.issubset(cloud_priorities) and
          clouds_start.pixels != clouds_later.pixels,
          "cloud depth lanes did not move with distinct far/near parallax")

    large_event_args = parse_args([
        "--mode", "pua4", "--sky-events", "aeroplane,ufo,santa",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    large_event_engine = SnowEngine(large_event_args, 672, 216)
    large_travel = ((large_event_engine.width +
                     sky_event_margin(large_event_engine) * 2) / 100)
    compact_bounds = []
    for index in range(2):
        event_surface = Surface(672, 216)
        elapsed = 0.35 + index * (large_travel + 1) + large_travel * 0.5
        draw_sky_event(event_surface, large_event_engine, elapsed)
        compact_bounds.append(painted_bounds(event_surface))
    check(compact_bounds[0][0] <= 110 and compact_bounds[1][0] <= 65,
          "aeroplane or UFO regressed to its oversized former footprint")

    santa_depth_args = parse_args([
        "--mode", "pua4", "--sky-events", "santa", "--flyby-interval", "1",
        "--flyby-speed", "100", "--santa-scale-min", "0.02",
        "--santa-scale-max", "0.5", "--snow-rate", "0", "--max-flakes", "0",
    ])
    santa_depth_engine = SnowEngine(santa_depth_args, 320, 160)
    santa_travel = ((santa_depth_engine.width + sky_event_margin(santa_depth_engine) * 2) /
                    santa_depth_args.flyby_speed)
    santa_entry = current_sky_event_state(
        santa_depth_args, santa_depth_engine, 0.35 + santa_travel * 0.01)
    santa_middle = current_sky_event_state(
        santa_depth_args, santa_depth_engine, 0.35 + santa_travel * 0.5)
    santa_exit = current_sky_event_state(
        santa_depth_args, santa_depth_engine, 0.35 + santa_travel * 0.99)
    check(santa_entry["scale"] < 0.025 and santa_middle["scale"] > 0.49 and
          abs(santa_exit["scale"] - santa_entry["scale"]) < 1e-9,
          "Santa did not zoom symmetrically from a point to the configured maximum")

    abduction_args = parse_args([
        "--mode", "pua4", "--sky-events", "ufo", "--ufo-abduction",
        "--ufo-hover-seconds", "4", "--flyby-interval", "1",
        "--flyby-speed", "100", "--rabbit-count", "1",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    abduction_engine = SnowEngine(abduction_args, 200, 100)
    rabbit = abduction_engine.rabbits[0]
    rabbit.state, rabbit.x = "hopping", 82.0
    abduction_travel = ((abduction_engine.width + sky_event_margin(abduction_engine) * 2) /
                        abduction_args.flyby_speed)
    hover_start = 0.35 + abduction_travel * 0.5
    early = hover_start + abduction_args.ufo_hover_seconds * 0.15
    late = hover_start + abduction_args.ufo_hover_seconds * 0.85
    early_event = current_sky_event_state(abduction_args, abduction_engine, early)
    late_event = current_sky_event_state(abduction_args, abduction_engine, late)
    check(early_event["x"] == late_event["x"] and
          early_event["phase"] == late_event["phase"] == "abduction",
          "UFO did not remain stationary throughout the abduction phase")
    abduction_engine.step_ufo_abduction(early)
    early_y, early_scale = rabbit.abduction_y, rabbit.abduction_scale
    check(abs(rabbit.abduction_x - early_event["x"]) < 1e-9,
          "rabbit was not directly below the UFO when capture began")
    abduction_engine.step_ufo_abduction(late)
    check(rabbit.state == "abducting" and rabbit.abduction_y < early_y and
          rabbit.abduction_scale < early_scale and abduction_engine.ufo_beam_active and
          abs(rabbit.abduction_x - late_event["x"]) < 1e-9,
          "rabbit did not rise and shrink while the UFO beam was active")
    beam_surface = Surface(abduction_engine.width, abduction_engine.height)
    draw_sky_event(beam_surface, abduction_engine, late)
    beam_palette = {(44, 236, 255), (51, 121, 255), (184, 75, 255),
                    (255, 205, 54), (224, 255, 249)}
    beam_pixels = [pixel for pixel in beam_surface.pixels
                   if pixel is not None and pixel[0] in beam_palette]
    check(len(beam_palette & {pixel[0] for pixel in beam_pixels}) >= 2 and
          len(beam_pixels) < 90,
          "UFO transporter was not sparse, animated multi-colour energy")
    for beam_style in ("spiral", "rings", "lattice", "stargate"):
        abduction_engine.args.ufo_beam_style = beam_style
        styled_surface = Surface(abduction_engine.width,
                                 abduction_engine.height)
        draw_sky_event(styled_surface, abduction_engine, late)
        check(any(pixel is not None and pixel[0] in beam_palette
                  for pixel in styled_surface.pixels),
              f"{beam_style} transporter style produced no energy geometry")
    abduction_engine.args.ufo_beam_style = "spiral"
    opaque_scenery = Surface(abduction_engine.width, abduction_engine.height)
    opaque_scenery.rectangle(0, 0, opaque_scenery.width - 1,
                             opaque_scenery.height - 1, (8, 8, 8), 40)
    abduction_engine.elapsed = late
    abduction_engine.depths = [0.0] * abduction_engine.width
    abduction_engine.args.ambient_set = frozenset()
    rabbit.depth = 1.0
    near_capture = render_surface(opaque_scenery, abduction_engine)
    capture_colours = beam_palette | rabbit_colours
    check(any(pixel is not None and pixel[0] in capture_colours
              for pixel in near_capture.pixels),
          "foreground rabbit and beam jumped behind cabin scenery during capture")
    rabbit.depth = 0.3
    far_capture = render_surface(opaque_scenery, abduction_engine)
    check(not any(pixel is not None and pixel[0] in capture_colours
                  for pixel in far_capture.pixels),
          "background rabbit and beam did not retain their shared rear depth lane")
    target_unit = max(0.65, max(1.0, min(3.0, abduction_engine.height // 65)) / 3.0)
    finish = hover_start + abduction_args.ufo_hover_seconds * 0.99
    abduction_engine.step_ufo_abduction(finish)
    check(rabbit.state == "hidden" and not abduction_engine.ufo_beam_active and
          abduction_engine.ufo_abduction_count == 1 and
          rabbit.abduction_scale <= target_unit * 0.55,
          "completed UFO capture did not hide the beam/rabbit at 10% saucer scale")

    hidden_engine = SnowEngine(abduction_args, 200, 100)
    hidden = hidden_engine.rabbits[0]
    hidden_engine.step_ufo_abduction(early)
    check(hidden.state == "hidden" and
          hidden_engine.abducted_rabbit_index is None and
          not hidden_engine.ufo_beam_active,
          "UFO manufactured a hidden rabbit solely for an abduction")
    hidden.state, hidden.x = "hopping", 92.0
    hidden_engine.step_ufo_abduction(early + 0.05)
    check(hidden_engine.ufo_target_rabbit_index == 0 and
          hidden.state == "abducting",
          "UFO did not retry acquisition when an existing rabbit emerged")

    trail_surface = Surface(80, 24)
    trail_engine = SnowEngine(large_event_args, 80, 24)
    festive = ((255, 48, 72), (54, 145, 255), (255, 231, 64),
               (255, 132, 38), (55, 222, 105))
    trail_engine.santa_trail = [
        CometParticle(8 + index * 12, 12, 1.0, 1.0, index)
        for index in range(5)
    ]
    draw_sky_event(trail_surface, trail_engine, 0.0)
    check(set(festive).issubset({pixel[0] for pixel in trail_surface.pixels
                                 if pixel is not None}),
          "Santa trail did not expose the complete festive five-colour palette")

    plough_args = parse_args([
        "--mode", "pua4", "--plough-interval", "1", "--plough-speed", "20",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    plough_engine = SnowEngine(plough_args, 160, 80)
    plough_engine.depths = [2.0 + (x % 13) * 2.5 for x in range(160)]
    plough_engine.plough.active = True
    plough_engine.plough.x = 40.0
    plough_engine.plough.direction = 1
    plough_engine.plough.path_y = (
        plough_engine.height * (1.0 - plough_args.plough_clear_to) - 1)
    plough_engine.plough.y = plough_engine.plough.path_y
    path_y = plough_engine.plough.path_y
    plough_engine.step_plough(0.25)
    plough_engine.step_plough(0.25)
    check(plough_engine.plough.y == path_y,
          "snow plough followed the changing bank instead of a horizontal road datum")
    check(path_y > plough_engine.scenery_ground_y,
          "snow plough road datum remained stranded above its cleared surface")

    present_args = parse_args([
        "--mode", "pua4", "--sky-events", "santa", "--flyby-interval", "1",
        "--flyby-speed", "100", "--cabin", "--cabin-count", "2",
        "--cabin-types", "cottage,lodge", "--present-fall-speed", "2",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    present_engine = SnowEngine(present_args, 300, 120)
    present_travel = ((present_engine.width + sky_event_margin(present_engine) * 2) /
                      present_args.flyby_speed)
    elapsed = 0.35
    while elapsed < 0.35 + present_travel:
        present_engine.step_santa_presents(0.02, elapsed)
        elapsed += 0.02
    check(present_engine.present_drop_keys and
          all(abs(present.x - present.target_x) < 1e-9
              for present in present_engine.present_drops),
          "Santa did not release vertically aligned parcels over cabin chimneys")
    check(len(present_engine.present_drops) + present_engine.present_delivery_count >=
          len(present_engine.present_drop_keys) * present_args.santa_presents_min and
          len({round(present.speed, 4) for present in present_engine.present_drops}) > 1,
          "Santa did not release simultaneous multi-speed present groups")

    santa_elapsed = 0.35 + 2 * (large_travel + 1) + large_travel * 0.5
    santa_a = Surface(672, 216)
    santa_b = Surface(672, 216)
    draw_sky_event(santa_a, large_event_engine, santa_elapsed)
    draw_sky_event(santa_b, large_event_engine, santa_elapsed + 0.11)
    santa_colours = {pixel[0] for pixel in santa_a.pixels if pixel is not None}
    check(santa_a.pixels != santa_b.pixels and
          (111, 61, 43) in santa_colours and (83, 48, 38) in santa_colours,
          "Santa team lacks animated, depth-separated near/far leg phases")
    santa_width, _ = painted_bounds(santa_a)
    check(santa_width <= 135,
          "Santa formation regressed above its half-scale distant footprint")
    santa_start = 0.35 + 2 * (large_travel + 1)
    santa_edge = current_sky_event(
        large_event_args, large_event_engine, santa_start + large_travel * 0.08)
    santa_middle = current_sky_event(
        large_event_args, large_event_engine, santa_start + large_travel * 0.50)
    check(santa_middle[2] < santa_edge[2] - large_event_engine.height * 0.08,
          "Santa trajectory did not rise through a visible sky arc")
    large_event_engine.step_santa_trail(0.2, santa_start + large_travel * 0.50)
    check(large_event_engine.santa_trail,
          "Santa did not emit persistent comet-trail particles")
    large_event_args.sky_events = ()
    large_event_engine.step_santa_trail(10.0, santa_start + large_travel + 10)
    check(not large_event_engine.santa_trail,
          "Santa comet trail did not fade and expire")

    occlusion_args = parse_args([
        "--mode", "pua4", "--sky-events", "ufo", "--flyby-interval", "1",
        "--flyby-speed", "100", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--scenery", "none",
    ])
    occlusion_engine = SnowEngine(occlusion_args, 200, 100)
    occlusion_travel = ((occlusion_engine.width + sky_event_margin(occlusion_engine) * 2) /
                        occlusion_args.flyby_speed)
    occlusion_elapsed = 0.35 + occlusion_travel * 0.5
    _, event_x, event_y, _, _ = current_sky_event(
        occlusion_args, occlusion_engine, occlusion_elapsed)
    cover = Surface(200, 100)
    cover_colour = (17, 88, 39)
    cover.rectangle(event_x - 3, event_y - 3, event_x + 4, event_y + 4,
                    cover_colour, 14)
    occlusion_engine.elapsed = occlusion_elapsed
    layered = render_surface(cover, occlusion_engine)
    centre_pixel = layered.pixels[int(round(event_y)) * 200 + int(round(event_x))]
    check(centre_pixel is not None and centre_pixel[0] == cover_colour,
          "distant flight painted over foreground scenery")

    plough_args = parse_args([
        "--mode", "pua4", "--rabbit-count", "0", "--plough-interval", "1",
        "--plough-speed", "1000", "--plough-clear-to", "0.03",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    plough_engine = SnowEngine(plough_args, 80, 40)
    plough_engine.depths = [30.0] * 80
    plough_engine.plough.timer = 0
    plough_engine.step_plough(0.2)
    check(plough_engine.plough_count == 1 and
          max(plough_engine.depths) <= plough_engine.height * 0.03,
          "completed snow-plough pass did not clear the entire bank")
    target_depth = plough_engine.height * plough_args.plough_clear_to
    plough_engine.depths = [target_depth] * plough_engine.width
    plough_engine.depths[10] = target_depth + 3.0
    plough_engine.plough.active = True
    plough_engine.plough.direction = 1
    plough_engine.plough.x = plough_engine.width + 29.0
    plough_engine.step_plough(0.01)
    check(plough_engine.depths[10] == target_depth + 3.0,
          "plough exit erased new snow deposited behind the completed blade path")

    parser = build_parser()
    guide = pretty_help(parser, "pua4", colour=False)
    for action in parser._actions:
        for option in action.option_strings:
            check(option in guide, f"illustrated help omitted {option}")
    for launcher_option in ("--terminal-columns", "--terminal-rows", "--font-size"):
        check(launcher_option in guide,
              f"illustrated help omitted launcher option {launcher_option}")
    check("8 FLAKES" in guide and "24 FLAKES" in guide,
          "illustrated help omitted its exact-count renders")

    detailed_args = parse_args([
        "--mode", "pua4", "--columns", "40", "--rows", "14",
        "--detailed-dashboard", "--snapshot", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    detail_codec, detail_rows, detail_engine, detail_background = make_runtime(
        detailed_args, 160, 14)
    detailed_frame = complete_frame(
        detailed_args, detail_codec, detail_rows, detail_engine,
        detail_background, 160, 0, 0.0)
    check(dashboard_rows(detailed_args) == 6 and len(detailed_frame.splitlines()) == 14,
          "detailed font dashboard did not preserve requested terminal height")
    check("[FONT]" in detailed_frame and "REDEFINED 0/65,536" in detailed_frame and
          "UNIQUE GLYPHS CURRENT FRAME" in detailed_frame and
          "SEEN SINCE START" in detailed_frame and "DEDUP" in detailed_frame,
          "font dashboard tab omitted creation, current or cumulative glyph evidence")
    detail_engine.dashboard_tab = 7
    process_frame = complete_frame(
        detailed_args, detail_codec, detail_rows, detail_engine,
        detail_background, 160, 1, 0.1)
    check("[PROCESS]" in process_frame and "PROCESS CPU" in process_frame and
          "MEMORY" in process_frame,
          "process dashboard tab omitted CPU or memory evidence")
    tab_markers = ("[FONT]", "[SNOW]", "[SKY]", "[WEATHER]", "[TREES]", "[ANIMALS]",
                   "[FLIGHTS]", "[PROCESS]")
    for index, marker in enumerate(tab_markers):
        detail_engine.dashboard_tab = index
        tabbed = complete_frame(
            detailed_args, detail_codec, detail_rows, detail_engine,
            detail_background, 160, index + 2, 0.2 + index * 0.1)
        check(marker in tabbed,
              f"detailed dashboard did not expose the {marker} page")

    tower_args = parse_args([
        "--mode", "pua4", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--initial-snow", "0.20",
        "--shed-threshold", "0.95", "--shed-to", "0.30",
        "--tower-age", "0.2", "--tower-age-jitter", "0",
        "--tower-prominence", "0.05", "--tower-collapse-rate", "2",
        "--tower-cascade-chance", "1", "--tower-cascade-radius", "0.20",
    ])
    tower_engine = SnowEngine(tower_args, 200, 80)
    tower_engine.depths = [16.0] * tower_engine.width
    first, second = 80, 86
    tower_engine.depths[first] = 66.0
    tower_engine.depths[second] = 54.0
    before_tower = tower_engine.depths[first]
    tower_engine.detect_tower_collapses(0.1)
    check(tower_engine.tower_collapse_count == 0,
          "local tower collapsed before its configured lifetime")
    tower_engine.detect_tower_collapses(0.11)
    check(tower_engine.tower_collapse_count >= 1,
          "persistent local tower did not collapse after its configured lifetime")
    # Make subsequent failures cascade-driven rather than independently aged.
    tower_args.tower_age = 100
    for _ in range(20):
        tower_engine.step_tower_collapses(0.1)
    check(tower_engine.depths[first] < before_tower,
          "aged local tower did not lose height")
    check(tower_engine.tower_collapse_count >= 2,
          "completed tower failure did not trigger its forced nearby cascade")

    live_args = parse_args([
        "--mode", "pua4", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0",
    ])
    live_engine = SnowEngine(live_args, 80, 40)
    live_engine.flakes = [live_engine.new_flake() for _ in range(12)]
    with tempfile.TemporaryDirectory() as temporary:
        control_path = Path(temporary) / "control.json"
        control_path.write_text(json.dumps({
            "format": CONTROL_FORMAT, "revision": 7,
            "argv": ["--mode", "pua4", "--wind", "9", "--no-tower-collapse",
                     "--flake-sizes", "large", "--npc-count", "5",
                     "--npc-wander-angle", "180",
                     "--npc-social-factor", "-0.4"],
        }), encoding="utf-8")
        listener = ControlListener(control_path, 0.01)
        check(listener.poll(live_args, live_engine, force=True),
              "valid live-control JSON was not applied")
        check(live_args.wind == 9 and not live_args.tower_collapse and
              all(flake.shape == "large" for flake in live_engine.flakes) and
              len(live_engine.npcs) == 5 and
              live_args.npc_wander_angle == 180 and
              live_args.npc_social_factor == -0.4,
              "live control did not immediately update particles or npc behaviour")
        control_path.write_text(json.dumps({
            "format": CONTROL_FORMAT, "revision": 8, "restart": 1,
            "argv": ["--mode", "pua4", "--wind", "11"],
        }), encoding="utf-8")
        check(listener.poll(live_args, live_engine, force=True) and
              listener.restart_requested and live_args.wind == 11,
              "live-control restart token did not apply current values and request rebuild")

    control_parser = build_parser()
    control_actions = [action for action in control_parser._actions
                       if action.dest not in ("help", "listen")]
    round_trip = parse_args(namespace_to_argv(live_args, control_actions))
    check(round_trip.wind == live_args.wind and
          round_trip.tower_collapse == live_args.tower_collapse,
          "TUI serializer did not preserve effective options")

    with tempfile.TemporaryDirectory() as temporary:
        geometry_path = Path(temporary) / "geometry.json"
        geometry_path.write_text(json.dumps({
            "columns": 144, "rows": 44, "font_size": 9.5,
            "window_position": "77,88",
        }), encoding="utf-8")
        old_geometry = os.environ.get("FONT_DEMO_GEOMETRY_FILE")
        os.environ["FONT_DEMO_GEOMETRY_FILE"] = str(geometry_path)
        cli, cli.initial_argv = tui_parser().parse_known_args([
            "--mode", "pua4", "--control-file", str(Path(temporary) / "live.json"),
            "--save-file", str(Path(temporary) / "christmas-snow-preset.json"),
            "--snow-rate", "45", "--sky-events", "none",
        ])
        controller = Controller(cli)
        check("OTHER" not in [tab[0] for tab in controller.tabs] and
              sum(len(tab[2]) for tab in controller.tabs) == len(controller.actions),
              "control-console pages omitted or duplicated a production option")
        restart_before = controller.restart_generation
        controller.restart_viewer()
        restart_payload = json.loads(Path(cli.control_file).read_text(encoding="utf-8"))
        check(controller.restart_generation == restart_before + 1 and
              restart_payload["restart"] == controller.restart_generation,
              "X restart did not publish a viewer rebuild token")
        for tab_index, (label, _, _) in enumerate(controller.tabs):
            controller.tab_index = tab_index
            check(f"[{controller.tabs[tab_index][1]}{label}]" in controller.tab_strip(58),
                  f"narrow control console hid active {label} tab")
        controller.values.weather = "rain"
        controller.values.wind = 9.0
        controller.values.sky_events = ("ufo",)
        controller.values.ufo_abduction = True
        controller.values.rabbit_count = 2
        controller.tab_index = next(index for index, tab in enumerate(controller.tabs)
                                    if tab[0] == "WEATHER")
        weather_preview = controller.isolated_preview_values()
        check(weather_preview.weather == "rain" and weather_preview.wind == 9 and
              not weather_preview.scenery_set and weather_preview.rabbit_count == 0 and
              not weather_preview.sky_events and weather_preview.initial_snow == 0,
              "WEATHER preview did not isolate precipitation while preserving wind")
        controller.tab_index = next(index for index, tab in enumerate(controller.tabs)
                                    if tab[0] == "FLIGHTS")
        flight_preview = controller.isolated_preview_values()
        check(flight_preview.weather == "none" and
              flight_preview.sky_events == ("ufo",) and
              flight_preview.ufo_abduction and not flight_preview.scenery_set,
              "FLIGHTS preview did not isolate the configured sky event")
        controller.tab_index = next(index for index, tab in enumerate(controller.tabs)
                                    if tab[0] == "TREES")
        tree_preview = controller.isolated_preview_values()
        check(tree_preview.weather == "none" and
              tree_preview.scenery_set == frozenset(("trees",)) and
              tree_preview.rabbit_count == 0,
              "TREES preview did not isolate procedural trees")
        controller.tab_index = next(index for index, tab in enumerate(controller.tabs)
                                    if tab[0] == "CLOUDS")
        cloud_preview = controller.isolated_preview_values()
        check(cloud_preview.clouds and cloud_preview.cloud_count > 0 and
              cloud_preview.weather == "none" and not cloud_preview.scenery_set and
              not cloud_preview.sky_events,
              "CLOUDS preview did not isolate parallax atmosphere layers")
        controller.tab_index = 0
        for action in controller.actions:
            guidance = " ".join(controller.guidance(action))
            check(controller.icon(action) and "Predicted effect:" in guidance and
                  "Performance:" in guidance,
                  f"TUI option {action.dest} lacks an icon or operational guidance")
        flake_action = next(action for action in controller.actions
                            if action.dest == "flake_sizes")
        controller.validate_and_publish(flake_action, ("large",))
        check(controller.values.flake_sizes == ("large",) and
              controller.values.size_weights == (4.0,),
              "TUI flake-size change did not align its weight or publish")
        controller.save()
        command_file = Path(temporary) / "christmas-snow-preset.command.txt"
        command_text = command_file.read_text(encoding="utf-8")
        check(" \\\n" in command_text and command_text.startswith("#!/usr/bin/env bash"),
              "saved command is not a continuation-safe executable shell script")
        check(command_file.stat().st_mode & 0o111,
              "saved command file is not executable")
        check("--terminal-columns" in command_text and
              "--terminal-rows" in command_text and "--font-size 9.5" in command_text and
              "--window-position 77,88" in command_text,
              "S did not capture reproducible terminal dimensions and font size")
        controller.values.snapshot = True
        controller.save()
        command_text = command_file.read_text(encoding="utf-8")
        check("snapshot mode renders one frame and exits" in command_text and
              "--snapshot" in command_text,
              "snapshot command export does not explain its finite behaviour")
        if old_geometry is None:
            os.environ.pop("FONT_DEMO_GEOMETRY_FILE", None)
        else:
            os.environ["FONT_DEMO_GEOMETRY_FILE"] = old_geometry

    route_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "4",
        "--cabin-depth-share", "0.5", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    route_engine = SnowEngine(route_args, 360, 140)
    route_line = int(round(route_engine.scenery_ground_y))
    road_y, spurs = cabin_path_network(route_args, 360, 140, route_line)
    doors = {index: (x, y) for index, x, y, _ in cabin_door_targets(
        route_args, 360, 140, route_line)}
    route_surface = Surface(360, 140)
    draw_cabin_paths(route_surface, route_engine)
    check(len(spurs) == 4 and
          all(points[-1] == doors[index] for index, points in spurs) and
          any(len(points) == 2 for _, points in spurs) and
          any(len(points) > 2 for _, points in spurs) and
          all((points[0][0] < points[-1][0]) == (points[-1][0] < 180)
              for _, points in spurs) and
          sum(pixel is not None for pixel in route_surface.pixels) > 100,
          "perspective-split straight/curved dirt routes missed a cabin door")
    route_npc = route_engine.npcs[0]
    route_npc.x, route_npc.depth = 180.0, 0.52
    route_steering = route_engine.npc_steering(route_npc)
    check(abs(route_steering[5]) + abs(route_steering[6]) > 0.05,
          "NPC did not receive steering from the visible dirt path network")

    horizon_args = parse_args([
        "--mode", "pua4", "--scenery", "cabin", "--cabin-count", "5",
        "--cabin-depth-share", "0.8", "--horizon-structure", "both",
        "--horizon-dirt-density", "0.7", "--horizon-hut-density", "0.7",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    horizon_engine = SnowEngine(horizon_args, 360, 140)
    horizon_surface = build_scenery(
        horizon_args, 360, 140, horizon_engine.scenery_ground_y)
    check(sum(pixel is not None and pixel[1] <= 11
              for pixel in horizon_surface.pixels) > 180,
          "configured dirt horizon and receding huts lack background structure")

    mass_args = parse_args([
        "--mode", "pua4", "--initial-snow", "0.42",
        "--shed-threshold", "0.99", "--no-tower-collapse",
        "--snow-fallaway-threshold", "0.30",
        "--snow-fallaway-min-seconds", "0",
        "--snow-fallaway-max-seconds", "0",
        "--snow-fallaway-width", "0.12", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
    ])
    mass_engine = SnowEngine(mass_args, 200, 100)
    mass_engine.detect_mass_fallaways(0.05)
    check(mass_engine.tower_collapses and
          mass_engine.tower_collapses[0].span >= 20 and
          mass_engine.mass_fallaway_count > 0,
          "height-triggered local snow countdown did not start its fall-away")
    collapse = mass_engine.tower_collapses[0]
    mass_engine.tower_collapses = [collapse]
    for _ in range(240):
        mass_engine.step_tower_collapses(0.025)
        if not mass_engine.tower_collapses:
            break
    half = collapse.span // 2
    left = max(0, collapse.centre - half)
    right = min(mass_engine.width - 1, collapse.centre + half)
    edge_deltas = [abs(mass_engine.depths[x + 1] - mass_engine.depths[x])
                   for x in range(left, right)]
    check(edge_deltas and max(edge_deltas) < mass_engine.height * 0.10,
          "mass fall-away retained a straight vertical edge at its shoulder")

    # Exercise the complete production step order with the saved preset's
    # broad-shed values. Deposits on an active shoulder previously fought the
    # taper forever, leaving one SHED active and preventing future triggers.
    shed_args = parse_args([
        "--mode", "pua4", "--initial-snow", "0.12",
        "--accumulation", "2.4", "--shed-threshold", "0.37",
        "--shed-to", "0.10", "--shed-width", "0.40",
        "--shed-rate", "0.22", "--snow-rate", "525",
        "--max-flakes", "525", "--preload-seconds", "1",
        "--snow-fallaway-threshold", "0.50",
        "--snow-fallaway-min-seconds", "1",
        "--snow-fallaway-max-seconds", "1", "--no-tower-collapse",
        "--scenery", "none", "--rabbit-count", "0", "--no-npcs",
        "--no-postman", "--no-snow-plough",
    ])
    shed_engine = SnowEngine(shed_args, 303, 46)
    shed_engine.depths = [shed_engine.height * 0.34] * shed_engine.width
    for x in range(120, 181):
        shed_engine.depths[x] = shed_engine.height * 0.38
    for frame in range(240):
        shed_engine.step(0.05, (frame + 1) * 0.05)
        if shed_engine.shed_count and shed_engine.shedding is None:
            break
    check(shed_engine.shed_count == 1 and shed_engine.shedding is None,
          "preset-rate broad bank collapse did not trigger and finish")

    deposit_args = parse_args([
        "--mode", "pua4", "--initial-snow", "0.4", "--snow-rate", "0",
        "--max-flakes", "0", "--preload-seconds", "0",
        "--scenery", "none", "--rabbit-count", "0", "--no-npcs",
        "--no-postman", "--no-snow-plough",
    ])
    deposit_engine = SnowEngine(deposit_args, 100, 60)
    deposit_engine.shedding = (50, 20, deposit_engine.depths[40],
                               deposit_engine.depths[60])
    inside_before = deposit_engine.depths[50]
    outside_before = deposit_engine.depths[75]
    flake = deposit_engine.new_flake()
    flake.x = 50.0
    flake.shape = "tiny"
    deposit_engine.deposit(flake)
    check(deposit_engine.depths[50] == inside_before,
          "fresh snow settled on an actively collapsing bank")
    flake.x = 75.0
    deposit_engine.deposit(flake)
    check(deposit_engine.depths[75] > outside_before,
          "active collapse incorrectly stopped snow outside its footprint")

    hero_args = parse_args([
        "--mode", "pua4", "--sky-events", "superman",
        "--flyby-interval", "1", "--superman-speed", "100",
        "--snow-rate", "0", "--max-flakes", "0", "--preload-seconds", "0",
    ])
    hero_engine = SnowEngine(hero_args, 420, 150)
    hero_surface = Surface(hero_engine.width, hero_engine.height)
    hero_elapsed = next(
        tick * 0.05 for tick in range(2000)
        if ((state := current_sky_event_state(
            hero_args, hero_engine, tick * 0.05)) is not None and
            0.45 <= state["phase_progress"] <= 0.55))
    draw_sky_event(hero_surface, hero_engine, hero_elapsed)
    hero_width, hero_height = painted_bounds(hero_surface)
    check(hero_width >= 42 and hero_width >= hero_height * 4,
          "expanded Superman sprite is not recognisably long in flight")

    helicopter_args = parse_args([
        "--mode", "pua4", "--sky-events", "helicopter",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--helicopter-hover-seconds", "1", "--helicopter-wait-min", "2",
        "--helicopter-wait-max", "2", "--helicopter-downwash", "1",
        "--scenery", "cabin", "--cabin-count", "2",
        "--snow-rate", "20", "--max-flakes", "80", "--preload-seconds", "2",
    ])
    helicopter_engine = SnowEngine(helicopter_args, 320, 120)
    initial_snow_mass = sum(helicopter_engine.depths)
    landing_positions = {
        round(helicopter_landing_x(
            helicopter_args, 320, 120,
            int(round(helicopter_engine.scenery_ground_y)), index), 2)
        for index in range(12)
    }
    phases = {}
    turn_orientations = set()
    takeoff_orientations = set()
    departure_min_scale = 1.0
    roof_safe_samples = []
    event_depths = set()
    phase_depths = {}
    event_zero_ground_x = set()
    event_zero_departure_x = []
    for tick in range(1200):
        sample_elapsed = tick * 0.02
        state = current_sky_event_state(
            helicopter_args, helicopter_engine, sample_elapsed)
        if state is not None:
            phases.setdefault(state["phase"], state)
            event_depths.add(round(state["scene_depth"], 3))
            if state["event_index"] == 0:
                phase_depths.setdefault(state["phase"], []).append(
                    state["scene_depth"])
            if (state["event_index"] == 0 and state["phase"] in
                    ("heli_hover", "heli_descent", "heli_landed",
                     "heli_takeoff", "heli_turn")):
                event_zero_ground_x.add(round(state["x"], 6))
            if state["event_index"] == 0 and state["phase"] == "heli_departure":
                event_zero_departure_x.append(state["x"])
            if state["phase"] == "heli_turn":
                turn_orientations.add(state["orientation"])
            elif state["phase"] == "heli_takeoff":
                takeoff_orientations.add(state["orientation"])
            elif state["phase"] == "heli_departure":
                departure_min_scale = min(departure_min_scale, state["scale"])
            if (state["phase"] in ("heli_turn", "heli_departure") and
                    state["cabin_roof_y"] is not None):
                state_unit = compact_flyby_unit(helicopter_engine, 70) * 2.30
                roof_safe_samples.append(
                    state["y"] + 13 * state_unit * state["scale"] <=
                    state["cabin_roof_y"] + 0.001)
            helicopter_engine.step_helicopter(0.02, sample_elapsed)
    required_phases = {"heli_approach", "heli_hover", "heli_descent",
                       "heli_landed", "heli_takeoff", "heli_turn",
                       "heli_departure"}
    check(required_phases.issubset(phases) and
          phases["heli_approach"]["scale"] < phases["heli_hover"]["scale"] and
          phases["heli_departure"]["orientation"] == 12 and
          phases["heli_turn"]["y"] < phases["heli_hover"]["y"] and
          departure_min_scale < 0.2 and
          len(turn_orientations) >= 10 and
          takeoff_orientations == {0} and
          roof_safe_samples and all(roof_safe_samples) and
          len(event_depths) >= 3 and
          min(phase_depths["heli_approach"]) < phase_depths["heli_hover"][0] and
          phase_depths["heli_departure"][-1] < phase_depths["heli_turn"][0] and
          len(event_zero_ground_x) == 1 and
          (all(left <= right for left, right in zip(
              event_zero_departure_x, event_zero_departure_x[1:])) or
           all(left >= right for left, right in zip(
              event_zero_departure_x, event_zero_departure_x[1:]))) and
          len(landing_positions) >= 8 and
          min(landing_positions) < 100 and max(landing_positions) > 220,
          "helicopter did not complete approach, landing, turn and rear departure")
    helicopter_art = Surface(helicopter_engine.width, helicopter_engine.height)
    draw_sky_event(helicopter_art, helicopter_engine,
                   next(tick * 0.02 for tick in range(1200)
                        if ((sample := current_sky_event_state(
                            helicopter_args, helicopter_engine, tick * 0.02)) is not None
                            and sample["phase"] == "heli_hover")))
    helicopter_colours = {pixel[0] for pixel in helicopter_art.pixels
                          if pixel is not None}
    check(helicopter_engine.supply_crates and helicopter_engine.downwash_particles and
          helicopter_engine.downwash_snow_events > 0 and
          sum(helicopter_engine.depths) < initial_snow_mass * 0.96 and
          ({(255, 45, 30), (60, 255, 132)} & helicopter_colours) and
          painted_bounds(helicopter_art)[0] >= 45,
          "helicopter did not leave cargo or couple rotor downwash into the scene")
    yaw_frames = []
    for orientation in range(13):
        yaw_surface = Surface(180, 112)
        draw_ah64_helicopter(yaw_surface, helicopter_engine, 0.3, {
            "kind": "helicopter", "x": 90, "y": 62,
            "direction": 1, "event_index": 0, "scale": 0.8,
            "orientation": orientation,
        })
        yaw_frames.append(tuple(yaw_surface.pixels))
    check(len(set(yaw_frames)) == 13 and
          all(sum(pixel is not None for pixel in frame) > 150
              for frame in yaw_frames),
          "AH-64 yaw model does not provide thirteen detailed distinct angles")
    wash_engine = SnowEngine(helicopter_args, 320, 120)
    landed_elapsed = next(
        tick * 0.02 for tick in range(1200)
        if ((sample := current_sky_event_state(
            helicopter_args, wash_engine, tick * 0.02)) is not None and
            sample["phase"] == "heli_landed"))
    landed_state = current_sky_event_state(
        helicopter_args, wash_engine, landed_elapsed)
    wash_engine.step_helicopter(0.20, landed_elapsed)
    wash_unit = (compact_flyby_unit(wash_engine, 70) * 2.30 *
                 landed_state.get("scale", 1.0))
    check(wash_engine.downwash_particles and all(
        abs(particle.x - landed_state["x"]) > 8 * wash_unit and
        particle.y > landed_state["y"] + 10 * wash_unit
        for particle in wash_engine.downwash_particles),
        "helicopter downwash still originates inside the fuselage")
    check(helicopter_args.helicopter_downwash_width == 1.0 and
          reindeer_apparent_height(320, 120) > 0,
          "helicopter width/reindeer apparent-depth controls are unavailable")

    occlusion_args = parse_args([
        "--mode", "pua4", "--sky-events", "helicopter",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--helicopter-hover-seconds", "1", "--helicopter-wait-min", "1",
        "--helicopter-wait-max", "1", "--scenery", "none",
        "--initial-snow", ".86", "--snow-rate", "0", "--max-flakes", "0",
        "--preload-seconds", "0", "--rabbit-count", "0", "--no-npcs",
        "--no-postman", "--no-snow-plough",
    ])
    occlusion_engine = SnowEngine(occlusion_args, 320, 120)
    far_departure = next(
        tick * 0.02 for tick in range(1600)
        if ((sample := current_sky_event_state(
            occlusion_args, occlusion_engine, tick * 0.02)) is not None and
            sample["event_index"] == 0 and
            sample["phase"] == "heli_departure" and
            sample["scene_depth"] < 0.30))
    raw_helicopter = Surface(320, 120)
    draw_sky_event(raw_helicopter, occlusion_engine, far_departure)
    occlusion_engine.elapsed = far_departure
    composited = render_surface(Surface(320, 120), occlusion_engine)
    raw_indices = [index for index, pixel in enumerate(raw_helicopter.pixels)
                   if pixel is not None]
    overlapping = [index for index in raw_indices
                   if index // occlusion_engine.width >=
                   occlusion_engine.surface_y(index % occlusion_engine.width)]
    bank_colours = set(occlusion_engine.palette["bank"])
    covered = sum(composited.pixels[index] is not None and
                  composited.pixels[index][0] in bank_colours
                  for index in overlapping)
    check(overlapping and covered >= len(overlapping) * 0.90,
          "receding helicopter remained in front of the foreground snow bank")

    # Airwolf is a true selectable event and uses the same complete cinematic
    # state machine, but its black/red model remains distinct at all yaw angles.
    airwolf_args = parse_args([
        "--mode", "pua4", "--sky-events", "airwolf",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--helicopter-hover-seconds", "1", "--helicopter-wait-min", "2",
        "--helicopter-wait-max", "2", "--weather", "none",
    ])
    airwolf_engine = SnowEngine(airwolf_args, 320, 120)
    airwolf_phases = set()
    airwolf_frames = []
    for tick in range(1200):
        state = current_sky_event_state(
            airwolf_args, airwolf_engine, tick * 0.02)
        if state is not None:
            airwolf_phases.add(state["phase"])
    for orientation in range(13):
        yaw_surface = Surface(180, 112)
        draw_ah64_helicopter(yaw_surface, airwolf_engine, 0.3, {
            "kind": "airwolf", "x": 90, "y": 62,
            "direction": 1, "event_index": 0, "scale": 0.8,
            "orientation": orientation,
        })
        airwolf_frames.append(tuple(yaw_surface.pixels))
    airwolf_colours = {pixel[0] for frame in airwolf_frames
                       for pixel in frame if pixel is not None}
    check(required_phases.issubset(airwolf_phases) and
          len(set(airwolf_frames)) == 13 and
          any(colour[0] > 150 and colour[0] > colour[1] * 1.6
              for colour in airwolf_colours),
          "Airwolf does not retain its distinct black/red thirteen-angle model")

    # Occupied pads are rejected before descent. Once the rotor zone is live,
    # rabbits, the postman and tumbleweed cannot cross its boundary.
    safety_args = parse_args([
        "--mode", "pua4", "--sky-events", "helicopter",
        "--flyby-interval", "1", "--flyby-speed", "100",
        "--helicopter-hover-seconds", "1", "--helicopter-wait-min", "2",
        "--helicopter-wait-max", "2", "--scenery", "cabin",
        "--ambient", "tumbleweed",
        "--rabbit-count", "1", "--postman", "--postman-speed", "12",
    ])
    safety_engine = SnowEngine(safety_args, 320, 120)
    proposed_pad = helicopter_landing_x(
        safety_args, 320, 120,
        int(round(safety_engine.scenery_ground_y)), 0)
    safety_engine.rabbits[0].state = "hopping"
    safety_engine.rabbits[0].x = proposed_pad
    safety_engine.postman.state = "walking_on"
    safety_engine.postman.x = proposed_pad + 2
    selected_pad = safe_helicopter_landing_x(safety_args, safety_engine, 0)
    check(abs(selected_pad - proposed_pad) >= 20,
          "helicopter selected a landing pad beneath a rabbit or postman")
    safety_engine.rabbits[0].x = selected_pad
    safety_engine.postman.x = selected_pad
    check(safe_helicopter_landing_x(safety_args, safety_engine, 0) == selected_pad,
          "helicopter changed its committed landing position mid-event")
    exclusion_x, exclusion_radius = 160.0, 30.0
    safety_engine.helicopter_exclusion_active = True
    safety_engine.helicopter_exclusion_x = exclusion_x
    safety_engine.helicopter_exclusion_radius = exclusion_radius
    rabbit = safety_engine.rabbits[0]
    rabbit.x, rabbit.direction, rabbit.state = 128.0, 1, "hopping"
    safety_engine.step_rabbits(0.5, 0.0)
    safety_engine.postman.x = 128.0
    safety_engine.postman.direction = 1
    safety_engine.postman.state = "walking_on"
    safety_engine.step_postman(0.5)
    weed = safety_engine.tumbleweeds[0]
    weed.x, weed.direction, weed.speed = 128.0, 1, 18.0
    safety_engine.step_tumbleweeds(0.5, 0.0)
    check(abs(rabbit.x - exclusion_x) >= exclusion_radius and
          abs(safety_engine.postman.x - exclusion_x) >= exclusion_radius and
          abs(weed.x - exclusion_x) >= exclusion_radius,
          "a ground actor entered the landed helicopter downwash exclusion zone")

    # Only a foreground impact owns terrain heat. It melts a tapered local
    # cavity while a distant explosion leaves the accumulated bank untouched.
    melt_args = parse_args([
        "--mode", "pua4", "--sky-events", "none", "--weather", "none",
        "--initial-snow", "0.25", "--explosion-seconds", "8",
    ])
    melt_engine = SnowEngine(melt_args, 240, 100)
    before_melt = tuple(melt_engine.depths)
    melt_engine.ground_explosions.append(GroundExplosion(
        x=120, y=melt_engine.surface_y(120), kind="nuclear",
        duration=8, scale=1.0, seed=91, foreground=True))
    melt_engine.step_aircraft_crashes(1.0)
    check(melt_engine.depths[120] < before_melt[120] - 5 and
          melt_engine.depths[15] == before_melt[15],
          "foreground aircraft explosion did not melt only its local snow")
    hot_surface = Surface(240, 120)
    melt_engine.ground_explosions[0].age = 2.0
    draw_aircraft_crashes(hot_surface, melt_engine)
    late_surface = Surface(240, 120)
    melt_engine.ground_explosions[0].age = 7.8
    draw_aircraft_crashes(late_surface, melt_engine)
    hot_energy = sum(sum(pixel[0]) for pixel in hot_surface.pixels
                     if pixel is not None)
    late_energy = sum(sum(pixel[0]) for pixel in late_surface.pixels
                      if pixel is not None)
    check(hot_energy > late_energy * 3 and
          any(pixel is not None for pixel in late_surface.pixels),
          "apocalyptic explosion does not remain visible through a gradual fade")

    analyser = load_native_analyser(False)
    if analyser is not None:
        parity_surface = render_surface(
            build_scenery(route_args, route_engine.width, route_engine.height,
                          route_engine.scenery_ground_y), route_engine)
        python_stats, native_stats = {}, {}
        python_frame = encode_surface(parity_surface, CODECS["pua4"], 90, 35,
                                      python_stats)
        native_frame = encode_surface_native(
            parity_surface, CODECS["pua4"], 90, 35, analyser, native_stats)
        check(python_frame == native_frame and python_stats == native_stats,
              "Rust cell analysis changed Python ANSI or telemetry semantics")

    launcher_text = (Path(__file__).resolve().parents[2] /
                     "scripts/macos/run-demo.sh").read_text(encoding="utf-8")
    check("--snapshot)" in launcher_text and "hold-on-success" in launcher_text,
          "macOS launcher does not hold a successful one-frame snapshot")
    check("--window-position" in launcher_text and
          "FONT_DEMO_GEOMETRY_FILE" in launcher_text,
          "macOS launcher does not pass position or geometry metadata")
    for config_name in ("pua4.lua", "square-braille.lua"):
        config_text = (Path(__file__).resolve().parents[2] /
                       "config/wezterm" / config_name).read_text(encoding="utf-8")
        check("pane:get_dimensions()" in config_text and
              "window:effective_config()" in config_text,
              f"{config_name} does not report live terminal/font geometry")

    print("PASS: Christmas snow Square/PUA4 mappings, scenery and cell ownership")
    print("PASS: 50% accumulation triggers shedding; dense rear layers use ANSI background")
    print("PASS: live dimensions preserve bank depth; scenery stays terrain-anchored")
    print("PASS: procedural trees, scanline-cached sway and scenery snow shedding")
    print("PASS: tumbleweed rolls physically, stops at high snow and promotes collapse")
    print("PASS: illustrated help covers every program and launcher control")
    print("PASS: aged tower collapses can cascade; live JSON and TUI argv round-trip")
    print("PASS: seven compact flybys, wind-driven kite tail and enlarged moving parachute")
    print("PASS: sparse snow crystals and independently tapered 4.2 VPX tree trunks")
    print("PASS: rain streaks, bouncing hail and branched lightning render behind scenery")
    print("PASS: precipitation depth assignment, weather-off mode and isolated tab previews")
    print("PASS: Superman paths, Santa depth zoom and parallax cloud lanes animate")
    print("PASS: swooping UFO keeps rabbit/beam depth; sparse plasma effects animate")
    print("PASS: NPCs steer in 360-degree perspective, follow paths, avoid, respawn and track")
    print("PASS: distant cabins; postman cycles, scales, posts and collapses path snow")
    print("PASS: plough preserves snowfall deposited behind its completed blade path")
    print("PASS: Down-arrow escape sequence is not mistaken for the viewer quit key")
    print("PASS: paged live controls, in-window restart, CPU/memory and geometry-safe export")
    print("PASS: cabin path network, grouped gifts and elongated Superman geometry")
    print("PASS: AH-64/Airwolf yaw, safe landing, actor exclusion and rotor downwash")
    print("PASS: foreground crash heat melts local snow; apocalyptic impacts fade smoothly")
    if analyser is not None:
        print("PASS: optional Rust cell analyser is byte-for-byte compatible with Python")


if __name__ == "__main__":
    main()
