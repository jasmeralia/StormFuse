# SPDX-License-Identifier: GPL-3.0-or-later
"""CombineJob: probe → decide strategy → run ffmpeg (§5.1, §8)."""

from __future__ import annotations

import contextlib
import logging
import shutil
import tempfile
from pathlib import Path

from stormfuse.ffmpeg.concat import ConcatPlan, ConcatStrategy, make_concat_plan
from stormfuse.ffmpeg.encoders import EncoderChoice, audio_args, normalize_video_args
from stormfuse.ffmpeg.probe import FileProbe, ProbeError, probe
from stormfuse.ffmpeg.runner import ProgressCallback, ProgressEvent, RunResult, run_ffmpeg
from stormfuse.jobs.base import Job

log = logging.getLogger("jobs.combine")


class CombineJob(Job):
    """Combine an ordered list of video files into a single output MKV."""

    def __init__(
        self,
        ffmpeg_exe: Path,
        ffprobe_exe: Path,
        inputs: list[Path],
        output: Path,
        encoder: EncoderChoice,
    ) -> None:
        super().__init__()
        self.ffmpeg_exe = ffmpeg_exe
        self.ffprobe_exe = ffprobe_exe
        self.inputs = inputs
        self.output = output
        self.encoder = encoder

    def _run_job(self) -> None:
        probes: list[FileProbe] = []
        for inp in self.inputs:
            self.progress.emit(0.0, f"Probing {inp.name}…")
            try:
                fp = probe(self.ffprobe_exe, inp, job_id=self.job_id)
            except ProbeError as exc:
                self.fail(
                    event="probe.error",
                    message=f"Probe failed for {inp.name}: {exc}",
                    stderr_tail=exc.stderr_tail,
                )
            probes.append(fp)

            if self.is_cancelled:
                return

        plan = make_concat_plan(probes)
        log.info(
            "Concat strategy decided",
            extra={"event": "concat.decision", "job_id": self.job_id, "ctx": plan.to_log_ctx()},
        )

        if plan.strategy == ConcatStrategy.STREAM_COPY:
            self._run_stream_copy(probes)
        else:
            self._run_normalize_then_concat(plan)

    def _total_duration(self, probes: list[FileProbe]) -> float:
        return sum(p.duration_sec for p in probes)

    def _run_stream_copy(self, probes: list[FileProbe]) -> None:
        total_dur = self._total_duration(probes)

        list_file = self._write_concat_list([p.path for p in probes])
        try:
            args = [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "--",
                str(self.output),
            ]

            def on_progress(ev: ProgressEvent) -> None:
                pct = (ev.out_time_sec / total_dur) if total_dur > 0 else 0.0
                self.progress.emit(pct, "Stream-copy concat…")

            result = run_ffmpeg(
                self.ffmpeg_exe,
                args,
                on_progress=on_progress,
                cancel_event=self._cancel_event,
                job_id=self.job_id,
            )
            self._check_result(result, "concat")
        finally:
            list_file.unlink(missing_ok=True)

    def _run_normalize_then_concat(self, plan: ConcatPlan) -> None:
        assert plan.target_sig is not None
        target = plan.target_sig
        total_dur = self._total_duration(plan.inputs)
        normalize_index_set = set(plan.normalize_indices)
        total_progress_dur = (
            sum(plan.inputs[index].duration_sec for index in plan.normalize_indices) + total_dur
        )

        tmp_dir = Path(tempfile.mkdtemp(prefix="stormfuse_norm_"))
        log.info(
            "Normalize intermediates dir created",
            extra={
                "event": "concat.norm_dir",
                "job_id": self.job_id,
                "ctx": {"tmp_dir": str(tmp_dir)},
            },
        )

        concat_inputs: list[Path] = []
        norm_failed = False
        cleanup_tmp_dir = False

        try:
            progress_start = 0.0
            for i, fp in enumerate(plan.inputs):
                if self.is_cancelled:
                    return

                if i not in normalize_index_set:
                    concat_inputs.append(fp.path)
                    continue

                dst = tmp_dir / f"{i:02d}_{fp.path.stem}.mkv"
                phase_weight = (
                    fp.duration_sec / total_progress_dur if total_progress_dur > 0 else 0.0
                )

                vf = (
                    f"scale={target.width}:{target.height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={target.width}:{target.height}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps={target.fps},format=yuv420p"
                )

                args = [
                    "-i",
                    str(fp.path),
                    "-vf",
                    vf,
                    *normalize_video_args(self.encoder),
                    *audio_args(),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "--",
                    str(dst),
                ]

                norm_cb = self._make_norm_progress(
                    progress_start, phase_weight, fp.duration_sec, fp.path.name
                )
                result = run_ffmpeg(
                    self.ffmpeg_exe,
                    args,
                    on_progress=norm_cb,
                    cancel_event=self._cancel_event,
                    job_id=self.job_id,
                )
                if not result.succeeded:
                    norm_failed = True
                    self.fail(
                        event="ffmpeg.exit",
                        message=f"Normalization failed for {fp.path.name}",
                        stderr_tail=result.stderr_tail,
                    )

                concat_inputs.append(dst)
                progress_start += phase_weight

            if self.is_cancelled:
                return

            list_file = self._write_concat_list(concat_inputs)
            try:
                args = [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_file),
                    "-c",
                    "copy",
                    "--",
                    str(self.output),
                ]

                def on_concat_progress(ev: ProgressEvent) -> None:
                    pct = (ev.out_time_sec / total_dur) if total_dur > 0 else 0.0
                    concat_weight = (
                        total_dur / total_progress_dur if total_progress_dur > 0 else 0.0
                    )
                    self.progress.emit(progress_start + pct * concat_weight, "Concatenating…")

                result = run_ffmpeg(
                    self.ffmpeg_exe,
                    args,
                    on_progress=on_concat_progress,
                    cancel_event=self._cancel_event,
                    job_id=self.job_id,
                )
                self._check_result(result, "concat")
            finally:
                list_file.unlink(missing_ok=True)

            cleanup_tmp_dir = True

        except Exception:
            if not norm_failed and not self.is_cancelled:
                log.error(
                    "Normalize-then-concat failed; intermediates retained",
                    extra={
                        "event": "concat.norm_failed",
                        "job_id": self.job_id,
                        "ctx": {"tmp_dir": str(tmp_dir)},
                    },
                    exc_info=True,
                )
            raise
        finally:
            if cleanup_tmp_dir or self.is_cancelled:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info(
                    "Normalized intermediates deleted",
                    extra={"event": "concat.norm_cleanup", "job_id": self.job_id},
                )

    def _make_norm_progress(
        self,
        phase_start: float,
        phase_weight: float,
        duration_sec: float,
        filename: str,
    ) -> ProgressCallback:
        def on_progress(ev: ProgressEvent) -> None:
            local_pct = (ev.out_time_sec / duration_sec) if duration_sec > 0 else 0.0
            overall = phase_start + local_pct * phase_weight
            self.progress.emit(overall, f"Normalizing {filename}…")

        return on_progress

    def _write_concat_list(self, paths: list[Path]) -> Path:
        tmp = Path(tempfile.mktemp(prefix="stormfuse_concat_", suffix=".txt"))
        with tmp.open("w", encoding="utf-8") as f:
            for p in paths:
                escaped = str(p).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        return tmp

    def _check_result(self, result: RunResult, phase: str) -> None:
        if not result.succeeded and not self.is_cancelled:
            self.fail(
                event="ffmpeg.exit",
                message=f"ffmpeg {phase} failed (exit {result.exit_code})",
                stderr_tail=result.stderr_tail,
            )

        if self.is_cancelled and self.output.exists():
            with contextlib.suppress(OSError):
                self.output.unlink()
