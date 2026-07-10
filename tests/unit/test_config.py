# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for application configuration paths (§9.1, §11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stormfuse import config


def test_log_root_prefers_local_app_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    xdg_data_home = tmp_path / "xdg"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))

    assert config._log_root() == local_app_data / config.APP_NAME / "logs"


def test_log_root_uses_xdg_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xdg_data_home = tmp_path / "xdg"
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))

    assert config._log_root() == xdg_data_home / config.APP_NAME / "logs"


def test_log_root_falls_back_to_home_share(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)

    assert config._log_root() == tmp_path / ".local" / "share" / config.APP_NAME / "logs"
