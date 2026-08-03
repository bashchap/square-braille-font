#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FONT_FAMILY="Square Braille Unicode Text Seamless"
PROFILE_ID="square-braille"
PROFILE_NAME="Square Braille Unicode Text Seamless"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-shell}"

case "$MODE" in
    shell|probe|setup) ;;
    *) echo "Usage: $0 [shell|probe|setup]" >&2; exit 2 ;;
esac

"$SCRIPT_DIR/install-user.sh"
for command_name in dconf gsettings mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

profiles="$(gsettings get org.mate.terminal.global profile-list)"
updated="$(python3 - "$profiles" "$PROFILE_ID" <<'PY'
import ast, sys
profiles = ast.literal_eval(sys.argv[1])
if sys.argv[2] not in profiles:
    profiles.append(sys.argv[2])
print(repr(profiles))
PY
)"
gsettings set org.mate.terminal.global profile-list "$updated"
dconf write "${PROFILE_PATH}visible-name" "'$PROFILE_NAME'"
dconf write "${PROFILE_PATH}use-system-font" false
dconf write "${PROFILE_PATH}font" "'$FONT_FAMILY 14'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"

echo "Profile ready: $PROFILE_NAME"
[[ "$MODE" == setup ]] && exit 0

args=(--disable-factory "--profile=$PROFILE_NAME" --maximize "--working-directory=$ROOT_DIR")
case "$MODE" in
    shell) args+=("--title=$PROFILE_NAME") ;;
    probe) args+=("--title=Unicode and PUA Braille Comparison" "--command=$ROOT_DIR/demos/basic/unicode_braille_probe.py") ;;
esac
exec mate-terminal "${args[@]}"

