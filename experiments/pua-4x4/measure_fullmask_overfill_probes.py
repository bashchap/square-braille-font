#!/usr/bin/env python3
"""Measure point-size seams for the controlled full-mask probe fonts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=root / "output/audit/fullmask-overfill-probes/manifest.json")
    parser.add_argument("--output-dir", type=Path, default=root / "output/audit/fullmask-overfill-probes/rasters")
    parser.add_argument("--output", type=Path, default=root / "output/audit/fullmask-overfill-probes/measurements.json")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    field = "\n".join(chr(0x107FFF) * 80 for _ in range(20))
    results = []
    for record in manifest["records"]:
        overfill = record["overfill_font_units"]
        sizes = []
        for size in (8, 9, 10, 11, 12, 13, 14, 16, 18, 20):
            path = args.output_dir / f"overfill-{overfill:03d}-{size:02d}pt-96dpi.png"
            subprocess.run([
                "pango-view", "--no-display", "--dpi=96",
                f"--font={record['family']} {size}",
                "--foreground=#ffffff", "--background=#000000",
                "--margin=0", "--spacing=0", "--line-spacing=1",
                "--text=" + field, "--output=" + str(path),
            ], check=True)
            image = Image.open(path).convert("RGB")
            black = sum(pixel == (0, 0, 0) for pixel in image.getdata())
            nonwhite = sum(pixel != (255, 255, 255) for pixel in image.getdata())
            sizes.append({
                "size_points": size, "dpi": 96, "dimensions": list(image.size),
                "black_pixels": black, "nonwhite_pixels": nonwhite,
                "status": "PASS" if black == 0 and nonwhite == 0 else "SEAM",
                "image": str(path),
            })
        results.append({**record, "sizes": sizes, "all_sizes_solid_white": all(item["status"] == "PASS" for item in sizes)})
    report = {
        "audit": "full-mask overshoot threshold at 8..20 point and 96 DPI",
        "expectation": "zero black and zero nonwhite pixels inside the generated field",
        "records": results,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for record in results:
        print(record["overfill_font_units"], record["all_sizes_solid_white"], [(x["size_points"], x["nonwhite_pixels"]) for x in record["sizes"]])
    print(args.output)


if __name__ == "__main__":
    main()
