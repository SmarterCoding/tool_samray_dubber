import os
import sys

# 1. Force FFmpeg backend for hardware-accelerated playback on macOS
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"

def _resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


if getattr(sys, "frozen", False):
    os.environ["PATH"] = _resource_path("bin") + os.pathsep + os.environ.get("PATH", "")
    font_dir = _resource_path("assets/fonts")
    if os.path.isdir(font_dir):
        os.environ.setdefault("QT_QPA_FONTDIR", font_dir)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFontDatabase, QFont, QIcon

from app.theme import APP_STYLESHEET
from app.ui.main_window import MainWindow


def load_khmer_font(app: QApplication):
    families = QFontDatabase.families()
    for candidate in ("Khmer OS", "Khmer OS System", "Noto Sans Khmer",
                      "Kantumruy Pro", "Battambang"):
        if candidate in families:
            app.setFont(QFont(candidate, 10))
            return candidate
    default = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    default.setPointSize(10)
    app.setFont(default)
    return default.family()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CHAMNAN DUBBER PRO")
    app.setApplicationDisplayName("SAMRAY DUBBER PRO")

    icon_path = _resource_path("assets/icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setStyleSheet(APP_STYLESHEET)
    load_khmer_font(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())