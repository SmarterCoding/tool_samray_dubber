#!/bin/bash
# Create a lightweight "SAMRAY DUBBER PRO.app" launcher on the Desktop.
#
# This is not a PyInstaller bundle. It is a tiny macOS app wrapper that starts
# main.py with the first Python on this Mac that has PySide6 installed. That
# keeps the Desktop icon working immediately without a multi-gigabyte build.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="SAMRAY DUBBER PRO"
BUILD_DIR="$ROOT/build/desktop"
APP="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
ICON="$ROOT/samray.icns"
DESKTOP="$HOME/Desktop"

if [ ! -f "$ICON" ]; then
    echo "Icon not found: $ICON" >&2
    echo "Run: python3 assets/make_icon.py" >&2
    exit 1
fi

rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES"

cp "$ICON" "$RESOURCES/samray.icns"

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>SAMRAY DUBBER PRO</string>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundleIconFile</key>
    <string>samray.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.samray.dubberpro.launcher</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>SAMRAY DUBBER PRO</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.video</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 SAMRAY DUBBER PRO</string>
</dict>
</plist>
PLIST

printf 'APPL????' > "$CONTENTS/PkgInfo"

cat > "$MACOS/launch" <<LAUNCH
#!/bin/bash
set -u

PROJECT_DIR="$ROOT"
LOG_DIR="\$PROJECT_DIR/output"
LOG="\$LOG_DIR/launcher.log"
mkdir -p "\$LOG_DIR"
cd "\$PROJECT_DIR" || exit 1

# Finder launches apps with a minimal PATH. Add Homebrew and python.org
# locations so FFmpeg, ffprobe and the Python runtime are always found.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.14/bin:\$PATH"

CANDIDATES=(
    "\$PROJECT_DIR/venv/bin/python3"
    "\$PROJECT_DIR/venv/bin/python"
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
)

for PY in "\${CANDIDATES[@]}"; do
    if [ -x "\$PY" ] && "\$PY" -c "import PySide6, qtawesome" >/dev/null 2>&1; then
        echo "--- \$(date) launching with \$PY" >> "\$LOG"
        exec "\$PY" "\$PROJECT_DIR/main.py" >> "\$LOG" 2>&1
    fi
done

osascript -e 'display alert "SAMRAY DUBBER PRO" message "Python 3 with PySide6 was not found. Open Terminal in the project folder and run: python3 -m pip install -r requirements.txt"'
exit 1
LAUNCH

chmod +x "$MACOS/launch"

# Ad-hoc sign the wrapper so macOS treats it as a normal local app.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

# Register the bundle with LaunchServices so the custom icon is picked up.
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
    "$LSREGISTER" -f "$APP" >/dev/null 2>&1 || true
fi

echo "Built: $APP"

if [ ! -d "$DESKTOP" ]; then
    echo "Desktop folder not found; launcher is available at: $APP" >&2
    exit 0
fi

DEST="$DESKTOP/$APP_NAME.app"

# Remove a previous copy. Direct removal can be blocked by macOS privacy
# protection, so fall back to Finder, which has its own Desktop permission.
if [ -e "$DEST" ]; then
    if ! rm -rf "$DEST" 2>/dev/null; then
        osascript <<APPLESCRIPT
tell application "Finder"
    if exists POSIX file "$DEST" as alias then
        delete POSIX file "$DEST" as alias
    end if
end tell
APPLESCRIPT
    fi
fi

# Try a direct copy first. If macOS privacy protection blocks it, ask Finder
# (which has its own Desktop permission) to duplicate the bundle.
if cp -R "$APP" "$DESKTOP/" 2>/dev/null; then
    echo "Copied to: $DEST"
else
    echo "Direct copy blocked; asking Finder to place the app on the Desktop …"
    osascript <<APPLESCRIPT
tell application "Finder"
    set src to POSIX file "$APP" as alias
    set dest to POSIX file "$DESKTOP" as alias
    duplicate src to dest with replacing
end tell
APPLESCRIPT
    echo "Copied to: $DEST (via Finder)"
fi

# Refresh the icon cache for this bundle.
touch "$DEST" 2>/dev/null || true
if [ -x "$LSREGISTER" ]; then
    "$LSREGISTER" -f "$DEST" >/dev/null 2>&1 || true
fi

echo "Done. Double-click '$APP_NAME' on the Desktop to start."
