#!/usr/bin/env python3
"""Inspect and integrity-check a Voyager Graphics Recording (.vgr)."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path


HEADER = struct.Struct("<4sIHHBBd")


def value(mapping, *path, default=None):
    current = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--json", action="store_true",
                        help="print metadata.json rather than the summary")
    parser.add_argument("--no-crc", action="store_true",
                        help="skip testing every ZIP member CRC")
    args = parser.parse_args()

    try:
        with zipfile.ZipFile(args.recording, "r") as archive:
            metadata = json.loads(archive.read("metadata.json"))
            if not args.no_crc:
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"CRC failure in {bad}")
            if args.json:
                print(json.dumps(metadata, indent=2, sort_keys=True))
                return 0
            frames = metadata.get("frames", [])
            declared = value(metadata, "capture", "frame_count", default=0)
            if declared != len(frames):
                raise ValueError(
                    f"metadata declares {declared} frames but indexes {len(frames)}")
            first_header = None
            if frames:
                payload = archive.read(frames[0]["member"])
                if len(payload) < HEADER.size:
                    raise ValueError("first frame has a truncated VGF1 header")
                first_header = HEADER.unpack_from(payload)
                if first_header[0] != b"VGF1":
                    raise ValueError("first frame does not contain VGF1 magic")
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile,
            ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    capture = metadata.get("capture", {})
    terminal = metadata.get("terminal", {})
    render = metadata.get("render", {})
    duration = float(capture.get("duration_seconds") or 0.0)
    frames_per_second = float(capture.get("fps") or 0.0)
    measured = (len(frames) / duration) if duration > 0 else 0.0
    mode = render.get("mode", first_header[4] if first_header else "?")
    columns = terminal.get("columns", first_header[3] if first_header else "?")
    rows = terminal.get("rows", first_header[2] if first_header else "?")
    graphic_rows = terminal.get("graphic_rows", rows)
    print(f"VGR:              {args.recording.resolve()}")
    print(f"Schema/version:   {metadata.get('schema')} / {metadata.get('format_version')}")
    print(f"Renderer:         {value(metadata, 'renderer', 'title', default='unknown')}")
    print(f"Font mode:        {mode}x4")
    print(f"Terminal cells:   {columns} columns x {rows} rows ({graphic_rows} graphics rows)")
    print(f"Virtual pixels:   {terminal.get('virtual_width', '?')} x {terminal.get('virtual_height', '?')}")
    print(f"Frames:           {len(frames):,}")
    print(f"Duration:         {duration:,.3f} s")
    print(f"Playback FPS:     {frames_per_second:,.6f}")
    print(f"Frames/duration:  {measured:,.6f} fps")
    print(f"Style/camera:     {render.get('style', '?')} / {render.get('camera', '?')}")
    print(f"HLR:              {render.get('hidden_line_removal', '?')}")
    print(f"Archive bytes:    {args.recording.stat().st_size:,}")
    print(f"Frame raw bytes:  {capture.get('frame_raw_bytes', 'not recorded')}")
    print(f"Frame ZIP bytes:  {capture.get('frame_compressed_bytes', 'not recorded')}")
    print(f"CRC check:        {'skipped' if args.no_crc else 'PASS'}")
    if first_header:
        _, index, frame_rows, frame_columns, frame_mode, mask_bytes, timestamp = first_header
        print("First VGF1:       "
              f"index={index}, {frame_columns}x{frame_rows}, mode={frame_mode}, "
              f"mask_bytes={mask_bytes}, time={timestamp:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
