"""
Music Tools GUI — Log Panel  v0.1
===================================
Reusable QTextEdit-based log widget.

Usage
-----
    from gui.log_panel import LogPanel

    log = LogPanel(parent=self)
    log.info("Scan started")
    log.success("Found 12 duplicates")
    log.warning("3 files skipped")
    log.error("Could not read: bad_file.mp3")
    log.clear()

The widget exposes an append_callback() method that returns a plain
callable suitable for passing as log_callback= to any script's run_*
function:

    cb = log.append_callback()
    run_sort_cd_tracks(..., log_callback=cb)
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QTextCursor

from gui.theme import COLOURS


# ── Thread-safe bridge ──────────────────────────────────────────────────────
# Scripts run in QThread and cannot call Qt widgets directly.
# They call LogBridge.message(text) → signal → LogPanel.append_html (main thread).

class LogBridge(QObject):
    """Emit log messages from any thread; connect to the main-thread log panel."""
    message = Signal(str, str)   # (html_line, level)


# ── Log panel widget ─────────────────────────────────────────────────────────

class LogPanel(QWidget):
    """
    A collapsible log panel that sits at the bottom of the main window.

    Colours:
        info    — default text colour
        success — teal
        warning — yellow
        error   — red
        ts      — dim green (timestamp)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._bridge = LogBridge()
        self._bridge.message.connect(self._on_bridge_message)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(28)
        header.setStyleSheet(
            f"background: {COLOURS['surface']}; "
            f"border-top: 1px solid {COLOURS['border']};"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 0, 8, 0)

        self._title_label = QLabel("Output Log")
        self._title_label.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt; border: none; background: transparent;"
        )

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("secondary")
        self._clear_btn.setFixedHeight(20)
        self._clear_btn.setFixedWidth(50)
        self._clear_btn.setStyleSheet(
            f"font-size: 8pt; padding: 1px 6px; background: {COLOURS['input_bg']}; "
            f"color: {COLOURS['text_muted']}; border: 1px solid {COLOURS['border']}; border-radius: 2px;"
        )
        self._clear_btn.clicked.connect(self.clear)

        h_layout.addWidget(self._title_label)
        h_layout.addStretch()
        h_layout.addWidget(self._clear_btn)

        # Text area
        self._text = QTextEdit()
        self._text.setObjectName("log")
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        layout.addWidget(header)
        layout.addWidget(self._text)

    # ── Public API ─────────────────────────────────────────────────────────────

    def info(self, text: str):
        """Append a normal information message."""
        self._append(text, "info")

    def success(self, text: str):
        """Append a success message (teal)."""
        self._append(text, "success")

    def warning(self, text: str):
        """Append a warning message (yellow)."""
        self._append(text, "warning")

    def error(self, text: str):
        """Append an error message (red)."""
        self._append(text, "error")

    def clear(self):
        """Clear all log content."""
        self._text.clear()

    def append_callback(self, level: str = "info"):
        """
        Return a plain callable (str) -> None that appends to the log.
        Safe to call from any thread.

        Example:
            run_sort_cd_tracks(..., log_callback=log.append_callback())
        """
        def cb(msg: str):
            self._bridge.message.emit(msg, level)
        return cb

    def threadsafe_info(self, msg: str):
        """Thread-safe info append — safe to call from QThread."""
        self._bridge.message.emit(msg, "info")

    def threadsafe_success(self, msg: str):
        self._bridge.message.emit(msg, "success")

    def threadsafe_warning(self, msg: str):
        self._bridge.message.emit(msg, "warning")

    def threadsafe_error(self, msg: str):
        self._bridge.message.emit(msg, "error")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _append(self, text: str, level: str):
        """Append a coloured HTML line. Must be called from the main thread."""
        colour = COLOURS.get(f"log_{level}", COLOURS["log_info"])
        ts_colour = COLOURS["log_ts"]
        ts = datetime.now().strftime("%H:%M:%S")
        # Escape HTML special chars
        safe = (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
        html = (f'<span style="color:{ts_colour};">[{ts}]</span> '
                f'<span style="color:{colour};">{safe}</span>')
        self._text.append(html)
        # Auto-scroll to bottom
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)

    def _on_bridge_message(self, msg: str, level: str):
        """Slot: receives messages from the LogBridge (main thread)."""
        self._append(msg, level)
