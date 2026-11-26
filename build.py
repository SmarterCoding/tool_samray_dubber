
import os
import sys
import platform
import subprocess
from pathlib import Path


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

APP_NAME = "SamrayDubberPro"
APP_VERSION = "1.0.0"
BUNDLE_ID = "com.chamnan.samraydubberpro"

MAIN_FILE = ROOT / "main.py"

ASSETS_DIR = ROOT / "assets"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

SYSTEM = platform.system().lower()


# ============================================================
# PLATFORM DETECTION
# ============================================================

if SYSTEM == "darwin":

    TARGET = "macos"

    ICON_CANDIDATES = [
        ROOT / "samray.icns",
        ASSETS_DIR / "samray.icns",
        ASSETS_DIR / "icons" / "icon.icns",
    ]

elif SYSTEM == "windows":

    TARGET = "windows"

    ICON_CANDIDATES = [
        ASSETS_DIR / "icon.ico",
        ASSETS_DIR / "icons" / "icon.ico",
    ]

elif SYSTEM == "linux":

    TARGET = "linux"

    ICON_CANDIDATES = [
        ASSETS_DIR / "icon.png",
        ASSETS_DIR / "icons" / "icon.png",
    ]

else:

    raise RuntimeError(
        f"Unsupported operating system: {SYSTEM}"
    )


# ============================================================
# FIND APPLICATION ICON
# ============================================================

def find_icon():

    for icon in ICON_CANDIDATES:

        if icon.is_file():

            print(f"[OK] Application icon: {icon}")

            return icon

    expected = "\n".join(
        f"  - {path}" for path in ICON_CANDIDATES
    )

    raise FileNotFoundError(
        f"""
Application icon not found!

Platform: {TARGET}

Expected one of these files:

{expected}

Please prepare the correct icon for your platform.
"""
    )


# ============================================================
# VALIDATE PROJECT
# ============================================================

def validate_project():

    print("\nChecking project files...")

    if not MAIN_FILE.is_file():

        raise FileNotFoundError(
            f"Main Python file not found: {MAIN_FILE}"
        )

    if not ASSETS_DIR.is_dir():

        raise FileNotFoundError(
            f"Assets directory not found: {ASSETS_DIR}"
        )

    if not (ROOT / "requirements.txt").is_file():

        print("[WARNING] requirements.txt not found")

    print("[OK] Main file")
    print("[OK] Assets directory")


# ============================================================
# BUILD APPLICATION
# ============================================================

def build():

    print("\n" + "=" * 60)
    print(f" BUILDING {APP_NAME}")
    print("=" * 60)

    print(f"Application : {APP_NAME}")
    print(f"Version     : {APP_VERSION}")
    print(f"Platform    : {TARGET}")
    print(f"Python      : {sys.version.split()[0]}")
    print(f"Project     : {ROOT}")

    validate_project()

    ICON = find_icon()

    # --------------------------------------------------------
    # OUTPUT DIRECTORIES
    # --------------------------------------------------------

    OUTPUT_DIR = DIST_DIR / TARGET
    WORK_DIR = BUILD_DIR / TARGET

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # PYINSTALLER COMMAND
    # --------------------------------------------------------

    args = [

        sys.executable,
        "-m",
        "PyInstaller",

        "--clean",
        "--noconfirm",

        # Desktop application
        "--windowed",
        "--onedir",

        # Application information
        "--name",
        APP_NAME,

        "--icon",
        str(ICON),

        # Include application resources
        "--add-data",
        f"{ASSETS_DIR}{os.pathsep}assets",

        # Build output
        "--distpath",
        str(OUTPUT_DIR),

        "--workpath",
        str(WORK_DIR),

        # Python entry point
        str(MAIN_FILE),
    ]

    # --------------------------------------------------------
    # MACOS CONFIGURATION
    # --------------------------------------------------------

    if TARGET == "macos":

        args.extend([

            "--osx-bundle-identifier",
            BUNDLE_ID,

        ])

    # --------------------------------------------------------
    # BUILD
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print(" RUNNING PYINSTALLER")
    print("=" * 60 + "\n")

    subprocess.run(
        args,
        cwd=ROOT,
        check=True,
    )

    # --------------------------------------------------------
    # BUILD RESULT
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print(" BUILD COMPLETED SUCCESSFULLY!")
    print("=" * 60)

    if TARGET == "macos":

        APP_PATH = OUTPUT_DIR / f"{APP_NAME}.app"

        print(f"\nApplication: {APP_PATH}")

        if APP_PATH.exists():

            print("[OK] macOS application created")

            print("\nOpening application...")

            subprocess.run(
                ["open", str(APP_PATH)],
                check=False,
            )

    elif TARGET == "windows":

        APP_PATH = OUTPUT_DIR / APP_NAME / f"{APP_NAME}.exe"

        print(f"\nApplication: {APP_PATH}")

        if APP_PATH.exists():

            print("[OK] Windows executable created")

    elif TARGET == "linux":

        APP_PATH = OUTPUT_DIR / APP_NAME / APP_NAME

        print(f"\nApplication: {APP_PATH}")

        if APP_PATH.exists():

            print("[OK] Linux executable created")

    print("\nBuild directory:", OUTPUT_DIR)
    print("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        build()

    except subprocess.CalledProcessError as error:

        print("\n[BUILD ERROR]")
        print(f"PyInstaller exited with code: {error.returncode}")

        sys.exit(error.returncode)

    except Exception as error:

        print("\n[ERROR]")
        print(error)

        sys.exit(1)
