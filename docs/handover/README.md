# Square Braille / PUA 4x4 / FontPlotter handover

This directory is the authoritative zero-context handover package for the
terminal-graphics project developed with Tara. It is written for a new human
or AI collaborator who has no access to the original conversation.

Snapshot date: **2026-08-20**. Validation dates are recorded separately so a
future reader can distinguish documentation time from evidence time.

## Read in this order

1. [Current truth snapshot](00-CONTEXT-SNAPSHOT.md) — what exists and what is
   currently recommended.
2. [Vision and priorities](01-VISION-AND-PRIORITIES.md) — the user's intent and
   non-negotiable rules.
3. [Chronology and decisions](02-CHRONOLOGY-AND-DECISIONS.md) — how the project
   reached its current state and why earlier approaches were rejected.
4. [Architecture and data flow](03-ARCHITECTURE-AND-DATA-FLOW.md) — components,
   coordinate systems and the terminal rendering chain.
5. [Font specifications](04-FONT-SPECIFICATIONS.md) — exact 2x4 and 4x4
   mappings, metrics and packages.
6. [Rendering, framebuffer and VGR](05-RENDERING-FRAMEBUFFER-VGR.md) — depth,
   two-colour cells, RAM service, backup/restore and recordings.
7. [Operations and validation](06-OPERATIONS-AND-VALIDATION.md) — reproducible
   commands and current evidence.
8. [Status, risks and backlog](07-STATUS-RISKS-BACKLOG.md) — completed work,
   known limitations and ordered next actions.
9. [AI operating protocol](08-AI-OPERATING-PROTOCOL.md) — how to continue
   without repeating previous mistakes.
10. [Repository map](09-REPOSITORY-MAP.md) and
    [document register](10-DOCUMENT-REGISTER.md) — where everything lives and
    which documents are current or historical.
11. [Diagram atlas](11-DIAGRAM-ATLAS.md) — the complete visual summary of the
    evolution, mappings, runtime and next proof gates.

## Scope

The handover covers two working trees:

```text
github/square-braille-font/   Fonts, installers, original demonstrations,
                              PUA 4x4 experiments and Voyager tools
FontPlotter/                   RAM framebuffer service, two-colour/depth
                              renderer, VGR v2 and visual diagnostics
```

The Square Braille repository has a Git remote at
`https://github.com/bashchap/square-braille-font.git`. At the snapshot date,
substantial Candidate 6 and documentation work exists only in the dirty local
working tree and has not been committed or pushed. `FontPlotter` is a sibling
working tree rather than a committed subdirectory of that repository.

## Confidence labels used here

- **Released** — packaged, documented and intended for normal use.
- **Current Linux RC** — current candidate, verified on the designated Linux
  host, but not a final cross-platform release.
- **Verified** — backed by a named automated test, audit, hash or retained
  visual evidence.
- **Observed** — manually seen in a specified terminal environment.
- **Pending** — requested or architecturally planned, but not yet proved.
- **Historical** — retained to reproduce a decision; not current guidance.

Do not silently promote an observation to a verified claim. Terminal rendering
has repeatedly differed from raw outline, FreeType and Pango measurements.
