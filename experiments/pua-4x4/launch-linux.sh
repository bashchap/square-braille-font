#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_ID="pua4x4"
PROFILE_NAME="PUA 4x4 Experimental"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-demo}"

case "$MODE" in
    setup|shell|demo|motion|reference) ;;
    *) echo "Usage: $0 [setup|shell|demo|motion|reference]" >&2; exit 2 ;;
esac

if [[ -n "${PUA4X4_FONT_SIZE:-}" ]]; then
    FONT_SIZE="$PUA4X4_FONT_SIZE"
elif [[ "$MODE" == motion ]]; then
    # 12 pt at the tested 96-DPI Linux display gives a 16-device-pixel em,
    # placing every 4x4 subcell boundary on an integer device coordinate.
    FONT_SIZE=12
else
    FONT_SIZE=14
fi

for command_name in dconf fc-cache gsettings mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

"$SCRIPT_DIR/install-linux-user.sh"
python3 "$SCRIPT_DIR/verify_linux_runtime.py"

profiles="$(gsettings get org.mate.terminal.global profile-list)"
updated_profiles="$(python3 - "$profiles" "$PROFILE_ID" <<'PY'
import ast
import sys

profiles = ast.literal_eval(sys.argv[1])
if sys.argv[2] not in profiles:
    profiles.append(sys.argv[2])
print(repr(profiles))
PY
)"
gsettings set org.mate.terminal.global profile-list "$updated_profiles"
dconf write "${PROFILE_PATH}visible-name" "'$PROFILE_NAME'"
dconf write "${PROFILE_PATH}use-system-font" false
dconf write "${PROFILE_PATH}font" "'PUA 4x4 $FONT_SIZE'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"
dconf write "${PROFILE_PATH}bold-color-same-as-fg" true
dconf write "${PROFILE_PATH}exit-action" "'hold'"

echo "Profile ready: $PROFILE_NAME"
test "$MODE" = setup && exit 0

terminal_args=(
    --disable-factory
    "--profile=$PROFILE_NAME"
    --maximize
    "--working-directory=$SCRIPT_DIR"
)
if [[ "$MODE" == demo ]]; then
    terminal_args+=(
        "--title=PUA 4x4 — Mapping and Resolution Proof"
        "--command=python3 $SCRIPT_DIR/pua4x4_demo.py"
    )
elif [[ "$MODE" == motion ]]; then
    terminal_args+=(
        "--title=PUA 4x4 — Curved Vortex"
        "--command=python3 $SCRIPT_DIR/pua4x4_motion_demo.py"
    )
elif [[ "$MODE" == reference ]]; then
    terminal_args+=(
        "--title=PUA 4x4 — Reference Renderer"
        "--command=python3 $SCRIPT_DIR/pua4x4_reference_renderer.py"
    )
else
    terminal_args+=("--title=PUA 4x4 Experimental Shell")
fi
exec mate-terminal "${terminal_args[@]}"
