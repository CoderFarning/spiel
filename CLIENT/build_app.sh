#!/bin/bash
# ZombieClash - Ein-Klick Build

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
echo "[1/5] Aufraeumen..."
umount /tmp/zombieclash_mount 2>/dev/null || true
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/$APP_NAME.spec" "$PROJECT_DIR/$APP_NAME.dmg"
mkdir -p "$BUILD_DIR"

# 2) Logo zu .icns
echo "[2/5] Icon aus Logo.png erstellen..."
if [ -f "$LOGO_FILE" ]; then
    mkdir -p "$ICONSET_DIR"
    sips -z 16 16     "$LOGO_FILE" --out "$ICONSET_DIR/icon_16x16.png" 2>/dev/null
    sips -z 32 32     "$LOGO_FILE" --out "$ICONSET_DIR/icon_16x16@2x.png" 2>/dev/null
    sips -z 32 32     "$LOGO_FILE" --out "$ICONSET_DIR/icon_32x32.png" 2>/dev/null
    sips -z 64 64     "$LOGO_FILE" --out "$ICONSET_DIR/icon_32x32@2x.png" 2>/dev/null
    sips -z 128 128   "$LOGO_FILE" --out "$ICONSET_DIR/icon_128x128.png" 2>/dev/null
    sips -z 256 256   "$LOGO_FILE" --out "$ICONSET_DIR/icon_128x128@2x.png" 2>/dev/null
    sips -z 256 256   "$LOGO_FILE" --out "$ICONSET_DIR/icon_256x256.png" 2>/dev/null
    sips -z 512 512   "$LOGO_FILE" --out "$ICONSET_DIR/icon_256x256@2x.png" 2>/dev/null
    sips -z 512 512   "$LOGO_FILE" --out "$ICONSET_DIR/icon_512x512.png" 2>/dev/null
    sips -z 1024 1024 "$LOGO_FILE" --out "$ICONSET_DIR/icon_512x512@2x.png" 2>/dev/null
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE" 2>/dev/null
    if [ -f "$ICNS_FILE" ]; then
        echo "  OK - Icon erstellt"
    else
        echo "  FEHLER - Icon konnte nicht erstellt werden"
        ICNS_FILE=""
    fi
else
    echo "  KEIN Logo.png gefunden in: $PROJECT_DIR"
    ICNS_FILE=""
fi

# 3) Bauen
echo "[3/5] PyInstaller baut App..."
cd "$PROJECT_DIR"

ICON_ARG=""
if [ -n "$ICNS_FILE" ]; then
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

if [ ! -d "$APP_PATH" ]; then
    echo "FEHLER: App wurde nicht erstellt!"
    exit 1
fi

# 4) Icon einbetten + Signieren (fehlerfreundlich)
echo "[4/5] Icon einbetten + Signieren..."
if [ -n "$ICNS_FILE" ] && [ -f "$ICNS_FILE" ]; then
    mkdir -p "$APP_PATH/Contents/Resources"
    cp "$ICNS_FILE" "$APP_PATH/Contents/Resources/AppIcon.icns"
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon.icns" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
fi

# Signieren (wird nicht abgebrochen bei Fehlern)
find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || codesign --force --sign - "$APP_PATH" 2>/dev/null || echo "  Signieren fehlgeschlagen - App funktioniert trotzdem"

# 5) ZIP erstellen (IMMER, auch wenn Signieren fehlschlaegt)
echo "[5/5] ZIP erstellen..."
cd "$DIST_DIR"
find . -name ".DS_Store" -delete
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$ZIP_PATH"

# Finder Icon Cache aktualisieren damit das neue Icon sofort sichtbar ist
killall Finder 2>/dev/null || true

echo ""
echo "=== Fertig! ==="
echo ""
echo "App:  $APP_PATH"
echo "ZIP:  $ZIP_PATH"
echo ""
echo "Oeffnen mit:"
echo "  open "$ZIP_PATH""
echo ""
echo "Bei anderen Macs (damaged Meldung):"
echo "  Rechtsklick auf .app -> Oeffnen"
