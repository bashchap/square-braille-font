#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${PUA4X4_CANDIDATE6_DIR:-$SCRIPT_DIR/../../fonts/candidates/pua-4x4-v0.6-rc1}"
if [[ ! -f "$PACKAGE_DIR/PUA4x4Part0V06Candidate6.ttf" \
   && -f "$SCRIPT_DIR/build-v0.6-candidate.6-vertical-guard/PUA4x4Part0V06Candidate6.ttf" ]]; then
    PACKAGE_DIR="$SCRIPT_DIR/build-v0.6-candidate.6-vertical-guard"
fi
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"

test -f "$PACKAGE_DIR/PUA4x4Part0V06Candidate6.ttf"
test -f "$PACKAGE_DIR/PUA4x4Part1V06Candidate6.ttf"
install -d "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part0V06Candidate6.ttf" "$FONT_DIR/"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part1V06Candidate6.ttf" "$FONT_DIR/"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-v06-candidate6.conf" "$CONFIG_DIR/"
fc-cache -f "$FONT_DIR"
cmp "$PACKAGE_DIR/PUA4x4Part0V06Candidate6.ttf" "$FONT_DIR/PUA4x4Part0V06Candidate6.ttf"
cmp "$PACKAGE_DIR/PUA4x4Part1V06Candidate6.ttf" "$FONT_DIR/PUA4x4Part1V06Candidate6.ttf"
echo "Installed side-by-side: $FONT_DIR/PUA4x4Part0V06Candidate6.ttf"
echo "Installed side-by-side: $FONT_DIR/PUA4x4Part1V06Candidate6.ttf"
echo "Configured isolated alias: PUA 4x4 v0.6 Candidate 6"
