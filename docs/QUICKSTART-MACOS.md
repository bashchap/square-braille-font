# macOS quick start

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

Apple's current Font Book documentation describes installation by double-click,
drag-and-drop, or **File → Add Fonts to Current User**:
<https://support.apple.com/guide/font-book/fntbk1000/mac>
