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
        self._tree_cache = {}
        self.function = self.library.analyse_cells
        self.function.argtypes = [
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t,
            ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
        ]
        self.function.restype = ctypes.c_size_t
        surface_prefix = [
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.c_size_t,
        ]
        self._rectangle = self.library.surface_rectangle
        self._rectangle.argtypes = surface_prefix + [
            ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_uint32, ctypes.c_uint8,
        ]
        self._rectangle.restype = ctypes.c_size_t
        self._line = self.library.surface_line
        self._line.argtypes = surface_prefix + [
            ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_uint32, ctypes.c_uint8,
        ]
        self._line.restype = ctypes.c_size_t
        self._ellipse = self.library.surface_filled_ellipse
        self._ellipse.argtypes = surface_prefix + [
            ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_uint32, ctypes.c_uint8,
        ]
        self._ellipse.restype = ctypes.c_size_t
        self._polygon = self.library.surface_filled_polygon
        self._polygon.argtypes = surface_prefix + [
            ctypes.POINTER(ctypes.c_int32), ctypes.c_size_t,
            ctypes.c_uint32, ctypes.c_uint8,
        ]
        self._polygon.restype = ctypes.c_size_t
        self._thick_line = self.library.surface_thick_line
        self._thick_line.argtypes = surface_prefix + [
            ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint8,
        ]
        self._thick_line.restype = ctypes.c_size_t
        self._overlay = self.library.surface_overlay
        self._overlay.argtypes = [
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t, ctypes.c_uint8,
        ]
        self._overlay.restype = ctypes.c_size_t
        self._promote = self.library.surface_promote
        self._promote.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_uint8,
        ]
        self._promote.restype = ctypes.c_size_t
        self._accumulation = self.library.surface_draw_accumulation
        self._accumulation.argtypes = surface_prefix + [
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint8,
        ]
        self._accumulation.restype = ctypes.c_size_t
        self._tree = self.library.surface_draw_tree_points
        self._tree.argtypes = surface_prefix + [
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
            ctypes.c_int32, ctypes.c_int32, ctypes.c_double,
            ctypes.c_double, ctypes.c_uint8,
        ]
        self._tree.restype = ctypes.c_size_t
        self._top_edges = self.library.surface_top_edges
        self._top_edges.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_int32),
            ctypes.c_size_t,
        ]
        self._top_edges.restype = ctypes.c_size_t

    @staticmethod
    def _buffers(surface):
        colours = (ctypes.c_uint32 * len(surface.colours)).from_buffer(
            surface.colours)
        priorities = (ctypes.c_uint8 * len(surface.priorities)).from_buffer(
            surface.priorities)
        return colours, priorities

    @staticmethod
    def _colour(colour):
        return (colour[0] << 16) | (colour[1] << 8) | colour[2]

    def analyse(self, surface, codec, columns, rows):
        if hasattr(surface, "colours") and hasattr(surface, "priorities"):
            colours = surface.colours
            priorities = surface.priorities
        else:
            colours = array("I")
            priorities = bytearray(len(surface.pixels))
            append = colours.append
            for index, pixel in enumerate(surface.pixels):
                if pixel is None:
                    append(0)
                else:
                    colour, priority = pixel
                    append(self._colour(colour))
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

    def rectangle(self, surface, left, top, right, bottom, colour, priority):
        buffers = self._buffers(surface)
        return self._rectangle(*buffers, surface.width, surface.height,
                               left, top, right, bottom,
                               self._colour(colour), priority)

    def line(self, surface, x0, y0, x1, y1, colour, priority):
        buffers = self._buffers(surface)
        return self._line(*buffers, surface.width, surface.height,
                          x0, y0, x1, y1, self._colour(colour), priority)

    def filled_ellipse(self, surface, centre_x, centre_y, radius_x, radius_y,
                       colour, priority):
        buffers = self._buffers(surface)
        return self._ellipse(*buffers, surface.width, surface.height,
                             centre_x, centre_y, radius_x, radius_y,
                             self._colour(colour), priority)

    def filled_polygon(self, surface, points, colour, priority):
        coordinates = array("i", (coordinate for point in points
                                   for coordinate in point))
        coordinate_buffer = (ctypes.c_int32 * len(coordinates)).from_buffer(
            coordinates)
        buffers = self._buffers(surface)
        return self._polygon(*buffers, surface.width, surface.height,
                             coordinate_buffer, len(points),
                             self._colour(colour), priority)

    def thick_line(self, surface, x0, y0, x1, y1, radius, colour, priority):
        buffers = self._buffers(surface)
        return self._thick_line(*buffers, surface.width, surface.height,
                                x0, y0, x1, y1, radius,
                                self._colour(colour), priority)

    def overlay(self, destination, source, minimum_priority=0):
        if (destination.width != source.width or
                destination.height != source.height):
            raise ValueError("native surface overlay dimensions differ")
        destination_buffers = self._buffers(destination)
        source_buffers = self._buffers(source)
        return self._overlay(*destination_buffers, *source_buffers,
                             len(destination.colours), minimum_priority)

    def promote(self, surface, priority):
        _, priorities = self._buffers(surface)
        return self._promote(priorities, len(surface.priorities), priority)

    def draw_accumulation(self, surface, depths, bank, priority):
        if len(depths) != surface.width:
            raise ValueError("native accumulation depth width differs")
        depth_buffer = (ctypes.c_int32 * len(depths)).from_buffer(depths)
        packed_bank = array("I", (self._colour(colour) for colour in bank))
        bank_buffer = (ctypes.c_uint32 * len(packed_bank)).from_buffer(
            packed_bank)
        buffers = self._buffers(surface)
        return self._accumulation(*buffers, surface.width, surface.height,
                                  depth_buffer, bank_buffer, priority)

    def _packed_tree(self, pixels):
        key = id(pixels)
        cached = self._tree_cache.get(key)
        if cached is not None and cached[0] is pixels:
            return cached[1:]
        if len(self._tree_cache) >= 512:
            self._tree_cache.clear()
        offsets = array("i")
        colours = array("I")
        priorities = bytearray()
        for dx, dy, colour, priority in pixels:
            offsets.extend((dx, dy))
            colours.append(self._colour(colour))
            priorities.append(priority)
        packed = (offsets, colours, priorities)
        self._tree_cache[key] = (pixels, *packed)
        return packed

    def draw_tree_points(self, surface, pixels, centre, base, height, sway,
                         force=False):
        offsets, colours, priorities = self._packed_tree(pixels)
        if not priorities:
            return 0
        offset_buffer = (ctypes.c_int32 * len(offsets)).from_buffer(offsets)
        colour_buffer = (ctypes.c_uint32 * len(colours)).from_buffer(colours)
        priority_buffer = (ctypes.c_uint8 * len(priorities)).from_buffer(
            priorities)
        buffers = self._buffers(surface)
        return self._tree(*buffers, surface.width, surface.height,
                          offset_buffer, colour_buffer, priority_buffer,
                          len(priorities), int(centre), int(base), height, sway,
                          int(bool(force)))

    def top_edges(self, surface):
        _, priorities = self._buffers(surface)
        offsets = (ctypes.c_size_t * (surface.width + 1))()
        # Alternating occupied/empty single pixels is the maximum edge count.
        capacity = surface.width * ((surface.height + 1) // 2)
        values = (ctypes.c_int32 * max(1, capacity))()
        count = self._top_edges(priorities, surface.width, surface.height,
                                offsets, values, len(values))
        if count == 0 and any(surface.priorities):
            raise RuntimeError("native top-edge scan rejected the surface")
        return [list(values[offsets[x]:offsets[x + 1]])
                for x in range(surface.width)]

    def column_bits(self, surface):
        columns = [0] * surface.width
        for index, priority in enumerate(surface.priorities):
            if priority:
                y, x = divmod(index, surface.width)
                columns[x] |= 1 << y
        return columns


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
