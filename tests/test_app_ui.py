"""Smoke tests for the Streamlit UI (Today / The pack tabs), run headless with AppTest.

The agent is replaced by a canned result, and .env loading is switched off, so these tests need no
API key and no network. Each test uses its own temporary data file.
"""

from datetime import date, datetime, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ai_planner
from ai_planner import AgentResult
from pawpal_system import Owner, Pet, Task


APP = Path(__file__).resolve().parent.parent / "app.py"


def at_time(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(date.today(), time(hour, minute))


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    monkeypatch.setenv("PAWPAL_DATA_FILE", str(path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)  # don't read the real .env
    return path


def save(path, pets):
    owner = Owner(name="Jordan", available_minutes=90)
    for pet in pets:
        owner.add_pet(pet)
    owner.save_to_json(path)


def pack(*tasks_per_pet):
    """Pets Mochi (dog) and Luna (cat) with the given tasks on Mochi."""
    mochi = Pet(name="Mochi", species="dog", age=3)
    for task in tasks_per_pet:
        mochi.add_task(task)
    return [mochi, Pet(name="Luna", species="cat", age=6)]


def run_app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def all_markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def canned_result(*tasks: Task) -> AgentResult:
    return AgentResult(
        ok=True, summary="Here is a plan.", added=list(tasks), steps=["step one"], day=date.today()
    )


def ask(at: AppTest, monkeypatch, result: AgentResult) -> None:
    monkeypatch.setattr(ai_planner, "run_agent", lambda owner, request, day=None: result)
    at.chat_input[0].set_value("Plan Mochi's day").run()
    assert not at.exception, at.exception


def test_app_loads_with_greeting_and_pet_cards(data_file):
    save(data_file, pack())
    at = run_app()
    assert at.title[0].value == "Hi Jordan, the pack is ready for today."
    text = all_markdown(at)
    assert "### Mochi" in text and "### Luna" in text


def test_no_pets_shows_welcome_and_disables_chat(data_file):
    save(data_file, [])
    at = run_app()
    assert "let's meet your pack" in at.title[0].value
    assert at.chat_input[0].disabled


def test_missing_api_key_disables_chat(data_file, monkeypatch):
    save(data_file, pack())
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    at = run_app()
    assert at.chat_input[0].disabled


def test_adding_a_pet_shows_up_on_today_in_the_same_run(data_file):
    save(data_file, [])
    at = run_app()
    [w for w in at.text_input if w.label == "Pet name"][0].set_value("Rex")
    [b for b in at.button if b.label == "Add pet"][0].click().run()
    assert not at.exception
    assert "### Rex" in all_markdown(at)
    assert not at.chat_input[0].disabled


def test_agent_proposal_is_shown_and_add_all_saves_it(data_file, monkeypatch):
    save(data_file, pack())
    at = run_app()
    ask(at, monkeypatch, canned_result(Task("Morning walk", "Mochi", 20, 2, at_time(7)),
                                       Task("Breakfast", "Luna", 10, 3, at_time(8))))
    assert "Morning walk" in all_markdown(at)
    assert [b for b in at.button if b.label == "Add all 2 to today"]
    at.button(key="ai_apply_1").click().run()
    assert not at.exception
    saved = Owner.load_from_json(data_file)
    assert sorted(t.title for t in saved.get_all_tasks()) == ["Breakfast", "Morning walk"]


def test_not_now_adds_nothing(data_file, monkeypatch):
    save(data_file, pack())
    at = run_app()
    ask(at, monkeypatch, canned_result(Task("Morning walk", "Mochi", 20, 2, at_time(7))))
    at.button(key="ai_discard_1").click().run()
    assert not at.exception
    assert Owner.load_from_json(data_file).get_all_tasks() == []


def test_failed_agent_result_shows_the_error(data_file, monkeypatch):
    save(data_file, pack())
    at = run_app()
    ask(at, monkeypatch, AgentResult(ok=False, summary="The AI service could not be reached.", problems=["bad key"]))
    assert any("could not be reached" in e.value for e in at.error)
    assert not [b for b in at.button if b.label.startswith("Add all")]


def test_user_text_is_escaped_in_the_walkthrough(data_file):
    save(data_file, pack(Task("<script>alert(1)</script>", "Mochi", 10, 2, at_time(9))))
    at = run_app()
    text = all_markdown(at)
    assert "&lt;script&gt;" in text
    assert "<script>alert" not in text


def test_overlapping_tasks_get_an_overlap_chip(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9)), Task("Bath", "Mochi", 30, 2, at_time(9, 15))))
    at = run_app()
    assert "Overlap" in all_markdown(at)


def test_build_plan_button_opens_the_dialog_without_errors(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app()
    at.button(key="build_plan").click().run()
    assert not at.exception


def test_every_pet_card_opens_its_own_schedule(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app()
    for key in ("pet_open_0", "pet_open_1"):  # Mochi (has a task) and Luna (has none)
        at.button(key=key).click().run()
        assert not at.exception, at.exception
