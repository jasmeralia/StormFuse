# SPDX-License-Identifier: GPL-3.0-or-later
"""Client-side diagnostic log upload support."""

from __future__ import annotations

import base64
import getpass
import json
import logging
import platform
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stormfuse.config import APP_VERSION, LOG_DIR, LOG_UPLOAD_ENABLED, LOG_UPLOAD_ENDPOINT
from stormfuse.ffmpeg.encoders import EncoderChoice, detect_encoder
from stormfuse.ffmpeg.locator import FfmpegNotFoundError, ffmpeg_path

log = logging.getLogger("stormfuse.core.log_uploader")


@dataclass(frozen=True)
class _UploadResponse:
    status_code: int
    body: str


class LogUploader:
    """Upload the current diagnostic log bundle to the configured endpoint."""

    def __init__(
        self,
        *,
        log_dir: Path = LOG_DIR,
        endpoint: str = LOG_UPLOAD_ENDPOINT,
        enabled: bool = LOG_UPLOAD_ENABLED,
        encoder: EncoderChoice | None = None,
    ) -> None:
        self._log_dir = log_dir
        self._endpoint = endpoint
        self._enabled = enabled
        self._encoder = encoder

    def upload(self, user_notes: str) -> tuple[bool, str]:
        """Upload the current log bundle. Never raises."""
        if not self._enabled:
            log.info(
                "Log upload is disabled",
                extra={"event": "logs.upload.disabled", "ctx": {"endpoint": self._endpoint}},
            )
            return False, "Log submission is not enabled in this build."

        try:
            log_files = self._collect_log_files()
            payload: dict[str, object] = {
                "app_version": APP_VERSION,
                "user_notes": user_notes.strip(),
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "os_version": platform.platform(),
                "os_platform": sys.platform,
                "encoder": self._encoder_name(),
                "log_files": log_files,
            }
            log.info(
                "Uploading diagnostic logs",
                extra={
                    "event": "logs.upload.start",
                    "ctx": {
                        "endpoint": self._endpoint,
                        "file_count": len(log_files),
                    },
                },
            )

            response = self._post_payload(payload)
            return self._handle_response(response)
        except TimeoutError:
            log.warning(
                "Log upload timed out",
                extra={"event": "logs.upload.fail", "ctx": {"reason": "timeout"}},
            )
            return False, "Upload timed out."
        except ConnectionError:
            log.warning(
                "Log upload connection error",
                extra={"event": "logs.upload.fail", "ctx": {"reason": "connection_error"}},
            )
            return False, "Could not connect to the log server."
        except Exception as exc:  # pragma: no cover - defensive last resort
            log.exception(
                "Unexpected log upload failure",
                extra={
                    "event": "logs.upload.fail",
                    "ctx": {"reason": "unexpected", "error": type(exc).__name__},
                },
            )
            return False, "Upload failed due to an unexpected error."

    def _collect_log_files(self) -> list[dict[str, str]]:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_files: list[dict[str, str]] = []
        for path in sorted(self._log_dir.iterdir()):
            if not path.is_file():
                continue
            try:
                content = path.read_bytes()
            except OSError as exc:
                log.warning(
                    "Skipping unreadable log file",
                    extra={
                        "event": "logs.upload.skip",
                        "ctx": {"path": str(path), "error": str(exc)},
                    },
                )
                continue
            log_files.append(
                {
                    "filename": path.name,
                    "content": base64.b64encode(content).decode("ascii"),
                }
            )
        return log_files

    def _encoder_name(self) -> str:
        encoder = self._encoder
        if encoder is None:
            encoder = self._detect_encoder()
        if encoder == EncoderChoice.NVENC:
            return "NVENC"
        return "libx264"

    def _handle_response(self, response: _UploadResponse) -> tuple[bool, str]:
        if response.status_code == 200:
            upload_id = self._upload_id(response)
            log.info(
                "Diagnostic logs uploaded",
                extra={"event": "logs.upload.success", "ctx": {"upload_id": upload_id}},
            )
            return True, f"Logs sent (ID: {upload_id})"
        if response.status_code == 426:
            min_supported_version = self._min_supported_version(response)
            log.warning(
                "Log upload rejected for outdated client",
                extra={
                    "event": "logs.upload.fail",
                    "ctx": {
                        "status_code": 426,
                        "reason": "outdated_client",
                        "min_supported_version": min_supported_version,
                    },
                },
            )
            return (
                False,
                "This StormFuse build is too old for log submission. "
                f"Please upgrade to v{min_supported_version} or newer, retry the problem, "
                "then send logs again.",
            )
        log.warning(
            "Log upload failed",
            extra={
                "event": "logs.upload.fail",
                "ctx": {"status_code": response.status_code, "reason": "http_error"},
            },
        )
        return False, f"Upload failed (HTTP {response.status_code})."

    @staticmethod
    def _upload_id(response: _UploadResponse) -> str:
        payload = LogUploader._response_json(response)
        upload_id = payload.get("upload_id")
        return str(upload_id) if upload_id else "unknown"

    @staticmethod
    def _min_supported_version(response: _UploadResponse) -> str:
        payload = LogUploader._response_json(response)
        min_supported_version = payload.get("min_supported_version")
        return str(min_supported_version) if min_supported_version else "unknown"

    @staticmethod
    def _response_json(response: _UploadResponse) -> dict[str, object]:
        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _post_payload(self, payload: dict[str, object]) -> _UploadResponse:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self._endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return _UploadResponse(status_code=response.status, body=response_body)
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            return _UploadResponse(status_code=exc.code, body=response_body)
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError from exc
            raise ConnectionError from exc

    @staticmethod
    def _detect_encoder() -> EncoderChoice:
        try:
            return detect_encoder(ffmpeg_path())
        except (FfmpegNotFoundError, OSError):
            return EncoderChoice.LIBX264
