"""
Music Tools GUI -- Library Dupes Panel  v0.2
=============================================
GUI panel for library_dupes/find_library_dupes.py.

No folder picker (reads from config). Options -> Scan -> results table.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS
from gui._scan_mixin import ScanTimerMixin

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from library_dupes.find_library_dupes import run_find_library_dupes
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if "match" in s or "duplicate" in s:
        return COLOURS.get("log_warning")
    if "error" in s:
        return COLOURS.get("log_error")
    return None


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, use_fp, use_filename, rebuild_cache, parent=None):
        super().__init__(parent)
        self.use_fp         = use_fp
        self.use_filename   = use_filename
        self.rebuild_cache  = rebuild_cache

    def run(self):
        try:
            result = run_find_library_dupes(
                use_fp=self.use_fp,
                use_filename=self.use_filename,
                rebuild_cache=self.rebuild_cache,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class LibraryDupesPanel(ScanTimerMixin, QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
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
        title_lbl = QLabel("Library Dupes")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Finds tracks duplicated across two or more artist folders")
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

        note = QLabel("Uses the organized library folder from Settings (music_config.json).")
        note.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        note.setWordWrap(True)
        body_layout.addWidget(note)

        opts_box = QGroupBox("Matching Options")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(6)
        self._chk_fp = QCheckBox("Audio fingerprint matching")
        self._chk_fp.setChecked(True)
        self._chk_filename = QCheckBox("Filename / metadata matching")
        self._chk_filename.setChecked(True)
        self._chk_rebuild = QCheckBox("Rebuild fingerprint cache")
        opts_layout.addWidget(self._chk_fp)
        opts_layout.addWidget(self._chk_filename)
        opts_layout.addWidget(self._chk_rebuild)
        body_layout.addWidget(opts_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn = QPushButton("Scan for Duplicates")
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

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["File A", "File B", "Score", "Method"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
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

    def _on_run(self):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Library Dupes: script not found — check project structure.", "error"
            )
            return
        self._run_btn.setEnabled(False)
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Scanning library...")
        self._start_scan_timer()
        self.log_message.emit("Library Dupes: scanning...", "info")

        self._worker = _Worker(
            use_fp=self._chk_fp.isChecked(),
            use_filename=self._chk_filename.isChecked(),
            rebuild_cache=self._chk_rebuild.isChecked(),
            parent=self,
        )
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

        matches = result.get("matches", [])
        errors  = result.get("errors", [])
        report  = result.get("report_path")

        self._populate_table(matches)

        summary = f"Duplicate pairs found: {len(matches)}  |  Errors: {len(errors)}"
        self._summary_lbl.setText(summary)
        level = "warning" if matches else "success"
        self.log_message.emit(f"Library Dupes complete — {summary}", level)
        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self._stop_scan_timer()
        self._run_btn.setEnabled(True)
        self.log_message.emit(f"Library Dupes error: {message}", "error")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, matches: list[dict]):
        self._table.setRowCount(0)
        for m in matches:
            r = self._table.rowCount()
            self._table.insertRow(r)
            fg = COLOURS.get("log_warning")
            vals = [
                m.get("file_a", m.get("File A", "")),
                m.get("file_b", m.get("File B", "")),
                str(m.get("score", m.get("Score", ""))),
                m.get("method", m.get("Method", "")),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
