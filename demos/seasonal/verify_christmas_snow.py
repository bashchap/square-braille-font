#!/usr/bin/env python3
"""Deterministic structural checks for the Christmas snow demo."""

import json
import random
import tempfile
from pathlib import Path

from christmas_snow import (
    CONTROL_FORMAT,
    CODECS,
    ControlListener,
    SnowEngine,
    Surface,
    build_parser,
    cabin_layout,
    complete_frame,
    current_sky_event,
    dashboard_rows,
    draw_ambient,
    draw_rabbit,
    draw_reindeer,
    draw_sky_event,
    draw_tree,
    encode_surface,
    make_runtime,
    parse_args,
    parse_ambient,
    parse_scenery,
    pretty_help,
    render_surface,
    sky_event_margin,
    tumbleweed_states,
)
from christmas_snow_control import Controller, namespace_to_argv, tui_parser


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

    square = CODECS["square"]
    pua4 = CODECS["pua4"]
    check(chr(0x28FF) in encode_surface(filled_surface(square), square, 1, 1),
          "Square Braille full mask did not map to U+28FF")
    check(chr(0x107FFF) in encode_surface(filled_surface(pua4), pua4, 1, 1),
          "PUA 4x4 full mask did not map to U+107FFF")

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
    check("\x1b[48;2;" in encoded,
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
    detail_engine.dashboard_tab = 5
    process_frame = complete_frame(
        detailed_args, detail_codec, detail_rows, detail_engine,
        detail_background, 160, 1, 0.1)
    check("[PROCESS]" in process_frame and "PROCESS CPU" in process_frame and
          "MEMORY" in process_frame,
          "process dashboard tab omitted CPU or memory evidence")
    tab_markers = ("[FONT]", "[SNOW]", "[TREES]", "[ANIMALS]",
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
    with tempfile.TemporaryDirectory() as temporary:
        control_path = Path(temporary) / "control.json"
        control_path.write_text(json.dumps({
            "format": CONTROL_FORMAT, "revision": 7,
            "argv": ["--mode", "pua4", "--wind", "9", "--no-tower-collapse"],
        }), encoding="utf-8")
        listener = ControlListener(control_path, 0.01)
        check(listener.poll(live_args, live_engine, force=True),
              "valid live-control JSON was not applied")
        check(live_args.wind == 9 and not live_args.tower_collapse,
              "live control did not update both numeric and Boolean settings")

    control_parser = build_parser()
    control_actions = [action for action in control_parser._actions
                       if action.dest not in ("help", "listen")]
    round_trip = parse_args(namespace_to_argv(live_args, control_actions))
    check(round_trip.wind == live_args.wind and
          round_trip.tower_collapse == live_args.tower_collapse,
          "TUI serializer did not preserve effective options")

    with tempfile.TemporaryDirectory() as temporary:
        cli, cli.initial_argv = tui_parser().parse_known_args([
            "--mode", "pua4", "--control-file", str(Path(temporary) / "live.json"),
            "--save-file", str(Path(temporary) / "christmas-snow-preset.json"),
            "--snow-rate", "45", "--sky-events", "none",
        ])
        controller = Controller(cli)
        for action in controller.actions:
            guidance = " ".join(controller.guidance(action))
            check(controller.icon(action) and "Predicted effect:" in guidance and
                  "Performance:" in guidance,
                  f"TUI option {action.dest} lacks an icon or operational guidance")
        controller.save()
        command_file = Path(temporary) / "christmas-snow-preset.command.txt"
        command_text = command_file.read_text(encoding="utf-8")
        check(" \\\n" in command_text and command_text.startswith("#!/usr/bin/env bash"),
              "saved command is not a continuation-safe executable shell script")
        check(command_file.stat().st_mode & 0o111,
              "saved command file is not executable")
        controller.values.snapshot = True
        controller.save()
        command_text = command_file.read_text(encoding="utf-8")
        check("snapshot mode renders one frame and exits" in command_text and
              "--snapshot" in command_text,
              "snapshot command export does not explain its finite behaviour")

    launcher_text = (Path(__file__).resolve().parents[2] /
                     "scripts/macos/run-demo.sh").read_text(encoding="utf-8")
    check("--snapshot)" in launcher_text and "hold-on-success" in launcher_text,
          "macOS launcher does not hold a successful one-frame snapshot")

    print("PASS: Christmas snow Square/PUA4 mappings, scenery and cell ownership")
    print("PASS: 50% accumulation triggers shedding; dense rear layers use ANSI background")
    print("PASS: live dimensions preserve bank depth; scenery stays terrain-anchored")
    print("PASS: Honda/Leonardo trees include oak/maple; scenery snow sheds under gravity")
    print("PASS: tumbleweed rolls physically, stops at high snow and promotes collapse")
    print("PASS: illustrated help covers every program and launcher control")
    print("PASS: aged tower collapses can cascade; live JSON and TUI argv round-trip")
    print("PASS: compact flybys, half-scale arcing Santa and fading comet trail")
    print("PASS: six dashboard tabs, cumulative glyph count, CPU/memory and safe export")


if __name__ == "__main__":
    main()
