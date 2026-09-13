#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${PUA4X4_RC1_PACKAGE_DIR:-$SCRIPT_DIR/../../fonts/candidates/pua-4x4-v0.4-rc1}"
if [[ ! -f "$PACKAGE_DIR/PUA4x4Part0V04Candidate3.ttf" \
   && -f "$SCRIPT_DIR/build-v0.4-candidate.3-seamguard100/PUA4x4Part0V04Candidate3.ttf" ]]; then
    PACKAGE_DIR="$SCRIPT_DIR/build-v0.4-candidate.3-seamguard100"
fi
test -f "$PACKAGE_DIR/PUA4x4Part0V04Candidate3.ttf"
test -f "$PACKAGE_DIR/PUA4x4Part1V04Candidate3.ttf"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"

install -d "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part0V04Candidate3.ttf" "$FONT_DIR/"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part1V04Candidate3.ttf" "$FONT_DIR/"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-v04-candidate3.conf" "$CONFIG_DIR/"
fc-cache -f "$FONT_DIR"
cmp "$PACKAGE_DIR/PUA4x4Part0V04Candidate3.ttf" "$FONT_DIR/PUA4x4Part0V04Candidate3.ttf"
cmp "$PACKAGE_DIR/PUA4x4Part1V04Candidate3.ttf" "$FONT_DIR/PUA4x4Part1V04Candidate3.ttf"
echo "Installed candidate.3 side-by-side: $FONT_DIR/PUA4x4Part0V04Candidate3.ttf"
echo "Installed candidate.3 side-by-side: $FONT_DIR/PUA4x4Part1V04Candidate3.ttf"
echo "Configured isolated alias: PUA 4x4 v0.4 Candidate 3"
echo "Source package: $PACKAGE_DIR"
