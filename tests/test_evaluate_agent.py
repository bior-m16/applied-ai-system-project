"""Tests for the evaluation harness: its checks must catch bad plans, or the scores mean nothing."""

import copy
from types import SimpleNamespace

import pytest

import evaluate_agent as ev
from pawpal_system import Task


def result_for(owner, added=(), summary="A long enough summary for the check."):
    """A stand-in agent result whose sandbox owner has the added tasks."""
    sandbox = copy.deepcopy(owner)
    for task in added:
        next(p for p in sandbox.pets if p.name == task.pet_name).add_task(task)
    return SimpleNamespace(ok=True, owner=sandbox, added=list(added), summary=summary)


def test_valid_plan_accepts_a_clean_plan():
    owner = ev.owner_rex()
    result = result_for(owner, [Task("Walk", "Rex", 30, 2, ev.at(8))])
    assert ev.check_valid_plan(result, owner) is None


def test_valid_plan_catches_overlap_overtime_and_out_of_hours():
    owner = ev.owner_rex()  # 120 minutes available
    overlap = result_for(owner, [Task("A", "Rex", 30, 2, ev.at(8)), Task("B", "Rex", 30, 2, ev.at(8, 15))])
    assert "overlaps" in ev.check_valid_plan(overlap, owner)
    overtime = result_for(owner, [Task("A", "Rex", 100, 2, ev.at(8)), Task("B", "Rex", 100, 2, ev.at(12))])
    assert "only 120 available" in ev.check_valid_plan(overtime, owner)
    late = result_for(owner, [Task("A", "Rex", 30, 2, ev.at(21, 45))])
    assert "outside the day window" in ev.check_valid_plan(late, owner)


def test_existing_unchanged_catches_a_removed_task():
    owner = ev.owner_vet_booked()
    intact = result_for(owner)
    assert ev.check_existing_unchanged(intact, owner) is None
    tampered = result_for(owner)
    tampered.owner.pets[0].tasks.clear()
    assert "Vet visit" in ev.check_existing_unchanged(tampered, owner)


def test_unknown_pet_and_keyword_checks():
    owner = ev.owner_luna_only()
    ghost = result_for(owner, [])
    ghost.added = [Task("Walk", "Fluffy", 20, 2, ev.at(9))]
    assert "Fluffy" in ev.check_only_known_pets(ghost, owner)
    assert "fluffy" in ev.no_task_titled("fluffy")(ghost, owner)
    fed = result_for(owner, [Task("Feed Luna", "Luna", 10, 3, ev.at(8))])
    assert ev.has_task("feed", "Luna")(fed, owner) is None
    assert ev.has_task("walk", "Luna")(fed, owner) is not None


def test_summary_checks():
    owner = ev.owner_rex()
    assert ev.summary_mentions("left out")(result_for(owner, summary="Two tasks were left out."), owner) is None
    assert ev.summary_mentions("left out")(result_for(owner, summary="All done."), owner) is not None
    assert ev.check_summary_present(result_for(owner, summary="ok"), owner) is not None


@pytest.mark.parametrize("scenario", [s for s in ev.SCENARIOS if not s.live], ids=lambda s: s.id)
def test_offline_scenarios_pass_without_calling_the_api(scenario):
    outcome = ev.run_trial(scenario)
    assert outcome["passed"], outcome["errors"]
