# Font specifications and candidate lineage

## Released Square Braille 2x4

### Purpose

Provide normal terminal text plus eight independently addressable square
subcells in every terminal character cell. A program can use official Unicode
Braille characters and automatically fall back to ordinary system Braille if
the custom font is unavailable.

### Mapping

For pattern byte `n` in `0..255`:

```text
U+2800 + n --+
               +-- same square-pattern glyph
U+E000 + n --+
```

The PUA alias preserves compatibility with the earliest demonstrations. The
official mapping is preferred for new applications.

### Geometry and metrics

| Property | Value |
|---|---:|
| Character advance | 500 font units |
| Units per em | 1000 |
| Ascent/descent | 800 / 200 |
| Logical grid | 2 columns x 4 rows |
| Logical subcell | 250 x 250 units |
| Exterior guard | 100 units |
| Typographic line gap | 0 |

The exterior guard is deliberate. It hides fractional raster seams in the
validated terminals. It does not change the terminal advance.

### Current files and hashes

```text
TTF fonts/current/Square-Braille-Unicode-Text-Seamless.ttf
SHA 9a32b00193aaf39fc71fd19a16919f1e72bde3da0573cf2f083f404427631d15

OTF fonts/current/Square-Braille-Unicode-Text-Seamless.otf
SHA 78a40f32159af4c48b38eff7b17d76c9475d33854d54c2972c8fec248ff12258
```

Install one format, normally TTF for terminals. Both were verified on
2026-08-17.

### Licensing

- Original project code: MIT.
- Normal text glyph source: DejaVu Sans Mono under the included Bitstream
  Vera/DejaVu license.
- Preserve `LICENSE` and `LICENSE-DejaVu.txt` when redistributing.

## PUA 4x4 repertoire

### Capacity and split

A 4x4 binary grid has 16 positions and 65,536 masks. The repertoire is split
at bit 15:

| Font | Masks | Codepoints | Count |
|---|---|---|---:|
| Part 0 | `0000-7FFF` | `U+F0000-U+F7FFF` | 32,768 |
| Part 1 | `8000-FFFF` | `U+100000-U+107FFF` | 32,768 |

Both ranges are in Unicode supplementary Private Use Areas and require cmap
format 12. The split avoids exceeding practical per-font glyph limits.

### Bit layout

```text
virtual local x ->  0   1   2   3
local y 0           3   2   1   0
local y 1           7   6   5   4
local y 2          11  10   9   8
local y 3          15  14  13  12
```

The left pixel in each row is the row's most significant bit. This is a
project-defined mapping, not the Unicode Braille dot order.

### Mask logic

```python
bit = 4 * local_y + (3 - local_x)
value = 1 << bit
mask |= value       # set
mask &= ~value      # clear
mask ^= value       # toggle
```

OR combines occupancy, AND-NOT clears selected positions, and XOR toggles
selected positions. These mask operations do not themselves resolve colour or
depth; FontPlotter performs those decisions per virtual pixel before reducing
the cell.

### Codepoint logic

```python
def mask_to_codepoint(mask):
    if mask < 0x8000:
        return 0xF0000 + mask
    return 0x100000 + (mask - 0x8000)
```

Reference values:

| Mask | Part | Codepoint | Meaning |
|---:|---:|---:|---|
| `0000` | 0 | `U+F0000` | empty glyph pattern |
| `0001` | 0 | `U+F0001` | top-right subcell |
| `0008` | 0 | `U+F0008` | top-left subcell |
| `0400` | 0 | `U+F0400` | local `(1,2)` only |
| `7FFF` | 0 | `U+F7FFF` | all except bit 15 |
| `8000` | 1 | `U+100000` | bottom-left only |
| `9669` | 1 | `U+101669` | corners plus centre four |
| `FFFF` | 1 | `U+107FFF` | all sixteen subcells |

For `0x9669`, the codepoint calculation is
`0x100000 + (0x9669 - 0x8000) = 0x101669`.

## Candidate lineage

| Build | Mapping | Main property | Outcome |
|---|---|---|---|
| v0.1 | early experiment | initial two-font capacity | historical |
| v0.2 | LSB-left | opposite horizontal bit order | rejected for intended mapping |
| v0.3 | MSB-left | correct mapping, zero LSBs | sparse glyphs shifted; preserved |
| v0.4 Candidate 3 | MSB-left | all-edge 100-unit guard | seamless same-colour fields, but horizontal neighbour overpaint |
| v0.5 Candidate 4 | MSB-left | corrected bearings, strict x ownership | horizontal ownership correct; real-terminal row seams |
| v0.5 Candidate 5 | MSB-left | boundary-hint experiment | not promoted |
| v0.6 Candidate 6 | MSB-left | Candidate 4 plus vertical-only exterior guard | current Linux RC |

## Candidate 6 exact contract

- Source: Candidate 4 binaries.
- Character advance: 500.
- Horizontal glyph ownership: `x=0..500`.
- Horizontal exterior overfill: none.
- Vertical exterior guard: `y=-300..900`.
- Internal 4x4 boundaries: unchanged.
- Mapping and codepoints: unchanged.
- Hint programs: retained.
- Full cell: foreground mask `0xFFFF`, `U+107FFF`.
- Background/reverse-video full-cell substitution: prohibited.

Files:

```text
fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part0V06Candidate6.ttf
fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part1V06Candidate6.ttf
```

## Why raw geometry can still look wrong

Font behavior is a function of more than outline coordinates:

```text
visible placement = outline + side bearings + advance + hinting
                    + shaper/layout + terminal line box + raster rounding
```

Candidate v0.3 proved that a correct raw x range can still be placed wrongly
when side bearings are inconsistent. Candidate 4 proved that correct sparse
horizontal ownership can still have vertical terminal row seams. Candidate 6
proves normal-size continuity but not every extreme fractional ppem.

## Support boundary

- Released 2x4: cross-platform user font, with documented terminal settings.
- Candidate 6 4x4: current Linux release candidate, verified in MATE Terminal
  at normal and enlarged sizes.
- Candidate 6 at the two smallest MATE zoom levels: known unsupported visual
  range because horizontal seams can reappear.
- Candidate 6 on macOS/Windows: portable font files exist, but do not claim a
  validated release until explicit fallback configuration and raster tests are
  completed on those platforms.
