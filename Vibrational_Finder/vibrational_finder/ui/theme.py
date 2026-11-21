from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


BRAND_ACCENT = "#c8324b"
BRAND_ACCENT_BORDER = "#e05b70"
BRAND_BANDS = "#b32645"
IR_RAMAN_BRAND_CRIMSON = "#9f2435"


SEMANTIC_COLORS = {
    "match": "#e5f0fc",
    "residual": "#e2f4eb",
    "warning": "#fff0cf",
    "error": "#fce8ed",
    "semantic_text": "#202124",
}


def is_dark_theme(widget: QWidget) -> bool:
    app = QApplication.instance()
    palette = app.palette() if app is not None else widget.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def theme_colors(dark: bool = False, widget: QWidget | None = None) -> dict[str, str]:
    if widget is not None:
        dark = is_dark_theme(widget)
    if dark:
        return {
            "bg": "#050102",
            "panel": "#080203",
            "alt": "#0b0304",
            "text": "#f7e6eb",
            "muted": "#cba0ad",
            "border": "#241018",
            "selected": "#251017",
            "input": "#080203",
            "header": "#18090d",
            "hover": "#16070a",
            "link": BRAND_ACCENT_BORDER,
            "accent": BRAND_ACCENT,
            "cell_border": "#321722",
            "button": "#251017",
            "button_hover": "#351522",
            "button_pressed": "#461b2a",
            "button_border": "#4a2230",
            "button_emphasis": "#3b1724",
            "button_emphasis_hover": "#522034",
            "button_emphasis_border": "#6b2d42",
            **SEMANTIC_COLORS,
        }
    return {
        "bg": "#fff5f7",
        "panel": "#ffffff",
        "alt": "#fff0f3",
        "text": "#522636",
        "muted": "#8c6070",
        "border": "#efd4dc",
        "selected": "#f7e3e7",
        "input": "#ffffff",
        "header": "#fbeaf0",
        "hover": "#fbe6ed",
        "link": BRAND_ACCENT_BORDER,
        "accent": BRAND_ACCENT,
        "cell_border": "#e3bdc9",
        "button": "#fff0f3",
        "button_hover": "#fbe6ed",
        "button_pressed": "#f7e3e7",
        "button_border": "#efd4dc",
        "button_emphasis": "#f9dfe7",
        "button_emphasis_hover": "#f4ccd8",
        "button_emphasis_border": "#dfa9ba",
        **SEMANTIC_COLORS,
    }


def _asset(name: str) -> str:
    return (Path(__file__).parent / "assets" / name).resolve().as_posix()


def colored_hover_background(color: str) -> str:
    return QColor(color).darker(120).name()


def window_style(dark: bool = False) -> str:
    colors = theme_colors(dark)
    caret = _asset("chevron-light.svg" if dark else "chevron-dark.svg")
    up_caret = _asset("chevron-up-light.svg" if dark else "chevron-up-dark.svg")
    tick = _asset("check.svg")
    partial = _asset("partial.svg")
    accent_hover = colored_hover_background(BRAND_ACCENT)
    bands_hover = colored_hover_background(BRAND_BANDS)
    return f"""
        QMainWindow, QDialog {{ background: {colors['bg']}; color: {colors['text']}; font-size: 13px; }}
        QWidget {{ color: {colors['text']}; }}
        QLabel {{ background: transparent; }}
        QLabel[uiRole="sectionTitle"] {{ color: {colors['text']}; font-weight: 600; padding: 4px 0; }}
        QLabel[uiRole="muted"], QLabel#processingPlaceholder {{ color: {colors['muted']}; }}
        QGroupBox[databaseGroup="true"] {{
            background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 7px;
            margin-top: 9px; padding-top: 4px; font-weight: 600;
        }}
        QGroupBox[databaseGroup="true"]::title {{
            subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 0 4px;
            color: {colors['text']};
        }}
        QFrame[databaseGroup="true"] {{
            background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 8px;
        }}
        QScrollArea[databaseScroll="true"] {{ background: {colors['bg']}; border: none; }}
        QWidget#databaseScrollBody {{ background: {colors['bg']}; }}
        QWidget#projectSidebar, QWidget#compositionElements, QWidget#compositionControls {{
            background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 9px;
        }}
        QWidget#finderPlotControlBar {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 8px; }}
        QLabel#cursorReadout {{ background: {colors['input']}; color: {colors['muted']}; border: 0; border-radius: 5px; padding: 4px 7px; font-size: 12px; }}
        QTabWidget::pane {{ background: {colors['panel']}; border: 1px solid {colors['border']}; border-radius: 8px; }}
        QTabBar::tab {{ background: transparent; color: {colors['muted']}; border: 0; border-bottom: 2px solid transparent; padding: 9px 12px; margin-right: 2px; }}
        QTabBar::tab:selected {{ background: {colors['panel']}; color: {colors['text']}; border-bottom: 2px solid {BRAND_ACCENT}; font-weight: 600; }}
        QTabBar::tab:hover:!selected {{ background: {colors['hover']}; color: {colors['text']}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit {{
            background: {colors['input']}; color: {colors['text']}; border: 1px solid {colors['border']}; border-radius: 6px; min-height: 24px; padding: 3px 8px; selection-background-color: {colors['selected']};
        }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateTimeEdit:disabled {{ color: {colors['muted']}; background: {colors['bg']}; }}
        QComboBox {{ padding-right: 23px; }}
        QComboBox::drop-down {{ width: 21px; border: 0; }}
        QComboBox::down-arrow {{ image: url("{caret}"); width: 11px; height: 11px; }}
        QSpinBox, QDoubleSpinBox, QDateTimeEdit {{ padding-right: 27px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 22px; border-left: 1px solid {colors['border']}; border-bottom: 1px solid {colors['border']}; border-top-right-radius: 5px; background: {colors['alt']}; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border-left: 1px solid {colors['border']}; border-bottom-right-radius: 5px; background: {colors['alt']}; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateTimeEdit::up-arrow {{ image: url("{up_caret}"); width: 10px; height: 10px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateTimeEdit::down-arrow {{ image: url("{caret}"); width: 10px; height: 10px; }}
        QPushButton, QToolButton {{ background: {colors['button']}; color: {colors['text']}; border: 1px solid {colors['button_border']}; border-radius: 6px; padding: 6px 10px; font-weight: 500; }}
        QPushButton:hover:enabled, QToolButton:hover:enabled {{ background: {colors['button_hover']}; border-color: {BRAND_ACCENT_BORDER}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {colors['button_pressed']}; }}
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {BRAND_ACCENT_BORDER}; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {colors['muted']}; background: {colors['bg']}; }}
        QToolButton[databaseHelp="true"] {{ padding: 0; }}
        QPushButton[databaseAction="emphasis"]:enabled {{
            background: {colors['button_emphasis']}; border-color: {colors['button_emphasis_border']}; font-weight: 600;
        }}
        QPushButton[databaseAction="emphasis"]:hover:enabled {{
            background: {colors['button_emphasis_hover']}; border-color: {BRAND_ACCENT_BORDER};
        }}
        QPushButton[databaseAction="clear"]:enabled {{ border-color: {colors['button_emphasis_border']}; }}
        QPushButton#compositionSearchButton, QPushButton#compositionResetButton {{ background: {colors['button_emphasis']}; border-color: {colors['button_emphasis_border']}; font-weight: 600; }}
        QPushButton#compositionSearchButton:hover:enabled, QPushButton#compositionResetButton:hover:enabled {{ background: {colors['button_emphasis_hover']}; border-color: {BRAND_ACCENT_BORDER}; }}
        QToolButton[plotToggle="true"]:checked {{ background: {colors['selected']}; border-color: {BRAND_ACCENT_BORDER}; }}
        QToolButton[plotToggle="true"]:checked:hover:enabled {{ background: {colored_hover_background(colors['selected'])}; border-color: {BRAND_ACCENT_BORDER}; }}
        QPushButton[uiRole="primary"] {{ background: {BRAND_ACCENT}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; font-weight: 600; }}
        QPushButton[uiRole="primary"]:hover:enabled {{ background: {accent_hover}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}
        QPushButton[searchMode="auto"] {{ background: {BRAND_ACCENT}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; font-weight: 600; }}
        QPushButton[searchMode="auto"]:hover:enabled {{ background: {accent_hover}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}
        QPushButton[searchMode="bands"] {{ background: {BRAND_BANDS}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; font-weight: 600; }}
        QPushButton[searchMode="bands"]:hover:enabled {{ background: {bands_hover}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}
        QCheckBox {{ spacing: 6px; padding: 2px 0; }}
        QCheckBox::indicator, QTreeView::indicator {{ width: 14px; height: 14px; border: 1px solid {colors['muted']}; border-radius: 4px; background: {colors['input']}; }}
        QCheckBox::indicator:checked, QTreeView::indicator:checked {{ background: {BRAND_ACCENT}; border-color: {BRAND_ACCENT_BORDER}; image: url("{tick}"); }}
        QCheckBox::indicator:indeterminate, QTreeView::indicator:indeterminate {{ background: {BRAND_ACCENT}; border-color: {BRAND_ACCENT_BORDER}; image: url("{partial}"); }}
        QCheckBox::indicator:hover {{ border-color: {BRAND_ACCENT_BORDER}; }}
        QCheckBox:disabled {{ color: {colors['muted']}; }}
        QSlider::groove:horizontal {{ height: 4px; background: {colors['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {BRAND_ACCENT}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; background: {BRAND_ACCENT_BORDER}; border: 1px solid {BRAND_ACCENT}; border-radius: 7px; }}
        QTreeWidget, QTableView, QTableWidget, QTextEdit, QPlainTextEdit {{
            background: {colors['panel']}; alternate-background-color: {colors['alt']}; color: {colors['text']};
            border: 1px solid {colors['border']}; border-radius: 7px; gridline-color: {colors['cell_border']}; selection-background-color: {colors['selected']}; outline: 0;
        }}
        QTreeWidget#projectTree {{ border: 0; background: transparent; }}
        QTreeWidget::item {{ padding: 5px 3px; }}
        QTableView::item, QTableWidget::item {{ padding: 5px 7px; border-bottom: 1px solid {colors['cell_border']}; border-right: 1px solid {colors['cell_border']}; }}
        QTableWidget#candidateTable::item, QTableWidget#acceptedComponentsTable::item {{ padding: 2px 5px; }}
        QTreeWidget::item:selected, QTableView::item:selected, QTableWidget::item:selected {{ background: {colors['selected']}; color: {colors['text']}; }}
        QHeaderView {{ background: {colors['header']}; }}
        QHeaderView::section {{ background: {colors['header']}; color: {colors['muted']}; border: 0; border-bottom: 1px solid {colors['cell_border']}; border-right: 1px solid {colors['cell_border']}; padding: 8px 7px; font-size: 12px; font-weight: 600; }}
        QTableCornerButton::section {{ background: {colors['header']}; border: 0; }}
        QSplitter::handle {{ background: transparent; }}
        QSplitter::handle:hover {{ background: {colors['border']}; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0 2px; }}
        QScrollBar::handle {{ background: {colors['border']}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
        QScrollBar::handle:hover {{ background: {colors['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QMenu {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 5px; }}
        QMenu::item {{ padding: 7px 22px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {colors['selected']}; }}
        QMenu::item:disabled {{ color: {colors['muted']}; }}
        QToolTip {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 5px; opacity: 255; }}
    """
