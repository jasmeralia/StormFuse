# SPDX-License-Identifier: GPL-3.0-or-later
"""Client-side diagnostic log upload support."""

from __future__ import annotations

import getpass
import gzip
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
        self._endpoint = endpoint.rstrip("/")
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
            return self._run_upload(user_notes.strip())
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

    def _run_upload(self, user_notes: str) -> tuple[bool, str]:
        file_paths = self._collect_log_file_paths()
        filenames = [p.name for p in file_paths]

        # Step 1: Init — get upload_id and presigned S3 PUT URLs.
        log.info(
            "Initiating log upload",
            extra={
                "event": "logs.upload.start",
                "ctx": {
                    "endpoint": self._endpoint,
                    "file_count": len(file_paths),
                },
            },
        )
        init_resp = self._post_json(
            f"{self._endpoint}/logs/upload",
            {
                "app_version": APP_VERSION,
                "user_notes": user_notes,
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "os_version": platform.platform(),
                "os_platform": sys.platform,
                "encoder": self._encoder_name(),
                "filenames": filenames,
            },
        )

        if init_resp.status_code == 426:
            min_ver = self._parse_field(init_resp, "min_supported_version")
            log.warning(
                "Log upload rejected for outdated client",
                extra={
                    "event": "logs.upload.fail",
                    "ctx": {
                        "status_code": 426,
                        "reason": "outdated_client",
                        "min_supported_version": min_ver,
                    },
                },
            )
            return (
                False,
                "This StormFuse build is too old for log submission. "
                f"Please upgrade to v{min_ver} or newer, retry the problem, "
                "then send logs again.",
            )

        if init_resp.status_code != 200:
            log.warning(
                "Log upload init failed",
                extra={
                    "event": "logs.upload.fail",
                    "ctx": {"status_code": init_resp.status_code, "reason": "http_error"},
                },
            )
            return False, f"Upload failed (HTTP {init_resp.status_code})."

        init_data = self._response_json(init_resp)
        upload_id = str(init_data.get("upload_id", ""))
        raw_urls = init_data.get("presigned_urls", [])
        presigned_urls: dict[str, str] = {
            item["filename"]: item["url"]
            for item in (raw_urls if isinstance(raw_urls, list) else [])
            if isinstance(item, dict) and "filename" in item and "url" in item
        }

        # Step 2: Gzip-compress and PUT each file directly to S3.
        for path in file_paths:
            url = presigned_urls.get(path.name)
            if not url:
                continue
            try:
                compressed = gzip.compress(path.read_bytes(), compresslevel=6)
                self._put_bytes(url, compressed, "application/gzip")
                log.debug(
                    "Uploaded log file",
                    extra={
                        "event": "logs.upload.file",
                        "ctx": {"filename": path.name, "upload_id": upload_id},
                    },
                )
            except OSError as exc:
                log.warning(
                    "Could not read log file for upload",
                    extra={
                        "event": "logs.upload.skip",
                        "ctx": {"path": str(path), "error": str(exc)},
                    },
                )
            except Exception as exc:
                log.warning(
                    "Failed to upload log file",
                    extra={
                        "event": "logs.upload.skip",
                        "ctx": {"filename": path.name, "upload_id": upload_id, "error": str(exc)},
                    },
                )

        # Step 3: Signal completion so the Lambda sends the notification email.
        complete_resp = self._post_json(
            f"{self._endpoint}/logs/complete",
            {
                "upload_id": upload_id,
                "app_version": APP_VERSION,
                "user_notes": user_notes,
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "os_version": platform.platform(),
                "os_platform": sys.platform,
                "encoder": self._encoder_name(),
            },
        )

        if complete_resp.status_code != 200:
            log.warning(
                "Log upload completion failed",
                extra={
                    "event": "logs.upload.fail",
                    "ctx": {
                        "status_code": complete_resp.status_code,
                        "reason": "complete_failed",
                        "upload_id": upload_id,
                    },
                },
            )
            return False, f"Upload completion failed (HTTP {complete_resp.status_code})."

        log.info(
            "Diagnostic logs uploaded",
            extra={"event": "logs.upload.success", "ctx": {"upload_id": upload_id}},
        )
        return True, f"Logs sent (ID: {upload_id})"

    def _collect_log_file_paths(self) -> list[Path]:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        return [p for p in sorted(self._log_dir.iterdir()) if p.is_file()]

    def _encoder_name(self) -> str:
        encoder = self._encoder
        if encoder is None:
            encoder = self._detect_encoder()
        return "NVENC" if encoder == EncoderChoice.NVENC else "libx264"

    def _post_json(self, url: str, payload: dict[str, object]) -> _UploadResponse:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return _UploadResponse(
                    status_code=response.status,
                    body=response.read().decode("utf-8", errors="replace"),
                )
        except HTTPError as exc:
            return _UploadResponse(
                status_code=exc.code,
                body=exc.read().decode("utf-8", errors="replace"),
            )
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError from exc
            raise ConnectionError from exc

    def _put_bytes(self, url: str, data: bytes, content_type: str) -> None:
        request = Request(
            url,
            data=data,
            headers={"Content-Type": content_type},
            method="PUT",
        )
        try:
            with urlopen(request, timeout=120) as _:
                pass
        except HTTPError as exc:
            raise ConnectionError(f"S3 PUT failed: HTTP {exc.code}") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError from exc
            raise ConnectionError from exc

    @staticmethod
    def _response_json(response: _UploadResponse) -> dict[str, object]:
        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _parse_field(response: _UploadResponse, field: str) -> str:
        value = LogUploader._response_json(response).get(field)
        return str(value) if value else "unknown"

    @staticmethod
    def _detect_encoder() -> EncoderChoice:
        try:
            return detect_encoder(ffmpeg_path())
        except (FfmpegNotFoundError, OSError):
            return EncoderChoice.LIBX264
