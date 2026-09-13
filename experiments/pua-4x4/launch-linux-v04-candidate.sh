#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_ID="pua4x4v04candidate"
PROFILE_NAME="PUA 4x4 v0.4 Candidate"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-triangle}"
FONT_SIZE="${PUA4X4_FONT_SIZE:-14}"

case "$MODE" in
    setup|shell|triangle|probe) ;;
    *) echo "Usage: $0 [setup|shell|triangle|probe]" >&2; exit 2 ;;
esac

for command_name in dconf fc-cache gsettings mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

"$SCRIPT_DIR/install-linux-v04-candidate.sh"
python3 "$SCRIPT_DIR/verify_linux_v04_candidate_runtime.py"

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
dconf write "${PROFILE_PATH}font" "'PUA 4x4 v0.4 Candidate $FONT_SIZE'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"
dconf write "${PROFILE_PATH}bold-color-same-as-fg" true
dconf write "${PROFILE_PATH}exit-action" "'hold'"

echo "Candidate profile ready: $PROFILE_NAME at $FONT_SIZE pt"
test "$MODE" = setup && exit 0

terminal_args=(
    --disable-factory
    "--profile=$PROFILE_NAME"
    --maximize
    "--working-directory=$SCRIPT_DIR"
)
if [[ "$MODE" == triangle ]]; then
    terminal_args+=(
        "--title=PUA 4x4 v0.4 Candidate Triangle Evidence"
        "--command=python3 $SCRIPT_DIR/demos4x4/triangle.py --pps 100000 --hold 180"
    )
elif [[ "$MODE" == probe ]]; then
    terminal_args+=(
        "--title=PUA 4x4 v0.4 Candidate Terminal Probe"
        "--command=python3 $SCRIPT_DIR/terminal_candidate_probe.py --hold 180 --output $SCRIPT_DIR/output/audit/terminal-v0.4-candidate/probe-runtime.json"
    )
else
    terminal_args+=("--title=PUA 4x4 v0.4 Candidate Shell")
fi
exec mate-terminal "${terminal_args[@]}"
