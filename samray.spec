# samray.spec — PyInstaller build spec for SAMRAY DUBBER PRO

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# PyInstaller + PySide6 can exceed Python's default recursion limit.
sys.setrecursionlimit(sys.getrecursionlimit() * 5)  # [7†L8-L9]


block_cipher = None

# ---------------------------------------------------------------------------
# Bundle FFmpeg + FFprobe from the build environment
# ---------------------------------------------------------------------------
# If you installed FFmpeg with Homebrew, its path is one of:
#   /opt/homebrew/bin/ffmpeg      (Apple Silicon)
#   /usr/local/bin/ffmpeg         (Intel)
# Or use the static binaries from https://evermeet.cx/ffmpeg/ and put them
# under ./vendor/ffmpeg/ inside the project.
FFMPEG_DIR = os.path.abspath("vendor/ffmpeg")
if not os.path.isdir(FFMPEG_DIR):
    # Prefer Homebrew's ffmpeg-full: the regular ffmpeg bottle may be
    # built without libass, which is required for subtitle burn-in.
    for candidate in (
        "/opt/homebrew/opt/ffmpeg-full/bin",
        "/usr/local/opt/ffmpeg-full/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ):
        if os.path.exists(os.path.join(candidate, "ffmpeg")):
            FFMPEG_DIR = candidate
            break

ffmpeg_binaries = [
    (os.path.join(FFMPEG_DIR, "ffmpeg"),  "bin"),
    (os.path.join(FFMPEG_DIR, "ffprobe"), "bin"),
]

# ---------------------------------------------------------------------------
# QtAwesome ships its TTF files as package data — collect them explicitly
# ---------------------------------------------------------------------------
qta_datas = collect_data_files("qtawesome")

# ---------------------------------------------------------------------------
# Project assets (Khmer fonts, icons, etc.)
# ---------------------------------------------------------------------------
project_datas = [
    ("assets", "assets"),               # adjust if your assets folder is elsewhere
    ("samray.icns", "."),
]
# Include any khmer font TTF/OTF you ship
for f in ("assets/fonts/KhmerOS.ttf", "assets/fonts/NotoSansKhmer-Regular.ttf"):
    if os.path.exists(f):
        project_datas.append((f, "assets/fonts"))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=ffmpeg_binaries,                       # [1†L5-L8]
    datas=project_datas + qta_datas,
    hiddenimports=[
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "faster_whisper",
        "ctranslate2",
        "edge_tts",
        "deep_translator",
        "qtawesome",
        "pydub",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "PySide6.QtWebEngineCore"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SAMRAY DUBBER PRO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                          # CRITICAL for PySide6  [0†L32-L34]
    console=False,                      # --windowed equivalent
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,                   # "arm64", "x86_64", or None
    codesign_identity=None,             # set via CLI for notarized builds
    entitlements_file=None,
    icon="samray.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SAMRAY DUBBER PRO",
)

app = BUNDLE(
    coll,
    name="SAMRAY DUBBER PRO.app",
    icon="samray.icns",
    bundle_identifier="com.samray.dubberpro",
    info_plist={
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription":
            "SAMRAY DUBBER PRO does not record audio but needs access "
            "if you add microphone-based features.",
        "LSMinimumSystemVersion": "12.0",
        "CFBundleDisplayName": "SAMRAY DUBBER PRO",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
    },
)