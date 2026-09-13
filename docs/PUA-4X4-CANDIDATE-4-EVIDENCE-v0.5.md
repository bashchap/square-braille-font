# PUA 4x4 Candidate 4 evidence — v0.5

> **Superseded 2026-08-15:** subsequent testing with 20 stacked full-mask
> terminal rows proved that the earlier bounding-box audit excluded the black
> line-box rows that appear *between separate terminal lines*. Candidate 4 is
> structurally and mathematically correct, but its real MATE Terminal output
> has horizontal seams. It is preserved for reproduction and is no longer the
> default. Candidate 6 adds a vertical-only guard; see
> [Candidate 6 evidence](PUA-4X4-CANDIDATE-6-EVIDENCE-v0.6.md).

## Decision

**Historical decision, now superseded:** Candidate 4 was initially judged to
pass the corrected Linux release gate. It preserves the
mathematical mapping, confines raster ownership to the emitting terminal cell,
and forms continuous foreground-only fields at every tested internal cell
join. Candidate 1, Candidate 3 and Candidate 4 remain preserved side by side.

This decision does not use terminal background colour as a substitute for a
full glyph. A completely occupied cell is still the Part 1 foreground glyph
`U+107FFF`.

No reverse-video SGR operation is involved. Foreground glyph selection remains
the same operation for empty, partial and fully occupied cells.

## Non-negotiable encoding invariant

A cell is always encoded from its 16 virtual foreground pixels. Representation
does not change merely because all bits happen to be set.

| Virtual occupancy | Mask | Codepoint | Colour role |
|---|---:|---:|---|
| no pixels | `0x0000` | `U+0F0000` | no foreground coverage |
| any partial pattern | that exact 16-bit mask | P0/P1 formula | foreground |
| all 16 pixels | `0xFFFF` | `U+107FFF` | foreground |

The terminal background may represent a genuine farther colour layer in the
two-colour compositor. It must not replace `0xFFFF` as a seam workaround.

This rule is now asserted by tests in both encoders:

- `FontPlotter/tests/test_fontplotter.py` checks that a single-colour 4x4 cell
  remains mask `0xFFFF`, foreground colour, with no background flag.
- `FontPlotter/tests/test_framebuffer_service.py` checks that the service emits
  mask `0xFFFF`, codepoint `U+107FFF`, foreground RGBA, with no background flag.

## Mapping proof retained

For local virtual-pixel coordinates `local_x, local_y` in the range 0 through
3, the approved MSB-left mapping remains:

```text
bit = 4 * local_y + (3 - local_x)
```

The mask is the bitwise OR of every occupied pixel's bit value. The codepoint
is then:

```text
mask < 0x8000:  U+0F0000 + mask
mask >= 0x8000: U+100000 + (mask - 0x8000)
```

Candidate 4's exhaustive stored-font audit checked all 65,536 masks and found
no mapping, outline-boundary or horizontal-metric disagreement with Candidate
1's exact-core geometry.

## What Candidate 4 changed

Candidate 4 starts with Candidate 1's cell-bounded outlines:

```text
advance width: 500 font units
x cell:          0 .. 500
y cell:       -200 .. 800
external overfill: 0
```

It adds explicit TrueType grid-fitting instructions to each non-empty glyph.
It does not alter the raw outline coordinates, advance widths or Unicode cmap.

## Measured Linux outcome

The corrected report is:

`experiments/pua-4x4/output/audit/pua4x4-v0.5-candidate4-release-linux.json`

The release gates report:

| Gate | Outcome |
|---|---|
| mapping and stored structure | PASS |
| strict cell geometry | PASS |
| sparse foreground cell ownership, antialias off | PASS, 140/140 |
| full `0xFFFF` foreground continuity at internal joins | PASS, 20/20 |
| release gate | **PASS** |

The full-mask test covers horizontal and vertical adjacency at pixel sizes 8,
9, 10, 11, 12, 13, 14, 16, 18 and 20. Every internal join passed.

### Audit correction: exterior line-box padding is not a cell seam

The first Candidate 4 report incorrectly counted every black pixel anywhere in
the complete `pango-view` PNG. At 16 of 20 size/direction combinations, Pango's
rounded output surface contained one black row *outside* the coloured ink
bounding box. For example:

| Size | Direction | PNG | Coloured bounding box | Internal black | Exterior black |
|---:|---|---:|---:|---:|---:|
| 8 px | horizontal | 8 x 9 | `[0,1,8,9]` | 0 | 8 |
| 8 px | vertical | 4 x 17 | `[0,1,4,17]` | 0 | 4 |
| 11 px | horizontal | 12 x 12 | `[0,0,12,11]` | 0 | 12 |
| 11 px | vertical | 6 x 23 | `[0,0,6,22]` | 0 | 6 |

The corrected criterion counts black pixels only inside the bounding box of
the coloured two-glyph field. A gap between adjacent glyphs must lie inside
that box and therefore still fails. Outer image padding does not. Under this
criterion Candidate 4 has zero internal black pixels in all 20 tests.

The same correction was applied to the exact-core Candidate 1 control. Its
previously reported 16/20 solid-field failures were the same exterior padding,
not internal cell seams. Candidate 1 consequently passes the corrected
continuity control; Candidate 4 additionally retains its explicit per-point
grid-fitting program for deterministic sparse-pixel placement.

### Real MATE Terminal validation

The isolated Candidate 4 profile was then used by MATE Terminal 1.26.1 at
14 pt. The tests emitted foreground PUA glyphs only:

- a 180 x 120 virtual-pixel RGB triangle;
- alternating cyan and magenta `U+107FFF` cells;
- a white same-colour `U+107FFF` field;
- vertically adjacent cyan and magenta `U+107FFF` rows; and
- the previously failing box/grid masks.

The triangle has no enclosed black pixels. The horizontal solid probe renders
180 cyan device pixels immediately followed by 181 magenta device pixels on
every occupied scanline, with no black pixel at the join. The vertical probe
renders 19 continuous cyan rows immediately followed by 19 continuous magenta
rows.

The promoted FontPlotter runtime was then exercised on Linux with its complete
test suite: **31 tests passed**. This includes separate assertions for a solid
single-colour foreground cell (`0xFFFF`, `U+107FFF`, background flag clear) and
for the legitimate two-depth case where a sparse nearer foreground glyph may
use a farther colour as the terminal background.

![Candidate 4 foreground triangle in MATE Terminal](../experiments/pua-4x4/output/audit/candidate4-release-linux/terminal-stack/mate-terminal-candidate4-triangle-14pt.png)

![Candidate 4 foreground raster controls in MATE Terminal](../experiments/pua-4x4/output/audit/candidate4-release-linux/terminal-stack/mate-terminal-candidate4-raster-14pt.png)

## Rejected workaround

An intermediate experiment encoded a fully occupied cell as a blank glyph with
the solid colour placed in the terminal background. Terminal-owned background
rectangles were continuous in 40/40 diagnostic cases, but that is not an
acceptable solution for this project.

It was rejected because it made the representation depend on occupancy:

```text
partial cell -> PUA foreground mask
full cell    -> blank glyph + background colour
```

That breaks the intended direct relationship between framebuffer bits, mask,
codepoint and glyph, and complicates OR, AND, XOR, inspection, backup and
restore. The experiment was removed from FontPlotter; it is not a release gate.

## Reproducibility

Build Candidate 4 without replacing earlier candidates:

```bash
cd ~/dev/FontMaker/pua4x4
python3 make_v05_candidate4_strict.py
./install-linux-v05-candidate4.sh
```

Run the corrected audit and real-terminal probes:

```bash
python3 audit_candidate4_release.py
./launch-linux-v05-candidate4.sh triangle
./launch-linux-v05-candidate4.sh raster
```

The expected exit status is zero and the expected final decision is
`release_gate: PASS`.

## Promotion rule

Candidate 4 may replace Candidate 3 in the runtime only as the same two-font
foreground encoder. Promotion must not add an occupancy-dependent special
case. Empty, partial and full cells continue to map directly to their exact
16-bit masks and P0/P1 codepoints.
