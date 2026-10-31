"""
Music Tools GUI — Entry Point  v0.2
=====================================
Run this file to launch the application:

    python gui/main.py

Or from the project root:

    python -m gui.main

Requirements:
    pip install PySide6
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so imports like
# `from music_tools_common import ...` work from anywhere.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Must stay above the gui.main_window import: scripts must never open a terminal
# menu or a second folder dialog under the GUI, even if one is imported at load time.
import music_tools_common
music_tools_common.RUNNING_IN_GUI = True

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from gui.theme import build_stylesheet, load_gui_config, APP_FONT_FAMILY, APP_FONT_SIZE
from gui.main_window import MainWindow


def main() -> int:
    # High-DPI scaling (default in Qt6, but be explicit for clarity)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Music Tools")
    app.setOrganizationName("Shrutesh")

    # Load saved theme prefs and apply before the window is shown
    cfg = load_gui_config()
    app.setStyleSheet(build_stylesheet(cfg["mode"], cfg["accent"]))
    font = QFont(APP_FONT_FAMILY, APP_FONT_SIZE)
    app.setFont(font)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
