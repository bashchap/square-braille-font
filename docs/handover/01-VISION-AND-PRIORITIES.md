# Vision, intention and priorities

## Original intention

Create a font programmatically, using free tooling, that reproduces the 256
patterns in the official Unicode Braille Patterns block (`U+2800-U+28FF`) but
turns every Braille dot position into a square subcell. Adjacent occupied
subcells must touch horizontally and vertically so the terminal behaves like
a small addressable pixel display rather than a page of dotted characters.

The font must be usable by an ordinary user on Linux, macOS and Windows.
Parameters such as cell dimensions and overfill must remain reproducible in
code rather than being hand-edited in a GUI.

## Evolved intention

The project now aims to provide a terminal-native graphics stack:

1. deterministic subcell fonts (2x4 and 4x4);
2. mathematical conversion between virtual pixels, terminal cells, masks,
   codepoints and glyphs;
3. drawing, animation, 3-D rendering and offline frame capture;
4. a persistent high-performance RAM framebuffer accessible from shell and
   Python clients;
5. depth-aware and two-colour terminal-cell compositing;
6. exact backup/restore, blitting and eventually multi-client operation;
7. evidence that every stage matches the intended mathematics and the real
   terminal result.

## Non-negotiable rules

1. **Mathematics before font generation.** Prove coordinate, bit, mask and
   codepoint formulas independently before attributing a visual defect to a
   font or renderer.
2. **The terminal is the final authority.** FontTools, FreeType and Pango tests
   are necessary but cannot replace a real terminal screenshot at the actual
   font size and zoom.
3. **No hidden full-cell encoding.** A full 4x4 glyph is `0xFFFF` at
   `U+107FFF`, rendered as foreground. Reverse video or a blank glyph with a
   background colour is not an acceptable substitute.
4. **Preserve every candidate.** New fonts, scripts and aliases must be
   side-by-side. Never overwrite the last known-good or historically useful
   binary.
5. **No unexplained visual defects.** Jumping pixels, grid lines, broken
   diagonals and layer inversions require a reproducible root-cause chain.
6. **Foreground and background are terminal-cell properties.** Depth and
   colour originate per virtual pixel; encoding must explicitly explain how
   those richer samples collapse into one glyph, one foreground and optional
   background for a terminal cell.
7. **Normal-user operation.** Installation and runtime should avoid sudo or
   administrator rights.
8. **Linux first, then macOS, then Windows.** Cross-platform claims must name
   the exact tested terminal and font fallback configuration.
9. **Performance matters end to end.** Bulk operations, persistent IPC,
   viewport extraction and coalesced terminal writes are preferred over a
   process or socket request per pixel.
10. **Evidence over reassurance.** State expected result, observed result,
    environment and retained artifact. A PASS means those agree.

## User interaction preferences

- Lead with the result and keep operational answers direct.
- When exploring a risky technical direction, proceed one verified gate at a
  time and wait when the user explicitly requests confirmation.
- Do not bury a requested command under background explanation.
- Visual demonstrations should be attractive, but dashboards must not replace
  or obscure the underlying test.
- Diagnostics should separate labels from values, use readable spacing and
  expose masks/codepoints rather than printing noisy unstructured logs.
- When the user reports a visible contradiction, treat the screenshot as real
  evidence and reproduce it; do not defend the current implementation based
  only on unit tests.

## Priority order at handover

1. Preserve and checkpoint the current dirty working trees.
2. Keep Candidate 6 as the current Linux RC while documenting its small-zoom
   boundary honestly.
3. Complete a Candidate 6 full raster/terminal matrix across sparse,
   full-field, multicolour and box-over-grid cases before a final 4x4 release.
4. Bring cross-platform 4x4 installers/configurations forward from Candidate 3
   only after platform-specific validation.
5. Stabilize FontPlotter semantics and documentation before adding large new
   feature sets.
6. Implement pending framebuffer persistence, FIFO blocks, undo/redo,
   arbitrary viewport/destination blits and multi-client concurrency in
   evidence-backed stages.
7. Preserve the released Square Braille 2x4 font unchanged unless a regression
   is independently demonstrated.
