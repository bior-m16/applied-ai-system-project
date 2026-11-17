"""Tests for the reminder rules: five minutes before, at the start time, once each, never for done tasks."""

from datetime import datetime, timedelta

import pytest

import notifications as n
from pawpal_system import Task

START = datetime(2026, 11, 17, 8, 0)


def task(title="Walk", pet="Mochi", start=START, minutes=20, completed=False):
    return Task(title, pet, minutes, 2, start, completed=completed)


def at(minutes_from_start: float) -> datetime:
    return START + timedelta(minutes=minutes_from_start)


def kinds(tasks, now, sent=()):
    return [a.kind for a in n.alerts_due(tasks, now, sent)]


def test_nothing_more_than_five_minutes_before():
    assert kinds([task()], at(-5.5)) == []
    assert kinds([task()], at(-30)) == []


def test_soon_alert_fires_from_exactly_five_minutes_before():
    assert kinds([task()], at(-5)) == ["soon"]
    assert kinds([task()], at(-2)) == ["soon"]
    assert kinds([task()], at(-0.5)) == ["soon"]


def test_now_alert_fires_at_the_start_time_and_for_a_few_minutes_after():
    assert kinds([task()], at(0)) == ["now"]
    assert kinds([task()], at(2.9)) == ["now"]


def test_no_alert_once_the_window_has_passed():
    assert kinds([task()], at(3)) == []
    assert kinds([task()], at(60)) == []


def test_each_reminder_is_only_sent_once():
    first = n.alerts_due([task()], at(-4))
    assert len(first) == 1
    sent = {a.key for a in first}
    assert n.alerts_due([task()], at(-3), sent) == []          # same "soon" reminder, already sent
    assert [a.kind for a in n.alerts_due([task()], at(0), sent)] == ["now"]   # the "now" one is separate


def test_completed_tasks_never_alert():
    assert kinds([task(completed=True)], at(-3)) == []
    assert kinds([task(completed=True)], at(0)) == []


def test_text_names_the_task_the_pet_and_the_time():
    soon = n.alerts_due([task("Medication", "Luna", minutes=5)], at(-5))[0]
    assert soon.title == "Medication in 5 minutes"
    assert "Luna" in soon.body and "08:00" in soon.body
    now = n.alerts_due([task("Medication", "Luna", minutes=5)], at(0))[0]
    assert now.title == "Time for Medication" and "due now" in now.body


def test_one_minute_wording_and_rounding_up():
    assert n.alerts_due([task()], START - timedelta(seconds=30))[0].title == "Walk in 1 minute"
    assert n.minutes_until(task(), START - timedelta(seconds=61)) == 2


def test_two_tasks_are_listed_earliest_first_and_other_days_are_ignored():
    later = task("Dinner", "Luna", START + timedelta(minutes=2))
    other_day = task("Vet", "Mochi", START + timedelta(days=1))
    alerts = n.alerts_due([later, other_day, task()], at(-1))
    assert [a.task.title for a in alerts] == ["Walk", "Dinner"]


def test_identical_tasks_at_different_times_have_different_keys():
    a, b = task(start=START), task(start=START + timedelta(hours=1))
    assert n.alert_key(a, "soon") != n.alert_key(b, "soon")


def test_next_up_picks_the_earliest_pending_task_not_yet_over():
    done = task("Done", completed=True, start=at(10))
    old = task("Old", start=at(-60))
    first = task("First", start=at(20))
    second = task("Second", start=at(90))
    assert n.next_up([second, first, old, done], START).title == "First"
    assert n.next_up([old, done], START) is None
    just_started = task("Just started", start=at(-1))
    assert n.next_up([just_started, first], START).title == "Just started"


@pytest.mark.parametrize(
    "minutes_ahead, expected",
    [(12, "in 12 min"), (60, "in 1 h"), (125, "in 2 h 5 min"), (60 * 24, "tomorrow at 08:00"), (60 * 24 * 3, "Tue Nov 17 at 08:00")],
)
def test_describe_wait_for_a_future_task(minutes_ahead, expected):
    now = START - timedelta(minutes=minutes_ahead)
    assert n.describe_wait(task(start=START), now) == expected


def test_describe_wait_says_now_once_the_start_time_has_arrived():
    assert n.describe_wait(task(start=START), START) == "now"
    assert n.describe_wait(task(start=START), START + timedelta(minutes=1)) == "now"
