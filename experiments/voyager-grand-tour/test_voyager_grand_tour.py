#!/usr/bin/env python3
"""Deterministic proofs for the dual-font Voyager Grand Tour renderer."""

from __future__ import annotations

import json
import io
import math
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from os import terminal_size
from pathlib import Path
from unittest.mock import patch

import numpy as np

import voyager_grand_tour as demo
from voyager_core import BRAILLE_BITS, PUA4_BITS, pua4_codepoint
from voyager_layers import (BACKGROUND_VALID, encode_layers, expand_frame,
                            render_layered_frame, terminal_picture_v2)
from voyager_recording import (CaptureDashboard, CaptureMetrics, VGRReader,
                               decode_frame_packet, encode_frame_packet,
                               play_recording)


HERE = Path(__file__).resolve().parent


class VoyagerGrandTourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh = demo.load_mesh(demo.DEFAULT_MESH)

    def test_nasa_cache_provenance_and_counts(self):
        metadata = json.loads((HERE / "assets/voyager-vtad-source.json").read_text())
        self.assertEqual(metadata["source_sha256"],
                         "5338241f2e89e9cfe3ebb82f519b4cad64c97e66883cccba6fdda98667aec731")
        self.assertEqual(len(self.mesh["vertices"]), metadata["cache_vertices"])
        self.assertEqual(len(self.mesh["faces"]), metadata["cache_triangles"])
        self.assertEqual(len(self.mesh["edges"]), metadata["cache_unique_edges"])
        self.assertEqual(tuple(self.mesh["faces"].shape), (20372, 3))

    def test_pua4_msb_left_one_bit_mapping_exhaustively(self):
        """Every local coordinate must produce bit 4*y + (3-x)."""
        for local_y in range(4):
            for local_x in range(4):
                rgb = np.zeros((4, 4, 3), dtype=np.uint8)
                rgb[local_y, local_x] = (255, 255, 255)
                masks, _ = demo.encode_frame(rgb, 4, 1, 1)
                expected_bit = 4*local_y + (3-local_x)
                self.assertEqual(int(PUA4_BITS[local_y, local_x]), expected_bit)
                self.assertEqual(int(masks[0, 0]), 1 << expected_bit,
                                 (local_x, local_y, expected_bit))

    def test_pua4_full_mask_and_unicode_split(self):
        rgb = np.full((4, 4, 3), 255, dtype=np.uint8)
        masks, _ = demo.encode_frame(rgb, 4, 1, 1)
        self.assertEqual(int(masks[0, 0]), 0xFFFF)
        self.assertEqual(pua4_codepoint(0x0000), 0xF0000)
        self.assertEqual(pua4_codepoint(0x7FFF), 0xF7FFF)
        self.assertEqual(pua4_codepoint(0x8000), 0x100000)
        self.assertEqual(pua4_codepoint(0xFFFF), 0x107FFF)

    def test_square_braille_one_bits_and_full_mask(self):
        expected = ((0, 3), (1, 4), (2, 5), (6, 7))
        self.assertEqual(BRAILLE_BITS.tolist(), [list(row) for row in expected])
        for local_y in range(4):
            for local_x in range(2):
                rgb = np.zeros((4, 2, 3), dtype=np.uint8)
                rgb[local_y, local_x] = (255, 255, 255)
                masks, _ = demo.encode_frame(rgb, 2, 1, 1)
                self.assertEqual(int(masks[0, 0]), 1 << expected[local_y][local_x])
        masks, _ = demo.encode_frame(np.full((4, 2, 3), 255, dtype=np.uint8), 2, 1, 1)
        self.assertEqual(int(masks[0, 0]), 0xFF)

    def test_projection_compensates_for_virtual_pixel_aspect(self):
        vertices = np.array(((0., 0., 0.), (.1, 0., 0.), (0., 0., .1)))
        eye = np.array((0., -2., 0.))
        target = np.zeros(3)
        p2, _ = demo.project_mesh(vertices, eye, target, 0, 2, 200, 120,
                                  "grand-tour", 1.0)
        p4, _ = demo.project_mesh(vertices, eye, target, 0, 4, 400, 120,
                                  "grand-tour", 1.0)
        # Mode 4 has twice the virtual X displacement but each virtual pixel is
        # half as wide physically.  Physical displacement is therefore equal.
        virtual_dx2 = abs(float(p2[1, 0]-p2[0, 0]))
        virtual_dx4 = abs(float(p4[1, 0]-p4[0, 0]))
        self.assertAlmostEqual(virtual_dx4, virtual_dx2*2, places=4)
        physical_dx2 = virtual_dx2*(2/2)
        physical_dx4 = virtual_dx4*(2/4)
        self.assertAlmostEqual(physical_dx2, physical_dx4, places=4)
        self.assertAlmostEqual(float(p2[2, 1]-p2[0, 1]),
                               float(p4[2, 1]-p4[0, 1]), places=4)

    def test_contour_camera_stays_outside_directional_mesh_envelope(self):
        vertices = self.mesh["vertices"]
        for elapsed in np.linspace(0, 48, 97, endpoint=False):
            eye, target, _, _ = demo.camera_at(float(elapsed), "contour", vertices)
            direction = demo.normalize(eye-target)
            support = float(np.max((vertices-target) @ direction))
            self.assertGreaterEqual(float(np.linalg.norm(eye-target))+1e-8,
                                    support+.075)

    def test_bezier_path_is_first_derivative_continuous(self):
        epsilon = 1e-5
        keys = demo.CONTOUR_EYES
        for boundary in range(len(keys)):
            centre = float(boundary)
            before = demo.periodic_bezier(keys, centre-epsilon, .82)
            at = demo.periodic_bezier(keys, centre, .82)
            after = demo.periodic_bezier(keys, centre+epsilon, .82)
            left_velocity = (at-before)/epsilon
            right_velocity = (after-at)/epsilon
            np.testing.assert_allclose(left_velocity, right_velocity,
                                       rtol=2e-4, atol=2e-4)

    def test_spacecraft_remains_in_every_grand_tour_frame(self):
        vertices = self.mesh["vertices"]
        for elapsed in range(60):
            eye, target, roll, zoom = demo.camera_at(elapsed, "grand-tour", vertices)
            projected, depth = demo.project_mesh(
                vertices, eye, target, roll, 4, 400, 120, "grand-tour", zoom,
                elapsed)
            visible = ((depth > .025) & (projected[:, 0] >= 0) &
                       (projected[:, 0] < 400) & (projected[:, 1] >= 0) &
                       (projected[:, 1] < 120))
            self.assertGreater(np.count_nonzero(visible), 10, elapsed)

    def test_grand_tour_is_a_pursuit_flyby_not_a_turntable(self):
        for segment in range(6):
            samples = [demo.grand_tour_shot(segment*10+offset)
                       for offset in (.2, 2.5, 5.0, 7.5, 9.8)]
            eyes = np.asarray([sample["eye"] for sample in samples])
            path_length = np.linalg.norm(np.diff(eyes, axis=0), axis=1).sum()
            ranges = np.asarray([
                np.linalg.norm(sample["eye"]-sample["target"])
                for sample in samples])
            ship_x = [sample["ship_centre"][0] for sample in samples]
            self.assertGreater(path_length, 2.0, segment)
            self.assertGreater(np.ptp(ranges), .55, segment)
            self.assertGreater(ship_x[-1]-ship_x[0], .30, segment)
            # Both tracked subjects retain an on-screen centre throughout.
            for sample in samples:
                self.assertTrue(.12 < sample["ship_centre"][0] < .68)
                self.assertTrue(.30 < sample["ship_centre"][1] < .70)
                self.assertTrue(.62 < sample["planet_centre"][0] < .87)
                self.assertTrue(.40 < sample["planet_centre"][1] < .62)

    def test_grand_tour_shot_motion_is_smooth_inside_each_cut(self):
        epsilon = 1e-3
        for segment in range(6):
            for local in (1.0, 3.0, 5.0, 7.0, 9.0):
                elapsed = segment*10+local
                before = demo.grand_tour_shot(elapsed-epsilon)["eye"]
                at = demo.grand_tour_shot(elapsed)["eye"]
                after = demo.grand_tour_shot(elapsed+epsilon)["eye"]
                left_velocity = (at-before)/epsilon
                right_velocity = (after-at)/epsilon
                np.testing.assert_allclose(left_velocity, right_velocity,
                                           rtol=2e-2, atol=2e-2)

    def test_giant_planet_flattening_constants(self):
        expected = {
            "JUPITER": 66854/71492,
            "SATURN": 54364/60268,
            "URANUS": 24973/25559,
            "NEPTUNE": 24341/24764,
        }
        for planet in (demo.JUPITER, demo.SATURN, demo.URANUS, demo.NEPTUNE):
            self.assertTrue(0 < planet.flattening_ratio <= 1)
            self.assertTrue(math.isclose(planet.flattening_ratio,
                                         expected[planet.name], rel_tol=1e-12))

    def test_render_smoke_for_both_fonts_and_depth_modes(self):
        cases = ((2, "wire", True), (2, "filled", True),
                 (4, "wire", True), (4, "wire", False),
                 (4, "filled", True))
        for mode, style, hlr in cases:
            with self.subTest(mode=mode, style=style, hlr=hlr):
                encounter, _, masks, colors, stats = demo.render_frame(
                    self.mesh, mode, 28, 9, 24.0, "grand-tour", style, hlr, 3)
                self.assertEqual(masks.shape, (9, 28))
                self.assertEqual(colors.shape, (9, 28, 3))
                self.assertTrue(np.any(masks))
                self.assertGreater(stats[0], 0)
                self.assertGreater(stats[1], 0)
                self.assertIs(encounter.planet, demo.SATURN)
                if mode == 4:
                    self.assertTrue(np.any(masks & 0xFF00),
                                    "4x4 render never exercised bits 8..15")
                picture = demo.terminal_picture(masks, colors, mode)
                self.assertEqual(picture.count("\n"), 8)

    def test_two_colour_cell_preserves_sparse_foreground_over_planet(self):
        """A spacecraft pixel must not recolour an entire filled planet cell."""
        planet = np.full((4, 4, 3), (24, 80, 176), dtype=np.uint8)
        spacecraft = np.zeros((4, 4, 3), dtype=np.uint8)
        spacecraft[1, 2] = (32, 232, 240)
        frame = encode_layers(((20, planet), (30, spacecraft)), 4, 1, 1)

        # MSB-left mapping: b = 4*y + (3-x), so local (2,1) is bit 5.
        self.assertEqual(int(frame.masks[0, 0]), 1 << 5)
        self.assertEqual(tuple(frame.foreground[0, 0]), (32, 232, 240))
        self.assertEqual(tuple(frame.background[0, 0]), (24, 80, 176))
        self.assertTrue(int(frame.flags[0, 0]) & int(BACKGROUND_VALID))

        reconstructed = expand_frame(frame, 4)
        expected = planet.copy()
        expected[1, 2] = spacecraft[1, 2]
        np.testing.assert_array_equal(reconstructed, expected)

        picture = terminal_picture_v2(frame, 4)
        self.assertIn("\x1b[38;2;32;232;240m", picture)
        self.assertIn("\x1b[48;2;24;80;176m", picture)
        self.assertIn(chr(pua4_codepoint(1 << 5)), picture)

    def test_layered_neptune_overlap_uses_background_cells(self):
        encounter, _, frame, stats, _ = render_layered_frame(
            demo, self.mesh, 4, 60, 18, 47.9, "grand-tour", "wire", True, 2)
        self.assertIs(encounter.planet, demo.NEPTUNE)
        self.assertTrue(np.any(frame.masks))
        self.assertTrue(np.any(frame.flags & BACKGROUND_VALID))
        dual = (frame.flags & BACKGROUND_VALID) != 0
        self.assertTrue(np.any(frame.foreground[dual] != frame.background[dual]))
        self.assertGreater(stats[0], 0)
        self.assertGreater(stats[1], 0)

    def test_live_status_identifies_two_colour_compositor(self):
        line = demo.status_line(
            160, 4, demo.ENCOUNTERS[3], "grand-tour", "wire", True,
            12.0, 47.9)
        self.assertIn("2CLR=ON", line)

    def test_vgr_packet_roundtrip_for_both_font_modes(self):
        for mode, dtype in ((2, np.uint8), (4, np.uint16)):
            with self.subTest(mode=mode):
                masks = np.arange(12, dtype=dtype).reshape(3, 4)
                if mode == 4:
                    masks[2, 3] = 0xF00F
                colors = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
                payload = encode_frame_packet(7, 1.75, masks, colors, mode)
                index, animation_time, decoded_mode, decoded_masks, decoded_colors = \
                    decode_frame_packet(payload)
                self.assertEqual(index, 7)
                self.assertEqual(animation_time, 1.75)
                self.assertEqual(decoded_mode, mode)
                np.testing.assert_array_equal(decoded_masks, masks)
                np.testing.assert_array_equal(decoded_colors, colors)

    def test_capture_preflight_rejects_window_manager_geometry_clamp(self):
        expected = {
            "VOYAGER_EXPECT_TERMINAL_COLUMNS": "360",
            "VOYAGER_EXPECT_TERMINAL_ROWS": "104",
            "VOYAGER_TERMINAL_ZOOM": "1.0",
        }
        with patch.dict(demo.os.environ, expected, clear=False):
            with self.assertRaisesRegex(SystemExit,
                                        "requested terminal 360x104.*211x50"):
                demo.validate_expected_terminal(terminal_size((211, 50)))
            demo.validate_expected_terminal(terminal_size((360, 104)))

    def test_cinematic_hud_is_full_width_and_mapping_labels_are_correct(self):
        masks = np.full((31, 100), 0x1248, dtype=np.uint16)
        colors = np.full((31, 100, 3), (68, 224, 255), dtype=np.uint8)
        metrics = CaptureMetrics(
            frame_index=41, frame_count=720, animation_time=3.416,
            duration=60, target_fps=12, render_seconds=.082,
            real_elapsed=4.2, real_remaining=68, raw_bytes=31000,
            compressed_bytes=13000, archive_bytes=15000, p0_cells=400,
            p1_cells=200, encounter="JUPITER APPROACH",
            frame_raw_bytes=15522, frame_compressed_bytes=3120,
            frame_write_seconds=.006, scene_seconds=.074,
            encode_seconds=.008, packet_seconds=.0012, total_cells=3100,
            occupied_cells=922, blank_cells=2178, unique_masks=115,
            unique_nonzero_masks=114, p0_frame_cells=610,
            p1_frame_cells=312, p0_unique_masks=73, p1_unique_masks=41,
            visible_faces=1840, visible_edges=2660, masks=masks,
            colors=colors)
        metadata = {
            "render": {"mode": 4, "camera": "grand-tour", "style": "wire"},
            "terminal": {"virtual_width": 400, "virtual_height": 124},
            "capture": {"output": "voyager-grand-tour.vgr"},
        }
        dashboard = CaptureDashboard(False)
        dashboard.render_history = [82, 80, 91]
        dashboard.rate_history = [3, 4, 3.5]
        dashboard.data_rate_history = [1000, 2000, 1500]
        dashboard.storage_history = [1, 2, 3]
        dashboard.occupancy_history = [20, 27, 29.7]
        dashboard.compression_history = [4, 4.5, 4.97]
        dashboard.write_rate_history = [400000, 500000, 520000]
        dashboard.read_rate_history = [0, 0, 0]
        output = io.StringIO()
        with redirect_stdout(output):
            dashboard._render_cinematic(
                metadata, metrics, False, terminal_size((220, 50)))
        plain = re.sub(r"\x1b\[[0-9;]*m", "", output.getvalue())
        plain = plain.removeprefix("\x1b[H").removesuffix("\x1b[J")
        lines = plain.splitlines()
        self.assertEqual(len(lines), 50)
        self.assertTrue(all(len(line) == 220 for line in lines))
        self.assertIn("BITS 03..00", plain)
        self.assertIn("BITS 15..12", plain)
        self.assertIn("MASK 1248  P0 U+F1248  MSB-LEFT", plain)
        self.assertIn("BITS 03..00 TOP", plain)
        self.assertIn("BITS 15..12 BOTTOM", plain)
        self.assertIn("FRAME PROCESSING PIPELINE", plain)
        self.assertIn("BYTES / FRAME", plain)
        self.assertIn("FRAME RATE", plain)
        self.assertIn("DATA RATE", plain)
        self.assertIn("ACTIVE 922  29.7%", plain)
        self.assertIn("BLANK 2,178  70.3%", plain)
        self.assertIn("MASKS 115 / PUA 114", plain)
        self.assertNotIn("GLYPHS", plain)
        self.assertIn("P0 C/U 610/73  U/C 12.0%", plain)
        self.assertIn("P1 C/U 312/41  U/C 13.1%", plain)
        self.assertIn("FRAME BUFFER / PACKET", plain)
        self.assertIn("MASK PLANE 6.1 KiB", plain)
        self.assertIn("RGB PLANE 9.1 KiB", plain)
        self.assertIn("VGF HEADER 22 B", plain)
        self.assertIn("READ IDLE DURING CAPTURE", plain)
        self.assertIn("WRITE / READ HISTORY", plain)
        self.assertIn("GRAND TOUR TIMELINE / TOTAL CAPTURE PROGRESS", plain)
        self.assertIn("TOTAL CAPTURE 005.8%", plain)

    def test_offline_capture_archive_and_player(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"smoke.vgr"
            with redirect_stdout(io.StringIO()):
                demo.main(["capture", "-4", "--duration", ".5", "--fps", "4",
                           "--columns", "20", "--rows", "8", "--depth-scale", "4",
                           "--quiet", "--output", str(output)])
            self.assertTrue(output.exists())
            with VGRReader(output) as reader:
                reader.test_crc()
                metadata = reader.metadata
                self.assertEqual(metadata["schema"],
                                 "org.square-braille.voyager-recording")
                self.assertEqual(metadata["format_version"], 1)
                self.assertEqual(metadata["render"]["mode"], 4)
                self.assertEqual(metadata["capture"]["frame_count"], 2)
                self.assertEqual(metadata["capture"]["fps"], 4)
                self.assertEqual([frame["animation_time"] for frame in metadata["frames"]],
                                 [0.0, .25])
                encoding = metadata["frames"][0]["encoding"]
                self.assertEqual(encoding["total_cells"], 140)
                self.assertEqual(encoding["occupied_cells"]+encoding["blank_cells"], 140)
                self.assertEqual(encoding["p0_cells"]+encoding["p1_cells"],
                                 encoding["occupied_cells"])
                self.assertGreater(encoding["unique_nonzero_masks"], 0)
                self.assertGreater(metadata["frames"][0]["packet_seconds"], 0)
                self.assertGreater(metadata["frames"][0]["scene_seconds"], 0)
                self.assertGreater(metadata["frames"][0]["encode_seconds"], 0)
                _, _, _, masks, colors = reader.read_frame(0)
                self.assertEqual(masks.shape, (7, 20))
                self.assertEqual(colors.shape, (7, 20, 3))
                self.assertTrue(np.any(masks & 0xFF00))
            playback = io.StringIO()
            with redirect_stdout(playback):
                play_recording(output, expected_mode=4, fps_override=100,
                               no_status=True, allow_small_terminal=True)
            self.assertIn("\x1b[?1049h", playback.getvalue())
            with self.assertRaises(ValueError):
                play_recording(output, expected_mode=2, fps_override=100,
                               no_status=True, allow_small_terminal=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
