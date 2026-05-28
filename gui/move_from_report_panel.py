"""
move_from_report_panel.py — GUI panel for move_from_report.py
Moves review/no-match folders using an existing lookup CSV, no re-scan needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QProgressBar, QFileDialog,
)
from PySide6.QtCore import Signal, QThread

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from anjuna_mb_lookup.move_from_report import run_move_from_report  # noqa: E402


class _Worker(QThread):
    progress = Signal(int, int, str)
    log_msg  = Signal(str)
    done     = Signal(dict)
    error    = Signal(str)

    def __init__(self, kwargs: dict):
        super().__init__()
        self._kw = kwargs

    def run(self):
        try:
            self.done.emit(run_move_from_report(**self._kw))
        except Exception as exc:
            self.error.emit(str(exc))


class MoveFromReportPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker:     _Worker | None = None
        self._state      = "idle"
        self._last_would = 0
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel("Move from Report")
        lbl.setObjectName("pageTitle")
        tb.addWidget(lbl)
        tb.addStretch()
        root.addWidget(title_bar)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 12, 20, 16)
        bl.setSpacing(10)

        # CSV file picker
        csv_row = QHBoxLayout()
        self._csv_edit = QLineEdit()
        self._csv_edit.setPlaceholderText("Select lookup report CSV…")
        self._csv_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._on_browse)
        csv_row.addWidget(self._csv_edit)
        csv_row.addWidget(browse_btn)
        bl.addLayout(csv_row)

        # Description
        info = QLabel(
            "Moves folders based on their lookup status — "
            "review → To Review/  ·  not_found / no_catno → No Match/  "
            "— placed inside their original parent folder."
        )
        info.setObjectName("pageSubtitle")
        info.setWordWrap(True)
        bl.addWidget(info)

        # Buttons + progress
        btn_row = QHBoxLayout()
        self._dry_btn = QPushButton("Dry Run")
        self._dry_btn.setFixedWidth(100)
        self._dry_btn.setEnabled(False)
        self._dry_btn.clicked.connect(self._on_dry_run)
        self._apply_btn = QPushButton("Move Folders")
        self._apply_btn.setFixedWidth(120)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply)
        self._prog = QProgressBar()
        self._prog.setFixedHeight(22)
        self._prog.setValue(0)
        self._prog.setTextVisible(True)
        btn_row.addWidget(self._dry_btn)
        btn_row.addSpacing(6)
        btn_row.addWidget(self._apply_btn)
        btn_row.addSpacing(10)
        btn_row.addWidget(self._prog)
        bl.addLayout(btn_row)

        # Summary labels
        self._summary_lbl = QLabel("")
        self._summary_lbl.setObjectName("pageSubtitle")
        bl.addWidget(self._summary_lbl)

        bl.addStretch()
        root.addWidget(body, stretch=1)
        self._csv_edit.textChanged.connect(self._refresh_dry_btn)

    # ── Button state ────────────────────────────────────────────────────────────

    def _refresh_dry_btn(self):
        self._dry_btn.setEnabled(
            bool(self._csv_edit.text()) and self._state != "running"
        )

    def _refresh_apply_btn(self):
        self._apply_btn.setEnabled(
            self._last_would > 0 and self._state == "done_dry"
        )

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select lookup report CSV", "", "CSV files (*.csv)"
        )
        if path:
            self._csv_edit.setText(path)
            self._apply_btn.setEnabled(False)
            self._last_would = 0
            self._state = "idle"

    def _on_dry_run(self):
        self._run(apply=False)

    def _on_apply(self):
        self._run(apply=True)

    def _run(self, apply: bool):
        csv_path = self._csv_edit.text()
        if not csv_path:
            return

        self._state = "running"
        self._dry_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._prog.setValue(0)
        self._prog.setFormat("Running…")
        if not apply:
            self._summary_lbl.setText("Scanning…")
            self._last_would = 0

        def _prog_cb(current, total, msg):
            if total > 0:
                self._prog.setMaximum(total)
                self._prog.setValue(current)
                self._prog.setFormat(f"{current}/{total}  {str(msg)[:40]}")

        def _log_cb(msg):
            self.log_message.emit(str(msg), "info")

        self._worker = _Worker({
            "csv_path":          csv_path,
            "apply":             apply,
            "progress_callback": _prog_cb,
            "log_callback":      _log_cb,
        })
        self._worker.done.connect(lambda r: self._on_done(r, apply))
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: self._on_finished(apply))
        self._worker.start()

    # ── Result handlers ─────────────────────────────────────────────────────────

    def _on_finished(self, apply: bool):
        self._state = "done_apply" if apply else "done_dry"
        self._refresh_dry_btn()
        self._refresh_apply_btn()

    def _on_done(self, result: dict, apply: bool):
        moved           = result.get("moved", 0)
        would_move      = result.get("would_move", 0)
        skipped_missing = result.get("skipped_missing", 0)
        errors          = result.get("errors", 0)
        self._last_would = would_move

        if apply:
            self._summary_lbl.setText(
                f"Moved: {moved}  ·  Skipped (folder not found): {skipped_missing}  ·  Errors: {errors}"
            )
        else:
            self._summary_lbl.setText(
                f"Would move: {would_move}  ·  Skipped (folder not found): {skipped_missing}"
            )

        self._prog.setValue(self._prog.maximum() or 1)
        self._prog.setFormat("Done")
        self.log_message.emit(
            f"Move from Report {'apply' if apply else 'dry run'} — "
            f"{'moved' if apply else 'would move'}: {moved if apply else would_move}, "
            f"skipped: {skipped_missing}, errors: {errors}",
            "info",
        )

    def _on_error(self, msg: str):
        self._state = "idle"
        self._summary_lbl.setText(f"Error: {msg}")
        self._prog.setFormat("Error")
        self._refresh_dry_btn()
        self.log_message.emit(f"Move from Report error: {msg}", "error")
