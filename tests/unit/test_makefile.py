# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for Makefile cleanup behavior (§15)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_make_clean_removes_generated_artifacts_and_preserves_tracked_build_files(
    tmp_path: Path,
) -> None:
    shutil.copy2(REPO_ROOT / "Makefile", tmp_path / "Makefile")

    tracked_paths = [
        tmp_path / "build" / "generate_third_party.py",
        tmp_path / "build" / "fetch_ffmpeg.py",
        tmp_path / "build" / "ffmpeg.sha256",
        tmp_path / "build" / "stormfuse.spec",
        tmp_path / "build" / "installer" / "stormfuse.nsi",
    ]
    generated_paths = [
        tmp_path / "build" / "dist" / "StormFuse",
        tmp_path / "build" / "pyinstaller-cache",
        tmp_path / "build" / "installer" / "tmp",
        tmp_path / "dist" / "StormFuse.exe",
        tmp_path / ".pytest_cache" / "state",
        tmp_path / ".venv" / "bin" / "python",
        tmp_path / ".mypy_cache" / "meta.json",
        tmp_path / ".ruff_cache" / "0.13.0",
        tmp_path / "src" / "__pycache__" / "module.cpython-312.pyc",
        tmp_path / "src" / "module.pyc",
        tmp_path / "src" / "module.pyo",
        tmp_path / "coverage.xml",
    ]

    for path in tracked_paths + generated_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    result = subprocess.run(
        ["make", "clean"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    for path in tracked_paths:
        assert path.exists(), f"expected tracked path to remain: {path}"

    for path in generated_paths:
        assert not path.exists(), f"expected generated artifact to be removed: {path}"
