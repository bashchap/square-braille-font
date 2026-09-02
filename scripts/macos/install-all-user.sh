#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
DESTINATION="$HOME/Library/Fonts"

test "$(uname -s)" = Darwin || {
    echo 'This installer is for macOS.' >&2
    exit 1
}

mkdir -p "$DESTINATION"
for source in \
    "$ROOT_DIR/fonts/current/Square-Braille-Unicode-Text-Seamless.ttf" \
    "$ROOT_DIR/fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part0V06Candidate6.ttf" \
    "$ROOT_DIR/fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part1V06Candidate6.ttf"
do
    test -f "$source" || { echo "Font not found: $source" >&2; exit 1; }
    destination="$DESTINATION/$(basename "$source")"
    install -m 0644 "$source" "$destination"
    echo "Installed: $destination"
    shasum -a 256 "$destination"
done

echo 'Restart terminal applications so they rebuild their user-font lists.'
echo 'Square profile: Square Braille Unicode Text Seamless'
echo 'PUA 4x4 fallback order: Square Braille text, Candidate 6 Part 0, Candidate 6 Part 1'
echo 'No Terminal.app profile was changed. Use scripts/macos/run-demo.sh to launch an isolated WezTerm window.'
