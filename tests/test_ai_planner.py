"""Tests for the AI agent loop. A scripted fake client stands in for Claude, so no API key or network is needed."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from ai_planner import MAX_STEPS, PlanningSession, run_agent
from pawpal_system import Owner, Pet, Task

DAY = date(2026, 11, 16)


def at(hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 11, 16, hh, mm)


def make_owner(minutes: int = 120) -> Owner:
    owner = Owner(name="Jordan", available_minutes=minutes)
    owner.add_pet(Pet(name="Rex", species="dog", age=3))
    owner.add_pet(Pet(name="Mia", species="cat", age=7, notes="needs daily medication"))
    return owner


def call(name: str, **args):
    call.n += 1
    return SimpleNamespace(type="tool_use", id=f"t{call.n}", name=name, input=args)


call.n = 0


def turn(*blocks, stop="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


class FakeClient:
    """Plays back scripted responses and records the requests it was sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot: the agent keeps appending
        if not self.responses:
            raise AssertionError("agent asked for more turns than the script has")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def add(title="Walk", pet="Rex", start="08:00", minutes=30, priority=2, frequency="once"):
    return call("add_task", title=title, pet_name=pet, start_time=start,
                duration_minutes=minutes, priority=priority, frequency=frequency)


# --- the happy path -------------------------------------------------------------------

def test_agent_adds_checks_and_finishes():
    client = FakeClient(
        turn(add("Morning walk", "Rex", "08:00", 30, 3, "daily"), add("Medication", "Mia", "08:30", 10, 3)),
        turn(call("check_schedule")),
        turn(call("finish", summary="Added a walk and medication.")),
    )
    result = run_agent(make_owner(), "walk Rex and give Mia her pill", DAY, client)
    assert result.ok and result.summary == "Added a walk and medication."
    assert [t.title for t in result.added] == ["Morning walk", "Medication"]
    assert result.added[0].frequency == "daily" and result.added[0].scheduled_time == at(8)


def test_plan_is_a_proposal_until_committed():
    real = make_owner()
    client = FakeClient(turn(add()), turn(call("finish", summary="ok")))
    result = run_agent(real, "walk Rex", DAY, client)
    assert result.ok
    assert real.get_all_tasks() == []                  # sandbox only
    assert result.commit_to(real) == 1
    assert [t.title for t in real.get_all_tasks()] == ["Walk"]


def test_context_sent_to_the_model_includes_pets_and_existing_tasks():
    owner = make_owner(90)
    owner.pets[0].add_task(Task("Vet", "Rex", 45, 3, at(10)))
    client = FakeClient(turn(call("finish", summary="nothing to add")))
    run_agent(owner, "nothing", DAY, client)
    first = client.requests[0]["messages"][0]["content"]
    assert "Rex (dog, age 3)" in first and "needs daily medication" in first
    assert "10:00 Vet" in first and "90 minutes available" in first


# --- the check / revise loop ----------------------------------------------------------

def test_agent_revises_after_check_finds_a_conflict():
    client = FakeClient(
        turn(add("Walk", "Rex", "08:00", 30), add("Meds", "Mia", "08:15", 10)),
        turn(call("check_schedule")),
        turn(call("remove_task", title="Meds", pet_name="Mia")),
        turn(add("Meds", "Mia", "08:30", 10)),
        turn(call("check_schedule")),
        turn(call("finish", summary="Fixed the overlap.")),
    )
    result = run_agent(make_owner(), "walk and meds", DAY, client)
    assert result.ok
    assert any("Problems" in s or "overlap" in s for s in result.steps)
    # the conflict text really was sent back to the model as a tool result
    tool_results = [m["content"] for r in client.requests for m in r["messages"] if m["role"] == "user" and isinstance(m["content"], list)]
    assert any("overlaps" in item["content"] for batch in tool_results for item in batch)


def test_finish_is_verified_by_code_not_trusted():
    # The model claims it is done while two tasks overlap. The code refuses and sends it back.
    client = FakeClient(
        turn(add("Walk", "Rex", "08:00", 30), add("Meds", "Mia", "08:10", 10)),
        turn(call("finish", summary="done")),
        turn(call("remove_task", title="Meds", pet_name="Mia")),
        turn(add("Meds", "Mia", "09:00", 10)),
        turn(call("finish", summary="done for real")),
    )
    result = run_agent(make_owner(), "walk and meds", DAY, client)
    assert result.ok and result.summary == "done for real"
    assert any("Check after finish found problems" in s for s in result.steps)


def test_gives_up_when_finish_keeps_being_wrong():
    bad = [turn(add("A", "Rex", "08:00", 30), add("B", "Mia", "08:00", 30))]
    bad += [turn(call("finish", summary="done")) for _ in range(5)]
    result = run_agent(make_owner(), "x", DAY, FakeClient(*bad))
    assert not result.ok and result.problems
    assert "overlaps" in result.problems[0]


def test_over_the_time_budget_is_a_problem():
    client = FakeClient(turn(add("Long", "Rex", "08:00", 100), add("Longer", "Mia", "10:00", 100)),
                        turn(call("check_schedule")), turn(call("finish", summary="x")),
                        turn(call("finish", summary="x")), turn(call("finish", summary="x")))
    result = run_agent(make_owner(120), "lots", DAY, client)
    assert not result.ok
    assert any("200 min but the owner has 120" in p for p in result.problems)


def test_step_limit_stops_a_runaway_agent():
    client = FakeClient(*[turn(call("check_schedule")) for _ in range(MAX_STEPS)])
    result = run_agent(make_owner(), "loop forever", DAY, client)
    assert not result.ok and len(client.requests) == MAX_STEPS


# --- guardrails -----------------------------------------------------------------------

@pytest.mark.parametrize("args, fragment", [
    (dict(pet="Ghost"), "Unknown pet"),
    (dict(start="25:99"), "not a valid HH:MM"),
    (dict(start="noon"), "not a valid HH:MM"),
    (dict(minutes=0), "duration_minutes"),
    (dict(minutes=999), "duration_minutes"),
    (dict(minutes=True), "duration_minutes"),
    (dict(priority=9), "priority"),
    (dict(frequency="hourly"), "frequency"),
    (dict(title="   "), "title"),
])
def test_bad_tool_arguments_are_rejected_without_changing_anything(args, fragment):
    session = PlanningSession(make_owner(), DAY)
    with pytest.raises(ValueError, match=fragment):
        session.add_task(dict(title="Walk", pet_name="Rex", start_time="08:00",
                              duration_minutes=30, priority=2, frequency="once") | _rename(args))
    assert session.added == [] and session.owner.get_all_tasks() == []


def _rename(args):
    mapping = {"pet": "pet_name", "start": "start_time", "minutes": "duration_minutes"}
    return {mapping.get(k, k): v for k, v in args.items()}


def test_rejected_call_is_reported_back_and_the_agent_recovers():
    client = FakeClient(
        turn(add("Walk", "Ghost", "08:00")),
        turn(add("Walk", "Rex", "08:00")),
        turn(call("finish", summary="ok")),
    )
    result = run_agent(make_owner(), "walk", DAY, client)
    assert result.ok and len(result.added) == 1
    second_request_results = client.requests[1]["messages"][-1]["content"]
    assert second_request_results[0]["is_error"] and "Unknown pet" in second_request_results[0]["content"]


def test_agent_cannot_remove_existing_tasks():
    owner = make_owner()
    owner.pets[0].add_task(Task("Vet", "Rex", 45, 3, at(10)))
    session = PlanningSession(owner, DAY)
    with pytest.raises(ValueError, match="can't be removed"):
        session.remove_task({"title": "Vet", "pet_name": "Rex"})
    assert len(session.owner.get_all_tasks()) == 1


def test_task_cap():
    session = PlanningSession(make_owner(), DAY)
    for i in range(20):
        session.add_task(dict(title=f"T{i}", pet_name="Rex", start_time="08:00",
                              duration_minutes=1, priority=1, frequency="once"))
    with pytest.raises(ValueError, match="No more than"):
        session.add_task(dict(title="one more", pet_name="Rex", start_time="09:00",
                              duration_minutes=1, priority=1, frequency="once"))


def test_tasks_outside_the_day_window_are_flagged():
    session = PlanningSession(make_owner(), DAY)
    session.add_task(dict(title="Late", pet_name="Rex", start_time="21:45",
                          duration_minutes=30, priority=1, frequency="once"))
    session.add_task(dict(title="Early", pet_name="Mia", start_time="05:00",
                          duration_minutes=10, priority=1, frequency="once"))
    problems = session.problems()
    assert sum("runs outside" in p for p in problems) == 2


def test_find_free_slot_skips_existing_tasks():
    owner = make_owner()
    owner.pets[0].add_task(Task("Vet", "Rex", 60, 3, at(6)))
    session = PlanningSession(owner, DAY)
    assert "07:00" in session.find_free_slot({"duration_minutes": 30})


# --- failure handling -----------------------------------------------------------------

def test_empty_and_oversized_requests_never_call_the_api():
    client = FakeClient()
    assert not run_agent(make_owner(), "   ", DAY, client).ok
    assert "too long" in run_agent(make_owner(), "x" * 5000, DAY, client).summary
    assert client.requests == []


def test_needs_a_pet():
    result = run_agent(Owner("Jordan", 60), "walk the dog", DAY, FakeClient())
    assert not result.ok and "Add a pet" in result.summary


def test_api_error_becomes_a_failed_result():
    result = run_agent(make_owner(), "walk Rex", DAY, FakeClient(RuntimeError("connection reset")))
    assert not result.ok and "could not be reached" in result.summary


def test_refusal_becomes_a_failed_result():
    result = run_agent(make_owner(), "walk Rex", DAY, FakeClient(turn(stop="refusal")))
    assert not result.ok and "declined" in result.summary


def test_missing_api_key_is_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    result = run_agent(make_owner(), "walk Rex", DAY)
    assert not result.ok and "ANTHROPIC_API_KEY" in result.summary


def test_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("PAWPAL_MODEL", "claude-haiku-5-5")
    client = FakeClient(turn(call("finish", summary="ok")))
    run_agent(make_owner(), "nothing", DAY, client)
    assert client.requests[0]["model"] == "claude-haiku-5-5"
