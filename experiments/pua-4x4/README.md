# PUA 4x4 experimental proof

This experiment represents every 16-bit MSB-left 4x4 bitmap in one normal
500-by-1000 terminal cell. It is strictly separate from the released Square
Braille fonts.

```text
 bit 3   bit 2   bit 1   bit 0
 bit 7   bit 6   bit 5   bit 4
 bit 11  bit 10  bit 9   bit 8
 bit 15  bit 14  bit 13  bit 12
```

The complete 65,536-pattern set is divided predictably:

```text
Part 0: masks 0000-7FFF -> U+F0000-U+F7FFF
Part 1: masks 8000-FFFF -> U+100000-U+107FFF
```

The fonts are graphics-only apart from a blank space metric anchor. The Linux
alias uses the released Square Braille Unicode Text Seamless face for normal
text because its proven 500-by-1000 metrics exactly match both graphics parts.

## Status

The approved MSB-left mathematics is proven independently for all 65,536
patterns. Font generation then exposed two separate implementation effects:

1. **v0.3 horizontal placement defect.** Its cmap and raw component layout are
   mathematically correct, but every pattern uses `leftSideBearing = 0`.
   TrueType therefore shifts 4,095 Part 0 patterns whose raw `xMin > 0` to the
   left edge. This is the exact cause of the observed detached and jumping
   pixels.
2. **Raster-audit correction.** The bounding-box audit excluded black line-box
   rows between separately emitted terminal lines. A real 20-row MATE Terminal
   field proved Candidate 4 still has horizontal seams.
3. **v0.4 Candidate 3 ownership defect.** Its 100-unit exterior guard makes
   same-colour fields look continuous, but crosses terminal-cell boundaries.
   A later, differently coloured glyph can overwrite the preceding cell.

The selected **v0.6 Candidate 6 / RC1** preserves Candidate 4's mapping,
codepoints, corrected bearings, strict horizontal ownership, internal 4x4
boundaries and grid fitting. It adds a vertical-only guard at the top and
bottom exterior edges. No background-colour or reverse-video substitution is
used.

Normal and enlarged MATE Terminal sizes pass. The two smallest Ctrl-minus zoom
levels can still reveal horizontal seams and are outside the supported range.

Candidates 1, 3, 4 and 6 remain side-by-side under distinct names. No released
Square Braille asset or existing PUA 4×4 font is overwritten.

## Selected v0.6 RC1 metrics and construction

```text
units per em:       1000
character advance:  500
ascent/descent:     800 / 200
grid:               4 columns x 4 rows
nominal subcell:    125 x 250 font units
horizontal bounds:  x=0..500
guarded y bounds:   y=-300..900
vertical guard:     100 units at top and bottom only
horizontal guard:   none
terminal width:     one column per PUA character
```

Candidate 6 retains Candidate 4's direct simple contours and grid programs.
Internal boundaries remain at x = 125, 250, 375 and y = 50, 300, 550. Exterior
x coordinates remain exactly 0 and 500. Only exterior y coordinates expand
from -200..800 to -300..900.

### Historical construction

v0.3 uses reusable composite pixel outlines and remains preserved. Its earlier
verification proved the raw component/mask mapping but omitted TrueType's
effective placement calculation using `xMin` and `leftSideBearing`; v0.4 makes
that calculation a regression gate.

Version 0.1 used 100 font units of exterior outline overfill. That eliminated
seams but incorrectly made edge pixels 225 units wide instead of 125 units and
made top/bottom pixels 350 units high instead of 250 units. It caused isolated
pixels to change size while moving through a cell. Version 0.1 is preserved in
`legacy/v0.1-overfill100/`; version 0.2 removes the overfill. The earlier claim
that exact-core geometry necessarily produced internal fractional-size seams
was caused by counting exterior Pango image padding. The corrected
internal-join test supersedes it.

Version 0.2 used an LSB-left row layout (`bit = 4*y + x`). That layout was
internally self-consistent, but it did not match the intended mathematical
mapping. Version 0.3 uses `bit = 4*y + (3-x)`: bit values increase from right
to left inside each row while virtual x still increases from left to right.
The v0.2 binaries are preserved in `legacy/v0.2-lsb-left/`.

## Requirements

- Python 3
- FontTools
- Fontconfig
- Pango (`pango-view`)
- Pillow for the pixel-level seam matrix
- ReportLab and pypdf for the reproducible evidence/specification PDFs
- MATE Terminal only for the supplied profile launcher

Regenerate v0.6 RC1 from the preserved Candidate 4 binaries:

```sh
cd experiments/pua-4x4
python3 make_v06_candidate6_vertical_guard.py
./install-linux-v06-candidate6.sh
```

The historical v0.3 build remains reproducible separately:

```sh
python3 generate_pua4x4.py --output-dir build
make verify
```

Install the packaged v0.6 RC1 for the current Linux user and run the first
visual proof:

```sh
./launch-linux.sh demo
```

`launch-linux.sh` now delegates to the isolated v0.6 Candidate 6 launcher. It
installs the checked-in RC1 package, verifies byte identity, `wcwidth`,
Fontconfig and Pango, and selects the candidate-specific terminal profile.

Preserved earlier environments remain available with:

```sh
PUA4X4_USE_V04_RC1=1 ./launch-linux.sh demo
PUA4X4_USE_V05_RC1=1 ./launch-linux.sh demo
PUA4X4_USE_V03=1 ./launch-linux.sh demo
```

Launch the continuously animated vector-flight demonstration:

```sh
./launch-linux.sh motion
```

The animation responds to terminal resizing and corrects its projection for
the 1:2 physical pixel aspect ratio. Circular rings and spiral ribs follow a
curved 3D centreline, making the distant opening sweep around the screen while
particles flow along the vortex walls. Rings continue through the near plane
instead of disappearing early, line brightness increases with proximity, and
an independent parallax starfield covers the complete viewport. It
continuously exercises moving curves, diagonals, individual virtual pixels,
character-boundary crossings and both font parts. Press `q`, Escape or Ctrl-C
to leave it. Direct execution supports `--fps`, `--seconds`, `--columns`,
`--rows` and `--no-color`. Live resizing is uncapped by default; optional
`--max-columns` and `--max-rows` limits can reduce rendering load on extremely
large terminals.

Generate and audit the exhaustive 259-page character specification PDF:

```sh
python3 generate_spec_pdf.py
python3 verify_spec_pdf.py
```

The catalog contains one page for every mask high byte. Each of its 65,536
entries includes the full mask, mapped codepoint and authoritative 4x4 bitmap.

Generate the expanded mapping specification and attach the exhaustive catalog:

```sh
python3 generate_mapping_spec_draft_pdf.py
python3 assemble_complete_spec_pdf.py
python3 verify_complete_spec_pdf.py
```

The 17-page guide begins with Unicode/text/font/glyph terminology, shows all
three Unicode Private Use Areas and explains why 65,536 masks require the P0/P1
split. It then uses a blinking text cursor to magnify one terminal cell into its
local 4x4 grid and follows virtual pixel `(13, 10)` through every coordinate
system, bit 10, bit value `0x0400`, mask `0x9669`, Part 1 codepoint `U+101669` and the final ANSI
cursor write. Further sections provide Boolean truth tables, binary OR/AND
NOT/XOR examples, shadow-framebuffer guidance, the keypress-to-rasterizer
pipeline and a complete executable reference renderer in the appendix. The
final 276-page PDF then appends the unchanged 259-page character specification,
including the complete 256-page mask/codepoint/glyph catalog.

Run the same reference renderer directly:

```sh
cd "$HOME/dev/FontMaker/pua4x4"
./launch-linux.sh reference
```

For a bounded smoke test, first run `./launch-linux.sh shell`, then inside the
new PUA 4x4 terminal run:

```sh
cd "$HOME/dev/FontMaker/pua4x4"
python3 pua4x4_reference_renderer.py \
  --columns 40 --rows 12 --seconds 2 --fps 12
```

`./launch-linux.sh shell` opens a normal interactive shell using the same
three-face Fontconfig alias. `./launch-linux.sh setup` installs and configures
without opening a window.

## Complete PUA 4x4 demo suite

For user-only installation on Linux, macOS and Windows, explicit terminal font
fallback configuration, complete generated-character proof catalogs, and VGR
operations, see `../../docs/OPERATIONS-QUICKSTART.md` in the published
repository.

Every graphical Square Braille demonstration has a separate PUA 4x4 port in
`demos4x4/`; the original programs are preserved. The suite includes geometry,
snow, starfield, trail, RGB triangle, vertical probe, vector tunnel, Elite-style
battle, Doom-style corridor, procedural Enterprise, hidden-line Enterprise and
supplied-mesh flyby demonstrations. It also adds **Defender**, a continuously
looping two-minute procedural gameplay attract mode.

```sh
cd "$HOME/dev/FontMaker/pua4x4/demos4x4"
./run-demo.sh help
./run-demo.sh starfield
./run-demo.sh defender --once
```

The launcher installs/verifies the two v0.5 RC1 graphics parts, configures the
dedicated 12-point candidate profile, and opens the requested demo. See
`demos4x4/README.md`
for the full inventory, direct-execution commands and external mesh-cache
requirements. Its noninteractive structural audit is:

```sh
python3 demos4x4/verify_demos4x4.py
```

## Preserved v0.3 binaries

```text
PUA4x4Part0.ttf
SHA-256 b34587617903d8115d8df788b6430b172c614d8fa9d1689eb403a5c8d26f8c6d

PUA4x4Part1.ttf
SHA-256 ccfad9f530ceda3f33791aec877b81b81472604e68c5e1633c50bb6d2da2681a
```

The historical build is byte-reproducible across the tested macOS and Linux
FontTools environments. Its hashes remain valid, but its effective-placement
defect is now documented above.

## Evidence

- `evidence/pua4x4-pango-proof.png` is the deterministic Pango raster.
- `evidence/pua4x4-terminal-window-proof.png` contains only the dedicated MATE
  Terminal proof window.
- `evidence/pua4x4-motion-proof.png` is a captured frame from the responsive
  curved-vortex animation running in the dedicated 12-point profile.
- `output/pdf/PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf` is the
  mathematics-gate report. It proves the agreed MSB-left coordinate, mask and
  P0/P1 codepoint formulas independently and exhaustively, while recording the
  2026-08-08 triangle terminal output as a separate unpassed visual gate.
- `verify_mathematical_mapping.py` reproduces the machine-readable evidence in
  `output/audit/pua4x4-mathematics-proof-v1.0.json` and the complete one-bit
  table in `output/audit/pua4x4-one-bit-table-v1.0.csv`.
- `output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf` records every v0.4
  expected/observed gate, including the v0.3 bearing defect, rejected hinting
  experiment, seam-guard threshold, paired terminal capture and declared
  overhang.
- `../../docs/PUA-4X4-FONT-GENERATION-EVIDENCE-v0.4.md` is the text evidence
  record.
- `../../docs/PUA-4X4-CANDIDATE-4-EVIDENCE-v0.5.md` records the corrected
  internal-join criterion and Candidate 4 release evidence.
- `../../fonts/candidates/pua-4x4-v0.5-rc1/` contains the selected binaries and
  manifest. The v0.4 Candidate 3 package remains preserved beside it.

## Current limitations

- The mathematical PUA assignment is private and requires these fonts and this
  published mapping agreement.
- Other installed fonts may cover Plane 15 PUA codepoints. The explicit
  `PUA 4x4` Fontconfig alias is therefore required.
- The four horizontal subdivisions are narrower than the four vertical
  subdivisions because a normal terminal cell is approximately 1:2.
- Cross-platform terminal rasterizers still require their own validation;
  Candidate 4's current release gate is specifically the tested Linux
  FreeType/Pango/Cairo/VTE/MATE stack.
- Diagonal vector edges still show ordinary device-pixel antialiasing. This is
  distinct from an incorrect mask, codepoint or effective glyph placement.
- The FontForge 2023 validator did not complete within 60 seconds on a
  32,786-glyph composite font. FontTools generation, exhaustive component
  verification, Fontconfig, Pango and MATE rendering all completed normally.
