# PUA 4x4 experimental font family

PUA 4x4 v0.3 represents every possible 4×4 bitmap in one terminal character
cell. It is a separate experiment and does not modify the released Square
Braille fonts.

## Mapping

Virtual coordinates increase left-to-right and top-to-bottom. Inside a cell:

```text
 3  2  1  0
 7  6  5  4
11 10  9  8
15 14 13 12
```

For virtual pixel `(x, y)`:

```text
cell_x  = x // 4
cell_y  = y // 4
local_x = x % 4
local_y = y % 4
bit     = 4 * local_y + (3 - local_x)
value   = 1 << bit
```

Masks `0000–7FFF` map to Part 0 at `U+F0000–U+F7FFF`. Masks `8000–FFFF`
map to Part 1 at `U+100000–U+107FFF` after subtracting `0x8000` for the Part 1
offset.

## Linux quick start

```sh
cd experiments/pua-4x4
./install-linux-user.sh
python3 verify_linux_runtime.py
./launch-linux.sh demo
```

The installer registers both graphics fonts for the current user and creates
the `PUA 4x4` Fontconfig alias with the released Square Braille text face as
the ordinary-text fallback.

Run a demonstration with:

```sh
cd experiments/pua-4x4/demos4x4
./run-demo.sh trail
./run-demo.sh starfield
./run-demo.sh defender --once
```

The interactive glyph editor shows every coordinate, bit, mask and codepoint:

```sh
./run-demo.sh editor
```

## Verification

```sh
cd experiments/pua-4x4
python3 verify_pua4x4.py build-v0.3
python3 verify_equal_pixel_geometry.py build-v0.3
python3 audit_pua4x4_chain.py build-v0.3 --edge-overfill 0
python3 verify_trail_steps.py
python3 demos4x4/verify_demos4x4.py
```

The verified v0.3 SHA-256 identities are:

```text
PUA4x4Part0.ttf  b34587617903d8115d8df788b6430b172c614d8fa9d1689eb403a5c8d26f8c6d
PUA4x4Part1.ttf  ccfad9f530ceda3f33791aec877b81b81472604e68c5e1633c50bb6d2da2681a
```

Version 0.2 used the opposite LSB-left convention and is preserved in
`experiments/pua-4x4/legacy/v0.2-lsb-left/`.

## Specifications

- [Educational mapping and renderer guide](../experiments/pua-4x4/output/pdf/PUA-4x4-Mapping-Specification-v0.8.pdf)
- [Exhaustive 65,536-glyph catalog](../experiments/pua-4x4/output/pdf/PUA-4x4-Full-Character-Specification-v0.2.pdf)
- [Combined 276-page specification](../experiments/pua-4x4/output/pdf/PUA-4x4-Complete-Mapping-and-Glyph-Catalog-v0.8.pdf)
- [Independent mapping-chain evidence](../experiments/pua-4x4/output/pdf/PUA-4x4-Mapping-Chain-MSB-Left-Evidence-v1.2.pdf)
