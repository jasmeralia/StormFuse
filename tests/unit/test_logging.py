# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the JSON log formatter (§11.2)."""

from __future__ import annotations

import json
import logging

from stormfuse.logging_setup import HumanReadableFormatter, JsonLinesFormatter


def _make_record(
    msg: str = "test message",
    event: str = "test.event",
    level: int = logging.INFO,
    **extra: object,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    record.__dict__["event"] = event
    for k, v in extra.items():
        record.__dict__[k] = v
    return record


class TestJsonLinesFormatter:
    def test_output_is_valid_json(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record()
        line = fmt.format(record)
        obj = json.loads(line)
        assert isinstance(obj, dict)

    def test_required_keys_present(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record()
        obj = json.loads(fmt.format(record))
        for key in ("ts", "level", "logger", "event", "msg"):
            assert key in obj, f"Missing key: {key}"

    def test_level_name(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record(level=logging.WARNING)
        obj = json.loads(fmt.format(record))
        assert obj["level"] == "WARNING"

    def test_event_field(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record(event="ffmpeg.start")
        obj = json.loads(fmt.format(record))
        assert obj["event"] == "ffmpeg.start"

    def test_ctx_included_when_present(self) -> None:
        fmt = JsonLinesFormatter()
        ctx = {"argv": ["ffmpeg", "-y"], "encoder": "nvenc"}
        record = _make_record(ctx=ctx)
        obj = json.loads(fmt.format(record))
        assert "ctx" in obj
        assert obj["ctx"]["encoder"] == "nvenc"

    def test_job_id_included_when_present(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record(job_id="abc-123")
        obj = json.loads(fmt.format(record))
        assert obj["job_id"] == "abc-123"

    def test_ts_format(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record()
        obj = json.loads(fmt.format(record))
        ts = obj["ts"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_round_trips(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record(msg="hello world", event="test.roundtrip")
        obj = json.loads(fmt.format(record))
        assert obj["msg"] == "hello world"

    def test_no_extra_keys_by_default(self) -> None:
        fmt = JsonLinesFormatter()
        record = _make_record()
        obj = json.loads(fmt.format(record))
        # Optional keys should not appear when not set
        assert "job_id" not in obj
        assert "ctx" not in obj


class TestHumanReadableFormatter:
    def test_contains_level(self) -> None:
        fmt = HumanReadableFormatter()
        record = _make_record(level=logging.ERROR)
        line = fmt.format(record)
        assert "ERROR" in line

    def test_contains_event(self) -> None:
        fmt = HumanReadableFormatter()
        record = _make_record(event="ffmpeg.start")
        line = fmt.format(record)
        assert "ffmpeg.start" in line

    def test_contains_message(self) -> None:
        fmt = HumanReadableFormatter()
        record = _make_record(msg="Something happened")
        line = fmt.format(record)
        assert "Something happened" in line

    def test_single_line(self) -> None:
        fmt = HumanReadableFormatter()
        record = _make_record()
        line = fmt.format(record)
        assert "\n" not in line.rstrip()
