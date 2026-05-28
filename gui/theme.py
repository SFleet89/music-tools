"""
Music Tools GUI -- Theme  v0.2
==============================
Centralised colour palette and Qt stylesheet.

build_stylesheet(mode, accent) -> full QSS string.
load_gui_config() / save_gui_config() -> persist theme prefs to gui_config.json.
"""

import json
from pathlib import Path

APP_FONT_FAMILY    = "Segoe UI"
APP_FONT_SIZE      = 10
SIDEBAR_WIDTH      = 230
LOG_HEIGHT_DEFAULT = 150

_PROJECT_ROOT   = Path(__file__).parent.parent
GUI_CONFIG_PATH = _PROJECT_ROOT / "gui_config.json"

ACCENT_PRESETS = [
    ("Blue",   "#007acc"),
    ("Sky",    "#0ea5e9"),
    ("Teal",   "#14b8a6"),
    ("Green",  "#22c55e"),
    ("Purple", "#8b5cf6"),
    ("Pink",   "#ec4899"),
    ("Orange", "#f97316"),
    ("Red",    "#ef4444"),
]

DEFAULT_ACCENT  = "#007acc"
DEFAULT_MODE    = "dark"

_DARK_BASE = {
    "bg":                     "#1e1e1e",
    "surface":                "#252526",
    "sidebar_bg":             "#2c2c2c",
    "sidebar_hover":          "#353535",
    "border":                 "#3c3c3c",
    "text":                   "#d4d4d4",
    "text_muted":             "#8a8a8a",
    "input_bg":               "#3c3c3c",
    "button_text":            "#ffffff",
    "secondary_bg":           "#3c3c3c",
    "secondary_hover":        "#4a4a4a",
    "secondary_pressed":      "#303030",
    "scrollbar_track":        "#2a2a2a",
    "scrollbar_handle":       "#6a6a6a",
    "scrollbar_handle_hover": "#909090",
    "tooltip_bg":             "#3c3c3c",
    "log_bg":                 "#1c1c1c",
    "log_info":               "#d4d4d4",
    "log_success":            "#4ec9b0",
    "log_warning":            "#dcdcaa",
    "log_error":              "#f44747",
    "log_ts":                 "#6a9955",
    "disabled_bg":            "#3a3a3a",
    "disabled_text":          "#8a8a8a",
}

_LIGHT_BASE = {
    "bg":                     "#f5f5f5",
    "surface":                "#ebebeb",
    "sidebar_bg":             "#e5e5e5",
    "sidebar_hover":          "#d8d8d8",
    "border":                 "#cccccc",
    "text":                   "#1e1e1e",
    "text_muted":             "#6b6b6b",
    "input_bg":               "#ffffff",
    "button_text":            "#ffffff",
    "secondary_bg":           "#dcdcdc",
    "secondary_hover":        "#cecece",
    "secondary_pressed":      "#c0c0c0",
    "scrollbar_track":        "#e0e0e0",
    "scrollbar_handle":       "#b0b0b0",
    "scrollbar_handle_hover": "#888888",
    "tooltip_bg":             "#ffffff",
    "log_bg":                 "#efefef",
    "log_info":               "#2d2d2d",
    "log_success":            "#0a6640",
    "log_warning":            "#7a5900",
    "log_error":              "#c0392b",
    "log_ts":                 "#2d7a4f",
    "disabled_bg":            "#e0e0e0",
    "disabled_text":          "#aaaaaa",
}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"

def _lighten(hex_color, amount=22):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(min(255, r+amount), min(255, g+amount), min(255, b+amount))

def _darken(hex_color, amount=22):
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(max(0, r-amount), max(0, g-amount), max(0, b-amount))


def _build_colours(mode="dark", accent=DEFAULT_ACCENT):
    base = dict(_DARK_BASE if mode == "dark" else _LIGHT_BASE)
    base["accent"]         = accent
    base["sidebar_sel"]    = _darken(accent, 30) if mode == "dark" else _lighten(accent, 60)
    base["sidebar_sel_fg"] = "#ffffff"
    base["button_bg"]      = accent
    base["button_hover"]   = _lighten(accent, 22)
    base["button_pressed"] = _darken(accent, 22)
    base["focus_border"]   = accent
    return base


COLOURS = _build_colours(DEFAULT_MODE, DEFAULT_ACCENT)


def apply_theme(mode, accent):
    global COLOURS
    COLOURS.update(_build_colours(mode, accent))


def build_stylesheet(mode=DEFAULT_MODE, accent=DEFAULT_ACCENT):
    c = _build_colours(mode, accent)
    f = APP_FONT_FAMILY
    s = APP_FONT_SIZE

    parts = []
    parts.append(f"""
    QMainWindow, QDialog, QWidget {{
        background: {c['bg']}; color: {c['text']};
        font-family: "{f}"; font-size: {s}pt;
    }}
    QListWidget#sidebar {{
        background: {c['sidebar_bg']}; border: none;
        border-right: 1px solid {c['border']}; outline: none;
    }}
    QListWidget#sidebar::item {{ padding: 6px 14px; border: none; }}
    QListWidget#sidebar::item:selected {{
        background: {c['sidebar_sel']}; color: {c['sidebar_sel_fg']};
        border-left: 3px solid {c['accent']}; padding-left: 11px;
    }}
    QListWidget#sidebar::item:hover:!selected {{ background: {c['sidebar_hover']}; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['input_bg']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 3px;
        padding: 4px 8px; selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c['focus_border']};
    }}
    QLineEdit:read-only {{ color: {c['text_muted']}; }}
    QComboBox::drop-down {{ border: none; padding-right: 6px; }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: {c['input_bg']}; border: none; width: 16px;
    }}
    QPushButton {{
        background: {c['button_bg']}; color: {c['button_text']};
        border: none; border-radius: 3px; padding: 5px 16px; min-width: 64px;
    }}
    QPushButton:hover   {{ background: {c['button_hover']}; }}
    QPushButton:pressed {{ background: {c['button_pressed']}; }}
    QPushButton:disabled {{ background: {c['disabled_bg']}; color: {c['disabled_text']}; }}
    QPushButton#secondary {{
        background: {c['secondary_bg']}; color: {c['text']};
        border: 1px solid {c['border']};
    }}
    QPushButton#secondary:hover   {{ background: {c['secondary_hover']}; }}
    QPushButton#secondary:pressed {{ background: {c['secondary_pressed']}; }}
    QPushButton#browse {{
        background: {c['secondary_bg']}; color: {c['text']};
        border: 1px solid {c['border']}; padding: 4px 10px; min-width: 0;
    }}
    QPushButton#browse:hover {{ background: {c['secondary_hover']}; }}
    QCheckBox {{ color: {c['text']}; spacing: 7px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border: 1px solid {c['border']};
        background: {c['input_bg']}; border-radius: 2px;
    }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; }}
    QCheckBox::indicator:hover   {{ border: 1px solid {c['accent']}; }}
    QRadioButton {{ color: {c['text']}; spacing: 7px; }}
    QRadioButton::indicator {{
        width: 16px; height: 16px; border: 1px solid {c['border']};
        background: {c['input_bg']}; border-radius: 8px;
    }}
    QRadioButton::indicator:checked {{
        background: {c['accent']}; border: 2px solid {c['input_bg']};
        outline: 1px solid {c['accent']};
    }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {c['accent']}; border: none;
        width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {c['button_hover']}; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QGroupBox {{
        border: 1px solid {c['border']}; border-radius: 4px;
        margin-top: 14px; padding-top: 4px;
        color: {c['text_muted']}; font-size: {s-1}pt;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; subcontrol-position: top left;
        padding: 0 6px; left: 10px;
    }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{
        background: {c['scrollbar_track']}; width: 10px; margin: 0; border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['scrollbar_handle']}; border-radius: 5px;
        min-height: 28px; margin: 1px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_handle_hover']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical  {{ background: none; }}
    QScrollBar:horizontal {{
        background: {c['scrollbar_track']}; height: 10px; margin: 0; border-radius: 5px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['scrollbar_handle']}; border-radius: 5px;
        min-width: 28px; margin: 1px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c['scrollbar_handle_hover']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QStatusBar {{
        background: {c['surface']}; color: {c['text_muted']};
        border-top: 1px solid {c['border']}; font-size: {s-1}pt;
    }}
    QTextEdit#log {{
        background: {c['log_bg']}; color: {c['text']};
        border: none; border-top: 1px solid {c['border']};
        font-family: "Consolas", "Courier New", monospace;
        font-size: {s-1}pt; padding: 4px 6px;
    }}
    QToolTip {{
        background: {c['tooltip_bg']}; color: {c['text']};
        border: 1px solid {c['border']}; padding: 4px 6px;
    }}
    QLabel#pageTitle    {{ color: {c['text']};       font-size: {s+3}pt; font-weight: bold; }}
    QLabel#pageSubtitle {{ color: {c['text_muted']}; font-size: {s}pt; }}
    QLabel#sectionLabel {{ color: {c['accent']};     font-size: {s-1}pt; font-weight: bold; }}
    QLabel#fieldLabel   {{ color: {c['text_muted']}; font-size: {s-1}pt; }}
    QLabel#placeholder  {{ color: {c['text_muted']}; font-size: {s+1}pt; }}
    """)
    return "\n".join(parts)


def load_gui_config():
    """Load gui_config.json from project root. Returns defaults if missing."""
    try:
        with open(GUI_CONFIG_PATH, encoding="utf-8") as fh:
            cfg = json.load(fh)
        return {
            "mode":   cfg.get("mode",   DEFAULT_MODE),
            "accent": cfg.get("accent", DEFAULT_ACCENT),
        }
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {"mode": DEFAULT_MODE, "accent": DEFAULT_ACCENT}


def save_gui_config(mode, accent):
    """Save current theme settings to gui_config.json."""
    with open(GUI_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump({"mode": mode, "accent": accent}, fh, indent=2)
