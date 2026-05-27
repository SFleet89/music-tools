"""
Music Tools GUI — Settings Panel  v0.1
========================================
Displays and saves all settings from music_config.json.

Reads via load_config() from music_tools_common.
Saves by merging edited values back into the raw JSON (preserving all
_comment keys) and writing to the project-root music_config.json.

Emits:
    settings_saved(dict)  — after a successful save
    log_message(str, str) — (message, level) for the log panel
"""

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QGroupBox, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog

from gui.theme import COLOURS

# Add project root to path so we can import music_tools_common
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from music_tools_common import load_config
    _COMMON_AVAILABLE = True
except ImportError:
    _COMMON_AVAILABLE = False

CONFIG_PATH = _PROJECT_ROOT / "music_config.json"


class SettingsPanel(QWidget):
    """Settings form wired to music_config.json."""

    settings_saved = Signal(dict)         # emits the saved config dict
    log_message    = Signal(str, str)     # (message, level)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg: dict = {}              # raw config dict (with _comments)
        self._build_ui()
        self.load()

    # ── UI build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page title
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(f"background: {COLOURS['surface']}; border-bottom: 1px solid {COLOURS['border']};")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Settings")
        title_lbl.setObjectName("pageTitle")
        sub_lbl   = QLabel("music_config.json")
        sub_lbl.setObjectName("pageSubtitle")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb_layout.addWidget(title_lbl)
        tb_layout.addSpacing(12)
        tb_layout.addWidget(sub_lbl)
        tb_layout.addStretch()
        outer.addWidget(title_bar)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_widget = QWidget()
        self._form_layout = QVBoxLayout(form_widget)
        self._form_layout.setContentsMargins(24, 20, 24, 20)
        self._form_layout.setSpacing(16)
        scroll.setWidget(form_widget)
        outer.addWidget(scroll, stretch=1)

        # ── Folder Paths ──────────────────────────────────────────────────────
        folders_box = QGroupBox("Folder Paths")
        folders_grid = QGridLayout(folders_box)
        folders_grid.setColumnStretch(1, 1)
        folders_grid.setHorizontalSpacing(8)
        folders_grid.setVerticalSpacing(8)
        folders_grid.setContentsMargins(12, 16, 12, 12)

        self._f_organized    = self._folder_row(folders_grid, 0, "Music Library",
            "Your main sorted library  (e.g. E:\\Music)")
        self._f_unsorted     = self._folder_row(folders_grid, 1, "New Downloads",
            "Unsorted folder to check against the library")
        self._f_duplicates   = self._folder_row(folders_grid, 2, "Duplicates Holding",
            "Confirmed duplicates are moved here")
        self._f_better       = self._folder_row(folders_grid, 3, "Better Quality",
            "Unsorted files with higher bitrate than your copy")

        self._form_layout.addWidget(folders_box)

        # ── Matching ──────────────────────────────────────────────────────────
        match_box = QGroupBox("Matching")
        match_form = QFormLayout(match_box)
        match_form.setContentsMargins(12, 16, 12, 12)
        match_form.setHorizontalSpacing(16)
        match_form.setVerticalSpacing(10)

        self._match_mode = QComboBox()
        self._match_mode.addItem("1 — Filename only",           "1")
        self._match_mode.addItem("2 — Metadata only",           "2")
        self._match_mode.addItem("3 — Filename or metadata",    "3")
        self._match_mode.addItem("4 — Both filename and metadata (recommended)", "4")
        self._match_mode.setToolTip("How two tracks are compared to decide if they're duplicates")
        match_form.addRow(self._label("Match Mode"), self._match_mode)

        self._fuzzy_enabled = QCheckBox("Enable fuzzy matching")
        self._fuzzy_enabled.setToolTip(
            "When on, tracks with slightly different spellings can still be matched")
        match_form.addRow("", self._fuzzy_enabled)

        self._fuzzy_threshold = QSpinBox()
        self._fuzzy_threshold.setRange(50, 100)
        self._fuzzy_threshold.setSuffix(" / 100")
        self._fuzzy_threshold.setToolTip(
            "Minimum similarity score for a fuzzy match (88 recommended)")
        match_form.addRow(self._label("Fuzzy Threshold"), self._fuzzy_threshold)

        self._use_duration = QCheckBox("Check track duration when matching")
        match_form.addRow("", self._use_duration)

        self._duration_tol = QSpinBox()
        self._duration_tol.setRange(0, 60)
        self._duration_tol.setSuffix(" sec")
        self._duration_tol.setToolTip(
            "Tracks within this many seconds are considered the same length")
        match_form.addRow(self._label("Duration Tolerance"), self._duration_tol)

        self._size_tol = QDoubleSpinBox()
        self._size_tol.setRange(0.0, 20.0)
        self._size_tol.setSingleStep(0.5)
        self._size_tol.setDecimals(1)
        self._size_tol.setSuffix(" %")
        self._size_tol.setToolTip(
            "File size difference allowed when auto-confirming an exact match")
        match_form.addRow(self._label("Size Tolerance"), self._size_tol)

        self._form_layout.addWidget(match_box)

        # ── Performance ───────────────────────────────────────────────────────
        perf_box = QGroupBox("Performance")
        perf_form = QFormLayout(perf_box)
        perf_form.setContentsMargins(12, 16, 12, 12)
        perf_form.setHorizontalSpacing(16)
        perf_form.setVerticalSpacing(10)

        self._max_threads = QSpinBox()
        self._max_threads.setRange(0, 32)
        self._max_threads.setSpecialValueText("Auto-detect")
        self._max_threads.setToolTip(
            "0 = auto-detect.  Set higher to use more CPU during scans.")
        perf_form.addRow(self._label("Max Threads"), self._max_threads)

        self._cache_enabled = QCheckBox("Cache library metadata between runs")
        self._cache_enabled.setToolTip(
            "Caches tag data in music_cache.db — makes repeated scans much faster")
        perf_form.addRow("", self._cache_enabled)

        self._form_layout.addWidget(perf_box)

        # ── Audio Fingerprinting ──────────────────────────────────────────────
        fp_box = QGroupBox("Audio Fingerprinting  (optional)")
        fp_grid = QGridLayout(fp_box)
        fp_grid.setColumnStretch(1, 1)
        fp_grid.setHorizontalSpacing(8)
        fp_grid.setVerticalSpacing(8)
        fp_grid.setContentsMargins(12, 16, 12, 12)

        self._fp_enabled = QCheckBox("Offer fingerprint matching after main scan")
        self._fp_enabled.setToolTip(
            "Uses fpcalc to compare audio fingerprints — catches renames/reorders")
        fp_grid.addWidget(self._fp_enabled, 0, 0, 1, 3)

        fp_label = QLabel("fpcalc.exe Path")
        fp_label.setObjectName("fieldLabel")
        self._fp_path = QLineEdit()
        self._fp_path.setPlaceholderText("Path to fpcalc.exe  (download from acoustid.org/chromaprint)")
        fp_browse = QPushButton("Browse…")
        fp_browse.setObjectName("browse")
        fp_browse.clicked.connect(self._browse_fpcalc)
        fp_grid.addWidget(fp_label,        1, 0)
        fp_grid.addWidget(self._fp_path,   1, 1)
        fp_grid.addWidget(fp_browse,       1, 2)

        self._fp_threshold = QSpinBox()
        self._fp_threshold.setRange(50, 100)
        self._fp_threshold.setSuffix(" / 100")
        self._fp_threshold.setToolTip("Fingerprint similarity required to count as a match")
        fp_thresh_label = QLabel("Fingerprint Threshold")
        fp_thresh_label.setObjectName("fieldLabel")
        fp_grid.addWidget(fp_thresh_label,    2, 0)
        fp_grid.addWidget(self._fp_threshold, 2, 1)

        self._form_layout.addWidget(fp_box)
        self._form_layout.addStretch()

        # ── Save / Reload buttons ─────────────────────────────────────────────
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        save_btn = QPushButton("Save Settings")
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self.save)

        reload_btn = QPushButton("Reload from File")
        reload_btn.setObjectName("secondary")
        reload_btn.setFixedHeight(32)
        reload_btn.clicked.connect(self.load)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(reload_btn)
        btn_layout.addSpacing(12)
        btn_layout.addWidget(self._status_label)
        btn_layout.addStretch()

        self._form_layout.addWidget(btn_row)

    # ── Helper: labelled field row with Browse button ─────────────────────────

    def _folder_row(self, grid: QGridLayout, row: int, label: str, tip: str) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setObjectName("fieldLabel")
        lbl.setToolTip(tip)
        edit = QLineEdit()
        edit.setPlaceholderText(tip)
        edit.setToolTip(tip)
        browse = QPushButton("Browse…")
        browse.setObjectName("browse")
        browse.clicked.connect(lambda _, e=edit: self._browse_folder(e))
        grid.addWidget(lbl,    row, 0)
        grid.addWidget(edit,   row, 1)
        grid.addWidget(browse, row, 2)
        return edit

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("fieldLabel")
        return lbl

    # ── Browse helpers ────────────────────────────────────────────────────────

    def _browse_folder(self, target: QLineEdit):
        current = target.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", current,
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            target.setText(folder)

    def _browse_fpcalc(self):
        current = self._fp_path.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate fpcalc.exe", current, "Executable (*.exe);;All files (*)"
        )
        if path:
            self._fp_path.setText(path)

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self):
        """Load music_config.json and populate form fields."""
        try:
            if _COMMON_AVAILABLE:
                self._cfg = load_config()
            else:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    self._cfg = json.load(f)
            self._populate()
            self._set_status("Loaded from music_config.json", success=True)
            self.log_message.emit("Settings loaded from music_config.json", "info")
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            self._set_status(f"Could not load config: {e}", success=False)
            self.log_message.emit(f"Settings load failed: {e}", "error")

    def _populate(self):
        """Fill form widgets from self._cfg."""
        folders  = self._cfg.get("folders",     {})
        matching = self._cfg.get("matching",     {})
        perf     = self._cfg.get("performance",  {})
        acoustid = self._cfg.get("acoustid",     {})

        self._f_organized.setText(folders.get("organized",    ""))
        self._f_unsorted.setText( folders.get("unsorted",     ""))
        self._f_duplicates.setText(folders.get("duplicates",  ""))
        self._f_better.setText(   folders.get("better_quality",""))

        mode_str = str(matching.get("mode", "4"))
        idx = self._match_mode.findData(mode_str)
        self._match_mode.setCurrentIndex(max(idx, 0))

        self._fuzzy_enabled.setChecked(bool(matching.get("fuzzy_enabled", True)))
        self._fuzzy_threshold.setValue(int(matching.get("fuzzy_threshold", 88)))
        self._use_duration.setChecked(bool(matching.get("use_duration", True)))
        self._duration_tol.setValue(int(matching.get("duration_tolerance_seconds", 5)))
        self._size_tol.setValue(float(matching.get("exact_match_size_tolerance_percent", 3.0)))

        self._max_threads.setValue(int(perf.get("max_threads", 0)))
        self._cache_enabled.setChecked(bool(perf.get("cache_enabled", True)))

        self._fp_enabled.setChecked(bool(acoustid.get("enabled", True)))
        self._fp_path.setText(acoustid.get("fpcalc_path", ""))
        self._fp_threshold.setValue(int(acoustid.get("similarity_threshold", 85)))

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self):
        """Write current form values back to music_config.json."""
        try:
            # Merge edited values into the existing raw dict (preserves _comments)
            cfg = self._cfg

            if "folders" not in cfg:
                cfg["folders"] = {}
            cfg["folders"]["organized"]     = self._f_organized.text().strip()
            cfg["folders"]["unsorted"]      = self._f_unsorted.text().strip()
            cfg["folders"]["duplicates"]    = self._f_duplicates.text().strip()
            cfg["folders"]["better_quality"]= self._f_better.text().strip()

            if "matching" not in cfg:
                cfg["matching"] = {}
            cfg["matching"]["mode"]                          = self._match_mode.currentData()
            cfg["matching"]["fuzzy_enabled"]                 = self._fuzzy_enabled.isChecked()
            cfg["matching"]["fuzzy_threshold"]               = self._fuzzy_threshold.value()
            cfg["matching"]["use_duration"]                  = self._use_duration.isChecked()
            cfg["matching"]["duration_tolerance_seconds"]    = self._duration_tol.value()
            cfg["matching"]["exact_match_size_tolerance_percent"] = self._size_tol.value()

            if "performance" not in cfg:
                cfg["performance"] = {}
            cfg["performance"]["max_threads"]   = self._max_threads.value()
            cfg["performance"]["cache_enabled"] = self._cache_enabled.isChecked()

            if "acoustid" not in cfg:
                cfg["acoustid"] = {}
            cfg["acoustid"]["enabled"]              = self._fp_enabled.isChecked()
            cfg["acoustid"]["fpcalc_path"]          = self._fp_path.text().strip()
            cfg["acoustid"]["similarity_threshold"] = self._fp_threshold.value()

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)

            self._set_status("Saved.", success=True)
            self.log_message.emit("Settings saved to music_config.json", "success")
            self.settings_saved.emit(cfg)

        except Exception as e:
            self._set_status(f"Save failed: {e}", success=False)
            self.log_message.emit(f"Settings save failed: {e}", "error")

    # ── Status label ──────────────────────────────────────────────────────────

    def _set_status(self, msg: str, success: bool = True):
        colour = COLOURS["log_success"] if success else COLOURS["log_error"]
        self._status_label.setStyleSheet(f"color: {colour}; font-size: 9pt;")
        self._status_label.setText(msg)
