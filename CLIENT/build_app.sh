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
ICON_FILE="$SCRIPT_DIR/ZombieClash.icns"

echo "=== ZombieClash Build ==="
echo ""

# 1) Aufraeumen
echo "[1/5] Alte Build-Dateien entfernen..."
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/$APP_NAME.spec"

# 2) Bauen
echo "[2/5] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

ICON_ARG=""
if [ -f "$ICON_FILE" ]; then
    ICON_ARG="--icon $ICON_FILE"
    echo "  Icon: $ICON_FILE"
fi

python3 -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "CLIENT/assets:assets" \
    --hidden-import SERVER.server \
    --osx-bundle-identifier "com.nevenpara.zombieclash" \
    $ICON_ARG \
    CLIENT/main.py

# 3) Icon in die App kopieren (falls PyInstaller es nicht tut)
echo "[3/5] Icon setzen..."
if [ -f "$ICON_FILE" ]; then
    mkdir -p "$APP_PATH/Contents/Resources"
    cp "$ICON_FILE" "$APP_PATH/Contents/Resources/AppIcon.icns"
    # Info.plist aktualisieren
    if command -v /usr/libexec/PlistBuddy &> /dev/null; then
        /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon.icns" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
    fi
fi

# 4) Signieren
echo "[4/5] Signiere die App..."
find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || {
    echo "  Deep-Sign fehlgeschlagen, versuche alternativ..."
    find "$APP_PATH/Contents/MacOS" -type f -exec codesign --force --sign - {} \; 2>/dev/null || true
    codesign --force --sign - "$APP_PATH" 2>/dev/null || true
}

# 5) ZIP direkt im Spiel-Ordner (ohne .DS_Store)
echo "[5/5] Erstelle ZIP im Spiel-Ordner..."
cd "$DIST_DIR"
rm -f "$ZIP_PATH"
find . -name ".DS_Store" -delete
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$ZIP_PATH"

echo ""
echo "=== Fertig! ==="
echo ""
echo "Deine App: $ZIP_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$ZIP_PATH""
echo ""
echo "TIPP fuer andere: Falls 'beschaeidgt' kommt:"
echo "  Rechtsklick auf ZombieClash.app -> Oeffnen"
