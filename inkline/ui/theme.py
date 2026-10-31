"""界面主题：深色「墨色」配色 + QSS 样式表。"""
from __future__ import annotations

COLORS = {
    "bg": "#14161A",
    "panel": "#1B1E24",
    "panel_alt": "#22262E",
    "border": "#2C313B",
    "border_soft": "#242932",
    "text": "#E9EBEF",
    "muted": "#8B93A3",
    "accent": "#D9564A",
    "accent_hover": "#E86B5F",
    "accent_soft": "#3A2321",
    "canvas": "#0E1014",
    "success": "#5FBF8F",
}

QSS = f"""
* {{
    outline: none;
}}

QWidget {{
    color: {COLORS['text']};
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget#root {{
    background: {COLORS['bg']};
}}

QFrame#header {{
    background: {COLORS['panel']};
    border-bottom: 1px solid {COLORS['border_soft']};
}}

QLabel#appName {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 2px;
}}

QLabel#appSub {{
    color: {COLORS['muted']};
    font-size: 11px;
    letter-spacing: 1.5px;
}}

QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#hint {{ color: {COLORS['muted']}; font-size: 12px; }}
QLabel#value {{
    color: {COLORS['text']};
    font-size: 12px;
    font-weight: 600;
    min-width: 34px;
}}

QFrame#card {{
    background: {COLORS['panel']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 10px;
}}

QLabel#cardTitle {{
    color: {COLORS['muted']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QLabel#emptyTitle {{
    color: #C9CEDA;
    font-size: 17px;
    font-weight: 600;
}}

QLabel#emptyHint {{
    color: {COLORS['muted']};
    font-size: 12px;
}}

QPushButton {{
    background: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 7px 14px;
    color: {COLORS['text']};
}}

QPushButton:hover {{
    background: #2A2F38;
    border-color: #3A404B;
}}

QPushButton:pressed {{
    background: #20242B;
}}

QPushButton#primary {{
    background: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
    color: #FFFFFF;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background: {COLORS['accent_hover']};
    border-color: {COLORS['accent_hover']};
}}

QPushButton#primary:disabled {{
    background: #4A2C29;
    border-color: #4A2C29;
    color: #A88480;
}}

QPushButton:disabled {{
    color: #5E6572;
    background: #1C1F25;
    border-color: #262B33;
}}

QPushButton#method {{
    background: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 9px 4px;
    font-size: 13px;
}}

QPushButton#method:hover {{
    border-color: #4A5160;
    background: #272C35;
}}

QPushButton#method:checked {{
    background: {COLORS['accent_soft']};
    border: 1px solid {COLORS['accent']};
    color: #FF9C90;
    font-weight: 600;
}}

QPushButton#chip {{
    background: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 13px;
    padding: 5px 12px;
    color: {COLORS['muted']};
    font-size: 12px;
}}

QPushButton#chip:hover {{
    color: {COLORS['text']};
    border-color: #4A5160;
}}

QPushButton#chip:checked {{
    color: #FFB0A6;
    border-color: {COLORS['accent']};
    background: {COLORS['accent_soft']};
}}

QPushButton#iconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    color: {COLORS['muted']};
    font-size: 13px;
}}

QPushButton#iconButton:hover {{
    background: #262B33;
    color: {COLORS['text']};
}}

QPushButton#iconButton:checked {{
    background: {COLORS['accent_soft']};
    color: #FFB0A6;
    border-color: {COLORS['accent']};
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: #2A2F38;
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {COLORS['accent']};
    border-radius: 2px;
}}

QSlider::add-page:horizontal {{
    background: #2A2F38;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: #F0F2F5;
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background: #FFFFFF;
}}

QSlider::handle:horizontal:pressed {{
    background: {COLORS['accent_hover']};
}}

QSlider::sub-page:horizontal:disabled {{
    background: #3A3F49;
}}

QSlider::groove:horizontal:disabled {{
    background: #23272F;
}}

QSlider::handle:horizontal:disabled {{
    background: #4A505C;
}}

QCheckBox {{
    spacing: 8px;
    color: {COLORS['muted']};
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #3A404B;
    background: {COLORS['panel_alt']};
}}

QCheckBox::indicator:checked {{
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #343A45;
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: #414855;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
    height: 0;
}}

QMenuBar {{
    background: {COLORS['panel']};
    border-bottom: 1px solid {COLORS['border_soft']};
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
}}

QMenuBar::item:selected {{
    background: #2A2F38;
    border-radius: 4px;
}}

QMenu {{
    background: {COLORS['panel_alt']};
    border: 1px solid {COLORS['border']};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 22px 6px 18px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background: {COLORS['accent_soft']};
    color: #FFB0A6;
}}

QMenu::separator {{
    height: 1px;
    background: {COLORS['border']};
    margin: 4px 8px;
}}

QStatusBar {{
    background: {COLORS['panel']};
    border-top: 1px solid {COLORS['border_soft']};
    color: {COLORS['muted']};
    font-size: 12px;
}}

QStatusBar::item {{ border: none; }}

QToolTip {{
    background: {COLORS['panel_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    padding: 5px 8px;
    border-radius: 6px;
}}

QProgressDialog {{
    background: {COLORS['panel']};
}}

QMessageBox {{
    background: {COLORS['panel']};
}}

QMenu::icon {{ padding-left: 6px; }}
"""
