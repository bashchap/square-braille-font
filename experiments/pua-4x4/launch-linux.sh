#!/usr/bin/env bash
# Default PUA 4×4 launcher: v0.6 RC1 (Candidate 6). Set
# PUA4X4_USE_V05_RC1=1, PUA4X4_USE_V04_RC1=1 or PUA4X4_USE_V03=1 to
# reproduce a preserved earlier environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${PUA4X4_USE_V03:-0}" == 1 ]]; then
    exec "$SCRIPT_DIR/launch-linux-v03.sh" "$@"
fi
if [[ "${PUA4X4_USE_V04_RC1:-0}" == 1 ]]; then
    exec "$SCRIPT_DIR/launch-linux-v04-candidate3.sh" "$@"
fi
if [[ "${PUA4X4_USE_V05_RC1:-0}" == 1 ]]; then
    exec "$SCRIPT_DIR/launch-linux-v05-candidate4.sh" "$@"
fi
exec "$SCRIPT_DIR/launch-linux-v06-candidate6.sh" "$@"
