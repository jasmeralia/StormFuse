# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for theme helpers and Windows integration."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

from PyQt6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from stormfuse.ui import theme


def test_windows_prefers_dark_reads_registry(monkeypatch) -> None:
    class _FakeKey:
        def __enter__(self) -> _FakeKey:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda *_args: _FakeKey(),
        QueryValueEx=lambda *_args: (0, 0),
    )

    monkeypatch.setattr(theme.sys, "platform", "win32")
    monkeypatch.setattr(theme, "winreg", fake_winreg)

    assert theme.windows_prefers_dark() is True


def test_resolve_theme_mode_follows_windows_system_preference(monkeypatch) -> None:
    monkeypatch.setattr(theme.sys, "platform", "win32")
    monkeypatch.setattr(theme, "windows_prefers_dark", lambda: True)
    monkeypatch.setattr(theme, "_qt_prefers_dark", lambda: False)

    assert theme.resolve_theme_mode("system") == "dark"
    assert theme.resolve_theme_mode("light") == "light"
    assert theme.resolve_theme_mode("dark") == "dark"


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

    assert theme.apply_title_bar_theme(widget, "dark") is True
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

    assert theme.apply_title_bar_theme(child, "dark") is False
    assert calls == []
