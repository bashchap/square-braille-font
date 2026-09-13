#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build-v0.4-candidate.2-hinted"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"

install -d "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$BUILD_DIR/PUA4x4Part0V04Candidate2.ttf" "$FONT_DIR/"
install -m 0644 "$BUILD_DIR/PUA4x4Part1V04Candidate2.ttf" "$FONT_DIR/"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-v04-candidate2.conf" "$CONFIG_DIR/"
fc-cache -f "$FONT_DIR"

cmp "$BUILD_DIR/PUA4x4Part0V04Candidate2.ttf" "$FONT_DIR/PUA4x4Part0V04Candidate2.ttf"
cmp "$BUILD_DIR/PUA4x4Part1V04Candidate2.ttf" "$FONT_DIR/PUA4x4Part1V04Candidate2.ttf"
echo "Installed candidate.2 side-by-side: $FONT_DIR/PUA4x4Part0V04Candidate2.ttf"
echo "Installed candidate.2 side-by-side: $FONT_DIR/PUA4x4Part1V04Candidate2.ttf"
echo "Configured isolated alias: PUA 4x4 v0.4 Candidate 2"
