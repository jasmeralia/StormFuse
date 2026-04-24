# SPDX-License-Identifier: GPL-3.0-or-later
"""CompressJob: re-encode a single video to hit a size ceiling (§5.2, §8)."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from stormfuse.ffmpeg.bitrate import compute_bitrate
from stormfuse.ffmpeg.encoders import EncoderChoice, audio_args, compressed_video_args
from stormfuse.ffmpeg.probe import FileProbe, ProbeError, probe
from stormfuse.ffmpeg.runner import ProgressEvent, RunResult, run_ffmpeg
from stormfuse.jobs.base import Job

log = logging.getLogger("jobs.compress")


class CompressJob(Job):
    """Re-encode *input* to *output* targeting *target_gb* file size."""

    def __init__(
        self,
        ffmpeg_exe: Path,
        ffprobe_exe: Path,
        input_path: Path,
        output_path: Path,
        target_gb: float,
        encoder: EncoderChoice,
        two_pass: bool = False,
    ) -> None:
        super().__init__()
        self.ffmpeg_exe = ffmpeg_exe
        self.ffprobe_exe = ffprobe_exe
        self.input_path = input_path
        self.output_path = output_path
        self.target_gb = target_gb
        self.encoder = encoder
        self.two_pass = two_pass

    def _run_job(self) -> None:
        # Probe input
        self.progress.emit(0.0, f"Probing {self.input_path.name}…")
        try:
            fp: FileProbe = probe(self.ffprobe_exe, self.input_path, job_id=self.job_id)
        except ProbeError as exc:
            self.fail(
                event="probe.error",
                message=f"Probe failed: {exc}",
                stderr_tail=exc.stderr_tail,
            )

        br = compute_bitrate(self.target_gb, fp.duration_sec)
        if not br.feasible:
            self.fail(event="job.fail", message=f"Cannot compress: {br.reason}")

        log.info(
            "Starting compress encode",
            extra={
                "event": "job.compress.start",
                "job_id": self.job_id,
                "ctx": {
                    "input": str(self.input_path),
                    "output": str(self.output_path),
                    "target_gb": self.target_gb,
                    "video_bitrate_k": br.video_bitrate_k,
                    "two_pass": self.two_pass,
                    "encoder": self.encoder.name,
                },
            },
        )

        if self.two_pass and self.encoder == EncoderChoice.LIBX264:
            self._run_two_pass_x264(fp, br.video_bitrate_k)
        else:
            self._run_single_pass(fp, br.video_bitrate_k)

    def _run_single_pass(self, fp: FileProbe, bitrate_k: int) -> None:
        args = [
            "-i",
            str(self.input_path),
            *compressed_video_args(self.encoder, bitrate_k, two_pass=self.two_pass),
            *audio_args(),
            "-movflags",
            "+faststart",
            "--",
            str(self.output_path),
        ]

        def on_progress(ev: ProgressEvent) -> None:
            pct = (ev.out_time_sec / fp.duration_sec) if fp.duration_sec > 0 else 0.0
            self.progress.emit(pct, "Encoding…")

        result = run_ffmpeg(
            self.ffmpeg_exe,
            args,
            on_progress=on_progress,
            cancel_event=self._cancel_event,
            job_id=self.job_id,
        )
        self._handle_result(result, "encode")

    def _run_two_pass_x264(self, fp: FileProbe, bitrate_k: int) -> None:
        passlog = tempfile.mktemp(prefix="stormfuse_2pass_")

        try:
            # Pass 1
            pass1_args = [
                "-i",
                str(self.input_path),
                *compressed_video_args(self.encoder, bitrate_k, two_pass=True, pass_num=1),
                "-passlogfile",
                passlog,
                "NUL" if os.name == "nt" else "/dev/null",
            ]

            def on_pass1(ev: ProgressEvent) -> None:
                pct = (ev.out_time_sec / fp.duration_sec) if fp.duration_sec > 0 else 0.0
                self.progress.emit(pct * 0.5, "Pass 1/2…")

            result = run_ffmpeg(
                self.ffmpeg_exe,
                pass1_args,
                on_progress=on_pass1,
                cancel_event=self._cancel_event,
                job_id=self.job_id,
            )
            if not result.succeeded or self.is_cancelled:
                self._handle_result(result, "pass 1")
                return

            # Pass 2
            pass2_args = [
                "-i",
                str(self.input_path),
                *compressed_video_args(self.encoder, bitrate_k, two_pass=True, pass_num=2),
                "-passlogfile",
                passlog,
                *audio_args(),
                "-movflags",
                "+faststart",
                "--",
                str(self.output_path),
            ]

            def on_pass2(ev: ProgressEvent) -> None:
                pct = (ev.out_time_sec / fp.duration_sec) if fp.duration_sec > 0 else 0.0
                self.progress.emit(0.5 + pct * 0.5, "Pass 2/2…")

            result = run_ffmpeg(
                self.ffmpeg_exe,
                pass2_args,
                on_progress=on_pass2,
                cancel_event=self._cancel_event,
                job_id=self.job_id,
            )
            self._handle_result(result, "pass 2")

        finally:
            # Clean up pass log files
            for ext in ("", ".log", ".log.mbtree"):
                p = Path(passlog + ext)
                p.unlink(missing_ok=True)

    def _handle_result(self, result: RunResult, phase: str) -> None:
        if self.is_cancelled:
            if self.output_path.exists():
                self.output_path.unlink(missing_ok=True)
            return
        if not result.succeeded:
            if self.output_path.exists():
                self.output_path.unlink(missing_ok=True)
            self.fail(
                event="ffmpeg.exit",
                message=f"ffmpeg {phase} failed (exit {result.exit_code})",
                stderr_tail=result.stderr_tail,
            )
