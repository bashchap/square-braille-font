# Square Braille Unicode Text Seamless

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
- [Windows quick start](docs/QUICKSTART-WINDOWS.md)

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
demos/vector/        Vector tunnel and space demonstrations
demos/3d/            Parametric and external-mesh rendering engines
docs/                Quick starts and engineering record
config/              VROBI PUA mapping
requirements.txt     Python verification and 3D demo dependencies
```

The chronological design and validation history is documented in
[Architecture and history](docs/ARCHITECTURE.md).

## Experimental PUA 4x4 font family

The repository also contains a separate two-font graphics experiment that
turns each terminal cell into a 4×4 virtual-pixel grid. Version 0.3 contains
all 65,536 patterns and implements the explicit MSB-left formula:

```text
bit = 4 * local_y + (3 - local_x)
```

The 4×4 fonts do not replace the released Square Braille font. See the
[PUA 4x4 guide](docs/PUA-4X4.md) for the ranges, installation, demos,
verification evidence and complete specification.

## External assets and licensing

Original project code is released under the [MIT License](LICENSE). Normal text
outlines derive from DejaVu Sans Mono and remain subject to the included
[Bitstream Vera / DejaVu license](LICENSE-DejaVu.txt).

Third-party spacecraft meshes and derived geometry caches are deliberately not
included. See [Third-party assets](docs/THIRD-PARTY-ASSETS.md).
