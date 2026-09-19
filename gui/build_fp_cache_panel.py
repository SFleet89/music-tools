"""
Music Tools GUI -- Build FP Cache Panel  v0.3
==============================================
GUI panel for duplicate_finder/build_fp_cache.py.

Folder picker -> options (FP Only, Recheck, Rebuild) -> Run -> progress -> summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QGroupBox, QFileDialog, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from gui.theme import COLOURS
from gui._scan_mixin import ScanTimerMixin

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
    from duplicate_finder.build_fp_cache import run_build_fp_cache
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder, build_meta, build_fp, rebuild, recheck,
                 fpcalc_path="fpcalc", parent=None):
        super().__init__(parent)
        self.folder      = folder
        self.build_meta  = build_meta
        self.build_fp    = build_fp
        self.rebuild     = rebuild
        self.recheck     = recheck
        self.fpcalc_path = fpcalc_path

    def run(self):
        try:
            result = run_build_fp_cache(
                root=self.folder,
                build_meta=self.build_meta,
                build_fp=self.build_fp,
                rebuild=self.rebuild,
                recheck=self.recheck,
                fpcalc_path=self.fpcalc_path,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class BuildFpCachePanel(ScanTimerMixin, QWidget):
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

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']};"
            f"border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Build FP Cache")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Pre-computes audio fingerprints and metadata for the music library")
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
        folder_box = QGroupBox("Library Folder")
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(12, 12, 12, 12)
        folder_layout.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select the organized music library folder...")
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
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(6)
        self._chk_fp_only = QCheckBox("Fingerprints only (skip metadata scan)")
        self._chk_recheck = QCheckBox("Recheck — retry only previously failed files")
        self._chk_rebuild = QCheckBox("Rebuild — wipe cache before building")
        opts_layout.addWidget(self._chk_fp_only)
        opts_layout.addWidget(self._chk_recheck)
        opts_layout.addWidget(self._chk_rebuild)
        body_layout.addWidget(opts_box)

        # Run button
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn = QPushButton("Build Cache")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self._run_btn)
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

        # Summary
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

        body_layout.addStretch()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select music library folder",
            (
            self._last_browse_folder
            or self._folder_edit.text()
            or str(Path.home())
        ),
        )
        if folder:
            self._last_browse_folder = folder
            self._folder_edit.setText(folder)
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
            self.log_message.emit("Build FP Cache: no folder selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Build FP Cache: script not found — check project structure.", "error"
            )
            return

        folder = Path(self._folder_edit.text().strip())
        fp_only = self._chk_fp_only.isChecked()

        self._run_btn.setEnabled(False)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Building cache...")
        self._start_scan_timer()
        self.log_message.emit(f"Build FP Cache: started — {folder}", "info")

        cfg      = _load_config()
        fpcalc   = cfg.get("acoustid", {}).get("fpcalc_path", "fpcalc")

        self._worker = _Worker(
            folder,
            build_meta=not fp_only,
            build_fp=True,
            rebuild=self._chk_rebuild.isChecked(),
            recheck=self._chk_recheck.isChecked(),
            fpcalc_path=fpcalc,
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

        scanned = result.get("scanned", result.get("meta_scanned", 0))
        fp_done = result.get("fingerprinted", result.get("fp_new", 0))
        skipped = result.get("skipped", result.get("fp_skipped", 0))
        errors  = result.get("errors", result.get("fp_errors", 0))
        report  = result.get("report_path")

        summary = f"Scanned: {scanned}  |  Fingerprinted: {fp_done}  |  Skipped: {skipped}  |  Errors: {errors}"
        self._summary_lbl.setText(summary)
        level = "error" if errors else "success"
        self.log_message.emit(f"Build FP Cache complete — {summary}", level)
        if report:
            self.log_message.emit(f"Report: {report}", "info")

    def _on_error(self, message: str):
        self._stop_scan_timer()
        self._run_btn.setEnabled(True)
        self.log_message.emit(f"Build FP Cache error: {message}", "error")
        self._status_lbl.setText(f"Error: {message}")
