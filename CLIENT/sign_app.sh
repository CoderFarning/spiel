#!/bin/bash
# ============================================================
#  ZombieClash – macOS App signieren (Ad-Hoc / Entwickler)
# ============================================================
#
#  Benutzung:
#    chmod +x sign_app.sh
#    ./sign_app.sh
#
#  Das Skript sucht automatisch nach ZombieClash.app im
#  build/-Ordner und signiert alle darin enthaltenen
#  Binaries mit den korrekten Entitlements.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="ZombieClash.app"

# App suchen (im build-Ordner)
APP_PATH=""
for candidate in \
    "$SCRIPT_DIR/dist/$APP_NAME" \
    "$SCRIPT_DIR/build/"*"/$APP_NAME" \
    "$SCRIPT_DIR/build/$APP_NAME"; do
    if [ -d "$candidate" ]; then
        APP_PATH="$candidate"
        break
    fi
done

if [ -z "$APP_PATH" ] || [ ! -d "$APP_PATH" ]; then
    echo "FEHLER: $APP_NAME nicht gefunden."
    echo "Bitte zuerst die App bauen (z.B. mit PyInstaller)."
    exit 1
fi

echo "Signiere: $APP_PATH"
echo "-------------------------------------------"

# Entitlements-Datei
ENTITLEMENTS="$SCRIPT_DIR/Entitlements.plist"
if [ ! -f "$ENTITLEMENTS" ]; then
    echo "FEHLER: $ENTITLEMENTS nicht gefunden."
    exit 1
fi

# 1) Zuerst alle Embedded Frameworks / Dylibs signieren
echo "[1/3] Signiere Libraries & Frameworks..."
find "$APP_PATH/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -name "*.framework" \) 2>/dev/null | while read -r lib; do
    echo "  -> $(basename "$lib")"
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$lib" 2>/dev/null || true
done

# 2) Alle ausfuehrbaren Dateien im MacOS-Ordner signieren
echo "[2/3] Signiere Executables..."
find "$APP_PATH/Contents/MacOS" -type f -perm +111 2>/dev/null | while read -r exe; do
    echo "  -> $(basename "$exe")"
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$exe" 2>/dev/null || true
done

# 3) Die .app selbst signieren (deep)
echo "[3/3] Signiere App-Bundle..."
codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP_PATH"

echo "-------------------------------------------"
echo "Erfolgreich signiert!"
echo ""
echo "Jetzt kannst du die App oeffnen:"
echo "  open \"$APP_PATH\""
echo ""
echo "Falls macOS noch immer blockiert:"
echo "  Rechtsklick -> Oeffnen  (nicht Doppelklick)"
echo "  Oder: Systemeinstellungen -> Datenschutz & Sicherheit -> Trotzdem oeffnen"