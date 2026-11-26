"""
Samray Dubber Pro — professional studio theme.

Design tokens keep the whole app on an 8-pixel grid. Panel titles use
uppercase + letter-spacing so they read as chrome rather than content.
Accent colour is used sparingly: primary actions and active state only.
"""

# ---------------------------------------------------------------- palette
BG          = "#0E1116"      # app background (deepest)
PANEL       = "#151A22"      # main panels
PANEL_ALT   = "#1A2029"      # cards / inputs / hovered rows
ELEVATED    = "#1F2631"      # menus, popovers, tooltips
BORDER      = "#242C3A"      # subtle dividers
BORDER_STRONG = "#2F3949"    # stronger outlines on focus

PRIMARY     = "#3B82F6"      # refined blue
PRIMARY_HOV = "#4F91FA"
PRIMARY_DIM = "#1E3A5F"      # tinted backgrounds

SECONDARY   = "#8B5CF6"
SUCCESS     = "#10B981"
WARNING     = "#F59E0B"
DANGER      = "#EF4444"

TEXT        = "#E5E7EB"
TEXT_MUTED  = "#9CA3AF"
TEXT_DIM    = "#6B7280"

FONT_UI = ('-apple-system, "SF Pro Text", "Segoe UI Variable Text", '
           '"Segoe UI", "Inter", "Roboto", sans-serif')
FONT_MONO = ('"SF Mono", "Cascadia Mono", "JetBrains Mono", '
             '"Consolas", monospace')


APP_STYLESHEET = f"""
/* ============================================================ root */
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: {FONT_UI};
    font-size: 12px;
}}
QMainWindow {{
    background-color: {BG};
}}

/* ============================================================ toolbar */
#Toolbar {{
    background-color: {PANEL};
    border-bottom: 1px solid {BORDER};
    padding: 0 12px;
}}
#Toolbar QPushButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 10px;
    color: {TEXT_MUTED};
    font-size: 12px;
}}
#Toolbar QPushButton:hover {{
    background-color: {PANEL_ALT};
    color: {TEXT};
}}
#Toolbar QPushButton:pressed {{
    background-color: {ELEVATED};
}}
#Toolbar QPushButton#Primary {{
    background-color: {PRIMARY};
    color: white;
    font-weight: 600;
    padding: 5px 14px;
}}
#Toolbar QPushButton#Primary:hover {{
    background-color: {PRIMARY_HOV};
}}
#ProjectName {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
#SaveIndicator {{
    color: {TEXT_DIM};
    font-size: 11px;
}}

/* ============================================================ panels */
#Panel {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#PanelTitle {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
}}
#SectionLabel {{
    color: {TEXT_DIM};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
}}
#Muted {{
    color: {TEXT_MUTED};
}}
#Dim {{
    color: {TEXT_DIM};
}}
#TimeCode {{
    color: {TEXT};
    font-family: {FONT_MONO};
    font-size: 11px;
    letter-spacing: 0.3px;
}}
#Card {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

/* ============================================================ buttons */
QPushButton {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 20px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {ELEVATED};
    border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    background-color: {PANEL};
}}

QPushButton#Primary {{
    background-color: {PRIMARY};
    border-color: {PRIMARY};
    color: white;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background-color: {PRIMARY_HOV};
    border-color: {PRIMARY_HOV};
}}
QPushButton#Primary:disabled {{
    background-color: {PRIMARY_DIM};
    border-color: {PRIMARY_DIM};
    color: {TEXT_MUTED};
}}

QPushButton#Accent {{
    background-color: {SECONDARY};
    border-color: {SECONDARY};
    color: white;
    font-weight: 600;
}}
QPushButton#Accent:hover {{
    background-color: #9B6FF7;
    border-color: #9B6FF7;
}}

QPushButton#Success {{
    background-color: {SUCCESS};
    border-color: {SUCCESS};
    color: white;
    font-weight: 600;
}}
QPushButton#Success:hover {{
    background-color: #16C68D;
    border-color: #16C68D;
}}

QPushButton#Danger {{
    background-color: {DANGER};
    border-color: {DANGER};
    color: white;
    font-weight: 600;
}}
QPushButton#Danger:hover {{
    background-color: #F45B5B;
    border-color: #F45B5B;
}}

QPushButton#Ghost {{
    background: transparent;
    border-color: transparent;
    color: {TEXT_MUTED};
}}
QPushButton#Ghost:hover {{
    background-color: {PANEL_ALT};
    color: {TEXT};
}}

QPushButton#IconOnly {{
    padding: 4px;
    min-width: 26px;
    max-width: 26px;
    min-height: 24px;
    max-height: 24px;
}}

/* ============================================================ inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {PRIMARY};
    selection-color: white;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {PRIMARY};
}}
QLineEdit:disabled {{
    color: {TEXT_DIM};
    background-color: {PANEL};
}}

QComboBox {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 20px;
}}
QComboBox:hover {{
    border-color: {BORDER_STRONG};
}}
QComboBox:focus {{
    border-color: {PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_MUTED};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {PRIMARY};
    selection-color: white;
    outline: none;
}}

/* ============================================================ tables */
QTableWidget {{
    background-color: {PANEL};
    alternate-background-color: {PANEL_ALT};
    gridline-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {PRIMARY_DIM};
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {BORDER};
}}
QTableWidget::item:hover {{
    background-color: {PANEL_ALT};
}}
QTableWidget::item:selected {{
    background-color: {PRIMARY_DIM};
    color: {TEXT};
}}
QHeaderView {{
    background-color: transparent;
}}
QHeaderView::section {{
    background-color: {PANEL_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}
QTableCornerButton::section {{
    background-color: {PANEL_ALT};
    border: none;
}}

/* ============================================================ tabs */
QTabWidget::pane {{
    border: none;
    background-color: transparent;
    top: -1px;
}}
QTabBar {{
    background-color: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 12px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {TEXT_MUTED};
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {PRIMARY};
    font-weight: 600;
}}

/* ============================================================ sliders */
QSlider::groove:horizontal {{
    height: 3px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {PRIMARY};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background: {PRIMARY};
}}

/* ============================================================ progress */
QProgressBar {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
    font-size: 10px;
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{
    background-color: {PRIMARY};
    border-radius: 3px;
}}

/* ============================================================ checkbox */
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background: {PANEL_ALT};
}}
QCheckBox::indicator:hover {{
    border-color: {PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCIgdmlld0JveD0iMCAwIDEwIDEwIj48cGF0aCBkPSJNMiA1bDIgMiA0LTRsLTEtMS0zIDMtMS0xeiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=);
}}
QCheckBox::indicator:indeterminate {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCIgdmlld0JveD0iMCAwIDEwIDEwIj48cGF0aCBkPSJNMiA1aDYiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==);
}}

/* Checkboxes drawn inside table cells (subtitle USE column) */
QTableWidget::indicator,
QTableView::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background: {PANEL_ALT};
}}
QTableWidget::indicator:hover,
QTableView::indicator:hover {{
    border-color: {PRIMARY};
}}
QTableWidget::indicator:checked,
QTableView::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCIgdmlld0JveD0iMCAwIDEwIDEwIj48cGF0aCBkPSJNMiA1bDIgMiA0LTRsLTEtMS0zIDMtMS0xeiIgZmlsbD0id2hpdGUiLz48L3N2Zz4=);
}}

/* ============================================================ scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    min-height: 30px;
    border-radius: 5px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER_STRONG};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    min-width: 30px;
    border-radius: 5px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {BORDER_STRONG};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}

/* ============================================================ splitter */
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QSplitter::handle:vertical {{
    height: 4px;
}}
QSplitter::handle:hover {{
    background: {PRIMARY_DIM};
}}

/* ============================================================ statusbar */
QStatusBar {{
    background-color: {PANEL};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {TEXT_MUTED};
    padding: 0 8px;
}}

/* ============================================================ groupbox */
QGroupBox {{
    background-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    background-color: {PANEL};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}

/* ============================================================ menu */
QMenuBar {{
    background-color: {PANEL};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 10px;
    font-size: 12px;
}}
QMenuBar::item:selected {{
    background-color: {PANEL_ALT};
}}
QMenu {{
    background-color: {ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {PRIMARY};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* ============================================================ dialogs */
QDialog {{
    background-color: {PANEL};
}}
QMessageBox {{
    background-color: {PANEL};
}}
QMessageBox QLabel {{
    color: {TEXT};
    font-size: 12px;
}}

/* ============================================================ empty state */
#EmptyIcon {{
    color: {TEXT_DIM};
}}
#EmptyTitle {{
    color: {TEXT_MUTED};
    font-size: 13px;
    font-weight: 600;
}}
#EmptyText {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
"""