#!/bin/bash
# ============================================================
#  ZombieClash – macOS Build + Sign
#  Erstellt eine saubere, signierte .app
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

echo "=== ZombieClash Build ==="
echo ""

# 1) Alten Build entfernen
echo "[1/4] Alte Build-Dateien entfernen..."
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR/$APP_NAME.spec"

# 2) PyInstaller-Build (main.py ist der Einstiegspunkt!)
echo "[2/4] Baue App mit PyInstaller..."
cd "$PROJECT_DIR"

python3 -m PyInstaller     --name "$APP_NAME"     --windowed     --onedir     --noconfirm     --clean     --add-data "CLIENT/assets:assets"     --hidden-import SERVER.server     --osx-bundle-identifier "com.nevenpara.zombieclash"     CLIENT/main.py

# 3) Finder-Metadaten entfernen + Ad-Hoc signieren
echo "[3/4] Signiere die App..."
xattr -cr "$APP_PATH"
codesign --force --deep --sign - "$APP_PATH"

echo ""
echo "=== Fertig! ==="
echo "App:   $APP_PATH"
echo ""
echo "Zum Oeffnen:"
echo "  open "$APP_PATH""
echo ""
echo "Die Datei zum Oeffnen ist:"
echo "  dist/ZombieClash.app"
