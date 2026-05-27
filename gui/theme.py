"""
Music Tools GUI — Theme  v0.1
==============================
Centralised colour palette and Qt stylesheet.
Import COLOURS for individual values; call build_stylesheet() to get the
full QSS string to pass to QApplication.setStyleSheet().
"""

APP_FONT_FAMILY    = "Segoe UI"
APP_FONT_SIZE      = 10          # pt
SIDEBAR_WIDTH      = 230
LOG_HEIGHT_DEFAULT = 150

COLOURS = {
    "bg":           "#1e1e1e",
    "surface":      "#252526",
    "sidebar_bg":   "#2c2c2c",
    "sidebar_sel":  "#094771",
    "sidebar_hdr":  "#3c3c3c",
    "border":       "#3c3c3c",
    "accent":       "#007acc",
    "text":         "#d4d4d4",
    "text_muted":   "#8a8a8a",
    "input_bg":     "#3c3c3c",
    "button_bg":    "#0e639c",
    "button_hover": "#1177bb",
    "button_text":  "#ffffff",
    # Log colours (used as HTML colour strings in log_panel.py)
    "log_bg":       "#1e1e1e",
    "log_info":     "#d4d4d4",
    "log_success":  "#4ec9b0",
    "log_warning":  "#dcdcaa",
    "log_error":    "#f44747",
    "log_ts":       "#6a9955",
}


def build_stylesheet() -> str:
    c = COLOURS
    f = APP_FONT_FAMILY
    s = APP_FONT_SIZE

    return f"""
    /* ── Base ──────────────────────────────────────────── */
    QMainWindow, QDialog, QWidget {{
        background: {c['bg']};
        color: {c['text']};
        font-family: "{f}";
        font-size: {s}pt;
    }}

    /* ── Sidebar list ───────────────────────────────────── */
    QListWidget#sidebar {{
        background: {c['sidebar_bg']};
        border: none;
        border-right: 1px solid {c['border']};
        outline: none;
    }}
    QListWidget#sidebar::item {{
        padding: 6px 14px;
        border: none;
    }}
    QListWidget#sidebar::item:selected {{
        background: {c['sidebar_sel']};
        color: #ffffff;
        border-left: 3px solid {c['accent']};
        padding-left: 11px;
    }}
    QListWidget#sidebar::item:hover:!selected {{
        background: #353535;
    }}

    /* ── Text inputs / spinboxes / combos ───────────────── */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['input_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        padding: 4px 8px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {c['accent']};
    }}
    QLineEdit:read-only {{
        color: {c['text_muted']};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 6px;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: {c['input_bg']};
        border: none;
        width: 16px;
    }}

    /* ── Buttons ────────────────────────────────────────── */
    QPushButton {{
        background: {c['button_bg']};
        color: {c['button_text']};
        border: none;
        border-radius: 3px;
        padding: 5px 16px;
        min-width: 64px;
    }}
    QPushButton:hover  {{ background: {c['button_hover']}; }}
    QPushButton:pressed {{ background: #0a4f7e; }}
    QPushButton:disabled {{ background: #3a3a3a; color: {c['text_muted']}; }}

    QPushButton#secondary {{
        background: {c['input_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
    }}
    QPushButton#secondary:hover  {{ background: #4a4a4a; }}
    QPushButton#secondary:pressed {{ background: #303030; }}

    QPushButton#browse {{
        background: {c['input_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 4px 10px;
        min-width: 0;
    }}
    QPushButton#browse:hover {{ background: #4a4a4a; }}

    /* ── Checkbox ───────────────────────────────────────── */
    QCheckBox {{
        color: {c['text']};
        spacing: 7px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {c['border']};
        background: {c['input_bg']};
        border-radius: 2px;
    }}
    QCheckBox::indicator:checked {{
        background: {c['accent']};
        border: 1px solid {c['accent']};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {c['accent']};
    }}

    /* ── Group box ──────────────────────────────────────── */
    QGroupBox {{
        border: 1px solid {c['border']};
        border-radius: 4px;
        margin-top: 14px;
        padding-top: 4px;
        color: {c['text_muted']};
        font-size: {s - 1}pt;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        left: 10px;
    }}

    /* ── Scroll bars ────────────────────────────────────── */
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{
        background: {c['surface']};
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #555;
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #666; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {c['surface']};
        height: 8px;
    }}
    QScrollBar::handle:horizontal {{
        background: #555;
        border-radius: 4px;
        min-width: 20px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* ── Splitter ───────────────────────────────────────── */
    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    /* ── Status bar ─────────────────────────────────────── */
    QStatusBar {{
        background: {c['surface']};
        color: {c['text_muted']};
        border-top: 1px solid {c['border']};
        font-size: {s - 1}pt;
    }}

    /* ── Log panel text area ────────────────────────────── */
    QTextEdit#log {{
        background: {c['log_bg']};
        color: {c['text']};
        border: none;
        border-top: 1px solid {c['border']};
        font-family: "Consolas", "Courier New", monospace;
        font-size: {s - 1}pt;
        padding: 4px 6px;
    }}

    /* ── Tool tip ───────────────────────────────────────── */
    QToolTip {{
        background: #3c3c3c;
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 4px 6px;
    }}

    /* ── Labels ─────────────────────────────────────────── */
    QLabel#pageTitle {{
        color: {c['text']};
        font-size: {s + 3}pt;
        font-weight: bold;
    }}
    QLabel#pageSubtitle {{
        color: {c['text_muted']};
        font-size: {s}pt;
    }}
    QLabel#sectionLabel {{
        color: {c['accent']};
        font-size: {s - 1}pt;
        font-weight: bold;
    }}
    QLabel#fieldLabel {{
        color: {c['text_muted']};
        font-size: {s - 1}pt;
    }}
    QLabel#placeholder {{
        color: {c['text_muted']};
        font-size: {s + 1}pt;
    }}
    """
