# Square Braille Unicode Text Seamless

> **Maintainer/AI handover:** begin with [HANDOVER.md](HANDOVER.md). It records
> the complete project history, current Candidate 6 status, sibling FontPlotter
> architecture, verified evidence, known limitations and ordered next work as
> of 2026-08-20.

A programmatically generated monospaced terminal font that turns the official
Unicode Braille Patterns block into a seamless 2×4 square-pixel canvas.

The recommended font contains:

- normal text suitable for an interactive shell;
- square Braille at official Unicode `U+2800–U+28FF`;
- identical compatibility aliases at PUA `U+E000–U+E0FF`;
- a 500-unit character advance and 1000-unit em;
- 100 units of controlled exterior overfill to suppress raster seams,
  including small-point-size CoreText rendering on macOS.

![Unicode and PUA mappings rendered with the current font](assets/unicode-braille-proof.png)

## Quick start

Download or clone the repository, then follow the guide for your system:

- [Linux quick start](docs/QUICKSTART-LINUX.md)
- [macOS quick start](docs/QUICKSTART-MACOS.md)
- [macOS Apple Silicon: all fonts and demonstrations](docs/QUICKSTART-MACOS-ALL-FONTS.md)
- [Windows quick start](docs/QUICKSTART-WINDOWS.md)
- [Complete cross-platform operations guide](docs/OPERATIONS-QUICKSTART.md)

macOS users can run the complete Python and ANSI demonstration suite natively;
see the [native macOS demonstration guide](docs/DEMOS-MACOS.md).

The recommended file is:

```text
fonts/current/Square-Braille-Unicode-Text-Seamless.ttf
```

Install either the TTF or OTF, not both. TTF is recommended for terminal use.

## Verify the build

With Python and FontTools installed:

```sh
python3 src/font/verify_unicode_braille.py \
  fonts/current/Square-Braille-Unicode-Text-Seamless.ttf \
  fonts/current/Square-Braille-Unicode-Text-Seamless.otf
```

The verifier proves that every official Braille codepoint and its PUA partner
map to the same glyph, and checks the text and terminal metrics.

## Repository map

```text
fonts/current/       Recommended Unicode + PUA font
fonts/legacy/        Preserved earlier font generations
src/font/            Generators and verification programs
scripts/             User-level installers and terminal setup
demos/basic/         Snow, starfield, trail, triangle and probes
demos/seasonal/      Layered Christmas snow for Square 2x4 and PUA 4x4
demos/vector/        Vector tunnel and space demonstrations
demos/3d/            Parametric and external-mesh rendering engines
experiments/voyager-grand-tour/ Dual-font NASA Voyager renderer, VGR recorder/player
experiments/voyager-model-viewer/ Interactive PUA 4x4 NASA Voyager viewer/recorder
docs/                Quick starts and engineering record
config/              VROBI PUA mapping
requirements.txt     Python verification and 3D demo dependencies
```

The chronological design and validation history is documented in
[Architecture and history](docs/ARCHITECTURE.md).

The broader evolution from the released 2×4 font through PUA 4×4, Voyager,
VGR and the RAM framebuffer service is documented in the
[zero-context handover package](docs/handover/README.md).

The indexed recording container is documented byte-for-byte in the
[VGR v1 format reference](docs/VGR-FORMAT.md).

## Experimental PUA 4x4 font family

The repository also contains a separate two-font graphics experiment that
turns each terminal cell into a 4×4 virtual-pixel grid. It contains all 65,536
patterns and implements the explicit MSB-left formula:

```text
bit = 4 * local_y + (3 - local_x)
```

The preserved v0.3 build has a now-proven TrueType bearing defect. The packaged
v0.6 RC1 / Candidate 6 retains the corrected MSB-left mapping and strict
horizontal ownership, and adds a vertical-only guard for normal-size terminal
continuity. It does not substitute terminal background colour or reverse
video. The two smallest MATE Terminal Ctrl-minus zoom levels remain a documented
limitation. The 4×4 fonts do not replace the released Square Braille font. See
the [PUA 4x4 guide](docs/PUA-4X4.md) for the ranges, installation, demos,
expected-versus-observed verification evidence and complete specification.

## External assets and licensing

Original project code is released under the [MIT License](LICENSE). Normal text
outlines derive from DejaVu Sans Mono and remain subject to the included
[Bitstream Vera / DejaVu license](LICENSE-DejaVu.txt).

User-supplied and third-party commercial spacecraft meshes remain deliberately
excluded. The Voyager Grand Tour includes a compact cache derived from NASA's
official VTAD Voyager model, with source URL, checksum and credit recorded in
its [asset documentation](experiments/voyager-grand-tour/assets/README.md).
See also [Third-party assets](docs/THIRD-PARTY-ASSETS.md).
