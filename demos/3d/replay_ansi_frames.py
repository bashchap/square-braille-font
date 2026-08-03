#!/usr/bin/env python3
"""Replay numbered, self-contained ANSI terminal frames."""

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path)
    ap.add_argument("--fps", type=float,
                    help="override recorded FPS (otherwise read recording.json)")
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()
    manifest_path = args.directory / "recording.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    fps = args.fps if args.fps is not None else float(manifest.get("fps", 1.0))
    if fps <= 0:
        ap.error("--fps must be positive")
    frames = sorted(args.directory.glob("frame_*.ansi"))
    if not frames:
        raise SystemExit(f"no frame_*.ansi files in {args.directory}")
    try:
        while True:
            deadline = time.monotonic()
            for frame in frames:
                sys.stdout.buffer.write(frame.read_bytes())
                sys.stdout.buffer.flush()
                deadline += 1.0 / fps
                time.sleep(max(0.0, deadline - time.monotonic()))
            if not args.loop:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\n")


if __name__ == "__main__":
    main()
