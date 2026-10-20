"""
Music Tools GUI -- Music Integrity Panel  v0.4
===============================================
GUI panel for music_integrity/check_music_integrity.py.

Folder picker + options -> Scan -> results table -> Apply (fix VBR headers).
"View Report" opens the last scan in ReportViewerDialog.
"Load Report..." browses for a saved CSV report.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS
from gui._scan_mixin import ScanTimerMixin
from gui.report_viewer_dialog import ReportViewerDialog

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from music_integrity.check_music_integrity import run_check_music_integrity
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if s in ("ok", "clean", "fixed", "decode_ok"):
        return COLOURS.get("log_success")
    if "error" in s or "corrupt" in s or "decode_errors" in s:
        return COLOURS.get("log_error")
    if "needs_fix" in s or "warning" in s:
        return COLOURS.get("log_warning")
    return None


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder, apply, quick, rebuild_cache, parent=None):
        super().__init__(parent)
        self.folder        = folder
        self.apply         = apply
        self.quick         = quick
        self.rebuild_cache = rebuild_cache

    def run(self):
        try:
            result = run_check_music_integrity(
                root=self.folder,
                apply=self.apply,
                run_integrity=not self.quick,   # Quick = VBR check only (CLI --quick)
                rebuild_cache=self.rebuild_cache,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m),
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class MusicIntegrityPanel(ScanTimerMixin, QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_results: list[dict] = []
        self._fixable: int = 0             # vbr_needs_fix count from the last dry run
        self._last_browse_folder: str = ""
        self._last_report_path: Path | None = None
        self._worker: _Worker | None = None
        self._scan_mixin_init()
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
        title_lbl = QLabel("Music Integrity")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Scans for missing tags, unreadable files, and format-specific issues")
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

        opts_box = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(6)
        self._chk_quick = QCheckBox("Quick mode (VBR check only, skip full decode)")
        self._chk_rebuild = QCheckBox("Rebuild cache (force full re-scan)")
        opts_layout.addWidget(self._chk_quick)
        opts_layout.addWidget(self._chk_rebuild)
        body_layout.addWidget(opts_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn   = QPushButton("Scan")
        self._apply_btn = QPushButton("Fix VBR Headers")
        self._load_btn  = QPushButton("Load Report...")
        self._view_btn  = QPushButton("View Report")
        self._apply_btn.setEnabled(False)
        self._view_btn.setEnabled(False)
        self._run_btn.setFixedHeight(32)
        self._apply_btn.setFixedHeight(32)
        self._load_btn.setFixedHeight(32)
        self._view_btn.setFixedHeight(32)
        self._load_btn.setToolTip("Open a previously saved CSV report")
        self._view_btn.setToolTip("Open the last scan report in the viewer")
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS.get('log_success', '#4ec9b0')};"
            f"color: #000; border-radius: 3px; padding: 5px 16px; min-width: 64px; }}"
            f"QPushButton:hover {{ background: #5edfc0; }}"
            f"QPushButton:disabled {{ background: {COLOURS['disabled_bg']};"
            f"color: {COLOURS['disabled_text']}; }}"
        )
        self._run_btn.clicked.connect(self._on_run)
        self._apply_btn.clicked.connect(self._on_apply)
        self._load_btn.clicked.connect(self._on_load_report)
        self._view_btn.clicked.connect(self._on_view_report)
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._apply_btn)
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

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Folder", "Filename", "VBR Status", "Integrity"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
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

    def _set_state(self, state: str):
        if state == "idle":
            self._stop_scan_timer()
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Scan")
            self._apply_btn.setEnabled(False)
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(False)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._start_scan_timer()
            self._run_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._load_btn.setEnabled(False)
            self._view_btn.setEnabled(False)
        elif state == "done_dry":
            self._stop_scan_timer()
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Re-scan")
            # Apply only fixes VBR headers, so enable it only when the scan found some to fix
            self._apply_btn.setEnabled(self._fixable > 0)
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(self._last_report_path is not None)
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._stop_scan_timer()
            self._run_btn.setEnabled(True)
            self._run_btn.setText("Scan")
            self._apply_btn.setEnabled(False)
            self._load_btn.setEnabled(True)
            self._view_btn.setEnabled(self._last_report_path is not None)
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
            self.log_message.emit(f"Path not found -- {text}", "warning")

    def _on_run(self):
        if not self._folder_edit.text().strip():
            self.log_message.emit("Music Integrity: no folder selected.", "warning")
            return
        self._start_worker(apply=False)

    def _on_apply(self):
        self._start_worker(apply=True)

    def _start_worker(self, apply: bool):
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "Music Integrity: script not found -- check project structure.", "error"
            )
            return
        folder = Path(self._folder_edit.text().strip())
        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        self._status_lbl.setText("Fixing..." if apply else "Scanning...")
        self.log_message.emit(
            f"Music Integrity: {'apply' if apply else 'scan'} -- {folder}", "info"
        )
        self._worker = _Worker(
            folder, apply,
            quick=self._chk_quick.isChecked(),
            rebuild_cache=self._chk_rebuild.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(lambda r: self._on_finished(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        self._on_scan_progress(current, total, message)

    def _on_finished(self, result: dict, was_apply: bool):
        # run_check_music_integrity() returns {"rows", "counts", "report_path", "reports_dir"};
        # counts is keyed by each row's overall_status.
        self._last_results = result.get("rows", [])
        self._populate_table(self._last_results)

        counts  = result.get("counts", {})
        scanned = len(self._last_results)
        issues  = scanned - counts.get("ok", 0) - counts.get("error", 0)
        fixed   = counts.get("vbr_fixed", 0)
        errors  = counts.get("error", 0)
        self._fixable = counts.get("vbr_needs_fix", 0)
        report  = result.get("report_path")

        if report:
            self._last_report_path = Path(report)
            self.log_message.emit(f"Report: {report}", "info")

        if was_apply:
            summary = f"Scanned: {scanned}  |  Fixed: {fixed}  |  Errors: {errors}"
            level = "error" if errors else "success"
            self._set_state("done_apply")
        else:
            summary = f"Scanned: {scanned}  |  Issues: {issues}  |  Errors: {errors}"
            level = "warning" if issues else "success"
            self._set_state("done_dry")

        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        self.log_message.emit(
            f"Music Integrity {'complete' if was_apply else 'scan'} -- {summary}", level
        )

    def _on_error(self, message: str):
        self.log_message.emit(f"Music Integrity error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    def _on_view_report(self):
        if not self._last_report_path or not self._last_report_path.exists():
            self.log_message.emit("Music Integrity: report file not found.", "warning")
            return
        dlg = ReportViewerDialog(self._last_report_path, self)
        dlg.show()

    def _on_load_report(self):
        """Open a saved CSV report in the viewer."""
        start = (
            self._last_browse_folder
            or str(Path(__file__).parent.parent / "music_integrity" / "reports")
        )
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Open Music Integrity Report", start,
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
        self.log_message.emit(f"Music Integrity: opened {path.name}", "info")

    def _populate_table(self, rows: list[dict]):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            vbr = row.get("vbr_status", row.get("VBR Status", ""))
            integrity = row.get("integrity_status", row.get("Integrity", ""))
            status_str = f"{vbr} / {integrity}" if vbr and integrity else (vbr or integrity)
            fg = _status_fg(status_str)
            # Rows carry one full path (file_path); split it for the Folder / Filename columns
            fpath = Path(row.get("file_path", ""))
            vals = [
                row.get("folder", row.get("Folder", str(fpath.parent) if fpath.name else "")),
                row.get("filename", row.get("Filename", fpath.name)),
                vbr,
                integrity,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg and col >= 2:
                    item.setForeground(QColor(fg))
                self._table.setItem(r, col, item)
