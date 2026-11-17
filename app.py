import html
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

import theme
from ai_planner import run_agent
from formatting import priority_badge, task_emoji
from pawpal_system import Owner, Pet, Scheduler, Task

# Read ANTHROPIC_API_KEY from a .env file next to this script, if there is one.
# The file wins over any older ANTHROPIC_API_KEY already set in Windows.
load_dotenv(Path(__file__).with_name(".env"), override=True)

# Everything the AI agent does is logged here (and by pawpal.ai to the console).
logging.basicConfig(
    filename=Path(__file__).with_name("pawpal_ai.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)

PRIORITY_VALUES = {"low": 1, "medium": 2, "high": 3}
PRIORITY_LABELS = {value: label for label, value in PRIORITY_VALUES.items()}

# Where pets and tasks are remembered between runs (set PAWPAL_DATA_FILE to use another file).
DATA_FILE = Path(os.environ.get("PAWPAL_DATA_FILE", Path(__file__).with_name("data.json")))

MAX_CHAT_TURNS = 10
CHAT_HEIGHT = 420  # pixels; the chat scrolls inside this height


# --- small helpers ---------------------------------------------------------------------
def show_conflicts(warnings: list[str], suggestions: list[str] = ()) -> None:
    """Show every conflict in one box: what is wrong, which tasks, and what to do about it."""
    if not warnings:
        return
    plural = "s" if len(warnings) > 1 else ""
    details = "\n".join(f"- {w.removeprefix('Warning: ')}" for w in warnings)
    message = (
        f"**{len(warnings)} scheduling conflict{plural}.** You can't do two things at once, "
        f"so change one task in each pair to a different time, or remove it, using "
        f"**Edit or remove a task**.\n\n{details}"
    )
    if suggestions:
        message += "\n\n**Suggestions:**\n" + "\n".join(f"- {s}" for s in suggestions)
    st.warning(message)


def conflict_suggestions(scheduler: Scheduler, conflicts: list[tuple[Task, Task]]) -> list[str]:
    """One "move it to HH:MM" line for the second task of every conflicting pair."""
    suggestions = []
    for _, clashing in conflicts:
        slot = scheduler.find_next_free_slot(
            clashing.duration_minutes,
            day=clashing.scheduled_time.date(),
            after=clashing.scheduled_time,
            ignore=clashing,
        )
        if slot is None:
            suggestions.append(
                f"No free {clashing.duration_minutes}-minute slot is left for '{clashing.title}' "
                f"on {clashing.scheduled_time:%A}."
            )
        else:
            suggestions.append(
                f"Move '{clashing.title}' ({clashing.pet_name}) to {slot:%H:%M}, "
                f"the next free {clashing.duration_minutes} minutes."
            )
    return suggestions


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def age_text(age: int) -> str:
    return "under 1 year" if age == 0 else plural(age, "year")


def pet_index(owner: Owner, pet_name: str) -> int:
    """Position of a pet in the owner's list, so its chip matches its card color."""
    return next((i for i, p in enumerate(owner.pets) if p.name == pet_name), 0)


def tasks_today(owner: Owner) -> list[Task]:
    """Pending tasks scheduled for today, in time order."""
    today = date.today()
    pending = owner.filter_tasks(completed=False)
    return Scheduler.sort_by_time([t for t in pending if t.scheduled_time.date() == today])


SCHEDULE_NOTE = (
    "A repeating task appears on its next day once you mark the current one complete, "
    "so days further ahead can look empty."
)


def go(page: str, scroll: str = "top", **state) -> None:
    """Button callback: set some session values, then show another page (runs before the next rerun).

    `scroll` is "top" or the key of a container to bring into view; Streamlit would otherwise keep the
    old scroll position, leaving the owner halfway down the new page.
    """
    for key, value in state.items():
        st.session_state[key] = value
    st.session_state["_scroll"] = scroll
    st.session_state.page = page
    st.session_state["_last_page"] = page
    if page != "The pack":
        st.session_state.pop("pack_focus", None)


def shift_day(days: int) -> None:
    st.session_state.sched_day = st.session_state.sched_day + timedelta(days=days)


def set_day(day: date) -> None:
    st.session_state.sched_day = day


def schedule_row_html(task: Task, overlapping: set[int]) -> str:
    """One task as a display-only row: time range, title, pet, status. User text is escaped."""
    end = task.scheduled_time + timedelta(minutes=task.duration_minutes)
    repeat = "" if task.frequency == "once" else f" · repeats {task.frequency}"
    chips = theme.pet_chip_html(task.pet_name, pet_index(owner, task.pet_name))
    chips += " " + theme.priority_chip_html(task.priority)
    if task.completed:
        chips += " " + theme.chip_html("Done", theme.MINT)
    if id(task) in overlapping:
        chips += " " + theme.chip_html("Overlap", theme.PINK)
    faded = "opacity:.65;" if task.completed else ""
    return (
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;'
        f'background:#FFFFFF;border:2px solid {theme.INK};border-radius:16px;padding:10px 14px;'
        f'margin-bottom:8px;color:{theme.INK};{faded}">'
        f'<div><strong>{task.scheduled_time:%H:%M}&ndash;{end:%H:%M}</strong> &nbsp; {html.escape(task.title)}'
        f'<div style="font-size:13px;color:{theme.MUTED}">{task.duration_minutes} min{repeat}</div></div>'
        f'<div>{chips}</div></div>'
    )


def render_schedule() -> None:
    """One day at a time, for all pets or one pet. A day with nothing on it says so clearly."""
    st.session_state.setdefault("sched_day", date.today())
    pet_options = ["All pets"] + [p.name for p in owner.pets]
    if st.session_state.get("sched_pet") not in pet_options:
        st.session_state.sched_pet = "All pets"

    st.title("Full schedule")
    pet_col, prev_col, day_col, next_col, today_col = st.columns([2, 1, 2, 1, 1], vertical_alignment="bottom")
    pet_choice = pet_col.selectbox("Pet", pet_options, key="sched_pet")
    prev_col.button("← Prev", key="sched_prev", on_click=shift_day, args=(-1,), width="stretch")
    day = day_col.date_input("Day", key="sched_day")
    next_col.button("Next →", key="sched_next", on_click=shift_day, args=(1,), width="stretch")
    today_col.button("Today", key="sched_today", on_click=set_day, args=(date.today(),), width="stretch")

    everyone = pet_choice == "All pets"
    day_all = [t for t in owner.get_all_tasks() if t.scheduled_time.date() == day]
    shown = Scheduler.sort_by_time([t for t in day_all if everyone or t.pet_name == pet_choice])
    label = f"{day:%A, %b %d}" + (" (today)" if day == date.today() else "")
    who = "" if everyone else f" for {pet_choice}"

    if not owner.pets:
        with st.container(key="sched_empty"):
            st.markdown("### No pets yet")
            st.write("Add a pet first, then you can schedule tasks for them.")
            st.button("Add a pet", key="sched_add_pet", type="primary", on_click=go, args=("The pack",))
        return

    if not shown:
        later = sorted(
            {
                t.scheduled_time.date()
                for t in owner.get_all_tasks()
                if t.scheduled_time.date() > day and (everyone or t.pet_name == pet_choice)
            }
        )
        with st.container(key="sched_empty"):
            st.markdown(f"### Nothing scheduled for {label}{who}")
            st.write(f"There are no tasks{who} on this day. Pick another day above, or add some.")
            add_col, jump_col, _ = st.columns([1.2, 3, 2])
            add_col.button(
                "Add tasks", key="sched_add_empty", type="primary", on_click=go, args=("The pack",),
                kwargs={"pack_focus": "tasks", "scroll": "add_task_card"},
            )
            if later:
                jump_col.button(
                    f"Jump to the next day with tasks ({later[0]:%a %b %d})", key="sched_jump",
                    on_click=set_day, args=(later[0],),
                )
            else:
                st.caption(f"{'Your pets have' if everyone else pet_choice + ' has'} no tasks on any later day either.")
        st.caption(SCHEDULE_NOTE)
        return

    pending = [t for t in shown if not t.completed]
    used = sum(t.duration_minutes for t in pending)
    budget = f"{used} of your {owner.available_minutes} minutes" if everyone else f"{used} min"
    st.markdown(f"#### {label}{who}")
    summary_col, add_col = st.columns([4, 1], vertical_alignment="center")
    summary_col.caption(f"{plural(len(shown), 'task')} · {len(pending)} to do · {budget}")
    add_col.button(
        "Add tasks", key="sched_add", type="primary", on_click=go, args=("The pack",),
        kwargs={"pack_focus": "tasks", "scroll": "add_task_card"}, width="stretch",
    )

    day_pending = [t for t in day_all if not t.completed]
    conflicts = scheduler.detect_conflicts(day_pending)
    overlapping = {id(t) for pair in conflicts for t in pair}
    for task in shown:
        st.markdown(schedule_row_html(task, overlapping), unsafe_allow_html=True)

    if conflicts:
        with st.container(key="ai_note_sched"):
            lines = [f"- {w.removeprefix('Warning: ')}" for w in scheduler.conflict_warnings(day_pending)]
            lines += [f"- {text}" for text in conflict_suggestions(scheduler, conflicts)]
            st.markdown("**Overlapping tasks**\n" + "\n".join(lines))
    if day_pending:
        with st.expander("Why this plan? (all pets, within your available minutes)"):
            st.text(scheduler.explain_plan(scheduler.generate_plan(day)))
    st.caption(SCHEDULE_NOTE)


# --- page setup -------------------------------------------------------------------------
st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")
theme.inject_css()

# The "vault": load the saved Owner (or start a new one) once per session and reuse it.
if "owner" not in st.session_state:
    loaded = None
    try:
        loaded = Owner.load_from_json(DATA_FILE)
    except ValueError:
        # Keep the unreadable file as a backup instead of overwriting it.
        os.replace(DATA_FILE, DATA_FILE.with_name(DATA_FILE.name + ".bak"))
        st.session_state.load_warning = (
            f"{DATA_FILE.name} could not be read, so PawPal+ started fresh. "
            f"The old file was kept as {DATA_FILE.name}.bak."
        )
    st.session_state.owner = loaded if loaded is not None else Owner(name="Jordan", available_minutes=90)
owner: Owner = st.session_state.owner

if "load_warning" in st.session_state:
    st.warning(st.session_state.pop("load_warning"))
if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"), icon=":material/check_circle:")

st.markdown(theme.logo_html(), unsafe_allow_html=True)

PAGES = ["Today", "Schedule", "The pack"]
st.session_state.setdefault("page", "Today")


def nav_changed() -> None:
    """The owner picked a page from the bar: forget any "jump to add tasks" request, and never end up on no page."""
    st.session_state.pop("pack_focus", None)
    if st.session_state.get("page") is None:  # clicking the selected pill again deselects it
        st.session_state.page = st.session_state.get("_last_page", "Today")


st.segmented_control("Go to", PAGES, key="page", label_visibility="collapsed", on_change=nav_changed)
page = st.session_state.page or "Today"
st.session_state["_last_page"] = page

scheduler = Scheduler(owner)

# --- The pack page ------------------------------------------------------------
def pack_owner() -> None:
    with st.container(border=True):
        st.subheader("Owner")
        owner.name = st.text_input("Owner name", value=owner.name)
        owner.available_minutes = int(
            st.number_input("Minutes available today", min_value=1, max_value=720, value=owner.available_minutes)
        )


def pack_add_pet() -> None:
    with st.container(border=True):
        st.subheader("Add a pet")
        with st.form("add_pet_form", clear_on_submit=True):
            new_pet_name = st.text_input("Pet name")
            new_species = st.selectbox("Species", ["dog", "cat", "other"])
            new_age = st.number_input("Age", min_value=0, max_value=40, value=1)
            pet_submitted = st.form_submit_button("Add pet")

        if pet_submitted:
            cleaned_name = new_pet_name.strip()
            if not cleaned_name:
                st.error("Please enter a pet name.")
            elif cleaned_name in [pet.name for pet in owner.pets]:
                st.error(f"You already have a pet named {cleaned_name}.")
            else:
                owner.add_pet(Pet(name=cleaned_name, species=new_species, age=int(new_age)))
                st.success(f"Added {cleaned_name}.")

        if owner.pets:
            st.table(
                [{"name": p.name, "species": p.species, "age": p.age, "tasks": len(p.tasks)} for p in owner.pets]
            )
            with st.expander("Remove a pet"):
                doomed_name = st.selectbox("Pet to remove", [p.name for p in owner.pets], key="remove_pet_pick")
                doomed = next(p for p in owner.pets if p.name == doomed_name)
                confirmed = st.checkbox(
                    f"Yes, remove {doomed.name} and their {plural(len(doomed.tasks), 'task')} for good",
                    key=f"remove_pet_confirm_{doomed.name}",
                )
                if st.button("Remove pet", disabled=not confirmed, key="remove_pet_button"):
                    owner.remove_pet(doomed)
                    st.session_state.flash = f"Removed {doomed.name} and their tasks."
                    st.rerun()  # redraw so no widget above still lists the removed pet
        else:
            st.info("No pets yet. Add one above.")


def pack_add_task() -> None:
    with st.container(border=True, key="add_task_card"):
        st.subheader("Add a task")
        if not owner.pets:
            st.info("Add a pet first, then you can give it tasks.")
        else:
            with st.form("add_task_form", clear_on_submit=True):
                chosen_pet_name = st.selectbox("Pet", [pet.name for pet in owner.pets])
                col1, col2, col3 = st.columns(3)
                with col1:
                    task_title = st.text_input("Task title", value="Morning walk")
                with col2:
                    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
                with col3:
                    priority = st.selectbox("Priority", list(PRIORITY_VALUES), index=2)
                col4, col5, col6 = st.columns(3)
                with col4:
                    task_day = st.date_input("Date", value=date.today(), key="new_task_day")
                with col5:
                    start_time = st.time_input("Start time", value=datetime(2000, 1, 1, 8, 0).time())
                with col6:
                    frequency = st.selectbox("Repeats", ["once", "daily", "weekly"])
                task_submitted = st.form_submit_button("Add task")

            if task_submitted:
                if not task_title.strip():
                    st.error("Please enter a task title.")
                else:
                    pet = next(p for p in owner.pets if p.name == chosen_pet_name)
                    new_task = Task(
                        title=task_title.strip(),
                        pet_name=pet.name,
                        duration_minutes=int(duration),
                        priority=PRIORITY_VALUES[priority],
                        scheduled_time=datetime.combine(task_day, start_time),
                        frequency=frequency,
                    )
                    pet.add_task(new_task)
                    st.success(f"Added '{new_task.title}' for {pet.name}.")


def pack_manage_tasks() -> None:
    with st.container(border=True):
        st.subheader("Manage tasks")
        if not owner.get_all_tasks():
            st.info("No tasks yet. Add one above.")
        else:
            # Completing a task runs before the table below is drawn, so the table shows the result.
            pending = scheduler.sort_by_time(owner.filter_tasks(completed=False))
            with st.expander("Mark a task complete"):
                if not pending:
                    st.write("Everything is done. 🎉")
                else:
                    pick = st.selectbox(
                        "Task",
                        range(len(pending)),
                        format_func=lambda i: (
                            f"{pending[i].pet_name}: {pending[i].title} ({pending[i].scheduled_time:%a %H:%M})"
                        ),
                    )
                    if st.button("Mark complete"):
                        done_task = pending[pick]
                        pet = next(p for p in owner.pets if p.name == done_task.pet_name)
                        count_before = len(pet.tasks)
                        pet.complete_task(done_task)
                        st.success(f"Completed '{done_task.title}' for {pet.name}.")
                        if len(pet.tasks) > count_before:
                            nxt = pet.tasks[-1]
                            st.info(f"It repeats {nxt.frequency}: next one is on {nxt.scheduled_time:%A at %H:%M}.")

            with st.expander("Edit or remove a task"):
                # Stable order (by pet, as added) so the selection doesn't jump when a time is edited.
                every_task = owner.get_all_tasks()
                by_id = {id(t): t for t in every_task}
                # The number makes labels unique, so identical-looking tasks can be told apart.
                labels = {
                    id(t): f"{n}. {t.pet_name}: {t.title} ({t.scheduled_time:%a %H:%M})"
                    for n, t in enumerate(every_task, start=1)
                }
                task_id = st.selectbox("Task to edit", list(by_id), format_func=labels.get)
                task = by_id[task_id]
                edit_pet = next(p for p in owner.pets if p.name == task.pet_name)

                with st.form("edit_task_form"):
                    edit_title = st.text_input("Title", value=task.title, key=f"edit_title_{task_id}")
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        edit_duration = st.number_input(
                            "Duration (minutes)", min_value=1, max_value=240,
                            value=task.duration_minutes, key=f"edit_duration_{task_id}",
                        )
                        edit_time = st.time_input(
                            "Start time", value=task.scheduled_time.time(), key=f"edit_time_{task_id}"
                        )
                    with edit_col2:
                        edit_priority = st.selectbox(
                            "Priority", list(PRIORITY_VALUES), index=task.priority - 1,
                            key=f"edit_priority_{task_id}",
                        )
                        edit_frequency = st.selectbox(
                            "Repeats", ["once", "daily", "weekly"],
                            index=["once", "daily", "weekly"].index(task.frequency),
                            key=f"edit_frequency_{task_id}",
                        )
                    edit_date = st.date_input(
                        "Date", value=task.scheduled_time.date(), key=f"edit_date_{task_id}"
                    )
                    edit_saved = st.form_submit_button("Save changes")

                if edit_saved:
                    if not edit_title.strip():
                        st.error("Please enter a task title.")
                    else:
                        task.title = edit_title.strip()
                        task.duration_minutes = int(edit_duration)
                        task.priority = PRIORITY_VALUES[edit_priority]
                        task.frequency = edit_frequency
                        task.scheduled_time = datetime.combine(edit_date, edit_time)
                        st.success(f"Updated '{task.title}' for {task.pet_name}.")

                if st.button("Remove task"):
                    edit_pet.remove_task(task)
                    st.session_state.flash = f"Removed '{task.title}' from {edit_pet.name}."
                    st.rerun()  # redraw so no widget above still lists the removed task

            # Conflicts come first because they are the thing the owner has to act on.
            pending_conflicts = scheduler.detect_conflicts(owner.filter_tasks(completed=False))
            show_conflicts(scheduler.conflict_warnings(), conflict_suggestions(scheduler, pending_conflicts))
            conflicting = {id(t) for pair in pending_conflicts for t in pair}

            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                pet_filter = st.selectbox("Show pet", ["All"] + [pet.name for pet in owner.pets])
            with filter_col2:
                status_filter = st.selectbox("Show status", ["All", "pending", "done"])
            with filter_col3:
                sort_choice = st.selectbox("Sort by", ["Time", "Priority, then time"])

            shown = owner.filter_tasks(
                pet_name=None if pet_filter == "All" else pet_filter,
                completed={"All": None, "pending": False, "done": True}[status_filter],
            )
            if shown:
                st.table(
                    [
                        {
                            "pet": t.pet_name,
                            "task": f"{task_emoji(t.title)} {t.title}",
                            "start": f"{t.scheduled_time:%a %H:%M}",
                            "minutes": t.duration_minutes,
                            "priority": priority_badge(t.priority),
                            "repeats": t.frequency,
                            "status": "✅ done" if t.completed else "⏳ pending",
                            "conflict": "⚠️ overlap" if id(t) in conflicting else "",
                        }
                        for t in (
                            scheduler.sort_by_priority(shown) if sort_choice != "Time" else scheduler.sort_by_time(shown)
                        )
                    ]
                )
            else:
                st.info("No tasks match that filter.")


def render_pack() -> None:
    """Forms for the owner, pets and tasks. Arriving through "Add tasks" puts the task form first."""
    sections = [pack_owner, pack_add_pet, pack_add_task, pack_manage_tasks]
    if st.session_state.get("pack_focus") == "tasks":
        sections = (
            [pack_add_task, pack_manage_tasks, pack_add_pet, pack_owner]
            if owner.pets
            else [pack_add_pet, pack_add_task, pack_manage_tasks, pack_owner]  # a task needs a pet first
        )
    for section in sections:
        section()


# --- Today tab --------------------------------------------------------------------------
def render_hero() -> None:
    due = tasks_today(owner)
    used = sum(t.duration_minutes for t in due)
    with st.container(key=theme.KEYS["hero"]):
        name = owner.name.strip() or "there"
        if owner.pets:
            st.title(f"Hi {name}, the pack is ready for today.")
        else:
            st.title(f"Hi {name}, let's meet your pack.")
            st.write("Add your first pet in **The pack** tab.")
        st.caption(
            f"{date.today():%A, %b %d} · {plural(len(due), 'task')} today · "
            f"{used} of your {owner.available_minutes} minutes"
        )


def render_pet_cards() -> None:
    if not owner.pets:
        with st.container(key=theme.KEYS["pet_card"].format(i=0)):
            st.markdown(theme.pet_face_html("other"), unsafe_allow_html=True)
            st.markdown("### No pets yet")
            st.caption("Add your first pet in **The pack** tab.")
        return
    due = tasks_today(owner)
    for start in range(0, len(owner.pets), 4):
        group = owner.pets[start:start + 4]
        for offset, col in enumerate(st.columns(len(group))):
            i = start + offset
            pet = group[offset]
            left = sum(1 for t in due if t.pet_name == pet.name)
            with col, st.container(key=theme.KEYS["pet_card"].format(i=i)):
                st.markdown(theme.pet_face_html(pet.species), unsafe_allow_html=True)
                st.markdown(f"### {pet.name}")
                st.caption(f"{pet.species.capitalize()} · {age_text(pet.age)}")
                label = f"{plural(left, 'task')} left today" if left else "Nothing left today"
                st.markdown(theme.chip_html(label), unsafe_allow_html=True)
                st.button(
                    "View schedule", key=f"pet_open_{i}", help=f"Open {pet.name}'s schedule",
                    on_click=go, args=("Schedule",), kwargs={"sched_pet": pet.name, "sched_day": date.today()},
                )


def render_sticker_grid(turn: int, tasks: list[Task]) -> None:
    """The tasks the agent proposes, as small cards in two columns."""
    ordered = Scheduler.sort_by_time(tasks)
    for row_start in range(0, len(ordered), 2):
        for offset, col in enumerate(st.columns(2)):
            if row_start + offset >= len(ordered):
                break
            i = row_start + offset
            task = ordered[i]
            with col, st.container(key=theme.KEYS["task_sticker"].format(turn=turn, i=i)):
                st.markdown(
                    f"**{task.scheduled_time:%H:%M}** &nbsp; " + theme.priority_chip_html(task.priority),
                    unsafe_allow_html=True,
                )
                repeat = "" if task.frequency == "once" else f" · repeats {task.frequency}"
                st.markdown(f"{task.title} · {task.duration_minutes} min{repeat}")
                st.markdown(
                    theme.pet_chip_html(task.pet_name, pet_index(owner, task.pet_name)), unsafe_allow_html=True
                )


def render_assistant_turn(turn: int, item: dict, is_latest: bool) -> None:
    result = item["result"]
    with st.chat_message("assistant", avatar=":material/pets:"):
        if not result.ok:
            st.error(f"I couldn't finish that: {result.summary}")
            for problem in result.problems:
                st.write(f"- {problem}")
        else:
            st.markdown(result.summary)
            if result.added:
                render_sticker_grid(turn, result.added)
        with st.expander("How PawPal planned this"):
            st.write("\n".join(f"- {s}" for s in result.steps) or "No steps were taken.")

        if result.ok and result.added:
            if item["status"] == "added":
                st.caption("Added to your schedule.")
            elif item["status"] == "dismissed":
                st.caption("Not added.")
            elif is_latest:
                n = len(result.added)
                day = result.day
                label = f"Add all {n} to today"
                if day is not None and day != date.today():
                    label = f"Add all {n} to {day:%a %b %d}"
                apply_col, skip_col, _ = st.columns([2, 1, 2])
                if apply_col.button(label, type="primary", key=f"ai_apply_{turn}"):
                    count = result.commit_to(owner)
                    item["status"] = "added"
                    st.session_state.flash = f"Added {plural(count, 'task')} to your schedule."
                    owner.save_to_json(DATA_FILE)
                    st.rerun()
                if skip_col.button("Not now", key=f"ai_discard_{turn}"):
                    item["status"] = "dismissed"
                    st.rerun()


def render_chat() -> None:
    chat: list[dict] = st.session_state.setdefault("chat", [])
    with st.container(key=theme.KEYS["chat_card"]):
        st.subheader("Ask PawPal")
        # A fixed-height box: the conversation scrolls inside it instead of growing the page.
        messages = st.container(height=CHAT_HEIGHT, border=False, key="chat_messages")
        with messages:
            if not chat:
                with st.chat_message("assistant", avatar=":material/pets:"):
                    st.markdown(
                        "Hi! Tell me what your pets need, like *“Rex needs two walks and his flea medicine”* "
                        "or *“Luna needs her pill with breakfast.”* I'll check your schedule and available "
                        "time before suggesting anything, and nothing is saved until you add it."
                    )
            last_assistant = max((i for i, item in enumerate(chat) if item["role"] == "assistant"), default=-1)
            for turn, item in enumerate(chat):
                if item["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(item["text"])
                else:
                    render_assistant_turn(turn, item, is_latest=turn == last_assistant)

        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        can_ask = bool(owner.pets) and has_key
        day_col, _ = st.columns([1, 2])
        ai_day = day_col.date_input("Plan for", value=date.today(), key="ai_day")
        if not owner.pets:
            placeholder = "Add a pet first"
        elif not has_key:
            placeholder = "Add your Anthropic API key to .env to chat"
        else:
            placeholder = "Ask about walks, meals, meds, vet visits…"
        prompt = st.chat_input(placeholder, key="ai_prompt", max_chars=1000, disabled=not can_ask)
        if owner.pets and not has_key:
            st.caption("Set ANTHROPIC_API_KEY in a .env file next to app.py, then restart. See the README setup steps.")
        st.caption(
            "PawPal is a scheduling helper, not a veterinarian: check feeding and medication details with your "
            "vet. For emergencies, call your vet or an emergency clinic right away."
        )

        if prompt:
            for item in chat:
                if item["role"] == "assistant" and item["status"] == "pending":
                    item["status"] = "dismissed"
            chat.append({"role": "user", "text": prompt})
            with messages:  # show the new message and the spinner inside the scrolling box
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.spinner("Planning, checking, and revising..."):
                    result = run_agent(owner, prompt, ai_day)
            chat.append({"role": "assistant", "result": result, "status": "pending"})
            del chat[:-MAX_CHAT_TURNS]
            st.rerun()


def render_walkthrough() -> None:
    due = tasks_today(owner)
    all_pending = owner.filter_tasks(completed=False)
    conflicts = scheduler.detect_conflicts(all_pending)
    overlapping = {id(t) for pair in conflicts for t in pair}
    with st.container(key=theme.KEYS["walkthrough"]):
        st.subheader("Today's walk-through")
        if not due:
            st.markdown("Nothing planned yet. Ask PawPal or add a task in **The pack**.")
        for task in due:
            repeat = "" if task.frequency == "once" else f" · {task.frequency}"
            overlap = " " + theme.chip_html("Overlap", theme.PINK) if id(task) in overlapping else ""
            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;'
                f'background:#FFFFFF;border:2px solid {theme.INK};border-radius:16px;padding:8px 12px;'
                f'margin-bottom:8px;color:{theme.INK}">'
                f'<div><strong>{task.scheduled_time:%H:%M}</strong> &nbsp; {html.escape(task.title)}'
                f'<div style="font-size:13px;color:{theme.MUTED}">{task.duration_minutes} min{repeat}</div></div>'
                f'<div>{theme.pet_chip_html(task.pet_name, pet_index(owner, task.pet_name))}{overlap}</div></div>',
                unsafe_allow_html=True,
            )
        if conflicts:
            with st.container(key="ai_note_walk"):
                lines = [f"- {w.removeprefix('Warning: ')}" for w in scheduler.conflict_warnings()]
                lines += [f"- {s}" for s in conflict_suggestions(scheduler, conflicts)]
                st.markdown("**Overlapping tasks**\n" + "\n".join(lines))
        schedule_col, add_col = st.columns([3, 2])
        schedule_col.button(
            "View full schedule", key=theme.KEYS["build_plan"], width="stretch", on_click=go,
            args=("Schedule",), kwargs={"sched_pet": "All pets", "sched_day": date.today()},
        )
        add_col.button(
            "Add tasks", key="add_tasks", width="stretch", on_click=go, args=("The pack",),
            kwargs={"pack_focus": "tasks", "scroll": "add_task_card"},
        )


def render_today() -> None:
    render_hero()
    render_pet_cards()
    chat_col, walk_col = st.columns([1.9, 1], gap="large")
    with chat_col:
        render_chat()
    with walk_col:
        render_walkthrough()


{"Today": render_today, "Schedule": render_schedule, "The pack": render_pack}[page]()

scroll_target = st.session_state.pop("_scroll", None)
if scroll_target:
    # A zero-height script frame that scrolls the main page (it can reach the parent document).
    script = (
        "const doc = window.parent.document;"
        "const go = () => { const main = doc.querySelector('[data-testid=\"stMain\"]');"
        f"const target = {scroll_target!r} === 'top' ? null : doc.querySelector('.st-key-{scroll_target}');"
        "if (target) { target.style.scrollMarginTop = '80px'; target.scrollIntoView({block: 'start'}); }"
        "else if (main) { main.scrollTo(0, 0); } };"
        "go(); setTimeout(go, 150); setTimeout(go, 500);"
    )
    components.html(f"<script>{script}</script>", height=0)

st.caption(
    "PawPal+ plans routine care only. If your pet seems unwell or hurt, call your vet or an emergency clinic."
)

# Save after every interaction so the next run picks up where this one left off.
try:
    owner.save_to_json(DATA_FILE)
except OSError as error:
    st.warning(f"Your changes could not be saved to {DATA_FILE.name}: {error}")
