#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate README screenshots using offscreen-rendered fake data.

Runs StormFuse's real GUI code with fabricated sample paths and probe data
(no real media files or user paths) and writes PNGs to ``docs/images/``.

Usage:
    .venv/bin/python tools/screenshots/generate_readme_screenshots.py

Re-run this after UI changes to regenerate the README screenshot set.
"""

# QT_QPA_PLATFORM must be set before importing Qt.
# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from PIL import Image
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QTabWidget

from stormfuse.ffmpeg.encoders import EncoderChoice
from stormfuse.ffmpeg.probe import AudioStream, FileProbe, VideoStream
from stormfuse.ui.main_window import MainWindow
from stormfuse.ui.theme import apply_application_theme

OUT_DIR = REPO_ROOT / "docs" / "images"

FAKE_DIR = Path("/tmp/stormfuse-screenshots/sample-videos")


def _probe(
    path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    video_codec: str = "h264",
    audio_codec: str = "aac",
    duration_sec: float = 3600.0,
) -> FileProbe:
    return FileProbe(
        path=path,
        video=VideoStream(
            codec=video_codec,
            width=width,
            height=height,
            pix_fmt="yuv420p",
            fps=fps,
        ),
        audio=AudioStream(codec=audio_codec, sample_rate=48000, channels=2),
        duration_sec=duration_sec,
        size_bytes=12_500_000_000,
        raw={},
    )


def _qpixmap_to_pil(pixmap) -> Image.Image:
    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = qimage.width(), qimage.height()
    buffer = qimage.bits().asstring(qimage.sizeInBytes())
    return Image.frombuffer("RGBA", (width, height), buffer, "raw", "RGBA", 0, 1).copy()


def _grab(widget) -> Image.Image:
    QApplication.processEvents()
    return _qpixmap_to_pil(widget.grab())


def _save(image: Image.Image, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    image.convert("RGB").save(path)
    print(f"Wrote {path} ({image.width}x{image.height})")


def _populate_combine_tab(window: MainWindow) -> None:
    tab = window._combine_tab  # type: ignore[attr-defined]
    path_a = FAKE_DIR / "clip_20260417-204926.mkv"
    path_b = FAKE_DIR / "clip_20260417-205026.mkv"
    path_c = FAKE_DIR / "clip_20260417-210126.mkv"
    probes = {
        path_a: _probe(path_a),
        path_b: _probe(path_b, width=1280, height=720, fps=29.97),
        path_c: _probe(path_c),
    }
    tab._file_list._set_paths([path_a, path_b, path_c], emit_files_changed=False)  # type: ignore[attr-defined]
    tab._file_list.set_probe_results(probes)  # type: ignore[attr-defined]
    tab._out_filename.setText("clip_20260417-combined.mkv")  # type: ignore[attr-defined]
    tab._out_folder.setText(str(FAKE_DIR))  # type: ignore[attr-defined]
    tab._refresh_preview()  # type: ignore[attr-defined]
    tab._run_btn.setEnabled(True)  # type: ignore[attr-defined]


def _populate_compress_tab(window: MainWindow) -> None:
    tab = window._compress_tab  # type: ignore[attr-defined]
    input_path = FAKE_DIR / "clip_20260417-combined.mkv"
    tab._input_field.setText(str(input_path))  # type: ignore[attr-defined]
    tab._source_size_label.setText("Source size: 12.50 GB")  # type: ignore[attr-defined]
    tab.set_duration(3600.0)  # type: ignore[attr-defined]
    tab._slider.set_max_gb(12.4)  # type: ignore[attr-defined]
    tab._out_filename.setText("clip_20260417-compressed.mp4")  # type: ignore[attr-defined]
    tab._out_folder.setText(str(FAKE_DIR))  # type: ignore[attr-defined]
    tab._refresh_run_button_state()  # type: ignore[attr-defined]


def capture_tab(window: MainWindow, tab_index: int, output_name: str) -> None:
    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    tabs.setCurrentIndex(tab_index)
    QApplication.processEvents()
    _save(_grab(window), output_name)


def main() -> None:
    app = QApplication(sys.argv)
    apply_application_theme(app)

    window = MainWindow(
        ffmpeg_exe=FAKE_DIR / "ffmpeg",
        ffprobe_exe=FAKE_DIR / "ffprobe",
        encoder=EncoderChoice.NVENC,
        check_updates_on_startup=False,
    )
    window.resize(920, 760)
    window.show()
    QApplication.processEvents()

    _populate_combine_tab(window)
    capture_tab(window, 0, "combine-walkthrough.png")

    _populate_compress_tab(window)
    capture_tab(window, 1, "compress-walkthrough.png")

    window.close()


if __name__ == "__main__":
    main()
