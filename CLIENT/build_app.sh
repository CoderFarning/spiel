#!/bin/bash
# ZombieClash - Ein-Klick Build

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"
APP_PATH="$DIST_DIR/$APP_NAME.app"
ZIP_PATH="$PROJECT_DIR/$APP_NAME.zip"
LOGO_FILE="$PROJECT_DIR/Logo.png"
ICONSET_DIR="$BUILD_DIR/icon.iconset"
ICNS_FILE="$BUILD_DIR/ZombieClash.icns"

echo "=== ZombieClash Build ==="
echo ""

# 1) Aufraeumen
echo "[1/7] Alte Build-Dateien entfernen..."
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/$APP_NAME.spec"
mkdir -p "$BUILD_DIR"

# 2) Logo zu .icns (macOS nativ)
if [ -f "$LOGO_FILE" ]; then
    echo "[2/7] Erstelle App-Icon aus Logo.png..."
    mkdir -p "$ICONSET_DIR"
    sips -z 16 16     "$LOGO_FILE" --out "$ICONSET_DIR/icon_16x16.png" > /dev/null 2>&1
    sips -z 32 32     "$LOGO_FILE" --out "$ICONSET_DIR/icon_16x16@2x.png" > /dev/null 2>&1
    sips -z 32 32     "$LOGO_FILE" --out "$ICONSET_DIR/icon_32x32.png" > /dev/null 2>&1
    sips -z 64 64     "$LOGO_FILE" --out "$ICONSET_DIR/icon_32x32@2x.png" > /dev/null 2>&1
    sips -z 128 128   "$LOGO_FILE" --out "$ICONSET_DIR/icon_128x128.png" > /dev/null 2>&1
    sips -z 256 256   "$LOGO_FILE" --out "$ICONSET_DIR/icon_128x128@2x.png" > /dev/null 2>&1
    sips -z 256 256   "$LOGO_FILE" --out "$ICONSET_DIR/icon_256x256.png" > /dev/null 2>&1
    sips -z 512 512   "$LOGO_FILE" --out "$ICONSET_DIR/icon_256x256@2x.png" > /dev/null 2>&1
    sips -z 512 512   "$LOGO_FILE" --out "$ICONSET_DIR/icon_512x512.png" > /dev/null 2>&1
    sips -z 1024 1024 "$LOGO_FILE" --out "$ICONSET_DIR/icon_512x512@2x.png" > /dev/null 2>&1
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"
    echo "  Icon erstellt"
else
    echo "[2/7] Kein Logo.png gefunden, kein Icon"
fi

# 3) Bauen
echo "[3/7] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

ICON_ARG=""
if [ -f "$ICNS_FILE" ]; then
    ICON_ARG="--icon $ICNS_FILE"
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

# 4) Icon in die App einbetten
if [ -f "$ICNS_FILE" ]; then
    echo "[4/7] Icon in App einbetten..."
    mkdir -p "$APP_PATH/Contents/Resources"
    cp "$ICNS_FILE" "$APP_PATH/Contents/Resources/AppIcon.icns"
    if command -v /usr/libexec/PlistBuddy &> /dev/null; then
        /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon.icns" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
    fi
else
    echo "[4/7] Uebersprungen (kein Icon)"
fi

# 5) Signieren
echo "[5/7] Signiere die App..."
find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || {
    echo "  Deep-Sign fehlgeschlagen, versuche alternativ..."
    find "$APP_PATH/Contents/MacOS" -type f -exec codesign --force --sign - {} \; 2>/dev/null || true
    codesign --force --sign - "$APP_PATH" 2>/dev/null || true
}

# 6) ZIP erstellen
echo "[6/7] Erstelle ZIP im Spiel-Ordner..."
cd "$DIST_DIR"
rm -f "$ZIP_PATH"
find . -name ".DS_Store" -delete
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$ZIP_PATH"

# 7) Icon auf die ZIP-Datei setzen
if [ -f "$ICNS_FILE" ]; then
    echo "[7/7] Setze Icon auf ZIP-Datei..."
    # Icon in die Resource Fork der ZIP kopieren
    cp "$ICNS_FILE" "$ZIP_PATH/../${APP_NAME}.icns"
    DeRez -only icns "$ICNS_FILE" > "$BUILD_DIR/icon.r" 2>/dev/null && \
    Rez "$BUILD_DIR/icon.r" -o "$ZIP_PATH"/..namedfork/rsrc 2>/dev/null && \
    SetFile -a C "$ZIP_PATH" 2>/dev/null && \
    echo "  ZIP-Icon gesetzt!" || echo "  Xcode Tools fehlen - Icon nur in der App"
    rm -f "$ZIP_PATH/../${APP_NAME}.icns"
else
    echo "[7/7] Uebersprungen"
fi

echo ""
echo "=== Fertig! ==="
echo ""
echo "App:   $ZIP_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$ZIP_PATH""
