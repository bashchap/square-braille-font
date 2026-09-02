# Voyager PUA 4x4 Model Viewer

An interactive, terminal-native 3-D viewer for the verified NASA Voyager model.
Every visible pixel—including the scaled HUD—is encoded through the PUA 4x4
font. One terminal cell supplies a 4 × 4 virtual-pixel tile.

## Start it on macOS Apple Silicon

From the repository root:

```sh
./scripts/macos/install-all-user.sh
./scripts/macos/run-demo.sh pua4 model-viewer --start-rotating
```

For a larger initial workspace:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 240 --terminal-rows 72 --font-size 8 \
  pua4 model-viewer --start-rotating
```

This uses a repository-local WezTerm Candidate 6 fallback configuration and
does not alter Terminal.app profiles. See
[the complete macOS guide](../../docs/QUICKSTART-MACOS-ALL-FONTS.md).

## Start it on Linux

```bash
cd ~/dev/FontMaker/voyager-model-viewer
./run-linux.sh
```

For the high-resolution workspace:

```bash
./run-linux.sh \
  --terminal-columns 360 \
  --terminal-rows 104 \
  --terminal-zoom 0.40 \
  --start-rotating
```

The window size above creates a 1,440 × 416 virtual-pixel framebuffer. It is
only the initial size: resize the window at any time. `SIGWINCH` and an explicit
geometry poll detect the change; the framebuffer, projection, grid, model, HUD,
and PUA glyph stream are regenerated for the new terminal dimensions.

HUD text defaults to `--hud-scale 2.0`, twice the original proof-of-concept
size. It can be enlarged further, for example with `--hud-scale 2.5`.

## Controls

| Input | Action |
|---|---|
| Arrow keys | Orbit the model, or look in free-camera mode |
| Shift + arrows | Strafe the camera horizontally/vertically |
| `+` / `-` | Dolly toward/away from the target |
| `[` / `]` | Roll the camera |
| Alt + Up/Down | Adjust model X-axis angular velocity |
| Alt + Left/Right | Adjust model Y-axis angular velocity |
| Alt + Shift + Left/Right | Adjust model Z-axis angular velocity |
| Space | Start/pause simultaneous three-axis rotation |
| `1` | Hide/show the camera/view panel |
| `2` | Hide/show the model transform/rotation panel |
| Z | Centre the model and zoom to a close inspection distance |
| C | Start/stop clean full-screen recording |
| Tab | Switch between the viewer and details/control page |
| G | Cycle floor, vertical, and depth grids |
| H | Toggle hidden-line removal |
| F | Toggle wireframe/filled rendering |
| M | Toggle orbit/free camera mode |
| Home, 0, or R | Frame/reset the camera |
| X | Reset model angles and angular velocities |
| Q or Escape | Quit |

Any navigation or configuration key pauses an active rotation loop before the
requested operation. Space restarts it. Angular velocities for all three axes
are retained independently.

The viewer intentionally assigns no action to Ctrl combinations, leaving them
available for existing terminal, multiplexer, or desktop bindings. Hiding one
side panel immediately gives its width to the drawing viewport; hiding both
produces the maximum drawing area.

## Record the clean model view

Press `C` at any time. The recording uses the complete terminal framebuffer:
`columns × rows` PUA cells, equivalent to `4×columns × 4×rows` virtual pixels.
It is not restricted by the live viewer's centre viewport. Every stored frame
contains only the model and selected grids. HUD text, panels, borders, margins,
status rows and the coloured orientation axes are explicitly excluded.

The recording dimensions are fixed when `C` is pressed, so resizing the live
viewer does not introduce mixed frame dimensions. Press `C` again to finish and
index the `.vgr` archive. With no output option, the viewer creates a timestamped
file in the home directory.

To begin recording immediately:

```bash
./run-linux.sh \
  --terminal-columns 360 \
  --terminal-rows 104 \
  --terminal-zoom 0.40 \
  --start-rotating \
  --start-recording \
  --record-output "$HOME/voyager-model-view.vgr"
```

Replay it with the existing indexed VGR player:

```bash
cd ~/dev/FontMaker/voyager-grand-tour
./run-linux.sh -4 play "$HOME/voyager-model-view.vgr" --no-status --loop
```

`--no-status` preserves the full recorded rows for graphics during playback.

Inspect the actual archive selected by the non-destructive recorder before
playback:

```bash
cd ~/dev/FontMaker
python3 scripts/vgr-info.py "$HOME/voyager-model-view.vgr"
```

If that name already existed, the viewer records to a timestamp-suffixed name
instead. The final `Recorded:` line is authoritative. Interactive recordings
store their achieved frame rate (`frame_count / real elapsed`), not merely the
requested redraw target; this explains why a long high-resolution HLR session
can be small and play quickly. The complete binary contract is documented in
[VGR format](../../docs/VGR-FORMAT.md) in the published repository. In the
historical development tree the same document is deployed under `docs/`.

## Responsive pages

At 155 × 42 cells or larger, page 1 shows the central 3-D viewport plus camera
and model side panels. Below that threshold, page 1 gives the model most of the
available area. Page 2 contains camera, model, mesh and render telemetry. Page 3
contains the complete navigation reference. Press `Tab` to cycle pages at any
size; the compact page layouts are deliberately reflowed rather than clipped.

## Direct invocation

From an already prepared PUA 4x4 terminal:

```bash
cd ~/dev/FontMaker/voyager-model-viewer
python3 voyager_model_viewer.py --style wire --depth-scale 2
```

Normally omit `--columns` and `--rows` so live resize remains enabled. Supplying
both fixes the renderer to that geometry, which is useful only for automated
tests or deterministic output.

## Model provenance

The viewer reuses `voyager-vtad-hlr.npz` from the Grand Tour experiment: 12,456
vertices, 20,372 triangles, and 31,637 unique edges. Its source and conversion
metadata remain beside that asset in `voyager-vtad-source.json`.
