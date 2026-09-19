"""
gui/report_viewer_dialog.py — v0.1
===================================
Reusable full-screen CSV report viewer dialog.

Opens any CSV report in a maximizable window with:
  - All columns shown in a sortable QTableWidget
  - Live filter bar
  - Row count display
  - Open in Explorer on right-click
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMenu, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from gui.theme import COLOURS

_FULL_PATH_ROLE = Qt.ItemDataRole.UserRole

# Columns that contain file paths — used for right-click "Open in Explorer"
_PATH_COLS = frozenset({
    "unsorted path", "match path", "path", "file", "filepath", "folder",
})

# Per-category row colours
_CAT_COLOURS = {
    "exact":      COLOURS.get("log_warning",  "#f5d97e"),
    "duplicate":  COLOURS.get("log_error",    "#f08080"),
    "better":     COLOURS.get("log_success",  "#7ecf88"),
    "no_match":   COLOURS.get("text_muted",   "#888888"),
}


class ReportViewerDialog(QDialog):
    """Non-modal, maximizable CSV report viewer."""

    def __init__(self, csv_path: Path, parent=None):
        super().__init__(parent)
        self._csv_path  = csv_path
        self._all_rows: list[list[str]] = []
        self._headers:  list[str]       = []
        self._path_col_indices: list[int] = []

        self.setWindowTitle(f"Report Viewer — {csv_path.name}")
        self.setMinimumSize(900, 600)
        self.resize(1300, 780)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setStyleSheet(f"background: {COLOURS['bg']}; color: {COLOURS['text']};")

        self._build_ui()
        self._load_csv()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Header row
        hdr_row = QHBoxLayout()
        self._title_lbl = QLabel()
        self._title_lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self._row_count_lbl = QLabel()
        self._row_count_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(72)
        close_btn.clicked.connect(self.close)
        hdr_row.addWidget(self._title_lbl)
        hdr_row.addStretch()
        hdr_row.addWidget(self._row_count_lbl)
        hdr_row.addSpacing(12)
        hdr_row.addWidget(close_btn)
        layout.addLayout(hdr_row)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to filter any column…")
        self._filter_edit.setFixedHeight(28)
        self._filter_edit.textChanged.connect(self._apply_filter)
        clr_btn = QPushButton("✕")
        clr_btn.setFixedSize(28, 28)
        clr_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS['border']}; color: {COLOURS['text_muted']};"
            f"border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {COLOURS['accent']}; color: {COLOURS['text']}; }}"
        )
        clr_btn.clicked.connect(self._filter_edit.clear)
        filter_row.addWidget(filter_lbl)
        filter_row.addSpacing(6)
        filter_row.addWidget(self._filter_edit, stretch=1)
        filter_row.addWidget(clr_btn)
        layout.addLayout(filter_row)

        # Table
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid {COLOURS['border']};"
            f"background: {COLOURS['surface']};"
            f"alternate-background-color: {COLOURS['bg']}; }}"
            f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
            f"color: {COLOURS['text_muted']}; padding: 4px 8px;"
            f"border: none; border-bottom: 1px solid {COLOURS['border']};"
            f"font-size: 9pt; font-weight: bold; }}"
        )
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._table, stretch=1)

        # Status bar
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 8pt;")
        layout.addWidget(self._status_lbl)

    # ── CSV loading ───────────────────────────────────────────────────────────

    def _load_csv(self):
        try:
            with self._csv_path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                self._headers = list(reader.fieldnames or [])
                self._all_rows = [
                    [row.get(h, "") for h in self._headers]
                    for row in reader
                ]
        except Exception as exc:
            self._status_lbl.setText(f"Error loading CSV: {exc}")
            return

        # Identify path columns by header name
        self._path_col_indices = [
            i for i, h in enumerate(self._headers)
            if h.lower() in _PATH_COLS
        ]

        # Identify category column index if present
        cat_col = next(
            (i for i, h in enumerate(self._headers) if h.lower() == "category"),
            None,
        )

        self._table.setColumnCount(len(self._headers))
        self._table.setHorizontalHeaderLabels(self._headers)

        # Resize modes
        hh = self._table.horizontalHeader()
        for i, h in enumerate(self._headers):
            hl = h.lower()
            if "path" in hl or "folder" in hl or "file" in hl:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        # Last column always stretches
        if self._headers:
            hh.setSectionResizeMode(len(self._headers) - 1, QHeaderView.ResizeMode.Stretch)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._all_rows))

        for r, row_vals in enumerate(self._all_rows):
            cat = row_vals[cat_col].strip().lower() if cat_col is not None else ""
            fg_hex = _CAT_COLOURS.get(cat)
            for c, val in enumerate(row_vals):
                item = QTableWidgetItem(val)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if fg_hex:
                    item.setForeground(QColor(fg_hex))
                self._table.setItem(r, c, item)
            self._table.setRowHeight(r, 18)

        self._table.setSortingEnabled(True)
        self._title_lbl.setText(self._csv_path.name)
        self._update_count()
        self._status_lbl.setText(str(self._csv_path))

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        needle = text.strip().lower()
        visible = 0
        for row in range(self._table.rowCount()):
            if not needle:
                self._table.setRowHidden(row, False)
                visible += 1
                continue
            hit = any(
                needle in (self._table.item(row, col).text() or "").lower()
                for col in range(self._table.columnCount())
                if self._table.item(row, col)
            )
            self._table.setRowHidden(row, not hit)
            if hit:
                visible += 1
        self._update_count(visible if needle else None)

    def _update_count(self, visible: int | None = None):
        total = self._table.rowCount()
        if visible is None or visible == total:
            self._row_count_lbl.setText(f"{total:,} rows")
        else:
            self._row_count_lbl.setText(f"{visible:,} of {total:,} rows")

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        menu = QMenu(self)
        # Build path actions from any path column in the row
        path_actions = {}
        for ci in self._path_col_indices:
            item = self._table.item(r, ci)
            val  = item.text().strip() if item else ""
            if val:
                label = self._headers[ci]
                path_actions[menu.addAction(f"Open in Explorer — {label}")] = val
                path_actions[menu.addAction(f"Copy path — {label}")]        = val + "__COPY"
        if not path_actions:
            copy_act = menu.addAction("Copy row")
        else:
            copy_act = None

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == copy_act:
            cells = [
                self._table.item(r, c).text() if self._table.item(r, c) else ""
                for c in range(self._table.columnCount())
            ]
            QApplication.clipboard().setText("\t".join(cells))
            return
        val = path_actions.get(chosen, "")
        if val.endswith("__COPY"):
            QApplication.clipboard().setText(val[:-6])
        else:
            try:
                subprocess.Popen(["explorer", "/select,", val])
            except Exception:
                pass
