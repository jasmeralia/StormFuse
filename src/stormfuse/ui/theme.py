# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme helpers for StormFuse's dark interface."""

from __future__ import annotations

import ctypes
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from stormfuse.ui import tokens

tok = tokens.DARK

GLOBAL_QSS = f"""
QWidget {{
    background-color: {tok.SURFACE};
    color: {tok.TEXT};
    font-size: {tok.FONT_BODY[0]}pt;
    font-weight: {tok.FONT_BODY[1]};
}}

QWidget:disabled {{
    color: {tok.TEXT_MUTED};
}}

QMainWindow::separator {{
    background: {tok.BORDER};
    width: 1px;
    height: 1px;
}}

QDockWidget {{
    color: {tok.TEXT};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background: {tok.SURFACE_RAISED};
    border: 1px solid {tok.BORDER};
    padding: 4px 8px;
}}

QGroupBox {{
    border: 1px solid {tok.BORDER};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: {tok.FONT_BODY_STRONG[1]};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {tok.TEXT};
}}

QPushButton {{
    background-color: {tok.SURFACE_RAISED};
    color: {tok.TEXT};
    border: 1px solid {tok.BORDER};
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: {tok.FONT_BODY_STRONG[1]};
}}

QPushButton:hover,
QPushButton:focus {{
    border-color: {tok.ACCENT};
}}

QPushButton:pressed {{
    background-color: {tok.SURFACE_INSET};
    border-color: {tok.ACCENT};
}}

QPushButton:disabled {{
    background-color: {tok.SURFACE};
    color: {tok.TEXT_MUTED};
    border-color: {tok.BORDER};
}}

QPushButton#primaryButton {{
    background-color: {tok.SUCCESS};
    color: {tok.CANVAS};
    font-weight: 700;
    font-size: 11pt;
    padding: 8px 20px;
    border: none;
}}

QPushButton#primaryButton:hover {{
    background-color: {tokens.darken(tok.SUCCESS, 0.85)};
    border: none;
}}

QPushButton#primaryButton:pressed {{
    background-color: {tokens.darken(tok.SUCCESS, 0.7)};
    border: none;
}}

QPushButton#primaryButton:disabled {{
    background-color: {tok.SURFACE_RAISED};
    color: {tok.TEXT_MUTED};
    border: 1px solid {tok.BORDER};
}}

QLineEdit,
QTextEdit,
QPlainTextEdit {{
    background-color: {tok.SURFACE_INSET};
    color: {tok.TEXT};
    border: 1px solid {tok.BORDER};
    border-radius: 4px;
    padding: 5px;
    selection-background-color: {tok.ACCENT};
    selection-color: {tok.CANVAS};
}}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus {{
    border-color: {tok.ACCENT};
}}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled {{
    color: {tok.TEXT_MUTED};
}}

QTabWidget::pane {{
    border: 1px solid {tok.BORDER};
    border-top: none;
    background: {tok.SURFACE};
}}

QTabBar::tab {{
    background-color: {tok.SURFACE};
    color: {tok.TEXT_MUTED};
    border: 1px solid {tok.BORDER};
    padding: 7px 16px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {tok.SURFACE_RAISED};
    color: {tok.TEXT};
    border-bottom-color: {tok.ACCENT};
}}

QTabBar::tab:hover {{
    color: {tok.TEXT};
    border-color: {tok.ACCENT};
}}

QListWidget {{
    background-color: {tok.SURFACE_INSET};
    color: {tok.TEXT};
    border: 1px solid {tok.BORDER};
    border-radius: 4px;
    padding: 2px;
}}

QListWidget::item:selected {{
    background-color: {tok.ACCENT};
    color: {tok.CANVAS};
}}

QListWidget::item:hover {{
    background-color: {tokens.with_alpha(tok.ACCENT, 0.2)};
}}

QCheckBox {{
    color: {tok.TEXT};
    spacing: 6px;
}}

QCheckBox:disabled {{
    color: {tok.TEXT_MUTED};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background-color: {tok.SURFACE_INSET};
    border: 1px solid {tok.BORDER};
    border-radius: 3px;
}}

QCheckBox::indicator:hover {{
    border-color: {tok.ACCENT};
}}

QCheckBox::indicator:checked {{
    background-color: {tok.ACCENT};
    border-color: {tok.ACCENT};
}}

QCheckBox::indicator:disabled {{
    background-color: {tok.SURFACE};
    border-color: {tok.BORDER};
}}

QProgressBar {{
    border: 1px solid {tok.BORDER};
    border-radius: 4px;
    background-color: {tok.SURFACE_INSET};
    text-align: center;
    color: {tok.TEXT};
}}

QProgressBar::chunk {{
    background-color: {tok.ACCENT};
    border-radius: 3px;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {tok.SURFACE_INSET};
    border: 1px solid {tok.BORDER};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {tok.ACCENT};
    border: 1px solid {tokens.darken(tok.ACCENT, 0.85)};
    border-radius: 7px;
}}

QSlider::sub-page:horizontal {{
    background: {tokens.with_alpha(tok.ACCENT, 0.45)};
    border-radius: 3px;
}}

QStatusBar {{
    background: {tok.SURFACE_RAISED};
    color: {tok.TEXT_SECONDARY};
    border-top: 1px solid {tok.BORDER};
}}

QMenuBar {{
    background: {tok.SURFACE_RAISED};
    color: {tok.TEXT};
    border-bottom: 1px solid {tok.BORDER};
}}

QMenuBar::item:selected {{
    background: {tokens.with_alpha(tok.ACCENT, 0.2)};
}}

QMenu {{
    background: {tok.SURFACE_RAISED};
    color: {tok.TEXT};
    border: 1px solid {tok.BORDER};
}}

QMenu::item:selected {{
    background: {tok.ACCENT};
    color: {tok.CANVAS};
}}

QLabel#sourceSize,
QLabel#encoderBadge,
QLabel#bitratePreview {{
    color: {tok.TEXT_SECONDARY};
}}

QLabel#strategyWhy {{
    color: {tok.ACCENT};
    font-weight: 600;
    text-decoration: underline;
}}

QToolTip {{
    color: {tok.TEXT};
    background-color: {tok.SURFACE_RAISED};
    border: 1px solid {tok.BORDER};
    padding: 4px;
}}

QScrollBar:vertical {{
    background: {tok.SURFACE};
    width: 8px;
    margin: 0;
}}

QScrollBar:horizontal {{
    background: {tok.SURFACE};
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background: {tok.SURFACE_RAISED};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background: {tok.BORDER};
}}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: none;
    border: none;
}}
"""


def dark_palette() -> QPalette:
    """Build the application's dark palette."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tok.SURFACE))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tok.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(tok.SURFACE_INSET))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tok.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tok.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tok.TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(tok.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(tok.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tok.TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tok.DANGER))
    palette.setColor(QPalette.ColorRole.Link, QColor(tok.ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tok.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tok.CANVAS))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tok.TEXT_MUTED))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(tok.TEXT_MUTED),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tok.TEXT_MUTED),
    )
    return palette


def apply_application_theme(app: QApplication) -> None:
    """Apply the dark theme to the entire QApplication."""
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(GLOBAL_QSS)

    for widget in app.topLevelWidgets():
        apply_title_bar_theme(widget)


def apply_widget_theme(widget: QWidget) -> None:
    """Ensure a widget follows the application theme and title-bar mode."""
    qapp = QApplication.instance()
    if isinstance(qapp, QApplication):
        apply_application_theme(qapp)
    apply_title_bar_theme(widget)
    QTimer.singleShot(0, lambda widget=widget: apply_title_bar_theme(widget))


def apply_title_bar_theme(widget: QWidget) -> bool:
    """Apply dark title bar styling on supported Windows builds."""
    if sys.platform != "win32":
        return False
    if not widget.isWindow():
        return False

    try:
        hwnd = int(widget.winId())
    except AttributeError, RuntimeError:
        return False

    windll = getattr(ctypes, "windll", None)
    if windll is None or not hasattr(windll, "dwmapi"):
        return False

    value = ctypes.c_int(1)
    hwnd_value = ctypes.c_void_p(hwnd)
    value_size = ctypes.sizeof(value)
    for attribute in (20, 19):
        result = windll.dwmapi.DwmSetWindowAttribute(
            hwnd_value,
            ctypes.c_uint(attribute),
            ctypes.byref(value),
            value_size,
        )
        if result == 0:
            return True
    return False


def show_information_message(parent: QWidget | None, title: str, text: str) -> int:
    """Show a themed information dialog."""
    return _show_message(parent, QMessageBox.Icon.Information, title, text)


def show_warning_message(parent: QWidget | None, title: str, text: str) -> int:
    """Show a themed warning dialog."""
    return _show_message(parent, QMessageBox.Icon.Warning, title, text)


def _show_message(
    parent: QWidget | None,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
) -> int:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    apply_widget_theme(box)
    return box.exec()
