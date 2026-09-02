# Voyager Graphics Recording (`.vgr`) format

## Purpose and scope

VGR v1 records the already rasterized state of a terminal graphics program so
it can be replayed without running the 3-D renderer again. It is used by the
Voyager Grand Tour offline capture and by the interactive Voyager model viewer.
It is not a video codec, a font package, an ANSI transcript, or a model format.

The implementation of record is:

```text
experiments/voyager-grand-tour/voyager_recording.py
```

The schema identifier and version are:

```text
org.square-braille.voyager-recording
format_version = 1
```

## Container layout

A `.vgr` is a ZIP64-capable archive. DEFLATE is used by default and each frame
is an independently indexed member:

```text
metadata.json
frames/00000000.vgf
frames/00000001.vgf
frames/00000002.vgf
…
```

This provides per-frame CRC-32, random access, paused stepping, streaming
decode, and recovery of individual frame payloads with standard ZIP tools.
Capture writes `NAME.vgr.partial`; after all frames and final metadata have
been written, the writer closes the ZIP and atomically renames it to
`NAME.vgr`. An interrupted capture therefore does not publish a valid final
archive under the requested name.

Grand Tour capture refuses to replace an existing target unless `--force` is
given. The model viewer is always non-destructive: it chooses a timestamped
suffix if its requested name or partial file already exists.

## VGF1 frame packet

Each `frames/NNNNNNNN.vgf` member uncompresses to one binary `VGF1` packet:

```text
+--------------------------+ 22-byte little-endian header
| magic                    | 4 bytes: ASCII "VGF1"
| frame index              | uint32
| terminal graphic rows    | uint16
| terminal columns         | uint16
| font mode                | uint8: 2 or 4
| mask width               | uint8: 1 or 2 bytes
| animation timestamp      | float64 seconds
+--------------------------+
| mask plane               | rows × columns masks, row-major
+--------------------------+
| RGB plane                | rows × columns × 3 bytes, row-major RGB888
+--------------------------+
```

Python `struct` declaration:

```python
struct.Struct("<4sIHHBBd")
```

The mode determines mask storage:

| Mode | Cell grid | Mask type | Codepoint interpretation |
|---:|---|---|---|
| 2 | 2×4 | unsigned 8-bit | Unicode Braille `U+2800 + mask` |
| 4 | 4×4 | unsigned 16-bit little-endian | split P0/P1 formula below |

For a frame with `C` columns and `R` graphics rows:

```text
mode 2 raw packet bytes = 22 + (1 × C × R) + (3 × C × R)
                        = 22 + 4CR

mode 4 raw packet bytes = 22 + (2 × C × R) + (3 × C × R)
                        = 22 + 5CR
```

Colours are per terminal cell, not per virtual pixel. Mask zero is normally
emitted as an ordinary space. A nonzero mask selects the glyph; that cell's
RGB triplet becomes its ANSI true-colour foreground.

## 4×4 mask and codepoint mapping

Inside one 4×4 terminal cell, bit positions are MSB-left within every row:

```text
 3  2  1  0
 7  6  5  4
11 10  9  8
15 14 13 12
```

For zero-based virtual pixel `(x, y)`:

```text
cell_x  = x // 4
cell_y  = y // 4
local_x = x % 4
local_y = y % 4
bit     = 4 * local_y + (3 - local_x)
value   = 1 << bit
```

All values set in a cell are ORed to form its 16-bit mask. The mask selects a
codepoint as follows:

```text
if mask < 0x8000:
    codepoint = 0xF0000 + mask
else:
    codepoint = 0x100000 + (mask - 0x8000)
```

Thus P0 covers masks `0000–7FFF` at `U+F0000–U+F7FFF`; P1 covers masks
`8000–FFFF` at `U+100000–U+107FFF`.

## `metadata.json`

Metadata is UTF-8 JSON. The writer currently records these top-level groups:

| Key | Meaning |
|---|---|
| `schema`, `format_version`, `created_utc` | format identity and creation time |
| `renderer` | program title, source hash and runtime versions |
| `model` | NASA model provenance or model census |
| `render` | mode, style, HLR, camera, depth scale and content exclusions |
| `terminal` | columns, total/graphics/status rows, virtual dimensions and cell grid |
| `encoding` | packet description, mask width, ranges and bit mapping |
| `capture` | output, duration, stored playback FPS, frame count, compression and totals |
| `timeline` | Grand Tour encounter intervals; empty for interactive recordings |
| `frames` | ordered per-frame index described below |

Each `frames[]` record contains at least:

```text
index, member, animation_time,
render_seconds, packet_seconds, write_seconds, frame_seconds,
raw_bytes, compressed_bytes, crc32, encounter
```

Grand Tour frames also contain visible-face/edge timing and an encoding census:

```text
total_cells, occupied_cells, blank_cells,
unique_masks_including_blank, unique_nonzero_masks,
p0_cells, p1_cells, p0_unique_masks, p1_unique_masks
```

The final `capture` object adds real elapsed seconds, cumulative raw/compressed
frame-member bytes, and compression ratio.

## Sampling rate versus achieved rate

For deterministic Grand Tour capture, `capture.fps` is the requested animation
sampling rate. `duration × fps` determines the indexed frame count. The render
runs as fast as the machine can compute; it does not sleep between captured
frames. Playback uses this stored FPS unless overridden.

For interactive model-viewer recording, frames are appended only when the
viewer completes a redraw. On finish:

```text
capture.duration_seconds = real recording elapsed time
capture.fps              = frame_count / real elapsed time
```

The stored rate is therefore the rate actually achieved. An 11-hour session
can legitimately produce a comparatively small archive when a 360×104 HLR
render completes only a fraction of one frame per second. VGR compression also
reduces repeated grid/model frames substantially.

## Install, inspect and extract

Frames are not installed. Keep the `.vgr` anywhere writable by the user. The
fonts required by its `render.mode` must be installed and selected separately.

Inspect metadata and verify every member CRC:

```bash
python3 scripts/vgr-info.py recording.vgr
python3 scripts/vgr-info.py recording.vgr --json | less
unzip -t recording.vgr
```

Extract without modifying the original:

```bash
mkdir -p recording-unpacked
cd recording-unpacked
unzip ../recording.vgr
```

The extracted `.vgf` members are binary packets; `cat` is not a renderer. Use
the project player to decode masks, map codepoints and emit ANSI colour.

## Create and play

Direct capture from an already configured PUA 4×4 terminal:

```bash
python3 experiments/voyager-grand-tour/voyager_grand_tour.py capture -4 \
  --columns 180 --rows 52 --duration 60 --fps 12 \
  --camera contour --style wire --output recording.vgr
```

Direct playback:

```bash
python3 experiments/voyager-grand-tour/voyager_grand_tour.py play -4 \
  recording.vgr --loop --stream
```

PowerShell capture and playback use the same Python entry point:

```powershell
python .\experiments\voyager-grand-tour\voyager_grand_tour.py capture -4 `
  --columns 180 --rows 52 --duration 60 --fps 12 `
  --camera contour --style wire --output "$HOME\recording.vgr"

python .\experiments\voyager-grand-tour\voyager_grand_tour.py play -4 `
  "$HOME\recording.vgr" --loop --stream
```

Model-viewer recordings occupy every stored row. Play them with `--no-status`:

```bash
python3 experiments/voyager-grand-tour/voyager_grand_tour.py play -4 \
  voyager-model-view.vgr --no-status --loop --stream
```

The player verifies the complete archive by default, rejects a requested font
mode that differs from metadata, and rejects a terminal smaller than the
recorded grid. `--allow-small-terminal` only suppresses that safety check; it
does not rescale cells and will clip the display.

Player timing is:

```text
effective frame interval = 1 / (stored_or_overridden_fps × speed)
```

Use `--fps` only for an intentional absolute override and `--speed` for a
relative playback change. The default player preloads frames; `--stream`
decodes each indexed member on demand and is preferable for large recordings.

## Compatibility rules for future readers

A conforming VGR v1 reader should:

1. Require the schema string and `format_version == 1`.
2. Confirm `len(frames) == capture.frame_count`.
3. Read members by the names in `frames[]`, not by assuming contiguous ZIP
   physical order.
4. Validate ZIP CRC-32 unless the operator explicitly disables it.
5. Validate VGF1 magic, mode, mask width, dimensions and exact payload length.
6. Interpret 16-bit masks as little-endian and both planes as C/row-major.
7. Preserve the recorded grid; v1 defines no resampling operation.
8. Select the font mode recorded in `render.mode` before emitting glyphs.

The operator walkthrough for all three systems is in
[Cross-platform operations quick start](OPERATIONS-QUICKSTART.md).
