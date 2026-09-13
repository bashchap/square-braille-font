# Operations and validation runbook

The current handover integration checks were last run on 2026-08-20. Runtime
and visual evidence retains its own original date; do not substitute the
documentation date for a terminal acceptance date.

## Authoritative working locations

### macOS workspace

```text
/Users/tara/Documents/Codex/2026-07-29/i-want-you-to-create-me/
  github/square-braille-font/
  FontPlotter/
```

### Linux `vmfm1`

```text
/home/tara/dev/FontMaker/
/home/tara/dev/FontMaker/pua4x4/
/home/tara/dev/FontPlotter/
```

The Linux host is reachable as `tara@192.168.1.15` with an existing SSH key.
Do not assume SSH access in a new environment; verify read-only before copying
or installing anything.

## Released 2x4 verification

From the Square Braille repository root:

```bash
python3 src/font/verify_unicode_braille.py \
  fonts/current/Square-Braille-Unicode-Text-Seamless.ttf \
  fonts/current/Square-Braille-Unicode-Text-Seamless.otf

shasum -a 256 \
  fonts/current/Square-Braille-Unicode-Text-Seamless.ttf \
  fonts/current/Square-Braille-Unicode-Text-Seamless.otf
```

Expected hashes are in [the font specification](04-FONT-SPECIFICATIONS.md).

## Linux Candidate 6 setup and inspection

On `vmfm1`:

```bash
cd ~/dev/FontMaker/pua4x4

./launch-linux.sh setup
./launch-linux.sh triangle
./launch-linux.sh box
./launch-linux.sh field
./launch-linux.sh shell
```

The unversioned launcher is expected to select `PUA 4x4 v0.6 Candidate 6`.
It installs files only in the user's font directory and creates an isolated
Fontconfig/MATE profile.

Preserved earlier environments:

```bash
PUA4X4_USE_V05_RC1=1 ./launch-linux.sh triangle
PUA4X4_USE_V04_RC1=1 ./launch-linux.sh triangle
PUA4X4_USE_V03=1     ./launch-linux.sh triangle
```

Do not run tests only at the smallest zoom. Validate normal size, enlarged
size and then deliberately inspect the two smallest Ctrl-minus sizes to
confirm the documented boundary.

## Candidate 6 package integrity

```bash
cd fonts/candidates/pua-4x4-v0.6-rc1
shasum -a 256 -c SHA256SUMS
```

Verify mapping and demo packers:

```bash
python3 experiments/pua-4x4/demos4x4/verify_demos4x4.py
```

Rebuild to a separate directory. Never overwrite the package during a proof:

```bash
python3 experiments/pua-4x4/make_v06_candidate6_vertical_guard.py \
  --output /tmp/pua4x4-candidate6-rebuild
```

Then compare its hashes with the packaged files.

## Real-terminal visual matrix

Minimum visual acceptance cases:

| Case | What it detects |
|---|---|
| all-full same-colour field | horizontal and vertical seams |
| filled gradient triangle | row seams and sparse edge placement |
| one-cell outline/corners/solid box | every local bit and cross-cell movement |
| box over differently coloured grid | horizontal glyph ownership/overpaint |
| moving diagonal | mapping/order and single-pixel continuity |
| multicolour adjacent cells | paint-order ownership defects |

Record terminal name/version, profile font, point size, zoom, DPI, screenshot,
font hashes and command. A screenshot without those facts is useful evidence
but not a reproducible release gate.

## FontPlotter test suite

```bash
cd /path/to/FontPlotter
python3 -m unittest discover -s tests -v
```

Current expected result: **31 tests, all PASS**.

The suite creates Unix-domain sockets. In a restricted sandbox it can fail
every service test with `Operation not permitted`. Rerun in an ordinary user
shell or an approved environment that permits local sockets before recording
a regression.

## FontPlotter basic service

```bash
cd ~/dev/FontPlotter

bin/fp-buffer start --log-level info --log-capacity 4096
bin/fp-buffer create canvas --width 320 --height 96
bin/fp-buffer plot-pixel canvas 13 10 --colour 12ab34ef --depth 42.5
bin/fp-buffer get-pixel canvas 13 10
bin/fp-buffer info canvas
bin/fp-buffer stop
```

`info` reports both width and height. Stopping discards RAM state.

## Visual FontPlotter demonstrations

```bash
cd ~/dev/FontPlotter

./run-linux.sh -4 lab --fps 8
./run-linux.sh -4 asteroids
./run-linux.sh -4 box
demos/run-framebuffer-evidence-presentation.sh
```

The box diagnostic's continuously increasing `Frame` value is a redraw/update
counter, not evidence that a VGR capture is active. Recording requires an
explicit recording command or hotkey in a tool that implements it.

## Backup/restore evidence

```bash
bin/fp-buffer backup-create fred canvas 13 10 22 19 --mode 4
bin/fp-buffer backup-show fred
bin/fp-buffer backup-restore fred --target-x 76 --target-y 28 --merge replace
bin/fp-buffer backup-copy fred fred-copy
bin/fp-buffer backup-move fred-copy fred-archive
bin/fp-buffer backup-export fred "$HOME/fred.json"
bin/fp-buffer backup-delete fred-archive
```

Use `replace` for exact restoration. `plot` and `or` are compositing
operations, not exact restoration aliases.

## VGR inspection and playback

Square repository VGR v1:

```bash
python3 scripts/vgr-info.py recording.vgr
unzip -t recording.vgr

python3 experiments/voyager-grand-tour/voyager_grand_tour.py play -4 \
  recording.vgr --loop --stream
```

For model-view recordings using every row:

```bash
python3 experiments/voyager-grand-tour/voyager_grand_tour.py play -4 \
  voyager-model-view.vgr --no-status --loop --stream
```

Do not `cat` `.vgf` members. They are binary packets. Do not use
`--allow-small-terminal` expecting rescaling; it only allows clipping.

## Git safety and checkpointing

Before any repository mutation:

```bash
git status --short
git diff --check
git diff --stat
git log -8 --oneline --decorate
```

The current working tree contains valuable untracked candidate binaries,
audit JSON, screenshots, PDFs and scripts. Do not use `git clean`, hard reset,
checkout-overwrite or broad deletion. Proposed checkpoint sequence:

1. fonts, build generator, package and Candidate 6 evidence;
2. launchers, Fontconfig and demo routing;
3. Voyager/VGR tools and docs;
4. cross-platform operations/config files;
5. handover package;
6. FontPlotter in its own repository or an explicitly chosen integration.

Review staged files and binary sizes before every commit. Push only after the
user confirms the checkpoint structure.
