#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
FONT_FAMILY='Square Braille Unicode Text Seamless'
FONT_FILE='Square-Braille-Unicode-Text-Seamless.ttf'
SOURCE="$ROOT_DIR/fonts/current/$FONT_FILE"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"

command -v fc-cache >/dev/null 2>&1 || {
    echo 'fc-cache is required (install fontconfig).' >&2
    exit 1
}
test -f "$SOURCE" || { echo "Font not found: $SOURCE" >&2; exit 1; }

mkdir -p "$FONT_DIR"
install -m 0644 "$SOURCE" "$FONT_DIR/$FONT_FILE"
fc-cache -f "$FONT_DIR" >/dev/null

selected=$(fc-match -f '%{family}\n' "$FONT_FAMILY" | head -n 1)
test "$selected" = "$FONT_FAMILY" || {
    echo "Fontconfig selected '$selected', expected '$FONT_FAMILY'." >&2
    exit 1
}

echo "Installed: $FONT_DIR/$FONT_FILE"
echo "Validated family: $selected"

