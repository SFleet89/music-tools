"""
Music Tools GUI -- Rename CD Folders Panel  v0.1
=================================================
GUI panel for rename_cd_folders/rename_cd_folders.py.

Finds folders named "CD #" (with a space) and renames them to "CD#" (no space).
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
    from rename_cd_folders.rename_cd_folders import run_rename_cd_folders
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if s in ("renamed",):
        return COLOURS.get("log_success")
    if s in ("would rename",):
        return COLOURS.get("log_success")
    if "error" in s:
        return COLOURS.get("log_error")
    if "skip" in s:
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
            result = run_rename_cd_folders(
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


class RenameCdFoldersPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_results: list[dict] = []
        self._last_browse_folder: str = ""
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
        title_lbl = QLabel("Rename CD Folders")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Removes the space between CD and number  (CD 1 → CD1)")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        # Body
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
        self._folder_edit.editingFinished.connect(self._validate_folder_path)
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

        # Progress bar
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

        # Results table: Parent Folder / Old Name / New Name / Status
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Parent Folder", "Old Name", "New Name", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
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
            (
            self._last_browse_folder
            or self._folder_edit.text()
            or str(Path.home())
        ),
        )
        if folder:
            self._last_browse_folder = folder
            self._folder_edit.setText(folder)
            self._set_state("idle")
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
            self._set_state("idle")
            if hasattr(self, "_table"):
                self._table.setRowCount(0)
            if hasattr(self, "_summary_lbl"):
                self._summary_lbl.setText("")
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _on_run(self):
        if not self._folder_edit.text().strip():
            self.log_message.emit("Rename CD Folders: no folder selected.", "warning")
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Rename CD Folders: script not found — check project structure.", "error"
            )
            return
        folder = Path(self._folder_edit.text().strip())
        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Applying..." if apply else "Scanning (dry run)...")
        self.log_message.emit(
            f"Rename CD Folders: {'apply' if apply else 'dry run'} — {folder}", "info"
        )
        self._worker = _Worker(folder, apply, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(lambda r: self._on_finished(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_lbl.setText(f"Processing: {message}")

    def _on_finished(self, result: dict, was_apply: bool):
        self._last_results = result.get("results", [])
        self._populate_table(self._last_results)

        renamed = result.get("renamed", 0)
        pending = result.get("pending", 0)
        skipped = result.get("skipped", 0)
        errors  = result.get("errors", 0)
        report  = result.get("report_path")

        if was_apply:
            summary = f"Renamed: {renamed}  |  Skipped: {skipped}  |  Errors: {errors}"
            level = "error" if errors else "success"
            self._set_state("done_apply")
        else:
            summary = f"Would rename: {pending}  |  Skipped: {skipped}"
            level = "info"
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        self.log_message.emit(
            f"Rename CD Folders {'complete' if was_apply else 'dry run'} — {summary}", level
        )
        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self.log_message.emit(f"Rename CD Folders error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = row.get("status", "")
            fg = _status_fg(str(status))
            try:
                parent_rel = str(row["parent"].relative_to(Path(self._folder_edit.text())))
            except (ValueError, KeyError):
                parent_rel = str(row.get("parent", ""))
            vals = [
                parent_rel,
                row.get("old_name", ""),
                row.get("new_name", ""),
                status,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
