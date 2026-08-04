#!/usr/bin/env python3
"""Render solid PUA 4x4 fields at small sizes and reject raster gaps."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from pua4x4 import mask_to_codepoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="8,9,10,11,12,13,14,16,18,20")
    parser.add_argument("--font", default="PUA 4x4",
                        help="Fontconfig family or alias (default: PUA 4x4)")
    parser.add_argument("--columns", type=int, default=64)
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",")]
    field = "\n".join(
        chr(mask_to_codepoint(0xFFFF)) * args.columns for _ in range(args.rows)
    )

    temporary = None
    if args.output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="pua4x4-seams-")
        output_dir = Path(temporary.name)
    else:
        output_dir = args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    for size in sizes:
        image_path = output_dir / ("solid-%02d.png" % size)
        subprocess.run(
            [
                "pango-view",
                "--no-display",
                "--pixels",
                "--font=%s %d" % (args.font, size),
                "--foreground=#ffffff",
                "--background=#000000",
                "--margin=0",
                "--spacing=0",
                "--line-spacing=1",
                "--text=" + field,
                "--output=" + str(image_path),
            ],
            check=True,
        )
        image = Image.open(image_path).convert("RGB")
        black = sum(1 for pixel in image.getdata() if pixel == (0, 0, 0))
        assert black == 0, "%d px: found %d black seam pixels" % (size, black)
        print("PASS %2d px: %dx%d solid raster, zero seam pixels" % (size, *image.size))

    if temporary is not None:
        temporary.cleanup()


if __name__ == "__main__":
    main()
