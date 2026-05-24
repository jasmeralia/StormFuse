# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify config.APP_VERSION resolution paths."""

from __future__ import annotations

import importlib
import sys

import pytest


def test_config_uses_generated_version_when_present() -> None:
    # _version.py is written by `make deps` (or `scripts/write_version.py
    # --tag` in CI); when present, config exposes its value verbatim.
    from stormfuse import _version, config

    assert _version.__version__ == config.APP_VERSION


def test_config_falls_back_to_dev_sentinel_when_version_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Setting sys.modules[name] = None makes a subsequent `import name` raise
    # ImportError, which is exactly the situation a fresh checkout (no
    # generated _version.py yet) presents.
    monkeypatch.setitem(sys.modules, "stormfuse._version", None)
    monkeypatch.delitem(sys.modules, "stormfuse.config", raising=False)

    reloaded = importlib.import_module("stormfuse.config")
    try:
        assert reloaded.APP_VERSION == "0.0.0+dev"
    finally:
        # Pop the reloaded module so subsequent tests see the original config
        # (the monkeypatch.setitem on _version is reverted automatically).
        sys.modules.pop("stormfuse.config", None)
        importlib.import_module("stormfuse.config")
