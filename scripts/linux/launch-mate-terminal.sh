#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
FONT_FAMILY="Square Braille Unicode Text Seamless"
PROFILE_ID="square-braille"
PROFILE_NAME="Square Braille Unicode Text Seamless"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-shell}"
[[ $# -eq 0 ]] || shift
terminal_columns=""
terminal_rows=""
font_size="14"
demo_arguments=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --terminal-columns) terminal_columns="${2:?missing column count}"; shift 2 ;;
        --terminal-rows) terminal_rows="${2:?missing row count}"; shift 2 ;;
        --font-size) font_size="${2:?missing font size}"; shift 2 ;;
        *) demo_arguments+=("$1"); shift ;;
    esac
done
set -- "${demo_arguments[@]}"

if [[ -n "$terminal_columns" || -n "$terminal_rows" ]]; then
    [[ "$terminal_columns" =~ ^[0-9]+$ && "$terminal_columns" -ge 24 ]] || {
        echo '--terminal-columns and --terminal-rows must both be supplied; columns must be at least 24.' >&2
        exit 2
    }
    [[ "$terminal_rows" =~ ^[0-9]+$ && "$terminal_rows" -ge 8 ]] || {
        echo '--terminal-columns and --terminal-rows must both be supplied; rows must be at least 8.' >&2
        exit 2
    }
fi
[[ "$font_size" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo '--font-size must be a positive number.' >&2; exit 2;
}

case "$MODE" in
    shell|probe|setup|christmas-snow|seasonal-snow|christmas-snow-control|seasonal-control) ;;
    *) echo "Usage: $0 [shell|probe|setup|christmas-snow|christmas-snow-control] [window options] [demo arguments...]" >&2; exit 2 ;;
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
dconf write "${PROFILE_PATH}font" "'$FONT_FAMILY $font_size'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"

echo "Profile ready: $PROFILE_NAME"
[[ "$MODE" == setup ]] && exit 0

window_arguments=(--maximize)
if [[ -n "$terminal_columns" ]]; then
    window_arguments=("--geometry=${terminal_columns}x${terminal_rows}")
fi
args=(--disable-factory "--profile=$PROFILE_NAME" "${window_arguments[@]}" "--working-directory=$ROOT_DIR")
case "$MODE" in
    shell) args+=("--title=$PROFILE_NAME") ;;
    probe) args+=("--title=Unicode and PUA Braille Comparison" "--command=$ROOT_DIR/demos/basic/unicode_braille_probe.py") ;;
    christmas-snow|seasonal-snow)
        command=(python3 "$ROOT_DIR/demos/seasonal/christmas_snow.py" --mode square "$@")
        printf -v command_string '%q ' "${command[@]}"
        args+=("--title=Square Braille — Christmas Snow" "--command=$command_string")
        ;;
    christmas-snow-control|seasonal-control)
        command=(python3 "$ROOT_DIR/demos/seasonal/christmas_snow_control.py" --mode square "$@")
        printf -v command_string '%q ' "${command[@]}"
        args+=("--title=Christmas Snow — Live Control" "--command=$command_string")
        ;;
esac
exec mate-terminal "${args[@]}"
