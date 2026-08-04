"""Shared 4x4 cell encoder used by the isolated PUA 4x4 demo suite."""

PART0_BASE = 0xF0000
PART1_BASE = 0x100000
PART1_MASK = 0x8000
FULL_MASK = 0xFFFF

# MSB-left row mapping: bit b = 4 * local_y + (3 - local_x).
DOT_BIT = (
    (3, 2, 1, 0),
    (7, 6, 5, 4),
    (11, 10, 9, 8),
    (15, 14, 13, 12),
)

DOT_WEIGHTS = (
    (0x0008, 0x0004, 0x0002, 0x0001),
    (0x0080, 0x0040, 0x0020, 0x0010),
    (0x0800, 0x0400, 0x0200, 0x0100),
    (0x8000, 0x4000, 0x2000, 0x1000),
)


def mask_to_codepoint(mask):
    """Map a complete 16-bit cell mask into Part 0 or Part 1."""
    if not 0 <= mask <= FULL_MASK:
        raise ValueError("PUA 4x4 mask must be in the range 0x0000..0xFFFF")
    if mask < PART1_MASK:
        return PART0_BASE + mask
    return PART1_BASE + (mask - PART1_MASK)


def mask_to_glyph(mask):
    """Return the one-character string representing *mask*."""
    return chr(mask_to_codepoint(mask))


def codepoint_to_mask(codepoint):
    """Reverse either font's codepoint into its 16-bit cell mask."""
    if PART0_BASE <= codepoint < PART0_BASE + PART1_MASK:
        return codepoint - PART0_BASE
    if PART1_BASE <= codepoint < PART1_BASE + PART1_MASK:
        return PART1_MASK + codepoint - PART1_BASE
    raise ValueError("codepoint is outside the PUA 4x4 Part 0/Part 1 ranges")
