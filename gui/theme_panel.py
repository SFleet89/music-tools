"""
Music Tools GUI -- Appearance Panel  v0.2
==========================================
Theme controls: dark/light mode and accent colour.
Settings are applied live and saved to gui_config.json.

Emits:
    theme_changed(mode: str, accent: str)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QRadioButton,
    QButtonGroup, QGroupBox, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, Signal

from gui.theme import (
    ACCENT_PRESETS, DEFAULT_MODE, DEFAULT_ACCENT,
    COLOURS, load_gui_config, save_gui_config,
)


class _SwatchButton(QPushButton):
    """A small square colour swatch used to pick an accent colour."""

    SIZE = 30

    def __init__(self, colour, parent=None):
        super().__init__(parent)
        self.colour = colour
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCheckable(True)
        self.setToolTip(colour)
        self._update_style(False)

    def _update_style(self, selected):
        border = "2px solid #ffffff" if selected else "2px solid transparent"
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {self.colour};"
            f"  border: {border};"
            f"  border-radius: 6px;"
            f"  min-width: 0; min-height: 0; padding: 0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border: 2px solid rgba(255,255,255,0.7);"
            f"}}"
        )

    def setSelected(self, selected):
        self.setChecked(selected)
        self._update_style(selected)


class AppearancePanel(QWidget):
    """Appearance settings panel."""

    theme_changed = Signal(str, str)   # (mode, accent)

    def __init__(self, parent=None):
        super().__init__(parent)
        cfg = load_gui_config()
        self._mode   = cfg["mode"]
        self._accent = cfg["accent"]
        self._build_ui()
        self._load_current()

    # -- UI build ---------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet(
            f"background: {COLOURS['surface']}; border-bottom: 1px solid {COLOURS['border']};"
        )
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(20, 0, 20, 0)
        title_lbl = QLabel("Appearance")
        title_lbl.setObjectName("pageTitle")
        sub_lbl = QLabel("Live -- changes apply immediately")
        sub_lbl.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")
        tb.addWidget(title_lbl)
        tb.addSpacing(12)
        tb.addWidget(sub_lbl)
        tb.addStretch()
        outer.addWidget(title_bar)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 24, 28, 24)
        body_layout.setSpacing(20)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        # -- Mode ---------------------------------------------------------------
        mode_box = QGroupBox("Colour Mode")
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(16, 16, 16, 16)
        mode_layout.setSpacing(24)

        self._mode_group  = QButtonGroup(self)
        self._dark_radio  = QRadioButton("Dark")
        self._light_radio = QRadioButton("Light")
        self._dark_radio.setStyleSheet("font-size: 11pt;")
        self._light_radio.setStyleSheet("font-size: 11pt;")
        self._mode_group.addButton(self._dark_radio,  id=0)
        self._mode_group.addButton(self._light_radio, id=1)
        self._dark_radio.toggled.connect(self._on_mode_changed)

        mode_layout.addWidget(self._dark_radio)
        mode_layout.addWidget(self._light_radio)
        mode_layout.addStretch()
        body_layout.addWidget(mode_box)

        # -- Accent colour ------------------------------------------------------
        accent_box = QGroupBox("Accent Colour")
        accent_layout = QVBoxLayout(accent_box)
        accent_layout.setContentsMargins(16, 16, 16, 16)
        accent_layout.setSpacing(10)

        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        self._swatches = {}

        for name, colour in ACCENT_PRESETS:
            btn = _SwatchButton(colour)
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked, c=colour: self._on_accent_changed(c))
            swatches_row.addWidget(btn)
            self._swatches[colour] = btn

        swatches_row.addStretch()

        self._accent_label = QLabel(self._accent)
        self._accent_label.setStyleSheet(f"color: {COLOURS['text_muted']}; font-size: 9pt;")

        accent_layout.addLayout(swatches_row)
        accent_layout.addWidget(self._accent_label)
        body_layout.addWidget(accent_box)

        # -- Reset button -------------------------------------------------------
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setObjectName("secondary")
        reset_btn.setFixedWidth(160)
        reset_btn.clicked.connect(self._reset)
        body_layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        body_layout.addStretch()

    # -- Load / populate --------------------------------------------------------

    def _load_current(self):
        self._dark_radio.setChecked(self._mode == "dark")
        self._light_radio.setChecked(self._mode == "light")
        for colour, btn in self._swatches.items():
            btn.setSelected(colour.lower() == self._accent.lower())
        self._accent_label.setText(self._accent)

    # -- Handlers ---------------------------------------------------------------

    def _on_mode_changed(self):
        self._mode = "dark" if self._dark_radio.isChecked() else "light"
        self._emit()

    def _on_accent_changed(self, colour):
        self._accent = colour
        self._accent_label.setText(colour)
        for c, btn in self._swatches.items():
            btn.setSelected(c.lower() == colour.lower())
        self._emit()

    def _reset(self):
        self._mode   = DEFAULT_MODE
        self._accent = DEFAULT_ACCENT
        self._load_current()
        self._emit()

    def _emit(self):
        save_gui_config(self._mode, self._accent)
        self.theme_changed.emit(self._mode, self._accent)
