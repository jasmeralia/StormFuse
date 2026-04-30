# SPDX-License-Identifier: GPL-3.0-or-later
"""Combine tab UI (§6.2)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from stormfuse.ffmpeg.concat import ConcatPlan, ConcatStrategy, make_concat_plan
from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ffmpeg.locator import ffprobe_path
from stormfuse.ffmpeg.probe import FileProbe, probe
from stormfuse.jobs.base import JobError, JobResult
from stormfuse.jobs.probe import ProbeFilesJob, ProbeFilesResult
from stormfuse.ui.error_dialogs import build_job_failure_guidance, show_diagnostic_dialog
from stormfuse.ui.settings import KEY_COMBINE_ADD, KEY_COMBINE_OUT, last_dir, remember_dir
from stormfuse.ui.theme import show_warning_message
from stormfuse.ui.widgets.file_list import FileListWidget


class CombineTab(QWidget):
    """The "Combine" tab."""

    run_requested = pyqtSignal(list, Path, EncoderChoice)  # inputs, output, encoder
    cancel_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        probe_file: Callable[[Path], FileProbe] | None = None,
    ) -> None:
        super().__init__(parent)
        self._encoder: EncoderChoice = EncoderChoice.LIBX264
        self._probe_file = probe_file or self._default_probe_file
        self._probe_jobs: list[ProbeFilesJob] = []
        self._probe_threads: list[QThread] = []
        self._probe_paths_by_job_id: dict[str, list[Path]] = {}

        # --- File list ---
        self._file_list = FileListWidget()
        self._file_list.files_changed.connect(self._on_files_changed)
        self._file_list.files_added.connect(self._on_files_added)

        add_btn = QPushButton("Add Files…")
        add_btn.clicked.connect(self._add_files)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._file_list.remove_selected)
        up_btn = QPushButton("Up")
        up_btn.clicked.connect(self._file_list.move_up)
        down_btn = QPushButton("Down")
        down_btn.clicked.connect(self._file_list.move_down)
        sort_name_btn = QPushButton("Sort by name")
        sort_name_btn.clicked.connect(self._file_list.sort_by_name)
        sort_ts_btn = QPushButton("Sort by timestamp")
        sort_ts_btn.clicked.connect(self._file_list.sort_by_timestamp)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._on_clear)

        btn_col = QVBoxLayout()
        for b in (add_btn, remove_btn, up_btn, down_btn, sort_name_btn, sort_ts_btn, clear_btn):
            btn_col.addWidget(b)
        btn_col.addStretch()

        list_row = QHBoxLayout()
        list_row.addWidget(self._file_list, stretch=1)
        list_row.addLayout(btn_col)

        # --- Strategy preview ---
        self._strategy_toggle = QToolButton()
        self._strategy_toggle.setText("Strategy Preview")
        self._strategy_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._strategy_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._strategy_toggle.setCheckable(True)
        self._strategy_toggle.setChecked(False)
        self._strategy_toggle.clicked.connect(self._on_strategy_toggled)

        self._strategy_label = QLabel("Add files to begin.")
        self._strategy_label.setObjectName("strategyLabel")

        self._why_label = QLabel("Why?")
        self._why_label.setObjectName("strategyWhy")
        self._why_label.setVisible(False)
        self._why_label.setStyleSheet(
            "QLabel { color: #1d4ed8; font-weight: 600; text-decoration: underline; }"
        )

        preview_header = QHBoxLayout()
        preview_header.addWidget(self._strategy_toggle)
        preview_header.addWidget(self._strategy_label, stretch=1)
        preview_header.addWidget(self._why_label)

        self._strategy_details = QLabel("")
        self._strategy_details.setObjectName("strategyDetails")
        self._strategy_details.setWordWrap(True)
        self._strategy_details.setVisible(False)
        self._strategy_details.setStyleSheet("QLabel { padding: 0 0 0 28px; }")

        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addLayout(preview_header)
        preview_layout.addWidget(self._strategy_details)

        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)

        # --- Output ---
        out_group = QGroupBox("Output")
        self._out_filename = QLineEdit()
        self._out_filename.setPlaceholderText("combined.mkv")
        self._out_folder = QLineEdit()
        self._out_folder.setPlaceholderText("Choose an output folder…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_output_folder)

        out_name_row = QHBoxLayout()
        out_name_row.addWidget(QLabel("Filename:"))
        out_name_row.addWidget(self._out_filename, stretch=1)

        out_folder_row = QHBoxLayout()
        out_folder_row.addWidget(QLabel("Folder:"))
        out_folder_row.addWidget(self._out_folder, stretch=1)
        out_folder_row.addWidget(browse_btn)

        out_layout = QVBoxLayout()
        out_layout.addLayout(out_name_row)
        out_layout.addLayout(out_folder_row)
        out_group.setLayout(out_layout)

        # --- Progress / run ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
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
        layout.addLayout(list_row, stretch=1)
        layout.addWidget(preview_widget)
        layout.addWidget(out_group)
        layout.addLayout(run_row)

    # ------------------------------------------------------------------ #
    # Public slots called by MainWindow
    # ------------------------------------------------------------------ #

    def set_encoder(self, choice: EncoderChoice) -> None:
        self._encoder = choice

    def set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running and self._can_run())
        self._cancel_btn.setEnabled(running)
        self._file_list.setEnabled(not running)

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
        guidance = build_job_failure_guidance(
            "combine",
            error.event,
            error.message,
            job_id=error.job_id,
        )
        show_diagnostic_dialog(
            self,
            title="Combine failed",
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

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _add_files(self) -> None:
        default_dir = ""
        current_paths = self._file_list.all_paths()
        if current_paths:
            default_dir = str(current_paths[0].parent)
        if not default_dir:
            default_dir = last_dir(KEY_COMBINE_ADD)
        selected_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add video files",
            default_dir,
            "Video files (*.mkv *.mp4);;All files (*)",
        )
        if selected_paths:
            remember_dir(KEY_COMBINE_ADD, str(Path(selected_paths[0]).parent))
            self._file_list.add_paths([Path(path) for path in selected_paths])

    def _browse_output_folder(self) -> None:
        default_dir = self._out_folder.text().strip()
        if not default_dir:
            paths = self._file_list.all_paths()
            default_dir = str(paths[0].parent) if paths else last_dir(KEY_COMBINE_OUT)

        folder = QFileDialog.getExistingDirectory(self, "Output folder", default_dir)
        if folder:
            self._out_folder.setText(folder)
            remember_dir(KEY_COMBINE_OUT, folder)

    def _on_clear(self) -> None:
        self._file_list.clear_all()
        self._out_filename.clear()

    def _on_files_changed(self) -> None:
        self._update_default_output()
        self._refresh_preview()
        self._run_btn.setEnabled(self._can_run())

    @pyqtSlot(list)
    def _on_files_added(self, new_paths: list[Path]) -> None:
        self._update_default_output()
        self._refresh_preview()
        self._run_btn.setEnabled(self._can_run())
        if new_paths:
            self._start_probe_job(new_paths)

    def set_probe_results(self, probes: list[FileProbe]) -> None:
        probes_by_path = {probe.path: probe for probe in probes}
        self._file_list.set_probe_results(probes_by_path)
        self._refresh_preview()

    def _update_default_output(self) -> None:
        paths = self._file_list.all_paths()
        if not paths:
            return
        if not self._out_filename.text():
            self._out_filename.setText(f"{paths[0].stem}-combined.mkv")
        if not self._out_folder.text():
            self._out_folder.setText(str(paths[0].parent))

    def _can_run(self) -> bool:
        return self._file_list.count() >= 2

    def _default_probe_file(self, path: Path) -> FileProbe:
        return probe(ffprobe_path(), path)

    def _on_strategy_toggled(self, checked: bool) -> None:
        self._strategy_toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self._strategy_details.setVisible(checked and bool(self._strategy_details.text()))

    def _set_strategy_state(
        self,
        *,
        summary: str,
        color: str,
        details: str,
        why_tooltip: str = "",
    ) -> None:
        self._strategy_label.setText(summary)
        self._strategy_label.setStyleSheet(f"QLabel {{ color: {color}; font-weight: 700; }}")
        self._strategy_details.setText(details)
        has_details = bool(details)
        self._strategy_toggle.setEnabled(has_details)
        if not has_details:
            self._strategy_toggle.setChecked(False)
            self._strategy_toggle.setArrowType(Qt.ArrowType.RightArrow)
            self._strategy_details.setVisible(False)
        else:
            self._strategy_details.setVisible(self._strategy_toggle.isChecked())
        self._why_label.setVisible(bool(why_tooltip))
        self._why_label.setToolTip(why_tooltip)

    def _refresh_preview(self) -> None:
        paths = self._file_list.all_paths()
        if not paths:
            self._set_strategy_state(
                summary="Add files to begin.",
                color="#475569",
                details="",
            )
            return

        probes_by_path = self._file_list.cached_probes()
        missing_paths = [path for path in paths if path not in probes_by_path]
        if missing_paths:
            count = len(missing_paths)
            noun = "input" if count == 1 else "inputs"
            self._set_strategy_state(
                summary=f"Probing {count} {noun}…",
                color="#475569",
                details="",
            )
            return

        if len(paths) < 2:
            self._set_strategy_state(
                summary="Add at least two files to preview the concat strategy.",
                color="#475569",
                details="",
            )
            return

        probes = [probes_by_path[path] for path in paths]
        self._apply_plan(make_concat_plan(probes))

    def _apply_plan(self, plan: ConcatPlan) -> None:
        if plan.strategy == ConcatStrategy.STREAM_COPY:
            self._set_strategy_state(
                summary="Will stream-copy concat",
                color="#15803d",
                details=(
                    f"All {len(plan.inputs)} inputs match on video and audio signatures, "
                    "so the final combine can stay on the copy path."
                ),
            )
            return

        assert plan.target_sig is not None
        normalize_names = [plan.inputs[index].path.name for index in plan.normalize_indices]
        detail_lines = [
            (
                "Target normalize signature: "
                f"{plan.target_sig.width}x{plan.target_sig.height}"
                f"@{plan.target_sig.fps:.2f} {plan.target_sig.codec}/aac"
            ),
            "Normalize: " + (", ".join(normalize_names) if normalize_names else "none"),
        ]
        why_lines = [
            f"{mismatch.path.name}: " + "; ".join(mismatch.fields) for mismatch in plan.mismatches
        ]
        self._set_strategy_state(
            summary=f"Will normalize {len(plan.normalize_indices)} of {len(plan.inputs)} inputs",
            color="#b45309",
            details="\n".join(detail_lines),
            why_tooltip="\n".join(why_lines),
        )

    def _on_run(self) -> None:
        paths = self._file_list.all_paths()
        if not paths:
            return
        output_path = self._selected_output_path()
        if output_path is None:
            return
        self.run_requested.emit(paths, output_path, self._encoder)

    def _selected_output_path(self) -> Path | None:
        filename = self._out_filename.text().strip()
        if not filename:
            show_warning_message(self, "No output", "Please specify an output filename.")
            return None
        if "/" in filename or "\\" in filename:
            show_warning_message(
                self,
                "Invalid filename",
                "Please enter only an output filename. Choose the folder separately.",
            )
            return None
        folder = self._out_folder.text().strip()
        if not folder:
            show_warning_message(self, "No output", "Please specify an output folder.")
            return None
        return Path(folder) / filename

    def _start_probe_job(self, paths: list[Path]) -> None:
        thread = QThread(self)
        job = ProbeFilesJob(paths, self._probe_file)
        job.moveToThread(thread)

        self._probe_threads.append(thread)
        self._probe_jobs.append(job)
        self._probe_paths_by_job_id[job.job_id] = list(paths)

        thread.started.connect(job.run)
        job.finished.connect(thread.quit)
        job.probed.connect(self._on_probe_results)
        job.failed.connect(self._on_probe_failed)
        thread.finished.connect(lambda thread=thread, job=job: self._cleanup_probe_job(thread, job))
        thread.start()

    def _cleanup_probe_job(self, thread: QThread, job: ProbeFilesJob) -> None:
        if job in self._probe_jobs:
            self._probe_jobs.remove(job)
        if thread in self._probe_threads:
            self._probe_threads.remove(thread)
        self._probe_paths_by_job_id.pop(job.job_id, None)
        job.deleteLater()
        thread.deleteLater()

    @pyqtSlot(object)
    def _on_probe_results(self, result: ProbeFilesResult) -> None:
        expected_paths = result.paths
        current_paths = set(self._file_list.all_paths())
        if not any(path in current_paths for path in expected_paths):
            return
        probes_by_path = self._file_list.cached_probes()
        probes_by_path.update(
            {probe.path: probe for probe in result.probes if probe.path in current_paths}
        )
        self._file_list.set_probe_results(probes_by_path)
        self._refresh_preview()

    @pyqtSlot(object)
    def _on_probe_failed(self, error: JobError) -> None:
        expected_paths = self._probe_paths_by_job_id.get(error.job_id, [])
        current_paths = set(self._file_list.all_paths())
        if not any(path in current_paths for path in expected_paths):
            return
        self._set_strategy_state(
            summary="Preview unavailable until inputs can be probed.",
            color="#92400e",
            details=error.message,
        )
