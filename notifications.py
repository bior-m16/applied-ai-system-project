"""Reminder logic for PawPal+: which tasks need a notification right now. No Streamlit in here.

Two reminders per pending task:
- "soon": the task starts within LEAD_MINUTES (default 5 minutes) and hasn't started yet.
- "now":  the task's start time has arrived (it started less than NOW_WINDOW ago).

The app checks every 30 seconds while a browser tab is open. A reminder can be missed if the tab
was closed, or the computer asleep, for the whole window, so the windows are generous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from pawpal_system import Task

LEAD_MINUTES = 5                        # how early the "soon" reminder fires
NOW_WINDOW = timedelta(minutes=3)       # how long after the start time the "now" reminder can still fire


@dataclass(frozen=True)
class Alert:
    """One reminder to show: `key` is unique per task and kind, so it is only sent once."""

    kind: str          # "soon" or "now"
    key: str
    title: str
    body: str
    task: Task


def current_time() -> datetime:
    """The clock the app uses (a function so tests can fake it)."""
    return datetime.now()


def alert_key(task: Task, kind: str) -> str:
    return f"{kind}|{task.pet_name}|{task.title}|{task.scheduled_time.isoformat()}"


def minutes_until(task: Task, now: datetime) -> int:
    """Whole minutes until the task starts, rounded up (a task 30 seconds away is "1 minute")."""
    seconds = (task.scheduled_time - now).total_seconds()
    return max(0, -(-int(seconds) // 60))


def alerts_due(
    tasks: Iterable[Task], now: datetime, sent: Iterable[str] = (), lead_minutes: int = LEAD_MINUTES
) -> list[Alert]:
    """Reminders that should be shown now and have not been sent yet, earliest task first.

    Completed tasks never alert. `sent` holds the keys of reminders already shown; the caller adds the
    returned alerts' keys to it, so each reminder appears once.
    """
    already = set(sent)
    lead = timedelta(minutes=lead_minutes)
    found: list[Alert] = []
    for task in sorted(tasks, key=lambda t: t.scheduled_time):
        if task.completed:
            continue
        start = task.scheduled_time
        if start - lead <= now < start:
            kind = "soon"
            mins = minutes_until(task, now)
            unit = "minute" if mins == 1 else "minutes"
            title = f"{task.title} in {mins} {unit}"
            body = f"{task.pet_name}: starts at {start:%H:%M} ({task.duration_minutes} min)."
        elif start <= now < start + NOW_WINDOW:
            kind = "now"
            title = f"Time for {task.title}"
            body = f"{task.pet_name}: {task.title} is due now ({start:%H:%M}, {task.duration_minutes} min)."
        else:
            continue
        key = alert_key(task, kind)
        if key not in already:
            found.append(Alert(kind=kind, key=key, title=title, body=body, task=task))
    return found


def next_up(tasks: Iterable[Task], now: datetime) -> Optional[Task]:
    """The pending task that starts next (a task that started under NOW_WINDOW ago still counts)."""
    upcoming = [t for t in tasks if not t.completed and t.scheduled_time + NOW_WINDOW > now]
    return min(upcoming, key=lambda t: t.scheduled_time, default=None)


def describe_wait(task: Task, now: datetime) -> str:
    """"in 12 min", "in 2 h 5 min", "now", or "tomorrow at 07:00", for the 'up next' line."""
    if task.scheduled_time <= now:
        return "now"
    mins = minutes_until(task, now)
    if task.scheduled_time.date() != now.date():
        day = "tomorrow" if (task.scheduled_time.date() - now.date()).days == 1 else f"{task.scheduled_time:%a %b %d}"
        return f"{day} at {task.scheduled_time:%H:%M}"
    if mins < 60:
        return f"in {mins} min"
    hours, rest = divmod(mins, 60)
    return f"in {hours} h {rest} min" if rest else f"in {hours} h"
