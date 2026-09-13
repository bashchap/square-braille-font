#!/usr/bin/env python3
"""Create controlled one-glyph probes for measuring seam overshoot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


def rectangle(x_min: int, y_min: int, x_max: int, y_max: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, y_min))
    pen.lineTo((x_min, y_max))
    pen.lineTo((x_max, y_max))
    pen.lineTo((x_max, y_min))
    pen.closePath()
    return pen.glyph()


def replace_names(font: TTFont, family: str, postscript: str) -> None:
    values = {1: family, 2: "Regular", 3: postscript, 4: family, 5: "Version 0.4-overfill-probe", 6: postscript}
    for record in font["name"].names:
        if record.nameID in values:
            font["name"].setName(values[record.nameID], record.nameID, record.platformID, record.platEncID, record.langID)
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "build-v0.4-candidate.1/PUA4x4Part1V04Candidate.ttf")
    parser.add_argument("--output-dir", type=Path, default=root / "output/audit/fullmask-overfill-probes/fonts")
    parser.add_argument("--overfills", type=int, nargs="+", default=(0, 8, 16, 24, 32, 40, 48, 64, 80, 100))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for overfill in args.overfills:
        font = TTFont(args.source, recalcTimestamp=False)
        cmap = font.getBestCmap()
        name = cmap[0x107FFF]
        font["glyf"][name] = rectangle(-overfill, -200 - overfill, 500 + overfill, 800 + overfill)
        font["hmtx"].metrics[name] = (500, -overfill)
        family = f"PUA 4x4 Fullmask Overfill Probe {overfill:03d}"
        postscript = f"PUA4x4FullmaskOverfillProbe{overfill:03d}-Regular"
        replace_names(font, family, postscript)
        output = args.output_dir / f"PUA4x4FullmaskOverfillProbe{overfill:03d}.ttf"
        font.save(output, reorderTables=True)
        font.close()
        records.append({"overfill_font_units": overfill, "family": family, "file": str(output), "sha256": sha(output)})
    manifest = {
        "audit": "full-mask controlled overfill probe fonts",
        "source": str(args.source),
        "source_sha256": sha(args.source),
        "controlled_change": "only U+107FFF outline and its matching left side bearing",
        "records": records,
    }
    path = args.output_dir.parent / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
