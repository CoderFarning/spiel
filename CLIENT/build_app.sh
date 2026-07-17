#!/bin/bash
# ============================================================
#  ZombieClash – macOS Build + Sign
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"
APP_PATH="$PROJECT_DIR/dist/$APP_NAME.app"

echo "=== ZombieClash Build ==="
echo ""

# 1) Alten Build entfernen
echo "[1/4] Alte Build-Dateien entfernen..."
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR/$APP_NAME.spec"

# 2) PyInstaller-Build
echo "[2/4] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

python3 -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "CLIENT/assets:assets" \
    --hidden-import SERVER.server \
    --osx-bundle-identifier "com.nevenpara.zombieclash" \
    CLIENT/main.py

# 3) Signieren mit xattr-Reset
echo "[3/4] Signiere die App..."
# Alle xattr/Resource Forks entfernen
find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
# Kurz warten damit macOS die Aenderungen verarbeitet
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null
# Falls deep sign fehlschlaegt, einzeln signieren
if [ $? -ne 0 ]; then
    echo "  Deep-Sign fehlgeschlagen, versuche alternativ..."
    find "$APP_PATH/Contents/MacOS" -type f -exec codesign --force --sign - {} \; 2>/dev/null || true
    codesign --force --sign - "$APP_PATH" 2>/dev/null || true
    echo "  Manuelles Signieren abgeschlossen"
fi

echo ""
echo "=== Fertig! ==="
echo "App: $APP_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$APP_PATH""
echo ""
echo "Falls die App nicht oeffnet (Dock-Bouncen ohne Start):"
echo "  1) Rechtsklick auf ZombieClash.app -> Oeffnen"
echo "  2) Oder im Terminal: dist/ZombieClash.app/Contents/MacOS/ZombieClash"
