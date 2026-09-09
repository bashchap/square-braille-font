#!/usr/bin/env python3
"""Keyboard TUI for live control of the Christmas Snow demo."""

import argparse
import contextlib
import curses
import io
import json
import os
import shlex
import sys
import textwrap
import time
from pathlib import Path

from christmas_snow import (
    CONTROL_FORMAT,
    DEFAULT_CONTROL_PATH,
    LIVE_OPTION_DESTS,
    build_parser,
    parse_args,
)


RANGES = {
    "fps": (1.0, 60.0, 1.0), "duration": (0.0, 3600.0, 5.0),
    "frames": (0, 100000, 10), "columns": (24, 500, 1), "rows": (8, 200, 1),
    "seed": (0, 99999, 1), "control_poll": (0.05, 2.0, 0.05),
    "snow_rate": (0.0, 500.0, 5.0), "max_flakes": (0, 5000, 25),
    "preload_seconds": (0.0, 20.0, 0.5), "fall_speed": (1.0, 80.0, 1.0),
    "speed_variation": (0.0, 0.95, 0.05), "wind": (-30.0, 30.0, 0.5),
    "gust_strength": (0.0, 30.0, 0.5), "gust_period": (0.5, 30.0, 0.5),
    "drift": (0.0, 15.0, 0.25), "wobble": (0.0, 10.0, 0.25),
    "initial_snow": (0.0, 0.85, 0.01), "bank_drift": (0.0, 0.30, 0.005),
    "accumulation": (0.0, 12.0, 0.2), "shed_threshold": (0.05, 0.95, 0.01),
    "snow_repose_slope": (0.0, 8.0, 0.1),
    "snow_relaxation": (0.0, 40.0, 0.5),
    "shed_to": (0.0, 0.90, 0.01), "shed_width": (0.01, 1.0, 0.01),
    "shed_rate": (0.01, 1.5, 0.02), "tower_age": (0.0, 30.0, 0.5),
    "tower_age_jitter": (0.0, 30.0, 0.5), "tower_prominence": (0.01, 0.50, 0.01),
    "tower_collapse_rate": (0.01, 2.0, 0.05),
    "tower_cascade_chance": (0.0, 1.0, 0.05),
    "tower_cascade_radius": (0.01, 0.50, 0.01),
    "tree_density": (0.0, 3.0, 0.05), "max_trees": (0, 500, 5),
    "tree_sway": (0.0, 12.0, 0.25), "lights": (0.0, 2.0, 0.05),
    "tree_branches": (1, 16, 1), "tree_branch_levels": (1, 7, 1),
    "tree_branch_angle": (1.0, 75.0, 1.0),
    "tree_length_ratio": (0.35, 0.90, 0.01),
    "tree_trunk_thickness": (0.5, 12.0, 0.25),
    "tree_thickness_exponent": (1.2, 4.0, 0.1),
    "tree_segment_budget": (0, 100000, 500),
    "object_snow_capture": (0.0, 1.0, 0.01),
    "object_snow_max": (0, 5000, 25),
    "object_snow_hold": (0.0, 60.0, 0.5),
    "object_snow_hold_jitter": (0.0, 60.0, 0.5),
    "object_snow_adhesion": (0.0, 20.0, 0.25),
    "cabin_count": (0, 20, 1), "max_cabins": (0, 20, 1),
    "cabin_scale": (0.25, 3.0, 0.05), "leaf_count": (0, 1000, 10),
    "tumbleweed_count": (0, 100, 1), "ambient_speed": (0.0, 40.0, 0.5),
    "tumbleweed_climb": (0.0, 2.0, 0.05),
    "tumbleweed_collapse_pressure": (0.0, 20.0, 0.25),
    "cabin_size_variation": (0.0, 0.75, 0.025),
    "rabbit_count": (0, 20, 1), "rabbit_interval": (1.0, 180.0, 2.0),
    "rabbit_speed": (1.0, 50.0, 1.0), "flyby_interval": (1.0, 300.0, 5.0),
    "flyby_speed": (1.0, 100.0, 2.0), "plough_interval": (1.0, 600.0, 5.0),
    "santa_scale": (0.2, 2.0, 0.05), "santa_arc_height": (0.0, 0.5, 0.01),
    "santa_trail_seconds": (0.0, 15.0, 0.25),
    "plough_speed": (1.0, 100.0, 2.0), "plough_clear_to": (0.0, 0.50, 0.005),
}

RESTART_ONLY = frozenset({
    "mode", "duration", "frames", "columns", "rows", "seed", "snapshot",
    "no_dashboard", "detailed_dashboard", "preload_seconds", "initial_snow",
    "bank_drift", "control_poll",
})

GROUP_COLOURS = {
    "display and reproducibility": 1,
    "live control": 4,
    "falling snow": 6,
    "accumulation and shedding": 5,
    "seasonal scenery": 2,
    "wildlife and occasional events": 7,
}

GROUP_ICONS = {
    "display and reproducibility": "▣",
    "live control": "◎",
    "falling snow": "❄",
    "accumulation and shedding": "▂",
    "seasonal scenery": "♠",
    "wildlife and occasional events": "✦",
}

OPTION_ICONS = {
    "mode": "▦", "fps": "◷", "duration": "◴", "frames": "≡",
    "columns": "↔", "rows": "↕", "seed": "※", "snapshot": "▣",
    "no_dashboard": "▤", "detailed_dashboard": "▥", "listen": "◎",
    "control_poll": "↻", "snow_rate": "❄", "max_flakes": "⁙",
    "preload_seconds": "◌", "flake_sizes": "✣", "size_weights": "⚖",
    "fall_speed": "↓", "speed_variation": "±", "wind": "→",
    "gust_strength": "≋", "gust_period": "∿", "drift": "⌁",
    "wobble": "〰", "palette": "◈", "initial_snow": "▂",
    "bank_drift": "≈", "accumulation": "▴", "accumulate": "+",
    "snow_repose_slope": "∡", "snow_relaxation": "≈",
    "shed_threshold": "⌁", "shed_to": "↘", "shed_width": "↔",
    "shed_rate": "⇣", "tower_collapse": "▥", "tower_age": "◴",
    "tower_age_jitter": "±", "tower_prominence": "▴",
    "tower_collapse_rate": "⇣", "tower_cascade_chance": "※",
    "tower_cascade_radius": "↔", "scenery": "◇", "cabin": "⌂",
    "reindeer": "♞", "no_trees": "△", "tree_density": "♠",
    "max_trees": "▲", "tree_sway": "〰", "tree_types": "♣",
    "tree_branches": "Y", "tree_branch_levels": "⑂",
    "tree_branch_angle": "∠", "tree_length_ratio": "↘",
    "tree_trunk_thickness": "┃", "tree_thickness_exponent": "²",
    "tree_segment_budget": "Σ", "lights": "✦",
    "object_snow": "❅", "object_snow_capture": "⌁",
    "object_snow_max": "▦", "object_snow_hold": "◴",
    "object_snow_hold_jitter": "±", "object_snow_adhesion": "⚖",
    "cabin_count": "⌂", "max_cabins": "⌂", "cabin_scale": "↕",
    "cabin_types": "⌂", "cabin_size_variation": "±", "ambient": "≈",
    "leaf_count": "❧", "tumbleweed_count": "⊛", "ambient_speed": "→",
    "tumbleweed_climb": "∡", "tumbleweed_collapse_pressure": "⇥",
    "rabbit_count": "♙", "rabbit_interval": "◴", "rabbit_speed": "→",
    "sky_events": "✈", "flyby_interval": "◴", "flyby_speed": "→",
    "santa_scale": "↕", "santa_arc_height": "⌒",
    "santa_trail_seconds": "☄",
    "snow_plough": "▰", "plough_interval": "◴", "plough_speed": "→",
    "plough_clear_to": "▁",
}

IMPACT_GUIDANCE = {
    "fps": "Higher values make motion smoother but raise CPU and terminal-output work almost linearly.",
    "duration": "Zero runs until stopped; a positive value ends the viewer after that many seconds.",
    "frames": "Zero leaves duration in control; a positive value stops after an exact rendered-frame count.",
    "columns": "Larger fixed widths increase cell encoding, memory, and terminal output; omit this to follow live resizing.",
    "rows": "Larger fixed heights increase raster memory and cell encoding; omit this to follow live resizing.",
    "seed": "Changing it produces a different but repeatable layout and event sequence with no material runtime cost.",
    "snapshot": "ON renders exactly one frame and exits; in a macOS spawned window that frame is held for inspection.",
    "detailed_dashboard": "ON reserves six rows; press Tab in the viewer to cycle font, snow, tree, animal, flight and process pages.",
    "control_poll": "Lower intervals react faster but perform more filesystem checks; 0.1–0.5 seconds is normally comfortable.",
    "snow_rate": "Higher values create more particles and faster accumulation until the active-flake ceiling is reached.",
    "max_flakes": "A higher ceiling permits denser storms but increases particle simulation and draw work.",
    "preload_seconds": "Higher values begin with a fuller sky and make startup simulation proportionally more expensive.",
    "flake_sizes": "Larger shapes occupy more virtual pixels and are more legible, but cost more drawing and encoding work.",
    "size_weights": "Larger weights make the corresponding comma-position flake size more frequent; they need not total 100.",
    "fall_speed": "Higher values cross the scene faster, shorten particle lifetime, and can accelerate accumulation.",
    "speed_variation": "Zero makes speeds uniform; higher values create a wider slow/fast distribution.",
    "wind": "Negative values blow left, positive values blow right, and larger magnitudes move particles faster sideways.",
    "gust_strength": "Higher values add stronger periodic wind changes and more dramatic lateral motion.",
    "gust_period": "Lower values cycle gusts more rapidly; higher values create slower weather changes.",
    "drift": "Higher values give individual flakes a wider persistent horizontal bias.",
    "wobble": "Higher values increase side-to-side flutter and visible particle movement.",
    "initial_snow": "Higher fractions start with a deeper bank and may approach the shedding threshold immediately.",
    "accumulation": "Higher values add more bank depth per settling flake and create towers or sheds sooner.",
    "snow_repose_slope": "Sets the stable neighbouring height difference; lower values make a smoother, flatter bank.",
    "snow_relaxation": "Sets how quickly excess slopes flow sideways; high values remove spikes faster but scan the bank each frame.",
    "shed_threshold": "Lower fractions trigger broad fall-away earlier; 0.50 means half the scene height.",
    "tower_age": "Lower values collapse persistent narrow towers sooner; zero makes qualifying towers fail immediately.",
    "tree_density": "Higher values place more trees, increasing raster drawing and unique cell combinations.",
    "max_trees": "This is the hard performance ceiling for trees on very wide terminal grids.",
    "tree_sway": "Higher values bend crowns farther without materially changing tree count.",
    "tree_types": "Choose pine, fir, spruce, oak, maple and birch individually or as a comma list; all rotates every family.",
    "tree_branches": "Sets conifer whorls or broadleaf primary crown limbs; 3–7 is natural, while high values add drawing work.",
    "tree_branch_levels": "Adds recursive oak/maple/birch daughter generations; each extra level can roughly double their branch segments.",
    "tree_branch_angle": "Controls daughter divergence: narrow values make upright crowns; wide values produce spreading forms.",
    "tree_length_ratio": "Sets child/parent length from 0.35 to 0.90; high values make large, overlapping crowns.",
    "tree_trunk_thickness": "Sets base stroke width in virtual pixels; thick trunks survive coarse cells but occupy more raster area.",
    "tree_thickness_exponent": "Controls taper; 2 preserves summed child cross-sectional area under Leonardo's rule.",
    "tree_segment_budget": "Hard frame-wide safety cap for formula limbs; raise it for detail or lower it to protect frame time.",
    "object_snow": "ON lets a small fraction of impacts rest on trees, roofs and figures before mass or time makes it fall.",
    "object_snow_capture": "Chance per exposed-surface impact; 0.03–0.12 stays sparse, while high values can obscure scenery.",
    "object_snow_max": "Hard cap for retained scenery patches; high values add collision, ageing and raster work.",
    "object_snow_hold": "Mean lifetime before a retained patch creeps loose and becomes a falling chunk.",
    "object_snow_hold_jitter": "Randomises hold time so object snow does not shed in a uniform synchronized wave.",
    "object_snow_adhesion": "Supported flake-equivalent mass; low values shed quickly, high values allow heavier patches.",
    "lights": "Higher values add coloured points to foreground trees and can increase colour-state changes in the encoder.",
    "cabin_count": "AUTO responds to width; high explicit counts add complete buildings and increase raster complexity.",
    "max_cabins": "Caps automatic village growth on very wide displays.",
    "cabin_scale": "Higher values enlarge each fixed-aspect cabin and increase the number of occupied cells.",
    "leaf_count": "Each extra leaf is animated every frame; large counts can noticeably increase CPU use.",
    "tumbleweed_count": "Each tumbleweed has rotating multi-line geometry; large counts are more expensive than leaves.",
    "tumbleweed_climb": "Maximum upward terrain step as a radius fraction; lower values make modest snow faces block progress.",
    "tumbleweed_collapse_pressure": "Multiplies tower ageing while blocked, increasing how quickly the contacted snow wall can slump.",
    "rabbit_count": "Each rabbit follows terrain and animates independently; modest counts keep reactions readable.",
    "rabbit_interval": "Lower values make hidden rabbits return sooner and keep more animals visible.",
    "sky_events": "Select none, one event, or a comma list; the listed events rotate in order.",
    "flyby_interval": "Lower values reduce the quiet period between sky crossings.",
    "flyby_speed": "Higher values cross the viewport faster and shorten each visible flyby.",
    "santa_scale": "0.50 is half the original linear size, keeping the formation smaller than foreground houses.",
    "santa_arc_height": "Sets the mid-flight rise as a scene-height fraction; zero restores a straight crossing.",
    "santa_trail_seconds": "Controls how long emitted sparks remain and fade; long trails increase active particle work.",
    "snow_plough": "ON schedules complete terrain-following clearing passes; rabbits react when it approaches.",
    "plough_interval": "Lower values schedule bank-clearing passes more often.",
    "plough_speed": "Higher values clear the scene faster and leave less time to inspect the vehicle.",
    "plough_clear_to": "Lower fractions leave a thinner snow bank after a completed full-width pass.",
}

HIGH_COST = frozenset({
    "fps", "columns", "rows", "snow_rate", "max_flakes", "preload_seconds",
    "tree_density", "max_trees", "lights", "cabin_count", "max_cabins",
    "tree_branch_levels", "tree_branches", "tree_segment_budget",
    "object_snow_max", "object_snow_capture", "snow_relaxation",
    "cabin_scale", "leaf_count", "tumbleweed_count", "rabbit_count",
})
MEDIUM_COST = frozenset({
    "flake_sizes", "detailed_dashboard", "ambient", "ambient_speed",
    "sky_events", "flyby_interval", "snow_plough",
})


def tui_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=("Any Christmas Snow option not listed here is accepted as an initial "
                "value, validated by the animation's production parser, and then "
                "available in the TUI."),
    )
    parser.add_argument("--mode", choices=("square", "pua4"), default="pua4")
    parser.add_argument("--control-file", default=str(DEFAULT_CONTROL_PATH),
                        help="shared JSON file watched by christmas-snow --listen")
    parser.add_argument("--preset", help="load a previously saved JSON preset")
    parser.add_argument("--save-file", default="christmas-snow-preset.json",
                        help="destination used by the S key")
    return parser


def option_for(action):
    return next((item for item in action.option_strings
                 if item.startswith("--") and not item.startswith("--no-")),
                action.option_strings[0])


def value_text(value):
    if value is None:
        return "AUTO"
    if isinstance(value, tuple):
        if not value:
            return "none"
        return ",".join(str(item) for item in value)
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def namespace_to_argv(namespace, actions):
    """Serialize all effective settings into a validated, reproducible argv."""
    argv = []
    for action in actions:
        name = action.dest
        value = getattr(namespace, name)
        if isinstance(action, argparse.BooleanOptionalAction):
            positive = option_for(action)
            negative = next(item for item in action.option_strings if item.startswith("--no-"))
            argv.append(positive if value else negative)
        elif isinstance(action, argparse._StoreTrueAction):
            if value:
                argv.append(option_for(action))
        elif isinstance(action, argparse._StoreFalseAction):
            if not value:
                argv.append(option_for(action))
        elif value is not None:
            argv.extend((option_for(action), value_text(value)))
    return argv


class Controller:
    def __init__(self, cli):
        self.cli = cli
        self.snow_parser = build_parser()
        self.actions = [action for action in self.snow_parser._actions
                        if action.dest not in ("help", "listen")]
        self.index = 0
        self.scroll = 0
        self.revision = 0
        self.status = "Ready"
        self.command_message = ""
        self.values = self.load_initial()
        self.publish("Initial settings published")

    def parse_safely(self, argv):
        with contextlib.redirect_stderr(io.StringIO()):
            return parse_args(argv)

    def load_initial(self):
        candidates = [Path(self.cli.preset).expanduser()] if self.cli.preset else []
        if not self.cli.preset and self.cli.initial_argv:
            return self.parse_safely(["--mode", self.cli.mode, *self.cli.initial_argv])
        candidates.append(Path(self.cli.control_file).expanduser())
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("format") == CONTROL_FORMAT:
                    parsed = self.parse_safely(payload["argv"])
                    if parsed.mode == self.cli.mode:
                        self.revision = int(payload.get("revision", 0))
                        self.status = f"Loaded {path}"
                        return parsed
            except (OSError, ValueError, KeyError, TypeError, SystemExit):
                pass
        return self.parse_safely(["--mode", self.cli.mode])

    def payload(self):
        return {
            "format": CONTROL_FORMAT,
            "revision": self.revision,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "argv": namespace_to_argv(self.values, self.actions),
        }

    @staticmethod
    def atomic_json(path, payload):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def publish(self, message="Updated live viewer"):
        self.revision += 1
        self.atomic_json(self.cli.control_file, self.payload())
        self.status = f"{message} · revision {self.revision}"

    def command_parts(self):
        settings = [item for item in namespace_to_argv(self.values, self.actions)
                    if item not in ("--mode", self.values.mode)]
        if sys.platform == "darwin":
            prefix = ["./scripts/macos/run-demo.sh", self.values.mode, "christmas-snow"]
        elif os.name == "nt":
            prefix = ["python", r".\demos\seasonal\christmas_snow.py",
                      "--mode", self.values.mode]
        elif self.values.mode == "pua4":
            prefix = ["./experiments/pua-4x4/demos4x4/run-demo.sh", "christmas-snow"]
        else:
            prefix = ["./scripts/linux/launch-mate-terminal.sh", "christmas-snow"]
        segments = []
        index = 0
        while index < len(settings):
            segment = [settings[index]]
            if index + 1 < len(settings) and not settings[index + 1].startswith("--"):
                segment.append(settings[index + 1])
                index += 1
            segments.append(segment)
            index += 1
        return prefix, segments

    def command(self):
        """Return a copyable multiline command with real shell continuations."""
        prefix, segments = self.command_parts()
        continuation = " `\n  " if os.name == "nt" else " \\\n  "
        rendered = shlex.join(prefix)
        if segments:
            rendered += continuation + continuation.join(shlex.join(part) for part in segments)
        return rendered

    def save(self):
        destination = Path(self.cli.save_file).expanduser()
        self.atomic_json(destination, self.payload())
        command_path = destination.with_suffix(".command.txt")
        preamble = ("# Run from the repository root in PowerShell.\n" if os.name == "nt"
                    else "#!/usr/bin/env bash\nset -euo pipefail\n")
        if self.values.snapshot:
            preamble += ("# NOTE: snapshot mode renders one frame and exits; "
                         "turn --snapshot OFF for animation.\n")
        command_path.write_text(preamble + self.command() + "\n", encoding="utf-8")
        if os.name != "nt":
            command_path.chmod(0o755)
        suffix = " · SNAPSHOT: one frame only" if self.values.snapshot else ""
        self.status = f"Saved {destination} and {command_path}{suffix}"

    def reset(self):
        self.values = self.parse_safely(["--mode", self.values.mode])
        self.publish("Defaults restored")

    def validate_and_publish(self, action, candidate):
        old = getattr(self.values, action.dest)
        setattr(self.values, action.dest, candidate)
        try:
            self.values = self.parse_safely(namespace_to_argv(self.values, self.actions))
        except SystemExit:
            setattr(self.values, action.dest, old)
            self.status = "Rejected: setting conflicts with another option"
            return
        scope = "viewer restart required" if action.dest in RESTART_ONLY else "applied live"
        self.publish(f"{option_for(action)} {scope}")

    def adjust(self, direction):
        action = self.actions[self.index]
        current = getattr(self.values, action.dest)
        if isinstance(current, bool):
            self.validate_and_publish(action, not current)
            return
        if action.choices:
            choices = list(action.choices)
            index = choices.index(current)
            self.validate_and_publish(action, choices[(index + direction) % len(choices)])
            return
        if action.dest in RANGES:
            minimum, maximum, step = RANGES[action.dest]
            if current is None:
                candidate = minimum if direction > 0 else maximum
            else:
                candidate = max(minimum, min(maximum, current + direction * step))
            if action.type is int:
                candidate = int(round(candidate))
            self.validate_and_publish(action, candidate)
            return
        self.status = "Press Enter for direct input on this option"

    def direct_input(self, screen):
        action = self.actions[self.index]
        height, width = screen.getmaxyx()
        prompt = f"Set {option_for(action)} (AUTO allowed where shown): "
        curses.echo()
        with contextlib.suppress(curses.error):
            curses.curs_set(1)
        try:
            screen.move(height - 1, 0)
            screen.clrtoeol()
            screen.addnstr(height - 1, 0, prompt, max(1, width - 1), curses.color_pair(3))
            raw = screen.getstr(height - 1, min(len(prompt), width - 2),
                                max(1, width - len(prompt) - 2)).decode("utf-8").strip()
        finally:
            curses.noecho()
            with contextlib.suppress(curses.error):
                curses.curs_set(0)
        if not raw:
            self.status = "Direct input cancelled"
            return
        try:
            if isinstance(getattr(self.values, action.dest), bool):
                candidate = raw.lower() in ("1", "true", "yes", "on")
            elif (action.dest in {"columns", "rows", "snow_rate", "max_flakes",
                                  "cabin_count", "leaf_count", "tumbleweed_count"}
                  and raw.lower() == "auto"):
                candidate = None
            else:
                candidate = action.type(raw) if action.type else raw
            if action.choices and candidate not in action.choices:
                raise ValueError("not an available choice")
            self.validate_and_publish(action, candidate)
        except (ValueError, TypeError, argparse.ArgumentTypeError) as error:
            self.status = f"Invalid value: {error}"

    def slider(self, action, value, width=16):
        if action.dest not in RANGES or value is None:
            return ""
        minimum, maximum, _ = RANGES[action.dest]
        fraction = (float(value) - minimum) / max(0.0001, maximum - minimum)
        filled = max(0, min(width, int(round(fraction * width))))
        return "▰" * filled + "▱" * (width - filled)

    @staticmethod
    def icon(action):
        return OPTION_ICONS.get(action.dest,
                                GROUP_ICONS.get(action.container.title, "·"))

    @staticmethod
    def guidance(action):
        lines = []
        if action.dest in RANGES:
            minimum, maximum, step = RANGES[action.dest]
            lines.append(f"Slider range: {minimum:g} … {maximum:g}  ·  arrow step {step:g}; Enter accepts exact validated input")
        elif action.choices:
            lines.append("Values: " + " · ".join(map(str, action.choices)))
        elif isinstance(action, (argparse.BooleanOptionalAction,
                                 argparse._StoreTrueAction,
                                 argparse._StoreFalseAction)):
            lines.append("Values: ON / OFF")
        else:
            lines.append("Value: direct text, comma list, or AUTO where documented")
        lines.append("Predicted effect: " + IMPACT_GUIDANCE.get(
            action.dest, action.help or "Changes this renderer setting."))
        if action.dest in HIGH_COST:
            lines.append("Performance: HIGH sensitivity at large values or very large grids.")
        elif action.dest in MEDIUM_COST:
            lines.append("Performance: MODERATE; impact grows with viewport and object count.")
        else:
            lines.append("Performance: LOW direct impact under normal settings.")
        return lines

    @staticmethod
    def put(screen, y, x, text, style=0):
        height, width = screen.getmaxyx()
        if 0 <= y < height and x < width:
            try:
                screen.addnstr(y, max(0, x), str(text), max(0, width - max(0, x) - 1), style)
            except curses.error:
                pass

    def show_command(self, screen):
        command = self.command()
        self.command_message = command
        height, width = screen.getmaxyx()
        lines = (["⚠ SNAPSHOT IS ON: this command renders one frame and exits.", ""]
                 if self.values.snapshot else [])
        for logical_line in command.splitlines():
            lines.extend(textwrap.wrap(logical_line, max(30, width - 8),
                                       subsequent_indent="  ") or [""])
        top = max(2, (height - len(lines) - 6) // 2)
        self.put(screen, top, 2, "╭" + "─" * max(1, width - 6) + "╮", curses.color_pair(1))
        self.put(screen, top + 1, 4, "REPRODUCIBLE COMMAND", curses.color_pair(3) | curses.A_BOLD)
        for offset, line in enumerate(lines):
            self.put(screen, top + 3 + offset, 4, line, curses.color_pair(2))
        self.put(screen, top + 4 + len(lines), 4,
                 "This command will also be printed after you quit. Press any key.",
                 curses.color_pair(4))
        self.put(screen, top + 5 + len(lines), 2,
                 "╰" + "─" * max(1, width - 6) + "╯", curses.color_pair(1))
        screen.refresh()
        screen.getch()

    def draw(self, screen):
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 12 or width < 58:
            self.put(screen, 1, 2, "Resize to at least 58 columns × 12 rows", curses.color_pair(3))
            screen.refresh()
            return
        self.put(screen, 0, 0, "╭" + "─" * (width - 2) + "╮", curses.color_pair(1))
        title = " ❄ CHRISTMAS SNOW · LIVE CONTROL CONSOLE ❄ "
        self.put(screen, 1, 0, "│" + title.center(width - 2) + "│",
                 curses.color_pair(1) | curses.A_BOLD)
        self.put(screen, 2, 0, "├" + "─" * (width - 2) + "┤", curses.color_pair(1))
        summary = (f" MODE {self.values.mode.upper()}  REV {self.revision}  "
                   f"CONTROL {Path(self.cli.control_file).expanduser()} ")
        self.put(screen, 3, 0, "│" + summary.ljust(width - 2) + "│", curses.color_pair(2))
        self.put(screen, 4, 0, "├" + "─" * (width - 2) + "┤", curses.color_pair(1))

        panel_width = max(46, int(width * 0.64)) if width >= 92 else width - 2
        visible = height - 9
        if self.index < self.scroll:
            self.scroll = self.index
        if self.index >= self.scroll + visible:
            self.scroll = self.index - visible + 1
        for row, action in enumerate(self.actions[self.scroll:self.scroll + visible], 5):
            absolute = self.scroll + row - 5
            selected = absolute == self.index
            marker = "▶" if selected else " "
            icon = self.icon(action)
            scope = "● LIVE" if action.dest in LIVE_OPTION_DESTS else "◌ RESTART"
            value = getattr(self.values, action.dest)
            line = (f"{marker} {icon} {option_for(action):<23} {value_text(value):>12} "
                    f"{self.slider(action, value):<16} {scope:>9}")
            group_pair = GROUP_COLOURS.get(action.container.title, 2)
            style = (curses.color_pair(3) | curses.A_BOLD | curses.A_REVERSE
                     if selected else curses.color_pair(group_pair))
            self.put(screen, row, 1, line[:panel_width - 1], style)

        if width >= 92:
            split = panel_width + 1
            for row in range(5, height - 3):
                self.put(screen, row, split, "│", curses.color_pair(1))
            action = self.actions[self.index]
            details = [
                f"◆ {self.icon(action)} SELECTED OPTION ◆", "",
                f"{self.icon(action)}  {option_for(action)}",
                f"Group: {action.container.title}",
                f"Current: {value_text(getattr(self.values, action.dest))}",
                f"Scope: {'applies immediately' if action.dest in LIVE_OPTION_DESTS else 'saved now; viewer restart required'}",
                "",
            ]
            details.extend(textwrap.wrap(action.help or "", max(24, width - split - 5)))
            details.extend([""])
            for guidance in self.guidance(action):
                details.extend(textwrap.wrap(guidance, max(24, width - split - 5)))
            details.extend(["", "←/→ adjust or cycle", "Enter direct input", "Space toggle"])
            for row, line in enumerate(details, 6):
                self.put(screen, row, split + 2, line,
                         curses.color_pair(4) if row > 7 else curses.color_pair(3))

        self.put(screen, height - 3, 0, "├" + "─" * (width - 2) + "┤", curses.color_pair(1))
        keys = " ↑↓ SELECT  ←→ ADJUST  ⏎ TYPE  ␠ TOGGLE  S SAVE  P COMMAND  R RESET  Q QUIT "
        self.put(screen, height - 2, 0, "│" + keys.ljust(width - 2) + "│", curses.color_pair(4))
        self.put(screen, height - 1, 0, ("└─ " + self.status + " ").ljust(width - 1, "─") + "┘",
                 curses.color_pair(1))
        screen.refresh()

    def run(self, screen):
        # Some valid terminal/PTY combinations cannot change cursor visibility;
        # that cosmetic limitation must not prevent the controller opening.
        with contextlib.suppress(curses.error):
            curses.curs_set(0)
        screen.keypad(True)
        with contextlib.suppress(curses.error):
            curses.start_color()
        with contextlib.suppress(curses.error):
            curses.use_default_colors()
        # Prefer vivid xterm-256 colours while retaining a conventional
        # eight-colour fallback for older MATE/Terminal/Windows consoles.
        vivid = (51, 46, 226, 213, 75, 255, 203)
        basic = (curses.COLOR_CYAN, curses.COLOR_GREEN, curses.COLOR_YELLOW,
                 curses.COLOR_MAGENTA, curses.COLOR_BLUE, curses.COLOR_WHITE,
                 curses.COLOR_RED)
        palette = vivid if getattr(curses, "COLORS", 0) >= 256 else basic
        for pair, foreground in enumerate(palette, 1):
            with contextlib.suppress(curses.error, ValueError):
                curses.init_pair(pair, foreground, -1)
        while True:
            self.draw(screen)
            key = screen.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key == curses.KEY_UP:
                self.index = (self.index - 1) % len(self.actions)
            elif key == curses.KEY_DOWN:
                self.index = (self.index + 1) % len(self.actions)
            elif key == curses.KEY_PPAGE:
                self.index = max(0, self.index - max(1, screen.getmaxyx()[0] - 9))
            elif key == curses.KEY_NPAGE:
                self.index = min(len(self.actions) - 1,
                                 self.index + max(1, screen.getmaxyx()[0] - 9))
            elif key == curses.KEY_HOME:
                self.index = 0
            elif key == curses.KEY_END:
                self.index = len(self.actions) - 1
            elif key == curses.KEY_LEFT:
                self.adjust(-1)
            elif key == curses.KEY_RIGHT:
                self.adjust(1)
            elif key in (ord(" "),):
                action = self.actions[self.index]
                if isinstance(getattr(self.values, action.dest), bool):
                    self.adjust(1)
                else:
                    self.status = "Space toggles Boolean options; use arrows or Enter here"
            elif key in (10, 13, curses.KEY_ENTER):
                self.direct_input(screen)
            elif key in (ord("s"), ord("S")):
                self.save()
            elif key in (ord("p"), ord("P")):
                self.show_command(screen)
            elif key in (ord("r"), ord("R")):
                self.reset()


def main(argv=None):
    cli, cli.initial_argv = tui_parser().parse_known_args(argv)
    controller = Controller(cli)
    try:
        curses.wrapper(controller.run)
    except KeyboardInterrupt:
        pass
    print("Christmas Snow control file:", Path(cli.control_file).expanduser())
    print("Reproducible viewer command:")
    print(controller.command_message or controller.command())


if __name__ == "__main__":
    main()
