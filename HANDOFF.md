# Handoff: Phase 11/14, Grace periods and reminders

**Next session goal:** carry on with `/implement applicant-tracking-system phase 11`, starting at the **TDD cycles**. The brief below is **approved**. The user's words were "Everything else is good so far". The next stop is the first RED test, shown to the user for approval.

## Where things stand

- Phases 1–10 are committed (latest: `6fd0f67 Implemented Phase 10`). The working tree was clean at the start of this session, and **no code has been written for Phase 11 yet**.
- Read these first:
  - [CLAUDE.md](CLAUDE.md)
  - Phase 11 in [plans/applicant-tracking-system.md](plans/applicant-tracking-system.md) (its acceptance criteria are all unticked)
  - the PRD's "Closing openings", "Candidate email schedule" and data-model sections in [prd/applicant-tracking-system.md](prd/applicant-tracking-system.md)
  - [docs/TESTING.md](docs/TESTING.md)
- The code to build on:
  - `openings/services.py` (`close_opening`, `cancel_refusal`, `latest_closure`, `cancel_remaining_applications`, `CLOSURE_NOTE`) and `openings/models.py` (`OpeningEvent`, `awaiting_closure_decision()`);
  - `notifications/services.py` (`send_candidate_message`, `render_email`, `send_after_commit`) and `notifications/attention.py`;
  - `openings/views.py` (`OpeningCancelRemainingView` is the pattern for confirmation pages) and `openings/templates/openings/partials/closure_panel.html`;
  - `accounts/management/commands/seed.py` (`SeedClosure`, `seed_closure`);
  - test fixtures: `openings/tests/conftest.py` (`application_at`, `close_directly`, `backend`, `make_candidate`) and `notifications/tests/conftest.py`.
- `HANDOFF.md` is referenced from CLAUDE.md. This file replaces the old design handoff, which was deleted in Phase 1. Its content now lives in the PRD and in PROMPTS.md.

## New instructions from the user (outrank the brief)

1. **Make the expiry boundary explicit in tests.** Write the end-date boundary out as test cases, covering the day before, the end date and the day after.
2. **Expiry is processed on the end date itself, not the following day.** The rule is `today >= grace_period_ends`. A run on `ends - 1` changes nothing; a run on `ends` performs the action.
3. **The end-of-period action runs only once.** A later run, on the same day or any day after, must not cancel again, flag again, write a second "grace period expired" event or email the authority again. This holds even if someone has reopened an application on that closed opening in the meantime.

Fold 1–3 into the TDD tests. The natural places are candidate 3 (the expiry branches) and candidate 2 (safe to run twice), plus a parametrized boundary test on the pure rule. Show them at each RED stop.

## Approved TDD candidates (the plan's, unchanged)

1. **Which reminder is due on a given date.** A pure function in a new `openings/grace.py`, such as `due_reminder(*, ends, set_on, today) -> int | None`. Test it with a hand-written table and no `django_db` mark.
2. **`process_grace_periods(today=…)` is safe to run twice.** Take a snapshot of the rows and the `mailoutbox`, run it a second time on the same date, and expect nothing new.
3. **The expiry action.** Auto-cancel rejects the active applications through `cancel_remaining_applications`. Flag overdue marks the opening overdue and emails the designated authority. Both happen on the end date itself, and only once (instructions 2 and 3).

Follow `.claude/skills/tdd/SKILL.md`: one test at a time, RED must fail on an assertion, stop for approval at RED, then summarize GREEN and carry on.

## Approved design decisions (only recorded here)

- **Dates** are in the project time zone (`America/Chicago`). A grace period of N days set on day D ends on `D+N`. The 3-day reminder falls on `ends-3` and the 1-day reminder on `ends-1`. Services take `today: date | None` (defaulting to `timezone.localdate()`), and rules never call `date.today()`.
- **Skipped reminders.** A reminder dated on or before `grace_period_set_on` (the day the grace period was set or last extended) is skipped. So a 3-day grace period gets only the 1-day reminder, and a 1-day grace period gets none.
- **Missed runs.** A late run sends only the most recent reminder that's due (the one with the fewest days left), never one for a stale date. A reminder is due only while `today < ends`.
- **New `JobOpening` fields** (migration `openings/0004`):
  - `grace_period_ends` (date, null)
  - `grace_expiry_action` (choices: auto-cancel / flag overdue, blank)
  - `grace_period_set_on` (date, null)
  - `grace_expired_on` (date, null): set when the command handles the end, which is what makes the action run only once
  - a check constraint keeping the first three filled in or empty together, with `grace_expired_on` empty when there's no grace period.
- **New event kinds** for `OpeningEvent`: `grace_period_set`, `grace_period_extended` and `grace_period_expired`. The notes are written with the dates in them (for example "Extended from Oct 27, 2026 to Nov 3, 2026. Reason: …").
- **Setting a grace period:**
  - only on a closed opening with active applications;
  - only by someone `can_decide_closure` allows;
  - refused if a grace period already exists (extend it instead);
  - the form asks for a number of days (1–90) and the expiry action;
  - it emails every active candidate once (message kind `grace_period_set`).
- **Extending:**
  - asks for a new end date, which must be after both the current end and today, plus a required note;
  - allowed while the grace period is running or overdue, and it clears `grace_expired_on`;
  - refused after an auto-cancel expiry;
  - sends candidates no email, but the reminders then follow the new date.
- **Email identities.** Each message is keyed on the closure, like Phase 10's `closure-<closed event pk>`. A reminder's key also includes the end date and the days left, so extending leads to fresh reminders. Reminders go only to applications that are active at that moment. `send_candidate_message` gains an optional `context` argument.
- **What happens at the end:**
  - **Auto-cancel** calls `cancel_remaining_applications`, which sends the usual cancellation emails and writes its "Remaining applications cancelled" event.
  - **Flag overdue** writes the expired event and calls a new `notify_authority_of_overdue`, which sends the staff email only if anyone is still active.
  - **Who the history names:** the person who set the grace period, or the designated authority if the setter can no longer decide. If neither can, the command skips that opening and prints a warning.
  - Each opening is handled in its own transaction, with the row locked and re-read first.
- **Needs attention.** `awaiting_closure_decision()` now means closed, with active applications, and no grace period running. So it includes overdue openings, and openings mid-grace-period drop out. Overdue items show an "Overdue" badge, and the nav badge counts them too.
- **Cancel now during a grace period** still works. The later expiry has nothing to cancel.
- **The command** is `notifications/management/commands/process_grace_periods.py`, with a `--today YYYY-MM-DD` option for demos and manual testing.
- **Views:** `openings:grace_period` (`/openings/<pk>/grace-period/`) and `openings:extend_grace_period` (`/openings/<pk>/grace-period/extend/`). Both are confirmation pages (open the page, confirm, return to the opening). They share a `ClosureDeciderMixin`, extracted from `OpeningCancelRemainingView`, which then uses it too. The closure panel shows the grace period's state with Set, Extend and Cancel actions.
- **Admin:** the grace fields are read-only.
- **Seed:** one more closure. The recruiter (its authority) closes Data Engineer, where Dev is at Applied, and gives it a grace period, for example 4 days with flag overdue, set only in the run that creates it. `accounts/tests/test_seed.py::test_seed_closes_three_openings_through_the_closure_flow` will need its expected emails and titles updated.
- **Leave for later phases:**
  - Phase 12: the in-progress view and its status logic;
  - Phase 13: reopening clears the grace fields.

## Finishing the phase (from the implement skill)

- When the build is done, run the full `uv run pytest`, `uv run ruff check .` and `uv run ruff format .`.
- Run `seed` twice to confirm the second run changes nothing.
- Tick the plan's criteria.
- Give the manual browser test guide in the reply (seeded password: see `SEED_PASSWORD` in the seed command), including how to use `process_grace_periods --today`.
- Add a **new** PROMPTS.md entry at the top for the build session. This planning session is already logged there, as "Phase 11/14, Grace periods and reminders (brief and handoff)". Never edit that entry: the log's rule is that older entries are never changed. The new entry may point back to it.
- End with `git status --short`. Never stage, commit or push.

## Suggested skills

- `implement` (`/implement applicant-tracking-system phase 11`): resumes the phase; skip straight to step 5, since the brief is approved.
- `tdd`: the three cycles above, with RED approval stops.
- `prototype`: only if the user asks to see the closure panel's grace-period states first (they were offered this and haven't asked yet).
