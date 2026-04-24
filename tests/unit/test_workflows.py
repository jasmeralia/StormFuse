# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for CI workflow contracts in DESIGN.md §16."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_uses_make_targets() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "run: make deps" in workflow
    assert "run: make lint" in workflow
    assert "run: make test" in workflow
    assert "ruff check" not in workflow
    assert "mypy src/stormfuse/" not in workflow
    assert "pytest tests/unit/" not in workflow


def test_release_workflow_uses_make_targets_on_windows() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "run: make deps" in workflow
    assert "run: make fetch-ffmpeg" in workflow
    assert "run: make test" in workflow
    assert "run: make installer" in workflow
    assert "shell: bash" in workflow
    assert "pip install -r requirements-dev.txt" not in workflow
    assert "pytest tests/unit/" not in workflow
    assert "pyinstaller build/stormfuse.spec" not in workflow
    assert "makensis build/installer/stormfuse.nsi" not in workflow


def test_makefile_supports_windows_virtualenv_paths() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ifeq ($(OS),Windows_NT)" in makefile
    assert "VENV_BIN := $(VENV)/Scripts" in makefile
    assert "PY       := $(VENV_BIN)/python.exe" in makefile
