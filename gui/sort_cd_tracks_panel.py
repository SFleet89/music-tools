"""
Music Tools GUI -- Sort CD Tracks Panel  v0.1
=============================================
GUI panel for sort_cd_tracks/sort_cd_tracks.py.

Folder picker -> Dry Run -> results table -> Apply.
Uses QThread to keep the UI responsive during the scan.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS

# Ensure project root on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from sort_cd_tracks.sort_cd_tracks import run_sort_cd_tracks
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


# ── Status colour mapping ──────────────────────────────────────────────────────

_STATUS_COLOURS = {
    "would move":                   ("log_success",  None),
    "moved":                        ("log_success",  None),
    "skipped — destination already exists": ("log_warning", None),
    "no disc tag — left in place":  ("text_muted",   None),
}


def _status_fg(status: str) -> str | None:
    for key, (fg, _bg) in _STATUS_COLOURS.items():
        if key in status:
            return COLOURS.get(fg)
    if "error" in status.lower():
        return COLOURS.get("log_error")
    return None


# ── Worker thread ──────────────────────────────────────────────────────────────

class _Worker(QThread):
    progress = Signal(int, int, str)   # current, total, filename
    log      = Signal(str)             # log line
    finished = Signal(dict)            # result dict
    error    = Signal(str)             # error message

    def __init__(self, folder: Path, apply: bool, recursive: bool, parent=None):
        super().__init__(parent)
        self.folder    = folder
        self.apply     = apply
        self.recursive = recursive

    def run(self):
        try:
            result = run_sort_cd_tracks(
                folder=self.folder,
                apply=self.apply,
                recursive=self.recursive,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


# ── Panel ──────────────────────────────────────────────────────────────────────

class SortCdTracksPanel(QWidget):
    """Full GUI panel for Sort CD Tracks."""

    log_message = Signal(str, str)   # (message, level) -> main LogPanel

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_results: list[dict] = []
        self._worker: _Worker | None = None
        self._build_ui()
        self._set_state("idle")

    # ── UI build ───────────────────────────────────────────────────────────────

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
        title_lbl = QLabel("Sort CD Tracks")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Reads DISCNUMBER tags and moves files into CD1 / CD2 subfolders")
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

        # -- Folder picker -------------------------------------------------------
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

        # -- Options -------------------------------------------------------------
        opts_box = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        self._recursive_chk = QCheckBox("Recursive — scan all album subfolders")
        opts_layout.addWidget(self._recursive_chk)
        opts_layout.addStretch()
        body_layout.addWidget(opts_box)

        # -- Action buttons ------------------------------------------------------
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

        # -- Progress bar --------------------------------------------------------
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

        # -- Status label --------------------------------------------------------
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._status_lbl)

        # -- Results table -------------------------------------------------------
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Filename", "Disc", "Destination", "Status"]
        )
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
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

        # -- Summary row ---------------------------------------------------------
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

    # ── State machine ──────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        """idle | running | done_dry | done_apply"""
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

    # ── Slots ──────────────────────────────────────────────────────────────────

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
        folder_text = self._folder_edit.text().strip()
        if not folder_text:
            self.log_message.emit("Sort CD Tracks: no folder selected.", "warning")
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Sort CD Tracks: script not found — check project structure.", "error"
            )
            return

        folder = Path(self._folder_edit.text().strip())
        recursive = self._recursive_chk.isChecked()

        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")

        label = "Applying..." if apply else "Scanning (dry run)..."
        self._status_lbl.setText(label)
        self.log_message.emit(
            f"Sort CD Tracks: {'apply' if apply else 'dry run'} — {folder}", "info"
        )

        self._worker = _Worker(folder, apply, recursive, parent=self)
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

        moved   = result.get("moved", 0)
        skipped = result.get("skipped", 0)
        no_tag  = result.get("no_tag", 0)
        errors  = result.get("errors", 0)
        skipped_albums = result.get("skipped_albums", 0)
        report  = result.get("report_path")

        if was_apply:
            summary = f"Moved: {moved}  |  Skipped: {skipped}  |  No disc tag: {no_tag}  |  Errors: {errors}"
            level = "error" if errors else "success"
            self.log_message.emit(f"Sort CD Tracks complete — {summary}", level)
            self._set_state("done_apply")
        else:
            would_move = sum(1 for r in self._last_results if "would move" in r.get("Status", ""))
            summary = (
                f"Would move: {would_move}  |  Skipped: {skipped}  |  "
                f"No disc tag: {no_tag}  |  Albums skipped: {skipped_albums}"
            )
            self.log_message.emit(f"Sort CD Tracks dry run — {summary}", "info")
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)

        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self.log_message.emit(f"Sort CD Tracks error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    # ── Table population ───────────────────────────────────────────────────────

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = row.get("Status", "")
            fg = _status_fg(status)

            for col, key in enumerate(["Filename", "Disc Number", "Destination Folder", "Status"]):
                item = QTableWidgetItem(str(row.get(key, "")))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
