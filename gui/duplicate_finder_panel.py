"""
Music Tools GUI -- Duplicate Finder Panel  v0.1
===============================================
GUI panel for duplicate_finder/find_music_duplicates.py.

Source folder picker -> options -> Scan -> tabbed results
(Exact / Duplicates / Better Quality / No Match) -> Apply.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QTabWidget, QSizePolicy,
    QSplitter, QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QFont

from gui.theme import COLOURS

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from duplicate_finder.find_music_duplicates import run_find_music_duplicates
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_path(path_str: str) -> str:
    """Show just the last two path components for readability."""
    if not path_str:
        return ""
    p = Path(path_str)
    parts = p.parts
    return str(Path(*parts[-2:])) if len(parts) >= 2 else p.name


def _meta(item: dict, side: str, key: str) -> str:
    obj = item.get(side) or {}
    meta = obj.get("metadata") or {}
    return str(meta.get(key, "") or "")


def _path(item: dict, side: str) -> str:
    obj = item.get(side) or {}
    return str(obj.get("path", "") or "")


# ── Worker ─────────────────────────────────────────────────────────────────────

class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, unsorted: Path, use_fp: bool, parent=None):
        super().__init__(parent)
        self.unsorted = unsorted
        self.use_fp   = use_fp

    def run(self):
        try:
            result = run_find_music_duplicates(
                unsorted_folder=self.unsorted,
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


class _ApplyWorker(QThread):
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, unsorted: Path, use_fp: bool, parent=None):
        super().__init__(parent)
        self.unsorted = unsorted
        self.use_fp   = use_fp

    def run(self):
        try:
            result = run_find_music_duplicates(
                unsorted_folder=self.unsorted,
                dry_run=False,
                no_review=True,
                use_fingerprints=self.use_fp,
                log_callback=lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


# ── Results table helper ────────────────────────────────────────────────────────

def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    for i in range(len(headers) - 1):
        t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    t.setStyleSheet(
        f"QTableWidget {{ border: 1px solid {COLOURS['border']};"
        f"background: {COLOURS['surface']}; alternate-background-color: {COLOURS['bg']}; }}"
        f"QHeaderView::section {{ background: {COLOURS['sidebar_bg']};"
        f"color: {COLOURS['text_muted']}; padding: 4px 8px;"
        f"border: none; border-bottom: 1px solid {COLOURS['border']}; font-size: 9pt; }}"
    )
    return t


def _add_row(table: QTableWidget, values: list[str], fg: str | None = None):
    r = table.rowCount()
    table.insertRow(r)
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        if fg:
            item.setForeground(QColor(fg))
        table.setItem(r, col, item)


# ── Panel ──────────────────────────────────────────────────────────────────────

class DuplicateFinderPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_result: dict | None = None
        self._worker: _Worker | None = None
        self._apply_worker: _ApplyWorker | None = None
        self._build_ui()
        self._set_state("idle")

    # ── UI ─────────────────────────────────────────────────────────────────────

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
        sub_lbl = QLabel("Compares unsorted downloads against your library and identifies duplicates")
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

        # Source folder
        src_box = QGroupBox("Source Folder (unsorted downloads to check)")
        src_layout = QHBoxLayout(src_box)
        src_layout.setContentsMargins(12, 10, 12, 10)
        src_layout.setSpacing(8)
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("Select the folder of new downloads to check...")
        self._src_edit.setReadOnly(True)
        src_browse = QPushButton("Browse")
        src_browse.setObjectName("browse")
        src_browse.setFixedWidth(72)
        src_browse.clicked.connect(self._browse_src)
        src_layout.addWidget(self._src_edit, stretch=1)
        src_layout.addWidget(src_browse)
        body_layout.addWidget(src_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QHBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        self._fp_chk = QCheckBox("Use audio fingerprinting (slower — compares audio content, not just tags/filename)")
        opts_layout.addWidget(self._fp_chk)
        opts_layout.addStretch()
        body_layout.addWidget(opts_box)

        # Buttons + progress
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._scan_btn  = QPushButton("Scan (Dry Run)")
        self._apply_btn = QPushButton("Move Duplicates")
        self._apply_btn.setEnabled(False)
        self._scan_btn.setFixedHeight(32)
        self._apply_btn.setFixedHeight(32)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOURS.get('log_warning', '#dcdcaa')};"
            f"color: #000; border-radius: 3px; padding: 5px 16px; min-width: 96px; }}"
            f"QPushButton:hover {{ background: #eaeaa0; }}"
            f"QPushButton:disabled {{ background: {COLOURS['disabled_bg']};"
            f"color: {COLOURS['disabled_text']}; }}"
        )
        self._scan_btn.clicked.connect(self._on_scan)
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self._scan_btn)
        btn_row.addWidget(self._apply_btn)
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

        # Summary counts row
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        body_layout.addWidget(self._summary_lbl)

        # Tabbed results
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabBar::tab {{ background: {COLOURS['sidebar_bg']}; color: {COLOURS['text_muted']};"
            f"padding: 5px 14px; border: 1px solid {COLOURS['border']};"
            f"border-bottom: none; border-radius: 3px 3px 0 0; margin-right: 2px; }}"
            f"QTabBar::tab:selected {{ background: {COLOURS['surface']}; color: {COLOURS['text']};"
            f"border-bottom: 1px solid {COLOURS['surface']}; }}"
            f"QTabWidget::pane {{ border: 1px solid {COLOURS['border']};"
            f"background: {COLOURS['surface']}; }}"
        )

        # Tab: Exact Matches
        self._tbl_exact = _make_table(["Unsorted File", "Artist", "Title", "Matched Library File"])
        self._tabs.addTab(self._tbl_exact, "Exact (0)")

        # Tab: Duplicates
        self._tbl_dup = _make_table(["Unsorted File", "Artist", "Title", "Method", "Matched Library File"])
        self._tabs.addTab(self._tbl_dup, "Duplicates (0)")

        # Tab: Better Quality
        self._tbl_better = _make_table(["Unsorted File", "Bitrate", "Artist", "Title", "Replaces Library File"])
        self._tabs.addTab(self._tbl_better, "Better Quality (0)")

        # Tab: No Match
        self._tbl_nomatch = _make_table(["File", "Artist", "Title", "Album"])
        self._tabs.addTab(self._tbl_nomatch, "No Match (0)")

        body_layout.addWidget(self._tabs, stretch=1)

    # ── State ──────────────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        if state == "idle":
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Scan (Dry Run)")
            self._apply_btn.setEnabled(False)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._scan_btn.setEnabled(False)
            self._apply_btn.setEnabled(False)
        elif state == "done_scan":
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Re-scan")
            # Enable apply only if there are duplicates or exact matches to move
            has_matches = bool(
                self._last_result and (
                    self._last_result["counts"].get("exact", 0) +
                    self._last_result["counts"].get("duplicate", 0) +
                    self._last_result["counts"].get("better", 0)
                ) > 0
            )
            self._apply_btn.setEnabled(has_matches)
            self._status_lbl.setText("")
        elif state == "done_apply":
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText("Scan (Dry Run)")
            self._apply_btn.setEnabled(False)
            self._status_lbl.setText("")

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _browse_src(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select unsorted downloads folder",
            self._src_edit.text() or str(Path.home()),
        )
        if folder:
            self._src_edit.setText(folder)
            self._set_state("idle")
            self._clear_tables()
            self._summary_lbl.setText("")

    def _on_scan(self):
        if not self._src_edit.text().strip():
            self.log_message.emit("Duplicate Finder: no source folder selected.", "warning")
            return
        if not _SCRIPT_AVAILABLE:
            self.log_message.emit("Duplicate Finder: script not found.", "error")
            return

        self._set_state("running")
        self._clear_tables()
        self._progress.setValue(0)
        self._status_lbl.setText("Scanning...")
        self._summary_lbl.setText("")
        self.log_message.emit(
            f"Duplicate Finder: scanning {self._src_edit.text().strip()}", "info"
        )

        self._worker = _Worker(
            Path(self._src_edit.text().strip()),
            self._fp_chk.isChecked(),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_apply(self):
        if not _SCRIPT_AVAILABLE:
            return
        self._set_state("running")
        self._status_lbl.setText("Moving duplicates...")
        self.log_message.emit("Duplicate Finder: applying — moving duplicates...", "warning")

        self._apply_worker = _ApplyWorker(
            Path(self._src_edit.text().strip()),
            self._fp_chk.isChecked(),
            parent=self,
        )
        self._apply_worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._apply_worker.finished.connect(self._on_apply_finished)
        self._apply_worker.error.connect(self._on_error)
        self._apply_worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        self._status_lbl.setText(f"Scanning: {Path(filename).name if filename else ''}")

    def _on_scan_finished(self, result: dict):
        self._last_result = result
        cats   = result.get("cats", {})
        counts = result.get("counts", {})

        self._populate_exact(cats.get("exact", []))
        self._populate_duplicates(cats.get("duplicate", []))
        self._populate_better(cats.get("better", []))
        self._populate_nomatch(cats.get("no_match", []))

        # Update tab labels
        self._tabs.setTabText(0, f"Exact ({counts.get('exact', 0)})")
        self._tabs.setTabText(1, f"Duplicates ({counts.get('duplicate', 0)})")
        self._tabs.setTabText(2, f"Better Quality ({counts.get('better', 0)})")
        self._tabs.setTabText(3, f"No Match ({counts.get('no_match', 0)})")

        summary = (
            f"Exact: {counts.get('exact', 0)}  |  "
            f"Duplicates: {counts.get('duplicate', 0)}  |  "
            f"Better quality: {counts.get('better', 0)}  |  "
            f"No match: {counts.get('no_match', 0)}"
        )
        self._summary_lbl.setText(summary)
        self._progress.setValue(100)
        self.log_message.emit(f"Duplicate Finder scan complete — {summary}", "info")

        report = result.get("report_path")
        if report:
            self.log_message.emit(f"Report: {report}", "info")

        self._set_state("done_scan")

        # Auto-switch to the most interesting tab
        if counts.get("duplicate", 0):
            self._tabs.setCurrentIndex(1)
        elif counts.get("exact", 0):
            self._tabs.setCurrentIndex(0)
        elif counts.get("better", 0):
            self._tabs.setCurrentIndex(2)

    def _on_apply_finished(self, result: dict):
        counts = result.get("counts", {})
        summary = (
            f"Moved exact: {counts.get('exact', 0)}  |  "
            f"Moved duplicates: {counts.get('moved_dups', 0)}  |  "
            f"Moved better quality: {counts.get('moved_better', 0)}"
        )
        self._summary_lbl.setText(summary)
        self._progress.setValue(100)
        self.log_message.emit(f"Duplicate Finder complete — {summary}", "success")

        report = result.get("report_path")
        if report:
            self.log_message.emit(f"Report: {report}", "info")

        self._set_state("done_apply")

    def _on_error(self, message: str):
        self.log_message.emit(f"Duplicate Finder error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    # ── Table population ───────────────────────────────────────────────────────

    def _clear_tables(self):
        for tbl in (self._tbl_exact, self._tbl_dup,
                    self._tbl_better, self._tbl_nomatch):
            tbl.setRowCount(0)
        for i, label in enumerate(("Exact (0)", "Duplicates (0)",
                                    "Better Quality (0)", "No Match (0)")):
            self._tabs.setTabText(i, label)

    def _populate_exact(self, items: list):
        fg = COLOURS.get("log_warning")
        for item in items:
            _add_row(self._tbl_exact, [
                _fmt_path(_path(item, "unsorted")),
                _meta(item, "unsorted", "artist"),
                _meta(item, "unsorted", "title"),
                _fmt_path(_path(item, "match")),
            ], fg)

    def _populate_duplicates(self, items: list):
        fg = COLOURS.get("log_error")
        for item in items:
            _add_row(self._tbl_dup, [
                _fmt_path(_path(item, "unsorted")),
                _meta(item, "unsorted", "artist"),
                _meta(item, "unsorted", "title"),
                str(item.get("match_method", "") or ""),
                _fmt_path(_path(item, "match")),
            ], fg)

    def _populate_better(self, items: list):
        fg = COLOURS.get("log_success")
        for item in items:
            u_meta = (item.get("unsorted") or {}).get("metadata") or {}
            from duplicate_finder.find_music_duplicates import format_bitrate
            _add_row(self._tbl_better, [
                _fmt_path(_path(item, "unsorted")),
                format_bitrate(u_meta.get("bitrate")),
                _meta(item, "unsorted", "artist"),
                _meta(item, "unsorted", "title"),
                _fmt_path(_path(item, "match")),
            ], fg)

    def _populate_nomatch(self, items: list):
        fg = COLOURS.get("text_muted")
        for item in items:
            _add_row(self._tbl_nomatch, [
                _fmt_path(_path(item, "unsorted")),
                _meta(item, "unsorted", "artist"),
                _meta(item, "unsorted", "title"),
                _meta(item, "unsorted", "album"),
            ], fg)
