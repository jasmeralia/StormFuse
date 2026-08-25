# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for theme helpers and Windows integration."""

from __future__ import annotations

import ctypes
import re
from types import SimpleNamespace

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from stormfuse.ui import theme, tokens

_VALID_QSS_FONT_WEIGHTS = {"normal", "bold", "bolder", "lighter"} | {
    str(weight) for weight in range(100, 1000, 100)
}


def test_global_qss_font_weights_are_valid_qt_values() -> None:
    weights = re.findall(r"font-weight:\s*([^;]+);", theme.GLOBAL_QSS)
    assert weights, "expected font-weight declarations in GLOBAL_QSS"
    for weight in weights:
        assert weight.strip() in _VALID_QSS_FONT_WEIGHTS, f"invalid font-weight: {weight!r}"


def test_font_tokens_use_valid_qss_weights() -> None:
    for name in ("FONT_HEADING", "FONT_BODY_STRONG", "FONT_BODY", "FONT_MONO"):
        _size, weight = getattr(tokens.DARK, name)
        assert str(weight) in _VALID_QSS_FONT_WEIGHTS, f"{name} has invalid weight {weight!r}"


def test_apply_application_theme_sets_fusion_palette_and_stylesheet(qtbot: QtBot) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)

    original_palette = QPalette(app.palette())
    original_stylesheet = app.styleSheet()
    original_style = app.style().objectName() if app.style() is not None else ""

    try:
        theme.apply_application_theme(app)
        palette = app.palette()

        assert app.style() is not None
        assert palette.color(QPalette.ColorRole.Window) == QColor(tokens.DARK.SURFACE)
        assert palette.color(QPalette.ColorRole.Highlight) == QColor(tokens.DARK.ACCENT)
        assert app.styleSheet() == theme.GLOBAL_QSS
    finally:
        app.setStyleSheet(original_stylesheet)
        app.setPalette(original_palette)
        if original_style:
            app.setStyle(original_style)


def test_apply_title_bar_theme_uses_windows_dwm_api(qtbot: QtBot, monkeypatch) -> None:
    calls: list[tuple[int, int, int]] = []

    class _FakeDwmApi:
        def DwmSetWindowAttribute(self, hwnd, attribute, value_ptr, value_size) -> int:
            calls.append(
                (
                    hwnd.value,
                    attribute.value,
                    ctypes.cast(value_ptr, ctypes.POINTER(ctypes.c_int)).contents.value,
                )
            )
            return 0

    monkeypatch.setattr(theme.sys, "platform", "win32")
    monkeypatch.setattr(
        theme.ctypes,
        "windll",
        SimpleNamespace(dwmapi=_FakeDwmApi()),
        raising=False,
    )

    widget = QWidget()
    qtbot.addWidget(widget)

    assert theme.apply_title_bar_theme(widget) is True
    assert calls == [(int(widget.winId()), 20, 1)]


def test_apply_title_bar_theme_skips_child_widgets(qtbot: QtBot, monkeypatch) -> None:
    calls: list[object] = []

    class _FakeDwmApi:
        def DwmSetWindowAttribute(self, *_args) -> int:
            calls.append(_args)
            return 0

    monkeypatch.setattr(theme.sys, "platform", "win32")
    monkeypatch.setattr(
        theme.ctypes,
        "windll",
        SimpleNamespace(dwmapi=_FakeDwmApi()),
        raising=False,
    )

    parent = QWidget()
    child = QWidget(parent)
    qtbot.addWidget(parent)

    assert theme.apply_title_bar_theme(child) is False
    assert calls == []
