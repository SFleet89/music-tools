"""
Music Tools GUI -- Duplicate Finder Panel  v0.7
===============================================
GUI panel for duplicate_finder/find_music_duplicates.py.

Results are shown in the ReportViewerDialog (full-screen, filterable).
Use "View Report" after a scan, or "Load Report" to open an older CSV.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QProgressBar,
    QGroupBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer

from gui.theme import COLOURS
from gui.report_viewer_dialog import ReportViewerDialog

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from duplicate_finder.find_music_duplicates import run_find_music_duplicates
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


# -- Worker -------------------------------------------------------------------

class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, unsorted: Path, organized: Path, use_fp: bool, parent=None):
        super().__init__(parent)
        self.unsorted  = unsorted
        self.organized = organized
        self.use_fp    = use_fp

    def run(self):
        try:
            result = run_find_music_duplicates(
                unsorted_folder=self.unsorted,
                organized_folder=self.organized,
                dry_run=True,
                no_review=True,
                use_fingerprints=self.use_fp,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


# -- Panel --------------------------------------------------------------------

class DuplicateFinderPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _Worker | None = None
        self._last_report_path: Path | None = None
        self._last_src_folder: str = ""
        self._last_lib_folder: str = ""
        self._elapsed_secs  = 0
        self._current_phase = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_elapsed)
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
        title_lbl = QLabel("Duplicate Finder")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Compare two folders and identify duplicate tracks")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 16, 24, 16)
        body_layout.setSpacing(12)
        outer.addWidget(body, stretch=1)

        # Folder A
        src_box = QGroupBox("Folder A — files to check for duplicates")
        src_layout = QHBoxLayout(src_box)
        src_layout.setContentsMargins(12, 10, 12, 10)
        src_layout.setSpacing(8)
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("Select the folder to check...")
        self._src_edit.editingFinished.connect(self._validate_src_path)
        src_browse = QPushButton("Browse")
        src_browse.setObjectName("browse")
        src_browse.setFixedWidth(72)
        src_browse.clicked.connect(self._browse_src)
        src_layout.addWidget(self._src_edit, stretch=1)
        src_layout.addWidget(src_browse)
        body_layout.addWidget(src_box)

        # Folder B
        lib_box = QGroupBox("Folder B — compare against this folder")
        lib_layout = QHBoxLayout(lib_box)
        lib_layout.setContentsMargins(12, 10, 12, 10)
        lib_layout.setSpacing(8)
        self._lib_edit = QLineEdit()
        self._lib_edit.setPlaceholderText("Select the reference folder to compare against...")
        self._lib_edit.editingFinished.connect(self._validate_lib_path)
        lib_browse = QPushButton("Browse")
        lib_browse.setObjectName("browse")
        lib_browse.setFixedWidth(72)
        lib_browse.clicked.connect(self._browse_lib)
        lib_layout.addWidget(self._lib_edit, stretch=1)
        lib_layout.addWidget(lib_browse)
        body_layout.addWidget(lib_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        self._fp_chk = QCheckBox(
            "Use audio fingerprinting (slower — compares audio content, not just tags/filename)"
        )
        opts_layout.addWidget(self._fp_chk)
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

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

        body_layout.addStretch()

    # -- State ----------------------------------------------------------------

    def _set_state(self, state: str):
        if state == "idle":
            self._timer.stop()
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Scan")
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._elapsed_secs  = 0
            self._current_phase = "Starting…"
            self._timer.start(1000)
            self._progress.setRange(0, 0)
            self._scan_btn.setEnabled(False)
            self._load_btn.setEnabled(False)
            self._view_btn.setEnabled(False)
        elif state == "done":
            self._timer.stop()
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Re-scan")
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(self._last_report_path is not None)
            self._status_lbl.setText("")

    # -- Validation / browse --------------------------------------------------

    def _validate_src_path(self):
        text = self._src_edit.text().strip()
        if not text:
            return
        path = Path(text)
        if path.exists() and path.is_dir():
            self._last_src_folder = str(path)
            self._set_state("idle")
            self._summary_lbl.setText("")
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _validate_lib_path(self):
        text = self._lib_edit.text().strip()
        if not text:
            return
        path = Path(text)
        if path.exists() and path.is_dir():
            self._last_lib_folder = str(path)
            self._set_state("idle")
            self._summary_lbl.setText("")
        else:
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _browse_src(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder A (files to check)",
            self._last_src_folder or self._src_edit.text() or str(Path.home()),
        )
        if folder:
            self._last_src_folder = folder
            self._src_edit.setText(folder)
            self._set_state("idle")
            self._summary_lbl.setText("")

    def _browse_lib(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder B (compare against)",
            self._last_lib_folder or self._lib_edit.text() or str(Path.home()),
        )
        if folder:
            self._last_lib_folder = folder
            self._lib_edit.setText(folder)
            self._set_state("idle")
            self._summary_lbl.setText("")

    # -- Scan -----------------------------------------------------------------

    def _on_scan(self):
        src = self._src_edit.text().strip()
        lib = self._lib_edit.text().strip()
        if not src:
            self.log_message.emit("Duplicate Finder: Folder A not selected.", "warning")
            return
        if not lib:
            self.log_message.emit("Duplicate Finder: Folder B not selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit("Duplicate Finder: script not found.", "error")
            return

        self._set_state("running")
        self._progress.setValue(0)
        self._status_lbl.setText("Scanning...")
        self._summary_lbl.setText("")
        self.log_message.emit(f"Duplicate Finder: comparing {src} against {lib}", "info")

        self._worker = _Worker(
            Path(src), Path(lib), self._fp_chk.isChecked(), parent=self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        elapsed = self._fmt_elapsed(self._elapsed_secs)
        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(current / total * 100))
            self._current_phase = f"Reading metadata  [{current:,} / {total:,}]"
        else:
            self._progress.setRange(0, 0)
            self._current_phase = message or "Scanning…"
        self._status_lbl.setText(f"{self._current_phase}  {elapsed}")

    def _tick_elapsed(self):
        self._elapsed_secs += 1
        elapsed = self._fmt_elapsed(self._elapsed_secs)
        self._status_lbl.setText(f"{self._current_phase}  {elapsed}")

    @staticmethod
    def _fmt_elapsed(secs: int) -> str:
        if secs < 60:
            return f"({secs}s)"
        m, s = divmod(secs, 60)
        return f"({m}m {s:02d}s)"

    def _on_finished(self, result: dict):
        counts = result.get("counts", {})
        summary = (
            f"Exact: {counts.get('exact', 0)}  |  "
            f"Duplicates: {counts.get('duplicate', 0)}  |  "
            f"Better quality: {counts.get('better', 0)}  |  "
            f"No match: {counts.get('no_match', 0)}"
        )
        self._summary_lbl.setText(summary)
        self._progress.setValue(100)
        self.log_message.emit(f"Duplicate Finder complete — {summary}", "info")

        report = result.get("report_path")
        if report:
            self._last_report_path = Path(report)
            self.log_message.emit(f"Report: {report}", "info")

        self._set_state("done")

    def _on_error(self, message: str):
        self.log_message.emit(f"Duplicate Finder error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    # -- View / Load Report ---------------------------------------------------

    def _on_view_report(self):
        if not self._last_report_path or not self._last_report_path.exists():
            self.log_message.emit("Duplicate Finder: report file not found.", "warning")
            return
        dlg = ReportViewerDialog(self._last_report_path, self)
        dlg.show()

    def _on_load_report(self):
        """Open a saved CSV report in the viewer."""
        start = (
            self._last_src_folder
            or str(Path(__file__).parent.parent / "duplicate_finder" / "reports")
        )
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Duplicate Finder Report", start,
            "CSV Reports (*.csv);;All files (*)",
        )
        if not csv_path:
            return
        path = Path(csv_path)
        if not path.exists():
            self.log_message.emit(f"Load Report: file not found — {csv_path}", "error")
            return
        self._last_report_path = path
        self._view_btn.setEnabled(True)
        dlg = ReportViewerDialog(path, self)
        dlg.show()
        self.log_message.emit(f"Duplicate Finder: opened {path.name}", "info")

    @staticmethod
    def _open_in_explorer(path_str: str):
        import subprocess
        try:
            subprocess.Popen(["explorer", "/select,", path_str])
        except Exception:
            pass
