# SPDX-License-Identifier: GPL-3.0-or-later
"""subprocess.Popen wrapper for ffmpeg with progress parsing (§7.7).

No PyQt6 imports. Progress and results are delivered via callbacks so that
the jobs layer can bridge them to Qt signals on its own thread.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from stormfuse.logging_setup import current_job_id

log = logging.getLogger("ffmpeg.runner")

_CREATE_NO_WINDOW = 0x08000000  # Windows only


@dataclass
class ProgressEvent:
    out_time_sec: float = 0.0
    speed: float = 0.0
    bitrate_kbps: float = 0.0
    frame: int = 0


@dataclass
class RunResult:
    argv: list[str]
    exit_code: int
    duration_sec: float
    stderr_tail: str
    succeeded: bool = field(init=False)

    def __post_init__(self) -> None:
        self.succeeded = self.exit_code == 0


ProgressCallback = Callable[[ProgressEvent], None]
LogCallback = Callable[[str], None]


def _parse_progress_block(lines: list[str]) -> ProgressEvent:
    ev = ProgressEvent()
    for line in lines:
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key == "out_time_us":
            with contextlib.suppress(ValueError):
                ev.out_time_sec = int(val) / 1_000_000
        elif key == "speed":
            with contextlib.suppress(ValueError):
                ev.speed = float(val.rstrip("x"))
        elif key == "bitrate":
            with contextlib.suppress(ValueError):
                ev.bitrate_kbps = float(val.split("k")[0])
        elif key == "frame":
            with contextlib.suppress(ValueError):
                ev.frame = int(val)
    return ev


def _progress_reader(
    progress_path: str,
    on_progress: ProgressCallback,
    done_event: threading.Event,
    job_id: str | None,
) -> None:
    last_emit = 0.0
    block: list[str] = []

    while not done_event.is_set():
        try:
            with open(progress_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            time.sleep(0.1)
            continue

        lines = content.splitlines()
        block = []
        for line in lines:
            if line.startswith("progress="):
                if block:
                    now = time.monotonic()
                    if now - last_emit >= 1.0 or line == "progress=end":
                        event = _parse_progress_block(block)
                        on_progress(event)
                        log.debug(
                            "ffmpeg progress",
                            extra=_log_extra(
                                "ffmpeg.progress",
                                {
                                    "out_time_sec": round(event.out_time_sec, 3),
                                    "speed": event.speed,
                                    "bitrate_kbps": event.bitrate_kbps,
                                    "frame": event.frame,
                                },
                                job_id,
                            ),
                        )
                        last_emit = now
                block = []
            else:
                block.append(line)

        time.sleep(0.25)


def run_ffmpeg(
    ffmpeg_exe: Path,
    args: list[str],
    *,
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
    cancel_event: threading.Event | None = None,
    cwd: Path | None = None,
    job_id: str | None = None,
) -> RunResult:
    """Spawn ffmpeg and wait for it to finish.

    Args are passed as a list (never shell=True). A temp file is used for
    -progress output so progress can be read from a separate thread.
    """
    full_argv = [str(ffmpeg_exe), "-hide_banner", "-y"]
    resolved_job_id = job_id or current_job_id()

    progress_path: str | None = None
    if on_progress is not None:
        # Use a temp file instead of a named pipe for ffmpeg progress output.
        # Windows named pipes need \\.\pipe\... setup and extra lifecycle
        # handling; polling a temp file gives equivalent progress reporting
        # with simpler, cross-platform code.
        fd, progress_path = tempfile.mkstemp(prefix="stormfuse_progress_", suffix=".txt")
        os.close(fd)
        full_argv += ["-progress", progress_path, "-nostats"]

    full_argv += args

    log.info(
        "Starting ffmpeg",
        extra=_log_extra(
            "ffmpeg.start",
            {"argv": full_argv, "cwd": str(cwd or "")},
            resolved_job_id,
        ),
    )

    kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE,
        "cwd": str(cwd) if cwd else None,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW

    start_time = time.monotonic()

    try:
        proc = subprocess.Popen(full_argv, **kwargs)  # type: ignore[call-overload]
    except OSError as exc:
        log.error(
            "Failed to spawn ffmpeg",
            extra=_log_extra(
                "ffmpeg.exit",
                {"error": str(exc), "argv": full_argv},
                resolved_job_id,
            ),
            exc_info=True,
        )
        return RunResult(argv=full_argv, exit_code=-1, duration_sec=0.0, stderr_tail=str(exc))

    done_event = threading.Event()
    stderr_lines: list[str] = []

    def read_stderr() -> None:
        assert proc.stderr is not None
        for raw_line in proc.stderr:
            line = raw_line.decode(errors="replace").rstrip()
            stderr_lines.append(line)
            if on_log:
                on_log(line)
            if line:
                log.debug(line, extra=_log_extra("ffmpeg.stderr", {"line": line}, resolved_job_id))

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    progress_thread: threading.Thread | None = None
    if on_progress is not None and progress_path is not None:

        def _safe_progress(ev: ProgressEvent) -> None:
            with contextlib.suppress(Exception):
                on_progress(ev)

        progress_thread = threading.Thread(
            target=_progress_reader,
            args=(
                progress_path,
                _safe_progress,
                done_event,
                resolved_job_id,
            ),
            daemon=True,
        )
        progress_thread.start()

    cancelled = False
    cancel_step = "q"

    while proc.poll() is None:
        if cancel_event and cancel_event.is_set():
            with contextlib.suppress(OSError):
                assert proc.stdin is not None
                proc.stdin.write(b"q\n")
                proc.stdin.flush()
                proc.stdin.close()
            for _ in range(50):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                proc.terminate()
                cancel_step = "terminate"
                for _ in range(30):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
                cancel_step = "kill"
            cancelled = True
            break
        time.sleep(0.1)

    proc.wait()
    done_event.set()
    stderr_thread.join(timeout=2.0)
    if progress_thread:
        progress_thread.join(timeout=1.0)

    if progress_path:
        with contextlib.suppress(OSError):
            os.unlink(progress_path)

    duration = time.monotonic() - start_time
    exit_code = proc.returncode if proc.returncode is not None else -1
    stderr_tail = "\n".join(stderr_lines[-200:])

    level = logging.INFO if exit_code == 0 else logging.ERROR
    event = "ffmpeg.exit"
    ctx: dict[str, object] = {
        "exit_code": exit_code,
        "duration_sec": round(duration, 2),
    }
    if cancelled:
        ctx["cancel_step"] = cancel_step or "q"
        event = "ffmpeg.cancel"
    if exit_code != 0:
        ctx["stderr_tail"] = stderr_lines[-20:]

    log.log(level, "ffmpeg exited", extra=_log_extra(event, ctx, resolved_job_id))

    return RunResult(
        argv=full_argv,
        exit_code=exit_code,
        duration_sec=duration,
        stderr_tail=stderr_tail,
    )


def _log_extra(event: str, ctx: dict[str, object], job_id: str | None) -> dict[str, object]:
    extra: dict[str, object] = {"event": event, "ctx": ctx}
    if job_id is not None:
        extra["job_id"] = job_id
    return extra
