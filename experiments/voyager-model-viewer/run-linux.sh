#!/usr/bin/env bash
set -euo pipefail

VIEWER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODERN_ROOT="$(cd "$VIEWER_DIR/../.." && pwd)"
LEGACY_ROOT="$(cd "$VIEWER_DIR/.." && pwd)"

if [[ -x "$MODERN_ROOT/experiments/pua-4x4/launch-linux.sh" ]]; then
    FONT_SETUP=("$MODERN_ROOT/experiments/pua-4x4/launch-linux.sh" setup)
elif [[ -x "$LEGACY_ROOT/pua4x4/launch-linux.sh" ]]; then
    FONT_SETUP=("$LEGACY_ROOT/pua4x4/launch-linux.sh" setup)
else
    echo "Could not locate the PUA 4x4 Linux launcher." >&2
    exit 1
fi

usage() {
    cat <<'EOF'
Usage: ./run-linux.sh [viewer options]

Launcher-only options:
  --terminal-columns N   initial MATE Terminal width in character cells
  --terminal-rows N      initial MATE Terminal height in character cells
  --terminal-zoom Z      MATE font zoom, for example 0.40

Viewer options include:
  --style {wire,filled}  initial spacecraft rendering style
  --no-hlr               start with hidden-line removal disabled
  --depth-scale {1..4}   depth-buffer scale; 1 is most accurate
  --fps FPS              interactive redraw target
  --hud-scale SCALE      HUD text scale; default 2.0
  --start-rotating       begin the three-axis rotation loop immediately
  --start-recording      begin clean full-screen VGR recording immediately
  --record-output FILE   preferred VGR output path used by C/start-recording

Examples:
  ./run-linux.sh
  ./run-linux.sh --start-rotating --style wire
  ./run-linux.sh --terminal-columns 360 --terminal-rows 104 \
    --terminal-zoom 0.40 --depth-scale 2
  ./run-linux.sh --terminal-columns 360 --terminal-rows 104 \
    --terminal-zoom 0.40 --start-rotating --start-recording \
    --record-output "$HOME/voyager-model-view.vgr"

The viewer responds to every terminal resize. Its framebuffer, 3-D projection,
PUA 4x4 encoding and GUI are rebuilt at the new columns × rows geometry.
EOF
}

terminal_columns=""
terminal_rows=""
terminal_zoom=""
viewer_args=()
while (($#)); do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --terminal-columns)
            [[ $# -ge 2 ]] || { echo "--terminal-columns requires a value" >&2; exit 2; }
            terminal_columns="$2"
            shift 2
            ;;
        --terminal-columns=*) terminal_columns="${1#*=}"; shift ;;
        --terminal-rows)
            [[ $# -ge 2 ]] || { echo "--terminal-rows requires a value" >&2; exit 2; }
            terminal_rows="$2"
            shift 2
            ;;
        --terminal-rows=*) terminal_rows="${1#*=}"; shift ;;
        --terminal-zoom)
            [[ $# -ge 2 ]] || { echo "--terminal-zoom requires a value" >&2; exit 2; }
            terminal_zoom="$2"
            shift 2
            ;;
        --terminal-zoom=*) terminal_zoom="${1#*=}"; shift ;;
        *) viewer_args+=("$1"); shift ;;
    esac
done

if [[ -n "$terminal_columns" || -n "$terminal_rows" ]]; then
    [[ "$terminal_columns" =~ ^[0-9]+$ && "$terminal_columns" -ge 40 ]] || {
        echo "--terminal-columns must be an integer of at least 40" >&2
        exit 2
    }
    [[ "$terminal_rows" =~ ^[0-9]+$ && "$terminal_rows" -ge 16 ]] || {
        echo "--terminal-rows must be an integer of at least 16" >&2
        exit 2
    }
    window_options=("--geometry=${terminal_columns}x${terminal_rows}")
else
    window_options=(--maximize)
fi
if [[ -n "$terminal_zoom" ]]; then
    [[ "$terminal_zoom" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ \
       && "$terminal_zoom" != "0" && "$terminal_zoom" != "0.0" ]] || {
        echo "--terminal-zoom must be a positive number such as 0.40 or 1.0" >&2
        exit 2
    }
    window_options+=("--zoom=$terminal_zoom")
fi

"${FONT_SETUP[@]}"
for command_name in mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done
python3 -c 'import numpy; from PIL import Image' >/dev/null 2>&1 || {
    echo "Python dependencies missing: numpy and/or Pillow" >&2
    exit 1
}

command=(python3 "$VIEWER_DIR/voyager_model_viewer.py" "${viewer_args[@]}")
printf -v command_string '%q ' "${command[@]}"
exec mate-terminal \
    --disable-factory \
    "--profile=PUA 4x4 v0.4 Candidate 3" \
    "${window_options[@]}" \
    "--working-directory=$VIEWER_DIR" \
    "--title=PUA 4x4 Voyager Model Viewer" \
    "--command=$command_string"
