"""
Music Tools GUI -- AcousticID Fingerprint Panel  v0.2
=====================================================
GUI panel for acoustid_fingerprint/acoustid_fingerprint.py.

v0.2: adds Write Tags checkbox, min-confidence spinbox, and Tagged column.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFileDialog, QDoubleSpinBox, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from gui.theme import COLOURS

_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_PATH  = _PROJECT_ROOT / "music_config.json"
_DB_PATH      = _PROJECT_ROOT / "music_cache.db"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from acoustid_fingerprint.acoustid_fingerprint import run_acoustid_fingerprint
    _SCRIPT_AVAILABLE = True
except ImportError:
    _SCRIPT_AVAILABLE = False


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _status_fg(status: str) -> str | None:
    s = status.lower()
    if s == "identified":
        return COLOURS.get("log_success")
    if "error" in s:
        return COLOURS.get("log_error")
    if s in ("no_match", "low_conf") or s.startswith("low_conf"):
        return COLOURS.get("log_warning")
    if "skip" in s or s == "fingerprinted":
        return COLOURS.get("text_muted")
    return None


def _tagged_fg(tagged: str) -> str | None:
    t = tagged.lower()
    if t == "yes":
        return COLOURS.get("log_success")
    if t.startswith("would_tag"):
        return COLOURS.get("log_warning")
    if "error" in t or "unsupported" in t:
        return COLOURS.get("log_error")
    return COLOURS.get("text_muted")


class _Worker(QThread):
    progress = Signal(int, int, str)
    log      = Signal(str)
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, folder: Path, db_path: Path, fpcalc_path: str,
                 api_key: str, skip_cached: bool, do_lookup: bool,
                 write_tags: bool, min_confidence: float, dry_run: bool,
                 api_delay: float, parent=None):
        super().__init__(parent)
        self.folder         = folder
        self.db_path        = db_path
        self.fpcalc_path    = fpcalc_path
        self.api_key        = api_key
        self.skip_cached    = skip_cached
        self.do_lookup      = do_lookup
        self.write_tags     = write_tags
        self.min_confidence = min_confidence
        self.dry_run        = dry_run
        self.api_delay      = api_delay

    def run(self):
        try:
            result = run_acoustid_fingerprint(
                folder          = self.folder,
                db_path         = self.db_path,
                fpcalc_path     = self.fpcalc_path,
                api_key         = self.api_key,
                skip_cached     = self.skip_cached,
                do_lookup       = self.do_lookup,
                write_tags      = self.write_tags,
                min_confidence  = self.min_confidence,
                dry_run         = self.dry_run,
                api_delay       = self.api_delay,
                progress_callback = lambda c, t, m: self.progress.emit(c, t, m),
                log_callback    = lambda msg: self.log.emit(msg),
            )
            self.finished.emit(result)
        except (ValueError, RuntimeError) as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class AcousticIDFingerprintPanel(QWidget):
    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._last_browse_folder: str = ""
        self._build_ui()
        self._set_state("idle")
        self._prefill_from_config()

    def _prefill_from_config(self):
        cfg      = _load_config()
        acoustid = cfg.get("acoustid", {})
        api_key  = acoustid.get("api_key", "")
        if api_key:
            self._api_key_edit.setText(api_key)
        if _DB_PATH.exists():
            self._db_edit.setText(str(_DB_PATH))

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
        title_lbl = QLabel("AcousticID Fingerprint")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Fingerprint files, look up MusicBrainz IDs, and write tags")
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
        folder_box = QGroupBox("Folder to Fingerprint")
        fl = QHBoxLayout(folder_box)
        fl.setContentsMargins(12, 12, 12, 12)
        fl.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select a folder of audio files...")
        self._folder_edit.editingFinished.connect(self._validate_folder_path)
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(self._browse_folder)
        fl.addWidget(self._folder_edit, stretch=1)
        fl.addWidget(browse_btn)
        body_layout.addWidget(folder_box)

        # DB picker
        db_box = QGroupBox("music_cache.db")
        dl = QHBoxLayout(db_box)
        dl.setContentsMargins(12, 12, 12, 12)
        dl.setSpacing(8)
        self._db_edit = QLineEdit()
        self._db_edit.setPlaceholderText("Path to music_cache.db...")
        self._db_edit.setReadOnly(True)
        db_btn = QPushButton("Browse")
        db_btn.setObjectName("browse")
        db_btn.setFixedWidth(72)
        db_btn.clicked.connect(self._browse_db)
        dl.addWidget(self._db_edit, stretch=1)
        dl.addWidget(db_btn)
        body_layout.addWidget(db_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(12, 12, 12, 12)
        opts_layout.setSpacing(10)

        # Row 1: checkboxes
        chk_row = QHBoxLayout()
        self._skip_chk = QCheckBox("Skip files already in cache (same mtime)")
        self._skip_chk.setChecked(True)
        self._lookup_chk = QCheckBox("Look up AcousticID after fingerprinting")
        self._lookup_chk.setChecked(True)
        self._lookup_chk.stateChanged.connect(self._on_lookup_toggled)
        chk_row.addWidget(self._skip_chk)
        chk_row.addSpacing(16)
        chk_row.addWidget(self._lookup_chk)
        chk_row.addStretch()
        opts_layout.addLayout(chk_row)

        # Row 2: API key + delay
        api_row = QHBoxLayout()
        api_key_lbl = QLabel("API Key:")
        api_key_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setPlaceholderText("AcousticID API key (acoustid.org)")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setMinimumWidth(200)

        delay_lbl = QLabel("Request delay (s):")
        delay_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._delay_spin = QDoubleSpinBox()
        self._delay_spin.setRange(0.1, 5.0)
        self._delay_spin.setSingleStep(0.05)
        self._delay_spin.setValue(0.35)
        self._delay_spin.setDecimals(2)
        self._delay_spin.setFixedWidth(64)
        self._delay_spin.setToolTip("Seconds between AcousticID API requests.\nKeep at 0.35+ to stay within rate limits.")

        api_row.addWidget(api_key_lbl)
        api_row.addWidget(self._api_key_edit)
        api_row.addSpacing(16)
        api_row.addWidget(delay_lbl)
        api_row.addWidget(self._delay_spin)
        api_row.addStretch()
        opts_layout.addLayout(api_row)

        # Row 3: Write tags + min confidence
        tag_row = QHBoxLayout()
        self._write_tags_chk = QCheckBox("Write tags to files (Apply mode)")
        self._write_tags_chk.setChecked(False)
        self._write_tags_chk.setToolTip(
            "When checked, writes MUSICBRAINZ_TRACKID, ACOUSTID_ID, and\n"
            "ACOUSTID_FINGERPRINT tags to matched files.\n"
            "When unchecked (default), shows what WOULD be tagged without writing."
        )
        self._write_tags_chk.stateChanged.connect(self._on_write_tags_toggled)

        self._min_conf_lbl = QLabel("Min confidence:")
        self._min_conf_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        self._min_conf_spin = QDoubleSpinBox()
        self._min_conf_spin.setRange(0.0, 1.0)
        self._min_conf_spin.setSingleStep(0.05)
        self._min_conf_spin.setValue(0.80)
        self._min_conf_spin.setDecimals(2)
        self._min_conf_spin.setFixedWidth(64)
        self._min_conf_spin.setToolTip(
            "Minimum AcousticID confidence score (0.0-1.0) required to write tags.\n"
            "Files below this threshold are skipped. Default: 0.80"
        )

        tag_row.addWidget(self._write_tags_chk)
        tag_row.addSpacing(16)
        tag_row.addWidget(self._min_conf_lbl)
        tag_row.addWidget(self._min_conf_spin)
        tag_row.addStretch()
        opts_layout.addLayout(tag_row)

        # Apply-mode warning label
        self._apply_warning = QLabel(
            "Apply mode: tags will be written to files on disk."
        )
        self._apply_warning.setStyleSheet(
            f"color: {COLOURS.get('log_warning', '#f5d97e')}; font-size: 9pt;"
        )
        self._apply_warning.setVisible(False)
        opts_layout.addWidget(self._apply_warning)

        body_layout.addWidget(opts_box)

        # Run button
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._run_btn = QPushButton("Run (Dry Run)")
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

        # Results table — 8 columns (added Tagged)
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["Filename", "Duration", "Status", "Score",
             "AcousticID", "MB Recording ID", "MB Title / Artist", "Tagged"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
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

    # -------------------------------------------------------------------------
    #  Slot helpers
    # -------------------------------------------------------------------------

    def _on_lookup_toggled(self, state):
        enabled = self._lookup_chk.isChecked()
        self._api_key_edit.setEnabled(enabled)
        self._delay_spin.setEnabled(enabled)
        self._write_tags_chk.setEnabled(enabled)
        self._min_conf_spin.setEnabled(enabled and self._write_tags_chk.isChecked())
        self._min_conf_lbl.setEnabled(enabled and self._write_tags_chk.isChecked())

    def _on_write_tags_toggled(self, state):
        writing = self._write_tags_chk.isChecked()
        self._min_conf_spin.setEnabled(writing)
        self._min_conf_lbl.setEnabled(writing)
        self._apply_warning.setVisible(writing)
        self._run_btn.setText("Run (Apply — Write Tags)" if writing else "Run (Dry Run)")

    def _set_state(self, state: str):
        if state == "idle":
            self._run_btn.setEnabled(True)
            label = ("Run (Apply -- Write Tags)"
                     if self._write_tags_chk.isChecked() else "Run (Dry Run)")
            self._run_btn.setText(label)
            self._progress.setValue(0)
            self._status_lbl.setText("")
        elif state == "running":
            self._run_btn.setEnabled(False)
        elif state == "done":
            self._run_btn.setEnabled(True)
            label = ("Run Again (Apply)" if self._write_tags_chk.isChecked()
                     else "Run Again (Dry Run)")
            self._run_btn.setText(label)
            self._status_lbl.setText("")

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
            self.log_message.emit(f"Path not found — {text}", "warning")

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to fingerprint",
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

    def _browse_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select music_cache.db",
            self._db_edit.text() or str(_PROJECT_ROOT),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if path:
            self._db_edit.setText(path)

    def _on_run(self):
        folder_text = self._folder_edit.text().strip()
        if not folder_text:
            self.log_message.emit("AcousticID Fingerprint: no folder selected.", "warning")
            return

        db_text = self._db_edit.text().strip()
        if not db_text:
            self.log_message.emit("AcousticID Fingerprint: no database selected.", "warning")
            return

        if not _SCRIPT_AVAILABLE:
            self.log_message.emit(
                "AcousticID Fingerprint: script import failed. Check acoustid_fingerprint/ folder.",
                "error",
            )
            return

        cfg      = _load_config()
        fpcalc   = cfg.get("acoustid", {}).get("fpcalc_path", "fpcalc")
        api_key  = self._api_key_edit.text().strip()
        do_lookup = self._lookup_chk.isChecked()

        if do_lookup and not api_key:
            self.log_message.emit(
                "AcousticID Fingerprint: API key required for lookup. Enter it in Options.",
                "warning",
            )
            return

        write_tags = self._write_tags_chk.isChecked()
        dry_run    = not write_tags
        min_conf   = self._min_conf_spin.value()

        self._set_state("running")
        self._progress.setValue(0)
        self._table.setRowCount(0)
        self._summary_lbl.setText("")
        mode_str = "apply -- writing tags" if write_tags else "dry run"
        self._status_lbl.setText(f"Running ({mode_str})...")
        self.log_message.emit(
            f"AcousticID Fingerprint: starting ({mode_str}) -- {folder_text}", "info"
        )

        self._worker = _Worker(
            folder         = Path(folder_text),
            db_path        = Path(db_text),
            fpcalc_path    = fpcalc,
            api_key        = api_key,
            skip_cached    = self._skip_chk.isChecked(),
            do_lookup      = do_lookup,
            write_tags     = write_tags,
            min_confidence = min_conf,
            dry_run        = dry_run,
            api_delay      = self._delay_spin.value(),
            parent         = self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda msg: self.log_message.emit(msg.strip(), "info"))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        if total > 0:
            self._progress.setValue(int(current / total * 100))
        if filename:
            self._status_lbl.setText(f"Processing: {filename}")

    def _on_finished(self, result: dict):
        self._populate_table(result.get("results", []))

        total          = result.get("total", 0)
        fingerprinted  = result.get("fingerprinted", 0)
        identified     = result.get("identified", 0)
        no_match       = result.get("no_match", 0)
        errors         = result.get("errors", 0)
        skipped        = result.get("skipped", 0)
        tagged         = result.get("tagged", 0)
        low_conf       = result.get("low_confidence", 0)
        report         = result.get("report_path")

        write_mode = self._write_tags_chk.isChecked()
        tag_label  = "Tagged" if write_mode else "Would tag"

        summary = (
            f"Fingerprinted: {fingerprinted}  |  "
            f"Identified: {identified}  |  "
            f"No match: {no_match}  |  "
            f"{tag_label}: {tagged}  |  "
            f"Low conf: {low_conf}  |  "
            f"Skipped: {skipped}  |  "
            f"Errors: {errors}"
        )
        self._progress.setValue(100)
        self._summary_lbl.setText(summary)
        level = "error" if errors else "success"
        self.log_message.emit(f"AcousticID Fingerprint complete -- {summary}", level)
        if report:
            self.log_message.emit(f"Report: {report}", "info")
        self._set_state("done")

    def _on_error(self, message: str):
        self.log_message.emit(f"AcousticID Fingerprint error: {message}", "error")
        self._set_state("idle")
        self._status_lbl.setText(f"Error: {message}")

    def _populate_table(self, rows: list):
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            status = str(row.get("status", ""))
            tagged = str(row.get("tagged", ""))
            fg_status = _status_fg(status)
            fg_tagged = _tagged_fg(tagged)
            score     = row.get("acoustid_score", "")
            score_str = f"{score:.0%}" if isinstance(score, float) else str(score)
            mb_title_artist = row.get("mb_title", "")
            if row.get("mb_artist"):
                mb_title_artist += f"  --  {row['mb_artist']}"
            vals = [
                row.get("filename", ""),
                f"{row.get('duration_s', '')}s",
                status,
                score_str,
                row.get("acoustid_id", ""),
                row.get("mb_recording_id", ""),
                mb_title_artist,
                tagged,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col == 7 and fg_tagged:
                    item.setForeground(QColor(fg_tagged))
                elif fg_status:
                    item.setForeground(QColor(fg_status))
                self._table.setItem(r, col, item)
