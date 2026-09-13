# Repository and artifact map

## Workspace-level layout

```text
i-want-you-to-create-me/
├── github/square-braille-font/   primary Git repository
├── FontPlotter/                  active framebuffer/rendering working tree
├── outputs/                      exported specimens and earlier deliverables
└── work/                         conversion/intermediate historical work
```

Treat `github/square-braille-font` and `FontPlotter` as authoritative working
trees. `outputs/` and `work/` contain valuable provenance and historical
artifacts, but should not override current source or documentation.

## Square Braille repository

```text
square-braille-font/
├── HANDOVER.md                   handover entry point
├── README.md                     public project entry point
├── LICENSE                       MIT for original code
├── LICENSE-DejaVu.txt            text-outline license
├── fonts/
│   ├── current/                  released 2x4 TTF/OTF
│   ├── candidates/               side-by-side 4x4 candidates
│   └── legacy/                   preserved 2x4 generations
├── src/font/                     2x4 generators and verifiers
├── scripts/                      per-user installers and catalog tools
├── config/                       mappings and terminal configurations
├── demos/
│   ├── basic/                    snow, starfield, trail, triangle, probes
│   ├── vector/                   tunnel, Elite-like and vector demos
│   └── 3d/                       mesh/procedural renderers and ANSI replay
├── experiments/
│   ├── pua-4x4/                  4x4 generators, candidates, audits, demos
│   ├── voyager-grand-tour/       NASA scene, capture dashboard, VGR v1 player
│   └── voyager-model-viewer/     interactive model viewer/recorder
└── docs/
    ├── handover/                 this package
    ├── QUICKSTART-*.md           platform-specific released-font guides
    ├── PUA-4X4*.md               specification and historical audits
    ├── VGR-FORMAT.md             VGR v1 format
    └── THIRD-PARTY-ASSETS.md     provenance/licensing boundaries
```

### PUA 4x4 evidence hierarchy

```text
experiments/pua-4x4/
├── build-v0.6-candidate.6-vertical-guard/  generated Candidate 6 build
├── evidence/                               real-terminal screenshots
├── output/audit/                           JSON, CSV, raster and runtime audit
├── output/pdf/                             generated specifications/reports
├── legacy/                                 rejected/superseded builds
├── demos4x4/                               renderer backend and demos
├── make_v06_candidate6_vertical_guard.py   Candidate 6 derivation
├── install-linux-v06-candidate6.sh         user-only install
└── launch-linux-v06-candidate6.sh          isolated runtime/profile
```

Packaged fonts live under `fonts/candidates`, not only under build directories.
Build directories are reproducibility evidence; candidate packages are the
operator assets.

## FontPlotter tree

```text
FontPlotter/
├── README.md
├── bin/fp-buffer                  CLI entry point
├── fontplotter/
│   ├── framebuffer_service.py     service, protocol, planes, backups
│   ├── renderer.py                terminal cell encoding
│   ├── two_colour.py              depth/two-colour reduction
│   ├── vgr.py                     VGR v2 packet/archive support
│   ├── dashboard.py               capture dashboard and PUA graphs
│   ├── scene.py                   Voyager scenes
│   └── legacy_*                   preserved original implementations
├── demos/
│   ├── framebuffer-evidence-presentation.py
│   ├── framebuffer-visual-lab.py
│   ├── framebuffer-asteroids.py
│   └── framebuffer-box-diagnostic.py
├── docs/
│   ├── FRAMEBUFFER-REQUIREMENTS.md
│   ├── FRAMEBUFFER-TEST-PLAN.md
│   ├── FRAMEBUFFER-TEST-RESULTS.md
│   ├── FRAMEBUFFER-SERVICE-POC.md
│   └── VGR-V2-FORMAT.md
├── output/audit/framebuffer/      retained Linux/macOS JSON evidence
├── tests/                         31-test current suite
├── tools/                         benchmark/evidence/report helpers
└── fonts/                         isolated runtime copies of active fonts
```

## External model assets

- NASA Voyager model: compact derived cache is distributable with documented
  source, credit and checksum.
- Third-party Enterprise/spacecraft models: do not assume redistribution is
  allowed. Commercial/user-supplied meshes are deliberately excluded from the
  public repository.
- Model attribution text is metadata/documentation, not intended to be drawn
  into terminal scene frames.

## Generated versus authored files

Before committing, classify files:

| Class | Typical examples | Policy |
|---|---|---|
| authored source | generators, verifiers, renderers, Markdown | commit |
| release binary | current/candidate TTF and checksum | commit deliberately |
| reproducibility manifest | JSON derivation manifest | commit |
| evidence | compact JSON/CSV and selected screenshots | commit when it supports a claim |
| generated report | PDF/specification | commit only if public deliverable |
| local capture | large `.vgr`, terminal dumps | normally exclude |
| third-party source mesh | `.rar`, `.3ds`, commercial OBJ | exclude unless license permits |
| runtime cache | `__pycache__`, temporary render cache | exclude |

## Remote and branch state

```text
remote: https://github.com/bashchap/square-braille-font.git
branch: main
snapshot HEAD: a51725bc06fbe75ec80604370745132bdd3a835f
origin/main at inventory time: 05edb26
```

The local working tree contains later work that is not represented by that
commit ID. The handover snapshot therefore describes the filesystem state as
well as the Git history.
