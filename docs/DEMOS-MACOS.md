# Native macOS demonstration guide

> **Current complete inventory:** the final Square Braille 2x4 suite and PUA
> 4x4 Candidate 6 suite now share a user-only Apple Silicon launcher. See
> [macOS Apple Silicon: all fonts and demonstrations](QUICKSTART-MACOS-ALL-FONTS.md)
> for the authoritative commands.

The authoritative entry point for both font families is:

```sh
./scripts/macos/run-demo.sh --list
```

Use that launcher rather than invoking the Python files directly. It opens a
new, isolated WezTerm window, loads the repository font files explicitly,
disables WezTerm's built-in dotted-Braille renderer, verifies the selected font
files, and then starts the requested demo. For complete installation, catalog,
Voyager and VGR commands, see
[macOS Apple Silicon: all fonts and demonstrations](QUICKSTART-MACOS-ALL-FONTS.md).

The demonstrations use UTF-8 PUA characters, ANSI colour and standard terminal
control sequences. The basic and vector suites need only Python's standard
library. The 3D renderers additionally use NumPy and Pillow. They run natively
in Terminal.app; no X server, Linux VM or compatibility layer is required.

## Prerequisites

Install the v1.4 TTF and create the Terminal profile described in the
[macOS quick start](QUICKSTART-MACOS.md). The tested CoreText configuration is:

```text
Family:            Square Braille Unicode Text Seamless
Character spacing: 0.969
Line spacing:      0.861
Validated sizes:   8 pt and larger
```

Confirm the active window rather than relying on its profile label:

```sh
osascript -e 'tell application "Terminal" to get {font name, font size} of front window'
```

Terminal.app's Command-Plus and Command-Minus shortcuts apply temporary window
zoom. In the tested macOS version that zoom was not reflected by the AppleScript
`font size` property. For reproducible tests, enter the point size directly in
the profile's font panel and open a new window.

## Python environment

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For later sessions:

```sh
cd ~/Documents/square-braille-font
source .venv/bin/activate
```

Run the automated native smoke test:

```sh
./scripts/macos/smoke-all-demos.sh
```

## Demonstrations through the verified launcher

Square Braille 2×4 examples:

```sh
./scripts/macos/run-demo.sh square snow
./scripts/macos/run-demo.sh square starfield
./scripts/macos/run-demo.sh square triangle --pps 6000 --hold 5
./scripts/macos/run-demo.sh square voyager --camera grand-tour --style wire
```

PUA 4×4 examples:

```sh
./scripts/macos/run-demo.sh pua4 snow
./scripts/macos/run-demo.sh pua4 triangle
./scripts/macos/run-demo.sh pua4 voyager --camera contour --style wire
./scripts/macos/run-demo.sh pua4 vortex --fps 20
```

The `vortex` command is the twisting, moving-opening flight demo. It uses both
PUA 4×4 font parts, shades distant rings more darkly, and distributes the star
field across the entire viewport. Press `q` or Escape to quit.

The direct Python commands below remain useful for development, but they do not
select or verify a terminal font on their own.

## Direct Python: basic demonstrations

```sh
python demos/basic/unicode_braille_probe.py
python demos/basic/geometry_test.py
python demos/basic/snow.py
python demos/basic/starfield.py
python demos/basic/terminal_font_probe.py
python demos/basic/triangle.py --pps 6000 --hold 5
python demos/basic/trail.py
```

Snow and starfield run until `Control-C`. The triangle needs at least 90 columns
by 30 rows; check the current grid with `stty size`. Trail controls are arrow
keys to move, Space to lift or lower the pen, `c` to clear and `q` to quit.

## Vector demonstrations

```sh
python demos/vector/vertical_probe.py --hold 20
python demos/vector/vector_tunnel.py --duration 30 --fps 20
python demos/vector/doom_demo.py --duration 30 --fps 6
python demos/vector/elite_battle.py --once --duration 60 --fps 20
```

Omit `--once` from `elite_battle.py` to loop continuously.

## Procedural 3D Enterprise

This demonstration generates its geometry locally and needs no downloaded
model:

```sh
python demos/3d/test_enterprise_flyby.py
python demos/3d/enterprise_flyby.py \
  --once --duration 60 --fps 1 --detail 2 \
  --max-columns 200 --max-rows 100
```

## Supplied spacecraft OBJ

The renderer accepts a locally held, properly licensed Wavefront OBJ. The
following exact pipeline was tested with `/Users/tara/Downloads/space_shipe.obj`:

```sh
mkdir -p local-assets

python demos/3d/convert_obj_mesh.py \
  "/Users/tara/Downloads/space_shipe.obj" \
  local-assets/space_ship_geometry.npz

python demos/3d/simplify_mesh.py \
  local-assets/space_ship_geometry.npz \
  local-assets/space_ship_simplified.npz \
  --grid 180

python demos/3d/space_ship_flyby.py \
  --prepare-from local-assets/space_ship_simplified.npz \
  --mesh local-assets/space_ship_wire.npz

python demos/3d/space_ship_flyby.py \
  --mesh local-assets/space_ship_wire.npz \
  --once --duration 60 --fps 1
```

The tested conversion produced 429,758 vertices and 803,825 triangles. Grid-180
vertex clustering reduced this to 24,567 vertices and 56,505 triangles; cache
preparation retained 56,504 non-degenerate triangles and 79,310 unique edges.

Record one complete reel and replay it later:

```sh
python demos/3d/space_ship_flyby.py \
  --mesh local-assets/space_ship_wire.npz \
  --duration 60 --fps 1 \
  --record-dir recordings/space_ship

python demos/3d/replay_ansi_frames.py recordings/space_ship --loop
```

## Platform-specific limitations

- Do not use the demos' `--capture` option in Terminal.app. That path expects
  Linux/MATE's `WINDOWID` and ImageMagick's X11 `import` command. Use macOS
  screenshots, or a renderer's `--png` option where available.
- The externally sourced TOS Enterprise wireframe cache and supplied spacecraft
  caches are intentionally absent from Git. Rebuild them from licensed local
  model files as described above.
- `trail.py` requires a real interactive terminal and is therefore excluded
  from the non-interactive smoke test.

## Native evidence

The following were executed successfully on macOS during the v1.4 validation:

- all non-interactive basic and vector smoke frames;
- procedural Enterprise mesh, depth-buffer and PUA mapping tests;
- one procedural Enterprise render frame;
- OBJ conversion, grid simplification, hidden-line cache preparation and one
  supplied-spacecraft render frame;
- high-contrast `btop` rendering without seams at 8 pt.
