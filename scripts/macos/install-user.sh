#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
FONT_FILE='Square-Braille-Unicode-Text-Seamless.ttf'
SOURCE="$ROOT_DIR/fonts/current/$FONT_FILE"
DESTINATION="$HOME/Library/Fonts/$FONT_FILE"

test "$(uname -s)" = Darwin || {
    echo 'This installer is for macOS.' >&2
    exit 1
}
test -f "$SOURCE" || { echo "Font not found: $SOURCE" >&2; exit 1; }

mkdir -p "$HOME/Library/Fonts"
install -m 0644 "$SOURCE" "$DESTINATION"
echo "Installed: $DESTINATION"
shasum -a 256 "$DESTINATION"
echo 'Restart Terminal, then select "Square Braille Unicode Text Seamless" in a profile.'
echo 'Tested Terminal settings: character spacing 0.969; line spacing 0.861; 8 pt or larger.'
