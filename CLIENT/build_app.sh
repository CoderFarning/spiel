#!/bin/bash
# ============================================================
#  ZombieClash – macOS Build + Sign + Zip
#  Erstellt eine saubere, signierte .app und eine .zip
#  die Apple nicht als "unbekannt" blockt.
# ============================================================
#
#  Benutzung:
#    chmod +x build_app.sh
#    ./build_app.sh
#
#  Voraussetzungen:
#    pip3 install arcade pyinstaller
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="ZombieClash"
APP_PATH="$PROJECT_DIR/dist/$APP_NAME.app"
ZIP_PATH="$PROJECT_DIR/dist/$APP_NAME.zip"

echo "=== ZombieClash Build ==="
echo ""

# 1) Alten Build entfernen
echo "[1/4] Alte Build-Dateien entfernen..."
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR/$APP_NAME.spec"

# 2) PyInstaller-Build
echo "[2/4] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

pyinstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "CLIENT/assets:assets" \
    --osx-bundle-identifier "com.nevenpara.zombieclash" \
    CLIENT/main.py

# 3) Finder-Metadaten entfernen + Ad-Hoc signieren
echo "[3/4] Signiere die App..."
xattr -cr "$APP_PATH"
codesign --force --deep --sign - "$APP_PATH"

# 4) Zip erstellen (ohne .DS_Store und __pycache__)
echo "[4/4] Erstelle ZIP..."
cd "$PROJECT_DIR/dist"
ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$APP_NAME.zip"

echo ""
echo "=== Fertig! ==="
echo "App:   $APP_PATH"
echo "Zip:   $ZIP_PATH"
echo ""
echo "Zum Testen:"
echo "  open \"$APP_PATH\""
echo ""
echo "Hinweis: Fuer volle Apple-Verifizierung (ohne Rechtsklick)"
echo "wird ein Apple Developer Account (\$99/Jahr) fuer Notarisierung benoetigt."