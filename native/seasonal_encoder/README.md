# Shared Rust terminal encoder

This dependency-free optional library accelerates the most expensive inner
part of `demos/seasonal/christmas_snow.py`: scanning each terminal cell to find
its foremost priority, PUA/Square mask, foreground colour, optional rear
colour, and reconstruction-error decision.

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
`--native-encoder on` to require the Rust library.

The ABI functions are `analyse_cells`, `encode_terminal_cells`, and
`encode_terminal_cells_v2`. They accept only borrowed fixed-width buffers and
write into caller-owned output buffers. The library owns no Python objects,
spawns no process, has no third-party crates, and cannot change scene
simulation or glyph mapping.
The seasonal verifier compares its complete ANSI output and telemetry with the
Python implementation byte-for-byte when the release library is available.

On the 2026-09-15 development Mac, the current full-engine benchmark measured
the encode phase at 19.90 to 11.15 ms for 120x36, 48.01 to 29.64 ms for
168x60, and 65.53 to 39.90 ms for 303x46 (Python to Rust, including current
buffer marshaling). Complete-frame improvement was 16.3% at 303x46. These are
directional local measurements, not cross-machine guarantees. Full methodology,
phase tables and migration decisions are in
`demos/seasonal/PERFORMANCE-2026-09-15.md`.

The next optimization boundary is the mutable virtual-pixel `Surface`. Move
its backing store to packed RGB/priority arrays, then port shared primitives,
accumulation and cached-tree compositing as batched operations. Keep behavioural
state machines in Python and avoid a per-pixel FFI boundary.

Not every legacy program should use this encoder. Triangle/vertical seam
diagnostics intentionally write positioned glyphs directly; catalogues and
font probes inspect repertoire behaviour; the editor is an interactive UI.
They have no framebuffer encode loop to accelerate. The shared migration
therefore recreates the performance-critical terminal-emission layer in Rust
without replacing the Python simulations or changing these diagnostic tools.
