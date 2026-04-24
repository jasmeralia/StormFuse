# SPDX-License-Identifier: GPL-3.0-or-later
"""Compress tab UI (§6.3)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse.ffmpeg.bitrate import compute_bitrate
from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ffmpeg.locator import ffprobe_path
from stormfuse.ffmpeg.probe import FileProbe, probe
from stormfuse.jobs.base import JobError, JobResult
from stormfuse.jobs.probe import ProbeFilesJob
from stormfuse.ui.error_dialogs import build_job_failure_guidance, show_diagnostic_dialog
from stormfuse.ui.widgets.size_slider import SizeSlider


class CompressTab(QWidget):
    """The "Compress" tab."""

    run_requested = pyqtSignal(Path, Path, float, object, bool)  # in, out, gb, enc, 2pass
    cancel_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        probe_file: Callable[[Path], FileProbe] | None = None,
    ) -> None:
        super().__init__(parent)
        self._encoder: EncoderChoice = EncoderChoice.LIBX264
        self._duration_sec: float = 0.0
        self._probe_file = probe_file or self._default_probe_file
        self._probe_request_id = 0
        self._probe_jobs: list[ProbeFilesJob] = []
        self._probe_threads: list[QThread] = []

        # --- Input ---
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Select a video file…")
        self._input_field.setReadOnly(True)
        input_browse = QPushButton("Browse…")
        input_browse.clicked.connect(self._browse_input)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Input:"))
        input_row.addWidget(self._input_field, stretch=1)
        input_row.addWidget(input_browse)

        # --- Size slider ---
        self._slider = SizeSlider()
        self._slider.setToolTip(
            "ffmpeg bitrate targeting is imprecise.\n"
            "9.5 GB leaves ~5% headroom under the MFC Share 10 GB per-file limit."
        )
        self._slider.value_changed.connect(self._on_slider_changed)

        # --- 2-pass ---
        self._two_pass_cb = QCheckBox("2-pass encode (slower, tighter size)")
        self._two_pass_cb.setChecked(False)

        # --- Encoder badge ---
        self._encoder_label = QLabel("Encoder: libx264")
        self._encoder_label.setObjectName("encoderBadge")

        # --- Output ---
        out_group = QGroupBox("Output")
        self._out_filename = QLineEdit()
        self._out_filename.setPlaceholderText("compressed.mp4")
        self._out_folder = QLineEdit()
        self._out_folder.setPlaceholderText("Choose an output folder…")
        out_browse = QPushButton("Browse…")
        out_browse.clicked.connect(self._browse_output_folder)

        out_name_row = QHBoxLayout()
        out_name_row.addWidget(QLabel("Filename:"))
        out_name_row.addWidget(self._out_filename, stretch=1)

        out_folder_row = QHBoxLayout()
        out_folder_row.addWidget(QLabel("Folder:"))
        out_folder_row.addWidget(self._out_folder, stretch=1)
        out_folder_row.addWidget(out_browse)

        out_layout = QVBoxLayout()
        out_layout.addLayout(out_name_row)
        out_layout.addLayout(out_folder_row)
        out_group.setLayout(out_layout)

        # --- Progress / run ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._phase_label = QLabel("")

        self._run_btn = QPushButton("Run")
        self._run_btn.setEnabled(False)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)

        self._run_btn.clicked.connect(self._on_run)
        self._cancel_btn.clicked.connect(self.cancel_requested)

        run_row = QHBoxLayout()
        run_row.addWidget(self._progress, stretch=1)
        run_row.addWidget(self._phase_label)
        run_row.addWidget(self._run_btn)
        run_row.addWidget(self._cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(input_row)
        layout.addWidget(self._slider)
        layout.addWidget(self._two_pass_cb)
        layout.addWidget(self._encoder_label)
        layout.addWidget(out_group)
        layout.addLayout(run_row)
        layout.addStretch()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def set_encoder(self, choice: EncoderChoice) -> None:
        self._encoder = choice
        name = "NVENC (h264_nvenc)" if choice == EncoderChoice.NVENC else "libx264"
        self._encoder_label.setText(f"Encoder: {name}")

    def set_running(self, running: bool) -> None:
        if running:
            self._run_btn.setEnabled(False)
        else:
            self._refresh_run_button_state()
        self._cancel_btn.setEnabled(running)
        self._input_field.setEnabled(not running)

    @pyqtSlot(float, str)
    def on_progress(self, pct: float, phase: str) -> None:
        self._progress.setValue(int(pct * 1000))
        self._phase_label.setText(phase)

    @pyqtSlot(object)
    def on_job_done(self, result: JobResult) -> None:
        self._progress.setValue(1000)
        self._phase_label.setText("Done!")
        self.set_running(False)

    @pyqtSlot(object)
    def on_job_failed(self, error: JobError) -> None:
        self._phase_label.setText("Failed")
        self.set_running(False)
        guidance = build_job_failure_guidance("compress", error.event, error.message)
        show_diagnostic_dialog(
            self,
            title="Compress failed",
            message=error.message,
            event=error.event,
            stderr_tail=error.stderr_tail,
            encoder=self._encoder,
            guidance=guidance,
        )

    @pyqtSlot()
    def on_job_cancelled(self) -> None:
        self._progress.setValue(0)
        self._phase_label.setText("Cancelled")
        self.set_running(False)

    def set_duration(self, duration_sec: float) -> None:
        self._duration_sec = duration_sec
        self._update_bitrate_preview()
        self._refresh_run_button_state()

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _browse_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select video", "", "Video files (*.mkv *.mp4);;All files (*)"
        )
        if path:
            self._set_input_path(Path(path))

    def _browse_output_folder(self) -> None:
        default_dir = self._out_folder.text().strip()
        if not default_dir and self._input_field.text().strip():
            default_dir = str(Path(self._input_field.text().strip()).parent)

        folder = QFileDialog.getExistingDirectory(self, "Output folder", default_dir)
        if folder:
            self._out_folder.setText(folder)

    def _on_slider_changed(self, gb: float) -> None:
        del gb
        self._update_bitrate_preview()
        self._refresh_run_button_state()

    def _update_bitrate_preview(self) -> None:
        if self._duration_sec > 0:
            br = compute_bitrate(self._slider.gb_value(), self._duration_sec)
            self._slider.set_bitrate_preview(br.video_bitrate_k if br.feasible else 0)
        else:
            self._slider.set_bitrate_preview(0)

    def _can_run(self) -> bool:
        if not self._input_field.text() or self._duration_sec <= 0:
            return False
        br = compute_bitrate(self._slider.gb_value(), self._duration_sec)
        return br.feasible

    def _refresh_run_button_state(self) -> None:
        if not self._input_field.text():
            self._run_btn.setEnabled(False)
            self._run_btn.setToolTip("")
            return
        if self._duration_sec <= 0:
            self._run_btn.setEnabled(False)
            return

        br = compute_bitrate(self._slider.gb_value(), self._duration_sec)
        self._run_btn.setEnabled(br.feasible)
        if br.feasible:
            self._run_btn.setToolTip("")
            return
        self._run_btn.setToolTip(
            f"{br.reason}.\nIncrease the target size or choose a shorter input."
        )

    def _on_run(self) -> None:
        in_text = self._input_field.text().strip()
        output_path = self._selected_output_path()
        if not in_text or output_path is None:
            return
        self.run_requested.emit(
            Path(in_text),
            output_path,
            self._slider.gb_value(),
            self._encoder,
            self._two_pass_cb.isChecked(),
        )

    def _default_probe_file(self, path: Path) -> FileProbe:
        return probe(ffprobe_path(), path)

    def _set_input_path(self, path: Path) -> None:
        self._input_field.setText(str(path))
        if not self._out_filename.text():
            self._out_filename.setText(f"{path.stem}-compressed.mp4")
        if not self._out_folder.text():
            self._out_folder.setText(str(path.parent))
        self._start_probe(path)

    def _selected_output_path(self) -> Path | None:
        filename = self._out_filename.text().strip()
        if not filename:
            QMessageBox.warning(self, "No output", "Please specify an output filename.")
            return None
        if "/" in filename or "\\" in filename:
            QMessageBox.warning(
                self,
                "Invalid filename",
                "Please enter only an output filename. Choose the folder separately.",
            )
            return None
        folder = self._out_folder.text().strip()
        if not folder:
            QMessageBox.warning(self, "No output", "Please specify an output folder.")
            return None
        return Path(folder) / filename

    def _start_probe(self, path: Path) -> None:
        self._cancel_pending_probe_jobs()
        self.set_duration(0.0)
        self._run_btn.setToolTip("Inspecting input media…")
        self._probe_request_id += 1
        request_id = self._probe_request_id

        thread = QThread(self)
        job = ProbeFilesJob([path], self._probe_file)
        job.moveToThread(thread)

        self._probe_threads.append(thread)
        self._probe_jobs.append(job)

        thread.started.connect(job.run)
        job.finished.connect(thread.quit)
        job.probed.connect(
            lambda probes, request_id=request_id: self._on_probe_results(request_id, probes)
        )
        job.failed.connect(
            lambda error, request_id=request_id: self._on_probe_failed(request_id, error)
        )
        thread.finished.connect(lambda thread=thread, job=job: self._cleanup_probe_job(thread, job))
        thread.start()

    def _cancel_pending_probe_jobs(self) -> None:
        for job in list(self._probe_jobs):
            job.cancel()

    def _cleanup_probe_job(self, thread: QThread, job: ProbeFilesJob) -> None:
        if job in self._probe_jobs:
            self._probe_jobs.remove(job)
        if thread in self._probe_threads:
            self._probe_threads.remove(thread)
        job.deleteLater()
        thread.deleteLater()

    def _on_probe_results(self, request_id: int, probes: list[FileProbe]) -> None:
        if request_id != self._probe_request_id or not probes:
            return
        self.set_duration(probes[0].duration_sec)

    def _on_probe_failed(self, request_id: int, error: JobError) -> None:
        if request_id != self._probe_request_id:
            return
        self.set_duration(0.0)
        self._run_btn.setToolTip(error.message)
