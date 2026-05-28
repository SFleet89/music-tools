"""
_lookup_base.py — Shared base panel for MusicBrainz lookup scripts.

Used by: AnjunaMBLookupPanel, MBLookupPanel, TiestoLookupPanel.
Subclasses override _run_fn() and optionally _extra_options() / _extra_kwargs().
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

# Ensure project root is on sys.path so script imports resolve
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Status → background / foreground colours (dark-theme palette)
_STATUS_BG: dict[str, str] = {
    "matched":      "#1a3823",
    "auto_matched": "#1a3823",
    "review":       "#3a2e08",
    "not_found":    "#252525",
    "error":        "#3a1010",
}
_STATUS_FG: dict[str, str] = {
    "matched":      "#7ecf88",
    "auto_matched": "#7ecf88",
    "review":       "#f5d97e",
    "not_found":    "#888888",
    "error":        "#f08080",
}


class _LookupWorker(QThread):
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


class MBLookupBasePanel(QWidget):
    """
    Shared UI shell for the three MusicBrainz lookup panels.

    Subclasses must implement:
        _run_fn(self) -> callable   — returns the script's run_* function

    Subclasses may override:
        _extra_options(self, row: QHBoxLayout) — add widgets after the auto-match checkbox
        _extra_kwargs(self) -> dict            — add script-specific keyword args
    """

    log_message = Signal(str, str)  # (message, level)

    _TITLE: str = "MB Lookup"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _LookupWorker | None = None
        self._build_ui()

    # ── Subclass hooks ──────────────────────────────────────────────────────────

    def _run_fn(self):
        """Return the callable to run. Must be overridden."""
        raise NotImplementedError

    def _extra_options(self, row: QHBoxLayout):
        """Override to add extra option widgets into the options row."""
        pass

    def _extra_kwargs(self) -> dict:
        """Override to add script-specific keyword arguments."""
        return {}

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

        # Body
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 12, 20, 16)
        bl.setSpacing(10)

        # Folder picker row
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText(
            "Select batch folder containing album subfolders…"
        )
        self._folder_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self._folder_edit)
        folder_row.addWidget(browse_btn)
        bl.addLayout(folder_row)

        # Options row
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)
        self._auto_chk = QCheckBox("Auto-match  (pick best result automatically)")
        self._auto_chk.setChecked(True)
        opts_row.addWidget(self._auto_chk)
        self._extra_options(opts_row)
        opts_row.addStretch()
        bl.addLayout(opts_row)

        # Run button + progress bar
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Lookup")
        self._run_btn.setFixedWidth(120)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run)
        self._prog = QProgressBar()
        self._prog.setFixedHeight(22)
        self._prog.setValue(0)
        self._prog.setTextVisible(True)
        btn_row.addWidget(self._run_btn)
        btn_row.addSpacing(10)
        btn_row.addWidget(self._prog)
        bl.addLayout(btn_row)

        # Summary + report path labels
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

        # Enable run button when folder is set
        self._folder_edit.textChanged.connect(self._refresh_run_btn)

    def _build_table(self) -> QTableWidget:
        headers = ["Folder", "Status", "MB Artist", "MB Title", "Score"]
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in (1, 2, 3, 4):
            t.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        t.verticalHeader().setVisible(False)
        return t

    # ── Button state ────────────────────────────────────────────────────────────

    def _refresh_run_btn(self):
        busy = self._worker is not None and self._worker.isRunning()
        self._run_btn.setEnabled(bool(self._folder_edit.text()) and not busy)

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, f"Select batch folder — {self._TITLE}"
        )
        if folder:
            self._folder_edit.setText(folder)

    def _on_run(self):
        folder = self._folder_edit.text()
        if not folder:
            return

        self._run_btn.setEnabled(False)
        self._prog.setValue(0)
        self._prog.setFormat("Running…")
        self._table.setRowCount(0)
        self._summary_lbl.setText("Scanning…")
        self._report_lbl.setText("")

        # Build callbacks before constructing the worker
        def _prog_cb(current, total, msg):
            if total > 0:
                self._prog.setMaximum(total)
                self._prog.setValue(current)
                self._prog.setFormat(f"{current}/{total}  {str(msg)[:40]}")

        def _log_cb(msg):
            self.log_message.emit(str(msg), "info")

        kwargs = {
            "batch_path":        folder,
            "auto_mode":         self._auto_chk.isChecked(),
            "progress_callback": _prog_cb,
            "log_callback":      _log_cb,
        }
        kwargs.update(self._extra_kwargs())

        self._worker = _LookupWorker(self._run_fn(), kwargs)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._refresh_run_btn)
        self._worker.start()

    # ── Result handlers ─────────────────────────────────────────────────────────

    def _on_done(self, result: dict):
        matched      = result.get("matched", 0)
        auto_matched = result.get("auto_matched", 0)
        review       = result.get("review", 0)
        not_found    = result.get("not_found", 0)
        errors       = result.get("errors", 0)
        total_match  = matched + auto_matched

        self._summary_lbl.setText(
            f"Matched: {total_match}  ·  Review: {review}  ·  "
            f"Not found: {not_found}  ·  Errors: {errors}"
        )
        rp = result.get("report_path")
        if rp:
            self._report_lbl.setText(f"Report saved: {rp}")

        self._prog.setValue(self._prog.maximum() or 1)
        self._prog.setFormat("Done")
        self._fill_table(result.get("rows", []))
        self.log_message.emit(
            f"{self._TITLE} complete — {total_match} matched, {review} review, "
            f"{not_found} not found, {errors} errors",
            "info",
        )

    def _on_error(self, msg: str):
        self._summary_lbl.setText(f"Error: {msg}")
        self._prog.setFormat("Error")
        self.log_message.emit(f"{self._TITLE} error: {msg}", "error")

    def _fill_table(self, rows: list):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = str(row.get("status", ""))
            bg = QColor(_STATUS_BG.get(status, "#252525"))
            fg = QColor(_STATUS_FG.get(status, "#aaaaaa"))

            # Score: prefer combined_score, fall back to search_score or catno_score
            score_raw = (
                row.get("combined_score")
                or row.get("search_score")
                or row.get("catno_score")
                or ""
            )
            try:
                score_str = f"{float(score_raw) * 100:.0f}%" if score_raw else "—"
            except (ValueError, TypeError):
                score_str = str(score_raw) if score_raw else "—"

            for col, val in enumerate([
                row.get("folder", ""),
                status,
                row.get("mb_artist", ""),
                row.get("mb_title", ""),
                score_str,
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(fg)
                if col == 1:   # status column gets background highlight
                    item.setBackground(bg)
                self._table.setItem(r, col, item)
