# Voyager 2 Grand Tour

This demonstration renders NASA's Voyager spacecraft in a continuously looping
terminal animation.  The same scene can be encoded through either the released
Square Braille 2×4 font or the PUA 4×4 v0.6 RC1 / Candidate 6 font pair.

## macOS Apple Silicon quick start

From the repository root:

```sh
./scripts/macos/install-all-user.sh
./scripts/macos/run-demo.sh square voyager --camera grand-tour --style wire
./scripts/macos/run-demo.sh pua4 voyager --camera contour --style wire
```

Capture/playback and explicit window sizing are documented in
[the complete macOS guide](../../docs/QUICKSTART-MACOS-ALL-FONTS.md).

## Linux quick start

From the repository root:

```sh
cd experiments/voyager-grand-tour
./run-linux.sh -2
./run-linux.sh -4
```

The launcher installs/configures the selected font in a dedicated MATE Terminal
profile before starting the demo.  It does not replace the other profile.
It detects both this published repository layout and the historical
`~/dev/FontMaker` development-tree layout.

Useful variants:

```sh
# Surface rendering with depth buffering
./run-linux.sh -4 --style filled

# Wireframe with hidden-line removal (default)
./run-linux.sh -4 --style wire

# Fast transparent wireframe: deliberately show rear/occluded edges
./run-linux.sh -4 --style wire --no-hlr

# Close, smooth, contour-hugging inspection of the spacecraft
./run-linux.sh -4 --camera contour

# One complete 60-second tour, then exit
./run-linux.sh -2 --once

# Save a replayable ANSI frame at mission time 24 s
./run-linux.sh -4 --freeze-at 24 --capture "$HOME/voyager-saturn.ansi"
# Later, in the same -4 font profile:
cat "$HOME/voyager-saturn.ansi"
```

If the terminal already uses the correct font profile, run the renderer directly:

```sh
python3 voyager_grand_tour.py -2
python3 voyager_grand_tour.py -4 --camera contour --style wire
```

Runtime keys are `q`/Escape to quit, `f` to switch wire/filled, `h` to
switch hidden-line removal for wireframe, and `c` to switch Grand Tour/contour
camera programmes.  Resizing the terminal changes the virtual framebuffer on
the next frame; there is no 246-column limit.

## Layer-aware live compositing

The live Linux and macOS launchers run the same renderer and the same
two-colour terminal compositor.  The status line displays `2CLR=ON` when this
path is active.  The scene is retained as ordered semantic layers until the
final terminal-cell encode: stars, rear rings, planet, front rings, moons and
Voyager.  Ring samples are classified geometrically against the visible planet
surface instead of relying on draw order alone.

Within a terminal cell, the nearest visible layer owns the PUA/Braille glyph
mask and ANSI foreground colour.  Where unselected subpixels reveal the next
layer, the encoder may retain that layer as the ANSI background colour.  It
does so only when measured RGB reconstruction error is lower.  Consequently a
sparse cyan spacecraft edge crossing a blue planet remains a sparse cyan
glyph over blue; it no longer turns the entire 4x4 cell cyan.  The real glyph
is always emitted—this does not use reverse video or replace a full glyph with
a space.

This enhancement currently applies to the live animation and ANSI snapshot
path.  The VGR v1 packet described below stores one mask and one foreground
RGB value per cell.  Existing VGR v1 recordings therefore cannot contain, or
recover, the second colour and semantic depth information.  VGR v1 capture and
playback remain unchanged for format compatibility.

## Offline capture and exact playback

The normative container layout, 22-byte VGF1 header, mask/color plane sizes,
metadata contract and compatibility rules are in the
[VGR v1 format reference](../../docs/VGR-FORMAT.md). Cross-platform user-only
installation and operator commands are in the
[operations quick start](../../docs/OPERATIONS-QUICKSTART.md).

The same program can render a tour without drawing the scene to the terminal,
store every frame in an indexed `.vgr` archive, and later replay those frames
without repeating any 3D calculation. During capture, the terminal shows a
cyan-and-amber instrumentation dashboard rather than the animation. It reports
the current frame, animation time, frame-render time, real elapsed time,
estimated time remaining, achieved capture rate, P0/P1 cell and unique-glyph
counts, active and blank cells, distinct mask states, bytes per frame, raw and
compressed sizes, compression ratio, encounter, visible geometry, frame write
latency, archive data rate, frame-flow activity and the Grand Tour timeline.
The frame-rate and data-rate histories use btop-style sparklines with their
current measured values printed alongside. On a terminal of at least 132×44
cells it expands into the
full cinematic console: configuration and live 4×4 mask inspection, an actual
current-frame PUA preview inside the central targeting aperture, animated
performance traces, the frame-processing pipeline, storage telemetry and the
planetary encounter rail. Smaller terminals automatically use a compact HUD.

Capture a 60-second 4×4 tour sampled at 12 frames per animation second:

```sh
./run-linux.sh -4 capture \
  --duration 60 --fps 12 \
  --output "$HOME/voyager-grand-tour-4x4.vgr"
```

Choose the size of the newly opened terminal in character cells with the two
launcher-only options below. If renderer `--columns` and `--rows` are omitted,
the capture reads and uses the actual dimensions of this new terminal:

```sh
./run-linux.sh -4 capture \
  --terminal-columns 180 --terminal-rows 52 \
  --style wire --duration 60 --fps 12 \
  --output "$HOME/voyager-wire-hlr-180x52.vgr"
```

This opens a 180-column by 52-row MATE Terminal instead of maximizing it and
captures the resulting terminal grid. Wireframe rendering uses hidden-line
removal unless `--no-hlr` is supplied.

Window geometry and recorded geometry can also be controlled independently.
For example, this keeps the dashboard window at 180×52 while recording a fixed
160×44 cell frame:

```sh
./run-linux.sh -4 capture \
  --terminal-columns 180 --terminal-rows 52 \
  --columns 160 --rows 44 \
  --style wire --duration 60 --fps 12 \
  --output "$HOME/voyager-wire-hlr-fixed-160x44.vgr"
```

`--terminal-columns/--terminal-rows` are consumed by `run-linux.sh` and control
MATE Terminal. `--columns/--rows` are forwarded to the renderer and stored in
the `.vgr` metadata. Specify both members of either pair when fixing a size.

Very large logical windows may exceed the physical desktop at the profile's
normal 14-point size. MATE then constrains the window and the PTY can have fewer
cells than requested. `--terminal-zoom` reduces the physical cell size without
changing the logical rows or columns. On the 1920×990 Linux development desktop,
the following produces and preserves a genuine 360×104 terminal:

```sh
./run-linux.sh -4 play \
  --terminal-columns 360 --terminal-rows 104 \
  --terminal-zoom 0.40 \
  "$HOME/voyager-wire-hlr-4x4.vgr"
```

The player still validates the actual PTY geometry against the dimensions
stored in the recording. This prevents a constrained or incorrectly sized
window from silently clipping a frame.

Capture also performs a strict geometry preflight. When launcher terminal
dimensions are supplied, the renderer compares them with the actual PTY that
MATE created. If the window manager constrained the request, capture aborts
before frame 1 and does not publish an archive:

```text
Capture aborted before frame 1: requested terminal 360x104, but MATE created
211x50 (zoom not set). Reduce --terminal-zoom, reduce the requested geometry,
or enlarge the desktop. No recording was written.
```

For successful captures, `terminal.launcher_zoom` in `metadata.json` records
the MATE zoom used to obtain the terminal geometry.

Capture a 2×4 contour fly-around, replacing a previous archive if necessary:

```sh
./run-linux.sh -2 capture \
  --duration 30 --fps 8 --camera contour --style wire \
  --output "$HOME/voyager-contour-2x4.vgr" --force
```

`--fps` is the deterministic animation sampling rate. For example, 60 seconds
at 12 fps produces exactly 720 frames at mission times `0`, `1/12`, `2/12`, ….
The recorder renders them as fast as the machine permits; it does not sleep to
simulate real time. `--start-time` chooses the initial mission time. The default
is 60 seconds at 4 fps. Use `--quiet` for batch operation without the dashboard,
`--compression 0..9` to tune DEFLATE, and `--columns`/`--rows` to fix the
captured terminal geometry.

Play the archive at its recorded rate:

```sh
./run-linux.sh -4 play "$HOME/voyager-grand-tour-4x4.vgr"
```

Useful player variants:

```sh
# Continuous replay
./run-linux.sh -4 play "$HOME/voyager-grand-tour-4x4.vgr" --loop

# Override playback rate or play at half speed
./run-linux.sh -4 play "$HOME/voyager-grand-tour-4x4.vgr" --fps 20
./run-linux.sh -4 play "$HOME/voyager-grand-tour-4x4.vgr" --speed 0.5

# Decode each indexed frame on demand instead of preloading all frames
./run-linux.sh -4 play "$HOME/voyager-grand-tour-4x4.vgr" --stream
```

Player controls are Space to pause/resume, left/right arrows to step while
paused, `+`/`-` to change speed, `r` to restart, and `q`/Escape to quit. The
player verifies every ZIP member CRC before playback. It also rejects `-2`/`-4`
font-mode mismatches and, by default, a terminal smaller than the captured
geometry. `--allow-small-terminal` overrides only the size check; it does not
rescale recorded cells.

The direct equivalents, for an already configured terminal profile, are:

```sh
python3 voyager_grand_tour.py capture -4 --duration 60 --fps 12 \
  --output "$HOME/voyager-grand-tour-4x4.vgr"
python3 voyager_grand_tour.py play -4 "$HOME/voyager-grand-tour-4x4.vgr" --loop
```

### VGR v1 archive

A `.vgr` file is a ZIP64-capable container with a stable metadata schema:

```text
metadata.json
frames/00000000.vgf
frames/00000001.vgf
…
```

Each `.vgf` member is independently compressed and indexed, permitting random
access, paused single-frame stepping and streaming. Its binary payload is a
small `VGF1` header followed by one mask per terminal cell (8 bits for 2×4 or
16-bit little-endian for 4×4), then RGB888 foreground colour for every cell.
There is no background-colour or per-virtual-pixel depth plane in VGR v1.
`metadata.json` records font mode, renderer/source hashes, NASA model
provenance, terminal and virtual dimensions, bit mapping, camera/style/HLR,
timeline, capture rate, each frame's mission time, render/write timing, sizes,
CRC-32, encounter, visible geometry counts and the per-frame encoding census.

Frames are not installed into the operating system. The `.vgr` can live in any
user-writable directory; its matching 2x4 or 4x4 fonts must be installed and
selected separately. Use `scripts/vgr-info.py FILE.vgr` from the repository
root to verify CRCs and report stored mode, geometry, frame count, duration and
playback rate before opening a terminal.

### What the 4×4 PUA encode figures mean

For a captured terminal grid of `C × R`, the encoder produces exactly `C × R`
16-bit masks per frame. The dashboard separates those masks as follows:

- **CELLS** is every terminal cell in the frame. **ACTIVE** is the number whose
  mask is nonzero; **BLANK** is the number whose mask is zero. Active plus blank
  therefore always equals cells. The dashboard also prints each as a percentage
  of the complete frame, so occupancy is visible without mental arithmetic.
- **MASKS** is the number of distinct 16-bit values present, including mask zero
  when the frame contains blank cells. **PUA** is the distinct nonzero-mask
  count. An earlier dashboard called these two figures `STATES` and `GLYPHS`;
  that wording was removed because the figures normally differ only by the
  blank mask and implied two independent resources. Every unique nonzero mask
  does select one PUA codepoint and therefore one font glyph, but the useful
  capture statistic is mask diversity and reuse.
- **P0 C/U** and **P1 C/U** mean *cell occurrences / unique masks*. **U/C** is
  the unique-mask count divided by the cell-occurrence count, as a percentage.
  A low U/C value means many cells reuse a small mask vocabulary; a high value
  means a visually diverse frame. P0 contains
  masks `0x0001..0x7FFF`, mapped to `U+F0001..U+F7FFF`. P1 contains masks
  `0x8000..0xFFFF`, mapped to `U+100000..U+107FFF`. Mask zero is stored in the
  frame but emitted as an ordinary space, so it belongs to neither active PUA
  count. P0 cells plus P1 cells always equals active cells.
- **FRAME BUFFER / PACKET** makes the in-memory boundary explicit. The renderer
  first owns a mask plane (`C × R × 2` bytes in 4×4 mode) and an RGB plane
  (`C × R × 3` bytes). `encode_frame_packet()` serialises a 22-byte `VGF1`
  header followed by those two planes. **RAW PACKET** is this complete,
  uncompressed in-memory byte string—not a network packet and not data read
  from elsewhere. Therefore a 4×4 frame is exactly `22 + 5 × C × R` bytes.
  **PACKET BUILD** times that serialisation. **DEFLATE** is the size after the
  packet becomes an independently compressed ZIP member; **RATIO** is raw size
  divided by compressed size.
- **ARCHIVE I/O** starts after packet assembly. **WRITE** is the compressed
  member size, **I/O** is the DEFLATE-plus-archive-write latency, and **WRITE
  RATE** is `WRITE / I/O` for the current member. Capture performs no archive
  reads, so **READ** is correctly zero and marked idle. The W/R traces are
  separate histories; playback is the phase that reads frame members.
- **FRAME STORAGE** reports the physical `.partial` archive size, cumulative
  compressed frame-member bytes, current member name, and the average archive
  growth rate. `INDEXED + CRC32` means the member has a ZIP central-directory
  entry and per-member integrity checksum; the final `metadata.json` is added
  when capture completes.
- **FRAME RATE** is completed frames divided by real capture time, not the
  requested animation sampling rate. **DATA RATE** is cumulative compressed
  frame bytes divided by real capture time. Both graphs retain the most recent
  72 dashboard samples and print the current value in FPS or bytes per second.
  The pipeline adds histories for render time, occupancy, compression ratio,
  archive write/read throughput and cumulative storage.

The same census is written under `frames[].encoding` in `metadata.json`; it is
not merely a dashboard estimate. For example:

```json
"encoding": {
  "total_cells": 10339,
  "occupied_cells": 2851,
  "blank_cells": 7488,
  "unique_masks_including_blank": 327,
  "unique_nonzero_masks": 326,
  "p0_cells": 2404,
  "p1_cells": 447,
  "p0_unique_masks": 251,
  "p1_unique_masks": 75
}
```

Metadata can be inspected without the player:

```sh
unzip -p "$HOME/voyager-grand-tour-4x4.vgr" metadata.json | python3 -m json.tool | less
unzip -t "$HOME/voyager-grand-tour-4x4.vgr"
```

The writer uses an adjacent `.partial` file and atomically publishes the final
archive only after all frames and metadata are complete. An existing target is
preserved unless `--force` is explicitly supplied.

The default target is 4 fps.  At 100×32 terminal cells on the development
machine, measured rates were approximately 5.6 fps (`-2` wire/HLR), 3.6 fps
(`-4` wire/HLR or filled/depth), and 15 fps (`-4` wire/`--no-hlr`).  These are
evidence points rather than guarantees: cost grows with window size and the
visible model area.  Set `--fps` to any positive target.

## Rendering modes

For a terminal region of `C` columns by `R` graphics rows:

| option | subpixels per cell | virtual framebuffer |
|---|---:|---:|
| `-2` | 2×4 | `(2C) × (4R)` |
| `-4` | 4×4 | `(4C) × (4R)` |

The terminal cell remains approximately 1:2 (width:height).  A 4×4 virtual
pixel is therefore physically half as wide as a 2×4 virtual pixel.  The 3D
projection compensates by multiplying its horizontal focal length by
`mode / 2`; a sphere and the spacecraft retain the same physical proportions
in both encodings.

`wire` draws material-colored topology/crease and silhouette edges.  With HLR
enabled, a triangle depth buffer suppresses occluded samples.  `--no-hlr`
intentionally reveals rear edges and avoids that depth pass.  `filled` always
uses a depth buffer because visible-surface selection is intrinsic to filled
rendering; HLR is shown as `N/A` in the status line.

The Grand Tour camera cuts to a new encounter every ten seconds:
Jupiter/Io, Jupiter/Ganymede, Saturn/Titan, Uranus/Miranda,
Neptune/Triton, then interstellar departure. Each encounter is a moving pursuit
shot rather than a turntable: the camera approaches from behind and outside,
dives into a close lateral pass, crosses Voyager's apparent velocity vector,
then recovers ahead while lead tracking, roll, elevation, range, planetary
parallax and speed-dependent star streaks change continuously. Voyager travels
across the frame while both subject centres remain visible. The contour camera
remains the slower inspection option; it follows a periodic cubic Bézier path
with a directional mesh-clearance envelope, keeping it close to the dish, bus,
booms and instrument platform without entering the model.

## What is exact, and what is cinematic

- Spacecraft geometry is derived from NASA's official VTAD Voyager glTF model.
  Its original 20,372 triangles are preserved; only coincident vertices are
  welded for correct topology and hidden-line classification.
- The giant planets use documented equatorial/polar radii, so their oblateness
  and rendered aspect are physically grounded.  Axial tilt, recognizable
  encounter-era bands/spots, rings, and named moons are represented.
- On-screen planet/moon sizes, positions, lighting, and spacecraft-to-body
  distances are deliberately cinematic and **not to scale**.  This is necessary
  to keep a detailed spacecraft and a recognizable planetary body visible in
  the same terminal frame.
- This is not an ephemeris or SPICE trajectory simulator.

## NASA model provenance

- Source page: [Voyager 3D Model — NASA Science](https://science.nasa.gov/resource/voyager-3d-model/)
- Credit: NASA Visualization Technology Applications and Development (VTAD)
- Mission chronology: [Voyager 2 — NASA Science](https://science.nasa.gov/mission/voyager/voyager-2/)
- Spacecraft reference: [Voyager Spacecraft — NASA Science](https://science.nasa.gov/mission/voyager/spacecraft/)
- Tour reference: [Planetary Voyage — NASA Science](https://science.nasa.gov/mission/voyager/planetary-voyage/)

The repository contains a compact derived geometry cache plus its SHA-256 and
source metadata.  See [assets/README.md](assets/README.md).  To independently
reproduce it, download NASA's `Voyager.glb` into
`local-assets/nasa-voyager/` and run `python3 prepare_model.py`.

## Deterministic validation

```sh
python3 -m unittest -v test_voyager_grand_tour.py
```

The tests cover all sixteen PUA bit positions, both Unicode range split
boundaries, the 2×4 encoder, aspect compensation, mesh provenance/counts,
camera clearance, planetary flattening, render smoke tests, binary frame
round-trips for both font modes, indexed capture metadata/CRC validation and
recorded playback.
