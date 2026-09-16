# Christmas Snow performance analysis — 2026-09-15, implemented 2026-09-16

This report profiles the complete engine, records the Rust migration boundary,
and now includes the measured phase-three implementation. It supersedes the
older recommendation to consider a full rewrite: the rendering data plane was
the correct boundary, not the behavioural engine.

## Method

Measurements were taken on the development Apple Silicon Mac with Python
3.14.7 and Rust 1.78.0. The benchmark uses PUA4, full scenery and tree types,
seven cabins across perspective depths, eight NPCs, six rabbits, eight clouds,
ambient objects, 525 weather particles, a loaded snow bank, and one selected
active flight type. Each result is the median of three runs, ten measured
frames per run, after two warm-up frames. Terminal writes are excluded because
their cost depends on the terminal application; the viewer's PROCESS tab
continues to report that cost separately as `TTY`.

Reproduce the principal comparison after building the native library:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
python3 demos/seasonal/benchmark_christmas_snow.py \
  --workload full --physics full --encoder both \
  --sky-event helicopter --start-seconds 15 \
  --frames 10 --runs 3 \
  --viewport 120x36 --viewport 168x60 --viewport 303x46
```

The selected time places the helicopter in a near, detailed phase. Use
`--sky-event` and `--start-seconds` to isolate another event or phase. `--json`
emits machine-readable results.

## Whole-frame results

| Cells | Encoder | Step | Scenery | Collision | Moving raster | Encode | Total | Ceiling |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 120×36 | Python | 8.54 ms | 6.18 ms | 0.16 ms | 20.98 ms | 19.90 ms | 56.32 ms | 17.76 fps |
| 120×36 | Rust | 8.66 ms | 6.25 ms | 0.18 ms | 20.30 ms | 11.15 ms | 46.97 ms | 21.29 fps |
| 168×60 | Python | 8.88 ms | 22.97 ms | 0.31 ms | 51.18 ms | 48.01 ms | 131.36 ms | 7.61 fps |
| 168×60 | Rust | 8.99 ms | 23.02 ms | 0.31 ms | 52.47 ms | 29.64 ms | 114.07 ms | 8.77 fps |
| 303×46 | Python | 9.25 ms | 16.44 ms | 0.54 ms | 66.44 ms | 65.53 ms | 158.77 ms | 6.30 fps |
| 303×46 | Rust | 9.24 ms | 16.71 ms | 0.54 ms | 66.22 ms | 39.90 ms | 132.90 ms | 7.52 fps |

At 303×46 with Rust enabled, moving-object/final compositing and scenery take
82.93 ms, or 62.4% of the frame. Encoding still takes 30.0%, while all
simulation plus full snow/object collision physics takes 7.4%. Moving the
existing encoder to Rust reduces complete-frame time by 16.3%, but Python must
still convert every `(RGB tuple, priority)` pixel into packed arrays on every
frame.

The current flight implementations are not the dominant scaling problem. A
directional one-run sweep at 303×46/full/Rust ranged from 112.77 ms for an
aeroplane frame to 125.08 ms for Airwolf; the shared framebuffer work dominates
every event.

## Function-level evidence

`cProfile` over 26 full/Rust/helicopter frames recorded 19.7 million calls.
Absolute times are inflated by profiler overhead, but the call distribution is
useful:

- `Surface.pixel` was called 2.01 million times and consumed 1.30 seconds.
- `draw_accumulation` consumed 1.76 seconds.
- native encoding consumed 2.06 seconds, of which the Python
  `NativeAnalyser.analyse` packing bridge consumed 1.38 seconds.
- `build_scenery` consumed 0.80 seconds; cached tree compositing alone consumed
  0.55 seconds.
- `step_npcs` consumed 0.43 seconds, mostly because each NPC rebuilt and
  projected the same cabin path network. This should be cached once per frame,
  but it does not justify moving NPC decisions to Rust.

## Decision

Do not rewrite the entire engine in Rust. Keep event scheduling, NPC/postman/
rabbit state machines, snow rules, live-control application, and procedural art
definitions in Python. They are change-heavy, easy to verify there, and account
for a small part of the measured frame.

The next native component should be the complete `Surface` data plane:

1. Replace the list of optional Python tuples with contiguous RGB and priority
   planes exposed through Python buffers. Preserve the existing `Surface` API
   behind an opt-in parity gate. Let the Rust encoder borrow these buffers
   directly, eliminating per-frame tuple-to-array marshaling.
2. Port the shared hot primitives as batched native operations: priority-tested
   pixel writes, rectangles, lines, thick lines, filled ellipses/polygons, and
   layer compositing. Do not call Rust once per pixel through FFI; submit command
   batches or keep the surface and primitive loop on the Rust side.
3. Port `draw_accumulation` and cached-tree/background compositing first. They
   cover the broadest workloads and avoid duplicating object-specific art.
4. Cache the cabin path network and projected segments once per frame in Python
   as a separate low-risk optimization.
5. Retain the Python surface/encoder as the byte-for-byte oracle until Square
   and PUA4 output, colour ownership, priorities, statistics, resize behaviour,
   and all platform demos pass parity tests.

Only after those stages should a full Rust renderer be reconsidered. Based on
the current phase split, migrating behavioural simulation first would increase
complexity substantially while targeting less than one tenth of frame time.

## Phase three implementation — 2026-09-16

All five recommendations above are complete:

- `Surface` now owns contiguous `array('I')` RGB and `bytearray` priority
  planes. Its list-compatible `pixels` view keeps the Python reference and old
  tests readable, while Rust borrows the real buffers directly with no
  per-frame RGB/priority repacking.
- the dependency-free Rust library now batches priority-tested rectangles,
  lines, thick lines, filled ellipses, filled polygons, overlays, priority
  promotion and exposed-top-edge scans;
- bank accumulation and cached-tree compositing run as native batches, with
  tree geometry packed once and retained by the bridge;
- NPC cabin obstacles and perspective-projected dirt-path segments are built
  once per simulation frame and reused by every NPC; and
- `--native-surface auto|off|on` is a separate restart-only control. `auto`
  enables it with the native encoder, `off` retains the packed Python oracle,
  and `on` fails clearly if the library is unavailable.

The verifier exercises every migrated primitive twice, once through Python and
once through Rust, then requires identical colours, priorities, exposed edges,
ANSI output and telemetry. The entire macOS Square/PUA4/3D/Voyager demo smoke
suite also passed after the migration.

## Post-migration results

These are medians of three runs with eight measured frames after two warm-ups,
using the same full workload at event time zero. `Python/Python` forces both
reference paths off; `Rust/Rust` is the normal built-library `auto` path.

| Cells | Encoder/surface | Step | Scenery | Collision | Moving raster | Encode | Total | Ceiling |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 120×36 | Python/Python | 3.51 ms | 5.57 ms | 0.16 ms | 23.64 ms | 27.56 ms | 60.55 ms | 16.52 fps |
| 120×36 | Rust/Rust | 3.52 ms | 1.17 ms | 0.20 ms | 3.99 ms | 3.28 ms | 12.56 ms | 79.60 fps |
| 168×60 | Python/Python | 3.64 ms | 24.88 ms | 0.31 ms | 57.31 ms | 65.87 ms | 153.50 ms | 6.52 fps |
| 168×60 | Rust/Rust | 3.71 ms | 2.01 ms | 0.35 ms | 5.58 ms | 8.82 ms | 20.53 ms | 48.71 fps |
| 303×46 | Python/Python | 4.22 ms | 17.42 ms | 0.52 ms | 75.59 ms | 91.07 ms | 189.34 ms | 5.28 fps |
| 303×46 | Rust/Rust | 4.24 ms | 2.19 ms | 0.55 ms | 6.42 ms | 11.70 ms | 25.12 ms | 39.81 fps |

At 303×46, keeping the Rust encoder but forcing the packed Python surface took
105.52 ms; enabling the Rust surface reduced that to 23.85 ms in the isolated
pair, a 77.4% complete-frame reduction attributable to the new data plane.
Compared with the previous phase-two production result of 132.90 ms, the
three-viewport result of 25.12 ms is 81.1% lower and 5.29 times faster. The
present terminal-independent ceiling is approximately 40 fps; actual display rate still includes terminal write
and paint time, reported separately as `TTY`.

Reproduce the post-migration comparison with:

```sh
cargo build --release --manifest-path native/seasonal_encoder/Cargo.toml
python3 demos/seasonal/benchmark_christmas_snow.py \
  --workload full --physics full --encoder both --surface auto \
  --sky-event helicopter --frames 8 --runs 3 \
  --viewport 120x36 --viewport 168x60 --viewport 303x46
```

There is no measured reason to migrate event scheduling, snow state, NPC
decisions, postman/rabbit behaviour or the live controller. They are now the
maintainable Python control plane around a borrowed-buffer Rust data plane.
Future work should be driven by a new profile rather than a blanket language
rewrite; terminal presentation is likely to become visible before simulation.
