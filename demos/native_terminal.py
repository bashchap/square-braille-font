"""Optional shared Rust encoder for legacy terminal demo framebuffers.

The simulations remain ordinary Python.  This module moves the repeated mask,
colour, Unicode mapping and ANSI state machine into the dependency-free native
library, with a byte-equivalent Python fallback when it has not been built.
"""

from array import array
import ctypes
from pathlib import Path
import sys


MAPPINGS = {"square-alias": 0, "braille": 1, "pua4": 2}


def library_path():
    suffix = {"darwin": ".dylib", "win32": ".dll"}.get(sys.platform, ".so")
    prefix = "" if sys.platform == "win32" else "lib"
    return (Path(__file__).resolve().parents[1] / "native" /
            "seasonal_encoder" / "target" / "release" /
            f"{prefix}seasonal_encoder{suffix}")


def _character(mask, mapping):
    if mapping == "square-alias":
        return chr(0xE000 + mask)
    if mapping == "braille":
        return chr(0x2800 + mask)
    return chr(0xF0000 + mask if mask < 0x8000 else
               0x100000 + mask - 0x8000)


def _flatten(values):
    if hasattr(values, "reshape"):
        return values.reshape(-1)
    return (value for row in values for value in row)


def _packed_colours(values, colour_mode, expected=None):
    packed = array("I")
    if colour_mode == "none":
        # Monochrome callers historically supplied either scalar palette
        # indices or RGB tuples. Colour is semantically ignored in this mode,
        # so do not inspect or coerce the payload at all.
        if expected is None:
            expected = sum(1 for row in values for _ in row)
        packed.extend(0 for _ in range(expected))
        return packed
    source = (values.reshape(-1) if colour_mode == "indexed" and
              hasattr(values, "reshape") else
              values.reshape(-1, 3) if hasattr(values, "reshape") else
              (value for row in values for value in row))
    for value in source:
        if colour_mode == "indexed":
            packed.append(int(value))
        else:
            red, green, blue = (int(channel) for channel in value)
            packed.append((red << 16) | (green << 8) | blue)
    return packed


def python_terminal_picture(masks, colours, columns, rows, *, mapping,
                            colour_mode="rgb", blank_glyph=False,
                            carriage_return=False, reset_at_end=True):
    flat_masks = list(_flatten(masks))
    if colour_mode == "none":
        flat_colours = [0] * (columns * rows)
    else:
        flat_colours = list(
            colours.reshape(-1) if colour_mode == "indexed" and
            hasattr(colours, "reshape") else
            colours.reshape(-1, 3) if hasattr(colours, "reshape") else
            (value for row in colours for value in row))
    lines = []
    active = None
    for row in range(rows):
        pieces = []
        for column in range(columns):
            index = row * columns + column
            mask = int(flat_masks[index])
            value = flat_colours[index]
            colour = (int(value) if colour_mode in ("indexed", "none") else
                      tuple(int(channel) for channel in value))
            if mask and colour_mode != "none":
                if colour != active:
                    if colour_mode == "indexed":
                        pieces.append(f"\x1b[38;5;{colour}m")
                    else:
                        pieces.append("\x1b[38;2;%d;%d;%dm" % colour)
                    active = colour
            elif active is not None:
                pieces.append("\x1b[39m")
                active = None
            pieces.append(_character(mask, mapping)
                          if mask or blank_glyph else " ")
        lines.append("".join(pieces))
    text = ("\r\n" if carriage_return else "\n").join(lines)
    if reset_at_end and active is not None:
        text += "\x1b[39m"
    return text


class NativeTerminalEncoder:
    def __init__(self, path=None):
        self.path = Path(path) if path else library_path()
        self.library = ctypes.CDLL(str(self.path))
        self.function = self.library.encode_terminal_cells
        self.function.argtypes = [
            ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8,
            ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ]
        self.function.restype = ctypes.c_size_t
        self.function_v2 = self.library.encode_terminal_cells_v2
        self.function_v2.argtypes = [
            ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
        ]
        self.function_v2.restype = ctypes.c_size_t

    def encode(self, masks, colours, columns, rows, *, mapping,
               colour_mode="rgb", blank_glyph=False, carriage_return=False,
               reset_at_end=True):
        expected = columns * rows
        packed_masks = array("H", (int(value) for value in _flatten(masks)))
        packed_colours = _packed_colours(colours, colour_mode, expected)
        if len(packed_masks) != expected or len(packed_colours) != expected:
            raise ValueError("mask and colour buffers must match the cell grid")
        mask_buffer = (ctypes.c_uint16 * expected).from_buffer(packed_masks)
        colour_buffer = (ctypes.c_uint32 * expected).from_buffer(packed_colours)
        capacity = max(64, expected * 28 + rows * 2 + 16)
        while True:
            output = bytearray(capacity)
            output_buffer = (ctypes.c_uint8 * capacity).from_buffer(output)
            size = self.function(
                mask_buffer, colour_buffer, columns, rows, MAPPINGS[mapping],
                {"rgb": 0, "indexed": 1, "none": 2}[colour_mode],
                int(blank_glyph),
                int(carriage_return), int(reset_at_end), output_buffer,
                capacity)
            if not size:
                raise RuntimeError("native terminal encoder rejected the frame")
            if size <= capacity:
                return bytes(output[:size]).decode("utf-8")
            capacity = size

    def encode_v2(self, masks, foreground, background, flags, columns, rows,
                  *, mapping):
        expected = columns * rows
        packed_masks = array("H", (int(value) for value in _flatten(masks)))
        packed_foreground = _packed_colours(foreground, "rgb")
        packed_background = _packed_colours(background, "rgb")
        packed_flags = bytearray(int(value) for value in _flatten(flags))
        if not all(len(values) == expected for values in (
                packed_masks, packed_foreground, packed_background,
                packed_flags)):
            raise ValueError("two-colour buffers must match the cell grid")
        mask_buffer = (ctypes.c_uint16 * expected).from_buffer(packed_masks)
        foreground_buffer = (ctypes.c_uint32 * expected).from_buffer(
            packed_foreground)
        background_buffer = (ctypes.c_uint32 * expected).from_buffer(
            packed_background)
        flags_buffer = (ctypes.c_uint8 * expected).from_buffer(packed_flags)
        capacity = max(64, expected * 38 + rows * 5)
        while True:
            output = bytearray(capacity)
            output_buffer = (ctypes.c_uint8 * capacity).from_buffer(output)
            size = self.function_v2(
                mask_buffer, foreground_buffer, background_buffer,
                flags_buffer, columns, rows, MAPPINGS[mapping], output_buffer,
                capacity)
            if not size:
                raise RuntimeError("native two-colour encoder rejected the frame")
            if size <= capacity:
                return bytes(output[:size]).decode("utf-8")
            capacity = size


_ENCODER = None
_CHECKED = False


def load_native_terminal_encoder():
    global _ENCODER, _CHECKED
    if not _CHECKED:
        _CHECKED = True
        path = library_path()
        if path.exists():
            try:
                _ENCODER = NativeTerminalEncoder(path)
            except OSError:
                _ENCODER = None
    return _ENCODER


def terminal_picture(masks, colours, columns, rows, *, mapping,
                     colour_mode="rgb", blank_glyph=False,
                     carriage_return=False, reset_at_end=True):
    encoder = load_native_terminal_encoder()
    keyword = dict(mapping=mapping, colour_mode=colour_mode,
                   blank_glyph=blank_glyph,
                   carriage_return=carriage_return,
                   reset_at_end=reset_at_end)
    if encoder is not None:
        return encoder.encode(masks, colours, columns, rows, **keyword)
    return python_terminal_picture(
        masks, colours, columns, rows, **keyword)


def terminal_picture_v2(masks, foreground, background, flags, columns, rows,
                        *, mapping, fallback):
    """Use Rust for a two-colour framebuffer, or the supplied Python fallback."""
    encoder = load_native_terminal_encoder()
    if encoder is None:
        return fallback()
    return encoder.encode_v2(
        masks, foreground, background, flags, columns, rows, mapping=mapping)
