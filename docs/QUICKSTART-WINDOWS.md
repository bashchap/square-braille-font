# Windows quick start

## 1. Install for the current user

Open PowerShell in the repository root and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Install-UserFont.ps1
```

Alternatively, right-click
`fonts\current\Square-Braille-Unicode-Text-Seamless.ttf` and choose
**Install**.

Close and restart Windows Terminal after installation.

## 2. Create an active Windows Terminal shell

1. Open Windows Terminal settings with `Ctrl+,`.
2. Select the PowerShell, Command Prompt or WSL profile you want to duplicate.
3. Choose **Duplicate profile** and name it `Square Braille Shell`.
4. Open **Appearance**.
5. Set **Font face** to **Square Braille Unicode Text Seamless**.
6. Set size 14 and save.
7. Open `Square Braille Shell` from the new-tab menu.

The equivalent appearance fragment in `settings.json` is:

```json
"font": {
  "face": "Square Braille Unicode Text Seamless",
  "size": 14,
  "weight": "normal"
}
```

Microsoft documents `font.face` as the per-profile font selector. If the face
is missing or invalid, Windows Terminal falls back to another font:
<https://learn.microsoft.com/windows/terminal/customize-settings/profile-appearance>

## 3. Test

With Python installed:

```powershell
python .\demos\basic\unicode_braille_probe.py
```

The Unicode and PUA columns should render with identical square patterns.

