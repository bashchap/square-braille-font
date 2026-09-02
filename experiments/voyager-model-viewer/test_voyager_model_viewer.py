#!/usr/bin/env python3
"""Deterministic tests for the interactive PUA 4x4 Voyager model viewer."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import voyager_model_viewer as viewer
from voyager_recording import VGRReader


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh = viewer.load_mesh(viewer.DEFAULT_MESH)
        cls.radius = float(np.max(np.linalg.norm(cls.mesh["vertices"], axis=1)))

    def test_verified_nasa_cache_counts(self):
        self.assertEqual(self.mesh["vertices"].shape, (12456, 3))
        self.assertEqual(self.mesh["faces"].shape, (20372, 3))
        self.assertEqual(self.mesh["edges"].shape, (31637, 2))

    def test_rotation_matrix_is_orthonormal(self):
        matrix = viewer.rotation_matrix((.3, -.7, 1.2))
        np.testing.assert_allclose(matrix @ matrix.T, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(float(np.linalg.det(matrix)), 1.0, places=12)

    def test_xterm_arrow_modifier_decoder(self):
        self.assertEqual(viewer.decode_arrow("\x1b[A")["direction"], "up")
        shifted = viewer.decode_arrow("\x1b[1;2D")
        self.assertTrue(shifted["shift"])
        self.assertFalse(shifted["alt"])
        alternate = viewer.decode_arrow("\x1b[1;3C")
        self.assertTrue(alternate["alt"])
        controlled = viewer.decode_arrow("\x1b[1;5A")
        self.assertTrue(controlled["ctrl"])
        combined = viewer.decode_arrow("\x1b[1;4D")
        self.assertTrue(combined["shift"] and combined["alt"])

    def test_camera_navigation_modes(self):
        state = viewer.ViewerState()
        eye = state.eye.copy()
        target = state.target.copy()
        state.handle_key("\x1b[D", self.radius)
        self.assertFalse(np.allclose(state.eye, eye))
        state.eye[:] = eye
        state.target[:] = target
        state.handle_key("\x1b[1;2C", self.radius)
        np.testing.assert_allclose(state.eye-eye, state.target-target)
        before = state.camera_distance()
        state.handle_key("+", self.radius)
        self.assertLess(state.camera_distance(), before)

    def test_ctrl_is_reserved_and_plain_keys_handle_dolly_and_roll(self):
        state = viewer.ViewerState()
        eye = state.eye.copy()
        target = state.target.copy()
        state.handle_key("\x1b[1;5A", self.radius)
        np.testing.assert_allclose(state.eye, eye)
        np.testing.assert_allclose(state.target, target)
        self.assertIn("RESERVED", state.message)
        initial_roll = state.roll
        state.handle_key("]", self.radius)
        self.assertGreater(state.roll, initial_roll)

    def test_panel_toggles_and_centre_zoom(self):
        state = viewer.ViewerState()
        state.handle_key("1", self.radius)
        state.handle_key("2", self.radius)
        self.assertFalse(state.show_camera_panel)
        self.assertFalse(state.show_model_panel)
        before = state.camera_distance()
        state.handle_key("z", self.radius)
        np.testing.assert_allclose(state.target, state.model_position)
        self.assertAlmostEqual(state.camera_distance(), self.radius*1.38,
                               places=10)
        self.assertLess(state.camera_distance(), before)

    def test_hiding_panels_returns_their_width_to_viewport(self):
        state = viewer.ViewerState()
        dimensions = []

        def fake_scene(mesh, state, mode, width, height, depth_scale, radius):
            dimensions.append((width, height))
            return np.zeros((height, width, 3), dtype=np.uint8), 0, 0

        with patch.object(viewer, "render_scene", side_effect=fake_scene):
            viewer.render_gui(self.mesh, state, 160, 50, 4, self.radius)
            state.show_camera_panel = False
            viewer.render_gui(self.mesh, state, 160, 50, 4, self.radius)
            state.show_model_panel = False
            viewer.render_gui(self.mesh, state, 160, 50, 4, self.radius)
        self.assertLess(dimensions[0][0], dimensions[1][0])
        self.assertLess(dimensions[1][0], dimensions[2][0])

    def test_record_hotkey_requests_external_recording_toggle(self):
        state = viewer.ViewerState(rotating=True)
        self.assertTrue(state.handle_key("c", self.radius))
        self.assertTrue(state.record_toggle_requested)
        self.assertTrue(state.rotating)

    def test_clean_recording_uses_full_screen_and_contains_no_gui(self):
        state = viewer.ViewerState(grid_mode=3)
        columns, rows = 48, 18
        scene, faces, edges = viewer.render_scene(
            self.mesh, state, 4, columns*4, rows*4, 4, self.radius,
            draw_axes=False)
        masks, colors = viewer.encode_frame(scene, 4, columns, rows)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"clean-view.vgr"
            recorder = viewer.ViewportRecorder(
                output, columns, rows, 12.0, state, 4, self.mesh)
            recorder.add(masks, colors, .01, faces, edges)
            path, _, _ = recorder.finish()
            with VGRReader(path) as reader:
                metadata = reader.metadata
                self.assertTrue(metadata["capture"]["full_terminal_framebuffer"])
                self.assertEqual(metadata["terminal"]["status_rows"], 0)
                self.assertEqual(metadata["terminal"]["graphic_rows"], rows)
                self.assertEqual(metadata["render"]["content"],
                                 "model_and_grid_only")
                self.assertFalse(metadata["render"]["hud"])
                self.assertFalse(metadata["render"]["panels"])
                self.assertFalse(metadata["render"]["borders"])
                self.assertFalse(metadata["render"]["model_axes"])
                _, _, mode, stored_masks, stored_colors = reader.read_frame(0)
                self.assertEqual(mode, 4)
                self.assertEqual(stored_masks.shape, (rows, columns))
                self.assertEqual(stored_colors.shape, (rows, columns, 3))

    def test_clean_capture_excludes_orientation_axes(self):
        state = viewer.ViewerState(grid_mode=0)
        with_axes, _, _ = viewer.render_scene(
            self.mesh, state, 4, 320, 120, 4, self.radius,
            draw_axes=True)
        clean, _, _ = viewer.render_scene(
            self.mesh, state, 4, 320, 120, 4, self.radius,
            draw_axes=False)
        self.assertGreater(np.count_nonzero(with_axes),
                           np.count_nonzero(clean))

    def test_independent_three_axis_rotation_loop(self):
        state = viewer.ViewerState()
        original_rates = state.angular_velocity.copy()
        state.handle_key("\x1b[1;3A", self.radius)  # Alt-Up: X rate
        state.handle_key("\x1b[1;3C", self.radius)  # Alt-Right: Y rate
        state.handle_key("\x1b[1;4C", self.radius)  # Alt-Shift-Right: Z rate
        self.assertTrue(np.all(state.angular_velocity > original_rates))
        original_angles = state.model_angles.copy()
        state.handle_key(" ", self.radius)
        state.step_rotation(.25)
        self.assertTrue(np.all(state.model_angles != original_angles))
        self.assertTrue(state.rotating)
        state.handle_key("\x1b[D", self.radius)
        self.assertFalse(state.rotating)

    def test_page_switch_and_rendered_page_difference(self):
        state = viewer.ViewerState()
        page1, _, full = viewer.render_gui(
            self.mesh, state, 80, 24, 4, self.radius)
        self.assertFalse(full)
        state.handle_key("\t", self.radius)
        page2, _, _ = viewer.render_gui(
            self.mesh, state, 80, 24, 4, self.radius)
        self.assertEqual(state.page, 1)
        self.assertFalse(np.array_equal(page1, page2))
        state.handle_key("\t", self.radius)
        page3, _, _ = viewer.render_gui(
            self.mesh, state, 80, 24, 4, self.radius)
        self.assertEqual(state.page, 2)
        self.assertFalse(np.array_equal(page2, page3))

    def test_resize_rebuilds_framebuffer_geometry(self):
        state = viewer.ViewerState()
        small_masks, small_colors, compact = viewer.render_gui(
            self.mesh, state, 80, 24, 4, self.radius)
        large_masks, large_colors, full = viewer.render_gui(
            self.mesh, state, 160, 50, 4, self.radius)
        self.assertEqual(small_masks.shape, (24, 80))
        self.assertEqual(small_colors.shape, (24, 80, 3))
        self.assertEqual(large_masks.shape, (50, 160))
        self.assertEqual(large_colors.shape, (50, 160, 3))
        self.assertFalse(compact)
        self.assertTrue(full)
        self.assertGreater(np.count_nonzero(small_masks), 0)
        self.assertGreater(np.count_nonzero(large_masks), 0)

    def test_minimum_supported_terminal_geometry(self):
        masks, colors, full = viewer.render_gui(
            self.mesh, viewer.ViewerState(), 40, 16, 4, self.radius)
        self.assertEqual(masks.shape, (16, 40))
        self.assertEqual(colors.shape, (16, 40, 3))
        self.assertFalse(full)

    def test_projection_preserves_physical_aspect(self):
        state = viewer.ViewerState(eye=np.array((0., -2., 0.)),
                                   target=np.zeros(3))
        points = np.array(((0., 0., 0.), (.1, 0., 0.), (0., 0., .1)))
        projected, _ = viewer.project_points(points, state.eye, state.target,
                                             0, 4, 400, 120)
        x_pixels = abs(float(projected[1, 0]-projected[0, 0]))
        y_pixels = abs(float(projected[2, 1]-projected[0, 1]))
        self.assertAlmostEqual(x_pixels/2, y_pixels, places=4)


if __name__ == "__main__":
    unittest.main()
