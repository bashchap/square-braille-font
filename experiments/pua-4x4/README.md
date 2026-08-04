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

Version 0.3 is a complete Linux proof rather than a proposal or reduced sample:

- all 65,536 patterns are present across two fonts;
- each pattern has one unique supplementary-PUA codepoint;
- every mapping and composite component was exhaustively verified;
- both ranges have `wcwidth=1` under the tested `C.UTF-8` Linux locale;
- all sixteen pixel components have identical 125-by-250-unit bounds and stay
  strictly inside the 500-by-1000 character cell;
- the explicit Fontconfig alias overrides existing Nerd Font PUA collisions;
- Pango selects the text face, Part 0 and Part 1 with zero missing glyphs;
- solid Pango rasters at 8-20 px contain zero seam pixels;
- the dedicated MATE Terminal solid-cell proof contains zero black seam pixels.

The released Square Braille assets are not modified by this experiment.

## Metrics and construction

```text
units per em:       1000
character advance:  500
ascent/descent:     800 / 200
grid:               4 columns x 4 rows
nominal subcell:    125 x 250 font units
exterior overfill:  0 font units
terminal width:     one column per PUA character
```

Each font contains 16 reusable, equal-sized pixel outlines. Pattern glyphs are
compact TrueType composites referencing the selected components. No component
crosses a character boundary. This keeps the two complete fonts near 2 MiB
each while retaining the direct one-character, one-pattern model.

Version 0.1 used 100 font units of exterior outline overfill. That eliminated
seams but incorrectly made edge pixels 225 units wide instead of 125 units and
made top/bottom pixels 350 units high instead of 250 units. It caused isolated
pixels to change size while moving through a cell. Version 0.1 is preserved in
`legacy/v0.1-overfill100/`; version 0.2 removes the overfill. The corrected
fonts still produce zero seam pixels throughout the tested 8-20 px Pango
matrix.

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
- MATE Terminal only for the supplied profile launcher

Build and exhaustively verify:

```sh
cd experiments/pua-4x4
python3 generate_pua4x4.py --output-dir build
python3 verify_pua4x4.py build
```

Or run the equivalent Make target:

```sh
make verify
```

Install for the current Linux user and run the first visual proof:

```sh
./install-linux-user.sh
python3 verify_linux_runtime.py
python3 verify_pango_seams.py
python3 pua4x4_demo.py
```

Create the dedicated MATE Terminal profile and launch the proof:

```sh
./launch-linux.sh demo
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

The launcher installs/verifies the two graphics parts, configures the dedicated
12-point MATE profile, and opens the requested demo. See `demos4x4/README.md`
for the full inventory, direct-execution commands and external mesh-cache
requirements. Its noninteractive structural audit is:

```sh
python3 demos4x4/verify_demos4x4.py
```

## Verified v0.3 binaries

```text
PUA4x4Part0.ttf
SHA-256 b34587617903d8115d8df788b6430b172c614d8fa9d1689eb403a5c8d26f8c6d

PUA4x4Part1.ttf
SHA-256 ccfad9f530ceda3f33791aec877b81b81472604e68c5e1633c50bb6d2da2681a
```

The build is byte-reproducible across the tested macOS and Linux FontTools
environments. The manifest records the mapping, metrics, filenames and hashes.

## Evidence

- `evidence/pua4x4-pango-proof.png` is the deterministic Pango raster.
- `evidence/pua4x4-terminal-window-proof.png` contains only the dedicated MATE
  Terminal proof window.
- `evidence/pua4x4-motion-proof.png` is a captured frame from the responsive
  curved-vortex animation running in the dedicated 12-point profile.

## Current limitations

- The mathematical PUA assignment is private and requires these fonts and this
  published mapping agreement.
- Other installed fonts may cover Plane 15 PUA codepoints. The explicit
  `PUA 4x4` Fontconfig alias is therefore required.
- The four horizontal subdivisions are narrower than the four vertical
  subdivisions because a normal terminal cell is approximately 1:2.
- At font sizes whose em is a fractional number of device pixels, diagonal
  edges show normal antialiasing variation. The independent geometry verifier
  proves exact pixel addressing and mirror symmetry; 12 pt and 18 pt at 96 DPI
  align the 4x4 subdivisions to whole device pixels most cleanly.
- The FontForge 2023 validator did not complete within 60 seconds on a
  32,786-glyph composite font. FontTools generation, exhaustive component
  verification, Fontconfig, Pango and MATE rendering all completed normally.
