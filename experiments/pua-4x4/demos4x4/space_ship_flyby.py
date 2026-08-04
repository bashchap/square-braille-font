#!/usr/bin/env python3
"""High-detail PUA-pixel fly-around for the supplied spaceship mesh."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

import enterprise_wireframe as renderer


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def blend(a, b, amount):
    return np.asarray(a, dtype=np.float64) * (1.0 - amount) + np.asarray(b, dtype=np.float64) * amount


def camera_at(t, duration):
    """A six-shot cinematic flight reel with deliberate camera cuts."""
    reel = ((t % duration) / duration) * 6.0
    shot, raw = int(reel) % 6, reel % 1.0
    amount = smooth(raw)

    if shot == 0:  # Hero reveal: sweeping front-quarter arc.
        eye = blend((-.82, 1.95, .38), (.78, 1.78, -.24), amount)
        target = blend((-.08, 0, .08), (.10, 0, -.04), amount)
        roll = -.10 + .20 * amount
    elif shot == 1:  # Low pass beneath the port wing.
        eye = blend((-1.15, 1.42, -.62), (.95, 1.35, -.48), amount)
        target = blend((-.28, 0, -.08), (.30, 0, .02), amount)
        roll = -.22 + .42 * amount
    elif shot == 2:  # Head-on compression and rapid closing shot.
        eye = blend((.10, 2.75, .16), (-.12, 1.46, -.06), amount)
        target = blend((0, 0, .04), (.04, 0, -.03), amount)
        roll = .04 * math.sin(raw * math.tau)
    elif shot == 3:  # Wingtip tracking shot with a pronounced bank.
        eye = blend((-1.22, 1.68, .18), (1.16, 1.62, .42), amount)
        target = blend((-.34, 0, .02), (.30, 0, .10), amount)
        roll = .28 * math.sin(raw * math.pi)
    elif shot == 4:  # Reverse-side chase revealing the underside.
        eye = blend((.82, -1.92, -.42), (-.72, -1.72, .30), amount)
        target = blend((.12, 0, -.08), (-.10, 0, .06), amount)
        roll = .16 - .32 * amount
    else:  # Climbing beauty pass into the loop point.
        eye = blend((.96, 1.72, -.38), (-.82, 1.95, .38), amount)
        target = blend((.18, 0, -.08), (-.08, 0, .08), amount)
        roll = -.18 * math.sin(raw * math.pi)

    forward = renderer.normalize(target - eye)
    world_up = np.array((0.0, 0.0, 1.0))
    if abs(float(np.dot(forward, world_up))) > .96:
        world_up = np.array((0.0, 1.0, 0.0))
    right = renderer.normalize(np.cross(forward, world_up))
    up = renderer.normalize(np.cross(right, forward))
    cr, sr = math.cos(roll), math.sin(roll)
    right, up = right * cr + up * sr, up * cr - right * sr
    return eye, np.stack((right, up, forward))


def main():
    # Friendly recording alias. It captures exactly one complete reel unless
    # the caller explicitly supplies --frames or --freeze-at.
    if "--keep-frames" in sys.argv:
        position = sys.argv.index("--keep-frames")
        if position + 1 >= len(sys.argv):
            raise SystemExit("--keep-frames requires a directory")
        sys.argv[position] = "--record-dir"
        if "--frames" not in sys.argv and "--freeze-at" not in sys.argv:
            def option_value(name, default):
                return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
            duration = option_value("--duration", 60.0)
            fps = option_value("--fps", 1.0)
            sys.argv.extend(("--frames", str(max(1, round(duration * fps)))))
    renderer.camera_at = camera_at
    renderer.DEMO_TITLE = "PUA Supplied Spaceship — Cinematic Action Reel"
    default_mesh = Path(__file__).with_name("space_ship_wire.npz")
    if "--mesh" not in sys.argv and "--prepare-from" not in sys.argv:
        sys.argv[1:1] = ["--mesh", str(default_mesh)]
    renderer.main()


if __name__ == "__main__":
    main()
