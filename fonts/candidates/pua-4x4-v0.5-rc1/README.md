# PUA 4x4 v0.5 RC1

This package contains Candidate 4, the first PUA 4x4 build to pass the
corrected Linux release gate without cross-cell outline overfill.

- `PUA4x4Part0V05Candidate4.ttf`: masks `0x0000..0x7FFF`, codepoints
  `U+0F0000..U+0F7FFF`.
- `PUA4x4Part1V05Candidate4.ttf`: masks `0x8000..0xFFFF`, codepoints
  `U+100000..U+107FFF`.

The mapping is `bit = 4 * local_y + (3 - local_x)`. Full occupancy remains
foreground mask `0xFFFF` at `U+107FFF`; the encoder does not substitute a
terminal background rectangle.

The fonts retain Candidate 1's exact cell-bounded geometry and add explicit
per-point TrueType grid fitting. See
`docs/PUA-4X4-CANDIDATE-4-EVIDENCE-v0.5.md` for the exhaustive and real-terminal
evidence.
