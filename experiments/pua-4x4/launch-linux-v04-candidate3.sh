#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_ID="pua4x4v04candidate3"
PROFILE_NAME="PUA 4x4 v0.4 Candidate 3"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-demo}"
FONT_SIZE="${PUA4X4_FONT_SIZE:-14}"
PACKAGE_DIR="${PUA4X4_RC1_PACKAGE_DIR:-$SCRIPT_DIR/../../fonts/candidates/pua-4x4-v0.4-rc1}"
if [[ ! -f "$PACKAGE_DIR/PUA4x4Part0V04Candidate3.ttf" \
   && -f "$SCRIPT_DIR/build-v0.4-candidate.3-seamguard100/PUA4x4Part0V04Candidate3.ttf" ]]; then
    PACKAGE_DIR="$SCRIPT_DIR/build-v0.4-candidate.3-seamguard100"
fi
export PUA4X4_RC1_PACKAGE_DIR="$PACKAGE_DIR"

case "$MODE" in
    setup|shell|demo|motion|reference|triangle|probe) ;;
    *) echo "Usage: $0 [setup|shell|demo|motion|reference|triangle|probe]" >&2; exit 2 ;;
esac

"$SCRIPT_DIR/install-linux-v04-candidate3.sh"
python3 "$SCRIPT_DIR/verify_linux_v04_candidate_runtime.py" \
    --build-dir "$PACKAGE_DIR" \
    --alias "PUA 4x4 v0.4 Candidate 3" \
    --part0-family "PUA 4x4 Part 0 v0.4 Candidate 3" \
    --part1-family "PUA 4x4 Part 1 v0.4 Candidate 3" \
    --part0-file PUA4x4Part0V04Candidate3.ttf \
    --part1-file PUA4x4Part1V04Candidate3.ttf \
    --output "$SCRIPT_DIR/output/audit/pua4x4-v0.4-candidate3-linux-runtime.json" \
    --layout-output "$SCRIPT_DIR/output/audit/pua4x4-v0.4-candidate3-pango-layout.json"

profiles="$(gsettings get org.mate.terminal.global profile-list)"
updated_profiles="$(python3 - "$profiles" "$PROFILE_ID" <<'PY'
import ast, sys
profiles = ast.literal_eval(sys.argv[1])
if sys.argv[2] not in profiles:
    profiles.append(sys.argv[2])
print(repr(profiles))
PY
)"
gsettings set org.mate.terminal.global profile-list "$updated_profiles"
dconf write "${PROFILE_PATH}visible-name" "'$PROFILE_NAME'"
dconf write "${PROFILE_PATH}use-system-font" false
dconf write "${PROFILE_PATH}font" "'PUA 4x4 v0.4 Candidate 3 $FONT_SIZE'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"
dconf write "${PROFILE_PATH}bold-color-same-as-fg" true
dconf write "${PROFILE_PATH}exit-action" "'hold'"

echo "Candidate.3 profile ready: $PROFILE_NAME at $FONT_SIZE pt"
test "$MODE" = setup && exit 0

terminal_args=(--disable-factory "--profile=$PROFILE_NAME" --maximize "--working-directory=$SCRIPT_DIR")
case "$MODE" in
    demo)
        terminal_args+=(
            "--title=PUA 4x4 v0.4 RC1 — Mapping and Resolution Proof"
            "--command=python3 $SCRIPT_DIR/pua4x4_demo.py"
        )
        ;;
    motion)
        terminal_args+=(
            "--title=PUA 4x4 v0.4 RC1 — Curved Vortex"
            "--command=python3 $SCRIPT_DIR/pua4x4_motion_demo.py"
        )
        ;;
    reference)
        terminal_args+=(
            "--title=PUA 4x4 v0.4 RC1 — Reference Renderer"
            "--command=python3 $SCRIPT_DIR/pua4x4_reference_renderer.py"
        )
        ;;
    triangle)
        terminal_args+=("--command=python3 $SCRIPT_DIR/demos4x4/triangle.py --pps 100000 --hold 180")
        ;;
    probe)
        terminal_args+=("--command=python3 $SCRIPT_DIR/terminal_candidate_probe.py --hold 180 --output $SCRIPT_DIR/output/audit/terminal-v0.4-candidate3/probe-runtime.json")
        ;;
    shell)
        terminal_args+=("--title=PUA 4x4 v0.4 Candidate 3 Shell")
        ;;
esac
exec mate-terminal "${terminal_args[@]}"
