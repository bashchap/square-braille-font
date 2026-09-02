#!/usr/bin/env python3
"""Indexed VGR recording container, capture dashboard, and timed player."""

from __future__ import annotations

import json
import math
import os
import select
import struct
import sys
import termios
import time
import tty
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from voyager_core import pua4_codepoint, terminal_picture


SCHEMA = "org.square-braille.voyager-recording"
FORMAT_VERSION = 1
FRAME_MAGIC = b"VGF1"
FRAME_HEADER = struct.Struct("<4sIHHBBd")

CYAN = (68, 224, 255)
CYAN_DIM = (32, 121, 151)
AMBER = (255, 178, 45)
ORANGE = (255, 92, 35)
WHITE = (214, 244, 255)
BLUE = (52, 137, 255)
GREEN = (69, 230, 170)
RED = (255, 76, 72)
DARK = (14, 54, 75)
GRID = (23, 83, 109)


class HudCanvas:
    """A cell-addressed true-colour canvas for the cinematic capture HUD."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.characters = [[" "]*width for _ in range(height)]
        self.colors = [[WHITE]*width for _ in range(height)]

    def put(self, x, y, character, color=WHITE):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.characters[y][x] = character
            self.colors[y][x] = color

    def text(self, x, y, value, color=WHITE, maximum=None):
        value = str(value)
        if maximum is not None:
            value = value[:max(0, maximum)]
        for offset, character in enumerate(value):
            self.put(x+offset, y, character, color)

    def hline(self, x0, x1, y, character="─", color=CYAN_DIM):
        for x in range(max(0, x0), min(self.width, x1+1)):
            self.put(x, y, character, color)

    def vline(self, x, y0, y1, character="│", color=CYAN_DIM):
        for y in range(max(0, y0), min(self.height, y1+1)):
            self.put(x, y, character, color)

    def box(self, x0, y0, x1, y1, color=CYAN_DIM, title=None):
        if x1 <= x0 or y1 <= y0:
            return
        self.hline(x0+1, x1-1, y0, "─", color)
        self.hline(x0+1, x1-1, y1, "─", color)
        self.vline(x0, y0+1, y1-1, "│", color)
        self.vline(x1, y0+1, y1-1, "│", color)
        for x, y, character in ((x0, y0, "┌"), (x1, y0, "┐"),
                                (x0, y1, "└"), (x1, y1, "┘")):
            self.put(x, y, character, color)
        if title:
            self.text(x0+2, y0, f" {title} ", CYAN)

    def ellipse(self, cx, cy, rx, ry, color=GRID, samples=180):
        for step in range(samples):
            angle = 2*math.pi*step/samples
            x = round(cx+rx*math.cos(angle))
            y = round(cy+ry*math.sin(angle))
            self.put(x, y, "·", color)

    def render(self):
        output = []
        for row, color_row in zip(self.characters, self.colors):
            previous = None
            parts = []
            for character, color in zip(row, color_row):
                if color != previous:
                    parts.append(f"\x1b[38;2;{color[0]};{color[1]};{color[2]}m")
                    previous = color
                parts.append(character)
            output.append("".join(parts)+"\x1b[0m")
        return "\n".join(output)


def paint(text, color, bold=False):
    prefix = "\x1b[1m" if bold else ""
    return f"{prefix}\x1b[38;2;{color[0]};{color[1]};{color[2]}m{text}\x1b[0m"


def format_seconds(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds//3600)
    minutes = int((seconds % 3600)//60)
    remaining = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:06.3f}"


def format_bytes(value):
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value):,} B"
        value /= 1024


def encode_frame_packet(index, animation_time, masks, colors, mode):
    rows, columns = masks.shape
    if not (0 < rows <= 65535 and 0 < columns <= 65535):
        raise ValueError("frame dimensions exceed VGR v1 limits")
    mask_bytes = 1 if mode == 2 else 2
    mask_dtype = np.dtype("u1") if mask_bytes == 1 else np.dtype("<u2")
    mask_data = np.asarray(masks, dtype=mask_dtype, order="C").tobytes()
    color_data = np.asarray(colors, dtype=np.uint8, order="C").tobytes()
    header = FRAME_HEADER.pack(FRAME_MAGIC, index, rows, columns, mode,
                               mask_bytes, animation_time)
    return header+mask_data+color_data


def decode_frame_packet(payload):
    if len(payload) < FRAME_HEADER.size:
        raise ValueError("truncated VGR frame header")
    magic, index, rows, columns, mode, mask_bytes, animation_time = \
        FRAME_HEADER.unpack_from(payload)
    if magic != FRAME_MAGIC or mode not in (2, 4):
        raise ValueError("invalid VGR frame header")
    expected_mask_bytes = 1 if mode == 2 else 2
    if mask_bytes != expected_mask_bytes:
        raise ValueError("VGR mask width does not match font mode")
    cells = rows*columns
    masks_end = FRAME_HEADER.size+cells*mask_bytes
    expected = masks_end+cells*3
    if len(payload) != expected:
        raise ValueError(f"VGR frame size mismatch: {len(payload)} != {expected}")
    mask_dtype = np.dtype("u1") if mask_bytes == 1 else np.dtype("<u2")
    masks = np.frombuffer(payload, dtype=mask_dtype, count=cells,
                          offset=FRAME_HEADER.size).reshape(rows, columns).copy()
    colors = np.frombuffer(payload, dtype=np.uint8, count=cells*3,
                           offset=masks_end).reshape(rows, columns, 3).copy()
    return index, animation_time, mode, masks, colors


class VGRWriter:
    """Write independently compressed frames into a ZIP-indexed VGR archive."""

    def __init__(self, path, metadata, force=False, compression=6):
        self.path = Path(path)
        self.partial = self.path.with_name(self.path.name+".partial")
        self.metadata = metadata
        self.force = force
        self.compression = compression
        self.archive = None
        self.frames = []
        self.raw_bytes = 0
        self.compressed_bytes = 0

    def __enter__(self):
        if self.path.exists() and not self.force:
            raise FileExistsError(f"capture already exists: {self.path} (use --force)")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.partial.exists():
            self.partial.unlink()
        self.archive = zipfile.ZipFile(
            self.partial, "w", compression=zipfile.ZIP_DEFLATED,
            compresslevel=self.compression, allowZip64=True)
        return self

    def add_frame(self, index, animation_time, masks, colors, render_seconds,
                  encounter, statistics=None):
        member = f"frames/{index:08d}.vgf"
        packet_started = time.perf_counter()
        payload = encode_frame_packet(index, animation_time, masks, colors,
                                      self.metadata["render"]["mode"])
        packet_seconds = time.perf_counter()-packet_started
        info = zipfile.ZipInfo(member)
        info.compress_type = zipfile.ZIP_DEFLATED
        write_started = time.perf_counter()
        self.archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED,
                              compresslevel=self.compression)
        stored = self.archive.getinfo(member)
        write_seconds = time.perf_counter()-write_started
        record = {
            "index": index,
            "member": member,
            "animation_time": animation_time,
            "render_seconds": render_seconds,
            "packet_seconds": packet_seconds,
            "write_seconds": write_seconds,
            "frame_seconds": render_seconds+packet_seconds+write_seconds,
            "raw_bytes": stored.file_size,
            "compressed_bytes": stored.compress_size,
            "crc32": f"{stored.CRC:08x}",
            "encounter": encounter,
        }
        if statistics is not None:
            record["visible_faces"] = int(statistics[0])
            record["visible_edges"] = int(statistics[1])
            if len(statistics) >= 6:
                record["scene_seconds"] = float(statistics[4])
                record["encode_seconds"] = float(statistics[5])
        self.frames.append(record)
        self.raw_bytes += stored.file_size
        self.compressed_bytes += stored.compress_size
        return record

    def finish(self, real_elapsed):
        self.metadata["frames"] = self.frames
        self.metadata["capture"].update({
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "real_elapsed_seconds": real_elapsed,
            "frame_raw_bytes": self.raw_bytes,
            "frame_compressed_bytes": self.compressed_bytes,
            "compression_ratio": (self.raw_bytes/max(1, self.compressed_bytes)),
        })
        encoded = json.dumps(self.metadata, indent=2, sort_keys=True).encode("utf-8")
        self.archive.writestr("metadata.json", encoded,
                              compress_type=zipfile.ZIP_DEFLATED,
                              compresslevel=self.compression)
        self.archive.comment = b"Voyager Grand Tour terminal recording VGR v1"
        self.archive.close()
        self.archive = None
        os.replace(self.partial, self.path)
        return self.path.stat().st_size

    def abort(self):
        if self.archive is not None:
            self.archive.close()
            self.archive = None
        if self.partial.exists():
            self.partial.unlink()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.archive is not None:
            if exc_type is None:
                raise RuntimeError("VGRWriter.finish() was not called")
            self.abort()


class VGRReader:
    def __init__(self, path):
        self.path = Path(path)
        self.archive = zipfile.ZipFile(self.path, "r")
        try:
            self.metadata = json.loads(self.archive.read("metadata.json"))
            self._validate_metadata()
        except Exception:
            self.archive.close()
            raise

    def _validate_metadata(self):
        if self.metadata.get("schema") != SCHEMA:
            raise ValueError("not a Voyager Grand Tour recording")
        if self.metadata.get("format_version") != FORMAT_VERSION:
            raise ValueError("unsupported VGR format version")
        expected = self.metadata["capture"]["frame_count"]
        frames = self.metadata.get("frames", ())
        if len(frames) != expected:
            raise ValueError("VGR frame index is incomplete")

    def read_frame(self, index):
        record = self.metadata["frames"][index]
        payload = self.archive.read(record["member"])
        frame = decode_frame_packet(payload)
        if frame[0] != index:
            raise ValueError("VGR frame index mismatch")
        return frame

    def load_all(self):
        return [self.read_frame(index) for index in range(len(self.metadata["frames"]))]

    def test_crc(self):
        bad = self.archive.testzip()
        if bad is not None:
            raise ValueError(f"VGR CRC failure: {bad}")

    def close(self):
        self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


@dataclass
class CaptureMetrics:
    frame_index: int
    frame_count: int
    animation_time: float
    duration: float
    target_fps: float
    render_seconds: float
    real_elapsed: float
    real_remaining: float
    raw_bytes: int
    compressed_bytes: int
    archive_bytes: int
    p0_cells: int
    p1_cells: int
    encounter: str
    frame_raw_bytes: int
    frame_compressed_bytes: int
    frame_write_seconds: float
    scene_seconds: float
    encode_seconds: float
    packet_seconds: float
    total_cells: int
    occupied_cells: int
    blank_cells: int
    unique_masks: int
    unique_nonzero_masks: int
    p0_frame_cells: int
    p1_frame_cells: int
    p0_unique_masks: int
    p1_unique_masks: int
    visible_faces: int
    visible_edges: int
    masks: np.ndarray
    colors: np.ndarray


class CaptureDashboard:
    """Cinematic terminal dashboard; it never displays the captured animation."""

    def __init__(self, enabled=True, refresh_hz=4.0):
        self.enabled = enabled and sys.stdout.isatty()
        self.refresh_interval = 1.0/max(.2, refresh_hz)
        self.last_update = 0.0
        self.started = False
        self.render_history = []
        self.rate_history = []
        self.data_rate_history = []
        self.storage_history = []
        self.scene_history = []
        self.encode_history = []
        self.packet_history = []
        self.write_latency_history = []
        self.write_rate_history = []
        self.read_rate_history = []
        self.occupancy_history = []
        self.unique_ratio_history = []
        self.compression_history = []

    def __enter__(self):
        if self.enabled:
            self.started = True
            sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
            sys.stdout.flush()
        return self

    def __exit__(self, *unused):
        if self.started:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    @staticmethod
    def _metric(label, value, width):
        available = max(1, width-len(label)-1)
        return f"{label} {value:>{available}}"[:width].ljust(width)

    @staticmethod
    def _activity(masks, mode, count=16):
        values = masks.ravel()
        nonzero = values[values != 0]
        if len(nonzero) == 0:
            return " "*count
        positions = np.linspace(0, len(nonzero)-1, count).astype(int)
        sample = nonzero[positions]
        if mode == 2:
            return "".join(chr(0x2800+int(mask)) for mask in sample)
        return "".join(chr(pua4_codepoint(int(mask))) for mask in sample)

    @staticmethod
    def _sparkline(values, width):
        if not values:
            return " "*width
        values = list(values[-width:])
        low, high = min(values), max(values)
        span = max(high-low, 1e-12)
        levels = "▁▂▃▄▅▆▇█"
        result = "".join(levels[min(7, int((value-low)/span*7))]
                         for value in values)
        return result.rjust(width)

    @staticmethod
    def _percent(numerator, denominator):
        return 100.0*float(numerator)/max(1, int(denominator))

    @staticmethod
    def _bar(fraction, width):
        fraction = min(1.0, max(0.0, float(fraction)))
        filled = min(width, int(round(fraction*width)))
        return "█"*filled+"░"*(width-filled)

    @staticmethod
    def _label_value(canvas, x0, x1, y, label, value,
                     label_color=CYAN, value_color=WHITE):
        canvas.text(x0, y, label, label_color, max(0, x1-x0+1))
        start = max(x0+len(label)+1, x1-len(str(value))+1)
        canvas.text(start, y, value, value_color, max(0, x1-start+1))

    @staticmethod
    def _preview(canvas, x0, y0, x1, y1, metrics, mode):
        source_rows, source_columns = metrics.masks.shape
        available_width = max(1, x1-x0+1)
        available_height = max(1, y1-y0+1)
        scale = min(available_width/source_columns,
                    available_height/source_rows, 1.0)
        output_columns = max(1, int(source_columns*scale))
        output_rows = max(1, int(source_rows*scale))
        left = x0+(available_width-output_columns)//2
        top = y0+(available_height-output_rows)//2
        for target_y in range(output_rows):
            source_y = min(source_rows-1,
                           int((target_y+.5)*source_rows/output_rows))
            for target_x in range(output_columns):
                source_x = min(source_columns-1,
                               int((target_x+.5)*source_columns/output_columns))
                mask = int(metrics.masks[source_y, source_x])
                if not mask:
                    continue
                character = (chr(0x2800+mask) if mode == 2 else
                             chr(pua4_codepoint(mask)))
                color = tuple(int(channel) for channel in
                              metrics.colors[source_y, source_x])
                canvas.put(left+target_x, top+target_y, character, color)

    def render(self, metadata, metrics, force=False, complete=False):
        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now-self.last_update < self.refresh_interval:
            return
        self.last_update = now
        capture_rate = (metrics.frame_index+1)/max(metrics.real_elapsed, 1e-9)
        data_rate = metrics.compressed_bytes/max(metrics.real_elapsed, 1e-9)
        write_rate = (metrics.frame_compressed_bytes /
                      max(metrics.frame_write_seconds, 1e-9))
        occupancy = self._percent(metrics.occupied_cells, metrics.total_cells)
        unique_ratio = self._percent(metrics.unique_nonzero_masks,
                                     metrics.occupied_cells)
        compression = (metrics.frame_raw_bytes /
                       max(1, metrics.frame_compressed_bytes))
        self.render_history.append(metrics.render_seconds*1000)
        self.rate_history.append(capture_rate)
        self.data_rate_history.append(data_rate)
        self.storage_history.append(metrics.archive_bytes)
        self.scene_history.append(metrics.scene_seconds*1000)
        self.encode_history.append(metrics.encode_seconds*1000)
        self.packet_history.append(metrics.packet_seconds*1000)
        self.write_latency_history.append(metrics.frame_write_seconds*1000)
        self.write_rate_history.append(write_rate)
        self.read_rate_history.append(0.0)
        self.occupancy_history.append(occupancy)
        self.unique_ratio_history.append(unique_ratio)
        self.compression_history.append(compression)
        for history in (self.render_history, self.rate_history,
                        self.data_rate_history, self.storage_history,
                        self.scene_history, self.encode_history,
                        self.packet_history, self.write_latency_history,
                        self.write_rate_history, self.read_rate_history,
                        self.occupancy_history, self.unique_ratio_history,
                        self.compression_history):
            del history[:-72]
        terminal_size = os.get_terminal_size()
        if terminal_size.columns >= 132 and terminal_size.lines >= 50:
            return self._render_cinematic(metadata, metrics, complete,
                                          terminal_size)
        return self._render_compact(metadata, metrics, complete)

    def _render_cinematic(self, metadata, metrics, complete, terminal_size):
        width = min(220, terminal_size.columns)
        height = min(50, terminal_size.lines)
        canvas = HudCanvas(width, height)
        render = metadata["render"]
        terminal = metadata["terminal"]
        progress = (metrics.frame_index+1)/metrics.frame_count
        ratio = metrics.raw_bytes/max(1, metrics.compressed_bytes)
        capture_rate = (metrics.frame_index+1)/max(metrics.real_elapsed, 1e-9)
        data_rate = metrics.compressed_bytes/max(metrics.real_elapsed, 1e-9)
        frame_ratio = metrics.frame_raw_bytes/max(1, metrics.frame_compressed_bytes)
        active_percent = self._percent(metrics.occupied_cells,
                                       metrics.total_cells)
        blank_percent = self._percent(metrics.blank_cells, metrics.total_cells)
        p0_unique_percent = self._percent(metrics.p0_unique_masks,
                                          metrics.p0_frame_cells)
        p1_unique_percent = self._percent(metrics.p1_unique_masks,
                                          metrics.p1_frame_cells)
        nonzero_unique_percent = self._percent(metrics.unique_nonzero_masks,
                                               metrics.occupied_cells)
        write_rate = (metrics.frame_compressed_bytes /
                      max(metrics.frame_write_seconds, 1e-9))
        mask_width = 1 if render["mode"] == 2 else 2
        mask_plane_bytes = metrics.total_cells*mask_width
        color_plane_bytes = metrics.total_cells*3

        # Architectural frame: header, three instrument bays, data pipeline,
        # and mission timeline mirror the approved cinematic concept.
        canvas.box(0, 0, width-1, 2, CYAN_DIM)
        title = "VOYAGER GRAND TOUR — OFFLINE CAPTURE"
        canvas.text((width-len(title))//2, 1, title, CYAN)
        left_end = 43
        right_start = width-51
        main_top, main_bottom = 3, 28
        canvas.box(0, main_top, left_end, main_bottom, CYAN_DIM,
                   "CAPTURE CONFIGURATION")
        canvas.box(left_end+1, main_top, right_start-1, main_bottom,
                   CYAN_DIM, "LIVE FRAME / VIRTUAL APERTURE")
        canvas.box(right_start, main_top, width-1, main_bottom,
                   CYAN_DIM, "LIVE PERFORMANCE")

        # Left configuration and bit-addressing bay.
        config = (
            ("MODE", f"PUA {render['mode']}×4"),
            ("RESOLUTION", f"{terminal['virtual_width']}×{terminal['virtual_height']} PX"),
            ("DURATION", f"{metrics.duration:0.3f} S"),
            ("TARGET", f"{metrics.target_fps:0.2f} FPS"),
            ("CAMERA", render["camera"].upper()),
            ("STYLE", render["style"].upper()),
            ("ENCODE", "P0 + P1" if render["mode"] == 4 else "U+2800 BRAILLE"),
        )
        for offset, (label, value) in enumerate(config):
            self._label_value(canvas, 2, left_end-2, 5+offset*2,
                              label, value, CYAN, WHITE)
        canvas.box(2, 19, left_end-2, 25, DARK, "4×4 CELL / MASK PREVIEW")
        sample = int(metrics.masks.ravel()[np.argmax(metrics.masks.ravel())])
        sample_codepoint = (0x2800+sample if render["mode"] == 2 else
                            pua4_codepoint(sample))
        sample_part = ("BRAILLE" if render["mode"] == 2 else
                       ("P0" if sample < 0x8000 else "P1"))
        summary = (f"MASK {sample:04X}  {sample_part} U+{sample_codepoint:05X}  "
                   "MSB-LEFT")
        canvas.text(4, 20, summary, AMBER, left_end-6)
        for local_y in range(4):
            row_bits = []
            for local_x in range(4):
                bit = 4*local_y+(3-local_x)
                row_bits.append("■" if sample & (1 << bit) else "·")
            canvas.text(5, 21+local_y, " ".join(row_bits),
                        AMBER if any(char == "■" for char in row_bits) else CYAN_DIM)
            position = (" TOP" if local_y == 0 else
                        (" BOTTOM" if local_y == 3 else ""))
            canvas.text(16, 21+local_y,
                        f"BITS {local_y*4+3:02d}..{local_y*4:02d}{position}",
                        CYAN_DIM, left_end-18)
        canvas.text(2, 27, "STATUS", CYAN)
        canvas.text(10, 27, "● COMPLETE" if complete else "● RECORDING",
                    GREEN if complete else ORANGE)

        # Central targeting aperture, coordinate grid, and live PUA preview.
        centre_left, centre_right = left_end+2, right_start-2
        centre_x = (centre_left+centre_right)//2
        centre_y = 16
        radius_x = max(12, min(42, (centre_right-centre_left)//2-2))
        radius_y = 11
        canvas.ellipse(centre_x, centre_y, radius_x, radius_y, GRID, 240)
        canvas.ellipse(centre_x, centre_y, max(8, radius_x-3),
                       max(5, radius_y-1), DARK, 180)
        canvas.hline(centre_x-radius_x+2, centre_x+radius_x-2,
                     centre_y, "·", DARK)
        canvas.vline(centre_x, centre_y-radius_y+1,
                     centre_y+radius_y-1, "·", DARK)
        for division in (-2, -1, 1, 2):
            grid_x = centre_x+division*radius_x//3
            canvas.vline(grid_x, 7, 24, "·", GRID)
        for division in (-1, 1):
            grid_y = centre_y+division*5
            canvas.hline(centre_x-radius_x+4, centre_x+radius_x-4,
                         grid_y, "·", GRID)
        self._preview(canvas, centre_left+2, 6, centre_right-2, 25,
                      metrics, render["mode"])
        gauge_width = max(12, min(34, centre_right-centre_left-8))
        completed_width = int(progress*gauge_width)
        gauge = "█"*completed_width+"░"*(gauge_width-completed_width)
        gauge_x = centre_x-gauge_width//2
        canvas.text(gauge_x, 26, gauge, AMBER)
        percent = f"TOTAL {progress*100:5.1f}%"
        canvas.text(centre_x-len(percent)//2, 27, percent,
                    GREEN if complete else CYAN)

        # Right telemetry bay with animated instrumentation traces.
        metrics_rows = (
            ("FRAME", f"{metrics.frame_index+1:06d} / {metrics.frame_count:06d}", AMBER),
            ("RENDER ELAPSED", format_seconds(metrics.animation_time), CYAN),
            ("FRAME TIME", f"{metrics.render_seconds*1000:7.1f} MS", CYAN),
            ("REAL ELAPSED", format_seconds(metrics.real_elapsed), CYAN),
            ("REAL REMAINING", format_seconds(metrics.real_remaining), AMBER),
            ("CAPTURE RATE", f"{capture_rate:7.2f} FPS", CYAN),
            ("BYTES / FRAME", format_bytes(metrics.frame_raw_bytes), WHITE),
            ("CAPTURE DATA", format_bytes(metrics.archive_bytes), CYAN),
            ("COMPRESSION", f"{ratio:0.2f}:1", CYAN),
        )
        for offset, (label, value, value_color) in enumerate(metrics_rows):
            y = 5+offset*2
            self._label_value(canvas, right_start+2, width-3, y,
                              label, value, CYAN, value_color)
        graph_width = min(31, width-right_start-6)
        self._label_value(canvas, right_start+2, width-3, 23,
                          "FRAME RATE", f"{capture_rate:.2f} FPS", CYAN_DIM, CYAN)
        canvas.text(width-3-graph_width, 24,
                    self._sparkline(self.rate_history, graph_width), CYAN)
        self._label_value(canvas, right_start+2, width-3, 25,
                          "DATA RATE", f"{format_bytes(data_rate)}/S", CYAN_DIM, ORANGE)
        canvas.text(width-3-graph_width, 26,
                    self._sparkline(self.data_rate_history, graph_width), ORANGE)
        p0_total = metrics.p0_cells
        p1_total = metrics.p1_cells
        p1_share = p1_total/max(1, p0_total+p1_total)
        p1_bar = int(p1_share*24)
        canvas.text(right_start+2, 27, "P0/P1 ", CYAN)
        canvas.text(right_start+8, 27, "█"*(24-p1_bar), BLUE)
        canvas.text(right_start+8+24-p1_bar, 27, "█"*p1_bar, ORANGE)
        canvas.text(right_start+33, 27,
                    f"{metrics.p0_frame_cells}/{metrics.p1_frame_cells}", WHITE,
                    max(0, width-right_start-35))

        # Frame-processing pipeline.  Every column now reports a real stage:
        # scene rasterisation, mask encoding, in-memory VGF packet assembly,
        # ZIP-member compression/write, and cumulative archive storage.
        pipe_top, pipe_bottom = 29, 40
        canvas.box(0, pipe_top, width-1, pipe_bottom, CYAN_DIM,
                   "FRAME PROCESSING PIPELINE")
        usable = width-4
        segment = usable//5
        labels = ("FRAME RENDER", f"{render['mode']}×4 PUA ENCODE",
                  "FRAME BUFFER / PACKET", "ARCHIVE I/O", "FRAME STORAGE")
        details = (
            (metrics.encounter,
             f"FACES {metrics.visible_faces:,}  EDGES {metrics.visible_edges:,}",
             f"SCENE {metrics.scene_seconds*1000:.1f} MS",
             f"ENCODE {metrics.encode_seconds*1000:.1f} MS",
             f"TOTAL {metrics.render_seconds*1000:.1f} MS",
             "RENDER HISTORY"),
            (f"CELLS {metrics.total_cells:,}",
             f"ACTIVE {metrics.occupied_cells:,}  {active_percent:.1f}%",
             f"BLANK {metrics.blank_cells:,}  {blank_percent:.1f}%",
             f"MASKS {metrics.unique_masks:,} / PUA {metrics.unique_nonzero_masks:,}",
             f"UNIQUE/ACTIVE {nonzero_unique_percent:.1f}%",
             f"P0 C/U {metrics.p0_frame_cells:,}/{metrics.p0_unique_masks:,}  U/C {p0_unique_percent:.1f}%",
             f"P1 C/U {metrics.p1_frame_cells:,}/{metrics.p1_unique_masks:,}  U/C {p1_unique_percent:.1f}%"),
            (f"MASK PLANE {format_bytes(mask_plane_bytes)}",
             f"RGB PLANE {format_bytes(color_plane_bytes)}",
             f"VGF HEADER {FRAME_HEADER.size} B",
             f"RAW PACKET {format_bytes(metrics.frame_raw_bytes)}",
             f"DEFLATE {format_bytes(metrics.frame_compressed_bytes)}",
             f"RATIO {frame_ratio:.2f}:1",
             f"PACKET BUILD {metrics.packet_seconds*1000:.2f} MS"),
            (f"WRITE {format_bytes(metrics.frame_compressed_bytes)}",
             f"I/O {metrics.frame_write_seconds*1000:.1f} MS",
             f"WRITE RATE {format_bytes(write_rate)}/S",
             "READ 0 B/S",
             "READ IDLE DURING CAPTURE",
             "WRITE / READ HISTORY"),
            (f"ARCHIVE {format_bytes(metrics.archive_bytes)}",
             f"FRAME {metrics.frame_index+1:,}/{metrics.frame_count:,}",
             f"MEMBER {metrics.frame_index:08d}.VGF",
             "INDEXED + CRC32",
             f"GROWTH {format_bytes(data_rate)}/S",
             f"FRAMES DATA {format_bytes(metrics.compressed_bytes)}",
             "ARCHIVE GROWTH"),
        )
        for index, (label, rows) in enumerate(zip(labels, details)):
            x0 = 2+index*segment
            x1 = width-3 if index == 4 else x0+segment-2
            if index:
                canvas.text(x0-2, 35, "▶", CYAN)
            canvas.text(x0, 31, label, CYAN_DIM, x1-x0+1)
            for row_offset, value in enumerate(rows):
                canvas.text(x0, 32+row_offset, value,
                            AMBER if index in (3, 4) and row_offset == 0 else
                            (WHITE if row_offset in (2, 4) else CYAN), x1-x0+1)

            graph_width = max(5, x1-x0-4)
            if index == 0:
                canvas.text(x0, 39, "R ", CYAN_DIM)
                canvas.text(x0+2, 39,
                            self._sparkline(self.render_history, graph_width), CYAN)
            elif index == 1:
                canvas.text(x0, 39, "O ", CYAN_DIM)
                canvas.text(x0+2, 39,
                            self._sparkline(self.occupancy_history, graph_width), GREEN)
            elif index == 2:
                canvas.text(x0, 39, "C ", CYAN_DIM)
                canvas.text(x0+2, 39,
                            self._sparkline(self.compression_history, graph_width), BLUE)
            elif index == 3:
                canvas.text(x0, 38, "W ", CYAN_DIM)
                canvas.text(x0+2, 38,
                            self._sparkline(self.write_rate_history, graph_width), ORANGE)
                canvas.text(x0, 39, "R ", CYAN_DIM)
                canvas.text(x0+2, 39,
                            self._sparkline(self.read_rate_history, graph_width), BLUE)
            else:
                canvas.text(x0, 39, "S ", CYAN_DIM)
                canvas.text(x0+2, 39,
                            self._sparkline(self.storage_history, graph_width), CYAN)

        # Mission encounter timeline and completion rail.
        timeline_top = 41
        canvas.box(0, timeline_top, width-1, height-1, CYAN_DIM,
                   "GRAND TOUR TIMELINE / TOTAL CAPTURE PROGRESS")
        stages = ("JUPITER", "SATURN", "URANUS", "NEPTUNE", "INTERSTELLAR")
        stage_colors = (AMBER, AMBER, CYAN, BLUE, ORANGE)
        line_left, line_right = 4, width-5
        canvas.hline(line_left, line_right, timeline_top+4, "─", GRID)
        for index, (stage, stage_color) in enumerate(zip(stages, stage_colors)):
            x = line_left+round(index*(line_right-line_left)/(len(stages)-1))
            canvas.put(x, timeline_top+4, "●", stage_color)
            label_x = max(2, min(width-len(stage)-2, x-len(stage)//2))
            canvas.text(label_x, timeline_top+2, stage, stage_color)
        marker = line_left+round(progress*(line_right-line_left))
        canvas.put(marker, timeline_top+4, "◆", WHITE)
        bar_left, bar_right = 3, width-4
        bar_width = bar_right-bar_left+1
        filled = min(bar_width, round(progress*bar_width))
        canvas.text(bar_left, timeline_top+6, "█"*filled,
                    GREEN if complete else CYAN)
        canvas.text(bar_left+filled, timeline_top+6, "░"*(bar_width-filled), DARK)
        footer = (f"TOTAL CAPTURE {progress*100:05.1f}%   {metrics.encounter}   "
                  f"OUTPUT {Path(metadata['capture']['output']).name}")
        canvas.text(max(2, (width-len(footer))//2), timeline_top+7,
                    footer, WHITE, width-4)

        sys.stdout.write("\x1b[H"+canvas.render()+"\x1b[J")
        sys.stdout.flush()

    def _render_compact(self, metadata, metrics, complete=False):
        width = max(78, min(156, os.get_terminal_size().columns))
        inner = width-2
        gap = " │ "
        left_width = (inner-len(gap))//2
        right_width = inner-len(gap)-left_width
        render = metadata["render"]
        terminal = metadata["terminal"]
        ratio = metrics.raw_bytes/max(1, metrics.compressed_bytes)
        capture_rate = (metrics.frame_index+1)/max(metrics.real_elapsed, 1e-9)
        progress = (metrics.frame_index+1)/metrics.frame_count
        bar_width = max(20, inner-24)
        completed_width = min(bar_width, int(round(progress*bar_width)))
        progress_bar = "█"*completed_width+"░"*(bar_width-completed_width)
        packets = min(28, max(1, int(progress*28)))
        packet_flow = "▰"*packets+"·"*(28-packets)+"  ═══▶  [ VGR ARCHIVE ]"
        activity = self._activity(metrics.masks, render["mode"])

        def border(left, fill, right):
            return paint(left+fill*inner+right, CYAN_DIM)

        def row(left, right):
            left = left[:left_width].ljust(left_width)
            right = right[:right_width].ljust(right_width)
            return (paint("║", CYAN_DIM)+paint(left, WHITE)+paint(gap, CYAN_DIM)+
                    paint(right, WHITE)+paint("║", CYAN_DIM))

        lines = [
            border("╔", "═", "╗"),
            paint("║", CYAN_DIM)+paint(" VOYAGER GRAND TOUR — OFFLINE CAPTURE ".center(inner), CYAN, True)+paint("║", CYAN_DIM),
            border("╠", "═", "╣"),
            row("CAPTURE CONFIGURATION", "LIVE PERFORMANCE"),
            row(self._metric("MODE", f"PUA {render['mode']}×4", left_width),
                self._metric("FRAME", f"{metrics.frame_index+1:06d} / {metrics.frame_count:06d}", right_width)),
            row(self._metric("RESOLUTION", f"{terminal['virtual_width']} × {terminal['virtual_height']} px", left_width),
                self._metric("RENDER ELAPSED", format_seconds(metrics.animation_time), right_width)),
            row(self._metric("DURATION", f"{metrics.duration:.3f} s", left_width),
                self._metric("FRAME TIME", f"{metrics.render_seconds*1000:.1f} ms", right_width)),
            row(self._metric("TARGET", f"{metrics.target_fps:.2f} FPS", left_width),
                self._metric("REAL ELAPSED", format_seconds(metrics.real_elapsed), right_width)),
            row(self._metric("CAMERA", render["camera"].upper(), left_width),
                self._metric("REAL REMAINING", format_seconds(metrics.real_remaining), right_width)),
            row(self._metric("STYLE", render["style"].upper(), left_width),
                self._metric("CAPTURE RATE", f"{capture_rate:.2f} FPS", right_width)),
            border("╠", "═", "╣"),
            row("PUA CELL ACTIVITY / FRAME FLOW", "ENCODE + STORAGE"),
            row(f"{activity}  {packet_flow}"[:left_width],
                self._metric("RAW FRAMES", format_bytes(metrics.raw_bytes), right_width)),
            row(self._metric("P0 / P1 CELLS", f"{metrics.p0_cells:,} / {metrics.p1_cells:,}", left_width),
                self._metric("COMPRESSED", format_bytes(metrics.compressed_bytes), right_width)),
            row(self._metric("ENCOUNTER", metrics.encounter, left_width),
                self._metric("COMPRESSION", f"{ratio:.2f}:1", right_width)),
            row(self._metric("OUTPUT", Path(metadata["capture"]["output"]).name, left_width),
                self._metric("ARCHIVE NOW", format_bytes(metrics.archive_bytes), right_width)),
            border("╠", "═", "╣"),
            paint("║", CYAN_DIM)+paint(" GRAND TOUR TIMELINE  ", AMBER, True)+paint(
                "JUPITER ━━━ SATURN ━━━ URANUS ━━━ NEPTUNE ━━━ INTERSTELLAR".ljust(inner-22)[:inner-22], WHITE)+paint("║", CYAN_DIM),
            paint("║", CYAN_DIM)+paint(f" {progress_bar}  {progress*100:6.2f}% ".ljust(inner)[:inner],
                                        AMBER if progress < .8 else ORANGE)+paint("║", CYAN_DIM),
            paint("║", CYAN_DIM)+paint(
                (" STATUS  COMPLETE" if complete else " STATUS  RECORDING").ljust(inner-28),
                GREEN, True)+paint(
                f"DATA {format_bytes(metrics.archive_bytes):>20} ", BLUE)+paint("║", CYAN_DIM),
            border("╚", "═", "╝"),
        ]
        sys.stdout.write("\x1b[H"+"\n".join(lines)+"\x1b[J")
        sys.stdout.flush()


class PlaybackKeyboard:
    def __init__(self):
        self.fd = None
        self.saved = None

    def __enter__(self):
        if sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def read(self):
        if self.fd is None:
            return ""
        ready, _, _ = select.select([self.fd], [], [], 0)
        return os.read(self.fd, 16).decode("utf-8", "ignore") if ready else ""

    def __exit__(self, *unused):
        if self.fd is not None and self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)


def playback_status(columns, metadata, index, fps, speed, paused):
    count = metadata["capture"]["frame_count"]
    animation_time = metadata["frames"][index]["animation_time"]
    state = "PAUSED" if paused else "PLAY"
    text = (f" VOYAGER VGR  {state}  frame {index+1:06d}/{count:06d}  "
            f"t={animation_time:07.3f}s  {fps:.2f} fps  speed={speed:.2f}×  "
            "Space pause  ←/→ step  +/- speed  r restart  q quit ")
    return "\x1b[0;30;46m"+text[:columns].ljust(columns)+"\x1b[0m"


def play_recording(path, expected_mode=None, fps_override=None, speed=1.0,
                   loop=False, stream=False, no_status=False,
                   allow_small_terminal=False, verify=True):
    if speed <= 0:
        raise ValueError("playback speed must be positive")
    with VGRReader(path) as reader:
        if verify:
            reader.test_crc()
        metadata = reader.metadata
        mode = metadata["render"]["mode"]
        if expected_mode is not None and expected_mode != mode:
            raise ValueError(f"recording requires -{mode}, not -{expected_mode}")
        columns = metadata["terminal"]["columns"]
        graphic_rows = metadata["terminal"]["graphic_rows"]
        required_rows = graphic_rows+(0 if no_status else 1)
        terminal = os.get_terminal_size() if sys.stdout.isatty() else None
        if terminal and not allow_small_terminal:
            if terminal.columns < columns or terminal.lines < required_rows:
                raise ValueError(
                    f"terminal is {terminal.columns}×{terminal.lines}; recording needs "
                    f"at least {columns}×{required_rows} (use --allow-small-terminal)")
        fps = float(fps_override or metadata["capture"]["fps"])
        if fps <= 0:
            raise ValueError("playback FPS must be positive")
        frames = None if stream else reader.load_all()
        frame_count = metadata["capture"]["frame_count"]
        index = 0
        paused = False
        quit_requested = False
        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H\x1b[?25l")
        sys.stdout.flush()
        try:
            with PlaybackKeyboard() as keyboard:
                deadline = time.monotonic()+1/(fps*speed)
                redraw = True
                while not quit_requested:
                    if redraw:
                        frame = reader.read_frame(index) if frames is None else frames[index]
                        _, _, _, masks, colors = frame
                        picture = terminal_picture(masks, colors, mode)
                        if no_status:
                            output = "\x1b[H"+picture
                        else:
                            output = ("\x1b[H"+playback_status(
                                columns, metadata, index, fps, speed, paused)+"\n"+picture)
                        sys.stdout.write(output)
                        sys.stdout.flush()
                        redraw = False
                    key = keyboard.read()
                    lower = key.lower()
                    if lower == "q" or key == "\x1b":
                        quit_requested = True
                        continue
                    if " " in key:
                        paused = not paused
                        deadline = time.monotonic()+1/(fps*speed)
                        redraw = True
                    if "r" in lower:
                        index = 0
                        deadline = time.monotonic()+1/(fps*speed)
                        redraw = True
                    if "+" in key or "=" in key:
                        speed = min(16.0, speed*1.25)
                        deadline = time.monotonic()+1/(fps*speed)
                        redraw = True
                    if "-" in key or "_" in key:
                        speed = max(.0625, speed/1.25)
                        deadline = time.monotonic()+1/(fps*speed)
                        redraw = True
                    if paused and "\x1b[D" in key:
                        index = max(0, index-1)
                        redraw = True
                    if paused and "\x1b[C" in key:
                        index = min(frame_count-1, index+1)
                        redraw = True
                    if paused:
                        time.sleep(.01)
                        continue
                    now = time.monotonic()
                    if now < deadline:
                        time.sleep(min(.01, deadline-now))
                        continue
                    index += 1
                    if index >= frame_count:
                        if loop:
                            index = 0
                        else:
                            break
                    deadline += 1/(fps*speed)
                    if deadline < now-1/(fps*speed):
                        deadline = now
                    redraw = True
        finally:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
    return metadata
