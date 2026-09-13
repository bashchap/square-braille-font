# Windows quick start

> **Scope:** the direct installation below is for the released 2x4 Square
> Braille font. The current PUA 4x4 Candidate 6 is verified only as a Linux
> release candidate. Historical Windows 4x4 configurations reproduce Candidate
> 3 and are not a Candidate 6 release. See the
> [current handover snapshot](handover/00-CONTEXT-SNAPSHOT.md).

For both font systems, complete character catalogs, every demo, and VGR
capture/playback, see the
[cross-platform operations guide](OPERATIONS-QUICKSTART.md).

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

Run the seasonal Square Braille demo in that configured terminal:

```powershell
python .\demos\seasonal\christmas_snow.py --mode square --scenery all
```

## PUA 4x4

Install the final Square Braille TTF and both PUA 4x4 RC1 TTFs for the current
user from a normal PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Install-AllUserFonts.ps1
```

Because the 65,536-pattern 4x4 repertoire is split across two fonts, use the
supplied explicit WezTerm fallback configuration for deterministic rendering:

```powershell
wezterm.exe --config-file "$PWD\config\wezterm\pua4.lua" start --cwd "$PWD"
```

Inside that PUA4-configured WezTerm window, run:

```powershell
python .\demos\seasonal\christmas_snow.py --mode pua4 --scenery all
```

See `demos\seasonal\README.md` for snow frequency, size, wind, gust, drift,
accumulation, shedding and scenery options.

The viewer and controller can also be run in two already configured terminals:

```powershell
python .\demos\seasonal\christmas_snow.py --mode pua4 --listen
python .\demos\seasonal\christmas_snow_control.py --mode pua4
```

Python's standard `curses` module is required by the controller. On Windows,
install `windows-curses` into the active environment if importing `curses`
fails; the renderer itself has no such dependency.

Add `--detailed-dashboard` to the viewer command for live font-usage, CPU,
raster/encode-time, and peak-memory graphs.
Press `S` in the controller to save both JSON state and a PowerShell-oriented
reproducible command file; the controller's `P` view shows the complete command
before it is saved.

Display the complete catalogs in an appropriately configured shell:

```powershell
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Square
.\scripts\windows\Show-FontCharacters.ps1 -Catalog Pua4
```

Windows Terminal remains suitable for the single-file Square Braille profile.
Its `font.face` setting is one face name; the WezTerm configuration makes the
required P0/P1 fallback order explicit for PUA 4x4.
