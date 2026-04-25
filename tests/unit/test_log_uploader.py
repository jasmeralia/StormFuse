# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for diagnostic log uploads."""

from __future__ import annotations

import gzip
import json

from stormfuse.config import APP_VERSION
from stormfuse.core import log_uploader
from stormfuse.core.log_uploader import LogUploader, _UploadResponse
from stormfuse.ffmpeg.encoders import EncoderChoice


def _make_init_response(filenames: list[str], upload_id: str = "test-uuid") -> _UploadResponse:
    presigned_urls = [
        {"filename": f, "url": f"https://s3.example/bucket/{upload_id}/{f}.gz"} for f in filenames
    ]
    return _UploadResponse(
        status_code=200,
        body=json.dumps({"upload_id": upload_id, "presigned_urls": presigned_urls}),
    )


def _make_complete_response(upload_id: str = "test-uuid") -> _UploadResponse:
    return _UploadResponse(
        status_code=200,
        body=json.dumps({"success": True, "upload_id": upload_id}),
    )


def test_upload_disabled_returns_clear_message(tmp_path) -> None:
    uploader = LogUploader(log_dir=tmp_path, enabled=False, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "not enabled" in message.lower()


def test_upload_success_init_complete_flow(tmp_path, monkeypatch) -> None:
    log1 = tmp_path / "stormfuse-20260424-111111-1.log"
    latest = tmp_path / "latest.log"
    ffmpeg_report = tmp_path / "ffmpeg-job-123.log"
    log1.write_text("session log\n", encoding="utf-8")
    latest.write_text("latest log\n", encoding="utf-8")
    ffmpeg_report.write_text("ffmpeg debug\n", encoding="utf-8")  # must be excluded

    post_calls: list[tuple[str, dict]] = []
    put_calls: list[tuple[str, bytes, str]] = []

    def fake_post_json(self, url, payload):
        post_calls.append((url, payload))
        if url.endswith("/logs/upload"):
            return _make_init_response(payload.get("filenames", []))
        return _make_complete_response()

    def fake_put_bytes(self, url, data, content_type):
        put_calls.append((url, data, content_type))

    monkeypatch.setattr(LogUploader, "_post_json", fake_post_json)
    monkeypatch.setattr(LogUploader, "_put_bytes", fake_put_bytes)
    monkeypatch.setattr(log_uploader.socket, "gethostname", lambda: "DESKTOP-TEST")
    monkeypatch.setattr(log_uploader.getpass, "getuser", lambda: "morgan")
    monkeypatch.setattr(log_uploader.platform, "platform", lambda: "Windows-11")

    uploader = LogUploader(
        log_dir=tmp_path,
        endpoint="https://stormfuse.example",
        enabled=True,
        encoder=EncoderChoice.LIBX264,
    )

    success, message = uploader.upload("Clicked Combine and ffmpeg failed.")

    assert success
    assert "test-uuid" in message

    # Init call checks
    assert len(post_calls) == 2
    init_url, init_payload = post_calls[0]
    assert init_url == "https://stormfuse.example/logs/upload"
    assert init_payload["app_version"] == APP_VERSION
    assert init_payload["user_notes"] == "Clicked Combine and ffmpeg failed."
    assert init_payload["hostname"] == "DESKTOP-TEST"
    assert init_payload["username"] == "morgan"
    assert init_payload["os_version"] == "Windows-11"
    assert init_payload["os_platform"] == log_uploader.sys.platform
    assert init_payload["encoder"] == "libx264"
    # ffmpeg-*.log files must be excluded from the filenames list
    assert "ffmpeg-job-123.log" not in init_payload["filenames"]
    assert set(init_payload["filenames"]) == {"latest.log", "stormfuse-20260424-111111-1.log"}

    # Complete call checks
    complete_url, complete_payload = post_calls[1]
    assert complete_url == "https://stormfuse.example/logs/complete"
    assert complete_payload["upload_id"] == "test-uuid"

    # Two files were PUT (gzip-compressed)
    assert len(put_calls) == 2
    for _url, data, content_type in put_calls:
        assert content_type == "application/gzip"
        # Must be valid gzip
        gzip.decompress(data)


def test_upload_excludes_ffmpeg_report_files(tmp_path, monkeypatch) -> None:
    ffmpeg_report = tmp_path / "ffmpeg-job-abc.log"
    ffmpeg_report.write_text("verbose trace\n", encoding="utf-8")

    captured_filenames: list[str] = []

    def fake_post_json(self, url, payload):
        if url.endswith("/logs/upload"):
            captured_filenames.extend(payload.get("filenames", []))
            return _make_init_response([])
        return _make_complete_response()

    monkeypatch.setattr(LogUploader, "_post_json", fake_post_json)
    monkeypatch.setattr(LogUploader, "_put_bytes", lambda *_a, **_kw: None)
    monkeypatch.setattr(log_uploader.socket, "gethostname", lambda: "H")
    monkeypatch.setattr(log_uploader.getpass, "getuser", lambda: "u")
    monkeypatch.setattr(log_uploader.platform, "platform", lambda: "W")

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)
    uploader.upload("notes")

    assert "ffmpeg-job-abc.log" not in captured_filenames


def test_upload_gzip_compresses_file_content(tmp_path, monkeypatch) -> None:
    log_file = tmp_path / "latest.log"
    content = b"line1\nline2\nline3\n"
    log_file.write_bytes(content)

    put_calls: list[tuple[str, bytes, str]] = []

    def fake_post_json(self, url, payload):
        if url.endswith("/logs/upload"):
            return _make_init_response(payload.get("filenames", []))
        return _make_complete_response()

    monkeypatch.setattr(LogUploader, "_post_json", fake_post_json)
    monkeypatch.setattr(
        LogUploader, "_put_bytes", lambda self, url, data, ct: put_calls.append((url, data, ct))
    )
    monkeypatch.setattr(log_uploader.socket, "gethostname", lambda: "H")
    monkeypatch.setattr(log_uploader.getpass, "getuser", lambda: "u")
    monkeypatch.setattr(log_uploader.platform, "platform", lambda: "W")

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)
    uploader.upload("notes")

    assert len(put_calls) == 1
    _url, data, _ct = put_calls[0]
    assert gzip.decompress(data) == content


def test_upload_upgrade_required_returns_clear_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_json",
        lambda self, url, payload: _UploadResponse(
            status_code=426,
            body='{"min_supported_version": "1.0.6"}',
        ),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "too old" in message.lower()
    assert "1.0.6" in message


def test_upload_init_http_error_returns_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_json",
        lambda self, url, payload: _UploadResponse(status_code=500, body="server error"),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "500" in message


def test_upload_timeout_returns_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_json",
        lambda self, url, payload: (_ for _ in ()).throw(TimeoutError("timeout")),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "timed out" in message.lower()


def test_upload_connection_error_returns_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        LogUploader,
        "_post_json",
        lambda self, url, payload: (_ for _ in ()).throw(ConnectionError("no route")),
    )

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "connect" in message.lower()


def test_upload_complete_failure_returns_message(tmp_path, monkeypatch) -> None:
    log_file = tmp_path / "latest.log"
    log_file.write_text("log\n", encoding="utf-8")

    def fake_post_json(self, url, payload):
        if url.endswith("/logs/upload"):
            return _make_init_response(payload.get("filenames", []))
        return _UploadResponse(status_code=500, body="error")

    monkeypatch.setattr(LogUploader, "_post_json", fake_post_json)
    monkeypatch.setattr(LogUploader, "_put_bytes", lambda *_a, **_kw: None)
    monkeypatch.setattr(log_uploader.socket, "gethostname", lambda: "H")
    monkeypatch.setattr(log_uploader.getpass, "getuser", lambda: "u")
    monkeypatch.setattr(log_uploader.platform, "platform", lambda: "W")

    uploader = LogUploader(log_dir=tmp_path, enabled=True, encoder=EncoderChoice.NVENC)

    success, message = uploader.upload("notes")

    assert not success
    assert "500" in message
