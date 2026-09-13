# PUA 4×4 font-generation evidence — v0.4 candidates

Status: **candidate.3 passes the approved mapping and the tested seamless-rendering gates.** It remains side-by-side with v0.3; no existing font was overwritten.

Generated 13-page PDF SHA-256:
`3bb31af46307cce86c2d359a82a6d0e2ab7acc16c815fa3609d1dd734f780289`.

This report begins only after approval of the independent mathematical oracle in `PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf`. Every result below distinguishes stored font data from effective TrueType placement, isolated rasterization, installed Linux selection and a real MATE Terminal capture.

## 1. Fixed mathematical oracle

Virtual coordinates increase left-to-right and top-to-bottom. A virtual pixel `(vx, vy)` maps to:

```text
terminal_cell_x = vx // 4
terminal_cell_y = vy // 4
local_x         = vx % 4
local_y         = vy % 4
bit             = 4 * local_y + (3 - local_x)
bit_value       = 1 << bit
```

The approved cell is:

```text
 3  2  1  0
 7  6  5  4
11 10  9  8
15 14 13 12
```

The 16-bit mask, written most-significant bit first, is `fedcba9876543210`. Codepoints are:

```text
mask 0000..7FFF: codepoint = U+F0000  + mask
mask 8000..FFFF: codepoint = U+100000 + (mask - 0x8000)
```

This oracle is not changed by any v0.4 candidate.

## 2. Evidence gates

| Gate | Required evidence | Outcome |
|---|---|---|
| A — mathematics | All 65,536 masks round-trip through coordinate, bit, mask, part and codepoint formulae | PASS; separately approved |
| B — stored font | cmap, raw outlines, decoded masks, advance widths and bearings match an independent oracle | PASS for candidate.1; 65,536/65,536 |
| C — integer-grid raster | FreeType at 40 and 80 ppem matches expected black/white pixels | PASS; 62 cases, zero mismatches and zero partial pixels |
| D — Linux selection | Installed bytes match build; `wcwidth=1`; Fontconfig and Pango select text, P0 and P1 with no unknown glyphs | PASS |
| E — fractional point raster | A full-mask field is solid at 8–20 pt, 96 DPI | FAIL candidate.1 and candidate.2; PASS candidate.3 |
| F — real terminal | Same 14 pt triangle has no under-covered full-cell boundary pixels | FAIL candidate.1: 5,632; PASS candidate.3: 0 |
| G — reproducibility | Independent Linux rebuild equals the macOS-generated binaries byte-for-byte | PASS candidate.3 |

## 3. Reproduced v0.3 placement defect

The v0.3 raw outlines and cmap encode the approved mask correctly. The failure occurs later, in TrueType horizontal placement.

For a glyph whose stored bounding box begins at `xMin`, TrueType effective placement is:

```text
effective_x = raw_x - (xMin - leftSideBearing)
effective_xMin = leftSideBearing
```

v0.3 assigns `leftSideBearing = 0` to every pattern. Therefore any nonempty glyph whose first selected pixel is not in the leftmost column has `xMin > 0` but renders with `effective_xMin = 0`. Exactly **4,095** Part 0 masks meet this condition. Part 1 always contains bit 15, which is in the leftmost column, so its `xMin` is already zero.

One-bit proof:

| mask | required local x | raw xMin | v0.3 LSB | v0.3 effective xMin | result |
|---:|---:|---:|---:|---:|---|
| `0008` | 0 | 0 | 0 | 0 | correct |
| `0004` | 1 | 125 | 0 | 0 | shifted left |
| `0002` | 2 | 250 | 0 | 0 | shifted left |
| `0001` | 3 | 375 | 0 | 0 | shifted left |

This explains the observed detached marks and horizontal “jumping.” The earlier verifier checked raw components but did not calculate effective placement using `hmtx`; that omission is now a regression test.

## 4. Candidate.1 — exact core geometry and corrected bearings

Candidate.1 is generated independently and installed under distinct family/file names. It does not replace v0.3.

Construction:

- one 500×1000 font-unit terminal cell;
- four columns of 125 units and four rows of 250 units;
- direct simple contours representing the selected-cell union;
- shared internal edges removed;
- no composite pattern glyphs;
- `leftSideBearing = xMin` for each nonempty pattern, preserving its raw x coordinate;
- zero exterior overfill.

Exhaustive stored-font outcome:

- 65,536 cmap entries checked;
- 65,536 unique pattern glyphs checked;
- zero mask-decode mismatches;
- zero outline-edge mismatches;
- zero horizontal-metric mismatches;
- zero effective-placement mismatches.

At 40 and 80 integer ppem, FreeType produces the expected pixels exactly. Installed Pango also places the four one-bit masks at the four distinct local x positions. Thus candidate.1 fixes the v0.3 mapping-to-placement failure.

## 5. Candidate.1 fractional-rendering difference

The exact vector geometry does not guarantee a solid terminal raster when the requested point size becomes a fractional pixel em. The reproducing condition is:

```text
terminal: MATE Terminal
profile font: PUA 4x4 v0.4 Candidate 14 pt
display: 96 DPI
terminal grid: 211 columns × 50 rows
measured cell: 9 × 19 device pixels
glyph vector cell: 500 × 1000 units at 1000 units/em
```

At 14 pt and 96 DPI, the nominal em is 18.666… device pixels, while the terminal row is 19 pixels. The isolated point-unit Pango field reproduces partially covered edge pixels even though the integer-pixel test passes.

In the paired terminal triangle capture, 640 full-mask cells were analyzed. Candidate.1 produced:

- 33,280 measured cell-boundary pixels;
- **5,632 boundary pixels below 90% of their expected ANSI-colour coverage**;
- 16.923% boundary low-coverage rate;
- 0.217% interior low-coverage rate.

The strong concentration at terminal-cell boundaries proves the visible grid is a fractional raster-edge effect, not a mask or codepoint error.

## 6. Candidate.2 — embedded grid instructions

Candidate.2 keeps candidate.1’s 65,536 cmap mappings, raw outlines and `hmtx` metrics byte-for-byte at the table-data level, while adding native TrueType point-grid instructions, integer-ppem metadata and a `gasp` gridfit policy.

Expected: device-grid execution should remove fractional outer-edge coverage without changing mathematical geometry.

Observed at 8–20 pt and 96 DPI: the nonwhite seam counts are unchanged from candidate.1:

```text
8: 8800   9: 45280   10: 80000   11: 22920   12: 61440
13: 105600   14: 29480   16: 85680   18: 93760   20: 22880
```

Candidate.2 therefore fails Gate E in the tested Pango/FreeType configuration and is not the selected solution. This negative outcome is retained with the exact font hashes and raster report.

## 7. Measured seam-guard threshold

Ten controlled probe fonts changed only the full-mask glyph and its matching bearing. Each was measured at 8, 9, 10, 11, 12, 13, 14, 16, 18 and 20 pt at 96 DPI.

| exterior guard (font units) | all ten sizes completely white? |
|---:|:---:|
| 0 | no |
| 8 | no |
| 16 | no |
| 24 | no |
| 32 | no |
| 40 | no |
| 48 | no |
| 64 | no |
| 80 | no |
| **100** | **yes** |

At 14 pt specifically, 40 units was sufficient, but 100 units was the first tested value to pass the complete 8–20 pt matrix. This is the same guard magnitude independently reached by the current seamless Square Braille font.

## 8. Candidate.3 — exact core plus declared seam guard

Candidate.3 is derived from candidate.1 by one explicit coordinate transform:

```text
x =   0 -> -100       x = 500 -> 600
y = -200 -> -300      y = 800 -> 900
all other outline coordinates are unchanged
leftSideBearing becomes the transformed xMin
```

Consequences:

- the mapping formula and both PUA codepoint ranges are unchanged;
- all 65,536 cmap entries are unchanged;
- all internal 4×4 boundaries remain at x = 125, 250, 375 and y = 50, 300, 550;
- only selected outline segments on the four terminal-cell exterior edges acquire a 100-unit raster guard;
- the guard is deliberate and exactly enumerable, not an unexplained difference.

The independent derivation verifier compared every candidate.3 contour point with the transformed candidate.1 oracle. It found zero unexpected coordinate changes and zero formula/cmap changes.

## 9. Candidate.3 observed result and declared cost

Point-unit Pango result: every full-mask field at 8–20 pt and 96 DPI contains zero black and zero nonwhite seam pixels.

Real MATE Terminal result under the same 211×50, 9×19-pixel-cell, 14 pt condition:

- candidate.1: 5,632 low-coverage boundary pixels;
- candidate.3: **0** low-coverage boundary pixels;
- candidate.3 interior: **0** low-coverage pixels.

The triangle’s previously detached left-edge marks are absent and the interior mass is visually seamless.

The cost is measured explicitly. At a 40-pixel em, an isolated middle-cell one-bit probe shows:

```text
candidate.1  masks 0008,0004,0002,0001: [19,26] [24,31] [29,36] [34,41]
candidate.3  masks 0008,0004,0002,0001: [15,26] [24,31] [29,36] [34,44]
```

The two interior one-bit positions are unchanged. The left-edge bit extends four pixels into the preceding cell and the right-edge bit extends three measured pixels past the core edge (the theoretical 100-unit guard is four pixels at this em; antialias boundaries determine the measured run). This overhang is the deliberate price of universal 8–20 pt seam coverage in this raster stack.

## 10. Cross-environment reproducibility

Candidate.3 was generated on macOS, then independently regenerated from the byte-identical candidate.1 source on Linux using Python 3.12.3 and FontTools 4.46.0. Both binaries compare byte-for-byte:

```text
PUA4x4Part0V04Candidate3.ttf
SHA-256 94847138178994d016d3a0e315be0aa10604c1ea85e01b6d98eb8f41421ac9d8

PUA4x4Part1V04Candidate3.ttf
SHA-256 a979a9568dbe5c0b90bb54eb6bc0e4a70caf536bd4c2e791d589796a984f0ec1
```

The checked-in RC1 package was then copied to the Linux project and installed
with `PUA4X4_RC1_PACKAGE_DIR` pointing to that package rather than to a build
tree. The installed hashes remained identical. The runtime verifier also
reported one-column `wcwidth` throughout both PUA ranges, correct Fontconfig
selection for P0/P1, and Pango shaping of ordinary text plus both graphics
parts with zero unknown glyphs. The exact result is retained in
`pua4x4-v0.4-rc1-packaged-linux-runtime.json`.

The unversioned launcher and `demos4x4/run-demo.sh` now select the v0.4 RC1
profile by default. Linux readback proved the configured font was
`PUA 4x4 v0.4 Candidate 3 12`; installed P0/P1 hashes and Fontconfig selections
matched the checked-in package. No demo mask, Boolean-operation or codepoint
formula changed. `PUA4X4_USE_V03=1` remains an explicit route to the preserved
v0.3 launcher. The machine-readable result is
`pua4x4-v0.4-demo-launcher-profile.json`.

## 11. Recorded procedural difference

The first candidate.3 terminal launch created the profile but MATE retained `visible-name='Default'`; `mate-terminal` therefore reported `No such profile "(null)", using default profile`. That window is excluded from the result. The profile name was read back, corrected to `PUA 4x4 v0.4 Candidate 3`, and the retry verified both the profile name and `font='PUA 4x4 v0.4 Candidate 3 14'` before capture. Both launch logs are retained.

This is a profile-registration failure, not a font or raster result.

## 12. Reproduce

From the repository root:

```sh
cd experiments/pua-4x4

# Approved mathematics
python3 verify_mathematical_mapping.py

# Exact-core candidate and exhaustive stored-font verification
python3 generate_pua4x4_v04_candidate.py
python3 verify_pua4x4_v04_candidate.py
python3 audit_horizontal_placement.py
python3 verify_candidate_freetype_raster.py

# Rejected native-hint diagnostic
python3 make_v04_candidate2_hinted.py
python3 verify_v04_candidate2_derivation.py

# Seam-guard threshold and selected candidate
python3 make_fullmask_overfill_probes.py
python3 make_v04_candidate3_seamguard.py
python3 verify_v04_candidate3_derivation.py

# Linux installation remains side-by-side with v0.3
./install-linux-v04-candidate3.sh
./launch-linux-v04-candidate3.sh triangle
```

The current v0.3 files, aliases and historical candidates remain preserved. Candidate.3 is the recommended v0.4 release candidate for visual acceptance; it has not silently replaced the current alias.

## 13. Primary evidence files

- `output/audit/pua4x4-horizontal-placement-root-cause.json`
- `output/audit/pua4x4-v0.4-candidate-font-audit.json`
- `output/audit/pua4x4-v0.4-candidate-freetype-raster.json`
- `output/audit/pua4x4-v0.4-candidate-pango-raster.json`
- `output/audit/pua4x4-v0.4-candidate2-final-diagnostic-pango-raster.json`
- `output/audit/fullmask-overfill-probes/measurements.json`
- `output/audit/pua4x4-v0.4-candidate.3-derivation.json`
- `output/audit/pua4x4-v0.4-candidate3-pango-raster.json`
- `output/audit/pua4x4-v0.4-terminal-triangle-comparison.json`
- `output/audit/pua4x4-v0.4-candidate3-onebit-overhang.json`
- `output/audit/pua4x4-v0.4-rc1-packaged-linux-runtime.json`
- `output/audit/pua4x4-v0.4-rc1-packaged-pango-layout.json`
- `output/audit/pua4x4-v0.4-demo-launcher-profile.json`
- `output/audit/cross-environment/candidate3-linux-hashes.txt`
- `output/audit/terminal-v0.4-candidate3/`
