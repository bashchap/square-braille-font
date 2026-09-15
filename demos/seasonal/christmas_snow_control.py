#!/usr/bin/env python3
"""Keyboard TUI for live control of the Christmas Snow demo."""

import argparse
import copy
import contextlib
import curses
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from christmas_snow import (
    CONTROL_FORMAT,
    DEFAULT_FLAKE_WEIGHTS,
    DEFAULT_CONTROL_PATH,
    LIVE_OPTION_DESTS,
    build_parser,
    parse_args,
)


RANGES = {
    "fps": (1.0, 60.0, 1.0), "duration": (0.0, 3600.0, 5.0),
    "frames": (0, 100000, 10), "columns": (24, 500, 1), "rows": (8, 200, 1),
    "terminal_columns": (24, 600, 1), "terminal_rows": (8, 240, 1),
    "font_size": (4.0, 72.0, 0.5),
    "seed": (0, 99999, 1), "control_poll": (0.05, 2.0, 0.05),
    "snow_rate": (0.0, 500.0, 5.0), "max_flakes": (0, 5000, 25),
    "preload_seconds": (0.0, 20.0, 0.5), "fall_speed": (1.0, 80.0, 1.0),
    "speed_variation": (0.0, 0.95, 0.05), "wind": (-30.0, 30.0, 0.5),
    "gust_strength": (0.0, 30.0, 0.5), "gust_period": (0.5, 30.0, 0.5),
    "drift": (0.0, 15.0, 0.25), "wobble": (0.0, 10.0, 0.25),
    "rain_share": (0.0, 1.0, 0.05), "hail_share": (0.0, 1.0, 0.05),
    "weather_foreground_share": (0.0, 1.0, 0.05),
    "rain_speed": (1.0, 8.0, 0.1), "rain_length": (1, 40, 1),
    "hail_size": (0.5, 6.0, 0.25), "hail_bounce": (0.0, 1.0, 0.05),
    "lightning_interval": (1.0, 180.0, 1.0),
    "lightning_flash": (0.05, 2.0, 0.05),
    "lightning_branches": (0, 16, 1),
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
    "tree_branch_thickness_ratio": (0.1, 1.0, 0.05),
    "conifer_colour_variation": (0.0, 100.0, 2.0),
    "tree_thickness_exponent": (1.2, 4.0, 0.1),
    "tree_segment_budget": (0, 100000, 500),
    "object_snow_capture": (0.0, 1.0, 0.01),
    "object_snow_max": (0, 5000, 25),
    "object_snow_hold": (0.0, 60.0, 0.5),
    "object_snow_hold_jitter": (0.0, 60.0, 0.5),
    "object_snow_adhesion": (0.0, 20.0, 0.25),
    "cabin_count": (0, 20, 1), "max_cabins": (0, 20, 1),
    "cabin_scale": (0.25, 3.0, 0.05), "leaf_count": (0, 1000, 10),
    "cabin_depth_share": (0.0, 1.0, 0.05),
    "cabin_depth_scale": (0.25, 0.95, 0.05),
    "cabin_path_curl": (0.0, 2.0, 0.1),
    "tumbleweed_count": (0, 100, 1), "ambient_speed": (0.0, 40.0, 0.5),
    "tumbleweed_climb": (0.0, 2.0, 0.05),
    "tumbleweed_collapse_pressure": (0.0, 20.0, 0.25),
    "cabin_size_variation": (0.0, 0.75, 0.025),
    "rabbit_count": (0, 20, 1), "rabbit_interval": (1.0, 180.0, 2.0),
    "rabbit_speed": (1.0, 50.0, 1.0),
    "npc_count": (0, 30, 1),
    "npc_speed_min": (0.5, 40.0, 0.5),
    "npc_speed_max": (0.5, 60.0, 0.5),
    "npc_decision_min_seconds": (0.25, 120.0, 0.25),
    "npc_decision_max_seconds": (0.25, 240.0, 0.5),
    "npc_response_seconds": (0.05, 8.0, 0.05),
    "npc_object_awareness": (0.0, 120.0, 1.0),
    "npc_avoidance_strength": (0.0, 4.0, 0.1),
    "npc_crossing_motivation_min": (-1.0, 1.0, 0.05),
    "npc_crossing_motivation_max": (-1.0, 1.0, 0.05),
    "npc_wander_angle": (0.0, 180.0, 5.0),
    "npc_reversal_chance": (0.0, 1.0, 0.05),
    "npc_side_spawn_share": (0.0, 1.0, 0.05),
    "npc_respawn_seconds": (0.1, 60.0, 0.5),
    "npc_depth_min": (0.05, 2.0, 0.05),
    "npc_depth_max": (0.05, 2.0, 0.05),
    "npc_social_factor": (-1.0, 1.0, 0.05),
    "npc_social_distance": (0.0, 120.0, 1.0),
    "npc_path_adherence": (0.0, 1.0, 0.05),
    "npc_viewport_respawn_chance": (0.0, 1.0, 0.05),
    "npc_track_id": (-1, 29, 1),
    "postman_interval": (1.0, 600.0, 5.0),
    "postman_speed": (1.0, 40.0, 0.5),
    "postman_stop_seconds": (0.5, 30.0, 0.5),
    "postman_delivery_frequency": (0.0, 8.0, 0.1),
    "flyby_interval": (1.0, 300.0, 5.0),
    "flyby_speed": (1.0, 100.0, 2.0), "plough_interval": (1.0, 600.0, 5.0),
    "superman_frequency": (0.1, 12.0, 0.1),
    "superman_speed": (1.0, 160.0, 2.0),
    "helicopter_hover_seconds": (0.5, 20.0, 0.5),
    "helicopter_wait_min": (0.0, 60.0, 0.5),
    "helicopter_wait_max": (0.0, 120.0, 0.5),
    "helicopter_downwash": (0.0, 4.0, 0.1),
    "helicopter_downwash_width": (0.25, 4.0, 0.1),
    "aircraft_crash_descent": (1.0, 120.0, 2.0),
    "aircraft_crash_arc": (0.0, 2.0, 0.05),
    "aircraft_crash_spin": (0.0, 12.0, 0.25),
    "aircraft_crash_smoke": (0.0, 6.0, 0.1),
    "explosion_size": (0.1, 8.0, 0.1),
    "explosion_seconds": (1.0, 60.0, 1.0),
    "horizon_dirt_density": (0.0, 1.0, 0.05),
    "horizon_randomness": (0.0, 1.0, 0.05),
    "horizon_height": (0.15, 0.85, 0.02),
    "horizon_hut_density": (0.0, 2.0, 0.05),
    "snow_fallaway_threshold": (0.0, 1.0, 0.01),
    "snow_fallaway_min_seconds": (0.0, 120.0, 1.0),
    "snow_fallaway_max_seconds": (0.0, 240.0, 1.0),
    "snow_fallaway_width": (0.01, 0.5, 0.01),
    "cloud_count": (0, 60, 1), "cloud_speed": (0.0, 40.0, 0.5),
    "cloud_parallax": (0.0, 4.0, 0.1),
    "santa_scale_min": (0.01, 2.0, 0.01),
    "santa_scale_max": (0.01, 2.0, 0.05),
    "santa_arc_height": (0.0, 0.5, 0.01),
    "santa_trail_seconds": (0.0, 15.0, 0.25),
    "santa_trail_length": (0.25, 8.0, 0.25),
    "santa_presents_min": (1, 20, 1),
    "santa_presents_max": (1, 30, 1),
    "present_fall_speed": (1.0, 80.0, 1.0),
    "ufo_hover_seconds": (1.0, 20.0, 0.5),
    "ufo_trail_seconds": (0.0, 15.0, 0.25),
    "ufo_trail_length": (0.25, 8.0, 0.25),
    "ejection_chance": (0.0, 1.0, 0.05),
    "parachute_fall_speed": (1.0, 30.0, 0.5),
    "plough_speed": (1.0, 100.0, 2.0), "plough_clear_to": (0.0, 0.50, 0.005),
}

RESTART_ONLY = frozenset({
    "mode", "duration", "frames", "columns", "rows", "seed", "snapshot",
    "no_dashboard", "detailed_dashboard", "preload_seconds", "initial_snow",
    "bank_drift", "control_poll", "terminal_columns", "terminal_rows",
    "font_size", "window_position", "native_encoder",
})

GROUP_COLOURS = {
    "display and reproducibility": 1,
    "launcher window reproduction": 3,
    "live control": 4,
    "falling snow": 6,
    "sky and atmosphere": 7,
    "clouds and parallax": 6,
    "rain hail and lightning": 1,
    "accumulation and shedding": 5,
    "seasonal scenery": 2,
    "wildlife and occasional events": 7,
}

GROUP_ICONS = {
    "display and reproducibility": "▣",
    "launcher window reproduction": "▤",
    "live control": "◎",
    "falling snow": "❄",
    "sky and atmosphere": "◒",
    "clouds and parallax": "☁",
    "rain hail and lightning": "☂",
    "accumulation and shedding": "▂",
    "seasonal scenery": "♠",
    "wildlife and occasional events": "✦",
}

OPTION_ICONS = {
    "mode": "▦", "fps": "◷", "duration": "◴", "frames": "≡",
    "physics": "⚙", "native_encoder": "⚡",
    "columns": "↔", "rows": "↕", "seed": "※", "snapshot": "▣",
    "terminal_columns": "⇔", "terminal_rows": "⇕", "font_size": "A",
    "window_position": "⌖",
    "no_dashboard": "▤", "detailed_dashboard": "▥", "listen": "◎",
    "control_poll": "↻", "snow_rate": "❄", "max_flakes": "⁙",
    "preload_seconds": "◌", "flake_sizes": "✣", "size_weights": "⚖",
    "fall_speed": "↓", "speed_variation": "±", "wind": "→",
    "gust_strength": "≋", "gust_period": "∿", "drift": "⌁",
    "wobble": "〰", "palette": "◈", "sky": "◒",
    "sky_colours": "◈", "sky_stops": "↕", "sky_blend": "≋",
    "clouds": "☁", "cloud_count": "☷", "cloud_speed": "→",
    "cloud_depths": "◫", "cloud_parallax": "≋", "cloud_colours": "◈",
    "weather": "☂", "weather_foreground_share": "◩",
    "rain_share": "╱", "hail_share": "●",
    "rain_speed": "⇣", "rain_length": "│", "rain_colour": "◈",
    "hail_size": "●", "hail_bounce": "↥", "hail_colour": "◈",
    "lightning": "ϟ", "lightning_interval": "◴",
    "lightning_flash": "✦", "lightning_branches": "⑂",
    "initial_snow": "▂",
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
    "tree_branch_thickness_ratio": "⑂",
    "conifer_colour_variation": "◈",
    "tree_segment_budget": "Σ", "lights": "✦",
    "object_snow": "❅", "object_snow_capture": "⌁",
    "object_snow_max": "▦", "object_snow_hold": "◴",
    "object_snow_hold_jitter": "±", "object_snow_adhesion": "⚖",
    "cabin_count": "⌂", "max_cabins": "⌂", "cabin_scale": "↕",
    "cabin_types": "⌂", "cabin_size_variation": "±",
    "cabin_depth_share": "◫", "cabin_depth_scale": "↕",
    "cabin_path_style": "〰", "cabin_path_curl": "∿", "ambient": "≈",
    "leaf_count": "❧", "tumbleweed_count": "⊛", "ambient_speed": "→",
    "tumbleweed_climb": "∡", "tumbleweed_collapse_pressure": "⇥",
    "rabbit_count": "♙", "rabbit_interval": "◴", "rabbit_speed": "→",
    "npcs": "♟", "npc_count": "♟", "npc_colours": "◈",
    "npc_speed_min": "⇥", "npc_speed_max": "→",
    "npc_decision_min_seconds": "◴",
    "npc_decision_max_seconds": "◷",
    "npc_response_seconds": "↻", "npc_object_awareness": "◉",
    "npc_avoidance_strength": "↯",
    "npc_crossing_motivation_min": "⇤",
    "npc_crossing_motivation_max": "⇥",
    "npc_wander_angle": "⟳", "npc_reversal_chance": "↶",
    "npc_side_spawn_share": "↔", "npc_respawn_seconds": "◌",
    "npc_depth_min": "·", "npc_depth_max": "◆",
    "npc_social_factor": "☍", "npc_social_distance": "↔",
    "npc_path_adherence": "⌁", "npc_viewport_respawn_chance": "↺",
    "npc_track_id": "⌖",
    "postman": "♟", "postman_interval": "◴", "postman_speed": "→",
    "postman_stop_seconds": "✉", "postman_delivery_frequency": "⟳",
    "sky_events": "✈", "flyby_interval": "◴", "flyby_speed": "→",
    "superman_path": "⌒", "superman_frequency": "◴",
    "superman_speed": "➜",
    "helicopter_hover_seconds": "⌁", "helicopter_wait_min": "◴",
    "helicopter_wait_max": "◷", "helicopter_downwash": "◎",
    "helicopter_downwash_width": "↔",
    "aircraft_crash": "↯", "aircraft_crash_depth": "◒",
    "aircraft_crash_descent": "⇣", "aircraft_crash_arc": "⌒",
    "aircraft_crash_spin": "⟳", "aircraft_crash_smoke": "♨",
    "explosion_types": "✹", "explosion_size": "✺",
    "explosion_seconds": "◴", "ufo_beam_style": "⌁",
    "horizon_structure": "▱", "horizon_dirt_density": "⠿",
    "horizon_randomness": "≈", "horizon_height": "⌁",
    "horizon_hut_density": "⌂", "snow_fallaway_threshold": "▴",
    "snow_fallaway_min_seconds": "◴",
    "snow_fallaway_max_seconds": "◷", "snow_fallaway_width": "↔",
    "aeroplane_types": "✈", "pilot_ejection": "♟",
    "ejection_chance": "⚄", "parachute_fall_speed": "☂",
    "santa_scale_min": "·", "santa_scale_max": "◆", "santa_arc_height": "⌒",
    "santa_trail_seconds": "◴", "santa_trail_length": "☄",
    "santa_presents": "◆", "santa_presents_min": "▣",
    "santa_presents_max": "▦", "present_fall_speed": "⇣",
    "ufo_abduction": "⌁", "ufo_hover_seconds": "◴",
    "ufo_types": "◉", "ufo_trail_seconds": "◴",
    "ufo_trail_length": "☄",
    "snow_plough": "▰", "plough_interval": "◴", "plough_speed": "→",
    "plough_clear_to": "▁",
}

IMPACT_GUIDANCE = {
    "physics": "NONE provides the cheapest legacy-style fall/deposit path; GROUND adds bank slumping and terrain-aware bodies; FULL also indexes scenery so snow can rest and shed from objects.",
    "native_encoder": "AUTO uses the optional Rust cell analyser when built, OFF forces Python, and ON refuses to start if the native library is unavailable.",
    "fps": "Higher values make motion smoother but raise CPU and terminal-output work almost linearly.",
    "duration": "Zero runs until stopped; a positive value ends the viewer after that many seconds.",
    "frames": "Zero leaves duration in control; a positive value stops after an exact rendered-frame count.",
    "columns": "Larger fixed widths increase cell encoding, memory, and terminal output; omit this to follow live resizing.",
    "rows": "Larger fixed heights increase raster memory and cell encoding; omit this to follow live resizing.",
    "terminal_columns": "Initial WezTerm width saved by S. The console captures its current terminal width so replay starts with the same columns.",
    "terminal_rows": "Initial WezTerm height saved by S. The console captures its current terminal height so replay starts with the same rows.",
    "font_size": "Initial WezTerm point size. It is read from launcher metadata and written into the reproducible command.",
    "window_position": "Initial macOS WezTerm X,Y placement. Supply it when launching the console; terminal APIs do not report a reliably moved window position.",
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
    "sky": "ON paints the most distant full-scene layer; OFF restores a transparent black terminal background.",
    "sky_colours": "Two to eight top-to-bottom RRGGBB colours, for example 07152F,315A82,B9D8E8.",
    "sky_stops": "Matching increasing vertical fractions beginning at 0 and ending at 1; stops control where each colour is reached.",
    "sky_blend": "LINEAR changes evenly; SMOOTH eases both ends; COSINE gives the gentlest merge between colour stops.",
    "clouds": "ON adds continuously wrapping procedural clouds without loading image assets.",
    "cloud_count": "Number of cloud bodies. High counts add several filled ellipses per frame and can noticeably increase encoding work on wide grids.",
    "cloud_speed": "Base virtual-pixel speed; actual speed is depth-scaled so near clouds cross faster.",
    "cloud_depths": "One to eight comma-separated lanes from 0.05 far to 1 near; lanes at 0.62+ can pass in front of distant flights.",
    "cloud_parallax": "Higher values increase the speed difference between far and near clouds; zero largely removes depth parallax.",
    "cloud_colours": "Two to eight RRGGBB colours cycled through the cloud population; darker values read as storm layers.",
    "weather": "NONE disables precipitation and lightning; SNOW accumulates; RAIN draws wind-slanted streaks; HAIL can bounce; MIXED combines all three; STORM combines rain and hail.",
    "weather_foreground_share": "At creation, this fraction of snow, rain and hail is assigned in front of scenery; the remainder is occluded by trees, cabins and animals.",
    "rain_share": "Fraction of mixed precipitation rendered as rain; the remainder after rain and hail is snow.",
    "hail_share": "Fraction of mixed or storm precipitation rendered as hail. In mixed mode rain plus hail may not exceed 1.",
    "rain_speed": "Multiplier applied to normal fall speed; 2–4 gives visibly faster rainfall without excessive aliasing.",
    "rain_length": "Visible streak length in virtual pixels. Long streaks improve motion cues but touch more cells per frame.",
    "rain_colour": "Six-digit RGB colour for rain streaks, such as 78C8F0.",
    "hail_size": "Hailstone radius in virtual pixels. Large stones touch many pixels and increase compositor work.",
    "hail_bounce": "Chance of up to two terrain bounces per hailstone; zero removes bounce calculations.",
    "hail_colour": "Six-digit RGB colour for hailstones, such as DDF7FF.",
    "lightning": "Enables occasional deterministic branched bolts plus a brief brightening of the distant sky.",
    "lightning_interval": "Average quiet time between strikes; low values flash more frequently.",
    "lightning_flash": "Visible flash lifetime. Longer values keep the bolt and brightened sky on screen longer.",
    "lightning_branches": "Number of side forks on each bolt; more branches add line drawing work during flashes.",
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
    "conifer_colour_variation": "Maximum seeded RGB separation between pine, fir and spruce individuals. Zero is uniform; 20–45 is clear but natural; very high values are stylised.",
    "tree_branch_levels": "Adds recursive oak/maple/birch daughter generations; each extra level can roughly double their branch segments.",
    "tree_branch_angle": "Controls daughter divergence: narrow values make upright crowns; wide values produce spreading forms.",
    "tree_length_ratio": "Sets child/parent length from 0.35 to 0.90; high values make large, overlapping crowns.",
    "tree_trunk_thickness": "Sets base stroke width in virtual pixels; thick trunks survive coarse cells but occupy more raster area.",
    "tree_branch_thickness_ratio": "Decouples branch weight from the trunk; 0.42 keeps a 4.2 VPX main trunk while primary limbs begin near 1.8 VPX.",
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
    "rabbit_speed": "Near rabbits use this full terrain speed; distant rabbits move more slowly for parallax and are drawn behind cabins and trees.",
    "npcs": "ON manages a population of colour-varied people using the postman's cached jointed gait but an independent roaming/steering model.",
    "npc_count": "Number of concurrent NPC slots. A slot respawns after leaving; high counts increase steering comparisons and raster work.",
    "npc_colours": "Two to eight RRGGBB coat colours rotated across identities and respawn generations.",
    "npc_speed_min": "Slowest individual ground-plane speed before depth parallax is applied.",
    "npc_speed_max": "Fastest individual ground-plane speed; must be at least the minimum.",
    "npc_decision_min_seconds": "Shortest time between autonomous heading decisions.",
    "npc_decision_max_seconds": "Longest time between heading decisions; must be at least the minimum.",
    "npc_response_seconds": "Time used to turn toward a chosen or avoidance heading. Lower values react sharply; higher values make broad smooth turns.",
    "npc_object_awareness": "Ground-plane radius for noticing cabins, people, animals, crates, ploughs and helicopter exclusion zones.",
    "npc_avoidance_strength": "Force applied away from nearby objects. Zero disables active avoidance; values above 1 produce decisive detours.",
    "npc_crossing_motivation_min": "Minimum signed drive toward the assigned left/right destination. Zero is free wandering; negative values prefer the opposite side.",
    "npc_crossing_motivation_max": "Maximum signed crossing drive assigned across the population; must be at least the minimum.",
    "npc_wander_angle": "Heading freedom around lateral travel. Zero is straight, 90 permits depth turns, and 180 permits any 360-degree bearing.",
    "npc_reversal_chance": "Chance at each decision that the NPC swaps its intended left/right destination.",
    "npc_side_spawn_share": "One spawns only at left/right edges; zero spawns at near/far depth boundaries, with intermediate values mixing both.",
    "npc_respawn_seconds": "Mean hidden delay before an out-of-bounds slot receives a new colour/speed/motivation identity.",
    "npc_depth_min": "Furthest NPC lane. Lower values permit smaller figures closer to the artificial horizon.",
    "npc_depth_max": "Nearest NPC lane. One reaches the foreground; values above one enlarge through the viewport for a fourth-wall close-up.",
    "npc_social_factor": "Signed response to neighbours: negative disperses, zero is independent and positive creates loose groups that track one another.",
    "npc_social_distance": "Radius over which the social factor acts; personal-space avoidance remains active inside close range.",
    "npc_path_adherence": "Strength of attraction to the visible perspective dirt network. Zero permits free roaming; one strongly favours paths.",
    "npc_viewport_respawn_chance": "Chance that an NPC reaching the near viewport disappears and respawns elsewhere; otherwise it immediately turns away.",
    "npc_track_id": "Highlight and report one stable NPC slot by ID. Use -1 for no tracker; respawn generation remains visible in the dashboard.",
    "postman": "ON schedules a detailed jointed postman who turns away from the road, scales toward a real door, posts mail, waits, returns and continues.",
    "postman_interval": "Lower values schedule postal visits more often; each postman waits for the previous visit to finish.",
    "postman_speed": "Walking speed in virtual pixels per second; gait cadence follows it automatically.",
    "postman_stop_seconds": "Time spent waiting at the selected cabin door after the letter has been posted.",
    "postman_delivery_frequency": "Multiplier for scheduled visits: 0 disables them, 0.5 halves frequency, 1 is normal and 2 doubles it; cabins are visited in rotation.",
    "sky_events": "Select none, one event, or a comma list; AEROPLANE, HELICOPTER, AIRWOLF, KITE, UFO, SANTA and SUPERMAN rotate in order.",
    "flyby_interval": "Lower values reduce the quiet period between sky crossings.",
    "flyby_speed": "Higher values cross the viewport faster and shorten each visible flyby.",
    "superman_path": "STRAIGHT holds altitude, CURVE undulates, and ARC rises through the middle of the crossing.",
    "superman_frequency": "Requested Superman appearances per minute within the configured event rotation; other listed flights also consume rotation time.",
    "superman_speed": "Independent Superman flight speed in virtual pixels per second; very high values can visibly skip narrow cells.",
    "helicopter_hover_seconds": "Pause before descent and again before departure; longer values make the staged transition easier to inspect.",
    "helicopter_wait_min": "Shortest landed wait before the supply crate is released; paired with the maximum for deterministic variation.",
    "helicopter_wait_max": "Longest landed wait. Large values keep rotor downwash active and can remove more loose surface snow.",
    "helicopter_downwash": "Rotor coupling from 0 off to 4 extreme; high values displace precipitation, scour snow and add many animated particles.",
    "helicopter_downwash_width": "Radius multiplier from 0.25 narrow to 4 very wide. Large radii inspect and disturb more airborne particles per frame.",
    "aircraft_crash": "ON makes the aircraft left by an ejected pilot enter the rotating crash simulation, emit fire/smoke and produce a ground impact.",
    "aircraft_crash_depth": "AUTO deterministically alternates AWAY and TOWARD; AWAY shrinks toward the horizon, while a TOWARD impact grows into the snowy foreground and melts a local heat cavity.",
    "aircraft_crash_descent": "Base downward acceleration/speed from 1 slow to 120 violent. Higher values shorten the visible falling arc.",
    "aircraft_crash_arc": "Initial upward kick from 0 direct descent to 2 large arc before gravity wins.",
    "aircraft_crash_spin": "Rotations per second from 0 stable to 12 extreme; affects animation work only slightly.",
    "aircraft_crash_smoke": "Trail density from 0 off to 6 dense. High values add many particles and can materially increase render cost.",
    "explosion_types": "AUTO/ALL alternates red/yellow FIERY and apocalyptic NUCLEAR mushroom-cloud impacts; both persist and fade gradually rather than vanishing.",
    "explosion_size": "Linear impact scale from 0.1 tiny to 8 scene-filling. Large explosions rasterize substantially more pixels.",
    "explosion_seconds": "Visible lifetime from 1 to 60 seconds; long values allow several animated impacts to overlap.",
    "ufo_beam_style": "Choose SPIRAL, RINGS, LATTICE or STARGATE transporter motion without changing rabbit depth.",
    "horizon_structure": "NONE, DIRT, HUTS or BOTH adds perspective structure behind the main scenery.",
    "horizon_dirt_density": "Paint probability from 0 empty to 1 dense across the horizon band; high density increases scenery raster work each frame.",
    "horizon_randomness": "Seeded positional disorder from 0 ordered to 1 irregular for dirt and distant huts.",
    "horizon_height": "Artificial horizon position from 0.15 near the sky top to 0.85 near the ground.",
    "horizon_hut_density": "Distant hut frequency from 0 off to 2 dense village; high values add scenery raster work each frame.",
    "snow_fallaway_threshold": "Local snow-height trigger as a scene fraction; 0 disables. Reaching it starts the randomized countdown, shown on the SNOW dashboard.",
    "snow_fallaway_min_seconds": "Shortest sustained-height countdown before local mass falls away.",
    "snow_fallaway_max_seconds": "Longest repeatably randomized countdown; must be at least the minimum.",
    "snow_fallaway_width": "Fraction of display width released by the timed local failure from 0.01 narrow to 0.5 broad.",
    "cabin_depth_share": "Fraction of cabins deterministically assigned to an elevated distance lane; these produce longer postman approaches.",
    "cabin_depth_scale": "Distant-cabin size from 0.25 to 0.95 of normal; smaller values push cabins higher and make the delivery walk longer.",
    "cabin_path_style": "AUTO rotates diagonal, curved and curly cabin spurs; every rendered route is the exact waypoint path followed by the postman.",
    "cabin_path_curl": "Curvature amplitude from 0 straight to 2 exaggerated. Wider curls lengthen deliveries and add more dirt pixels.",
    "aeroplane_types": "COMMUTER is compact and rounded; AIRLINER is longer with repeated windows, a red stripe and swept wing.",
    "pilot_ejection": "ON permits a repeatably random far-distance ejection during an aeroplane pass.",
    "ejection_chance": "Probability per aeroplane pass; 0 disables ejections and 1 forces every eligible pass.",
    "parachute_fall_speed": "Terminal descent speed after the canopy opens; wind adds a small distant drift.",
    "santa_scale_min": "Furthest entry/exit scale. The 0.02 default reduces the formation to approximately a point before it approaches.",
    "santa_scale_max": "Nearest midpoint scale. The 0.50 default remains smaller than foreground houses; legacy --santa-scale sets this value.",
    "santa_arc_height": "Sets the mid-flight rise as a scene-height fraction; zero restores a straight crossing.",
    "santa_trail_seconds": "Controls how long emitted sparks remain and fade; long trails increase active particle work.",
    "santa_trail_length": "Spatial multiplier behind the sleigh; 3 is three times the original length and also emits enough sparks to avoid gaps.",
    "santa_presents": "ON drops a simultaneous group of parcels into every non-A-frame cabin chimney crossed by Santa.",
    "santa_presents_min": "Minimum parcels released on the same frame at each chimney; each receives a different initial fall speed.",
    "santa_presents_max": "Maximum simultaneous parcels. High values briefly add more animated objects and colour changes.",
    "present_fall_speed": "Initial parcel descent speed in virtual pixels per second; gravity then accelerates it toward the chimney.",
    "ufo_abduction": "ON lets each UFO pause over the terrain, reveal its beam only while a rabbit rises, and hide the rabbit after it enters the craft.",
    "ufo_hover_seconds": "Longer values slow the rabbit's rise and keep the UFO stationary for easier inspection.",
    "ufo_types": "Rotate SAUCER, ORB and DELTA space vehicles; all share the distant swoop, plasma trail and optional capture logic.",
    "ufo_trail_seconds": "How long plasma sparks fade after a swooping UFO; longer values increase particle work.",
    "ufo_trail_length": "Spatial and emission multiplier for the UFO plasma wake; high values add active particles.",
    "snow_plough": "ON schedules complete horizontal road-datum clearing passes; rabbits react when it approaches.",
    "plough_interval": "Lower values schedule bank-clearing passes more often.",
    "plough_speed": "Higher values clear the scene faster and leave less time to inspect the vehicle.",
    "plough_clear_to": "Lower fractions leave a thinner snow bank after a completed full-width pass.",
}

HIGH_COST = frozenset({
    "fps", "columns", "rows", "terminal_columns", "terminal_rows",
    "snow_rate", "max_flakes", "preload_seconds",
    "tree_density", "max_trees", "lights", "cabin_count", "max_cabins",
    "tree_branch_levels", "tree_branches", "tree_segment_budget",
    "rain_length", "hail_size", "lightning_branches",
    "object_snow_max", "object_snow_capture", "snow_relaxation",
    "cabin_scale", "leaf_count", "tumbleweed_count", "rabbit_count",
    "npc_count",
    "aircraft_crash_smoke", "explosion_size", "horizon_dirt_density",
    "horizon_hut_density",
})
MEDIUM_COST = frozenset({
    "physics", "flake_sizes", "detailed_dashboard", "ambient", "ambient_speed",
    "sky", "sky_events", "flyby_interval", "santa_trail_length",
    "santa_trail_seconds", "weather", "weather_foreground_share",
    "hail_bounce", "lightning",
    "lightning_interval", "snow_plough", "ufo_trail_length",
    "ufo_trail_seconds", "pilot_ejection", "postman", "npcs",
    "npc_object_awareness", "npc_social_distance", "npc_path_adherence",
    "helicopter_downwash", "helicopter_downwash_width",
    "aircraft_crash", "explosion_seconds", "horizon_structure",
})

CONTROL_TAB_SPECS = (
    ("DISPLAY", "▣", frozenset({
        "mode", "fps", "duration", "frames", "columns", "rows", "seed",
        "snapshot", "no_dashboard", "detailed_dashboard", "physics",
        "native_encoder",
    })),
    ("WINDOW", "▤", frozenset({
        "terminal_columns", "terminal_rows", "font_size", "window_position",
    })),
    ("LIVE", "◎", frozenset({"control_poll"})),
    ("SNOW", "❄", frozenset({
        "snow_rate", "max_flakes", "preload_seconds", "flake_sizes",
        "size_weights", "fall_speed", "speed_variation", "wind",
        "gust_strength", "gust_period", "drift", "wobble", "palette",
    })),
    ("SKY", "◒", frozenset({"sky", "sky_colours", "sky_stops", "sky_blend"})),
    ("CLOUDS", "☁", frozenset({
        "clouds", "cloud_count", "cloud_speed", "cloud_depths",
        "cloud_parallax", "cloud_colours",
    })),
    ("WEATHER", "☂", frozenset({
        "weather", "weather_foreground_share", "rain_share", "hail_share",
        "rain_speed", "rain_length",
        "rain_colour", "hail_size", "hail_bounce", "hail_colour", "lightning",
        "lightning_interval", "lightning_flash", "lightning_branches",
    })),
    ("GROUND", "▂", frozenset({
        "initial_snow", "bank_drift", "accumulation", "accumulate",
        "snow_repose_slope", "snow_relaxation", "shed_threshold", "shed_to",
        "shed_width", "shed_rate", "tower_collapse", "tower_age",
        "tower_age_jitter", "tower_prominence", "tower_collapse_rate",
        "tower_cascade_chance", "tower_cascade_radius",
        "snow_fallaway_threshold", "snow_fallaway_min_seconds",
        "snow_fallaway_max_seconds", "snow_fallaway_width",
        "snow_plough", "plough_interval", "plough_speed", "plough_clear_to",
    })),
    ("SCENE", "⌂", frozenset({
        "scenery", "cabin", "reindeer", "cabin_count", "max_cabins",
        "cabin_scale", "cabin_types", "cabin_size_variation",
        "cabin_depth_share", "cabin_depth_scale", "cabin_path_style",
        "cabin_path_curl", "horizon_structure", "horizon_dirt_density",
        "horizon_randomness", "horizon_height", "horizon_hut_density",
    })),
    ("TREES", "♠", frozenset({
        "no_trees", "tree_density", "max_trees", "tree_sway", "tree_types", "tree_branches",
        "tree_branch_levels", "tree_branch_angle", "tree_length_ratio",
        "tree_trunk_thickness", "tree_branch_thickness_ratio",
        "conifer_colour_variation",
        "tree_thickness_exponent",
        "tree_segment_budget", "lights", "object_snow",
        "object_snow_capture", "object_snow_max", "object_snow_hold",
        "object_snow_hold_jitter", "object_snow_adhesion",
    })),
    ("ANIMALS", "♙", frozenset({
        "ambient", "leaf_count", "tumbleweed_count", "ambient_speed",
        "tumbleweed_climb", "tumbleweed_collapse_pressure", "rabbit_count",
        "rabbit_interval", "rabbit_speed", "npcs", "npc_count",
        "npc_colours", "npc_speed_min", "npc_speed_max",
        "npc_decision_min_seconds", "npc_decision_max_seconds",
        "npc_response_seconds", "npc_object_awareness",
        "npc_avoidance_strength", "npc_crossing_motivation_min",
        "npc_crossing_motivation_max", "npc_wander_angle",
        "npc_reversal_chance", "npc_side_spawn_share",
        "npc_respawn_seconds", "npc_depth_min", "npc_depth_max",
        "npc_social_factor", "npc_social_distance", "npc_path_adherence",
        "npc_viewport_respawn_chance",
        "npc_track_id", "postman", "postman_interval",
        "postman_speed", "postman_stop_seconds", "postman_delivery_frequency",
    })),
    ("FLIGHTS", "✈", frozenset({
        "sky_events", "flyby_interval", "flyby_speed", "aeroplane_types",
        "superman_path", "superman_frequency", "superman_speed",
        "helicopter_hover_seconds", "helicopter_wait_min",
        "helicopter_wait_max", "helicopter_downwash",
        "helicopter_downwash_width",
        "pilot_ejection", "ejection_chance", "parachute_fall_speed",
        "aircraft_crash", "aircraft_crash_depth", "aircraft_crash_descent",
        "aircraft_crash_arc", "aircraft_crash_spin", "aircraft_crash_smoke",
        "explosion_types", "explosion_size", "explosion_seconds",
        "santa_scale_min", "santa_scale_max",
        "santa_arc_height", "santa_trail_seconds", "santa_trail_length",
        "santa_presents", "santa_presents_min", "santa_presents_max",
        "present_fall_speed",
        "ufo_abduction", "ufo_hover_seconds", "ufo_types",
        "ufo_trail_seconds", "ufo_trail_length", "ufo_beam_style",
    })),
)


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
        if isinstance(value[0], tuple) and len(value[0]) == 3:
            return ",".join(
                f"{red:02X}{green:02X}{blue:02X}"
                for red, green, blue in value)
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
            if action.dest in ("rain_colour", "hail_colour"):
                rendered = "".join(f"{channel:02X}" for channel in value)
            else:
                rendered = value_text(value)
            argv.extend((option_for(action), rendered))
    return argv


class Controller:
    def __init__(self, cli):
        self.cli = cli
        self.snow_parser = build_parser()
        self.actions = [action for action in self.snow_parser._actions
                        if action.dest not in ("help", "listen")]
        assigned = set()
        self.tabs = []
        for label, icon, destinations in CONTROL_TAB_SPECS:
            actions = [action for action in self.actions
                       if action.dest in destinations]
            if actions:
                self.tabs.append((label, icon, actions))
                assigned.update(action.dest for action in actions)
        remaining = [action for action in self.actions
                     if action.dest not in assigned]
        if remaining:
            self.tabs.append(("OTHER", "◇", remaining))
        self.tab_index = 0
        self.index = 0
        self.scroll = 0
        self.revision = 0
        self.restart_generation = 0
        self.status = "Ready"
        self.command_message = ""
        self.values = self.load_initial()
        self.apply_launcher_defaults()
        self.publish("Initial settings published")

    @property
    def page_actions(self):
        return self.tabs[self.tab_index][2]

    @property
    def selected_action(self):
        return self.page_actions[self.index]

    def cycle_tab(self, direction=1):
        self.tab_index = (self.tab_index + direction) % len(self.tabs)
        self.index = 0
        self.scroll = 0
        self.status = f"Page {self.tabs[self.tab_index][0]}"

    def tab_strip(self, width):
        segments = []
        for index, (label, icon, _) in enumerate(self.tabs):
            text = f"{icon}{label}"
            segments.append(f"[{text}]" if index == self.tab_index else text)
        available = max(8, width - 3)
        if len("  ".join(segments)) <= available:
            return "  ".join(segments)
        selected = self.tab_index
        left = right = selected
        while True:
            candidates = []
            if left > 0:
                candidates.append((left - 1, right))
            if right + 1 < len(segments):
                candidates.append((left, right + 1))
            adopted = False
            for next_left, next_right in candidates:
                prefix = "‹ " if next_left > 0 else ""
                suffix = " ›" if next_right + 1 < len(segments) else ""
                text = prefix + "  ".join(segments[next_left:next_right + 1]) + suffix
                if len(text) <= available:
                    left, right = next_left, next_right
                    adopted = True
                    break
            if not adopted:
                break
        prefix = "‹ " if left > 0 else ""
        suffix = " ›" if right + 1 < len(segments) else ""
        return prefix + "  ".join(segments[left:right + 1]) + suffix

    def launcher_metadata(self):
        path = os.environ.get("FONT_DEMO_GEOMETRY_FILE", "")
        if not path:
            return {}
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def apply_launcher_defaults(self):
        metadata = self.launcher_metadata()
        columns = metadata.get("columns") or os.environ.get("FONT_DEMO_COLUMNS")
        rows = metadata.get("rows") or os.environ.get("FONT_DEMO_ROWS")
        font_size = metadata.get("font_size") or os.environ.get("FONT_DEMO_SIZE")
        position = metadata.get("window_position") or os.environ.get("FONT_DEMO_POSITION")
        try:
            if self.values.terminal_columns is None and columns is not None:
                self.values.terminal_columns = int(columns)
            if self.values.terminal_rows is None and rows is not None:
                self.values.terminal_rows = int(rows)
            if self.values.font_size is None and font_size is not None:
                self.values.font_size = float(font_size)
            if self.values.window_position is None and position:
                self.values.window_position = str(position)
            self.values = self.parse_safely(
                namespace_to_argv(self.values, self.actions))
        except (ValueError, TypeError, SystemExit):
            self.status = "Launcher geometry metadata was invalid; using preset values"

    def capture_window_state(self):
        """Capture the live PTY size plus launcher-reported font/position."""
        size = shutil.get_terminal_size((120, 36))
        self.values.terminal_columns = max(24, size.columns)
        self.values.terminal_rows = max(8, size.lines)
        metadata = self.launcher_metadata()
        font_size = metadata.get("font_size") or os.environ.get("FONT_DEMO_SIZE")
        position = metadata.get("window_position") or os.environ.get("FONT_DEMO_POSITION")
        if (sys.platform == "darwin" and
                os.environ.get("FONT_DEMO_WEZTERM_WINDOW") == "1" and
                shutil.which("osascript")):
            script = (
                'tell application "System Events"\n'
                'set appProcess to first application process whose frontmost is true\n'
                'set windowPosition to position of front window of appProcess\n'
                'return (item 1 of windowPosition as text) & "," & '
                '(item 2 of windowPosition as text)\nend tell'
            )
            try:
                completed = subprocess.run(
                    ["osascript", "-e", script], capture_output=True,
                    text=True, timeout=2.0, check=False)
                detected = completed.stdout.strip()
                if completed.returncode == 0 and detected:
                    position = detected
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.values.font_size = float(font_size or self.values.font_size or 12.0)
        if position:
            self.values.window_position = str(position)
        self.values = self.parse_safely(namespace_to_argv(self.values, self.actions))

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
                        self.restart_generation = int(payload.get("restart", 0))
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
            "restart": self.restart_generation,
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

    def command_parts(self, values=None):
        values = values or self.values
        settings = [item for item in namespace_to_argv(values, self.actions)
                    if item not in ("--mode", values.mode)]
        if sys.platform == "darwin":
            prefix = ["./scripts/macos/run-demo.sh", values.mode, "christmas-snow"]
        elif os.name == "nt":
            prefix = ["python", r".\demos\seasonal\christmas_snow.py",
                      "--mode", values.mode]
        elif values.mode == "pua4":
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

    def command(self, values=None):
        """Return a copyable multiline command with real shell continuations."""
        prefix, segments = self.command_parts(values)
        continuation = " `\n  " if os.name == "nt" else " \\\n  "
        rendered = shlex.join(prefix)
        if segments:
            rendered += continuation + continuation.join(shlex.join(part) for part in segments)
        return rendered

    def isolated_preview_values(self):
        """Return a validated visual-only configuration for the active page."""
        values = copy.deepcopy(self.values)
        page = self.tabs[self.tab_index][0]
        values.snapshot = False
        values.duration = 0.0
        values.frames = 0
        values.detailed_dashboard = False
        values.no_dashboard = False
        values.window_position = None

        def no_weather():
            values.weather = "none"
            values.lightning = False

        def no_ground():
            values.initial_snow = 0.0
            values.bank_drift = 0.0
            values.accumulation = 0.0
            values.accumulate = False
            values.snow_plough = False

        def no_scene():
            values.scenery = "none"
            values.cabin = False
            values.reindeer = False
            values.no_trees = True
            values.tree_density = 0.0

        def no_animals():
            values.ambient = "none"
            values.leaf_count = 0
            values.tumbleweed_count = 0
            values.rabbit_count = 0
            values.npcs = False
            values.npc_count = 0

        def no_flights():
            values.sky_events = ()
            values.ufo_abduction = False

        def no_clouds():
            values.clouds = False
            values.cloud_count = 0

        if page in {"DISPLAY", "WINDOW", "LIVE"}:
            return self.parse_safely(namespace_to_argv(values, self.actions))
        if page == "SKY":
            no_weather(); no_ground(); no_scene(); no_animals(); no_flights(); no_clouds()
        elif page == "CLOUDS":
            no_weather(); no_ground(); no_scene(); no_animals(); no_flights()
            values.clouds = True
        elif page in {"SNOW", "WEATHER"}:
            no_ground(); no_scene(); no_animals(); no_flights(); no_clouds(); values.sky = False
            if page == "SNOW":
                values.weather = "snow"
                values.lightning = False
        elif page == "GROUND":
            no_weather(); no_scene(); no_animals(); no_flights(); no_clouds(); values.sky = False
        elif page == "SCENE":
            no_weather(); no_ground(); no_animals(); no_flights(); no_clouds(); values.sky = False
        elif page == "TREES":
            no_weather(); no_ground(); no_animals(); no_flights(); no_clouds(); values.sky = False
            values.scenery = "trees"
            values.cabin = False
            values.reindeer = False
            values.no_trees = False
        elif page == "ANIMALS":
            no_weather(); no_scene(); no_flights(); no_clouds(); values.sky = False
            values.initial_snow = 0.025
            values.bank_drift = 0.01
            values.accumulation = 0.0
            values.accumulate = False
            values.snow_plough = False
        elif page == "FLIGHTS":
            no_weather(); no_ground(); no_scene(); no_animals(); no_clouds(); values.sky = False
        return self.parse_safely(namespace_to_argv(values, self.actions))

    def launch_preview(self):
        """Launch an isolated renderer for this page without blocking the TUI."""
        values = self.isolated_preview_values()
        prefix, segments = self.command_parts(values)
        argv = prefix + [item for segment in segments for item in segment]
        repository = Path(__file__).resolve().parents[2]
        kwargs = {
            "cwd": str(repository),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(argv, **kwargs)
            page = self.tabs[self.tab_index][0]
            self.status = f"Launched isolated {page} preview · current values · wind retained"
        except OSError as error:
            self.status = f"Preview launch failed: {error}"

    def save(self):
        self.capture_window_state()
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
        geometry = (f" · {self.values.terminal_columns}×{self.values.terminal_rows}"
                    f" @ {self.values.font_size:g}pt")
        if self.values.window_position:
            geometry += f" · position {self.values.window_position}"
        self.status = f"Saved {destination} and {command_path}{geometry}{suffix}"

    def restart_viewer(self):
        """Ask the listening viewer to rebuild in its existing terminal."""
        self.restart_generation += 1
        self.publish("Viewer restart requested in its current window")

    def reset(self):
        self.values = self.parse_safely(["--mode", self.values.mode])
        self.apply_launcher_defaults()
        self.publish("Defaults restored")

    def validate_and_publish(self, action, candidate):
        old = getattr(self.values, action.dest)
        old_weights = self.values.size_weights
        old_stops = self.values.sky_stops
        setattr(self.values, action.dest, candidate)
        if action.dest == "flake_sizes":
            existing = dict(zip(old, old_weights))
            self.values.size_weights = tuple(
                existing.get(name, DEFAULT_FLAKE_WEIGHTS[name])
                for name in candidate)
        if action.dest == "sky_colours" and len(candidate) != len(old_stops):
            self.values.sky_stops = tuple(
                index / (len(candidate) - 1) for index in range(len(candidate)))
        try:
            self.values = self.parse_safely(namespace_to_argv(self.values, self.actions))
        except SystemExit:
            setattr(self.values, action.dest, old)
            self.values.size_weights = old_weights
            self.values.sky_stops = old_stops
            self.status = "Rejected: setting conflicts with another option"
            return
        scope = "viewer restart required" if action.dest in RESTART_ONLY else "applied live"
        self.publish(f"{option_for(action)} {scope}")

    def adjust(self, direction):
        action = self.selected_action
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
        action = self.selected_action
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

        self.put(screen, 5, 1, self.tab_strip(width),
                 curses.color_pair(6) | curses.A_BOLD)
        strip = self.tab_strip(width)
        tab_colours = (1, 3, 4, 6, 5, 2, 7, 3, 2, 4, 1)
        for tab_index, (label, icon, _) in enumerate(self.tabs):
            token = f"{icon}{label}"
            offset = strip.find(token)
            if offset < 0:
                continue
            selected = tab_index == self.tab_index
            icon_style = curses.color_pair(tab_colours[tab_index % len(tab_colours)]) | curses.A_BOLD
            label_style = (curses.color_pair(3) | curses.A_BOLD
                           if selected else curses.color_pair(6) | curses.A_BOLD)
            self.put(screen, 5, 1 + offset, icon, icon_style)
            self.put(screen, 5, 1 + offset + len(icon), label, label_style)

        panel_width = max(46, int(width * 0.64)) if width >= 92 else width - 2
        actions = self.page_actions
        visible = height - 10
        if self.index < self.scroll:
            self.scroll = self.index
        if self.index >= self.scroll + visible:
            self.scroll = self.index - visible + 1
        for row, action in enumerate(actions[self.scroll:self.scroll + visible], 6):
            absolute = self.scroll + row - 6
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
            for row in range(6, height - 3):
                self.put(screen, row, split, "│", curses.color_pair(1))
            action = self.selected_action
            wrap_width = max(24, width - split - 5)
            details = []

            def section(title, text, heading_pair, body_pair=6):
                details.append((f"◆ {title}", curses.color_pair(heading_pair) | curses.A_BOLD))
                for line in textwrap.wrap(text, wrap_width) or [""]:
                    details.append(("  " + line, curses.color_pair(body_pair)))
                details.append(("", 0))

            details.append((f"◆ {self.icon(action)} SELECTED OPTION ◆",
                            curses.color_pair(3) | curses.A_BOLD))
            details.append((f"  {option_for(action)}", curses.color_pair(1) | curses.A_BOLD))
            details.append((f"  {action.container.title}", curses.color_pair(2)))
            details.append(("", 0))
            details.append(("CURRENT VALUE", curses.color_pair(5) | curses.A_BOLD))
            details.append((f"  {value_text(getattr(self.values, action.dest))}",
                            curses.color_pair(6) | curses.A_BOLD))
            scope = ('applies immediately' if action.dest in LIVE_OPTION_DESTS
                     else 'saved now; viewer restart required')
            details.append((f"  ◉ {scope}", curses.color_pair(2 if action.dest in LIVE_OPTION_DESTS else 7)))
            details.append(("", 0))
            section("WHAT IT CONTROLS", action.help or "No description supplied.", 4)
            guidance = self.guidance(action)
            if guidance:
                section("RANGE & INPUT", guidance[0], 1)
            if len(guidance) > 1:
                section("EXPECTED IMPACT", guidance[1].removeprefix("Predicted effect: "), 3)
            if len(guidance) > 2:
                performance_pair = 7 if action.dest in HIGH_COST else 2
                section("PERFORMANCE", guidance[2].removeprefix("Performance: "),
                        performance_pair, performance_pair)
            details.append((f"V  launch isolated {self.tabs[self.tab_index][0]} preview",
                            curses.color_pair(1) | curses.A_BOLD))
            details.append(("X  restart listening viewer in its current window",
                            curses.color_pair(3) | curses.A_BOLD))
            details.append(("←/→ adjust   Enter type   Space toggle", curses.color_pair(4)))
            for row, (line, style) in enumerate(details, 7):
                self.put(screen, row, split + 2, line, style)

        self.put(screen, height - 3, 0, "├" + "─" * (width - 2) + "┤", curses.color_pair(1))
        keys = " ⇥ TAB  ↑↓ SELECT  ←→ ADJUST  ⏎ TYPE  ␠ TOGGLE  V PREVIEW  X RESTART  S SAVE  P COMMAND  R RESET  Q QUIT "
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
            if key == 9:
                self.cycle_tab(1)
            elif key == getattr(curses, "KEY_BTAB", -1):
                self.cycle_tab(-1)
            if key == curses.KEY_UP:
                self.index = (self.index - 1) % len(self.page_actions)
            elif key == curses.KEY_DOWN:
                self.index = (self.index + 1) % len(self.page_actions)
            elif key == curses.KEY_PPAGE:
                self.index = max(0, self.index - max(1, screen.getmaxyx()[0] - 9))
            elif key == curses.KEY_NPAGE:
                self.index = min(len(self.page_actions) - 1,
                                 self.index + max(1, screen.getmaxyx()[0] - 9))
            elif key == curses.KEY_HOME:
                self.index = 0
            elif key == curses.KEY_END:
                self.index = len(self.page_actions) - 1
            elif key == curses.KEY_LEFT:
                self.adjust(-1)
            elif key == curses.KEY_RIGHT:
                self.adjust(1)
            elif key in (ord(" "),):
                action = self.selected_action
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
            elif key in (ord("v"), ord("V")):
                self.launch_preview()
            elif key in (ord("x"), ord("X")):
                self.restart_viewer()
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
