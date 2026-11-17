# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

This documents the two challenge features, which I gave to the agent as multi-step changes.

**What task did you give the agent?**

- **Challenge 1 (advanced algorithm):** add a third algorithmic capability beyond the basics, such as a "next available slot" finder.
- **Challenge 2 (data persistence):** make PawPal+ remember pets and tasks between runs by saving them to `data.json`, with `save_to_json` and `load_from_json` methods in `pawpal_system.py`, and explain the persistence workflow and the modified files in the README.
- I also asked a short question along the way: how to handle JSON serialization of complex objects with a library like marshmallow or a custom dictionary conversion.

**What did the agent do?**

1. **Planned the design before editing.** It chose `Scheduler.find_next_free_slot()` for Challenge 1 and `to_dict` / `from_dict` on each class plus `Owner.save_to_json()` / `Owner.load_from_json()` for Challenge 2.
2. **Wrote the algorithm** in `pawpal_system.py`: a sweep over the day's pending tasks in time order that returns the first gap long enough for the task, within 06:00 to 22:00, with an `after` limit and an `ignore` option.
3. **Wrote the persistence code** in `pawpal_system.py`: ISO-string datetimes, type checking on load, a safe write through a temporary file, `None` for a missing file, and a clear `ValueError` for a damaged one.
4. **Connected the UI** in `app.py`: load the saved owner at startup, save after every interaction, back up an unreadable file as `data.json.bak`, and show the free-slot suggestion inside the conflict warning.
5. **Wrote 15 new tests** in `tests/test_pawpal.py` (6 for the free slot, 9 for saving and loading), bringing the suite from 49 to 64 passing tests.
6. **Updated the docs and config:** `README.md` (features, a "Next available slot" section, a "Data persistence" section with the workflow and modified files, new test output), `diagrams/uml.mmd` and `diagrams/uml_final.mmd`, `reflection.md` (test counts), and `.gitignore` (the saved data files).
7. **Ran everything it changed:** pytest after each step, and a headless run of the Streamlit app that added data, started a brand new session to confirm it was remembered, and started with a corrupt file to confirm it was backed up.

**Files modified:** `pawpal_system.py`, `app.py`, `tests/test_pawpal.py`, `README.md`, `diagrams/uml.mmd`, `diagrams/uml_final.mmd`, `reflection.md`, `.gitignore`, and this file.

**What did you have to verify or fix manually?**

Things the agent got wrong or that needed review, and how they were handled:

- **Tests could have overwritten real data.** Driving the app in a test would have written to the real `data.json`. The app now reads a `PAWPAL_DATA_FILE` environment variable, and the agent's tests used a temporary file.
- **A Mermaid marker it couldn't check.** The agent first marked class methods in the UML with `$`, then removed it because it could not render the diagram to confirm it works, and used a comment instead. The diagram should be rendered in the Mermaid Live Editor to confirm.
- **Docs that went stale.** The test counts in the README and reflection had to be updated, and the README's example JSON was shortened, so it now says the real file is laid out differently.
- **Review I still own.** I read each change before accepting it, ran the app myself, and decided when to commit and push. Any edits I make by hand are my own to add here.

**Challenges 3 and 4 (priority scheduling and output formatting).** I asked the agent to add priority-first scheduling and friendlier output. It added a `Priority` enum (Low, Medium, High) and `Scheduler.sort_by_priority()` in `pawpal_system.py`, split `plan_notes()` out of `explain_plan()` so a table can sit above the notes, and wrote a new `formatting.py` (color-coded badges, task emojis, `tabulate` tables). It then rewired `main.py` (new `--minutes` option, tables, a priority view) and `app.py` (shared badges and a "Sort by" dropdown), added 14 tests including a new `tests/test_formatting.py`, and refreshed the README outputs from real runs. Files modified: `pawpal_system.py`, `formatting.py`, `main.py`, `app.py`, `requirements.txt`, `tests/test_pawpal.py`, `tests/test_formatting.py`, `diagrams/uml.mmd`, `diagrams/uml_final.mmd`, `README.md`, `reflection.md`. Things that needed fixing: a shell quoting error stopped a long command once, and one of its own edits produced a broken string in `pawpal_system.py` that the test run caught immediately. Emojis in task names are guessed from title keywords because tasks have no "type" field.

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

**Task:** the logic for rescheduling a weekly recurring task when it is completed, which is the trickiest algorithm in PawPal+ (it has to keep the task on its weekday whether it was finished on time, late, or early).

**A note on the models:** I could only call Claude models from this environment, so I could not use Gemini, ChatGPT, or Copilot. I ran the identical prompt through two different Claude models, Opus (the larger one) and Haiku (the smaller, faster one), each in a fresh agent with no access to my code or tools.

**The prompt (identical for both):**

> I'm building a pet care scheduler in Python. Write a function `next_weekly_occurrence(scheduled_time: datetime, completed_on: date) -> datetime` that reschedules a weekly recurring task when the user marks it complete. Requirements: the next occurrence keeps the same weekday and the same time of day as `scheduled_time`; it is the first weekly slot, `scheduled_time + k weeks` for k >= 1, whose date is strictly after `completed_on`; the task may be completed on time, late (even many weeks late), or early; use only the Python standard library. Reply with only: (1) the function with a short docstring, then (2) a bullet list of the edge cases you considered. Do not use any tools and do not read any files.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Claude Opus, in a fresh agent | Claude Haiku, in a fresh agent |
| **Prompt** | The prompt above | The same prompt |
| **Response summary** | A closed-form formula: `k = max(1, days_late // 7 + 1)`, then `scheduled_time + timedelta(weeks=k)`, with no loop. It also converts a `datetime` passed as `completed_on` into a `date`. It listed 10 edge cases, including daylight saving time and "exactly 7 days late skips that slot". | The same closed-form formula, in a shorter function without the `datetime` conversion. It listed 12 edge cases, including month, year, and leap-year boundaries, and noted that early completion returns the week after the original due date. |
| **What was useful** | The formula is correct and takes the same time for any lateness. The extra `datetime` guard avoids a confusing `TypeError`. The edge-case list read like a test checklist. | The same correct formula in fewer lines, and it was honest about its limits: it said callers must pass a `date` and that overflow near the maximum date is not handled. |
| **Problems noticed** | It was written without running anything (I told it not to use tools), so its claims were untested. Its daylight-saving explanation is the one claim I did not verify. | Passing a `datetime` as `completed_on` raises `TypeError`, which I confirmed. It also had no tests, and the code was never run. |
| **Decision** | Adopted its idea of using one division for the weekly case. | Adopted the same idea. It was no worse than Option A on the core logic. |

**How I checked them:** I ran both functions and my own existing implementation against a brute-force version of the rule (try k = 1, 2, 3, ... until the date is after the completion date) on 5,000 random dates, plus named cases (on the due day, a few days late, exactly a week late, three weeks late, early, very early, year rollover). All three matched the brute-force answer on every case. The differences were in handling and speed: only Opus accepted a `datetime` for `completed_on`, and for a task 100,000 weeks late the two closed-form functions took about 0.01 ms while my loop took about 35 ms.

**Which approach did you use in your final implementation and why?**

I kept my own code but replaced its loop with the closed-form idea both models used. The weekly branch of `Task._next_time()` is now `scheduled_time + step * max(1, weeks_late + 1)`, where `weeks_late` is one division. It is shorter, easier to reason about, and does not slow down for very late tasks. I did not add Opus's `datetime` guard because `mark_complete()` already converts its `now` argument to a date before calling `_next_time()`. I used the models' edge-case lists as a checklist for my tests, which already covered most of them. I added two tests for the gaps: completing exactly a week late (the same-day slot must be skipped) and completing 100,000 weeks late. Neither model was clearly better here: Opus wrote slightly more defensive code (the `datetime` guard), Haiku listed slightly more edge cases, and for a problem this small the cheaper model gave the same correct answer.

---

## Agentic Workflow Enhancement: reasoning traces

The AI Planner (`ai_planner.py`) works in a loop: **plan** (the agent receives the pets and existing tasks), **act** (it calls tools), **check** (my scheduler tests the result), **revise**, then **finish** (my code verifies the plan again). Every step is written to `pawpal_ai.log`. That file is git-ignored because it can hold personal text, so the trace below is copied from it. Nothing was edited except the cut-off summary text.

**Request (run on 2026-11-16, model `claude-opus-5-5`):** "My pets, Oona and Beanie need a morning and evening walk and bi-weekly vet visits. I also need them to have a strategic meal plan to help them maintain their weights as they easily lose and gain weight."

| Step | Tool called | What it did | Result from my code |
|---|---|---|---|
| 1 | `add_task` x8 | Morning walk, breakfast, evening walk and dinner for both dogs. Walks at 07:00 and 18:00, each meal right after the walks, Oona 15-minute walks and Beanie 10-minute walks | All 8 accepted |
| 1 | `check_schedule` | Asked my scheduler whether the plan is valid | "No problems found." |
| 2 | `finish` | Wrote the summary for the owner | My code re-checked the plan: clean, so the proposal was shown |

Log excerpt (shortened):

```
16:19:34 INFO pawpal.ai: agent start model=claude-opus-5-5 day=2026-11-16 request='My pets, Oona and Beanie need a morning and evening walk ...'
16:19:55 INFO pawpal.ai: step=1 tool=add_task args={'title': 'Morning walk', 'pet_name': 'Oona', 'start_time': '07:00', 'duration_minutes': 15, 'priority': 2, 'frequency': 'daily'} error=False -> Added Morning walk for Oona at 07:00 for 15 min.
16:19:55 INFO pawpal.ai: step=1 tool=add_task args={'title': 'Breakfast (measured portion)', 'pet_name': 'Beanie', 'start_time': '07:35', 'duration_minutes': 10, 'priority': 3, 'frequency': 'daily'} error=False -> Added Breakfast (measured portion) for Beanie at 07:35 for 10 min.
        ... six more add_task lines ...
16:19:55 INFO pawpal.ai: step=1 tool=check_schedule args={} error=False -> No problems found.
16:20:00 INFO pawpal.ai: step=2 tool=finish args={'summary': "Monday 16 Nov plan for Oona and Beanie (uses 90 of your 90 minutes, all set to repeat daily). ... Meals are high priority and come after the walks so the dogs don't exercise on a full stomach. ... Not scheduled: the vet visit every two weeks. The scheduler can't repeat a task every two weeks ..."}
16:20:00 INFO pawpal.ai: agent done: 8 tasks added
```

**What the trace shows.**
- The agent made a multi-step plan and chose its own ordering (walks before meals, with a reason).
- It said what it could not do (the bi-weekly vet visit) instead of pretending.
- The check and the finish were verified by my scheduler, not by the model's own word.

**What it does not show.** In this run, and in every live evaluation run, the first plan was already valid, so the check-and-revise step never found a problem. The revise path (the check reports an overlap, the agent moves a task, and the check passes) is covered by a scripted test, `test_agent_revises_after_check_finds_a_conflict` in `tests/test_ai_planner.py`, not by a live trace. The trace for that test is the sequence of fake-model replies written inside the test.

**Other traces.** `evaluate_agent.py` runs more scenarios (an unknown pet, a prompt-injection attempt, too little time) and writes a pass/fail table to [eval_results.md](eval_results.md). The README's "Sample interactions" section shows four more real requests with their results. To make a new trace, turn on the AI Planner, send a request, and read `pawpal_ai.log`.

---

## Test Harness / Evaluation Script

`evaluate_agent.py` runs the agent on 8 predefined scenarios, scores each trial with independent checks, repeats each live scenario twice, and prints a summary (passed trials, average seconds, consistency). Results: 14 of 14 trials passed on 2026-11-16, saved in [eval_results.md](eval_results.md) and [eval_results.json](eval_results.json). The scorer itself has 7 tests in `tests/test_evaluate_agent.py`. Run it with `python evaluate_agent.py` (or `--offline` for the two scenarios that need no API key).

