# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the custom pylint layering plugin (§4, §13)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from pylint.lint import Run
from pylint.reporters.collecting_reporter import CollectingReporter


def test_jobs_module_cannot_import_ui_package(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/jobs/bad_layer.py",
        """
        from stormfuse.ui.main_window import MainWindow
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-ui-import"]


def test_relative_ui_import_is_blocked_from_ffmpeg_module(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/ffmpeg/bad_relative.py",
        """
        from ..ui import main_window
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-ui-import"]


def test_subprocess_is_restricted_outside_ffmpeg_boundary(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/jobs/bad_subprocess.py",
        """
        from subprocess import PIPE
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-subprocess-import"]


def test_subprocess_is_allowed_in_documented_modules(tmp_path: Path, monkeypatch) -> None:
    ffmpeg_module = _write_module(
        tmp_path,
        "stormfuse/ffmpeg/runner.py",
        """
        import subprocess
        """,
    )
    menu_actions_module = _write_module(
        tmp_path,
        "stormfuse/ui/menu_actions.py",
        """
        from subprocess import run
        """,
    )

    ffmpeg_messages = _run_pylint(tmp_path, ffmpeg_module, monkeypatch)
    menu_messages = _run_pylint(tmp_path, menu_actions_module, monkeypatch)

    assert ffmpeg_messages == []
    assert menu_messages == []


def test_core_module_cannot_import_ui_package(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/core/bad_ui_import.py",
        """
        import stormfuse.ui.main_window
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-core-upward-import"]


def test_core_module_cannot_import_jobs_via_root_importfrom(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/core/bad_jobs_import.py",
        """
        from stormfuse import jobs
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-core-upward-import"]


def test_core_module_may_import_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/core/good_ffmpeg_import.py",
        """
        from stormfuse.ffmpeg import runner
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert messages == []


def test_jobs_module_cannot_import_core_package(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/jobs/bad_core_import.py",
        """
        import stormfuse.core.update_checker
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-core-import"]


def test_ffmpeg_module_cannot_import_core_via_relative_importfrom(
    tmp_path: Path, monkeypatch
) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/ffmpeg/bad_relative_core.py",
        """
        from ..core import update_checker
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert [message.symbol for message in messages] == ["stormfuse-forbidden-core-import"]


def test_jobs_module_may_import_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    module_path = _write_module(
        tmp_path,
        "stormfuse/jobs/good_ffmpeg_import.py",
        """
        from stormfuse.ffmpeg import runner
        """,
    )

    messages = _run_pylint(tmp_path, module_path, monkeypatch)

    assert messages == []


def _write_module(tmp_path: Path, relative_path: str, source: str) -> Path:
    module_path = tmp_path / relative_path
    module_path.parent.mkdir(parents=True, exist_ok=True)

    package_dir = module_path.parent
    while package_dir != tmp_path:
        init_path = package_dir / "__init__.py"
        init_path.touch()
        package_dir = package_dir.parent

    module_path.write_text(dedent(source).strip() + "\n", encoding="utf-8")
    return module_path


def _run_pylint(tmp_path: Path, module_path: Path, monkeypatch) -> list[object]:
    reporter = CollectingReporter()
    monkeypatch.chdir(tmp_path)
    Run(
        [
            str(module_path.relative_to(tmp_path)),
            "--disable=all",
            "--enable=stormfuse-forbidden-ui-import,"
            "stormfuse-forbidden-subprocess-import,"
            "stormfuse-forbidden-core-upward-import,"
            "stormfuse-forbidden-core-import",
            "--load-plugins=stormfuse._pylint_layering",
        ],
        reporter=reporter,
        exit=False,
    )
    return reporter.messages
