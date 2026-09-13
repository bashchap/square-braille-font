# Document register and authority

## Current documents

| Topic | Authoritative document |
|---|---|
| zero-context project handover | this `docs/handover/` package |
| consolidated visual explanation | handover `11-DIAGRAM-ATLAS.md` |
| released 2x4 overview | `README.md`, `docs/ARCHITECTURE.md` |
| Linux 2x4 installation | `docs/QUICKSTART-LINUX.md` |
| macOS 2x4 installation | `docs/QUICKSTART-MACOS.md` |
| Windows 2x4 installation | `docs/QUICKSTART-WINDOWS.md` |
| PUA 4x4 current mapping/status | `docs/PUA-4X4.md` |
| Candidate 6 evidence | `docs/PUA-4X4-CANDIDATE-6-EVIDENCE-v0.6.md` |
| Candidate 6 operator commands | handover `06-OPERATIONS-AND-VALIDATION.md` |
| third-party provenance | `docs/THIRD-PARTY-ASSETS.md` |
| VGR v1 | `docs/VGR-FORMAT.md` |
| FontPlotter current behavior | sibling `FontPlotter/README.md` |
| framebuffer requirements | sibling `FontPlotter/docs/FRAMEBUFFER-REQUIREMENTS.md` |
| framebuffer measured tests | sibling `FontPlotter/docs/FRAMEBUFFER-TEST-RESULTS.md` |
| framebuffer protocol v3 | sibling `FontPlotter/docs/FRAMEBUFFER-SERVICE-POC.md` |
| VGR v2 | sibling `FontPlotter/docs/VGR-V2-FORMAT.md` |

## Historical evidence — retain, do not treat as current guidance

| Document | Historical purpose |
|---|---|
| `docs/PUA-4X4-FONT-GENERATION-EVIDENCE-v0.4.md` | Candidate 3 creation and original release gate |
| `docs/PUA-4X4-FULL-RASTER-AUDIT-v0.4.md` | proof that Candidate 3 violates horizontal colour ownership |
| `docs/PUA-4X4-CANDIDATE-4-EVIDENCE-v0.5.md` | corrected bearings and strict ownership, later row-seam finding |
| `experiments/pua-4x4/output/pdf/PUA-4x4-Mathematical-Mapping-Evidence-v1.0.pdf` | approved mapping proof and catalog |
| `experiments/pua-4x4/output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf` | historical Candidate 3 font-generation report |

Historical reports should receive a prominent superseded note when a current
reader could otherwise mistake them for recommendations. Preserve their
original observations and commands.

## Known stale operational material

At the handover snapshot, `docs/OPERATIONS-QUICKSTART.md`, macOS/Windows
WezTerm PUA configuration and some cross-platform show/install scripts still
name v0.4 Candidate 3. They are accurate for reproducing that preserved
environment but are **not** the current Linux Candidate 6 path.

Do not globally replace the family names without testing. Candidate 6 has been
promoted only as a Linux RC. Update each platform's operational guide and
configuration when that platform has passed fallback, width and raster tests.

## Diagram authority

The Mermaid diagrams in this handover are the current high-level diagrams.
`11-DIAGRAM-ATLAS.md` collects the complete visual set in one place:

- system component/data flow;
- repository/runtime boundaries;
- coordinate conversion;
- encode/decode pipeline;
- rendering diagnostic layers;
- VGR capture/replay sequence;
- depth and two-colour reduction;
- chronological proof chain.

The detailed PDF diagrams remain useful for bit catalogs and worked examples,
but any status or candidate recommendation in an older PDF is superseded by
this register and `docs/PUA-4X4.md`.

## Maintenance rule

When a major gate changes:

1. update `00-CONTEXT-SNAPSHOT.md`;
2. append the decision to `02-CHRONOLOGY-AND-DECISIONS.md`;
3. update the relevant technical file;
4. update `07-STATUS-RISKS-BACKLOG.md`;
5. reclassify superseded documents here;
6. record the new dated validation commands and results;
7. keep historical evidence intact.
