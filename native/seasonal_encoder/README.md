# Seasonal Rust cell analyser

This dependency-free optional library accelerates the most expensive inner
part of `demos/seasonal/christmas_snow.py`: scanning each terminal cell to find
its foremost priority, PUA/Square mask, foreground colour, optional rear
colour, and reconstruction-error decision.

Build it from the repository root:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
```

`christmas-snow` defaults to `--native-encoder auto`: it loads the platform
library when present and otherwise uses the established Python encoder. Use
`--native-encoder off` for an explicit Python comparison or
`--native-encoder on` to require the Rust library.

The native ABI accepts only borrowed fixed-width buffers and writes into a
caller-owned output buffer. It owns no Python objects, spawns no process, has
no third-party crates, and cannot change scene simulation or glyph mapping.
The seasonal verifier compares its complete ANSI output and telemetry with the
Python implementation byte-for-byte when the release library is available.

On the 2026-09-12 development Mac, repeated PUA4 encoding of a fully rendered
168x60-cell scene averaged 61.34 ms in Python and 30.21 ms through Rust,
including buffer marshaling. At 120x36 it averaged 28.01 ms and 13.24 ms.
These are directional local measurements, not cross-machine guarantees.

The next optimization boundary is the mutable virtual-pixel `Surface`. Moving
that backing store to packed native arrays would remove the current per-frame
Python marshaling pass and give scenery rasterization the same native data.
