# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for stormfuse.timestamp_parser (§11.2)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from stormfuse.timestamp_parser import parse_filename_timestamp


class TestObsFormat:
    """Format A: YYYYMMDD-HHMMSS anywhere in the basename."""

    def test_basic(self) -> None:
        result = parse_filename_timestamp("RinCity_MyFreeCams_20260417-204926.mkv")
        assert result == datetime(2026, 4, 17, 20, 49, 26)

    def test_at_start(self) -> None:
        result = parse_filename_timestamp("20260101-000000_recording.mkv")
        assert result == datetime(2026, 1, 1, 0, 0, 0)

    def test_at_end(self) -> None:
        result = parse_filename_timestamp("recording_20260630-235959.mkv")
        assert result == datetime(2026, 6, 30, 23, 59, 59)

    def test_midnight(self) -> None:
        result = parse_filename_timestamp("obs_20260101-000000.mkv")
        assert result == datetime(2026, 1, 1, 0, 0, 0)

    def test_invalid_month_returns_none(self) -> None:
        result = parse_filename_timestamp("rec_20261399-120000.mkv")
        assert result is None

    def test_path_object(self) -> None:
        result = parse_filename_timestamp(Path("some/dir/obs_20260417-204926.mkv"))
        assert result == datetime(2026, 4, 17, 20, 49, 26)


class TestMfcFormat:
    """Format B: M-D-YYYY followed by HHMM[am|pm]."""

    def test_am(self) -> None:
        result = parse_filename_timestamp("Club Show - 4-18-2026 - 1242am.mp4")
        assert result == datetime(2026, 4, 18, 0, 42)  # 12am = 0h

    def test_pm(self) -> None:
        result = parse_filename_timestamp("Club Show - 4-18-2026 - 0130pm.mp4")
        assert result == datetime(2026, 4, 18, 13, 30)

    def test_noon(self) -> None:
        result = parse_filename_timestamp("Club Show - 1-1-2026 - 1200pm.mp4")
        assert result == datetime(2026, 1, 1, 12, 0)

    def test_midnight(self) -> None:
        result = parse_filename_timestamp("Club Show - 12-31-2026 - 1200am.mp4")
        assert result == datetime(2026, 12, 31, 0, 0)

    def test_uppercase_am(self) -> None:
        result = parse_filename_timestamp("Club Show - 4-18-2026 - 0930AM.mp4")
        assert result == datetime(2026, 4, 18, 9, 30)

    def test_single_digit_month_day(self) -> None:
        result = parse_filename_timestamp("Club Show - 1-5-2026 - 0800pm.mp4")
        assert result == datetime(2026, 1, 5, 20, 0)


class TestNoMatch:
    def test_no_timestamp_returns_none(self) -> None:
        assert parse_filename_timestamp("random_video_file.mkv") is None

    def test_empty_string(self) -> None:
        assert parse_filename_timestamp("") is None

    def test_just_extension(self) -> None:
        assert parse_filename_timestamp(".mkv") is None

    def test_partial_obs_pattern(self) -> None:
        # Only 6 digits, not full YYYYMMDD-HHMMSS
        assert parse_filename_timestamp("rec_202604-123456.mkv") is None
