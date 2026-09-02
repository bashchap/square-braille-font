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

"$SCRIPT_DIR/smoke-demos.sh"
"$PYTHON" experiments/pua-4x4/demos4x4/verify_demos4x4.py
"$PYTHON" experiments/voyager-grand-tour/test_voyager_grand_tour.py
"$PYTHON" experiments/voyager-model-viewer/test_voyager_model_viewer.py

"$PYTHON" -m py_compile \
    scripts/show-graphics-font-characters.py \
    scripts/macos/verify-install.py \
    experiments/pua-4x4/demos4x4/*.py \
    experiments/voyager-grand-tour/*.py \
    experiments/voyager-model-viewer/*.py

# The two external-mesh renderers are compiled above in both their Square and
# PUA variants. Their non-redistributable caches are deliberately not required.
echo 'PASS: complete native macOS demo suite'
echo 'NOTE: enterprise-hlr and spaceship need separately licensed local mesh caches.'
