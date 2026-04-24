# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the base Job lifecycle and job ID format (§8, §9)."""

from __future__ import annotations

import logging

import pytest

import stormfuse.jobs.base as jobs_base
from stormfuse.jobs.base import Job
from stormfuse.logging_setup import current_job_id


class DummyJob(Job):
    def __init__(self) -> None:
        self.observed_job_id: str | None = None
        super().__init__()

    def _run_job(self) -> None:
        self.observed_job_id = current_job_id()


def test_job_id_is_time_sortable_with_job_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_base._JOB_ID_STATE, "last_ms", 0)
    monkeypatch.setattr(jobs_base._JOB_ID_STATE, "seq", 0)
    monkeypatch.setattr(jobs_base.time, "time_ns", lambda: 1_700_000_000_000_000_000)
    monkeypatch.setattr(jobs_base.secrets, "randbits", lambda bits: 0x123456789ABC)

    first = DummyJob()
    second = DummyJob()

    assert first.job_id.startswith("dummy-")
    assert second.job_id.startswith("dummy-")
    assert second.job_id > first.job_id


def test_run_binds_active_job_id() -> None:
    job = DummyJob()

    job.run()

    assert job.observed_job_id == job.job_id
    assert current_job_id() is None


def test_handled_failure_logs_job_fail_without_job_finish(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingJob(Job):
        def _run_job(self) -> None:
            self.fail(
                event="probe.error",
                message="Probe failed for broken.mkv",
                stderr_tail="line 1\nline 2\n",
            )

    failed: list[object] = []
    done: list[object] = []
    job = FailingJob()
    job.failed.connect(failed.append)
    job.done.connect(done.append)

    with caplog.at_level(logging.INFO, logger="jobs.base"):
        job.run()

    assert len(failed) == 1
    assert done == []

    events = [record.event for record in caplog.records if record.name == "jobs.base"]
    assert "job.start" in events
    assert "job.fail" in events
    assert "job.finish" not in events

    fail_record = next(record for record in caplog.records if record.event == "job.fail")
    assert fail_record.job_id == job.job_id
    assert fail_record.ctx["cause_event"] == "probe.error"
    assert fail_record.ctx["stderr_tail"] == ["line 1", "line 2"]
