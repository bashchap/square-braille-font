"""Authoritative mathematical mapping for the experimental PUA 4x4 fonts."""

PART_PATTERN_COUNT = 0x8000
TOTAL_PATTERN_COUNT = 0x10000

PARTS = (
    {
        "part": 0,
        "family": "PUA 4x4 Part 0",
        "postscript": "PUA4x4Part0-Regular",
        "mask_start": 0x0000,
        "codepoint_start": 0xF0000,
    },
    {
        "part": 1,
        "family": "PUA 4x4 Part 1",
        "postscript": "PUA4x4Part1-Regular",
        "mask_start": 0x8000,
        "codepoint_start": 0x100000,
    },
)


def part_for_mask(mask):
    """Return the part specification for a 16-bit MSB-left row mask."""
    if not 0 <= mask < TOTAL_PATTERN_COUNT:
        raise ValueError("PUA 4x4 mask must be in the range 0x0000..0xFFFF")
    return PARTS[mask >> 15]


def mask_to_codepoint(mask):
    """Map a 16-bit mask to its supplementary-PUA codepoint."""
    spec = part_for_mask(mask)
    return spec["codepoint_start"] + (mask - spec["mask_start"])


def codepoint_to_mask(codepoint):
    """Reverse a PUA 4x4 codepoint into its 16-bit mask."""
    for spec in PARTS:
        offset = codepoint - spec["codepoint_start"]
        if 0 <= offset < PART_PATTERN_COUNT:
            return spec["mask_start"] + offset
    raise ValueError("codepoint is outside the two PUA 4x4 ranges")


def bit_for_cell(row, column):
    """Return the MSB-left bit number for a zero-based 4x4 cell."""
    if not (0 <= row < 4 and 0 <= column < 4):
        raise ValueError("row and column must both be in the range 0..3")
    return row * 4 + (3 - column)
