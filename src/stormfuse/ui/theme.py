# SPDX-License-Identifier: GPL-3.0-or-later
"""Theme helpers for light/dark/system appearance modes."""

from __future__ import annotations

import ctypes
import sys
from typing import Final, Literal, cast

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

if sys.platform == "win32":
    import winreg
else:
    winreg = None

ThemeMode = Literal["system", "light", "dark"]
ResolvedThemeMode = Literal["light", "dark"]

_THEME_MODE_PROPERTY: Final = "stormfuse.theme_mode"
_RESOLVED_THEME_PROPERTY: Final = "stormfuse.theme_resolved_theme"
_LIGHT_PALETTE_PROPERTY: Final = "stormfuse.theme_light_palette"
_DARK_TOOLTIP_STYLESHEET: Final = (
    "QToolTip {"
    " color: #f8fafc;"
    " background-color: #1f2937;"
    " border: 1px solid #475569;"
    " padding: 2px;"
    "}"
)


def normalize_theme_mode(mode: str | object) -> ThemeMode:
    """Return a valid persisted theme mode."""
    value = "" if mode is None else str(mode).strip().lower()
    if value in {"light", "dark"}:
        return cast(ThemeMode, value)
    return "system"


def windows_prefers_dark() -> bool:
    """Return whether Windows app mode currently prefers dark colors."""
    if sys.platform != "win32":
        return False

    if winreg is None:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (OSError, ValueError):
        return False

    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def resolve_theme_mode(mode: str) -> ResolvedThemeMode:
    """Resolve a persisted mode into a concrete light or dark theme."""
    normalized = normalize_theme_mode(mode)
    if normalized == "light":
        return "light"
    if normalized == "dark":
        return "dark"
    if sys.platform == "win32" and windows_prefers_dark():
        return "dark"
    if _qt_prefers_dark():
        return "dark"
    return "light"


def current_theme_mode(app: QApplication | None = None) -> ThemeMode:
    """Return the current application theme mode."""
    qapp = app or QApplication.instance()
    if not isinstance(qapp, QApplication):
        return "system"
    return normalize_theme_mode(qapp.property(_THEME_MODE_PROPERTY))


def current_resolved_theme(app: QApplication | None = None) -> ResolvedThemeMode:
    """Return the current concrete application theme."""
    qapp = app or QApplication.instance()
    if not isinstance(qapp, QApplication):
        return resolve_theme_mode("system")

    resolved = qapp.property(_RESOLVED_THEME_PROPERTY)
    if resolved in {"light", "dark"}:
        return cast(ResolvedThemeMode, resolved)
    return resolve_theme_mode(current_theme_mode(qapp))


def dark_palette() -> QPalette:
    """Build the application's dark palette."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(32, 36, 43))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(243, 244, 246))
    palette.setColor(QPalette.ColorRole.Base, QColor(22, 27, 34))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(44, 52, 62))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(22, 27, 34))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(243, 244, 246))
    palette.setColor(QPalette.ColorRole.Text, QColor(243, 244, 246))
    palette.setColor(QPalette.ColorRole.Button, QColor(44, 52, 62))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(243, 244, 246))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 99, 71))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(72, 133, 237))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(96, 165, 250))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(148, 163, 184))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(148, 163, 184),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(148, 163, 184),
    )
    return palette


def apply_application_theme(app: QApplication, mode: str) -> ResolvedThemeMode:
    """Apply the selected theme to the entire QApplication."""
    default_palette = app.property(_LIGHT_PALETTE_PROPERTY)
    if not isinstance(default_palette, QPalette):
        default_palette = QPalette(app.palette())
        app.setProperty(_LIGHT_PALETTE_PROPERTY, default_palette)

    normalized = normalize_theme_mode(mode)
    resolved = resolve_theme_mode(normalized)

    if resolved == "dark":
        app.setPalette(dark_palette())
        app.setStyleSheet(_DARK_TOOLTIP_STYLESHEET)
    else:
        app.setPalette(QPalette(default_palette))
        app.setStyleSheet("")

    app.setProperty(_THEME_MODE_PROPERTY, normalized)
    app.setProperty(_RESOLVED_THEME_PROPERTY, resolved)

    for widget in app.topLevelWidgets():
        apply_title_bar_theme(widget, resolved)

    return resolved


def apply_widget_theme(widget: QWidget) -> ResolvedThemeMode:
    """Ensure a widget follows the application's current theme and title-bar mode."""
    qapp = QApplication.instance()
    if not isinstance(qapp, QApplication):
        return resolve_theme_mode("system")

    resolved = apply_application_theme(qapp, current_theme_mode(qapp))
    apply_title_bar_theme(widget, resolved)
    QTimer.singleShot(
        0, lambda widget=widget, resolved=resolved: apply_title_bar_theme(widget, resolved)
    )
    return resolved


def apply_title_bar_theme(widget: QWidget, mode: ResolvedThemeMode | None = None) -> bool:
    """Apply dark-mode title bar styling on supported Windows builds."""
    if sys.platform != "win32":
        return False

    resolved = mode or current_resolved_theme()
    try:
        hwnd = int(widget.winId())
    except (AttributeError, RuntimeError):
        return False

    windll = getattr(ctypes, "windll", None)
    if windll is None or not hasattr(windll, "dwmapi"):
        return False

    value = ctypes.c_int(1 if resolved == "dark" else 0)
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


def _qt_prefers_dark() -> bool:
    qapp = QApplication.instance()
    if not isinstance(qapp, QApplication):
        return False

    try:
        style_hints = qapp.styleHints()
        if style_hints is None:
            return False
        return style_hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False
