
#!/bin/bash

set -e

APP_NAME="SamrayDubberPro"
VERSION="1.0.0"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

APP_PATH="$ROOT/dist/macos/$APP_NAME.app"
PACKAGE_DIR="$ROOT/release/macos"
DMG_NAME="$APP_NAME-macos.dmg"

mkdir -p "$PACKAGE_DIR"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: Application not found: $APP_PATH"
    exit 1
fi

TEMP_DIR="$(mktemp -d)"

echo "Preparing macOS DMG..."

cp -R "$APP_PATH" "$TEMP_DIR/"

ln -s /Applications "$TEMP_DIR/Applications"

echo "Creating DMG..."

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$TEMP_DIR" \
    -ov \
    -format UDZO \
    "$PACKAGE_DIR/$DMG_NAME"

rm -rf "$TEMP_DIR"

echo "DMG created successfully!"
echo "$PACKAGE_DIR/$DMG_NAME"
