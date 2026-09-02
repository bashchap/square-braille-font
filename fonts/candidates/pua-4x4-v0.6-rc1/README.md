# PUA 4x4 v0.6 RC1

This package contains Candidate 6, derived reproducibly from the preserved
Candidate 4 binaries.

- `PUA4x4Part0V06Candidate6.ttf`: masks `0x0000..0x7FFF`, codepoints
  `U+0F0000..U+0F7FFF`.
- `PUA4x4Part1V06Candidate6.ttf`: masks `0x8000..0xFFFF`, codepoints
  `U+100000..U+107FFF`.

The mapping remains `bit = 4 * local_y + (3 - local_x)`. Full occupancy is
still foreground mask `0xFFFF` at `U+107FFF`; no terminal-background or
reverse-video substitution is used.

Candidate 6 preserves Candidate 4's strict horizontal ownership (`x=0..500`,
advance `500`) and internal 4x4 boundaries. Only the exterior vertical edges
are guarded: `y=-200` becomes `-300`, and `y=800` becomes `900`.

Supported Linux use is at normal and enlarged MATE Terminal sizes. The two
smallest Ctrl-minus zoom levels can still expose horizontal seams because of
terminal line-box rasterisation and are not part of this release candidate's
supported visual range.
