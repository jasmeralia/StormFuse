# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for diagnostic log uploads."""

from __future__ import annotations

import base64

from stormfuse.config import APP_VERSION
from stormfuse.core import log_uploader
from stormfuse.core.log_uploader import LogUploader, _UploadResponse
from stormfuse.ffmpeg.encoders import EncoderChoice


def test_upload_disabled_returns_clear_message(tmp_path) -> None:
    uploader = LogUploader(log_dir=tmp_path, enabled=False, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "not enabled" in message.lower()


def test_upload_success_posts_logs_and_metadata(tmp_path, monkeypatch) -> None:
    first_log = tmp_path / "stormfuse-20260424-111111-1.log"
    ffmpeg_report = tmp_path / "ffmpeg-job-123.log"
    latest_log = tmp_path / "latest.log"
    first_log.write_text("session log\n", encoding="utf-8")
    ffmpeg_report.write_text("ffmpeg debug log\n", encoding="utf-8")
    latest_log.write_text("latest log\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_post(self, payload):
        captured["endpoint"] = self._endpoint
        captured["payload"] = payload
        return _UploadResponse(status_code=200, body='{"upload_id": "abc123"}')

    monkeypatch.setattr(LogUploader, "_post_payload", fake_post)
    monkeypatch.setattr(log_uploader.socket, "gethostname", lambda: "DESKTOP-TEST")
    monkeypatch.setattr(log_uploader.getpass, "getuser", lambda: "morgan")
    monkeypatch.setattr(log_uploader.platform, "platform", lambda: "Windows-11")

    uploader = LogUploader(
        log_dir=tmp_path,
        endpoint="https://stormfuse.example/logs/upload",
        enabled=True,
        encoder=EncoderChoice.LIBX264,
    )

    success, message = uploader.upload("Clicked Combine and ffmpeg failed.")

    assert success
    assert message == "Logs sent (ID: abc123)"
    assert captured["endpoint"] == "https://stormfuse.example/logs/upload"

    payload = captured["payload"]
    assert payload["app_version"] == APP_VERSION
    assert payload["user_notes"] == "Clicked Combine and ffmpeg failed."
    assert payload["hostname"] == "DESKTOP-TEST"
    assert payload["username"] == "morgan"
    assert payload["os_version"] == "Windows-11"
    assert payload["os_platform"] == log_uploader.sys.platform
    assert payload["encoder"] == "libx264"
    assert [entry["filename"] for entry in payload["log_files"]] == [
        "ffmpeg-job-123.log",
        "latest.log",
        "stormfuse-20260424-111111-1.log",
    ]
    encoded = payload["log_files"][1]["content"]
    assert base64.b64decode(encoded.encode("ascii")).replace(b"\r\n", b"\n") == b"latest log\n"


def test_upload_upgrade_required_returns_clear_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_payload",
        lambda self, payload: _UploadResponse(
            status_code=426,
            body='{"min_supported_version": "1.0.6"}',
        ),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "too old" in message.lower()
    assert "1.0.6" in message


def test_upload_timeout_returns_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_payload",
        lambda self, payload: (_ for _ in ()).throw(TimeoutError("timeout")),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "timed out" in message.lower()


def test_upload_connection_error_returns_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_payload",
        lambda self, payload: (_ for _ in ()).throw(ConnectionError("no route")),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "connect" in message.lower()
