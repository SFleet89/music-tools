"""
Music Tools GUI -- AcousticID MB Tagger Panel  v0.1
====================================================
GUI panel for acoustid_mb_tagger/acoustid_mb_tagger.py.

Folder picker -> conflict behaviour -> Dry Run -> results table
-> flagged-files review -> Apply.

Identifies files with ACOUSTID_ID tags, looks them up on AcousticID
and MusicBrainz, and writes metadata tags.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from acoustid_mb_tagger.acoustid_mb_tagger import run_acoustid_mb_tagger
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


# ── Conflict behaviour options (value, display label) ────────────────────────
_CONFLICT_OPTIONS = [
    ("flag",          "Flag conflicts — show below, don't write"),
    ("mb_wins",       "MB wins — always overwrite existing tags"),
    ("keep_existing", "Keep existing — only add MB IDs"),
]


def _status_colour(status: str) -> str | None:
    """Return foreground hex colour for a status string, or None for default."""
    s = status.lower()
    if s in ("tagged", "would_tag"):
        return COLOURS.get("log_success")
    if s == "flagged":
        return COLOURS.get("log_warning")
    if s == "error":
        return COLOURS.get("log_error")
    if s == "no_match":
        return COLOURS.get("text_muted")
    return None


# ── Worker thread ─────────────────────────────────────────────────────────────

class _Worker(QThread):
    progress = Signal(int, int, str)   # current, total, filename
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder: Path, apply: bool,
                 conflict_behaviour: str, parent=None):
        super().__init__(parent)
        self.folder             = folder
        self.apply              = apply
        self.conflict_behaviour = conflict_behaviour

    def run(self):
        try:
            result = run_acoustid_mb_tagger(
                folder=self.folder,
                apply=self.apply,
                tag_config=None,          # use DEFAULT_TAG_CONFIG from script
                conflict_behaviour=self.conflict_behaviour,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


# ── Panel ─────────────────────────────────────────────────────────────────────

class AcoustidMbTaggerPanel(QWidget):
    log_message = Signal(str, str)   # message, level

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_results: list = []
        self._last_browse_folder: str = ""
        self._worker = None
        self._build_ui()
        self._set_state("idle")

    # ── UI construction ───────────────────────────────────────────────────────

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
        title_lbl = QLabel("AcousticID MB Tagger")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel(
            "Look up MusicBrainz metadata via AcoustID and write tags"
        )
        sub_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        # Body
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(14)
        outer.addWidget(body, stretch=1)

        # ── Folder picker ─────────────────────────────────────────────────
        folder_box = QGroupBox("Folder")
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText(
            "Select a folder of audio files that have ACOUSTID_ID tags..."
        )
        self._folder_edit.editingFinished.connect(self._validate_folder_path)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        folder_layout.addWidget(self._folder_edit, stretch=1)
        folder_layout.addWidget(browse_btn)
        body_layout.addWidget(folder_box)

        # ── Options ───────────────────────────────────────────────────────
        opts_box = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(12)

        conflict_lbl = QLabel("Conflict behaviour:")
        conflict_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        self._conflict_combo = QComboBox()
        for value, label in _CONFLICT_OPTIONS:
            self._conflict_combo.addItem(label, userData=value)
        self._conflict_combo.setFixedWidth(270)
        self._conflict_combo.setToolTip(
            "What to do when a file already has tags that differ from the MB match:\n"
            "  Flag conflicts  — skip writing; file appears in Flagged section below\n"
            "  MB wins         — always overwrite with MusicBrainz data\n"
            "  Keep existing   — keep existing tags, only add MB IDs"
        )
        opts_layout.addWidget(conflict_lbl)
        opts_layout.addWidget(self._conflict_combo)
        opts_layout.addStretch()
        body_layout.addWidget(opts_box)

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn   = QPushButton("Dry Run")
        self._apply_btn = QPushButton("Apply — Write Tags")
        self._apply_btn.setEnabled(False)
        self._run_btn.setFixedHeight(32)
        self._apply_btn.setFixedHeight(32)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS.get('log_success', '#4ec9b0')};"
            f"color: #000; border-radius: 3px; padding: 5px 16px; min-width: 140px; }}"
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

        # ── Progress ──────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {COLOURS['border']};"
            f" border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {COLOURS['accent']};"
            f" border-radius: 3px; }}"
        )
        body_layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        body_layout.addWidget(self._status_lbl)

        # ── Results table ─────────────────────────────────────────────────
        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        results_layout.setContentsMargins(8, 8, 8, 8)
        results_layout.setSpacing(0)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Filename", "Current Artist", "Current Title",
            "MB Artist", "MB Title", "MB Album", "Status",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid {COLOURS['border']};"
            f" background: {COLOURS['surface']};"
            f" alternate-background-color: {COLOURS['bg']}; }}"
            f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
            f" color: {COLOURS['text_muted']}; padding: 4px 8px;"
            f" border: none; border-bottom: 1px solid {COLOURS['border']};"
            f" font-size: 9pt; }}"
        )
        results_layout.addWidget(self._table)
        body_layout.addWidget(results_box, stretch=2)

        # ── Flagged files section ─────────────────────────────────────────
        self._flagged_box = QGroupBox("⚠  Flagged Files — Conflicts Detected")
        self._flagged_box.setVisible(False)
        flagged_layout = QVBoxLayout(self._flagged_box)
        flagged_layout.setContentsMargins(8, 8, 8, 8)
        flagged_layout.setSpacing(6)

        warn_colour = COLOURS.get("log_warning", "#d7ba7d")
        flagged_note = QLabel(
            "These files have existing tags that differ from the MusicBrainz match. "
            "To write them, change the conflict behaviour to 'MB wins' and re-run."
        )
        flagged_note.setWordWrap(True)
        flagged_note.setStyleSheet(
            f"color: {warn_colour}; font-size: 9pt; padding: 0 4px 4px 4px;"
        )
        flagged_layout.addWidget(flagged_note)

        self._flagged_table = QTableWidget(0, 6)
        self._flagged_table.setHorizontalHeaderLabels([
            "Filename", "Current Artist", "Current Title",
            "MB Artist", "MB Title", "Note",
        ])
        fhdr = self._flagged_table.horizontalHeader()
        fhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        fhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        fhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        fhdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        fhdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        fhdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._flagged_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._flagged_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._flagged_table.setAlternatingRowColors(True)
        self._flagged_table.verticalHeader().setVisible(False)
        self._flagged_table.setMaximumHeight(150)
        self._flagged_table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid {warn_colour};"
            f" background: {COLOURS['surface']};"
            f" alternate-background-color: {COLOURS['bg']}; }}"
            f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
            f" color: {COLOURS['text_muted']}; padding: 4px 8px;"
            f" border: none; border-bottom: 1px solid {COLOURS['border']};"
            f" font-size: 9pt; }}"
        )
        flagged_layout.addWidget(self._flagged_table)
        body_layout.addWidget(self._flagged_box, stretch=1)

        # ── Summary label ─────────────────────────────────────────────────
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        body_layout.addWidget(self._summary_lbl)

    # ── State machine ─────────────────────────────────────────────────────────

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
            has_would_tag = any(
                r.get("status") == "would_tag" for r in self._last_results
            )
            self._apply_btn.setEnabled(has_would_tag)
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Dry Run")
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _browse(self):
        start_dir = (
            self._last_browse_folder
            or self._folder_edit.text()
            or str(Path.home())
        )
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to tag", start_dir,
        )
        if folder:
            self._last_browse_folder = folder
            self._folder_edit.setText(folder)
            self._set_state("idle")
            self._table.setRowCount(0)
            self._flagged_box.setVisible(False)
            self._flagged_table.setRowCount(0)
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
            self._table.setRowCount(0)
            self._flagged_box.setVisible(False)
            self._flagged_table.setRowCount(0)
            self._summary_lbl.setText("")
        else:
            self.log_message.emit(
                f"AcousticID MB Tagger: path not found — {text}", "warning"
            )

    def _on_run(self):
        if not self._folder_edit.text().strip():
            self.log_message.emit(
                "AcousticID MB Tagger: no folder selected.", "warning"
            )
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _conflict_value(self) -> str:
        return self._conflict_combo.currentData() or "flag"

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "AcousticID MB Tagger: script not found. "
                "Is musicbrainzngs installed?",
                "error",
            )
            return
        folder = Path(self._folder_edit.text().strip())
        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._flagged_box.setVisible(False)
        self._flagged_table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText(
            "Applying tags..." if apply else "Scanning files..."
        )
        self.log_message.emit(
            f"AcousticID MB Tagger: {'apply' if apply else 'dry run'} — {folder}",
            "info",
        )
        self._worker = _Worker(
            folder=folder,
            apply=apply,
            conflict_behaviour=self._conflict_value(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(
            lambda msg: self.log_message.emit(msg.strip(), "info")
        )
        self._worker.finished.connect(lambda r: self._on_finished(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        if filename:
            self._status_lbl.setText(f"Processing: {filename}")

    def _on_finished(self, result: dict, was_apply: bool):
        self._last_results = result.get("results", [])
        self._populate_table(self._last_results)
        self._populate_flagged(self._last_results)

        tagged    = result.get("tagged", 0)
        would_tag = result.get("would_tag", 0)
        flagged   = result.get("flagged", 0)
        no_match  = result.get("no_match", 0)
        errors    = result.get("errors", 0)
        report    = result.get("report_path")

        if was_apply:
            summary = (
                f"Tagged: {tagged}  |  Flagged: {flagged}  |  "
                f"No match: {no_match}  |  Errors: {errors}"
            )
            level = "error" if errors else "success"
            self._set_state("done_apply")
        else:
            summary = (
                f"Would tag: {would_tag}  |  Flagged: {flagged}  |  "
                f"No match: {no_match}  |  Errors: {errors}"
            )
            level = "info"
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        self.log_message.emit(
            f"AcousticID MB Tagger {'complete' if was_apply else 'dry run'}"
            f" — {summary}",
            level,
        )
        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self.log_message.emit(
            f"AcousticID MB Tagger error: {message}", "error"
        )
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_table(self, rows: list):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = row.get("status", "")
            fg = _status_colour(str(status))
            vals = [
                row.get("filename", ""),
                row.get("current_artist", ""),
                row.get("current_title", ""),
                row.get("mb_artist", ""),
                row.get("mb_title", ""),
                row.get("mb_album", ""),
                status,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val) if val else "")
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )
                if fg:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)

    def _populate_flagged(self, rows: list):
        """Populate the flagged-files table and show/hide the group box."""
        flagged_rows = [r for r in rows if r.get("status") == "flagged"]
        if not flagged_rows:
            self._flagged_box.setVisible(False)
            return

        warn_colour = COLOURS.get("log_warning", "#d7ba7d")
        self._flagged_table.setRowCount(0)
        for row in flagged_rows:
            r = self._flagged_table.rowCount()
            self._flagged_table.insertRow(r)
            vals = [
                row.get("filename", ""),
                row.get("current_artist", ""),
                row.get("current_title", ""),
                row.get("mb_artist", ""),
                row.get("mb_title", ""),
                row.get("note", ""),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val) if val else "")
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )
                item.setForeground(QColor(warn_colour))
                self._flagged_table.setItem(r, col, item)

        self._flagged_box.setVisible(True)
