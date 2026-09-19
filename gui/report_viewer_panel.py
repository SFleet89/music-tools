"""
gui/report_viewer_panel.py -- v0.1
====================================
Phase 5 -- Built-in Report Viewer Panel.

Replaces the external HTML viewers. Loads any script CSV report and provides:
  - Native sortable, filterable, searchable QTableWidget
  - Decision column (Keep / Skip / Move) editable per row
    (double-click to cycle; right-click for direct selection)
  - Filter bar searches across all columns including Decision
  - Decision summary (X Keep, Y Skip, Z Move) always visible
  - CSV export -- Decision column is prepended to original columns
  - Right-click: Open in Explorer / Copy path / Copy row / Set Decision
  - Recent files menu (last 8 opened, memory-only)
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QFileDialog, QMenu, QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QBrush

from gui.theme import COLOURS

_PROJECT_ROOT = Path(__file__).parent.parent

# Decision column is always column 0 in the displayed table
_DECISION_COL = 0

# Cycle order when the user double-clicks a row
_DECISION_CYCLE = ["", "Keep", "Skip", "Move"]

# Background / foreground colours for each decision value
_DECISION_STYLE: dict[str, dict[str, str]] = {
    "Keep": {"bg": "#1e3a2f", "fg": "#4ec9b0"},   # dark green / teal text
    "Skip": {"bg": "#3a1e1e", "fg": "#f44747"},   # dark red / red text
    "Move": {"bg": "#1e2a3a", "fg": "#569cd6"},   # dark blue / blue text
}

# Header names that may contain file paths (lower-case, matched against CSV headers)
_PATH_COLS = frozenset({
    "unsorted path", "match path", "path", "file", "filepath", "folder",
    "mp3 folder", "flac folder", "source", "destination",
    "old path", "new path", "old name", "new name",
})

# Per-category row foreground colours (matches ReportViewerDialog convention)
_CAT_COLOURS: dict[str, str] = {
    "exact":     COLOURS.get("log_warning", "#f5d97e"),
    "duplicate": COLOURS.get("log_error",   "#f08080"),
    "better":    COLOURS.get("log_success", "#7ecf88"),
    "no_match":  COLOURS.get("text_muted",  "#888888"),
}


class ReportViewerPanel(QWidget):
    """
    Standalone in-app report viewer -- Phase 5.

    Drop-in replacement for the external HTML viewers.  Opens any script CSV
    report, shows all columns in a sortable/filterable table, and lets the user
    annotate rows with Keep / Skip / Move decisions before exporting a new CSV.
    """

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._csv_path: Optional[Path] = None
        self._headers:  list[str]      = []     # original CSV headers (no Decision)
        self._all_rows: list[list[str]] = []     # original CSV data (no Decision)
        self._path_col_indices: list[int] = []   # 0-indexed into self._headers
        self._cat_col_index: Optional[int] = None
        self._recent_paths: list[Path] = []

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Title bar ────────────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']};"
            f"border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Report Viewer")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel(
            "Open any script CSV report -- filter, sort, annotate with decisions, and export"
        )
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        # ── Body ─────────────────────────────────────────────────────────────
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(14)
        outer.addWidget(body, stretch=1)

        # File picker group
        file_box = QGroupBox("Report File")
        file_layout = QHBoxLayout(file_box)
        file_layout.setContentsMargins(12, 12, 12, 12)
        file_layout.setSpacing(8)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a CSV report file...")
        self._path_edit.setReadOnly(True)
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.setObjectName("browse")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._on_browse)
        self._recent_btn = QPushButton("Recent ▾")
        self._recent_btn.setFixedWidth(80)
        self._recent_btn.setToolTip("Recently opened reports (this session)")
        self._recent_btn.clicked.connect(self._show_recent_menu)
        self._recent_btn.setEnabled(False)
        file_layout.addWidget(self._path_edit, stretch=1)
        file_layout.addWidget(self._browse_btn)
        file_layout.addWidget(self._recent_btn)
        body_layout.addWidget(file_box)

        # Filter + action buttons
        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)

        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to search any column...")
        self._filter_edit.setFixedHeight(28)
        self._filter_edit.textChanged.connect(self._apply_filter)
        clr_btn = QPushButton("x")
        clr_btn.setFixedSize(28, 28)
        clr_btn.setToolTip("Clear filter")
        clr_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS['border']}; color: {COLOURS['text_muted']};"
            f" border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {COLOURS['accent']}; color: {COLOURS['text']}; }}"
        )
        clr_btn.clicked.connect(self._filter_edit.clear)

        self._export_btn = QPushButton("Export CSV...")
        self._export_btn.setFixedHeight(28)
        self._export_btn.setToolTip(
            "Save the current table (with Decision column) as a new CSV file"
        )
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)

        self._clear_decisions_btn = QPushButton("Clear Decisions")
        self._clear_decisions_btn.setFixedHeight(28)
        self._clear_decisions_btn.setToolTip(
            "Remove all Keep / Skip / Move annotations from every row"
        )
        self._clear_decisions_btn.setEnabled(False)
        self._clear_decisions_btn.clicked.connect(self._on_clear_decisions)

        controls_row.addWidget(filter_lbl)
        controls_row.addSpacing(4)
        controls_row.addWidget(self._filter_edit, stretch=1)
        controls_row.addWidget(clr_btn)
        controls_row.addSpacing(16)
        controls_row.addWidget(self._export_btn)
        controls_row.addWidget(self._clear_decisions_btn)
        body_layout.addLayout(controls_row)

        # Table
        self._table = QTableWidget(0, 1)
        self._table.setHorizontalHeaderLabels(["Decision"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.setStyleSheet(
            f"QTableWidget {{ border: 1px solid {COLOURS['border']};"
            f" background: {COLOURS['surface']};"
            f" alternate-background-color: {COLOURS['bg']}; }}"
            f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
            f" color: {COLOURS['text_muted']}; padding: 4px 8px;"
            f" border: none; border-bottom: 1px solid {COLOURS['border']};"
            f" font-size: 9pt; font-weight: bold; }}"
        )
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body_layout.addWidget(self._table, stretch=1)

        # Status / summary row
        status_row = QHBoxLayout()
        self._row_count_lbl = QLabel("")
        self._row_count_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        self._decision_summary_lbl = QLabel("")
        self._decision_summary_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 9pt;"
        )
        status_row.addWidget(self._row_count_lbl)
        status_row.addStretch()
        status_row.addWidget(self._decision_summary_lbl)
        body_layout.addLayout(status_row)

        self._hint_lbl = QLabel(
            "Tip: Double-click any row to cycle its decision (Keep -> Skip -> Move -> clear).  "
            "Right-click for direct selection or multi-row annotation."
        )
        self._hint_lbl.setStyleSheet(
            f"color: {COLOURS['text_muted']}; font-size: 8pt;"
        )
        self._hint_lbl.setVisible(False)
        body_layout.addWidget(self._hint_lbl)

    # ── File browsing ─────────────────────────────────────────────────────────

    def _on_browse(self):
        start = (
            str(self._csv_path.parent)
            if self._csv_path
            else str(_PROJECT_ROOT)
        )
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open CSV Report", start,
            "CSV Reports (*.csv);;All files (*)",
        )
        if path_str:
            self._open_csv(Path(path_str))

    def _show_recent_menu(self):
        if not self._recent_paths:
            return
        menu = QMenu(self)
        acts: dict = {}
        for p in self._recent_paths:
            act = menu.addAction(p.name)
            act.setToolTip(str(p))
            acts[act] = p
        chosen = menu.exec(
            self._recent_btn.mapToGlobal(self._recent_btn.rect().bottomLeft())
        )
        if chosen and chosen in acts:
            self._open_csv(acts[chosen])

    def _open_csv(self, path: Path):
        """Open a CSV, update the recent list, and load the report."""
        if not path.exists():
            self.log_message.emit(
                f"Report Viewer: file not found -- {path}", "error"
            )
            return
        self._csv_path = path
        self._path_edit.setText(str(path))
        self._load_csv()
        # Maintain recent list (dedup, cap at 8)
        if path in self._recent_paths:
            self._recent_paths.remove(path)
        self._recent_paths.insert(0, path)
        self._recent_paths = self._recent_paths[:8]
        self._recent_btn.setEnabled(True)

    # ── CSV loading ───────────────────────────────────────────────────────────

    def _load_csv(self):
        """Read the CSV and populate the table."""
        self._table.setSortingEnabled(False)
        self._table.clearContents()
        self._table.setRowCount(0)
        self._filter_edit.clear()
        self._headers      = []
        self._all_rows     = []
        self._path_col_indices  = []
        self._cat_col_index = None

        try:
            with self._csv_path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                raw_headers = list(reader.fieldnames or [])
                all_rows = [
                    [row.get(h, "") for h in raw_headers]
                    for row in reader
                ]
        except Exception as exc:
            self.log_message.emit(
                f"Report Viewer: error loading CSV -- {exc}", "error"
            )
            return

        # If the CSV already has a Decision column (first column), strip it
        # and pre-load the values so we restore prior annotations.
        existing_decisions: list[str] = []
        if raw_headers and raw_headers[0].lower() == "decision":
            existing_decisions = [row[0] for row in all_rows]
            raw_headers = raw_headers[1:]
            all_rows    = [row[1:] for row in all_rows]
        else:
            existing_decisions = [""] * len(all_rows)

        self._headers  = raw_headers
        self._all_rows = all_rows

        # Identify path and category columns
        self._path_col_indices = [
            i for i, h in enumerate(self._headers)
            if h.lower() in _PATH_COLS
        ]
        self._cat_col_index = next(
            (i for i, h in enumerate(self._headers) if h.lower() == "category"),
            None,
        )

        # Build table columns: Decision first, then all CSV columns
        all_col_headers = ["Decision"] + self._headers
        self._table.setColumnCount(len(all_col_headers))
        self._table.setHorizontalHeaderLabels(all_col_headers)

        # Column resize modes
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Decision
        for i, h in enumerate(self._headers, start=1):
            hl = h.lower()
            if any(kw in hl for kw in ("path", "folder", "file", "name")):
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        # Last column always stretches
        if self._headers:
            hh.setSectionResizeMode(
                len(all_col_headers) - 1, QHeaderView.ResizeMode.Stretch
            )

        # Populate rows
        self._table.setRowCount(len(self._all_rows))
        for r, row_vals in enumerate(self._all_rows):
            self._populate_row(r, existing_decisions[r], row_vals)
            self._table.setRowHeight(r, 20)

        self._table.setSortingEnabled(True)
        self._export_btn.setEnabled(True)
        self._clear_decisions_btn.setEnabled(True)
        self._hint_lbl.setVisible(True)
        self._update_count()
        self._update_decision_summary()

        self.log_message.emit(
            f"Report Viewer: loaded {self._csv_path.name} "
            f"({len(self._all_rows):,} rows, {len(self._headers)} columns)",
            "info",
        )

    def _populate_row(self, r: int, decision: str, row_vals: list[str]):
        """Write all cells for row r: Decision cell + data cells."""
        # Decision cell
        self._write_decision_cell(r, decision)

        # Category colour (if CSV has a "category" column)
        cat = ""
        if self._cat_col_index is not None:
            cat = row_vals[self._cat_col_index].strip().lower()
        cat_fg = _CAT_COLOURS.get(cat)

        # Data cells
        for c, val in enumerate(row_vals, start=1):
            item = QTableWidgetItem(val)
            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            if cat_fg:
                item.setForeground(QColor(cat_fg))
            self._table.setItem(r, c, item)

    # ── Decision management ───────────────────────────────────────────────────

    def _write_decision_cell(self, row: int, decision: str):
        """Create or update the Decision cell at (row, 0) with styled text."""
        dec_item = self._table.item(row, _DECISION_COL)
        if dec_item is None:
            dec_item = QTableWidgetItem()
            dec_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            )
            self._table.setItem(row, _DECISION_COL, dec_item)

        dec_item.setText(decision)
        dec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if decision in _DECISION_STYLE:
            style = _DECISION_STYLE[decision]
            dec_item.setBackground(QColor(style["bg"]))
            dec_item.setForeground(QColor(style["fg"]))
            bold = QFont()
            bold.setBold(True)
            dec_item.setFont(bold)
        else:
            # Revert to default table styling
            dec_item.setData(Qt.ItemDataRole.BackgroundRole, None)
            dec_item.setData(Qt.ItemDataRole.ForegroundRole, None)
            dec_item.setFont(QFont())

    def _set_decision(self, row: int, decision: str):
        """Public helper -- set a decision and refresh the summary."""
        self._write_decision_cell(row, decision)
        self._update_decision_summary()

    def _on_cell_double_clicked(self, row: int, _col: int):
        """Double-click on any cell cycles the row's decision."""
        dec_item = self._table.item(row, _DECISION_COL)
        current  = dec_item.text() if dec_item else ""
        idx      = _DECISION_CYCLE.index(current) if current in _DECISION_CYCLE else 0
        new_val  = _DECISION_CYCLE[(idx + 1) % len(_DECISION_CYCLE)]
        self._set_decision(row, new_val)

    def _on_clear_decisions(self):
        """Clear all decision annotations from every row."""
        for r in range(self._table.rowCount()):
            self._write_decision_cell(r, "")
        self._update_decision_summary()

    def _update_decision_summary(self):
        """Recount Keep / Skip / Move across all rows and update the label."""
        counts: dict[str, int] = {"Keep": 0, "Skip": 0, "Move": 0}
        for r in range(self._table.rowCount()):
            item = self._table.item(r, _DECISION_COL)
            if item:
                d = item.text()
                if d in counts:
                    counts[d] += 1
        annotated = sum(counts.values())
        if annotated == 0:
            self._decision_summary_lbl.setText("")
            return
        parts: list[str] = []
        if counts["Keep"]:
            parts.append(f"Keep: {counts['Keep']}")
        if counts["Skip"]:
            parts.append(f"Skip: {counts['Skip']}")
        if counts["Move"]:
            parts.append(f"Move: {counts['Move']}")
        self._decision_summary_lbl.setText("  |  ".join(parts))

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        needle  = text.strip().lower()
        visible = 0
        for r in range(self._table.rowCount()):
            if not needle:
                self._table.setRowHidden(r, False)
                visible += 1
                continue
            hit = any(
                needle in (self._table.item(r, c).text() or "").lower()
                for c in range(self._table.columnCount())
                if self._table.item(r, c)
            )
            self._table.setRowHidden(r, not hit)
            if hit:
                visible += 1
        self._update_count(visible if needle else None)

    def _update_count(self, visible: Optional[int] = None):
        total = self._table.rowCount()
        if visible is None or visible == total:
            self._row_count_lbl.setText(f"{total:,} rows")
        else:
            self._row_count_lbl.setText(f"{visible:,} of {total:,} rows")

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        sel_rows = [idx.row() for idx in self._table.selectionModel().selectedRows()]
        if not sel_rows:
            return
        primary_row = sel_rows[0]

        menu = QMenu(self)

        # Decision submenu (applies to ALL selected rows)
        dec_menu     = menu.addMenu(
            f"Set Decision ({len(sel_rows)} row{'s' if len(sel_rows) > 1 else ''})"
        )
        dec_actions: dict = {}
        for label, val in [
            ("Keep",   "Keep"),
            ("Skip",   "Skip"),
            ("Move",   "Move"),
            ("Clear",  ""),
        ]:
            act = dec_menu.addAction(label)
            dec_actions[act] = val

        menu.addSeparator()

        # Path column actions (only for the primary row)
        path_actions: dict = {}
        for ci in self._path_col_indices:
            table_col = ci + 1          # +1 because Decision is at col 0
            item = self._table.item(primary_row, table_col)
            val  = item.text().strip() if item else ""
            if val:
                col_label = self._headers[ci]
                open_act = menu.addAction(f"Open in Explorer -- {col_label}")
                copy_act = menu.addAction(f"Copy path -- {col_label}")
                path_actions[open_act] = ("open", val)
                path_actions[copy_act] = ("copy", val)

        menu.addSeparator()
        copy_row_act = menu.addAction("Copy row as text")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        # Decision action?
        if chosen in dec_actions:
            decision = dec_actions[chosen]
            for r in sel_rows:
                self._write_decision_cell(r, decision)
            self._update_decision_summary()
            return

        # Path action?
        if chosen in path_actions:
            action_type, val = path_actions[chosen]
            if action_type == "copy":
                QApplication.clipboard().setText(val)
            else:
                try:
                    subprocess.Popen(["explorer", "/select,", val])
                except Exception:
                    pass
            return

        # Copy row
        if chosen is copy_row_act:
            cells = [
                self._table.item(primary_row, c).text()
                if self._table.item(primary_row, c) else ""
                for c in range(self._table.columnCount())
            ]
            QApplication.clipboard().setText("\t".join(cells))

    # ── Export ────────────────────────────────────────────────────────────────

    def _on_export(self):
        if not self._csv_path:
            return
        default_name = self._csv_path.stem + "_decisions.csv"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CSV with Decisions",
            str(self._csv_path.parent / default_name),
            "CSV files (*.csv);;All files (*)",
        )
        if not save_path:
            return
        try:
            out = Path(save_path)
            with out.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # Header row
                writer.writerow(["Decision"] + self._headers)
                # Data rows (visible rows only -- respects current filter)
                for r in range(self._table.rowCount()):
                    if self._table.isRowHidden(r):
                        continue
                    row = [
                        self._table.item(r, c).text()
                        if self._table.item(r, c) else ""
                        for c in range(self._table.columnCount())
                    ]
                    writer.writerow(row)
            self.log_message.emit(
                f"Report Viewer: exported {out.name}", "success"
            )
        except Exception as exc:
            self.log_message.emit(
                f"Report Viewer: export failed -- {exc}", "error"
            )
