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
"$PYTHON" -c 'import fontTools, numpy, PIL'
"$PYTHON" -m py_compile demos/basic/*.py demos/vector/*.py demos/3d/*.py

"$PYTHON" demos/basic/unicode_braille_probe.py >/dev/null
"$PYTHON" demos/basic/geometry_test.py --stage solid --seconds 0.02 >/dev/null
"$PYTHON" demos/basic/snow.py --frames 1 --columns 40 --rows 12 >/dev/null
"$PYTHON" demos/basic/starfield.py --frames 1 >/dev/null

"$PYTHON" demos/vector/vertical_probe.py --hold 0 >/dev/null
"$PYTHON" demos/vector/vector_tunnel.py --frames 1 >/dev/null
"$PYTHON" demos/vector/doom_demo.py --frames 1 >/dev/null
"$PYTHON" demos/vector/elite_battle.py --frames 1 >/dev/null

"$PYTHON" demos/3d/test_enterprise_flyby.py
"$PYTHON" demos/3d/enterprise_flyby.py \
    --frames 1 --columns 40 --rows 12 --detail 1 >/dev/null

echo 'PASS: native macOS basic, vector and procedural 3D smoke tests'
