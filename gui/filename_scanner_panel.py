"""
Music Tools GUI -- Filename Scanner Panel  v0.2
================================================
GUI panel for filename_scanner/scan_music_filenames.py.

Folder picker -> Scan -> results table (read-only, no apply).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS
from gui._scan_mixin import ScanTimerMixin

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from filename_scanner.scan_music_filenames import run_scan_music_filenames
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if "ok" in s or "clean" in s:
        return COLOURS.get("log_success")
    if "error" in s:
        return COLOURS.get("log_error")
    if "flag" in s or "issue" in s:
        return COLOURS.get("log_warning")
    return None


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self.folder = folder

    def run(self):
        try:
            result = run_scan_music_filenames(
                folder=self.folder,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class FilenameScannerPanel(ScanTimerMixin, QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_browse_folder: str = ""
        self._worker: _Worker | None = None
        self._scan_mixin_init()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']};"
            f"border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Filename Scanner")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Flags filenames that look messy and tracks cleanup progress over time")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(16)
        outer.addWidget(body, stretch=1)

        folder_box = QGroupBox("Folder")
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select a folder to scan...")
        self._folder_edit.editingFinished.connect(self._validate_folder_path)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        folder_layout.addWidget(self._folder_edit, stretch=1)
        folder_layout.addWidget(browse_btn)
        body_layout.addWidget(folder_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn = QPushButton("Scan")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self._run_btn)
        btn_row.addStretch()
        body_layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {COLOURS['border']}; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {COLOURS['accent']}; border-radius: 3px; }}"
        )
        body_layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._status_lbl)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Folder", "Filename", "Issues"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid {COLOURS['border']};"
            f"background: {COLOURS['surface']}; alternate-background-color: {COLOURS['bg']}; }}"
            f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
            f"color: {COLOURS['text_muted']}; padding: 4px 8px;"
            f"border: none; border-bottom: 1px solid {COLOURS['border']}; font-size: 9pt; }}"
        )
        body_layout.addWidget(self._table, stretch=1)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan",
            (
            self._last_browse_folder
            or self._folder_edit.text()
            or str(Path.home())
        ),
        )
        if folder:
            self._last_browse_folder = folder
            self._folder_edit.setText(folder)
            self._table.setRowCount(0)
            self._summary_lbl.setText("")

    def _validate_folder_path(self):
        """Validate a path typed or pasted directly into the folder field."""
        text = self._folder_edit.text().strip()
        if not text:
            return
        path = Path(text)
        if path.exists() and path.is_dir():
            self._last_browse_folder = str(path)
            self._stop_scan_timer()
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._status_lbl.setText("")
            if hasattr(self, "_table"):
                self._table.setRowCount(0)
            if hasattr(self, "_summary_lbl"):
                self._summary_lbl.setText("")
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _on_run(self):
        if not self._folder_edit.text().strip():
            self.log_message.emit("Filename Scanner: no folder selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Filename Scanner: script not found — check project structure.", "error"
            )
            return
        folder = Path(self._folder_edit.text().strip())
        self._run_btn.setEnabled(False)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Scanning...")
        self._start_scan_timer()
        self.log_message.emit(f"Filename Scanner: scanning — {folder}", "info")

        self._worker = _Worker(folder, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        self._on_scan_progress(current, total, message)

    def _on_finished(self, result: dict):
        self._stop_scan_timer()
        self._run_btn.setEnabled(True)
        self._progress.setValue(100)
        self._status_lbl.setText("")

        total   = result.get("total_scanned", 0)
        flagged = result.get("flagged", 0)
        skipped = result.get("skipped", 0)
        reports = result.get("report_paths", [])

        results = result.get("results", [])
        self._populate_table(results)

        summary = f"Scanned: {total}  |  Flagged: {flagged}  |  Skipped: {skipped}"
        self._summary_lbl.setText(summary)
        level = "warning" if flagged else "success"
        self.log_message.emit(f"Filename Scanner complete — {summary}", level)
        for rp in reports:
            self.log_message.emit(f"Report: {rp}", "info")

    def _on_error(self, message: str):
        self._stop_scan_timer()
        self._run_btn.setEnabled(True)
        self.log_message.emit(f"Filename Scanner error: {message}", "error")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            fg = COLOURS.get("log_warning")
            vals = [
                row.get("folder", row.get("Folder", "")),
                row.get("filename", row.get("Filename", "")),
                row.get("issues", row.get("Issues", "")),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
