#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_DIR="$SCRIPT_DIR/build-v0.4-candidate.1"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"

for command_name in fc-cache fc-match; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

for font_name in PUA4x4Part0V04Candidate.ttf PUA4x4Part1V04Candidate.ttf; do
    test -f "$BUILD_DIR/$font_name" || {
        echo "Missing isolated candidate: $BUILD_DIR/$font_name" >&2
        exit 1
    }
done

mkdir -p "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$BUILD_DIR/PUA4x4Part0V04Candidate.ttf" \
    "$FONT_DIR/PUA4x4Part0V04Candidate.ttf"
install -m 0644 "$BUILD_DIR/PUA4x4Part1V04Candidate.ttf" \
    "$FONT_DIR/PUA4x4Part1V04Candidate.ttf"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-v04-candidate.conf" \
    "$CONFIG_DIR/99-pua-4x4-v04-candidate.conf"
fc-cache -f >/dev/null

part0=$(fc-match -f '%{family}\n' 'PUA 4x4 Part 0 v0.4 Candidate' | head -n 1)
part1=$(fc-match -f '%{family}\n' 'PUA 4x4 Part 1 v0.4 Candidate' | head -n 1)
test "$part0" = 'PUA 4x4 Part 0 v0.4 Candidate' || {
    echo "Candidate Part 0 font match failed: $part0" >&2
    exit 1
}
test "$part1" = 'PUA 4x4 Part 1 v0.4 Candidate' || {
    echo "Candidate Part 1 font match failed: $part1" >&2
    exit 1
}

echo "Installed side-by-side: $FONT_DIR/PUA4x4Part0V04Candidate.ttf"
echo "Installed side-by-side: $FONT_DIR/PUA4x4Part1V04Candidate.ttf"
echo "Configured isolated alias: PUA 4x4 v0.4 Candidate"
echo "Preserved alias: PUA 4x4"
