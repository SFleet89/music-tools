"""
Music Tools GUI -- Format Dupe Finder Panel  v0.1
==================================================
GUI panel for format_dupe_finder/format_dupe_finder.py.

Read-only scan: finds albums that exist in both MP3 and FLAC format,
verifies the FLAC copies, and shows which MP3 folders are safe to delete.

Results shown in a colour-coded table (SAFE TO DELETE MP3 / NEEDS REVIEW /
FLAC CORRUPT) and in the ReportViewerDialog after the scan completes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QCheckBox, QComboBox, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS
from gui._scan_mixin import ScanTimerMixin
from gui.report_viewer_dialog import ReportViewerDialog

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CONFIG_PATH = _PROJECT_ROOT / "music_config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


try:
    from format_dupe_finder.format_dupe_finder import run_format_dupe_finder
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


# -- Verdict colours ----------------------------------------------------------

def _verdict_bg(verdict: str) -> str | None:
    v = verdict.upper()
    if "SAFE" in v:
        return "#1e3a2f"   # dark green
    if "CORRUPT" in v:
        return "#3a1e1e"   # dark red
    if "REVIEW" in v:
        return "#3a2f1e"   # dark amber
    return None


def _verdict_fg(verdict: str) -> str:
    v = verdict.upper()
    if "SAFE" in v:
        return COLOURS.get("log_success", "#4ec9b0")
    if "CORRUPT" in v:
        return COLOURS.get("log_error", "#f44747")
    if "REVIEW" in v:
        return COLOURS.get("log_warning", "#dcdcaa")
    return COLOURS.get("text", "#d4d4d4")


# -- Worker -------------------------------------------------------------------

class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, root, threshold, sample_mode, no_fp,
                 fpcalc_path, ffmpeg_path, parent=None):
        super().__init__(parent)
        self.root        = root
        self.threshold   = threshold
        self.sample_mode = sample_mode
        self.no_fp       = no_fp
        self.fpcalc_path = fpcalc_path
        self.ffmpeg_path = ffmpeg_path

    def run(self):
        try:
            result = run_format_dupe_finder(
                root=self.root,
                threshold=self.threshold,
                sample_mode=self.sample_mode,
                no_fp=self.no_fp,
                fpcalc_path=self.fpcalc_path or None,
                ffmpeg_path=self.ffmpeg_path or None,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


# -- Panel --------------------------------------------------------------------

class FormatDupeFinderPanel(ScanTimerMixin, QWidget):
    log_message = Signal(str, str)

    _TABLE_COLS = [
        "Type", "MP3 Folder", "FLAC Folder",
        "MP3 Trks", "FLAC Trks", "Tracks OK",
        "FLAC Integrity", "FP Similarity", "Verdict",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_browse_folder: str = ""
        self._last_report_path: Path | None = None
        self._worker: _Worker | None = None
        self._scan_mixin_init()
        self._build_ui()
        self._set_state("idle")

    # -- UI construction ------------------------------------------------------

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
        title_lbl = QLabel("Format Dupe Finder")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Finds albums that exist in both MP3 and FLAC, verifies the FLAC copies")
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
        folder_box = QGroupBox("Library Root Folder")
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select the root folder to scan for MP3/FLAC duplicates...")
        self._folder_edit.editingFinished.connect(self._validate_folder_path)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse)
        folder_layout.addWidget(self._folder_edit, stretch=1)
        folder_layout.addWidget(browse_btn)
        body_layout.addWidget(folder_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(16)

        sample_lbl = QLabel("Fingerprint sample:")
        self._sample_combo = QComboBox()
        self._sample_combo.addItems(["3 tracks per album", "Half of tracks", "All tracks"])
        self._sample_combo.setToolTip(
            "How many tracks to fingerprint per album pair.\n"
            "More tracks = more accurate but slower."
        )

        thresh_lbl = QLabel("FP threshold %:")
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(50, 100)
        self._threshold_spin.setValue(85)
        self._threshold_spin.setSuffix("%")
        self._threshold_spin.setToolTip(
            "Minimum fingerprint similarity to consider tracks a match.\n"
            "Default 85%. Lower = more lenient; higher = stricter."
        )

        self._no_fp_chk = QCheckBox("Skip fingerprinting (integrity + track count only)")
        self._no_fp_chk.setToolTip(
            "When checked, only runs the ffmpeg integrity check and compares track counts.\n"
            "Faster but less reliable — use if fpcalc is unavailable."
        )
        self._no_fp_chk.toggled.connect(self._on_no_fp_toggled)

        opts_layout.addWidget(sample_lbl)
        opts_layout.addWidget(self._sample_combo)
        opts_layout.addSpacing(8)
        opts_layout.addWidget(thresh_lbl)
        opts_layout.addWidget(self._threshold_spin)
        opts_layout.addSpacing(8)
        opts_layout.addWidget(self._no_fp_chk)
        opts_layout.addStretch()
        body_layout.addWidget(opts_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setFixedHeight(32)
        self._scan_btn.clicked.connect(self._on_scan)
        self._load_btn = QPushButton("Load Report…")
        self._load_btn.setFixedHeight(32)
        self._load_btn.setToolTip("Open a previously saved CSV report")
        self._load_btn.clicked.connect(self._on_load_report)
        self._view_btn = QPushButton("View Report")
        self._view_btn.setFixedHeight(32)
        self._view_btn.setEnabled(False)
        self._view_btn.setToolTip("Open the last scan report in the viewer")
        self._view_btn.clicked.connect(self._on_view_report)
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._load_btn)
        btn_row.addWidget(self._view_btn)
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

        # Results table
        self._table = QTableWidget(0, len(self._TABLE_COLS))
        self._table.setHorizontalHeaderLabels(self._TABLE_COLS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Type
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)            # MP3 Folder
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)            # FLAC Folder
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # MP3 Trks
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # FLAC Trks
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Tracks OK
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # FLAC Integrity
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # FP Similarity
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)  # Verdict
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

    # -- State management -----------------------------------------------------

    def _set_state(self, state: str):
        if state == "idle":
            self._stop_scan_timer()
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Scan")
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(False)
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._start_scan_timer()
            self._scan_btn.setEnabled(False)
            self._load_btn.setEnabled(False)
            self._view_btn.setEnabled(False)
        elif state == "done":
            self._stop_scan_timer()
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Re-scan")
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(self._last_report_path is not None)
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._status_lbl.setText("")

    # -- Options helpers ------------------------------------------------------

    def _on_no_fp_toggled(self, checked: bool):
        self._sample_combo.setEnabled(not checked)
        self._threshold_spin.setEnabled(not checked)

    def _sample_mode(self) -> str:
        idx = self._sample_combo.currentIndex()
        return ["3", "half", "all"][idx]

    # -- Folder browse / validate ---------------------------------------------

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select root folder to scan",
            self._last_browse_folder or self._folder_edit.text() or str(Path.home()),
        )
        if folder:
            self._last_browse_folder = folder
            self._folder_edit.setText(folder)
            self._set_state("idle")
            self._table.setRowCount(0)
            self._summary_lbl.setText("")

    def _validate_folder_path(self):
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
            self.log_message.emit(f"Path not found -- {text}", "warning")

    # -- Scan -----------------------------------------------------------------

    def _on_scan(self):
        folder_text = self._folder_edit.text().strip()
        if not folder_text:
            self.log_message.emit("Format Dupe Finder: no folder selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit("Format Dupe Finder: script not found -- check project structure.", "error")
            return

        cfg        = _load_config()
        fpcalc     = cfg.get("acoustid", {}).get("fpcalc_path", "fpcalc")
        ffmpeg     = cfg.get("tools", {}).get("ffmpeg_path", "ffmpeg")
        threshold  = float(self._threshold_spin.value())
        sample     = self._sample_mode()
        no_fp      = self._no_fp_chk.isChecked()

        self._set_state("running")
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._progress.setRange(0, 0)
        self.log_message.emit(
            f"Format Dupe Finder: scanning {folder_text} "
            f"(threshold={threshold}%, sample={sample}, no_fp={no_fp})",
            "info",
        )

        self._worker = _Worker(
            root=Path(folder_text),
            threshold=threshold,
            sample_mode=sample,
            no_fp=no_fp,
            fpcalc_path=fpcalc,
            ffmpeg_path=ffmpeg,
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
        rows         = result.get("rows", [])
        pairs_found  = result.get("pairs_found", len(rows))
        safe         = result.get("safe_to_delete", 0)
        review       = result.get("needs_review", 0)
        corrupt      = result.get("flac_corrupt", 0)
        report       = result.get("report_path")

        self._populate_table(rows)

        summary = (
            f"Pairs: {pairs_found}  |  "
            f"Safe to delete MP3: {safe}  |  "
            f"Needs review: {review}  |  "
            f"FLAC corrupt: {corrupt}"
        )
        self._summary_lbl.setText(summary)

        if report:
            self._last_report_path = Path(report)
            self.log_message.emit(f"Report: {report}", "info")

        level = "error" if corrupt else ("warning" if review else "success")
        self.log_message.emit(f"Format Dupe Finder complete -- {summary}", level)
        self._set_state("done")

    def _on_error(self, message: str):
        self.log_message.emit(f"Format Dupe Finder error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    # -- Table population -----------------------------------------------------

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            mp3_folder  = row.get("mp3_folder", "")
            flac_folder = row.get("flac_folder", "")
            pair_type   = "Same folder" if mp3_folder == flac_folder else "Sibling pair"
            mp3_name    = Path(mp3_folder).name if mp3_folder else ""
            flac_name   = Path(flac_folder).name if flac_folder else flac_folder
            verdict     = row.get("verdict", "")

            cells = [
                pair_type,
                mp3_name,
                flac_name,
                str(row.get("mp3_track_count", "")),
                str(row.get("flac_track_count", "")),
                str(row.get("tracks_match", "")),
                str(row.get("flac_integrity", "")),
                str(row.get("fp_similarity", "")),
                verdict,
            ]

            r = self._table.rowCount()
            self._table.insertRow(r)

            bg = _verdict_bg(verdict)
            fg = _verdict_fg(verdict)

            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg:
                    item.setBackground(QColor(bg))
                # Only colour the text of the verdict column
                if col == len(cells) - 1:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)

    # -- View / Load Report ---------------------------------------------------

    def _on_view_report(self):
        if not self._last_report_path or not self._last_report_path.exists():
            self.log_message.emit("Format Dupe Finder: report file not found.", "warning")
            return
        dlg = ReportViewerDialog(self._last_report_path, self)
        dlg.show()

    def _on_load_report(self):
        start = (
            self._last_browse_folder
            or str(_PROJECT_ROOT / "format_dupe_finder" / "reports")
        )
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Format Dupe Finder Report", start,
            "CSV Reports (*.csv);;All files (*)",
        )
        if not csv_path:
            return
        path = Path(csv_path)
        if not path.exists():
            self.log_message.emit(f"Load Report: file not found -- {csv_path}", "error")
            return
        self._last_report_path = path
        self._view_btn.setEnabled(True)
        dlg = ReportViewerDialog(path, self)
        dlg.show()
        self.log_message.emit(f"Format Dupe Finder: opened {path.name}", "info")
