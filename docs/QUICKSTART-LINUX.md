# Linux quick start

> **Scope:** the direct installation below is for the released 2x4 Square
> Braille font. The current PUA 4x4 build is a Linux release candidate with a
> separate launcher and validation path. See the
> [current handover snapshot](handover/00-CONTEXT-SNAPSHOT.md) before using
> 4x4 instructions from older documents.

For installation of both font systems, complete character catalogs, every
demo, and VGR capture/playback, see the
[cross-platform operations guide](OPERATIONS-QUICKSTART.md).

These instructions install the font for the current user only. Root access is
not required.

## 1. Install and validate

From the repository root:

```sh
./scripts/linux/install-user.sh
```

The font is copied to:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/fonts/
```

Validate the selected file and family:

```sh
fc-match -f 'File: %{file}\nFamily: %{family}\nStyle: %{style}\n' \
  'Square Braille Unicode Text Seamless'
```

## 2. Open an active shell using the font

### MATE Terminal — automatic profile

```sh
./scripts/linux/launch-mate-terminal.sh setup
./scripts/linux/launch-mate-terminal.sh shell
```

Run the Unicode/PUA comparison instead:

```sh
./scripts/linux/launch-mate-terminal.sh probe
```

Run the layered Square Braille Christmas snow demo with every optional scenery
element:

```sh
./scripts/linux/launch-mate-terminal.sh christmas-snow --scenery all
```

### GNOME Terminal, Konsole and other terminals

1. Close and reopen the terminal after installation.
2. Create or duplicate a terminal profile.
3. Disable **Use system/fixed-width font** if present.
4. Select **Square Braille Unicode Text Seamless** at size 14.
5. Open a new window or tab using that profile.

The font contains normal text, so the resulting shell remains readable.

## 3. Test ordinary Unicode Braille

```sh
python3 demos/basic/unicode_braille_probe.py
```

The Unicode and PUA columns should have identical square geometry.

## Fallback behavior

When the profile selects this font, `U+2800–U+28FF` uses the square glyphs.
When the font is unavailable or not selected, the terminal can fall back to its
normal system Braille font without changing the underlying Unicode text.

## PUA 4x4 and VGR

The current PUA 4x4 system is a two-font fallback stack and has a separate
verified MATE profile:

```sh
./experiments/pua-4x4/launch-linux.sh setup
./experiments/pua-4x4/launch-linux.sh shell
```

Launch the PUA 4×4 version directly in its verified MATE profile:

```sh
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow --scenery all
```

The MATE launchers also accept an initial window geometry and font size. The
animation remains responsive to later manual window resizing:

```sh
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow \
  --terminal-columns 240 --terminal-rows 72 --font-size 8 \
  --ambient all --accumulation-rate 1.5 --fps 5
```

All snowfall, scenery, wind, accumulation and shedding options are documented
in [`demos/seasonal/README.md`](../demos/seasonal/README.md).

To tune PUA4 snow live, use two terminals:

```sh
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow --listen
./experiments/pua-4x4/demos4x4/run-demo.sh christmas-snow-control
```

Press `S` in the controller to save an executable
`christmas-snow-preset.command.txt`; run it from the repository root with
`./christmas-snow-preset.command.txt` or
`bash christmas-snow-preset.command.txt`. Use `--detailed-dashboard` on the
viewer for live font-usage, CPU, raster/encode-time, and peak-memory graphs.

For Square Braille, use the same two demo names through
`./scripts/linux/launch-mate-terminal.sh`.

Display every generated character through the appropriate spawned profile:

```sh
./scripts/linux/show-font-characters.sh square
./scripts/linux/show-font-characters.sh pua4
```

See [VGR format](VGR-FORMAT.md) for recording storage and
`OPERATIONS-QUICKSTART.md` for capture/playback commands.
