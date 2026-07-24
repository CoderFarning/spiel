#!/bin/bash
# ZombieClash - Ein-Klick Build
# Erstellt ZombieClash.zip direkt im Spiel-Ordner

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"
APP_PATH="$DIST_DIR/$APP_NAME.app"
ZIP_PATH="$PROJECT_DIR/$APP_NAME.zip"

echo "=== ZombieClash Build ==="
echo ""
# 1) Aufraeumen
echo "[1/4] Alte Build-Dateien entfernen..."
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/$APP_NAME.spec"

# 2) Bauen
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

# 3) Signieren
echo "[3/4] Signiere die App..."
find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || {
    echo "  Deep-Sign fehlgeschlagen, versuche alternativ..."
    find "$APP_PATH/Contents/MacOS" -type f -exec codesign --force --sign - {} \; 2>/dev/null || true
    codesign --force --sign - "$APP_PATH" 2>/dev/null || true
}

# 4) ZIP direkt im Spiel-Ordner
echo "[4/4] Erstelle ZIP im Spiel-Ordner..."
cd "$DIST_DIR"
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$ZIP_PATH"

echo ""
echo "=== Fertig! ==="
echo ""
echo "Deine App: $ZIP_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$ZIP_PATH""
