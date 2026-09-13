# Verified status, risks and backlog

## Status dashboard

| Area | Current state | Confidence |
|---|---|---|
| Square Braille 2x4 font | released TTF/OTF, text + Unicode + PUA | verified |
| Linux 2x4 terminal use | established user installer/profile and demos | verified historically |
| macOS 2x4 use | 100-unit guard verified down to 8 pt in tested Terminal.app setup | verified historically |
| Windows 2x4 use | per-user installer and profile guidance | documented; needs fresh acceptance pass |
| PUA 4x4 mathematics | MSB-left formula and P0/P1 split | verified exhaustively |
| PUA 4x4 Candidate 6 | current Linux RC | verified normal-size Linux range |
| Candidate 6 extreme zoom | horizontal seams at two smallest MATE zooms | known limitation |
| Candidate 6 macOS/Windows | not a validated release | pending |
| Original 2x4 demos | extensive runnable suite | implemented |
| 4x4 demo ports | mapping/packer/launcher verifier passes | verified |
| NASA Voyager renderer | model provenance, scene, HLR/fill/wire, capture/player | implemented |
| VGR v1 | indexed foreground-only recording | implemented |
| VGR v2 | foreground/background/flags recording in FontPlotter | verified by tests |
| FontPlotter service | protocol v3 feature set | 31/31 local and Linux tests |
| FontPlotter Windows | Unix-specific transport prevents current use | pending |
| GitHub publication | remote exists; current large local delta unpushed | urgent repository task |

## Known risks

### R1 — dirty, uncheckpointed repository

The current Square Braille tree contains a large mix of modified and untracked
source, fonts, binaries, evidence and documentation. A reset/clean could erase
weeks of work. This is the highest operational risk.

Mitigation: inventory, classify, test and commit in small logical units before
changing branches or pulling divergent work.

### R2 — terminal-specific raster behavior

Seams depend on font size, zoom, DPI, hinting and terminal line-box rounding.
A font-level change that helps one size can overpaint neighbours or fail at
another.

Mitigation: retain strict horizontal ownership, use a platform/size matrix and
state support boundaries rather than claiming universal seamlessness.

### R3 — stale cross-platform 4x4 configuration

Some macOS/Windows WezTerm configs and install/show scripts still refer to
Candidate 3. Candidate 6 is Linux-verified, but simply changing names would
create an untested cross-platform claim.

Mitigation: update each platform in its own acceptance task with family-name,
fallback, width and raster proofs.

### R4 — duplicated code and assets

Voyager and VGR logic exists in both the Square repository and FontPlotter,
including legacy modules. Divergence can make documentation describe the
wrong implementation.

Mitigation: declare one implementation of record per format/version and add
cross-reader compatibility tests before consolidation.

### R5 — terminology drift

Earlier documents use cursor cell, canvas cell, terminal coordinate, ANSI
coordinate and virtual pixel inconsistently.

Mitigation: public drawing APIs use zero-based virtual pixels; internal cells
are zero-based; ANSI row/column are one-based output metadata only.

### R6 — test environment false failures

Sandboxed environments can forbid Unix socket creation, making every service
test fail at setup.

Mitigation: inspect the first error. If it is `Operation not permitted` during
socket startup, rerun outside the sandbox before diagnosing product code.

## Ordered next actions

### Gate 1 — preservation and publication

1. Produce a complete file inventory and classify source, generated binary,
   evidence, local-only asset and accidental output.
2. Check large files and GitHub size constraints.
3. Commit Candidate 6 and its evidence separately from unrelated Voyager and
   FontPlotter work.
4. Decide whether FontPlotter becomes its own repository, a submodule or a
   maintained subdirectory.
5. Push only after reviewing the commit graph and user approval.

### Gate 2 — Candidate 6 release matrix

1. Automate the full field, sparse corners, diagonals, multicolour adjacency,
   box/grid and triangle test matrix.
2. Record MATE Terminal version, font sizes and zoom boundaries.
3. Re-run Candidate 6 on macOS with explicit P0/P1 fallback.
4. Re-run on Windows with explicit fallback.
5. Promote beyond Linux RC only if the evidence supports it.

### Gate 3 — documentation reconciliation

1. Update `docs/OPERATIONS-QUICKSTART.md` only as each Candidate 6 platform is
   validated. It currently contains Candidate 3 cross-platform instructions.
2. Keep v0.4/v0.5 audit documents historical and add superseded banners rather
   than rewriting their observations.
3. Generate a fresh comprehensive specification PDF from the approved Markdown
   only after its formulas and support claims stabilize.

### Gate 4 — FontPlotter core

1. Define and implement explicit framebuffer save/load format.
2. Add named FIFO block queues and separate them conceptually from reusable
   backups.
3. Add bounded undo/redo journals.
4. Add remaining drawing primitives with depth interpolation and clipping
   policy.
5. Generalize viewport extraction and arbitrary terminal destination blits.
6. Add delta rendering and instrument bytes/runs/write calls.
7. Add multi-client locking, ordering and transaction semantics.
8. Add real group authorization tests and a Windows transport adapter.

### Gate 5 — requested diagnostics not yet complete

- Scrollable framebuffer inspector with arrow and modified-arrow navigation.
- Per-selected-cell display of every virtual pixel and encoded terminal state.
- Per-frame and cumulative PUA codepoint-use census.
- Hotkey to dump codepoint/glyph counts and complete framebuffer state.
- Clarified redraw counters versus actual recording counters in all dashboards.

## Definition of done for a future change

A change is not done merely because code runs. It needs:

1. stated invariant and expected result;
2. unit or mathematical proof where applicable;
3. mapping/font audit where applicable;
4. real terminal test for visual claims;
5. retained evidence with environment and hashes;
6. updated current docs and historical status labels;
7. preserved previous candidate;
8. clean diff and reproducible commands.
