#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

columns=120
rows=36
font_size=12

usage() {
    cat <<'EOF'
Usage:
  ./scripts/macos/run-demo.sh [window options] MODE NAME [demo arguments...]
  ./scripts/macos/run-demo.sh --list

Window options (must precede MODE):
  --terminal-columns N   initial WezTerm columns (default 120)
  --terminal-rows N      initial WezTerm rows (default 36)
  --font-size POINTS     initial font size (default 12)

MODE is square or pua4. NAME may be shell, catalog, aliases, catalog-all, or a
demo name.
The launcher uses a repository-local WezTerm configuration; it does not create
or modify a Terminal.app profile.
EOF
}

list_demos() {
    cat <<'EOF'
Square Braille 2x4:
  geometry snow starfield trail triangle vertical vector elite doom
  enterprise enterprise-hlr spaceship unicode font-probe voyager

PUA 4x4:
  geometry snow starfield trail editor triangle vertical vector elite doom
  enterprise enterprise-hlr spaceship defender voyager model-viewer

Both modes also provide:
  shell       open an interactive shell with the correct font/fallback stack
  catalog     display every generated graphics glyph (paged)

Square mode additionally provides:
  aliases     display the compatibility aliases at U+E000..U+E0FF
  catalog-all display official Square, aliases and both PUA 4x4 parts

enterprise-hlr and spaceship require a separately licensed local mesh cache.
The procedural enterprise and NASA Voyager demos include their required data.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --terminal-columns) columns="${2:?missing column count}"; shift 2 ;;
        --terminal-rows) rows="${2:?missing row count}"; shift 2 ;;
        --font-size) font_size="${2:?missing font size}"; shift 2 ;;
        --list) list_demos; exit 0 ;;
        -h|--help) usage; echo; list_demos; exit 0 ;;
        --) shift; break ;;
        *) break ;;
    esac
done

[[ $# -ge 2 ]] || { usage >&2; exit 2; }
mode="$1"
name="$2"
shift 2

case "$mode" in
    square) config="$ROOT_DIR/config/wezterm/square-braille.lua" ;;
    pua4) config="$ROOT_DIR/config/wezterm/pua4.lua" ;;
    *) echo "Unknown font mode: $mode (expected square or pua4)" >&2; exit 2 ;;
esac

if command -v wezterm >/dev/null 2>&1; then
    wezterm_bin="$(command -v wezterm)"
elif [[ -x /Applications/WezTerm.app/Contents/MacOS/wezterm ]]; then
    wezterm_bin=/Applications/WezTerm.app/Contents/MacOS/wezterm
elif [[ -x "$HOME/Applications/WezTerm.app/Contents/MacOS/wezterm" ]]; then
    wezterm_bin="$HOME/Applications/WezTerm.app/Contents/MacOS/wezterm"
else
    echo 'WezTerm is required for an isolated explicit fallback configuration.' >&2
    echo 'Install it without administrator access with:' >&2
    echo '  mkdir -p "$HOME/Applications"' >&2
    echo '  brew install --cask --appdir="$HOME/Applications" wezterm' >&2
    exit 1
fi

if [[ ! -f "$HOME/Library/Fonts/Square-Braille-Unicode-Text-Seamless.ttf" ]]; then
    echo 'Square Braille is not installed for this user.' >&2
    echo 'Run: ./scripts/macos/install-all-user.sh' >&2
    exit 1
fi
if [[ "$mode" == pua4 ]]; then
    for font in PUA4x4Part0V06Candidate6.ttf PUA4x4Part1V06Candidate6.ttf; do
        [[ -f "$HOME/Library/Fonts/$font" ]] || {
            echo "PUA 4x4 font is not installed: $HOME/Library/Fonts/$font" >&2
            echo 'Run: ./scripts/macos/install-all-user.sh' >&2
            exit 1
        }
    done
fi

python_bin="${PYTHON:-}"
if [[ -z "$python_bin" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        python_bin="$ROOT_DIR/.venv/bin/python"
    else
        python_bin="$(command -v python3)"
    fi
fi

demo_dir="$ROOT_DIR"
case "$name" in
    shell)
        command=("${SHELL:-/bin/zsh}" -l)
        ;;
    catalog)
        catalog=square
        [[ "$mode" == pua4 ]] && catalog=pua4
        command=("$python_bin" "$ROOT_DIR/scripts/show-graphics-font-characters.py" "$catalog")
        ;;
    aliases)
        [[ "$mode" == square ]] || { echo 'aliases is a Square Braille catalog.' >&2; exit 2; }
        command=("$python_bin" "$ROOT_DIR/scripts/show-graphics-font-characters.py" square-pua)
        ;;
    catalog-all)
        [[ "$mode" == pua4 ]] || { echo 'catalog-all needs the complete pua4 fallback stack.' >&2; exit 2; }
        command=("$python_bin" "$ROOT_DIR/scripts/show-graphics-font-characters.py" all)
        ;;
    geometry|snow|starfield|trail|triangle)
        script="$name.py"
        if [[ "$name" == geometry ]]; then script=geometry_test.py; fi
        if [[ "$mode" == square ]]; then
            demo_dir="$ROOT_DIR/demos/basic"
        else
            demo_dir="$ROOT_DIR/experiments/pua-4x4/demos4x4"
        fi
        command=("$python_bin" "$demo_dir/$script" "$@")
        ;;
    vertical|vector|elite|doom)
        case "$name" in
            vertical) script=vertical_probe.py ;;
            vector) script=vector_tunnel.py ;;
            elite) script=elite_battle.py ;;
            doom) script=doom_demo.py ;;
        esac
        if [[ "$mode" == square ]]; then
            demo_dir="$ROOT_DIR/demos/vector"
        else
            demo_dir="$ROOT_DIR/experiments/pua-4x4/demos4x4"
        fi
        command=("$python_bin" "$demo_dir/$script" "$@")
        ;;
    enterprise|enterprise-hlr|spaceship)
        case "$name" in
            enterprise) script=enterprise_flyby.py ;;
            enterprise-hlr) script=enterprise_wireframe.py ;;
            spaceship) script=space_ship_flyby.py ;;
        esac
        if [[ "$mode" == square ]]; then
            demo_dir="$ROOT_DIR/demos/3d"
        else
            demo_dir="$ROOT_DIR/experiments/pua-4x4/demos4x4"
        fi
        command=("$python_bin" "$demo_dir/$script" "$@")
        ;;
    unicode)
        [[ "$mode" == square ]] || { echo 'unicode is a Square Braille demo.' >&2; exit 2; }
        demo_dir="$ROOT_DIR/demos/basic"
        command=("$python_bin" "$demo_dir/unicode_braille_probe.py" "$@")
        ;;
    font-probe)
        [[ "$mode" == square ]] || { echo 'font-probe is a Square Braille demo.' >&2; exit 2; }
        demo_dir="$ROOT_DIR/demos/basic"
        command=("$python_bin" "$demo_dir/terminal_font_probe.py" "$@")
        ;;
    editor|defender)
        [[ "$mode" == pua4 ]] || { echo "$name is a PUA 4x4 demo." >&2; exit 2; }
        demo_dir="$ROOT_DIR/experiments/pua-4x4/demos4x4"
        [[ "$name" == editor ]] && script=glyph_editor.py || script=defender.py
        command=("$python_bin" "$demo_dir/$script" "$@")
        ;;
    voyager)
        demo_dir="$ROOT_DIR/experiments/voyager-grand-tour"
        resolution=-2
        [[ "$mode" == pua4 ]] && resolution=-4
        command=("$python_bin" "$demo_dir/voyager_grand_tour.py" "$resolution" "$@")
        ;;
    model-viewer)
        [[ "$mode" == pua4 ]] || { echo 'model-viewer is a PUA 4x4 demo.' >&2; exit 2; }
        demo_dir="$ROOT_DIR/experiments/voyager-model-viewer"
        command=("$python_bin" "$demo_dir/voyager_model_viewer.py" "$@")
        ;;
    *) echo "Unknown demo: $name" >&2; list_demos >&2; exit 2 ;;
esac

export FONT_DEMO_COLUMNS="$columns"
export FONT_DEMO_ROWS="$rows"
export FONT_DEMO_SIZE="$font_size"

exec "$wezterm_bin" --config-file "$config" start --always-new-process \
    --cwd "$demo_dir" -- "${command[@]}"
