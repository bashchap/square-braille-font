#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="${PUA4X4_CANDIDATE4_DIR:-$SCRIPT_DIR/../../fonts/candidates/pua-4x4-v0.5-rc1}"
if [[ ! -f "$PACKAGE_DIR/PUA4x4Part0V05Candidate4.ttf" \
   && -f "$SCRIPT_DIR/build-v0.5-candidate.4-strict/PUA4x4Part0V05Candidate4.ttf" ]]; then
    PACKAGE_DIR="$SCRIPT_DIR/build-v0.5-candidate.4-strict"
fi
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"

test -f "$PACKAGE_DIR/PUA4x4Part0V05Candidate4.ttf"
test -f "$PACKAGE_DIR/PUA4x4Part1V05Candidate4.ttf"
install -d "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part0V05Candidate4.ttf" "$FONT_DIR/"
install -m 0644 "$PACKAGE_DIR/PUA4x4Part1V05Candidate4.ttf" "$FONT_DIR/"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-v05-candidate4.conf" "$CONFIG_DIR/"
fc-cache -f "$FONT_DIR"
cmp "$PACKAGE_DIR/PUA4x4Part0V05Candidate4.ttf" "$FONT_DIR/PUA4x4Part0V05Candidate4.ttf"
cmp "$PACKAGE_DIR/PUA4x4Part1V05Candidate4.ttf" "$FONT_DIR/PUA4x4Part1V05Candidate4.ttf"
echo "Installed side-by-side: $FONT_DIR/PUA4x4Part0V05Candidate4.ttf"
echo "Installed side-by-side: $FONT_DIR/PUA4x4Part1V05Candidate4.ttf"
echo "Configured isolated alias: PUA 4x4 v0.5 Candidate 4"
