"""Smoke tests for the Streamlit UI (Today / The pack tabs), run headless with AppTest.

The agent is replaced by a canned result, and .env loading is switched off, so these tests need no
API key and no network. Each test uses its own temporary data file.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ai_planner
import notifications
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


def run_app(page: str = "Today") -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["page"] = page
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
    at = run_app("The pack")
    [w for w in at.text_input if w.label == "Pet name"][0].set_value("Rex")
    [b for b in at.button if b.label == "Add pet"][0].click().run()
    assert not at.exception
    at.session_state["page"] = "Today"
    at.run()
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
    # Only blocks that allow raw HTML are a risk; the rest is shown as plain text by Streamlit.
    html_blocks = chr(10).join(m.value for m in at.markdown if m.proto.allow_html)
    assert "&lt;script&gt;" in html_blocks
    assert "<script>alert" not in html_blocks


def test_overlapping_tasks_get_an_overlap_chip(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9)), Task("Bath", "Mochi", 30, 2, at_time(9, 15))))
    at = run_app()
    assert "Overlap" in all_markdown(at)


def test_view_full_schedule_opens_the_schedule_page_on_today(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app()
    at.button(key="build_plan").click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Schedule"
    assert at.title[0].value == "Full schedule"
    assert "Walk" in all_markdown(at)


def test_every_pet_card_opens_the_schedule_filtered_to_that_pet(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    for key, pet in (("pet_open_0", "Mochi"), ("pet_open_1", "Luna")):
        at = run_app()
        at.button(key=key).click().run()
        assert not at.exception, at.exception
        assert at.session_state["page"] == "Schedule"
        assert at.selectbox(key="sched_pet").value == pet


def test_add_tasks_button_goes_to_the_pack_with_the_task_form_first(data_file):
    save(data_file, pack())
    at = run_app()
    at.button(key="add_tasks").click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "The pack"
    headings = [h.value for h in at.subheader]
    assert headings.index("Add a task") < headings.index("Add a pet") < headings.index("Owner")


def test_add_tasks_with_no_pets_puts_the_pet_form_first(data_file):
    save(data_file, [])
    at = run_app()
    at.button(key="add_tasks").click().run()
    headings = [h.value for h in at.subheader]
    assert headings.index("Add a pet") < headings.index("Add a task")


def test_choosing_the_pack_from_the_nav_uses_the_normal_order(data_file):
    save(data_file, pack())
    at = run_app("The pack")
    headings = [h.value for h in at.subheader]
    assert headings.index("Owner") < headings.index("Add a pet") < headings.index("Add a task")


def test_a_day_with_no_tasks_says_so_clearly(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app("Schedule")
    at.session_state["sched_day"] = date.today() + timedelta(days=3)
    at.run()
    assert not at.exception, at.exception
    text = all_markdown(at)
    assert "Nothing scheduled for" in text
    assert [b for b in at.button if b.label == "Add tasks"]
    assert "Walk" not in text


def test_empty_day_offers_a_jump_to_the_next_day_with_tasks(data_file):
    later = datetime.combine(date.today() + timedelta(days=2), time(10))
    save(data_file, pack(Task("Vet visit", "Mochi", 45, 3, later)))
    at = run_app("Schedule")
    jump = at.button(key="sched_jump")
    assert f"{later:%a %b %d}" in jump.label
    jump.click().run()
    assert not at.exception, at.exception
    assert "Vet visit" in all_markdown(at)
    assert "Nothing scheduled" not in all_markdown(at)


def test_schedule_filters_by_pet_and_shows_only_that_days_tasks(data_file):
    tomorrow = datetime.combine(date.today() + timedelta(days=1), time(8))
    mochi = Pet(name="Mochi", species="dog", age=3)
    luna = Pet(name="Luna", species="cat", age=6)
    mochi.add_task(Task("Mochi walk", "Mochi", 20, 2, at_time(7)))
    luna.add_task(Task("Luna pill", "Luna", 5, 3, at_time(8)))
    luna.add_task(Task("Luna brushing", "Luna", 10, 1, tomorrow))
    save(data_file, [mochi, luna])
    at = run_app("Schedule")
    text = all_markdown(at)
    assert "Mochi walk" in text and "Luna pill" in text and "Luna brushing" not in text
    at.selectbox(key="sched_pet").select("Luna").run()
    text = all_markdown(at)
    assert "Luna pill" in text and "Mochi walk" not in text
    at.button(key="sched_next").click().run()
    assert "Luna brushing" in all_markdown(at)


def test_schedule_prev_and_today_buttons_move_the_day(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app("Schedule")
    at.button(key="sched_prev").click().run()
    assert at.session_state["sched_day"] == date.today() - timedelta(days=1)
    assert "Nothing scheduled for" in all_markdown(at)
    at.button(key="sched_today").click().run()
    assert at.session_state["sched_day"] == date.today()
    assert "Walk" in all_markdown(at)


def test_schedule_with_no_pets_points_to_adding_one(data_file):
    save(data_file, [])
    at = run_app("Schedule")
    assert not at.exception
    assert "No pets yet" in all_markdown(at)


def test_schedule_marks_overlaps_and_escapes_text(data_file):
    save(data_file, pack(Task("<b>Walk</b>", "Mochi", 30, 2, at_time(9)), Task("Bath", "Mochi", 30, 2, at_time(9, 15))))
    at = run_app("Schedule")
    text = all_markdown(at)
    assert "Overlap" in text
    # Only blocks that allow raw HTML are a risk; the rest is shown as plain text by Streamlit.
    html_blocks = "\n".join(m.value for m in at.markdown if m.proto.allow_html)
    assert "&lt;b&gt;Walk" in html_blocks and "<b>Walk" not in html_blocks


def test_new_task_form_can_pick_a_date(data_file):
    save(data_file, pack())
    at = run_app("The pack")
    target = date.today() + timedelta(days=4)
    at.date_input(key="new_task_day").set_value(target)
    [w for w in at.text_input if w.label == "Task title"][0].set_value("Dentist")
    [b for b in at.button if b.label == "Add task"][0].click().run()
    assert not at.exception, at.exception
    saved = Owner.load_from_json(data_file)
    assert [t.scheduled_time.date() for t in saved.get_all_tasks()] == [target]


def test_removing_a_pet_needs_confirmation_and_deletes_the_pet_and_its_tasks(data_file):
    save(data_file, pack(Task("Walk", "Mochi", 30, 2, at_time(9))))
    at = run_app("The pack")
    assert at.button(key="remove_pet_button").disabled  # nothing happens until the owner confirms
    at.checkbox(key="remove_pet_confirm_Mochi").check().run()
    at.button(key="remove_pet_button").click().run()
    assert not at.exception, at.exception
    saved = Owner.load_from_json(data_file)
    assert [p.name for p in saved.pets] == ["Luna"]
    assert saved.get_all_tasks() == []


def test_removing_the_last_pet_returns_to_the_welcome_state(data_file):
    save(data_file, [Pet(name="Rex", species="dog", age=2)])
    at = run_app("The pack")
    at.checkbox(key="remove_pet_confirm_Rex").check().run()
    at.button(key="remove_pet_button").click().run()
    assert not at.exception, at.exception
    at.session_state["page"] = "Today"
    at.run()
    assert "let's meet your pack" in at.title[0].value
    assert Owner.load_from_json(data_file).pets == []


# --- reminders -------------------------------------------------------------------------------
def fake_clock(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(notifications, "current_time", lambda: when)


def toasts(at: AppTest) -> list[str]:
    return [t.value for t in at.toast]


def test_toast_five_minutes_before_a_task_starts(data_file, monkeypatch):
    save(data_file, pack(Task("Morning walk", "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 55))
    at = run_app()
    assert any("Morning walk in 5 minutes" in t for t in toasts(at)), toasts(at)


def test_toast_when_the_task_is_due_and_it_is_not_repeated_on_the_next_run(data_file, monkeypatch):
    save(data_file, pack(Task("Medication", "Luna", 5, 3, at_time(8))))
    fake_clock(monkeypatch, at_time(8, 0))
    at = run_app()
    assert any("Time for Medication" in t for t in toasts(at))
    at.run()
    assert not any("Time for Medication" in t for t in toasts(at)), "the same reminder must not repeat"


def test_both_reminders_fire_for_one_task_over_time(data_file, monkeypatch):
    save(data_file, pack(Task("Walk", "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 56))
    at = run_app()
    assert any("Walk in 4 minutes" in t for t in toasts(at))
    fake_clock(monkeypatch, at_time(8, 1))
    at.run()
    assert any("Time for Walk" in t for t in toasts(at))


def test_no_toast_for_far_away_or_completed_tasks(data_file, monkeypatch):
    done = Task("Done walk", "Mochi", 20, 2, at_time(8), completed=True)
    save(data_file, pack(done, Task("Later", "Mochi", 20, 2, at_time(15))))
    fake_clock(monkeypatch, at_time(7, 57))
    at = run_app()
    assert toasts(at) == []


def test_reminders_can_be_switched_off(data_file, monkeypatch):
    save(data_file, pack(Task("Walk", "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 57))
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["reminders_on"] = False
    at.run()
    assert not at.exception, at.exception
    assert toasts(at) == []


def test_reminders_also_fire_on_other_pages(data_file, monkeypatch):
    save(data_file, pack(Task("Walk", "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 57))
    at = run_app("The pack")
    assert any("Walk in 3 minutes" in t for t in toasts(at))


def test_up_next_line_shows_the_next_task_and_the_wait(data_file, monkeypatch):
    save(data_file, pack(Task("Walk", "Mochi", 20, 2, at_time(8)), Task("Dinner", "Luna", 10, 3, at_time(18))))
    fake_clock(monkeypatch, at_time(7, 30))
    at = run_app()
    assert "**Up next:** Walk (Mochi), in 30 min" in all_markdown(at)


def test_up_next_line_when_nothing_is_coming(data_file, monkeypatch):
    save(data_file, pack())
    fake_clock(monkeypatch, at_time(7, 30))
    at = run_app()
    assert "nothing coming up" in all_markdown(at)


def test_notification_markers_escape_user_text(data_file, monkeypatch):
    save(data_file, pack(Task('</script><b x="1">x</b>', "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 57))
    at = run_app()
    markers = [h.proto.body for h in at.get("html") if 'class="pawpal-alert"' in h.proto.body]
    assert len(markers) == 1, "one hidden marker per reminder"
    assert "</script><b" not in markers[0] and '<b x="1">' not in markers[0]
    assert "&lt;/script&gt;" in markers[0]


def test_the_notification_listener_script_is_installed_once_and_has_no_user_text(data_file, monkeypatch):
    save(data_file, pack(Task("Secret title", "Mochi", 20, 2, at_time(8))))
    fake_clock(monkeypatch, at_time(7, 57))
    at = run_app()
    listeners = [h.proto.body for h in at.get("html") if "__pawpalNotifyInstalled" in h.proto.body]
    assert len(listeners) == 1
    assert "Secret title" not in listeners[0]
