"""Tests for the pure daily-quiz schedule logic in Cogs/quiz_logic.py."""

from datetime import datetime, timedelta, timezone

from Cogs.quiz_logic import evaluate_schedule

MST = timezone(timedelta(hours=-7))


def make_time(hour, minute):
    return datetime(2026, 8, 9, hour, minute, tzinfo=MST)


def test_new_day_returns_reset():
    now = make_time(0, 5)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-08", False, True) == "reset"


def test_midnight_missed_returns_reset():
    now = make_time(12, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-08", True, True) == "reset"


def test_before_start_is_idle():
    now = make_time(5, 59)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "idle"


def test_start_after_six():
    now = make_time(6, 1)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "start"


def test_no_start_when_already_started():
    now = make_time(10, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", True, False) == "idle"


def test_no_start_when_finished_today():
    now = make_time(10, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, True) == "idle"


def test_reveal_at_six_pm():
    now = make_time(18, 1)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", True, False) == "reveal"


def test_no_reveal_without_started():
    now = make_time(19, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "idle"


def test_no_late_start_after_reveal_time():
    # Bot restarts after 6PM; quiz was never posted. It should NOT fire a late
    # start that would be instantly revealed.
    now = make_time(19, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "idle"


def test_invalid_times_are_idle():
    now = make_time(12, 0)
    assert evaluate_schedule(now, "not-a-time", "18:00", "2026-08-09", False, False) == "idle"
    assert evaluate_schedule(now, "25:00", "18:00", "2026-08-09", False, False) == "idle"
    assert evaluate_schedule(now, "06:00", "18:99", "2026-08-09", False, False) == "idle"


def test_start_and_reveal_are_today_bound():
    # 6 AM yesterday: if it is now 6 AM today with a fresh date, start fires.
    now = make_time(6, 0)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "start"


def test_just_before_reveal_still_starts():
    now = make_time(17, 59)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, False) == "start"


def test_after_reveal_already_started_is_idle():
    # Quiz started, reveal already passed, but state not updated yet -> reveal once.
    now = make_time(18, 30)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", True, False) == "reveal"


def test_next_day_reveal_after_midnight_reset():
    # Next morning: reset flag should have fired, then start on the following tick.
    now = make_time(6, 1)
    assert evaluate_schedule(now, "06:00", "18:00", "2026-08-09", False, True) == "idle"
    now2 = now + timedelta(days=1)
    assert evaluate_schedule(now2, "06:00", "18:00", "2026-08-09", False, False) == "reset"
