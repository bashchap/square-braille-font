#!/usr/bin/env python3
"""Repeatable phase benchmark for Christmas Snow physics and rendering modes."""

import argparse
import json
import statistics
import time

from christmas_snow import (
    build_scenery,
    cached_tree_pixels,
    encode_surface,
    make_runtime,
    parse_args,
    render_surface,
)


PHASES = ("step", "scenery", "collision", "raster", "encode", "total")


def scenario_args(columns, rows, physics):
    return parse_args([
        "--mode", "pua4", "--columns", str(columns), "--rows", str(rows),
        "--detailed-dashboard", "--fps", "25", "--physics", physics,
        "--scenery", "all", "--tree-types", "all", "--max-trees", "96",
        "--ambient", "all", "--rabbit-count", "2",
        "--sky-events", "aeroplane,ufo,santa", "--flyby-interval", "12",
        "--snow-rate", "270", "--max-flakes", "270",
        "--preload-seconds", "1", "--seed", "1225",
    ])


def one_run(columns, rows, physics, frames):
    args = scenario_args(columns, rows, physics)
    codec, scene_rows, engine, background = make_runtime(args, columns, rows)
    samples = {name: [] for name in PHASES}
    dt = 1.0 / args.fps
    for frame in range(frames + 2):
        started = time.perf_counter()
        engine.step(dt, frame * dt)
        after_step = time.perf_counter()
        background = build_scenery(
            args, engine.width, engine.height, engine.scenery_ground_y, frame * dt)
        after_scenery = time.perf_counter()
        engine.update_scenery_collision(background)
        after_collision = time.perf_counter()
        engine.elapsed = frame * dt
        surface = render_surface(background, engine)
        after_raster = time.perf_counter()
        encode_surface(surface, codec, columns, scene_rows)
        after_encode = time.perf_counter()
        if frame < 2:
            continue
        values = (
            after_step - started,
            after_scenery - after_step,
            after_collision - after_scenery,
            after_raster - after_collision,
            after_encode - after_raster,
            after_encode - started,
        )
        for name, value in zip(PHASES, values):
            samples[name].append(value * 1000.0)
    return {name: statistics.median(values) for name, values in samples.items()}


def parse_dimensions(value):
    try:
        columns, rows = (int(part) for part in value.lower().split("x", 1))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("viewport must look like 168x60") from error
    if columns < 24 or rows < 8:
        raise argparse.ArgumentTypeError("viewport must be at least 24x8")
    return columns, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewport", action="append", type=parse_dimensions,
                        help="terminal cells, repeatable; defaults to 120x36, 168x60, 279x43")
    parser.add_argument("--frames", type=int, default=8,
                        help="timed frames per run after two warm-up frames")
    parser.add_argument("--runs", type=int, default=3,
                        help="independent runs whose medians are combined")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    options = parser.parse_args(argv)
    if options.frames < 1 or options.runs < 1:
        parser.error("--frames and --runs must be positive")
    viewports = options.viewport or [(120, 36), (168, 60), (279, 43)]
    report = []
    for columns, rows in viewports:
        for physics in ("none", "ground", "full"):
            runs = [one_run(columns, rows, physics, options.frames)
                    for _ in range(options.runs)]
            medians = {name: statistics.median(run[name] for run in runs)
                       for name in PHASES}
            report.append({
                "viewport": f"{columns}x{rows}", "physics": physics,
                **{f"{name}_ms": round(value, 3)
                   for name, value in medians.items()},
                "maximum_fps": round(1000.0 / medians["total"], 3),
            })
    if options.json:
        print(json.dumps({"benchmark": report}, indent=2))
        return
    for viewport in viewports:
        label = f"{viewport[0]}x{viewport[1]}"
        print(f"VIEWPORT {label} PUA4 · cached trees · 270 flakes")
        print("physics       step scenery collision raster  encode   total max-fps")
        for row in (item for item in report if item["viewport"] == label):
            print(f"{row['physics']:<10}" + "".join(
                f" {row[f'{phase}_ms']:7.2f}" for phase in PHASES) +
                f" {row['maximum_fps']:7.2f}")
        print()
    cache = cached_tree_pixels.cache_info()
    print(f"TREE CACHE hits={cache.hits} misses={cache.misses} size={cache.currsize}/{cache.maxsize}")


if __name__ == "__main__":
    main()
