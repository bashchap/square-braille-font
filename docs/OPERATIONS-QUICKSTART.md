# Cross-platform operations quick start

> **Status notice (2026-08-20):** the 2×4 instructions remain current. The
> cross-platform PUA 4×4 sections below intentionally reproduce preserved v0.4
> Candidate 3 because those macOS/Windows fallback configurations have not yet
> been revalidated with Candidate 6. For the current Linux v0.6 Candidate 6
> route use `experiments/pua-4x4/launch-linux.sh` and the
> [handover operations runbook](handover/06-OPERATIONS-AND-VALIDATION.md).

This is the operator's guide for the two current graphics encodings and the
Voyager Graphics Recording (`.vgr`) tools. Every installation below is scoped
to the signed-in user. `sudo`, an administrator PowerShell, and writes to a
system font directory are neither required nor used.

## 1. Know which font set a program needs

| Mode | Files | Character ranges | Virtual pixels per terminal cell |
|---|---|---|---:|
| Square Braille 2×4 | `Square-Braille-Unicode-Text-Seamless.ttf` | `U+2800–U+28FF`, with compatibility aliases at `U+E000–U+E0FF` | 8 |
| PUA 4×4 v0.4 RC1 | `PUA4x4Part0V04Candidate3.ttf` and `PUA4x4Part1V04Candidate3.ttf` | P0 `U+F0000–U+F7FFF`; P1 `U+100000–U+107FFF` | 16 |

The Square Braille file includes ordinary text and can be selected as a normal
terminal face. The 4×4 repertoire has 65,536 masks, which exceeds one
TrueType font's practical glyph capacity, so it is deliberately divided into
two files. A 4×4 terminal session needs an ordered fallback stack:

```text
Square Braille Unicode Text Seamless
  → PUA 4x4 Part 0 v0.4 Candidate 3
  → PUA 4x4 Part 1 v0.4 Candidate 3
```

Linux Fontconfig supplies that stack under the alias `PUA 4x4 v0.4 Candidate
3`. For macOS and Windows this guide uses WezTerm because it exposes an
explicit, per-user font fallback list. Terminal.app and Windows Terminal each
offer a single primary face in their profile user interface; their automatic
fallback selection is not a reproducible substitute for an ordered P0/P1
stack.

Install TTF, not both TTF and OTF. The current operator assets are:

```text
fonts/current/Square-Braille-Unicode-Text-Seamless.ttf
fonts/candidates/pua-4x4-v0.4-rc1/PUA4x4Part0V04Candidate3.ttf
fonts/candidates/pua-4x4-v0.4-rc1/PUA4x4Part1V04Candidate3.ttf
```

## 2. Linux: install, configure, prove

### User-only locations

The installers copy fonts to:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/fonts/
```

The PUA 4×4 Fontconfig alias is placed in:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d/
```

### Install and create MATE Terminal profiles

From the repository root:

```bash
# Final 2×4 font and profile
./scripts/linux/launch-mate-terminal.sh setup

# Current recommended 4×4 pair, fallback alias and profile
./experiments/pua-4x4/launch-linux.sh setup
```

Validate the exact resolved families and files:

```bash
fc-match -f '2x4: %{family} | %{file}\n' \
  'Square Braille Unicode Text Seamless'

for cp in f0000 f7fff 100000 107fff; do
  printf 'U+%s: ' "$cp"
  fc-match -f '%{family} | %{file}\n' \
    "PUA 4x4 v0.4 Candidate 3:charset=$cp"
done
```

Open readable shells with the correct font configuration:

```bash
./scripts/linux/launch-mate-terminal.sh shell
./experiments/pua-4x4/launch-linux.sh shell
```

### Spawn a proof catalog

```bash
chmod +x scripts/linux/show-font-characters.sh
./scripts/linux/show-font-characters.sh square
./scripts/linux/show-font-characters.sh pua4
```

The Square catalog is 256 glyphs. The 4×4 catalog is all 65,536 masks and is
paged; press Enter for the next page or `q` to stop. In an already configured
terminal the direct equivalents are:

```bash
python3 scripts/show-graphics-font-characters.py square
python3 scripts/show-graphics-font-characters.py pua4
```

## 3. macOS: install, configure, prove

### User-only location and installation

macOS user fonts live in:

```text
$HOME/Library/Fonts/
```

Install all three current TTFs:

```bash
chmod +x scripts/macos/install-all-user.sh
./scripts/macos/install-all-user.sh
```

Quit and reopen terminal applications after installation.

### Final Square Braille profile in Terminal.app

1. Open **Terminal → Settings → Profiles**.
2. Duplicate a profile and name it `Square Braille`.
3. Under **Text → Font → Change**, select **Square Braille Unicode Text
   Seamless**, Regular.
4. Start at 12 pt. The validated seam settings are character spacing `0.969`
   and line spacing `0.861`; the current font was verified from 8 pt upward.
5. Open **Shell → New Window → Square Braille**.

Confirm the active window, not merely the profile label:

```bash
osascript -e 'tell application "Terminal" to get {font name, font size} of front window'
```

Expected PostScript name: `SquareBrailleUnicodeTextSeamless-Regular`.

### Reproducible PUA 4×4 shell with WezTerm

Copying the three fonts installs them, but the 4×4 pair still needs an explicit
fallback order. A no-elevation WezTerm installation is: download its official
macOS release ZIP, extract `WezTerm.app` into `$HOME/Applications`, then add its
CLI to the current shell:

```bash
mkdir -p "$HOME/Applications"
export PATH="$HOME/Applications/WezTerm.app/Contents/MacOS:$PATH"
```

Launch a 4×4 shell without changing your global WezTerm configuration:

```bash
wezterm --config-file "$PWD/config/wezterm/pua4.lua" start --cwd "$PWD"
```

For the final 2×4 font in the same terminal implementation:

```bash
wezterm --config-file "$PWD/config/wezterm/square-braille.lua" start --cwd "$PWD"
```

The supplied 4×4 configuration uses `font_with_fallback` in the exact order
shown in section 1. This is a terminal configuration, not a system-wide font
substitution.

### Spawn a proof catalog

Spawn the final Square Braille proof in the Terminal.app profile created above:

```bash
chmod +x scripts/macos/show-font-characters.sh
./scripts/macos/show-font-characters.sh square
```

Spawn the complete 4×4 proof in an explicitly configured WezTerm window:

```bash
./scripts/macos/show-font-characters.sh pua4
```

Inside any matching Terminal.app or WezTerm window, the direct forms are:

```bash
python3 scripts/show-graphics-font-characters.py square
python3 scripts/show-graphics-font-characters.py pua4
```

A `PUA 4x4` Terminal.app profile is intentionally not asserted as the reference
4×4 configuration; use the WezTerm command above for its deterministic
three-font stack.

## 4. Windows: install, configure, prove

### User-only location and installation

Open a normal, non-administrator PowerShell in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Install-AllUserFonts.ps1
```

The script copies the three TTFs to:

```text
%LOCALAPPDATA%\Microsoft\Windows\Fonts\
```

and registers them under the current user's `HKCU` Fonts key. No `HKLM` entry
and no Windows font-directory write is performed. Restart terminal applications
afterwards.

### Final Square Braille profile in Windows Terminal

1. Open Windows Terminal settings (`Ctrl+,`).
2. Duplicate the PowerShell profile and name it `Square Braille Shell`.
3. Under **Appearance**, choose **Square Braille Unicode Text Seamless** and
   size 14.

Equivalent JSON:

```json
"font": {
  "face": "Square Braille Unicode Text Seamless",
  "size": 14,
  "weight": "normal"
}
```

### Reproducible PUA 4×4 shell with WezTerm

Windows Terminal's `font.face` accepts one face name. For a no-elevation
WezTerm installation, download its official Windows ZIP, expand it under the
current user's profile, and add that directory to the current PowerShell
session:

```powershell
$WezTermHome = "$HOME\Applications\WezTerm"
New-Item -ItemType Directory -Force $WezTermHome | Out-Null
# Expand the downloaded WezTerm ZIP into $WezTermHome, then:
$env:Path = "$WezTermHome;$env:Path"
```

Use the supplied configuration for the required ordered three-font stack:

```powershell
wezterm.exe --config-file "$PWD\config\wezterm\pua4.lua" start --cwd "$PWD"
```

The 2×4 equivalent is:

```powershell
wezterm.exe --config-file "$PWD\config\wezterm\square-braille.lua" start --cwd "$PWD"
```

### Spawn a proof catalog

Spawn the final 2×4 proof in the Windows Terminal profile created above:

```powershell
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Square -Spawn
```

Spawn the complete 4×4 proof with the explicit WezTerm stack:

```powershell
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Pua4 -Spawn
```

From a profile already using the correct stack, the direct forms are:

```powershell
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Square
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Pua4
```

The deterministic PUA path is the explicit WezTerm command above.

## 5. Python runtime

The catalog and basic/vector demos need Python 3. Voyager and mesh renderers
also need NumPy and Pillow. Use a repository-local virtual environment; this is
user-owned and does not alter the system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell equivalent:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 6. Run the demonstrations

### Square Braille 2×4

Run these inside a Square Braille terminal:

```bash
# Basic
python3 demos/basic/unicode_braille_probe.py
python3 demos/basic/geometry_test.py
python3 demos/basic/snow.py
python3 demos/basic/starfield.py
python3 demos/basic/terminal_font_probe.py
python3 demos/basic/triangle.py --pps 6000 --hold 5
python3 demos/basic/trail.py

# Vector
python3 demos/vector/vertical_probe.py --hold 20
python3 demos/vector/vector_tunnel.py --duration 30 --fps 20
python3 demos/vector/doom_demo.py --duration 30 --fps 6
python3 demos/vector/elite_battle.py --once --duration 60 --fps 20

# Procedural and mesh 3-D
python3 demos/3d/enterprise_flyby.py --once --duration 60 --fps 1 --detail 2
python3 demos/3d/enterprise_wireframe.py --help
python3 demos/3d/space_ship_flyby.py --help
python3 demos/3d/replay_ansi_frames.py --help
```

The last three need the locally prepared model caches described in
`docs/DEMOS-MACOS.md`; third-party model data is deliberately not distributed.

### PUA 4×4

On Linux, the launcher opens each demo in the verified PUA profile:

```bash
cd experiments/pua-4x4/demos4x4
./run-demo.sh help
./run-demo.sh geometry
./run-demo.sh snow
./run-demo.sh starfield
./run-demo.sh trail
./run-demo.sh editor
./run-demo.sh triangle
./run-demo.sh vertical
./run-demo.sh vector
./run-demo.sh elite
./run-demo.sh doom
./run-demo.sh enterprise
./run-demo.sh enterprise-hlr
./run-demo.sh spaceship
./run-demo.sh defender --once
```

The mapping/resolution proofs and curved-vortex experiment are separate from
the port inventory:

```bash
cd experiments/pua-4x4
./launch-linux.sh demo
./launch-linux.sh motion
./launch-linux.sh reference
```

Inside an already configured 4×4 terminal on any platform, run the corresponding
Python file directly, for example:

```bash
python3 experiments/pua-4x4/demos4x4/starfield.py
python3 experiments/pua-4x4/demos4x4/defender.py --once
```

`enterprise-hlr` and `spaceship` require external/local mesh caches. The
procedural Enterprise does not.

### Dual-font NASA Voyager Grand Tour

In an already configured shell, select resolution with `-2` or `-4`:

```bash
cd experiments/voyager-grand-tour
python3 voyager_grand_tour.py -2 --camera grand-tour --style wire
python3 voyager_grand_tour.py -4 --camera contour --style wire
python3 voyager_grand_tour.py -4 --style filled
python3 voyager_grand_tour.py -4 --style wire --no-hlr
```

Linux can create the correct profile and window automatically:

```bash
./run-linux.sh -2 --camera grand-tour --style wire
./run-linux.sh -4 --camera contour --style wire
```

### PUA 4×4 NASA Voyager model viewer

```bash
cd experiments/voyager-model-viewer
python3 voyager_model_viewer.py --start-rotating
```

Linux high-resolution launcher:

```bash
./run-linux.sh --terminal-columns 360 --terminal-rows 104 \
  --terminal-zoom 0.40 --start-rotating
```

Press `C` to start/stop a clean model-and-grid `.vgr` recording. See the model
viewer's README for all navigation and recording controls.

## 7. Create, inspect and play `.vgr` recordings

### Deterministic Grand Tour capture

From a prepared 4×4 shell on any platform:

```bash
cd experiments/voyager-grand-tour
python3 voyager_grand_tour.py capture -4 \
  --camera contour --style wire \
  --columns 180 --rows 52 \
  --duration 60 --fps 12 \
  --output "$HOME/voyager-contour-4x4.vgr"
```

For 2×4, change `-4` to `-2` and run it in the Square Braille profile.

PowerShell 4×4 equivalent:

```powershell
Set-Location .\experiments\voyager-grand-tour
python .\voyager_grand_tour.py capture -4 `
  --camera contour --style wire `
  --columns 180 --rows 52 `
  --duration 60 --fps 12 `
  --output "$HOME\voyager-contour-4x4.vgr"
```

Linux launcher example with a guaranteed 360×104 PTY:

```bash
./run-linux.sh -4 capture \
  --terminal-columns 360 --terminal-rows 104 --terminal-zoom 0.40 \
  --columns 360 --rows 104 \
  --camera contour --style wire \
  --duration 300 --fps 12 \
  --output "$HOME/voyager-contour-360x104-5min.vgr"
```

The dashboard's physical size does not define the recording when explicit
renderer `--columns/--rows` are supplied, but the terminal still must be large
enough to display the dashboard. Use `--quiet` to capture without it.

### Inspect before playback

```bash
python3 scripts/vgr-info.py "$HOME/voyager-contour-4x4.vgr"
python3 scripts/vgr-info.py "$HOME/voyager-contour-4x4.vgr" --json | less
```

The first command verifies every ZIP member CRC and reports the stored mode,
geometry, frame count, duration and playback rate. This is the quickest way to
detect an unexpectedly short or low-frame-rate interactive recording.

### Playback

From an already prepared terminal:

```bash
python3 experiments/voyager-grand-tour/voyager_grand_tour.py play -4 \
  "$HOME/voyager-contour-4x4.vgr" --loop --stream
```

PowerShell equivalent:

```powershell
python .\experiments\voyager-grand-tour\voyager_grand_tour.py play -4 `
  "$HOME\voyager-contour-4x4.vgr" --loop --stream
```

Linux can spawn a matching profile and sized terminal:

```bash
cd experiments/voyager-grand-tour
./run-linux.sh -4 play \
  --terminal-columns 360 --terminal-rows 104 --terminal-zoom 0.40 \
  "$HOME/voyager-contour-360x104-5min.vgr" --loop --stream
```

Do not supply `--fps` unless intentionally overriding the rate recorded in
metadata. `--speed 0.5` plays at half that rate. `--no-status` is required for
model-viewer recordings because they use every recorded row for graphics.

Player controls: Space pauses, arrows step while paused, `+`/`-` change speed,
`r` restarts, and `q` or Escape exits.

## 8. Important operational boundaries

- Installing fonts makes them discoverable; it does not make an existing
  terminal window switch fonts. Restart the terminal and use the matching
  profile/configuration.
- A `.vgr` archive stores terminal-cell masks and colours, not TTF files. The
  matching fonts must already be installed for playback.
- Frames are not “installed”. They are independently compressed members inside
  one `.vgr` ZIP container and are decoded by the player.
- Playback never rescales recorded terminal cells. Open a terminal at least as
  large as the recorded geometry; inspect it first with `scripts/vgr-info.py`.
- A Grand Tour capture's `--fps` is its deterministic animation sampling rate.
  An interactive model-viewer recording stores the rate it actually achieved.
- Model-viewer output paths are non-destructive: if the requested filename
  exists, a timestamped suffix is selected. Read the final `Recorded:` message
  or inspect matching files before assuming which archive was written.
- A long elapsed recording can still contain few frames when rendering a very
  large HLR scene is slow. File size follows frame count and compression, not
  wall-clock duration alone.

The byte-level archive specification is in [VGR format](VGR-FORMAT.md).
