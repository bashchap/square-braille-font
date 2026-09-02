#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
PYTHON=${PYTHON:-python3}

test "$(uname -s)" = Darwin || {
    echo 'This smoke test is for macOS.' >&2
    exit 1
}

cd "$ROOT_DIR"

for required in \
    fonts/current/Square-Braille-Unicode-Text-Seamless.ttf \
    fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part0V06Candidate6.ttf \
    fonts/candidates/pua-4x4-v0.6-rc1/PUA4x4Part1V06Candidate6.ttf \
    experiments/voyager-grand-tour/assets/voyager-vtad-hlr.npz
do
    test -f "$required" || { echo "FAIL missing asset: $required" >&2; exit 1; }
done

if command -v wezterm >/dev/null 2>&1; then
    square_resolution=$(FONT_DEMO_ROOT="$ROOT_DIR" wezterm \
        --config-file config/wezterm/square-braille.lua \
        ls-fonts --codepoints 41,2801,28ff 2>&1 | tr -d '\000')
    printf '%s\n' "$square_resolution" | grep -Fq \
        '/fonts/current/Square-Braille-Unicode-Text-Seamless.' || {
        echo 'FAIL: WezTerm did not select the repository Square Braille face.' >&2
        printf '%s\n' "$square_resolution" >&2
        exit 1
    }

    pua_resolution=$(FONT_DEMO_ROOT="$ROOT_DIR" wezterm \
        --config-file config/wezterm/pua4.lua \
        ls-fonts --codepoints 41,f0001,100001 2>&1 | tr -d '\000')
    for expected in PUA4x4Part0V06Candidate6.ttf PUA4x4Part1V06Candidate6.ttf; do
        printf '%s\n' "$pua_resolution" | grep -Fq "/$expected" || {
            echo "FAIL: WezTerm did not select $expected." >&2
            printf '%s\n' "$pua_resolution" >&2
            exit 1
        }
    done
    echo 'PASS: WezTerm resolves Square Braille and both PUA 4x4 faces from this repository'
fi

"$SCRIPT_DIR/smoke-demos.sh"
"$PYTHON" experiments/pua-4x4/demos4x4/verify_demos4x4.py
"$PYTHON" experiments/pua-4x4/verify_vortex_motion.py
"$PYTHON" experiments/voyager-grand-tour/test_voyager_grand_tour.py
"$PYTHON" experiments/voyager-model-viewer/test_voyager_model_viewer.py

"$PYTHON" -m py_compile \
    scripts/show-graphics-font-characters.py \
    scripts/macos/verify-install.py \
    experiments/pua-4x4/pua4x4_motion_demo.py \
    experiments/pua-4x4/verify_vortex_motion.py \
    experiments/pua-4x4/demos4x4/*.py \
    experiments/voyager-grand-tour/*.py \
    experiments/voyager-model-viewer/*.py

# The two external-mesh renderers are compiled above in both their Square and
# PUA variants. Their non-redistributable caches are deliberately not required.
echo 'PASS: complete native macOS demo suite'
echo 'NOTE: enterprise-hlr and spaceship need separately licensed local mesh caches.'
