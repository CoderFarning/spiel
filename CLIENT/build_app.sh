#!/bin/bash
# ============================================================
#  ZombieClash – Komplett-Build + Signierung fuer macOS
# ============================================================
#
#  Benutzung:
#    chmod +x build_app.sh
#    ./build_app.sh
#
#  Voraussetzungen:
#    - Python 3.13 installiert
#    - arcade und pyinstaller installiert:
#      pip install arcade pyinstaller
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"

echo "=== ZombieClash Build ==="
echo ""

# 1) PyInstaller-Build
echo "[1/2] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

pyinstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "CLIENT/assets:assets" \
    --icon "CLIENT/assets/AppIcon.icns" \
    --osx-bundle-identifier "com.nevenpara.zombieclash" \
    CLIENT/main.py

echo ""
echo "[2/2] Signiere die App..."

# 2) Sign-Skript aufrufen
bash "$SCRIPT_DIR/sign_app.sh"

echo ""
echo "=== Fertig! ==="
echo "Die App liegt hier:"
echo "  $PROJECT_DIR/dist/$APP_NAME.app"