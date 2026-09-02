# macOS Apple Silicon: all fonts and demonstrations

This is the canonical macOS guide for the complete graphics-font collection:

- **Square Braille Unicode Text Seamless** includes normal text and symbols,
  the official Braille Patterns block `U+2800..U+28FF`, and compatibility
  aliases `U+E000..U+E0FF`. Each terminal cell is a 2 × 4 virtual-pixel tile.
- **PUA 4x4 Candidate 6** uses Part 0 and Part 1 to encode all 65,536 masks for
  a 4 × 4 tile. Normal text falls back to the Square Braille text face.

These are user-only steps. They do not use `sudo`, edit system fonts, or alter
an existing Terminal.app profile. A repository-local WezTerm configuration
provides the exact font order for every newly opened demo window.

The launcher also tells WezTerm to read the repository font files directly and
disables WezTerm's built-in Braille renderer. This is essential: otherwise
WezTerm can draw ordinary dotted Braille even though the Square Braille TTF is
installed. Before opening a window, the launcher verifies the resolved file for
Square Braille and, in 4x4 mode, both Candidate 6 parts.

## 1. Clone and prepare Python

```sh
cd "$HOME/Documents"
git clone https://github.com/bashchap/square-braille-font.git
cd square-braille-font

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the repository already exists, use `git pull --ff-only` instead of cloning.

## 2. Install WezTerm without administrator access

The explicit three-font 4×4 fallback is not representable as a Terminal.app
profile. Install native Apple Silicon WezTerm in the user's Applications
directory:

```sh
mkdir -p "$HOME/Applications"
brew install --cask --appdir="$HOME/Applications" wezterm
```

If Homebrew is absent, install it from <https://brew.sh/>. Rosetta is not
required.

## 3. Install and verify all fonts for this user

```sh
cd "$HOME/Documents/square-braille-font"
source .venv/bin/activate

./scripts/macos/install-all-user.sh
python ./scripts/macos/verify-install.py
```

The files are copied to `~/Library/Fonts/`. Quit any already-running terminal
application after installation so CoreText refreshes its font list. The
verifier checks exact bytes, family names, complete cmap ranges, and one-column
macOS widths for both supplementary PUA planes.

## 4. Prove the character repertoires

```sh
./scripts/macos/run-demo.sh square catalog
./scripts/macos/run-demo.sh square aliases
./scripts/macos/run-demo.sh pua4 catalog
./scripts/macos/run-demo.sh pua4 catalog-all
```

The commands expose the official 256 Square patterns, their 256 PUA aliases,
the 65,536 PUA 4×4 masks, or the complete combined catalog. The `font-probe`
demo below proves the normal alphanumeric and symbol characters included in
the Square text face. Press `q` to stop a paged catalog.

Open an interactive shell with the selected graphics environment:

```sh
./scripts/macos/run-demo.sh square shell
./scripts/macos/run-demo.sh pua4 shell
```

## 5. Square Braille 2x4 demonstrations

Each command opens a new isolated window. Arguments after the demo name are
passed unchanged to its Python program.

```sh
./scripts/macos/run-demo.sh square unicode
./scripts/macos/run-demo.sh square font-probe
./scripts/macos/run-demo.sh square geometry
./scripts/macos/run-demo.sh square snow
./scripts/macos/run-demo.sh square starfield
./scripts/macos/run-demo.sh square trail
./scripts/macos/run-demo.sh square triangle --pps 6000 --hold 5
./scripts/macos/run-demo.sh square vertical --hold 20
./scripts/macos/run-demo.sh square vector --duration 30 --fps 20
./scripts/macos/run-demo.sh square doom --duration 30 --fps 6
./scripts/macos/run-demo.sh square elite --once --duration 60 --fps 20
./scripts/macos/run-demo.sh square enterprise --once --duration 60 --fps 1 --detail 2
./scripts/macos/run-demo.sh square voyager --camera grand-tour --style wire
```

`trail` uses the arrow keys; Space raises or lowers the pen, `c` clears, and
`q` quits. Long-running animations accept `Control-C` or their documented quit
key.

## 6. PUA 4x4 demonstrations

```sh
./scripts/macos/run-demo.sh pua4 geometry
./scripts/macos/run-demo.sh pua4 snow
./scripts/macos/run-demo.sh pua4 starfield
./scripts/macos/run-demo.sh pua4 trail
./scripts/macos/run-demo.sh pua4 editor
./scripts/macos/run-demo.sh pua4 triangle
./scripts/macos/run-demo.sh pua4 vertical
./scripts/macos/run-demo.sh pua4 vector --duration 30 --fps 20
./scripts/macos/run-demo.sh pua4 vortex --fps 20
./scripts/macos/run-demo.sh pua4 doom --duration 30 --fps 6
./scripts/macos/run-demo.sh pua4 elite --once --duration 60 --fps 20
./scripts/macos/run-demo.sh pua4 enterprise --once --duration 60 --fps 1 --detail 2
./scripts/macos/run-demo.sh pua4 defender --once
./scripts/macos/run-demo.sh pua4 voyager --camera contour --style wire
./scripts/macos/run-demo.sh pua4 model-viewer --start-rotating
```

The Voyager live demo uses the same layer-aware two-colour compositor on
macOS and Linux.  `2CLR=ON` in its status line confirms that the active path
preserves a sparse foreground spacecraft edge over a differently coloured
planet or ring.  For a stationary Neptune-overlap inspection:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 180 --terminal-rows 52 --font-size 9 \
  pua4 voyager --freeze-at 47.9 --hold 30 --style wire
```

The model viewer uses the included, provenance-recorded NASA Voyager cache.
Press `q` to quit. Its full control table is in
[`experiments/voyager-model-viewer/README.md`](../experiments/voyager-model-viewer/README.md).

## 7. Choose the new window size

Launcher window options must come before `square` or `pua4`:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 180 --terminal-rows 52 --font-size 10 \
  pua4 voyager --camera contour --style wire
```

For a large model-viewer workspace:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 240 --terminal-rows 72 --font-size 8 \
  pua4 model-viewer --start-rotating
```

The values select the initial window geometry. Programs that support live
resize, including Voyager and the model viewer, detect later changes.

## 8. Voyager capture and playback

Create a 60-second PUA 4×4 VGR capture at 12 frames per animation second:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 180 --terminal-rows 52 --font-size 9 \
  pua4 voyager capture \
  --columns 180 --rows 52 --duration 60 --fps 12 \
  --style wire --output "$HOME/voyager-macos-4x4.vgr"
```

Play it at its stored rate:

```sh
./scripts/macos/run-demo.sh \
  --terminal-columns 180 --terminal-rows 52 --font-size 9 \
  pua4 voyager play "$HOME/voyager-macos-4x4.vgr" --loop
```

For 2×4, replace `pua4` with `square`; archive and player modes must match.
VGR records terminal cells, so playback does not repeat the 3D render.
VGR v1 stores one glyph mask and one foreground RGB colour per cell; it does
not store the live compositor's background-colour or depth information.

## 9. External-model demonstrations

These entry points exist for both font modes:

```sh
./scripts/macos/run-demo.sh square enterprise-hlr --mesh /path/to/enterprise_tos_wire.npz
./scripts/macos/run-demo.sh pua4 enterprise-hlr --mesh /path/to/enterprise_tos_wire.npz
./scripts/macos/run-demo.sh square spaceship --mesh /path/to/space_ship_wire.npz
./scripts/macos/run-demo.sh pua4 spaceship --mesh /path/to/space_ship_wire.npz
```

Those two caches cannot be distributed because their source models have
separate licensing. Conversion tools remain in `demos/3d/` and
`experiments/pua-4x4/demos4x4/`. The procedural Enterprise and NASA Voyager
demos above require no external model.

If `--mesh` is omitted, the launcher also looks for the matching cache in
`local-assets/`. If neither location contains it, the command stops in the
calling shell with a clear message instead of opening a window that immediately
disappears. Any unexpected Python failure inside a new window is held on screen
until Return is pressed.

Confirm which fonts WezTerm will actually use:

```sh
FONT_DEMO_ROOT="$PWD" wezterm --config-file config/wezterm/square-braille.lua \
  ls-fonts --codepoints 41,2801,28ff

FONT_DEMO_ROOT="$PWD" wezterm --config-file config/wezterm/pua4.lua \
  ls-fonts --codepoints 41,f0001,100001
```

The output must name the TTFs under this repository, not WezTerm's built-in
Braille renderer, a Nerd Font, or a placeholder glyph.

## 10. Run the complete native M1 audit

```sh
source .venv/bin/activate
./scripts/macos/smoke-all-demos.sh
```

This checks the Square suite, every PUA 4×4 module and mapping, both Voyager
encoders, VGR capture/playback, the model viewer, NASA provenance, hidden-line
rendering, depth modes, and Python syntax. The separately licensed caches are
the only intentional runtime exclusions.

Show the canonical inventory at any time:

```sh
./scripts/macos/run-demo.sh --list
```
