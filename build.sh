#!/bin/bash

set -e

APP_NAME="Chamnan Dubber"

echo "================================"
echo " Building $APP_NAME"
echo "================================"

# Activate environment
source .venv/bin/activate

# Clean previous builds
rm -rf build dist

# Build desktop application
pyinstaller \
    --clean \
    --noconfirm \
    --windowed \
    --onedir \
    --name "$APP_NAME" \
    --icon assets/icons/icon.icns \
    --osx-bundle-identifier com.chamnan.desktop \
    --add-data "assets:assets" \
    main.py

echo ""
echo "================================"
echo " Build completed!"
echo "================================"

open "dist/$APP_NAME.app"