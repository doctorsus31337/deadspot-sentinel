#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-}"
OLD_PID="${2:-}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/deadspot-sentinel"
UPDATE_LOG="$STATE_DIR/update.log"

mkdir -p "$STATE_DIR"
exec >>"$UPDATE_LOG" 2>&1

if [[ -z "$SOURCE_DIR" || ! -f "$SOURCE_DIR/install.sh" || ! -f "$SOURCE_DIR/run.py" ]]; then
    echo "Refusing an incomplete update source: $SOURCE_DIR"
    exit 1
fi
if [[ ! "$OLD_PID" =~ ^[0-9]+$ ]]; then
    echo "Invalid application PID: $OLD_PID"
    exit 1
fi

echo "Waiting for DeadSpot Sentinel process $OLD_PID to exit."
for _attempt in {1..150}; do
    if ! kill -0 "$OLD_PID" 2>/dev/null; then
        break
    fi
    sleep 0.1
done
if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "The previous process did not exit in time; update cancelled."
    exit 1
fi

echo "Installing verified update from $SOURCE_DIR"
/usr/bin/env bash "$SOURCE_DIR/install.sh"
echo "Update installed successfully; relaunching."
"${HOME}/.local/bin/deadspot-sentinel"
