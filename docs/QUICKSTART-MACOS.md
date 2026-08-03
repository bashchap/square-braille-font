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
5. Select **Square Braille Unicode Text Seamless**, Regular, size 14.
6. Choose **Shell → New Window → Square Braille**.

The font includes normal alphanumerics, so this is a usable interactive shell.

## 3. Test

```sh
python3 demos/basic/unicode_braille_probe.py
```

The Unicode and PUA columns should render with identical square patterns.

Apple's current Font Book documentation describes installation by double-click,
drag-and-drop, or **File → Add Fonts to Current User**:
<https://support.apple.com/guide/font-book/fntbk1000/mac>

