# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests for diagnostic failure routing (§9.3, §10, §11.4)."""

from __future__ import annotations

from pytestqt.qtbot import QtBot

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.jobs.base import JobError
from stormfuse.ui.combine_tab import CombineTab
from stormfuse.ui.compress_tab import CompressTab


def test_compress_tab_uses_diagnostic_dialog_for_job_failures(qtbot: QtBot, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_show(parent, **kwargs) -> None:
        captured["parent"] = parent
        captured.update(kwargs)

    monkeypatch.setattr("stormfuse.ui.compress_tab.show_diagnostic_dialog", fake_show)

    tab = CompressTab()
    tab.set_encoder(EncoderChoice.NVENC)
    qtbot.addWidget(tab)

    error = JobError(
        job_id="compress-123",
        event="ffmpeg.exit",
        message="Compression failed",
        stderr_tail="line 1\nline 2\n",
    )

    tab.on_job_failed(error)

    assert tab._phase_label.text() == "Failed"  # type: ignore[attr-defined]
    assert captured["parent"] is tab
    assert captured["title"] == "Compress failed"
    assert captured["message"] == "Compression failed"
    assert captured["event"] == "ffmpeg.exit"
    assert captured["stderr_tail"] == "line 1\nline 2\n"
    assert captured["encoder"] == EncoderChoice.NVENC
    guidance = captured["guidance"]
    assert guidance.summary == "Compress failed while ffmpeg was processing the job."
    assert guidance.why == "Compression failed"
    assert (
        guidance.next_step
        == "Review the stderr excerpt below, confirm the output folder is writable, "
        "then try a larger target size or disable 2-pass and rerun."
    )


def test_combine_tab_uses_guidance_for_probe_failures(qtbot: QtBot, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_show(parent, **kwargs) -> None:
        captured["parent"] = parent
        captured.update(kwargs)

    monkeypatch.setattr("stormfuse.ui.combine_tab.show_diagnostic_dialog", fake_show)

    tab = CombineTab()
    tab.set_encoder(EncoderChoice.LIBX264)
    qtbot.addWidget(tab)

    error = JobError(
        job_id="combine-123",
        event="probe.error",
        message="Probe failed for clip01.mkv",
        stderr_tail="ffprobe could not read input\n",
    )

    tab.on_job_failed(error)

    assert captured["parent"] is tab
    assert captured["title"] == "Combine failed"
    guidance = captured["guidance"]
    assert guidance.summary == (
        "Combine could not start because StormFuse could not inspect one of the selected files."
    )
    assert guidance.why == "Probe failed for clip01.mkv"
    assert (
        guidance.next_step == "Check that each file still exists locally, is an MKV/MP4, "
        "and is not locked by another app, then try again."
    )
