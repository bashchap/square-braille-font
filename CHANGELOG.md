# Changelog

## 2026-09-13 engineering publication checkpoint

- Added the experimental two-font PUA 4×4 family and exhaustive MSB-left
  mapping evidence.
- Preserved all historical candidates; promoted v0.6 RC1 / Candidate 6 as the
  current Linux candidate with strict horizontal ownership and a vertical-only
  guard.
- Added 4×4 demonstrations, NASA Voyager renderers, indexed VGR capture/replay
  and the interactive model viewer.
- Added a zero-context project handover under `docs/handover/`.
- Added the cross-font Christmas Snow Lab with fixed scenery anchoring,
  layer-aware two-colour cells, aged local snow-tower collapse/cascades, and a
  separate live keyboard controller with JSON presets and command export.
- Extended Christmas Snow with fixed-aspect cottage, lodge, and A-frame cabin
  variants; terrain-following rabbits that react to tumbleweed and ploughs;
  aeroplane, UFO, and Santa flybys; full-bank snow-plough clearing; and a live
  font-usage telemetry dashboard.
- Redesigned the live controller with colour-coded groups, Unicode controls,
  scope badges, and executable multiline preset scripts whose continued shell
  lines contain literal trailing backslashes.
- Added per-option activity symbols, slider/value guidance, predicted effects,
  and performance-sensitivity warnings to the live controller; extended the
  detailed dashboard with sampled process CPU, raster/encode frame time, frame
  budget, and peak resident memory.
- Replaced the minimal seasonal reindeer and sky-event marks with richer,
  multi-colour virtual-pixel artwork, and made successful macOS snapshot
  windows remain open instead of appearing to fail instantly.
- Reduced the aeroplane, UFO, and foreground reindeer to one third of their
  former linear scale and Santa to one half; refined the sleigh, reins, parcels,
  four-phase jointed reindeer gait, arcing flight, and fading comet trail.
- Added pine, fir, spruce, oak, maple, and birch generation with live branch-count,
  recursion, divergence, length-ratio, trunk-weight, taper-exponent, and branch
  budget controls based on bounded parametric branching and area-aware taper.
- Added a purpose-built seasonal physics layer for slope-relaxed ground snow,
  sparse mass/adhesion-based object snow, stateful terrain-blocked tumbleweed,
  pressure-assisted snow-wall collapse, and distant-flight occlusion.
- Split the detailed dashboard into keyboard-cycled Font, Snow, Trees, Animals,
  Flights, and Process tabs, including current-frame and cumulative glyph use.
- Rebuilt the staged helicopter renderer around thirteen production yaw frames,
  thin projected four-blade rotors and reinforced axial cockpit/intake detail;
  added a separate black/red Airwolf-style flight using the same hover, landing,
  cargo, downwash and low-horizon departure behavior.
- Helicopter landing selection now rejects positions occupied by a rabbit or
  postman, while the live downwash radius prevents rabbits, the postman and
  tumbleweed from entering during descent, landing and takeoff.
- Helicopter departure is now explicitly staged: vertical lift above the
  highest cabin silhouette, a stationary thirteen-frame yaw, then low rear-view
  recession with a scale-aware roof-clearance constraint.
- Optimized cached-tree sway compositing by calculating displacement once per
  occupied scanline rather than per tree pixel. In a repeatable 303x46 PUA4
  full-physics profile this reduced scenery time 44.465 to 33.139 ms (25.5%)
  and complete frame time 120.966 to 110.645 ms (8.5%).
- Restored monochrome compatibility in the shared Rust terminal path: no-colour
  legacy demos may supply either palette indices or RGB tuples, both of which
  are now deliberately ignored rather than coerced.
- Expanded fiery and nuclear impacts into layered red/yellow apocalyptic
  fireballs with persistent embers and smooth end-of-life fading. Foreground
  crash heat now melts a tapered local cavity in accumulated snow.
- This checkpoint publishes Candidate 6, the retained evidence, the seasonal
  expansion and shared Rust terminal encoder together; it is not a tagged
  cross-platform font release.

## 1.4 — Square Braille Unicode Text Seamless

- Increased the exterior guard from 60 to 100 font units after macOS Terminal
  testing exposed small-point-size row seams.
- Verified the selected test environment down to 8 pt.
- Preserved v1.3 binaries under `fonts/legacy/`.

## 1.3 — Square Braille Unicode Text Seamless

- Added official Unicode Braille mappings at `U+2800–U+28FF`.
- Retained identical PUA aliases at `U+E000–U+E0FF`.
- Preserved normal text and the seam-corrected geometry from version 1.2.
- Added cross-platform user installation guides and installers.

## 1.2 — PUA Square Braille Text Seamless

- Added normalized DejaVu Sans Mono text glyphs.
- Made the font suitable as the primary font in an interactive shell.

## 1.1 — PUA Square Braille Seamless

- Added controlled 60-unit exterior overfill.
- Removed visible hairline fractures at terminal character boundaries in the
  tested Linux terminal configuration.

## 1.0 — PUA Square Braille

- Added all 256 Braille bit patterns at `U+E000–U+E0FF`.
- Established the 500×1000, 2×4 square-cell geometry.
