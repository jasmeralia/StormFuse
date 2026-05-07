# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for CI workflow contracts in DESIGN.md §16."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_uses_make_targets() -> None:
    assert not (REPO_ROOT / ".github" / "workflows" / "ci.yml").exists()

    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "name: CI / Build & Release" in workflow
    assert "branches:\n      - master" in workflow
    assert "pull_request:" in workflow
    assert "contents: write" in workflow
    assert "pull-requests: write" in workflow
    assert "run: make deps" in workflow
    assert "run: make lint" in workflow
    assert "run: make test" in workflow
    assert "needs: sync-version" in workflow
    assert "needs.sync-version.outputs.skip_release != 'true'" in workflow
    assert "ruff check" not in workflow
    assert "mypy src/stormfuse/" not in workflow
    assert "pytest tests/unit/" not in workflow
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "codecov/codecov-action@v6" in workflow
    assert "@v4" not in workflow
    assert "@v5" not in workflow


def test_release_workflow_uses_make_targets_on_windows() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "TAG_NAME" in workflow
    assert "Sync Release Version" in workflow
    assert "scripts/sync_release_version.py" in workflow
    assert "Tag ${tag_name} does not match APP_VERSION ${app_version}" in workflow
    assert "git add src/stormfuse/config.py README.md CHANGELOG.md" in workflow
    assert 'git commit -m "Release ${tag_name}"' in workflow
    assert 'git push --force-with-lease origin "HEAD:${bump_branch}"' in workflow
    assert "gh pr create" in workflow
    assert "create the release bump PR manually" in workflow
    assert "HEAD:master" not in workflow
    assert "Create Release Tag" in workflow
    assert "refs/tags/${{ env.TAG_NAME }}" in workflow
    assert "actions/checkout@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "codecov/codecov-action@v6" in workflow
    assert "softprops/action-gh-release@v3" in workflow
    assert 'gh run download "$GITHUB_RUN_ID" --name StormFuse-installer --dir .' in workflow
    assert "actions: read" in workflow
    assert "actions/download-artifact" not in workflow
    assert "@v4" not in workflow
    assert "@v5" not in workflow
    assert workflow.count("run: make generate-third-party") == 2
    assert "Ensure NSIS" in workflow
    assert "GITHUB_PATH" in workflow
    assert "run: make deps" in workflow
    assert "run: make fetch-ffmpeg" in workflow
    assert "run: make test" in workflow
    assert "run: make installer" in workflow
    assert "shell: bash" in workflow
    assert "pip install -r requirements-dev.txt" not in workflow
    assert "pytest tests/unit/" not in workflow
    assert "pyinstaller build/stormfuse.spec" not in workflow
    assert "makensis build/installer/stormfuse.nsi" not in workflow
    assert "gh release create" not in workflow


def test_makefile_supports_windows_virtualenv_paths() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ifeq ($(OS),Windows_NT)" in makefile
    assert "VENV_BIN := $(VENV)/Scripts" in makefile
    assert "PY       := $(VENV_BIN)/python.exe" in makefile
