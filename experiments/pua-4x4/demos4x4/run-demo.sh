#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUA_DIR="$(cd "$DEMO_DIR/.." && pwd)"
PROFILE_NAME="PUA 4x4 Experimental"

usage() {
    cat <<'EOF'
Usage: ./run-demo.sh NAME [demo arguments...]

PUA 4x4 demos (the original Square Braille demos remain untouched):
  geometry       solid/checker/subpixel tiling proof
  snow           smooth 4x4 virtual-pixel snowfall
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
  ./run-demo.sh defender --once
  ./run-demo.sh enterprise --detail 3 --fps 2
  ./run-demo.sh elite --freeze-at 42 --hold 20
EOF
}

[[ $# -gt 0 ]] || { usage; exit 2; }
name="$1"
shift

case "$name" in
    geometry)       script="geometry_test.py" ;;
    snow)           script="snow.py" ;;
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

# Setup is idempotent and verifies both supplementary-PUA fonts before launch.
PUA4X4_FONT_SIZE="${PUA4X4_FONT_SIZE:-12}" "$PUA_DIR/launch-linux.sh" setup

command=(python3 "$DEMO_DIR/$script" "$@")
printf -v command_string '%q ' "${command[@]}"
exec mate-terminal \
    --disable-factory \
    "--profile=$PROFILE_NAME" \
    --maximize \
    "--working-directory=$DEMO_DIR" \
    "--title=PUA 4x4 — $name" \
    "--command=$command_string"
