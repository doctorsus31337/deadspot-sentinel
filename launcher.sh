#!/usr/bin/env bash
set -u

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/deadspot-sentinel"
PYTHON_BIN="$INSTALL_DIR/.venv/bin/python"
APP_ENTRY="$INSTALL_DIR/run.py"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/deadspot-sentinel"
DIAGNOSTIC_LOG="$STATE_DIR/application.log"

if [[ ! -x "$PYTHON_BIN" || ! -f "$APP_ENTRY" ]]; then
    echo "DeadSpot Sentinel is not installed correctly." >&2
    echo "Expected: $PYTHON_BIN and $APP_ENTRY" >&2
    exit 1
fi

case "${1:-}" in
    --foreground)
        shift
        exec "$PYTHON_BIN" "$APP_ENTRY" "$@"
        ;;
    --diagnostic-log)
        mkdir -p "$STATE_DIR"
        touch "$DIAGNOSTIC_LOG"
        exec tail -n 200 -f "$DIAGNOSTIC_LOG"
        ;;
esac

mkdir -p "$STATE_DIR"
nohup "$PYTHON_BIN" "$APP_ENTRY" "$@" >>"$DIAGNOSTIC_LOG" 2>&1 </dev/null &
exit 0
