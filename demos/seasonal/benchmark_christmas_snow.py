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
    encode_surface_native,
    make_runtime,
    parse_args,
    render_surface,
)


PHASES = ("step", "scenery", "collision", "raster", "encode", "total")


def scenario_args(columns, rows, physics, encoder, surface, workload, sky_event):
    arguments = [
        "--mode", "pua4", "--columns", str(columns), "--rows", str(rows),
        "--detailed-dashboard", "--fps", "25", "--physics", physics,
        "--native-encoder", encoder,
        "--native-surface", surface,
        "--scenery", "all", "--tree-types", "all", "--max-trees", "96",
        "--ambient", "all", "--rabbit-count", "2",
        "--sky-events", "aeroplane,ufo,santa", "--flyby-interval", "12",
        "--snow-rate", "270", "--max-flakes", "270",
        "--preload-seconds", "1", "--seed", "1225",
    ]
    if workload == "full":
        # Exercise every continuously active subsystem at a deliberately busy
        # but valid load. A single selected flight type makes rare heavy event
        # phases independently repeatable instead of diluting them in a median.
        arguments.extend([
            "--tree-density", "0.18", "--rabbit-count", "6",
            "--npc-count", "8", "--cloud-count", "8",
            "--sky-events", sky_event, "--flyby-interval", "0.1",
            "--snow-rate", "525", "--max-flakes", "525",
            "--preload-seconds", "4", "--initial-snow", "0.34",
            "--cabin-count", "7", "--cabin-depth-share", "0.65",
        ])
    return parse_args(arguments)


def one_run(columns, rows, physics, frames, encoder="auto", surface="auto",
            workload="standard", sky_event="helicopter", start_seconds=0.0):
    args = scenario_args(
        columns, rows, physics, encoder, surface, workload, sky_event)
    codec, scene_rows, engine, background = make_runtime(args, columns, rows)
    samples = {name: [] for name in PHASES}
    dt = 1.0 / args.fps
    for frame in range(frames + 2):
        started = time.perf_counter()
        elapsed = start_seconds + frame * dt
        engine.step(dt, elapsed)
        after_step = time.perf_counter()
        background = build_scenery(
            args, engine.width, engine.height, engine.scenery_ground_y, elapsed,
            engine.native_surface)
        after_scenery = time.perf_counter()
        engine.update_scenery_collision(background)
        after_collision = time.perf_counter()
        engine.elapsed = elapsed
        surface = render_surface(background, engine)
        after_raster = time.perf_counter()
        if engine.native_analyser is not None:
            encode_surface_native(surface, codec, columns, scene_rows,
                                  engine.native_analyser)
        else:
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
    result = {name: statistics.median(values) for name, values in samples.items()}
    result["_encoder"] = "rust" if engine.native_analyser is not None else "python"
    result["_surface"] = "rust" if engine.native_surface is not None else "python"
    return result


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
    parser.add_argument("--encoder", choices=("auto", "off", "on", "both"),
                        default="auto",
                        help="encoder path; both emits directly comparable Python/Rust rows")
    parser.add_argument("--surface", choices=("auto", "off", "on"),
                        default="auto", help="packed raster/compositing backend")
    parser.add_argument("--workload", choices=("standard", "full"),
                        default="standard",
                        help="standard historical load or the current full-engine stress load")
    parser.add_argument("--physics", choices=("none", "ground", "full", "all"),
                        default="all", help="physics mode(s) to benchmark")
    parser.add_argument("--sky-event",
                        choices=("aeroplane", "helicopter", "airwolf", "kite",
                                 "ufo", "santa", "superman"),
                        default="helicopter",
                        help="single repeatable flight used by the full workload")
    parser.add_argument("--start-seconds", type=float, default=0.0,
                        help="simulation time at the first warm-up frame; selects event phase")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    options = parser.parse_args(argv)
    if options.frames < 1 or options.runs < 1:
        parser.error("--frames and --runs must be positive")
    viewports = options.viewport or [(120, 36), (168, 60), (279, 43)]
    encoders = ("off", "on") if options.encoder == "both" else (options.encoder,)
    physics_modes = (("none", "ground", "full") if options.physics == "all"
                     else (options.physics,))
    report = []
    for columns, rows in viewports:
        for physics in physics_modes:
            for encoder in encoders:
                runs = [one_run(
                    columns, rows, physics, options.frames, encoder,
                    options.surface, options.workload, options.sky_event,
                    options.start_seconds)
                        for _ in range(options.runs)]
                medians = {name: statistics.median(run[name] for run in runs)
                           for name in PHASES}
                report.append({
                    "viewport": f"{columns}x{rows}", "physics": physics,
                    "encoder": runs[0]["_encoder"],
                    "surface": runs[0]["_surface"],
                    "workload": options.workload,
                    "sky_event": options.sky_event,
                    "start_seconds": options.start_seconds,
                    **{f"{name}_ms": round(value, 3)
                       for name, value in medians.items()},
                    "maximum_fps": round(1000.0 / medians["total"], 3),
                })
    if options.json:
        print(json.dumps({"benchmark": report}, indent=2))
        return
    for viewport in viewports:
        label = f"{viewport[0]}x{viewport[1]}"
        print(f"VIEWPORT {label} PUA4 · {options.workload} · "
              f"{options.sky_event} @ {options.start_seconds:.2f}s")
        print("physics   encoder surface step scenery collision raster  encode   total max-fps")
        for row in (item for item in report if item["viewport"] == label):
            print(f"{row['physics']:<10}{row['encoder']:<8}{row['surface']:<8}" + "".join(
                f" {row[f'{phase}_ms']:7.2f}" for phase in PHASES) +
                f" {row['maximum_fps']:7.2f}")
        print()
    cache = cached_tree_pixels.cache_info()
    print(f"TREE CACHE hits={cache.hits} misses={cache.misses} size={cache.currsize}/{cache.maxsize}")


if __name__ == "__main__":
    main()
