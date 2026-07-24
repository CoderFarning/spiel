#!/bin/bash
# ZombieClash - Ein-Klick Build
# Erstellt eine DMG mit App-Icon

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$PROJECT_DIR/$APP_NAME.dmg"
LOGO_FILE="$PROJECT_DIR/Logo.png"
ICONSET_DIR="$BUILD_DIR/icon.iconset"
ICNS_FILE="$BUILD_DIR/ZombieClash.icns"

MOUNT_DIR="/tmp/zombieclash_mount"

echo "=== ZombieClash Build ==="
echo ""

# 1) Aufraeumen
echo "[1/6] Alte Build-Dateien entfernen..."
umount "$MOUNT_DIR" 2>/dev/null || true
rm -rf "$DIST_DIR" "$BUILD_DIR" "$PROJECT_DIR/$APP_NAME.spec"
mkdir -p "$BUILD_DIR"

# 2) Logo zu .icns (macOS nativ)
if [ -f "$LOGO_FILE" ]; then
    echo "[2/6] Erstelle App-Icon aus Logo.png..."
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
    echo "[2/6] Kein Logo.png gefunden"
fi

# 3) Bauen
echo "[3/6] Baue App mit PyInstaller..."
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

# 4) Icon einbetten + Signieren
if [ -f "$ICNS_FILE" ]; then
    echo "[4/6] Icon einbetten + Signieren..."
    mkdir -p "$APP_PATH/Contents/Resources"
    cp "$ICNS_FILE" "$APP_PATH/Contents/Resources/AppIcon.icns"
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon.icns" "$APP_PATH/Contents/Info.plist" 2>/dev/null || true
else
    echo "[4/6] Signieren..."
fi

find "$APP_PATH" -type f -exec xattr -cr {} \; 2>/dev/null || true
xattr -cr "$APP_PATH" 2>/dev/null || true
sleep 1
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || {
    find "$APP_PATH/Contents/MacOS" -type f -exec codesign --force --sign - {} \; 2>/dev/null || true
    codesign --force --sign - "$APP_PATH" 2>/dev/null || true
}

# 5) DMG erstellen (statt ZIP - besser fuer macOS!)
echo "[5/6] Erstelle DMG..."
rm -f "$DMG_PATH"
mkdir -p "$MOUNT_DIR"
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$APP_PATH" \
    -ov -format UDZO \
    "$DMG_PATH"

# 6) DMG Icon setzen
echo "[6/6] Setze DMG Icon..."
if [ -f "$ICNS_FILE" ]; then
    hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_DIR" -quiet 2>/dev/null || true
    if [ -d "$MOUNT_DIR" ]; then
        cp "$ICNS_FILE" "$MOUNT_DIR/.VolumeIcon.icns"
        SetFile -a C "$MOUNT_DIR" 2>/dev/null || true
        sleep 1
        hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
    fi
fi

# DMG Icon setzen (auf die Datei selbst)
if [ -f "$ICNS_FILE" ] && command -v SetFile &> /dev/null; then
    DeRez -only icns "$ICNS_FILE" > "$BUILD_DIR/icon.r" 2>/dev/null && \
    Rez "$BUILD_DIR/icon.r" -o "$DMG_PATH"/..namedfork/rsrc 2>/dev/null && \
    SetFile -a C "$DMG_PATH" 2>/dev/null || true
fi

echo ""
echo "=== Fertig! ==="
echo ""
echo "Deine App: $DMG_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$DMG_PATH""
echo ""
echo "TIPP: Bei anderen Macs (damaged Meldung):"
echo "  Rechtsklick auf die .app -> Oeffnen"
echo "  Oder: xattr -cr /Pfad/zur/App && codesign --force --deep --sign - /Pfad/zur/App"
