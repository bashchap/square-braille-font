# PUA 4x4 demo suite

This is a parallel 4x4 port of every graphical demonstration found in the
original Square Braille demo collection. The old programs and their assets are
not changed. Every terminal cell rendered here contains an MSB-left 4x4 mask:

```text
bit = 4 * local_y + (3 - local_x)
```

Masks `0x0000..0x7FFF` select **PUA 4x4 Part 0** at
`U+F0000..U+F7FFF`. Masks `0x8000..0xFFFF` select **PUA 4x4 Part 1** at
`U+100000..U+107FFF`.

## Linux quick start

From the repository root:

```bash
cd experiments/pua-4x4/demos4x4
chmod +x run-demo.sh
./run-demo.sh starfield
./run-demo.sh snow
./run-demo.sh defender --once
```

`run-demo.sh` performs the idempotent packaged-v0.6-RC1 installation/runtime
check and opens a MATE Terminal window using the dedicated **PUA 4x4 v0.6
Candidate 6** profile. The demo mathematics and P0/P1 codepoints are unchanged;
only the selected font/profile changed. Run `./run-demo.sh help` for the
complete list and examples.

When already inside a terminal configured with both PUA 4x4 fonts, a demo may
also be run directly:

```bash
python3 starfield.py
python3 defender.py --once
```

The historical v0.3 launcher remains available for controlled comparison:

```bash
PUA4X4_USE_V03=1 ../launch-linux.sh shell
```

The high-detail external-model demos additionally expect these caches in this
directory:

- `enterprise_tos_wire.npz` for `enterprise_wireframe.py`
- `space_ship_wire.npz` for `space_ship_flyby.py`

They are intentionally kept outside Git when their source model licensing or
size makes redistribution inappropriate. The procedural `enterprise_flyby.py`
has no external mesh dependency.

## macOS Apple Silicon quick start

From the repository root, install all three user fonts and invoke any 4x4 demo
through the isolated Candidate 6 fallback launcher:

```sh
./scripts/macos/install-all-user.sh
./scripts/macos/run-demo.sh pua4 catalog
./scripts/macos/run-demo.sh pua4 starfield
./scripts/macos/run-demo.sh pua4 defender --once
```

The full inventory, sizing options, dependencies and verification commands are
in [the complete macOS guide](../../../docs/QUICKSTART-MACOS-ALL-FONTS.md).

## Port inventory

| Command | Program | Purpose |
|---|---|---|
| `geometry` | `geometry_test.py` | solid, checker and moving subpixel proof |
| `snow` | `snow.py` | snow animation |
| `starfield` | `starfield.py` | forward starfield flight |
| `trail` | `trail.py` | interactive cursor-key drawing |
| `triangle` | `triangle.py` | progressive RGB filled triangle |
| `vertical` | `vertical_probe.py` | 4x4 vertical/seam diagnostic |
| `vector` | `vector_tunnel.py` | twisting vector tunnel flight |
| `elite` | `elite_battle.py` | cinematic vector space battle |
| `doom` | `doom_demo.py` | ray-cast corridor sequence |
| `enterprise` | `enterprise_flyby.py` | procedural color 3D fly-around |
| `enterprise-hlr` | `enterprise_wireframe.py` | mesh hidden-line render |
| `spaceship` | `space_ship_flyby.py` | supplied-model action flyby |
| `defender` | `defender.py` | new 120-second gameplay attract mode |

All programs use `pua4x4_backend.py`; vector programs share the 4x4
`FrameBuffer` in `vector_tunnel.py`.
