import logging
from datetime import time

import pytest
import schedule

from core.scheduler import TaskScheduler


@pytest.fixture
def scheduler():
    schedule.clear()
    yield TaskScheduler(config=None)
    schedule.clear()


def test_failing_task_does_not_stop_others(scheduler, caplog):
    calls = []

    def broken():
        raise RuntimeError("boom")

    scheduler.add_task(broken, interval=1, unit="seconds")
    scheduler.add_task(lambda: calls.append(1), 1, "seconds", task_name="ok")

    with caplog.at_level(logging.ERROR):
        schedule.run_all()

    assert calls == [1]
    assert "broken" in caplog.text and "boom" in caplog.text


@pytest.mark.parametrize("unit", ["days", "months", "quarters"])
def test_at_applies_to_first_run(scheduler, unit):
    scheduler.add_task(lambda: None, 1, unit, at="10:00", task_name="t")

    job = schedule.get_jobs("t")[0]
    assert job.at_time == time(10, 0)
    assert job.next_run.time() == time(10, 0)


def test_at_ignored_for_minutes(scheduler):
    scheduler.add_task(lambda: None, 1, "minutes", at="10:00", task_name="t")
    assert schedule.get_jobs("t")[0].at_time is None


def test_remove_task(scheduler):
    scheduler.add_task(lambda: None, 1, "minutes", task_name="t")
    scheduler.add_task(lambda: None, 1, "minutes", task_name="other")

    scheduler.remove_task("t")

    assert schedule.get_jobs("t") == []
    assert len(schedule.get_jobs("other")) == 1


def test_interval_for_months_is_warned(scheduler, caplog):
    with caplog.at_level(logging.WARNING):
        scheduler.add_task(lambda: None, 2, "months", at="10:00", task_name="t")
    assert "interval=2" in caplog.text
    assert len(schedule.get_jobs("t")) == 1
