# Shared Rust terminal encoder

This dependency-free optional library accelerates the stable rendering data
plane of `demos/seasonal/christmas_snow.py`: packed raster/compositing and the
terminal-cell scan that finds the foremost priority, PUA/Square mask,
foreground colour, optional rear colour, and reconstruction-error decision.

It also exposes complete one-colour and two-colour terminal encoders used by
the established basic, vector, 3D, PUA4 motion and Voyager framebuffer demos.
Those paths support RGB, ANSI-256 and no-colour output with Square Braille,
PUA4-part-0 and PUA4-part-1 mappings. `demos/native_terminal.py` owns library
discovery, buffer marshaling and the byte-compatible Python fallback.

Build it from the repository root:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
```

`christmas-snow` defaults to `--native-encoder auto`: it loads the platform
library when present and otherwise uses the established Python encoder. Use
`--native-encoder off` for an explicit Python comparison or
`--native-encoder on` to require the Rust library. `--native-surface` has the
same `auto|off|on` contract for packed raster and compositing. AUTO enables the
surface path when the native encoder is requested and available.

The ABI includes `analyse_cells`, `encode_terminal_cells`,
`encode_terminal_cells_v2`, and `surface_*` batch operations for rectangles,
lines, thick lines, ellipses, polygons, overlays, priority promotion,
accumulation, cached trees and exposed-edge extraction. All functions accept
borrowed fixed-width buffers and write into caller-owned output buffers. The
library owns no Python objects, spawns no process, has no third-party crates,
and cannot change scene simulation or glyph mapping. The bridge never calls
Rust once per pixel. The seasonal verifier compares every native primitive,
the complete ANSI output and telemetry with Python byte-for-byte.

On the 2026-09-16 development Mac, the 303x46 full-engine path measured 132.90
ms before the packed migration and 25.12 ms afterward, an 81.1% reduction and
5.29x speed-up. In an isolated pair, forcing the packed Python surface while
retaining Rust encoding took 105.52 ms; enabling the native surface reduced
this to 23.85 ms. These are
directional local measurements, not cross-machine guarantees. Full methodology,
phase tables and migration decisions are in
`demos/seasonal/PERFORMANCE-2026-09-15.md`.

Not every legacy program should use this encoder. Triangle/vertical seam
diagnostics intentionally write positioned glyphs directly; catalogues and
font probes inspect repertoire behaviour; the editor is an interactive UI.
They have no framebuffer encode loop to accelerate. The shared migration
therefore recreates the performance-critical terminal-emission layer in Rust
without replacing the Python simulations or changing these diagnostic tools.
