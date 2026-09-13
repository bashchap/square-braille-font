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

On the 2026-09-12 development Mac, repeated PUA4 encoding of a fully rendered
168x60-cell scene averaged 61.34 ms in Python and 30.21 ms through Rust,
including buffer marshaling. At 120x36 it averaged 28.01 ms and 13.24 ms.
These are directional local measurements, not cross-machine guarantees.

The next optimization boundary is the mutable virtual-pixel `Surface`. Moving
that backing store to packed native arrays would remove the current per-frame
Python marshaling pass and give scenery rasterization the same native data.

Not every legacy program should use this encoder. Triangle/vertical seam
diagnostics intentionally write positioned glyphs directly; catalogues and
font probes inspect repertoire behaviour; the editor is an interactive UI.
They have no framebuffer encode loop to accelerate. The shared migration
therefore recreates the performance-critical terminal-emission layer in Rust
without replacing the Python simulations or changing these diagnostic tools.
