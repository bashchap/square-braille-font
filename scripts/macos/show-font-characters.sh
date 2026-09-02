#!/bin/sh
set -eu

MODE=${1:-square}
case "$MODE" in
    square|pua4) ;;
    *) echo "Usage: $0 {square|pua4}" >&2; exit 2 ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$SCRIPT_DIR/run-demo.sh" "$MODE" catalog
