# Linux quick start

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

