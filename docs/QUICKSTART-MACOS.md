# macOS quick start

> **Complete Apple Silicon setup:** for the final Square Braille font, both
> current PUA 4x4 Candidate 6 parts, an isolated fallback terminal, every demo,
> and VGR capture/playback, use
> [macOS Apple Silicon: all fonts and demonstrations](QUICKSTART-MACOS-ALL-FONTS.md).

For both font systems, a deterministic PUA 4x4 fallback terminal, complete
character catalogs, every demo, and VGR capture/playback, see the
[cross-platform operations guide](OPERATIONS-QUICKSTART.md).

## 1. Install for the current user

From Terminal in the repository root:

```sh
./scripts/macos/install-user.sh
```

This copies the recommended TTF to `~/Library/Fonts/`. Alternatively,
double-click the TTF in Finder and select **Install** in Font Book. Font Book
validates fonts during installation.

Font file:

```text
fonts/current/Square-Braille-Unicode-Text-Seamless.ttf
```

## 2. Create an active Terminal shell

1. Quit and reopen Terminal after installation.
2. Open **Terminal → Settings → Profiles**.
3. Duplicate a profile and name it `Square Braille`.
4. In the profile's **Text** settings, choose **Change** beside Font.
5. Select **Square Braille Unicode Text Seamless**, Regular.
6. In the font panel, set character spacing to `0.969` and line spacing to
   `0.861`. Sizes from 8 pt upward were verified with the v1.4 font; 12 pt is a
   comfortable starting size.
7. Choose **Shell → New Window → Square Braille**.

The font includes normal alphanumerics, so this is a usable interactive shell.

## 3. Test

```sh
python3 demos/basic/unicode_braille_probe.py
```

The Unicode and PUA columns should render with identical square patterns.

For a direct seam test:

```sh
for row in 1 2 3 4 5 6; do
    printf '⣿%.0s' {1..60}
    printf '\n'
done
```

To confirm the active font and point size in Terminal.app:

```sh
osascript -e 'tell application "Terminal" to get {font name, font size} of front window'
```

Expected family:

```text
SquareBrailleUnicodeTextSeamless-Regular
```

Command-Plus and Command-Minus apply temporary window zoom and did not change
the point size reported by AppleScript during testing. Set exact test sizes in
the profile's font panel and open a new window.

## 4. Install native demo dependencies

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
./scripts/macos/smoke-demos.sh
```

See [Native macOS demonstration guide](DEMOS-MACOS.md) for every launch command,
interactive controls, 3D model preparation and frame recording.

## 5. Optional build tools

Installing the released font does not require FontForge. To rebuild it locally:

```sh
brew install fontforge python
source .venv/bin/activate
make clean
make verify \
  DEJAVU_MONO=fonts/legacy/unicode-text-seamless-v1.3/Square-Braille-Unicode-Text-Seamless-v1.3.ttf
```

The archived v1.3 font supplies the already licensed normal-text outlines while
the generators replace the Braille geometry with the v1.4 100-unit-overfill
outlines.

Apple's current Font Book documentation describes installation by double-click,
drag-and-drop, or **File → Add Fonts to Current User**:
<https://support.apple.com/guide/font-book/fntbk1000/mac>

## PUA 4x4

Install the final Square Braille TTF and both PUA 4x4 RC1 TTFs for this user:

```sh
./scripts/macos/install-all-user.sh
```

Because the 65,536-pattern 4x4 repertoire is split across two fonts, use the
supplied explicit Candidate 6 WezTerm fallback configuration for deterministic
rendering:

```sh
./scripts/macos/run-demo.sh pua4 shell
```

Terminal.app remains the validated reference for the final Square Braille
2x4 face. For PUA 4x4, the WezTerm configuration makes the required normal
text, Part 0, Part 1 order explicit without changing an existing profile.
The launcher reads the repository TTFs directly, disables WezTerm's built-in
Braille renderer, and verifies the selected font files before opening a window.
