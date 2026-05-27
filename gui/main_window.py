"""
Music Tools GUI — Main Window  v0.1
=====================================
QMainWindow with:
  - Left sidebar (categorised tool list)
  - Central QStackedWidget (settings panel + placeholder panels)
  - Bottom log panel (collapsible via splitter)
  - Status bar showing current tool name

Sidebar structure mirrors the README tool categories.
All tool panels show a placeholder in Phase 1; Settings is fully wired.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QSplitter, QLabel, QStatusBar,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

from gui.theme import COLOURS, SIDEBAR_WIDTH, LOG_HEIGHT_DEFAULT
from gui.log_panel import LogPanel
from gui.settings_panel import SettingsPanel


# ── Sidebar data: (display_name, is_header, description) ─────────────────────
# is_header=True → section label, non-selectable

_SIDEBAR_ITEMS: list[tuple[str, bool, str]] = [
    ("⚙  Settings",                  False, "Configure folder paths and matching options"),
    ("── ORGANISATION ──",           True,  ""),
    ("Sort CD Tracks",               False, "Reads disc number tags and sorts tracks into CD1 / CD2 subfolders"),
    ("Sort Albums to Artists",       False, "Moves album folders into the correct artist subfolder using Album Artist tags"),
    ("Sort by Artist",               False, "Sorts loose audio files from a flat folder into artist subfolders"),
    ("── RENAMING ──",               True,  ""),
    ("Rename Album Folders",         False, "Renames album folders to match the Album tag read from the files inside"),
    ("Rename CD Folders",            False, "Removes the space between CD and number  (CD 1 → CD1)"),
    ("Rename Music Files",           False, "Renames audio files using a FileBot-style template string"),
    ("Rename to Cat No.",            False, "Renames album folders to  CATNO - Album Name  using the embedded catalogue number tag"),
    ("Undo Renames",                 False, "Reverts renames from a previous dry-run report CSV"),
    ("── TAG FIXING ──",             True,  ""),
    ("Fix Featuring Tags",           False, "Moves featuring credits from the Artist tag into the Title tag"),
    ("── SCANNING ──",               True,  ""),
    ("Filename Scanner",             False, "Flags filenames that look messy and tracks cleanup progress over time"),
    ("Fix Double Spaces",            False, "Finds and renames files with double spaces in the filename"),
    ("Music Integrity",              False, "Scans for missing tags, unreadable files, and format-specific issues"),
    ("── LIBRARY ──",                True,  ""),
    ("Duplicate Finder",             False, "Compares unsorted downloads against the library and identifies duplicates"),
    ("Library Dupes",                False, "Finds tracks duplicated across two or more artist folders"),
    ("Repair Playlists",             False, "Fixes broken file paths in .m3u / .m3u8 playlist files"),
    ("Clean Album Folders",          False, "Moves non-music files out of album folders into a holding folder"),
    ("── FLAC / CUE ──",             True,  ""),
    ("FLAC to CUE",                  False, "Splits a single-file FLAC + CUE sheet into individual tracks"),
    ("── MUSICBRAINZ ──",            True,  ""),
    ("Anjuna MB Lookup",             False, "Looks up Anjunabeats releases on MusicBrainz by catalogue number"),
    ("MB Lookup",                    False, "General MusicBrainz lookup for any release"),
    ("Tiësto Lookup",                False, "Looks up Tiësto / Black Hole releases on MusicBrainz"),
    ("Anjuna Tagger",                False, "Tags files from a confirmed Anjunabeats lookup report"),
    ("MB Tagger",                    False, "Tags files from a confirmed MusicBrainz lookup report"),
    ("Tagger Undo",                  False, "Reverts tags to their pre-tagger values from a backup report"),
    ("Move from Report",             False, "Moves album folders based on a processed lookup report"),
    ("── PIPELINE ──",               True,  ""),
    ("Pipeline",                     False, "Runs multiple tools in sequence — useful for batch processing new downloads"),
]


class _PlaceholderPanel(QWidget):
    """Shown for every tool that isn't wired up yet (Phase 2+)."""

    def __init__(self, name: str, description: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']}; border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(name)
        lbl.setObjectName("pageTitle")
        tb.addWidget(lbl)
        tb.addStretch()
        layout.addWidget(title_bar)

        # Body
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🔧")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 32pt; background: transparent;")

        coming = QLabel("Coming in Phase 2")
        coming.setObjectName("placeholder")
        coming.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(description)
        desc.setObjectName("pageSubtitle")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color: {COLOURS['text_muted']}; max-width: 480px;")

        bl.addStretch()
        bl.addWidget(icon)
        bl.addSpacing(8)
        bl.addWidget(coming)
        bl.addSpacing(6)
        bl.addWidget(desc)
        bl.addStretch()

        layout.addWidget(body, stretch=1)


class MainWindow(QMainWindow):
    """
    Primary application window.

    Layout
    ------
    ┌─────────────┬──────────────────────────────────┐
    │   Sidebar   │       Central panel (stack)       │
    │  (tools)    │  Settings | Tool placeholder…     │
    │             ├──────────────────────────────────┤
    │             │         Log panel                 │
    └─────────────┴──────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Music Tools")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)
        self._build_ui()
        # Select "Settings" by default
        self._sidebar.setCurrentRow(0)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        self._sidebar = QListWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(SIDEBAR_WIDTH)
        self._sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        self._populate_sidebar()

        # ── Right side: splitter (central stack + log panel) ─────────────────
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.setHandleWidth(1)

        # Central stack
        self._stack = QStackedWidget()
        self._build_stack()
        right_splitter.addWidget(self._stack)

        # Log panel
        self._log = LogPanel()
        self._log.setMinimumHeight(80)
        right_splitter.addWidget(self._log)

        # Default sizes: most space to stack, fixed-ish log
        right_splitter.setSizes([700 - LOG_HEIGHT_DEFAULT, LOG_HEIGHT_DEFAULT])
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)

        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(right_splitter, stretch=1)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

        # ── Wire settings log signal ─────────────────────────────────────────
        self._settings_panel.log_message.connect(
            lambda msg, lvl: getattr(self._log, lvl, self._log.info)(msg)
        )

    def _populate_sidebar(self):
        """Fill the sidebar with tool items and section headers."""
        header_font = QFont()
        header_font.setPointSize(8)
        header_font.setBold(True)

        self._sidebar_rows: list[int | None] = []   # maps list row → stack index or None (header)
        _stack_index = 0

        for name, is_header, _desc in _SIDEBAR_ITEMS:
            item = QListWidgetItem(name)
            if is_header:
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # non-selectable
                item.setFont(header_font)
                item.setForeground(QColor(COLOURS["text_muted"]))
                item.setSizeHint(QSize(SIDEBAR_WIDTH, 24))
                self._sidebar_rows.append(None)
            else:
                item.setSizeHint(QSize(SIDEBAR_WIDTH, 34))
                self._sidebar_rows.append(_stack_index)
                _stack_index += 1
            self._sidebar.addItem(item)

    def _build_stack(self):
        """Add a panel to the stack for each non-header sidebar item."""
        # Page 0: Settings (index 0 → "⚙  Settings")
        self._settings_panel = SettingsPanel()
        self._stack.addWidget(self._settings_panel)

        # Remaining pages: placeholder panels for each tool
        for name, is_header, desc in _SIDEBAR_ITEMS:
            if not is_header and name != "⚙  Settings":
                panel = _PlaceholderPanel(name.strip(), desc)
                self._stack.addWidget(panel)

    # ── Sidebar selection ─────────────────────────────────────────────────────

    def _on_sidebar_changed(self, row: int):
        if row < 0 or row >= len(self._sidebar_rows):
            return
        stack_idx = self._sidebar_rows[row]
        if stack_idx is None:
            return   # header row — ignore
        self._stack.setCurrentIndex(stack_idx)
        name = self._sidebar.item(row).text().strip()
        self._status.showMessage(name)

    # ── Public helpers ────────────────────────────────────────────────────────

    def log(self) -> LogPanel:
        """Return the shared log panel (for external wiring)."""
        return self._log
