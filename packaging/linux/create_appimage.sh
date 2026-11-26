
#!/bin/bash

set -e

APP_NAME="SamrayDubberPro"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SOURCE="$ROOT/dist/linux/$APP_NAME"

APPDIR="$ROOT/build/linux/AppDir"

RELEASE="$ROOT/release/linux"

mkdir -p "$RELEASE"

if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Linux application not found: $SOURCE"
    exit 1
fi

if [ ! -f "$SOURCE/$APP_NAME" ]; then
    echo "ERROR: Application executable not found"
    exit 1
fi

echo "Preparing AppImage..."

rm -rf "$APPDIR"

mkdir -p "$APPDIR/usr/lib/$APP_NAME"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller onedir output
cp -a "$SOURCE/." "$APPDIR/usr/lib/$APP_NAME/"

# Application launcher
cat > "$APPDIR/usr/bin/samray-dubber-pro" <<'EOF'
#!/bin/sh

APPDIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

exec "$APPDIR/lib/SamrayDubberPro/SamrayDubberPro" "$@"
EOF

chmod +x "$APPDIR/usr/bin/samray-dubber-pro"

# Desktop entry
cat > "$APPDIR/usr/share/applications/samray-dubber-pro.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SamrayDubberPro
Comment=Samray Dubber Pro Desktop Application
Exec=samray-dubber-pro
Icon=samray-dubber-pro
Categories=AudioVideo;Audio;
Terminal=false
EOF

# Icon
cp "$ROOT/assets/icon.png" \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/samray-dubber-pro.png"

cp "$ROOT/assets/icon.png" "$APPDIR/samray-dubber-pro.png"

# AppImage metadata
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh

HERE="$(dirname "$(readlink -f "$0")")"

export PATH="$HERE/usr/bin:$PATH"

exec "$HERE/usr/bin/samray-dubber-pro" "$@"
EOF

chmod +x "$APPDIR/AppRun"

# AppImage desktop entry and icon at root
cp "$APPDIR/usr/share/applications/samray-dubber-pro.desktop" \
   "$APPDIR/samray-dubber-pro.desktop"

# Download linuxdeploy and its AppImage plugin separately
LINUXDEPLOY="$ROOT/linuxdeploy-x86_64.AppImage"
PLUGIN="$ROOT/linuxdeploy-plugin-appimage-x86_64.AppImage"

if [ ! -x "$LINUXDEPLOY" ] || [ ! -x "$PLUGIN" ]; then
    echo "ERROR: linuxdeploy or AppImage plugin missing."
    exit 1
fi

export ARCH=x86_64

"$LINUXDEPLOY" \
    --appdir "$APPDIR" \
    --output appimage \
    --desktop-file "$APPDIR/samray-dubber-pro.desktop" \
    --icon-file "$APPDIR/samray-dubber-pro.png"

# Move generated AppImage to release directory
find "$ROOT" -maxdepth 1 -name "*.AppImage" \
    -exec mv {} "$RELEASE/$APP_NAME-linux.AppImage" \;

echo "AppImage created:"
echo "$RELEASE/$APP_NAME-linux.AppImage"
