#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
MODE="${1:-square}"

case "$MODE" in
    square)
        "$SCRIPT_DIR/launch-mate-terminal.sh" setup
        profile="Square Braille Unicode Text Seamless"
        catalog="square"
        ;;
    pua4)
        "$ROOT_DIR/experiments/pua-4x4/launch-linux.sh" setup
        profile="PUA 4x4 v0.4 Candidate 3"
        catalog="pua4"
        ;;
    *) echo "Usage: $0 {square|pua4}" >&2; exit 2 ;;
esac

command=(python3 "$ROOT_DIR/scripts/show-graphics-font-characters.py" "$catalog")
printf -v command_string '%q ' "${command[@]}"
exec mate-terminal --disable-factory "--profile=$profile" --maximize \
    "--working-directory=$ROOT_DIR" "--title=$profile glyph catalog" \
    "--command=$command_string"
