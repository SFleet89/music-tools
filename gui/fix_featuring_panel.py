"""
Music Tools GUI -- Fix Featuring Tags Panel  v0.1
=================================================
GUI panel for fix_featuring/fix_featuring.py.

Folder picker -> Dry Run -> results table -> Apply.
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

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from fix_featuring.fix_featuring import run_fix_featuring
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if s in ("modified", "would modify"):
        return COLOURS.get("log_success")
    if s == "no featuring":
        return COLOURS.get("text_muted")
    if "error" in s:
        return COLOURS.get("log_error")
    if "skipped" in s:
        return COLOURS.get("log_warning")
    return None


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder: Path, apply: bool, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.apply  = apply

    def run(self):
        try:
            result = run_fix_featuring(
                folder=self.folder,
                apply=self.apply,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class FixFeaturingPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_results: list[dict] = []
        self._worker: _Worker | None = None
        self._build_ui()
        self._set_state("idle")

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']};"
            f"border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Fix Featuring Tags")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Moves featuring credits from the Artist tag into the Title tag")
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

        # Folder picker
        folder_box = QGroupBox("Folder")
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select a folder to scan...")
        self._folder_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        folder_layout.addWidget(self._folder_edit, stretch=1)
        folder_layout.addWidget(browse_btn)
        body_layout.addWidget(folder_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn   = QPushButton("Dry Run")
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setEnabled(False)
        self._run_btn.setFixedHeight(32)
        self._apply_btn.setFixedHeight(32)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS.get('log_success', '#4ec9b0')};"
            f"color: #000; border-radius: 3px; padding: 5px 16px; min-width: 64px; }}"
            f"QPushButton:hover {{ background: #5edfc0; }}"
            f"QPushButton:disabled {{ background: {COLOURS['disabled_bg']};"
            f"color: {COLOURS['disabled_text']}; }}"
        )
        self._run_btn.clicked.connect(self._on_run)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._apply_btn)
        btn_row.addStretch()
        body_layout.addLayout(btn_row)

        # Progress
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

        # Table — shows original vs new tags
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["File", "Original Artist", "New Artist", "Original Title", "Status"]
        )
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
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

    def _set_state(self, state: str):
        if state == "idle":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Dry Run")
            self._apply_btn.setEnabled(False)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._run_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("Running...")
        elif state == "done_dry":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Re-run Dry Run")
            self._apply_btn.setEnabled(bool(self._last_results))
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Dry Run")
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("")

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan",
            self._folder_edit.text() or str(Path.home()),
        )
        if folder:
            self._folder_edit.setText(folder)
            self._set_state("idle")
            self._table.setRowCount(0)
            self._summary_lbl.setText("")

    def _on_run(self):
        if not self._folder_edit.text().strip():
            self.log_message.emit("Fix Featuring: no folder selected.", "warning")
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Fix Featuring: script not found — check project structure.", "error"
            )
            return
        folder = Path(self._folder_edit.text().strip())
        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Applying..." if apply else "Scanning (dry run)...")
        self.log_message.emit(
            f"Fix Featuring: {'apply' if apply else 'dry run'} — {folder}", "info"
        )
        self._worker = _Worker(folder, apply, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(lambda r: self._on_finished(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_lbl.setText(f"Processing: {filename}")

    def _on_finished(self, result: dict, was_apply: bool):
        self._last_results = result.get("results", [])
        self._populate_table(self._last_results)

        modified      = result.get("modified", 0)
        no_featuring  = result.get("no_featuring", 0)
        skipped       = result.get("skipped", 0)
        errors        = result.get("errors", 0)
        report        = result.get("report_path")

        if was_apply:
            summary = f"Modified: {modified}  |  No featuring: {no_featuring}  |  Skipped: {skipped}  |  Errors: {errors}"
            level = "error" if errors else "success"
            self._set_state("done_apply")
        else:
            would = sum(1 for r in self._last_results if "would" in r.get("status", "").lower())
            summary = f"Would modify: {would}  |  No featuring: {no_featuring}  |  Skipped: {skipped}"
            level = "info"
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        self.log_message.emit(f"Fix Featuring {'complete' if was_apply else 'dry run'} — {summary}", level)
        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self.log_message.emit(f"Fix Featuring error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = row.get("status", "")
            fg = _status_fg(status)
            # Show only filename, not full path
            fp = Path(row.get("file_path", ""))
            display_path = fp.name if fp.name else str(fp)
            values = [
                display_path,
                row.get("original_artist", ""),
                row.get("new_artist", ""),
                row.get("original_title", ""),
                status,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
