"""Optional ctypes bridge to the dependency-free Rust seasonal cell analyser."""

from array import array
import ctypes
from pathlib import Path
import sys


RECORD_SIZE = 10


def library_path():
    suffix = {"darwin": ".dylib", "win32": ".dll"}.get(sys.platform, ".so")
    prefix = "" if sys.platform == "win32" else "lib"
    return (Path(__file__).resolve().parents[2] / "native" / "seasonal_encoder" /
            "target" / "release" / f"{prefix}seasonal_encoder{suffix}")


class NativeAnalyser:
    def __init__(self, path=None):
        self.path = Path(path) if path else library_path()
        self.library = ctypes.CDLL(str(self.path))
        self.function = self.library.analyse_cells
        self.function.argtypes = [
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t,
            ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
        ]
        self.function.restype = ctypes.c_size_t

    def analyse(self, surface, codec, columns, rows):
        colours = array("I")
        priorities = bytearray(len(surface.pixels))
        append = colours.append
        for index, pixel in enumerate(surface.pixels):
            if pixel is None:
                append(0)
            else:
                colour, priority = pixel
                append((colour[0] << 16) | (colour[1] << 8) | colour[2])
                priorities[index] = priority
        bits = bytearray(bit for row in codec.bits for bit in row)
        output = bytearray(columns * rows * RECORD_SIZE)
        colour_buffer = (ctypes.c_uint32 * len(colours)).from_buffer(colours)
        priority_buffer = (ctypes.c_uint8 * len(priorities)).from_buffer(priorities)
        bit_buffer = (ctypes.c_uint8 * len(bits)).from_buffer(bits)
        output_buffer = (ctypes.c_uint8 * len(output)).from_buffer(output)
        count = self.function(
            colour_buffer, priority_buffer, surface.width, columns, rows,
            codec.cell_width, codec.cell_height, bit_buffer, output_buffer)
        if count != columns * rows:
            raise RuntimeError("native seasonal analyser rejected the frame")
        return output


def load_native_analyser(required=False):
    path = library_path()
    if not path.exists():
        if required:
            raise RuntimeError(
                f"native encoder is not built; run cargo build --release "
                f"--manifest-path {path.parents[2] / 'Cargo.toml'}")
        return None
    try:
        return NativeAnalyser(path)
    except OSError:
        if required:
            raise
        return None
