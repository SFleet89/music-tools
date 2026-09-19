"""
Music Tools GUI -- Repair Playlists Panel  v0.1
================================================
GUI panel for repair_playlists/repair_playlists.py.

Two folder pickers (playlists dir, music dir) -> Scan -> results table -> Apply.
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
    from repair_playlists.repair_playlists import (
        run_repair_playlists_scan,
        run_repair_playlists_apply,
    )
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if s in ("matched", "repaired", "ok"):
        return COLOURS.get("log_success")
    if "error" in s or "missing" in s:
        return COLOURS.get("log_error")
    if "review" in s or "fuzzy" in s:
        return COLOURS.get("log_warning")
    return None


class _ScanWorker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, playlists_dir, music_dir, parent=None):
        super().__init__(parent)
        self.playlists_dir = playlists_dir
        self.music_dir     = music_dir

    def run(self):
        try:
            result = run_repair_playlists_scan(
                playlists_dir=self.playlists_dir,
                music_dir=self.music_dir,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class _ApplyWorker(QThread):
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, all_results, output_dir, parent=None):
        super().__init__(parent)
        self.all_results = all_results
        self.output_dir  = output_dir

    def run(self):
        try:
            result = run_repair_playlists_apply(
                all_results=self.all_results,
                output_dir=self.output_dir,
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class RepairPlaylistsPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scan_result: dict | None = None
        self._worker = None
        self._last_pl_folder: str = ""
        self._last_music_folder: str = ""
        self._build_ui()
        self._set_state("idle")

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
        title_lbl = QLabel("Repair Playlists")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Fixes broken file paths in .m3u / .m3u8 playlist files")
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

        # Playlists folder
        pl_box = QGroupBox("Playlists Folder")
        pl_layout = QHBoxLayout(pl_box)
        pl_layout.setContentsMargins(12, 12, 12, 12)
        pl_layout.setSpacing(8)
        self._pl_edit = QLineEdit()
        self._pl_edit.setPlaceholderText("Select folder containing .m3u playlists...")
        self._pl_edit.editingFinished.connect(self._validate_pl_path)
        pl_btn = QPushButton("Browse")
        pl_btn.setObjectName("browse")
        pl_btn.setFixedWidth(72)
        pl_btn.clicked.connect(self._browse_playlists)
        pl_layout.addWidget(self._pl_edit, stretch=1)
        pl_layout.addWidget(pl_btn)
        body_layout.addWidget(pl_box)

        # Music folder
        music_box = QGroupBox("Music Library Folder")
        music_layout = QHBoxLayout(music_box)
        music_layout.setContentsMargins(12, 12, 12, 12)
        music_layout.setSpacing(8)
        self._music_edit = QLineEdit()
        self._music_edit.setPlaceholderText("Select the music library root folder...")
        self._music_edit.editingFinished.connect(self._validate_music_path)
        music_btn = QPushButton("Browse")
        music_btn.setObjectName("browse")
        music_btn.setFixedWidth(72)
        music_btn.clicked.connect(self._browse_music)
        music_layout.addWidget(self._music_edit, stretch=1)
        music_layout.addWidget(music_btn)
        body_layout.addWidget(music_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn   = QPushButton("Scan")
        self._apply_btn = QPushButton("Repair Playlists")
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
        self._run_btn.clicked.connect(self._on_scan)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._apply_btn)
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
        self._table.setHorizontalHeaderLabels(["Playlist", "Entry", "Match", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
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

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

    def _set_state(self, state: str):
        if state == "idle":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Scan")
            self._apply_btn.setEnabled(False)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._run_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
        elif state == "done_scan":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Re-scan")
            self._apply_btn.setEnabled(self._scan_result is not None)
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Scan")
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("")

    def _validate_pl_path(self):
        text = self._pl_edit.text().strip()
        if not text:
            return
        path = Path(text)
        if path.exists() and path.is_dir():
            self._last_pl_folder = str(path)
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _validate_music_path(self):
        text = self._music_edit.text().strip()
        if not text:
            return
        path = Path(text)
        if path.exists() and path.is_dir():
            self._last_music_folder = str(path)
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _browse_playlists(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select playlists folder",
            (
                self._last_pl_folder
                or self._pl_edit.text()
                or str(Path.home())
            ),
        )
        if folder:
            self._last_pl_folder = folder
            self._pl_edit.setText(folder)

    def _browse_music(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select music library folder",
            (
                self._last_music_folder
                or self._music_edit.text()
                or str(Path.home())
            ),
        )
        if folder:
            self._last_music_folder = folder
            self._music_edit.setText(folder)

    def _on_scan(self):
        if not self._pl_edit.text().strip():
            self.log_message.emit("Repair Playlists: no playlists folder selected.", "warning")
            return
        if not self._music_edit.text().strip():
            self.log_message.emit("Repair Playlists: no music folder selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Repair Playlists: script not found — check project structure.", "error"
            )
            return

        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Scanning playlists...")
        self.log_message.emit("Repair Playlists: scanning...", "info")

        self._worker = _ScanWorker(
            Path(self._pl_edit.text().strip()),
            Path(self._music_edit.text().strip()),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_apply(self):
        if not self._scan_result:
            return
        if not _SCRIPT_AVAILABLE:
            return

        self._set_state("running")
        self._status_lbl.setText("Repairing playlists...")
        self.log_message.emit("Repair Playlists: applying...", "info")

        output_dir = Path(self._pl_edit.text().strip())
        self._worker = _ApplyWorker(
            self._scan_result.get("all_results", {}),
            output_dir,
            parent=self,
        )
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_apply_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_lbl.setText(f"Scanning: {message}")

    def _on_scan_finished(self, result: dict):
        self._scan_result = result
        self._progress.setValue(100)

        entries = result.get("entries", [])
        self._populate_table(entries)

        counts  = result.get("counts", {})
        matched = counts.get("matched", 0)
        missing = counts.get("missing", 0)
        total   = counts.get("total", len(entries))
        csv_path = result.get("csv_path")

        summary = f"Entries: {total}  |  Matched: {matched}  |  Missing: {missing}"
        self._summary_lbl.setText(summary)
        self._set_state("done_scan")
        self.log_message.emit(f"Repair Playlists scan — {summary}", "info")
        if csv_path:
            self.log_message.emit(f"Report: {csv_path}", "info")

    def _on_apply_finished(self, result: dict):
        repaired = result.get("repaired", result.get("playlists_written", 0))
        errors   = result.get("errors", 0)
        summary = f"Repaired: {repaired}  |  Errors: {errors}"
        self._summary_lbl.setText(summary)
        level = "error" if errors else "success"
        self._set_state("done_apply")
        self.log_message.emit(f"Repair Playlists complete — {summary}", level)

    def _on_error(self, message: str):
        self._run_btn.setEnabled(True)
        self.log_message.emit(f"Repair Playlists error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, entries: list[dict]):
        self._table.setRowCount(0)
        for row in entries:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = row.get("status", row.get("Status", ""))
            fg = _status_fg(str(status))
            vals = [
                row.get("playlist", row.get("Playlist", "")),
                row.get("entry", row.get("Entry", "")),
                row.get("match", row.get("Match", "")),
                status,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
