# PUA 4×4 v0.4 release candidate 1

This directory packages the selected **candidate.3** binaries from the v0.4
font-generation investigation. They are intentionally separate from the
installed v0.3 experiment and from the released Square Braille fonts.

## Files

```text
PUA4x4Part0V04Candidate3.ttf
SHA-256 94847138178994d016d3a0e315be0aa10604c1ea85e01b6d98eb8f41421ac9d8

PUA4x4Part1V04Candidate3.ttf
SHA-256 a979a9568dbe5c0b90bb54eb6bc0e4a70caf536bd4c2e791d589796a984f0ec1
```

`manifest.json` records the family names, codepoint ranges, mapping formula,
source-font identities and the precisely declared seam-guard transform.

## Status

The candidate passes:

- the approved exhaustive 65,536-mask mathematical oracle;
- exhaustive cmap, outline, mask, horizontal-metric and effective-placement
  verification;
- exact FreeType raster checks at integer 40- and 80-pixel em sizes;
- Linux Fontconfig, `wcwidth` and Pango selection checks;
- full-mask Pango fields at 8–20 pt and 96 DPI;
- the paired 14 pt MATE Terminal triangle boundary analysis; and
- a byte-identical independent Linux rebuild.

It is not yet promoted to the normal `PUA 4x4` alias. Use the isolated
candidate installer and launcher in `experiments/pua-4x4/`.

The unversioned launcher and the complete demo suite now select this isolated
candidate profile by default:

```sh
cd experiments/pua-4x4
./launch-linux.sh demo
cd demos4x4
./run-demo.sh starfield
```

Use `PUA4X4_USE_V03=1` with `launch-linux.sh` to reproduce the preserved v0.3
environment.

## Declared rendering guard

The mathematical mask and codepoint mapping are unchanged. The core 4×4
boundaries also remain unchanged. Only selected outline points on the exterior
cell edges are moved 100 font units outward:

```text
x = 0    -> -100       x = 500 -> 600
y = -200 -> -300       y = 800 -> 900
```

This is deliberate raster overlap. It eliminates the tested fractional-pixel
cell seams, but an isolated left- or right-edge pixel can paint into a
neighbouring terminal cell. The complete evidence report quantifies that
tradeoff rather than treating it as part of the mathematical mapping.

See `docs/PUA-4X4-FONT-GENERATION-EVIDENCE-v0.4.md` and
`experiments/pua-4x4/output/pdf/PUA-4x4-Font-Generation-Evidence-v0.4-RC1.pdf`.
