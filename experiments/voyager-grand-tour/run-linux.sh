#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Support both the published repository layout
#   ROOT/experiments/voyager-grand-tour
# and the preserved development tree
#   ~/dev/FontMaker/voyager-grand-tour.
MODERN_ROOT="$(cd "$DEMO_DIR/../.." && pwd)"
LEGACY_ROOT="$(cd "$DEMO_DIR/.." && pwd)"
if [[ -x "$MODERN_ROOT/scripts/linux/launch-mate-terminal.sh" ]]; then
    ROOT_DIR="$MODERN_ROOT"
    FONT2_SETUP=("$ROOT_DIR/scripts/linux/launch-mate-terminal.sh" setup)
    FONT4_SETUP=("$ROOT_DIR/experiments/pua-4x4/launch-linux.sh" setup)
elif [[ -x "$LEGACY_ROOT/unicode-braille/launch_unicode_braille_terminal.sh" \
     && -x "$LEGACY_ROOT/pua4x4/launch-linux.sh" ]]; then
    ROOT_DIR="$LEGACY_ROOT"
    FONT2_SETUP=("$ROOT_DIR/unicode-braille/launch_unicode_braille_terminal.sh" setup)
    FONT4_SETUP=("$ROOT_DIR/pua4x4/launch-linux.sh" setup)
else
    echo "Could not locate the Square Braille and PUA 4x4 Linux launchers." >&2
    exit 1
fi

usage() {
    cat <<'EOF'
Usage: ./run-linux.sh {-2|-4} [live options]
       ./run-linux.sh {-2|-4} capture [capture options]
       ./run-linux.sh {-2|-4} play RECORDING.vgr [player options]

Launcher options (accepted anywhere after -2/-4):
  --terminal-columns N   width of the newly opened MATE Terminal, in cells
  --terminal-rows N      height of the newly opened MATE Terminal, in cells
  --terminal-zoom Z      MATE font zoom (for example 0.40 for 360x104)

Examples:
  ./run-linux.sh -2
  ./run-linux.sh -4
  ./run-linux.sh -4 --style filled
  ./run-linux.sh -4 --style wire --no-hlr
  ./run-linux.sh -4 --camera contour
  ./run-linux.sh -2 --camera contour --style wire --fps 8
  ./run-linux.sh -4 capture --duration 60 --fps 12 --output voyager-4x4.vgr
  ./run-linux.sh -4 capture --terminal-columns 360 --terminal-rows 104 \
    --terminal-zoom 0.40 \
    --duration 60 --fps 12 --output voyager-wide.vgr
  ./run-linux.sh -4 play voyager-4x4.vgr --loop

The launcher installs/configures the selected font, creates the matching MATE
Terminal profile and opens the live demonstration, offline capture dashboard,
or VGR player. Capture FPS is deterministic animation sampling; capture runs as
fast as the renderer permits and does not wait between frames. When terminal
dimensions are omitted the new window is maximized. A capture without renderer
--columns/--rows inherits the actual size of the newly opened terminal.
EOF
}

[[ $# -gt 0 ]] || { usage >&2; exit 2; }
mode="$1"
shift

# These two options belong to the launcher, not the Python renderer.  Remove
# them from the forwarded argument vector while allowing them in any position.
terminal_columns=""
terminal_rows=""
terminal_zoom=""
program_args=()
while (($#)); do
    case "$1" in
        --terminal-columns)
            [[ $# -ge 2 ]] || { echo "--terminal-columns requires a value" >&2; exit 2; }
            terminal_columns="$2"
            shift 2
            ;;
        --terminal-columns=*)
            terminal_columns="${1#*=}"
            shift
            ;;
        --terminal-rows)
            [[ $# -ge 2 ]] || { echo "--terminal-rows requires a value" >&2; exit 2; }
            terminal_rows="$2"
            shift 2
            ;;
        --terminal-rows=*)
            terminal_rows="${1#*=}"
            shift
            ;;
        --terminal-zoom)
            [[ $# -ge 2 ]] || { echo "--terminal-zoom requires a value" >&2; exit 2; }
            terminal_zoom="$2"
            shift 2
            ;;
        --terminal-zoom=*)
            terminal_zoom="${1#*=}"
            shift
            ;;
        *)
            program_args+=("$1")
            shift
            ;;
    esac
done
set -- "${program_args[@]}"

if [[ -n "$terminal_columns" || -n "$terminal_rows" ]]; then
    [[ "$terminal_columns" =~ ^[0-9]+$ && "$terminal_columns" -ge 40 ]] || {
        echo "--terminal-columns must be an integer of at least 40" >&2
        exit 2
    }
    [[ "$terminal_rows" =~ ^[0-9]+$ && "$terminal_rows" -ge 12 ]] || {
        echo "--terminal-rows must be an integer of at least 12" >&2
        exit 2
    }
    terminal_window_options=("--geometry=${terminal_columns}x${terminal_rows}")
else
    terminal_window_options=(--maximize)
fi
if [[ -n "$terminal_zoom" ]]; then
    [[ "$terminal_zoom" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ \
       && "$terminal_zoom" != "0" && "$terminal_zoom" != "0.0" ]] || {
        echo "--terminal-zoom must be a positive number such as 0.40 or 1.0" >&2
        exit 2
    }
    terminal_window_options+=("--zoom=$terminal_zoom")
fi

case "$mode" in
    -2)
        PROFILE_NAME="Square Braille Unicode Text Seamless"
        "${FONT2_SETUP[@]}"
        ;;
    -4)
        PROFILE_NAME="PUA 4x4 v0.4 Candidate 3"
        "${FONT4_SETUP[@]}"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo "First argument must be -2 or -4." >&2
        usage >&2
        exit 2
        ;;
esac

for command_name in mate-terminal python3; do
    command -v "$command_name" >/dev/null || {
        echo "Required command not found: $command_name" >&2
        exit 1
    }
done

python3 -c 'import numpy' >/dev/null 2>&1 || {
    echo "Python dependency missing: numpy (run: python3 -m pip install -r requirements.txt)" >&2
    exit 1
}

action="${1:-live}"
case "$action" in
    capture) DEFAULT_WINDOW_TITLE="Voyager Offline Capture — $mode" ;;
    play) DEFAULT_WINDOW_TITLE="Voyager VGR Player — $mode" ;;
    *) DEFAULT_WINDOW_TITLE="Voyager 2 Grand Tour — $mode" ;;
esac
WINDOW_TITLE="${VOYAGER_WINDOW_TITLE:-$DEFAULT_WINDOW_TITLE}"

command=(env)
if [[ "$action" == "capture" && -n "$terminal_columns" ]]; then
    command+=("VOYAGER_EXPECT_TERMINAL_COLUMNS=$terminal_columns"
              "VOYAGER_EXPECT_TERMINAL_ROWS=$terminal_rows")
fi
if [[ "$action" == "capture" && -n "$terminal_zoom" ]]; then
    command+=("VOYAGER_TERMINAL_ZOOM=$terminal_zoom")
fi
command+=(python3 "$DEMO_DIR/voyager_grand_tour.py" "$mode" "$@")
printf -v command_string '%q ' "${command[@]}"
exec mate-terminal \
    --disable-factory \
    "--profile=$PROFILE_NAME" \
    "${terminal_window_options[@]}" \
    "--working-directory=$DEMO_DIR" \
    "--title=$WINDOW_TITLE" \
    "--command=$command_string"
