"""
tagger_undo_panel.py — GUI panel for tagger_undo.py
Reverses folder renames made by anjuna_tagger.py or mb_tagger.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog,
)
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QColor

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from anjuna_mb_lookup.tagger_undo import run_tagger_undo  # noqa: E402

_STATUS_BG: dict[str, str] = {
    "undone":    "#1a3823",
    "would_undo": "#1a3823",
    "error":     "#3a1010",
}
_STATUS_FG: dict[str, str] = {
    "undone":    "#7ecf88",
    "would_undo": "#7ecf88",
    "error":     "#f08080",
}


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
            self.done.emit(run_tagger_undo(**self._kw))
        except Exception as exc:
            self.error.emit(str(exc))


class TaggerUndoPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker:       _Worker | None = None
        self._state        = "idle"
        self._last_results: list = []
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
        lbl = QLabel("Tagger Undo")
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
        self._csv_edit.setPlaceholderText("Select tagger report CSV…")
        self._csv_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._on_browse)
        csv_row.addWidget(self._csv_edit)
        csv_row.addWidget(browse_btn)
        bl.addLayout(csv_row)

        # Buttons + progress
        btn_row = QHBoxLayout()
        self._dry_btn = QPushButton("Dry Run")
        self._dry_btn.setFixedWidth(100)
        self._dry_btn.setEnabled(False)
        self._dry_btn.clicked.connect(self._on_dry_run)
        self._apply_btn = QPushButton("Undo Renames")
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
        headers = ["Original Folder", "Tagged Folder", "Status", "Notes"]
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3):
            t.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        t.verticalHeader().setVisible(False)
        return t

    # ── Button state ────────────────────────────────────────────────────────────

    def _refresh_dry_btn(self):
        self._dry_btn.setEnabled(
            bool(self._csv_edit.text()) and self._state != "running"
        )

    def _refresh_apply_btn(self):
        self._apply_btn.setEnabled(
            bool(self._last_results) and self._state == "done_dry"
        )

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select tagger report CSV", "", "CSV files (*.csv)"
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
        undone     = result.get("undone", 0)
        would_undo = result.get("would_undo", 0)
        errors     = result.get("errors", 0)
        self._last_results = result.get("results", [])

        count  = undone if apply else would_undo
        action = "Undone" if apply else "Would undo"
        self._summary_lbl.setText(f"{action}: {count}  ·  Errors: {errors}")
        rp = result.get("report_path")
        if rp:
            self._report_lbl.setText(f"Report saved: {rp}")

        self._prog.setValue(self._prog.maximum() or 1)
        self._prog.setFormat("Done")
        self._fill_table(self._last_results)
        self.log_message.emit(
            f"Tagger Undo {'apply' if apply else 'dry run'} — "
            f"{count} {action.lower()}, {errors} errors",
            "info",
        )

    def _on_error(self, msg: str):
        self._state = "idle"
        self._summary_lbl.setText(f"Error: {msg}")
        self._prog.setFormat("Error")
        self._refresh_dry_btn()
        self.log_message.emit(f"Tagger Undo error: {msg}", "error")

    def _fill_table(self, results: list):
        self._table.setRowCount(0)
        for res in results:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = str(res.get("status", ""))
            bg = QColor(_STATUS_BG.get(status, "#252525"))
            fg = QColor(_STATUS_FG.get(status, "#aaaaaa"))

            for col, val in enumerate([
                res.get("original_folder", ""),
                res.get("tagged_folder", ""),
                status,
                res.get("notes", ""),
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(fg)
                if col == 2:
                    item.setBackground(bg)
                self._table.setItem(r, col, item)
