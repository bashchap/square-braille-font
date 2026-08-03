# Architecture and history

## Original objective

Represent the 256 patterns from Unicode Braille Patterns `U+2800–U+28FF` as a
2×4 virtual-pixel grid in which every raised dot becomes a full square and
adjacent occupied squares have no visible gap.

## Font generations

1. **PUA Square Braille 1.0** — mapped pattern values to `U+E000–U+E0FF` and
   established 500×1000 terminal-cell metrics.
2. **PUA Square Braille Seamless 1.1** — added 60 font units of exterior
   overfill after raster tests exposed hairline character-cell fractures.
3. **PUA Square Braille Text Seamless 1.2** — merged normalized DejaVu Sans
   Mono glyphs so a terminal could use one primary font for both shell text and
   graphics.
4. **Square Braille Unicode Text Seamless 1.3** — mapped official
   `U+2800–U+28FF` directly to the proven square glyphs while retaining the PUA
   aliases for existing demonstrations.
5. **Square Braille Unicode Text Seamless 1.4** — increased exterior overfill
   from 60 to 100 units after controlled macOS Terminal tests found seams in
   high-contrast `btop` graphics at 9–12 pt. The new outline rendered
   seamlessly down to 8 pt in the tested CoreText environment.

## Current mapping

For every pattern value `n` from 0 through 255:

```text
U+2800 + n ─┐
             ├── the same square-pattern glyph
U+E000 + n ─┘
```

This is a true cmap alias: the corresponding Unicode and PUA characters do not
contain separately regenerated outlines.

## Seam control

- Character advance: 500 font units
- Em: 1000 units
- Ascent/descent: 800/200
- Grid: 2 columns × 4 rows
- Logical square: 250×250 units
- Exterior overfill: 100 units (60 units in archived v1.3)
- Typographic line gap: zero

Normal text fixes the primary terminal font's advance and line-box metrics.
The exterior overfill—not the alphanumeric outlines—is the feature that masks
terminal rasterization seams.

## Evidence

- FontTools cmap, metric and outline verification
- FontForge generation and source files
- Pango/Cairo Linux raster proofs
- CoreText/macOS Terminal proofs at 8–13 pt using solid fills and `btop`
- native macOS Python smoke tests for basic, vector and procedural 3D demos
- native OBJ conversion, grid simplification and hidden-line cache preparation
- solid-fill, checkerboard and moving-diagonal probes
- snow, starfield, interactive trail and filled-triangle demonstrations
- depth-buffered vector and 3D demonstrations

The full engineering record is available as PDF and DOCX in this directory.
Exact macOS reproduction commands are in [DEMOS-MACOS.md](DEMOS-MACOS.md).
