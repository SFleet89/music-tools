"""
_tagger_base.py — Shared base panel for MB tagger scripts.

Used by: AnjunaTaggerPanel, MBTaggerPanel.
Subclasses override _run_fn() only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog,
)
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QColor

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_STATUS_BG: dict[str, str] = {
    "tagged":    "#1a3823",
    "would_tag": "#1a3823",
    "partial":   "#3a2e08",
    "skipped":   "#252525",
    "error":     "#3a1010",
}
_STATUS_FG: dict[str, str] = {
    "tagged":    "#7ecf88",
    "would_tag": "#7ecf88",
    "partial":   "#f5d97e",
    "skipped":   "#888888",
    "error":     "#f08080",
}


class _TaggerWorker(QThread):
    progress = Signal(int, int, str)
    log_msg  = Signal(str)
    done     = Signal(dict)
    error    = Signal(str)

    def __init__(self, run_fn, kwargs: dict):
        super().__init__()
        self._fn = run_fn
        self._kw = kwargs

    def run(self):
        try:
            self.done.emit(self._fn(**self._kw))
        except Exception as exc:
            self.error.emit(str(exc))


class TaggerBasePanel(QWidget):
    """
    Shared UI shell for Anjuna Tagger and MB Tagger.

    Subclasses must implement:
        _run_fn(self) -> callable   — returns the script's run_* function
    """

    log_message = Signal(str, str)

    _TITLE: str = "Tagger"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dry_worker:   _TaggerWorker | None = None
        self._apply_worker: _TaggerWorker | None = None
        self._state        = "idle"   # idle | running | done_dry | done_apply
        self._last_results: list = []
        self._build_ui()

    # ── Subclass hook ───────────────────────────────────────────────────────────

    def _run_fn(self):
        raise NotImplementedError

    # ── Build UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(self._TITLE)
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

        # Options row
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)
        self._skip_art_chk = QCheckBox("Skip cover art download")
        opts_row.addWidget(self._skip_art_chk)
        opts_row.addStretch()
        bl.addLayout(opts_row)

        # Buttons + progress bar
        btn_row = QHBoxLayout()
        self._dry_btn = QPushButton("Dry Run")
        self._dry_btn.setFixedWidth(100)
        self._dry_btn.setEnabled(False)
        self._dry_btn.clicked.connect(self._on_dry_run)
        self._apply_btn = QPushButton("Apply Tags")
        self._apply_btn.setFixedWidth(100)
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

        # Summary + report path
        self._summary_lbl = QLabel("")
        self._summary_lbl.setObjectName("pageSubtitle")
        bl.addWidget(self._summary_lbl)

        self._report_lbl = QLabel("")
        self._report_lbl.setObjectName("pageSubtitle")
        self._report_lbl.setWordWrap(True)
        bl.addWidget(self._report_lbl)

        # Results table
        self._table = self._build_table()
        bl.addWidget(self._table, stretch=1)

        root.addWidget(body, stretch=1)

        self._csv_edit.textChanged.connect(self._refresh_dry_btn)

    def _build_table(self) -> QTableWidget:
        headers = ["Folder", "Status", "Files Tagged", "New Folder", "Notes"]
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 4):
            t.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        t.verticalHeader().setVisible(False)
        return t

    # ── Button state ────────────────────────────────────────────────────────────

    def _refresh_dry_btn(self):
        busy = self._state == "running"
        self._dry_btn.setEnabled(bool(self._csv_edit.text()) and not busy)

    def _refresh_apply_btn(self):
        self._apply_btn.setEnabled(
            bool(self._last_results) and self._state == "done_dry"
        )

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select lookup CSV — {self._TITLE}", "", "CSV files (*.csv)"
        )
        if path:
            self._csv_edit.setText(path)
            self._apply_btn.setEnabled(False)
            self._last_results = []
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
            self._table.setRowCount(0)
            self._summary_lbl.setText("Scanning…")
            self._report_lbl.setText("")
            self._last_results = []

        def _prog_cb(current, total, msg):
            if total > 0:
                self._prog.setMaximum(total)
                self._prog.setValue(current)
                self._prog.setFormat(f"{current}/{total}  {str(msg)[:40]}")

        def _log_cb(msg):
            self.log_message.emit(str(msg), "info")

        kwargs = {
            "csv_path":          csv_path,
            "apply":             apply,
            "skip_art":          self._skip_art_chk.isChecked(),
            "progress_callback": _prog_cb,
            "log_callback":      _log_cb,
        }

        worker = _TaggerWorker(self._run_fn(), kwargs)
        if apply:
            self._apply_worker = worker
        else:
            self._dry_worker = worker

        worker.done.connect(lambda r: self._on_done(r, apply))
        worker.error.connect(self._on_error)
        worker.finished.connect(lambda: self._on_finished(apply))
        worker.start()

    # ── Result handlers ─────────────────────────────────────────────────────────

    def _on_finished(self, apply: bool):
        self._state = "done_apply" if apply else "done_dry"
        self._refresh_dry_btn()
        self._refresh_apply_btn()

    def _on_done(self, result: dict, apply: bool):
        tagged    = result.get("tagged", 0)
        would_tag = result.get("would_tag", 0)
        partial   = result.get("partial", 0)
        skipped   = result.get("skipped", 0)
        errors    = result.get("errors", 0)
        self._last_results = result.get("results", [])

        count  = tagged if apply else would_tag
        action = "Tagged" if apply else "Would tag"
        self._summary_lbl.setText(
            f"{action}: {count}  ·  Partial: {partial}  ·  "
            f"Skipped: {skipped}  ·  Errors: {errors}"
        )
        rp = result.get("report_path")
        if rp:
            self._report_lbl.setText(f"Report saved: {rp}")

        self._prog.setValue(self._prog.maximum() or 1)
        self._prog.setFormat("Done")
        self._fill_table(self._last_results)
        self.log_message.emit(
            f"{self._TITLE} {'apply' if apply else 'dry run'} complete — "
            f"{count} {action.lower()}, {partial} partial, "
            f"{skipped} skipped, {errors} errors",
            "info",
        )

    def _on_error(self, msg: str):
        self._state = "idle"
        self._summary_lbl.setText(f"Error: {msg}")
        self._prog.setFormat("Error")
        self._refresh_dry_btn()
        self.log_message.emit(f"{self._TITLE} error: {msg}", "error")

    def _fill_table(self, results: list):
        self._table.setRowCount(0)
        for res in results:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = str(res.get("status", ""))
            bg = QColor(_STATUS_BG.get(status, "#252525"))
            fg = QColor(_STATUS_FG.get(status, "#aaaaaa"))

            for col, val in enumerate([
                res.get("folder", ""),
                status,
                str(res.get("files_tagged", "")),
                res.get("new_folder", ""),
                res.get("notes", ""),
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(fg)
                if col == 1:
                    item.setBackground(bg)
                self._table.setItem(r, col, item)
