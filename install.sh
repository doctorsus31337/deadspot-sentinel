#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/deadspot-sentinel"
BIN_DIR="${HOME}/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$APPLICATIONS_DIR"
cp -R "$SOURCE_DIR/deadspot_sentinel" "$INSTALL_DIR/"
cp -R "$SOURCE_DIR/assets" "$INSTALL_DIR/"
cp "$SOURCE_DIR/run.py" "$SOURCE_DIR/requirements.txt" "$SOURCE_DIR/updater.sh" "$INSTALL_DIR/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

cp "$SOURCE_DIR/launcher.sh" "$BIN_DIR/deadspot-sentinel"
chmod +x "$BIN_DIR/deadspot-sentinel"

cat > "$APPLICATIONS_DIR/deadspot-sentinel.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=DeadSpot Sentinel
Comment=Fast dual-Wi-Fi connectivity monitor
Exec=$BIN_DIR/deadspot-sentinel
Icon=$INSTALL_DIR/assets/deadspot-sentinel.svg
Terminal=false
Categories=Network;Utility;
EOF

if [[ "${1:-}" == "--autostart" ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$APPLICATIONS_DIR/deadspot-sentinel.desktop" "$AUTOSTART_DIR/deadspot-sentinel.desktop"
    echo "Autostart enabled."
fi

echo "Installed DeadSpot Sentinel."
echo "Launch it with: $BIN_DIR/deadspot-sentinel"
