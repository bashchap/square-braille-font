#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_ID="pua4x4verticalguardprobe"
PROFILE_NAME="PUA 4x4 Vertical Guard Probe"
PROFILE_PATH="/org/mate/terminal/profiles/$PROFILE_ID/"
MODE="${1:-field}"
FONT_SIZE="${PUA4X4_FONT_SIZE:-14}"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"
BUILD_DIR="$SCRIPT_DIR/output/vertical-guard-probe"

case "$MODE" in
    setup|shell|field|triangle|raster|box) ;;
    *) echo "Usage: $0 [setup|shell|field|triangle|raster|box]" >&2; exit 2 ;;
esac

install -d "$FONT_DIR" "$CONFIG_DIR"
install -m 0644 "$BUILD_DIR/PUA4x4Part0VerticalGuardProbe.ttf" "$FONT_DIR/"
install -m 0644 "$BUILD_DIR/PUA4x4Part1VerticalGuardProbe.ttf" "$FONT_DIR/"
install -m 0644 "$SCRIPT_DIR/fontconfig/99-pua-4x4-vertical-guard-probe.conf" "$CONFIG_DIR/"
fc-cache -f "$FONT_DIR"

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
dconf write "${PROFILE_PATH}font" "'$PROFILE_NAME $FONT_SIZE'"
dconf write "${PROFILE_PATH}use-theme-colors" false
dconf write "${PROFILE_PATH}foreground-color" "'#FFFFFFFFFFFF'"
dconf write "${PROFILE_PATH}background-color" "'#000000000000'"
dconf write "${PROFILE_PATH}bold-color-same-as-fg" true
dconf write "${PROFILE_PATH}exit-action" "'hold'"

echo "Diagnostic profile ready: $PROFILE_NAME at $FONT_SIZE pt"
test "$MODE" = setup && exit 0

terminal_args=(--disable-factory "--profile=$PROFILE_NAME" --maximize "--working-directory=$SCRIPT_DIR")
case "$MODE" in
    field)
        terminal_args+=("--title=PUA4X4-VERTICAL-GUARD-FIELD"
            "--command=bash -lc 'printf \"\\e[38;2;0;255;0m\"; for row in {1..20}; do printf \"\\U00107FFF%.0s\" {1..80}; printf \"\\n\"; done; printf \"\\e[0m\"; exec bash'")
        ;;
    triangle)
        terminal_args+=("--title=PUA4X4-VERTICAL-GUARD-TRIANGLE"
            "--command=python3 $SCRIPT_DIR/demos4x4/triangle.py --pps 100000 --hold 180")
        ;;
    raster)
        terminal_args+=("--title=PUA4X4-VERTICAL-GUARD-RASTER"
            "--command=python3 $SCRIPT_DIR/terminal_multicolour_raster_probe.py --candidate-label 'Vertical Guard Probe' --hold 180")
        ;;
    box)
        fontplotter_root="${FONTPLOTTER_ROOT:-$HOME/dev/FontPlotter}"
        test -f "$fontplotter_root/demos/framebuffer-box-diagnostic.py" || {
            echo "FontPlotter box diagnostic not found: $fontplotter_root" >&2
            exit 1
        }
        terminal_args+=("--title=PUA4X4-VERTICAL-GUARD-BOX-GRID"
            "--command=python3 $fontplotter_root/demos/framebuffer-box-diagnostic.py --fps 8")
        ;;
    shell)
        terminal_args+=("--title=PUA 4x4 Vertical Guard Probe Shell")
        ;;
esac
exec mate-terminal "${terminal_args[@]}"
