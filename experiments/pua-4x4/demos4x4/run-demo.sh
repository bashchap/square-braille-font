#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUA_DIR="$(cd "$DEMO_DIR/.." && pwd)"
PROFILE_NAME="PUA 4x4 v0.6 Candidate 6"

usage() {
    cat <<'EOF'
Usage: ./run-demo.sh NAME [window options] [demo arguments...]

Window options:
  --terminal-columns N   initial MATE Terminal columns (default: maximized)
  --terminal-rows N      initial MATE Terminal rows (default: maximized)
  --font-size POINTS     isolated PUA4 profile font size (default: 12)

PUA 4x4 demos (the original Square Braille demos remain untouched):
  geometry       solid/checker/subpixel tiling proof
  snow           smooth 4x4 virtual-pixel snowfall
  christmas-snow layered seasonal snow, scenery, accumulation and shedding
  christmas-snow-control keyboard TUI for live snow tuning and saved presets
  starfield      forward starfield flight
  trail          cursor-key drawing with a persistent trail
  editor         interactive 4x4 mask/codepoint mapping editor
  triangle       filled RGB triangle, plotted pixel by pixel
  vertical       four subpixel columns plus a full-cell seam probe
  vector         twisting vector tunnel/vortex flight
  elite          one-minute cinematic vector space battle
  doom           30-second ray-cast corridor homage
  enterprise     procedural color Enterprise fly-around
  enterprise-hlr high-detail Enterprise hidden-line wireframe
  spaceship      supplied-model cinematic flyby
  defender       two-minute gameplay attract mode (continuous by default)

Examples:
  ./run-demo.sh snow
  ./run-demo.sh christmas-snow --scenery all
  ./run-demo.sh christmas-snow --help
  ./run-demo.sh christmas-snow --listen
  ./run-demo.sh christmas-snow-control
  ./run-demo.sh defender --once
  ./run-demo.sh enterprise --detail 3 --fps 2
  ./run-demo.sh elite --freeze-at 42 --hold 20
EOF
}

[[ $# -gt 0 ]] || { usage; exit 2; }
name="$1"
shift
mode_arguments=()
terminal_columns=""
terminal_rows=""
font_size="${PUA4X4_FONT_SIZE:-12}"
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

case "$name" in
    geometry)       script="geometry_test.py" ;;
    snow)           script="snow.py" ;;
    christmas-snow|seasonal-snow)
                    script="$PUA_DIR/../../demos/seasonal/christmas_snow.py"
                    mode_arguments=(--mode pua4) ;;
    christmas-snow-control|seasonal-control)
                    script="$PUA_DIR/../../demos/seasonal/christmas_snow_control.py"
                    mode_arguments=(--mode pua4) ;;
    starfield)      script="starfield.py" ;;
    trail)          script="trail.py" ;;
    editor)         script="glyph_editor.py" ;;
    triangle)       script="triangle.py" ;;
    vertical)       script="vertical_probe.py" ;;
    vector)         script="vector_tunnel.py" ;;
    elite)          script="elite_battle.py" ;;
    doom)           script="doom_demo.py" ;;
    enterprise)     script="enterprise_flyby.py" ;;
    enterprise-hlr) script="enterprise_wireframe.py" ;;
    spaceship)      script="space_ship_flyby.py" ;;
    defender)       script="defender.py" ;;
    help|-h|--help) usage; exit 0 ;;
    *) echo "Unknown demo: $name" >&2; usage >&2; exit 2 ;;
esac

for command_name in mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

# Setup is idempotent and verifies the packaged v0.6 RC1 fonts before launch.
PUA4X4_FONT_SIZE="$font_size" "$PUA_DIR/launch-linux.sh" setup

if [[ "$script" != /* ]]; then
    script="$DEMO_DIR/$script"
fi
command=(python3 "$script" "${mode_arguments[@]}" "$@")
printf -v command_string '%q ' "${command[@]}"
window_arguments=(--maximize)
working_directory="$DEMO_DIR"
if [[ "$name" == christmas-snow-control || "$name" == seasonal-control ]]; then
    working_directory="$(cd "$PUA_DIR/../.." && pwd)"
fi
if [[ -n "$terminal_columns" ]]; then
    window_arguments=("--geometry=${terminal_columns}x${terminal_rows}")
fi
exec mate-terminal \
    --disable-factory \
    "--profile=$PROFILE_NAME" \
    "${window_arguments[@]}" \
    "--working-directory=$working_directory" \
    "--title=PUA 4x4 — $name" \
    "--command=$command_string"
