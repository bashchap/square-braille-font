# Current truth snapshot

Snapshot date: **2026-08-20**
Primary user: **tara**
Primary Linux host: **vmfm1 / 192.168.1.15**
Primary Linux project root: **`/home/tara/dev/FontMaker`**
Linux framebuffer project: **`/home/tara/dev/FontPlotter`**

## One-paragraph summary

The project began as a programmatically generated font that replaces round
Braille dots with seamless square subcells. It produced a released 2x4 font
that works as both a normal terminal text font and an eight-subpixel graphics
font. It then evolved into a 4x4, 65,536-pattern two-font experiment, a set of
high-resolution terminal demonstrations, NASA Voyager renderers and indexed
VGR recordings. Rendering limitations led to a separate FontPlotter project:
a RAM-resident, depth-aware framebuffer service with terminal-cell foreground
and background encoding, backups, restore policies, bulk IPC and live PUA 4x4
blitting. The current 4x4 Linux candidate is v0.6 RC1 / Candidate 6. It passes
normal-size MATE Terminal tests but can show horizontal seams at the two
smallest Ctrl-minus zoom levels.

## Current assets

| Asset | Status | Location |
|---|---|---|
| Square Braille Unicode Text Seamless TTF | **Released** | `fonts/current/Square-Braille-Unicode-Text-Seamless.ttf` |
| Square Braille Unicode Text Seamless OTF | **Released** | `fonts/current/Square-Braille-Unicode-Text-Seamless.otf` |
| PUA 4x4 Part 0 Candidate 6 TTF | **Current Linux RC** | `fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part0V06Candidate6.ttf` |
| PUA 4x4 Part 1 Candidate 6 TTF | **Current Linux RC** | `fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part1V06Candidate6.ttf` |
| FontPlotter | **Active POC/engineering system** | sibling `FontPlotter/` tree |
| VGR v1 | **Supported legacy recording** | Square Braille repository Voyager tools |
| VGR v2 | **Current richer recording** | `FontPlotter/docs/VGR-V2-FORMAT.md` |

## Immutable mapping truths

### Square Braille 2x4

- Official Unicode Braille block: `U+2800-U+28FF`.
- Compatibility PUA alias: `U+E000-U+E0FF`.
- The Unicode and PUA characters for the same mask are cmap aliases to one
  glyph.
- A terminal of `C` columns by `R` rows becomes `2C x 4R` virtual pixels.

### PUA 4x4

- A terminal of `C` columns by `R` rows becomes `4C x 4R` virtual pixels.
- Coordinates are zero-based from the top-left.
- Each row is MSB-left:

```text
 3  2  1  0
 7  6  5  4
11 10  9  8
15 14 13 12
```

```text
cell_x  = virtual_x // 4
cell_y  = virtual_y // 4
local_x = virtual_x % 4
local_y = virtual_y % 4
bit     = 4 * local_y + (3 - local_x)
mask   |= 1 << bit
```

```text
mask 0x0000..0x7FFF -> Part 0: U+F0000 + mask
mask 0x8000..0xFFFF -> Part 1: U+100000 + (mask - 0x8000)
```

The full cell is mask `0xFFFF`, codepoint `U+107FFF`. It must remain a normal
foreground glyph. **Do not replace it with a blank plus terminal background,
reverse video or another special-case encoding.**

## Current 4x4 candidate

Candidate 6 derives from Candidate 4's corrected bearings and strict
horizontal ownership:

```text
advance: 500
x ownership: 0..500
vertical guard: -300..900
internal 4x4 boundaries: unchanged
horizontal overfill: 0
```

Only exterior vertical coordinates changed from Candidate 4:
`-200 -> -300` and `800 -> 900`. No x coordinate changed.

SHA-256:

```text
Part 0  2a473fc9fab1d1399fd46a04f85b9ff04a97962500a05d67c9677cb5bfe999af
Part 1  f023c3f4c74b69858b2a8083479589166d11c0562b6afe7261263127eb43dfe0
```

## Current validation baseline

Handover integration revalidated on 2026-08-20:

- released 2x4 TTF and OTF verifiers: PASS;
- PUA 4x4 mapping, packer and current-launcher verifier: PASS;
- Candidate 6 packaged SHA-256 manifest: PASS for both parts;
- all 37 repository Markdown files: PASS local-link audit;
- all seven FontPlotter Markdown files: PASS local-link audit;
- Git whitespace/error check for tracked changes: PASS.

Validated on 2026-08-17 in the macOS workspace:

- released 2x4 TTF: PASS text, Unicode Braille and PUA alias verifier;
- released 2x4 OTF: PASS the same verifier;
- PUA 4x4 demo mapping/packer/launcher verifier: PASS;
- FontPlotter: **31/31 tests PASS** when allowed to create its Unix-domain
  socket.

Validated on Linux `vmfm1` on 2026-08-15:

- Candidate 6 installed byte-identically for the user;
- both PUA ranges have terminal width one;
- Fontconfig selects the correct Part 0 and Part 1 files;
- Pango resolves text plus both parts with zero unknown glyphs;
- FontPlotter suite: **31/31 PASS**;
- normal-size real MATE Terminal box-over-grid and triangle evidence pass.

The same tests fail to start inside a filesystem sandbox that forbids Unix
socket creation with `Operation not permitted`. That is a harness restriction,
not a framebuffer regression.

## Most important current limitation

At normal and enlarged MATE Terminal sizes, Candidate 6 is visually seamless
in the tested full field and triangle. At the two smallest Ctrl-minus zoom
levels, one-pixel horizontal line-box seams can reappear. The user explicitly
accepted this as a minor limitation if necessary. Do not claim universal
seamlessness across arbitrary terminal, DPI, fractional ppem and zoom values.

## Repository state warning

The Square Braille repository is on branch `main` at local HEAD
`a51725bc06fbe75ec80604370745132bdd3a835f`. Its remote `origin/main` is older.
The local tree contains extensive modified and untracked work, including
Candidate 6, Voyager tools, audit evidence and this handover. Preserve it.
Do not reset, clean, checkout over it or discard files. Audit and commit it in
small logical checkpoints before any push.
