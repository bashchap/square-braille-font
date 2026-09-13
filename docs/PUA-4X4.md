# PUA 4x4 experimental font family

> For the current zero-context status, proof boundaries, operations and
> continuation priorities, begin with the
> [project handover](handover/README.md). Historical Candidate 3 and Candidate
> 4 reports are evidence records, not current operator guidance.

PUA 4x4 represents every possible 4×4 bitmap in one terminal character cell.
It is a separate experiment and does not modify the released Square Braille
fonts.

## Current status

The installed v0.3 binaries are preserved for comparison, but are no longer
the recommended build. Their raw outlines and cmap follow the approved mapping;
however, every pattern was assigned a zero left side bearing. Under TrueType's
effective-placement rule, this shifts **4,095 Part 0 masks** whose raw `xMin`
is greater than zero to the left edge of the cell. This is the reproduced cause
of the detached and jumping pixels seen in the trail and triangle
demonstrations.

The default packaged build is now **v0.6 RC1 / Candidate 6**. It preserves
Candidate 4's corrected bearings, all 65,536 mappings, strict horizontal cell
ownership, internal 4x4 boundaries and per-point grid fitting. It adds a
vertical-only 100-unit guard to the top and bottom exterior edges. This removes
the normal-size stacked-row seams without allowing one terminal column to
paint into its neighbour.

Candidate 4 is preserved but was demoted after a 20-row real-terminal test
revealed horizontal line-box seams that the earlier Pango bounding-box audit
excluded. Candidate 6 passes normal and enlarged MATE Terminal use. Horizontal
seams can still appear at the two smallest Ctrl-minus zoom levels; those
extreme sizes are an explicitly documented limitation.

The earlier v0.4 RC1 / Candidate 3 remains preserved. Its 100-font-unit guard
crosses all four exterior cell edges and can overpaint differently coloured
neighbours, so it is no longer the default.

No current or legacy font is overwritten. Candidate packages use distinct
family names under `fonts/candidates/`.

## Mapping

Virtual coordinates increase left-to-right and top-to-bottom. Inside a cell:

```text
 3  2  1  0
 7  6  5  4
11 10  9  8
15 14 13 12
```

For virtual pixel `(x, y)`:

```text
cell_x  = x // 4
cell_y  = y // 4
local_x = x % 4
local_y = y % 4
bit     = 4 * local_y + (3 - local_x)
value   = 1 << bit
```

Masks `0000–7FFF` map to Part 0 at `U+F0000–U+F7FFF`. Masks `8000–FFFF`
map to Part 1 at `U+100000–U+107FFF` after subtracting `0x8000` for the Part 1
offset.

## Linux quick start

```sh
cd experiments/pua-4x4
./launch-linux.sh demo
```

The unversioned launcher now installs and verifies the packaged v0.6 RC1 fonts,
creates the isolated `PUA 4x4 v0.6 Candidate 6` profile, and opens the demo.
The released Square Braille face remains the ordinary-text fallback.

User-only macOS and Windows installation plus an explicit cross-platform
three-font fallback configuration are documented in the
[operations quick start](OPERATIONS-QUICKSTART.md). The v0.4 RC1 binaries are
installed alongside, rather than over, the final 2x4 font.

To test v0.4 RC1 side-by-side without changing the normal v0.3 alias:

```sh
cd experiments/pua-4x4
./install-linux-v04-candidate3.sh
./launch-linux-v04-candidate3.sh triangle
```

To reproduce a preserved earlier environment explicitly:

```sh
PUA4X4_USE_V04_RC1=1 ./launch-linux.sh demo
PUA4X4_USE_V05_RC1=1 ./launch-linux.sh demo
PUA4X4_USE_V03=1 ./launch-linux.sh demo
```

Run a demonstration with:

```sh
cd experiments/pua-4x4/demos4x4
./run-demo.sh trail
./run-demo.sh starfield
./run-demo.sh defender --once
```

The interactive glyph editor shows every coordinate, bit, mask and codepoint:

```sh
./run-demo.sh editor
```

## v0.6 Candidate 6 verification

Candidate 6 is generated from the preserved Candidate 4 binaries. Its cmap,
mapping, horizontal coordinates, advances and internal boundaries are
unchanged. Only `y=-200` becomes `-300` and `y=800` becomes `900`.

The evidence and supported zoom range are recorded in
[PUA 4x4 Candidate 6 evidence](PUA-4X4-CANDIDATE-6-EVIDENCE-v0.6.md).

```sh
cd experiments/pua-4x4
python3 make_v06_candidate6_vertical_guard.py
./install-linux-v06-candidate6.sh
./launch-linux-v06-candidate6.sh triangle
./launch-linux-v06-candidate6.sh box
```

Candidate 6 SHA-256 identities:

```text
PUA4x4Part0V06Candidate6.ttf  2a473fc9fab1d1399fd46a04f85b9ff04a97962500a05d67c9677cb5bfe999af
PUA4x4Part1V06Candidate6.ttf  f023c3f4c74b69858b2a8083479589166d11c0562b6afe7261263127eb43dfe0
```

## Preserved v0.5 Candidate 4 verification

Candidate 4 is preserved for reproduction. Its mathematics and sparse
horizontal ownership pass, but its real MATE Terminal stacked-row field has
horizontal seams. The historical evidence and later correction are recorded in
[PUA 4x4 Candidate 4 evidence](PUA-4X4-CANDIDATE-4-EVIDENCE-v0.5.md).

```sh
cd experiments/pua-4x4
python3 make_v05_candidate4_strict.py
./install-linux-v05-candidate4.sh
python3 audit_candidate4_release.py
./launch-linux-v05-candidate4.sh triangle
./launch-linux-v05-candidate4.sh raster
```

Candidate 4 SHA-256 identities:

```text
PUA4x4Part0V05Candidate4.ttf  7ca7994c0ad220f3115d01c73915b619e89813713d835cc8ba3430c8dfef5d9e
PUA4x4Part1V05Candidate4.ttf  f1b183d7d7ac4f6dc506612efb64db0225f3b6bbfb6b80828e07451fa0c35fe3
```

## Preserved v0.4 verification

```sh
cd experiments/pua-4x4
python3 verify_mathematical_mapping.py
python3 generate_pua4x4_v04_candidate.py
python3 verify_pua4x4_v04_candidate.py
python3 audit_horizontal_placement.py
python3 verify_candidate_freetype_raster.py
python3 make_v04_candidate3_seamguard.py
python3 verify_v04_candidate3_derivation.py
```

Candidate.3 SHA-256 identities:

```text
PUA4x4Part0V04Candidate3.ttf  94847138178994d016d3a0e315be0aa10604c1ea85e01b6d98eb8f41421ac9d8
PUA4x4Part1V04Candidate3.ttf  a979a9568dbe5c0b90bb54eb6bc0e4a70caf536bd4c2e791d589796a984f0ec1
```

The exhaustive generation report records the expected and observed result at
each gate, including the rejected exact-core and hinting candidates, the
fractional-point reproduction condition, terminal screenshots and the
byte-identical Linux rebuild.

`demos4x4/run-demo.sh` selects the current v0.6 RC1 profile. The renderer code,
mask arithmetic and codepoint mapping did not change.

## Historical v0.3 verification

```sh
cd experiments/pua-4x4
python3 verify_pua4x4.py build-v0.3
python3 verify_equal_pixel_geometry.py build-v0.3
python3 verify_trail_steps.py
python3 demos4x4/verify_demos4x4.py
```

The preserved v0.3 SHA-256 identities are:

```text
PUA4x4Part0.ttf  b34587617903d8115d8df788b6430b172c614d8fa9d1689eb403a5c8d26f8c6d
PUA4x4Part1.ttf  ccfad9f530ceda3f33791aec877b81b81472604e68c5e1633c50bb6d2da2681a
```

Version 0.2 used the opposite LSB-left convention and is preserved in
`experiments/pua-4x4/legacy/v0.2-lsb-left/`.

## Specifications

- [Educational mapping and renderer guide](../experiments/pua-4x4/output/pdf/PUA-4x4-Mapping-Specification-v0.8.pdf)
- [Exhaustive 65,536-glyph catalog](../experiments/pua-4x4/output/pdf/PUA-4x4-Full-Character-Specification-v0.2.pdf)
- [Combined 276-page specification](../experiments/pua-4x4/output/pdf/PUA-4x4-Complete-Mapping-and-Glyph-Catalog-v0.8.pdf)
- [Independent mapping-chain evidence](../experiments/pua-4x4/output/pdf/PUA-4x4-Mapping-Chain-MSB-Left-Evidence-v1.2.pdf)
- [Mathematical mapping evidence and observed-failure record](../experiments/pua-4x4/output/pdf/PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf)
- [v0.4 font-generation evidence report](../experiments/pua-4x4/output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf)
- [v0.4 machine-readable generation evidence](PUA-4X4-FONT-GENERATION-EVIDENCE-v0.4.md)
