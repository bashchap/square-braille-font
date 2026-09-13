#!/usr/bin/env python3
"""Build temporary Part-1 vertical-metric probes from Candidate 4."""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont


def replace_names(font: TTFont, family: str, postscript: str, units: int) -> None:
    values = {
        1: family,
        2: "Regular",
        3: f"{postscript};graphics-metric-probe-{units}",
        4: family,
        5: f"Graphics metric probe {units}",
        6: postscript,
        16: family,
        17: "Regular",
    }
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)


def build(source: Path, output_dir: Path, units: int) -> Path:
    family = f"PUA 4x4 Graphics Metric Probe {units}"
    postscript = f"PUA4x4GraphicsMetricProbe{units}-Regular"
    output = output_dir / f"PUA4x4GraphicsMetricProbe{units}.ttf"
    font = TTFont(source, recalcBBoxes=False, recalcTimestamp=False)
    ascent = round(units * 0.8)
    descent = ascent - units
    font["hhea"].ascent = ascent
    font["hhea"].descent = descent
    font["hhea"].lineGap = 0
    os2 = font["OS/2"]
    os2.sTypoAscender = ascent
    os2.sTypoDescender = descent
    os2.sTypoLineGap = 0
    os2.usWinAscent = ascent
    os2.usWinDescent = -descent
    replace_names(font, family, postscript, units)
    output_dir.mkdir(parents=True, exist_ok=True)
    font.save(output, reorderTables=True)
    font.close()
    return output


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path,
        default=root / "build-v0.5-candidate.4-strict" /
        "PUA4x4Part1V05Candidate4.ttf",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "output" / "metric-probes",
    )
    parser.add_argument(
        "--units", type=int, nargs="+",
        default=[999, 995, 990, 980, 960, 940, 920],
    )
    args = parser.parse_args()
    for units in args.units:
        print(build(args.source, args.output_dir, units))


if __name__ == "__main__":
    main()
