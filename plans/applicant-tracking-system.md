# Plan: Applicant Tracking System

> Source PRD: [prd/applicant-tracking-system.md](../prd/applicant-tracking-system.md). User story numbers below refer to that PRD.

## Architectural decisions

These apply to every phase:

- **Stack:** Python, Django, SQLite, uv, Tailwind CSS + DaisyUI via django-tailwind-cli, HTMX, Ruff, and Pytest with pytest-django.
- **Owning apps** (Django apps, each with its own models, views, templates and tests):
  - `accounts`: role groups, the permission functions, and staff departure.
  - `candidates`: Candidate and Source.
  - `openings`: JobOpening, Skill, OpeningEvent, and the logic for closing and reopening openings.
  - `applications`: Application, StageChange, the stage rules, and the pipeline board.
  - `notifications`: CandidateMessage, email sending, the Needs attention panel, and the `process_grace_periods` command.
- **URLs:** every URL is named and app-namespaced (for example `candidates:detail`), and records are addressed by pk, not slug.
  - `/accounts/login/`, `/accounts/logout/`. There is no sign-up URL.
  - `/candidates/`, `/candidates/new/`, `/candidates/<pk>/`, `/candidates/<pk>/edit/`, `/candidates/<pk>/delete/`
  - `/sources/`
  - `/openings/`, `/openings/new/`, `/openings/<pk>/`, `/openings/<pk>/edit/`, `/openings/<pk>/board/`
  - `/applications/new/`, `/applications/<pk>/move/` (the single HTMX endpoint for stage moves)
  - `/attention/` (the Needs attention panel), `/in-progress/` (the Admin in-progress view)
- **Models and relationships:**
  - Candidate
  - Source
  - Skill
  - JobOpening, with an FK to User for the designated authority (PROTECT) and an M2M to Skill
  - Application, with FKs to Candidate, JobOpening and Source (PROTECT), and a unique constraint on (candidate, opening)
  - StageChange, with an FK to Application
  - OpeningEvent, with an FK to JobOpening
  - CandidateMessage, with FKs to Candidate and Application

  Fields are as listed in the PRD's data model section. Each phase adds only the models and fields it needs, in its own migration.
- **Auth:** Django's built-in authentication. All views need a login.
  - Roles are the Groups Recruiter, Hiring Manager and Interviewer, created by a data migration. Admin is `is_superuser`.
  - Permission decisions go through the pure functions the PRD names (`can_make_offer`, `can_manage_opening_skills`, `can_decide_closure`) and through role checks of the same kind.
  - Views stay thin and call these functions, and templates use the same functions to hide actions a user can't take.
- **Deep modules** (where the business logic lives, all fully unit-tested):
  - the stage rules: the allowed-transitions table, `can_move`, `requires_note`
  - the permission functions
  - `move_application`, the only way a stage changes
  - the closure services: closing, `cancel_remaining_applications`, grace periods, reopening and restoring
  - the candidate messaging service
  - `deactivate_staff`
- **Demo data:** a `seed` management command, added in Phase 1 and extended in each later phase. It creates one user per role plus sample data, and running it twice gives the same result.
- **TDD:** each phase lists *candidate* behaviors for the `/tdd` skill (at most three), or explains why it has none. The final choice is made and approved at the start of each phase. Every other acceptance criterion still gets ordinary tests.

---

## Phase 1: Project skeleton, staff login and roles

**User stories:** 1, 2, 3, 8, 9

### What to build

A running Django project with the full toolchain: uv, Ruff, Pytest, and Tailwind with DaisyUI through django-tailwind-cli.

- A base layout with navigation and a light/dark theme, and HTMX loaded.
- Staff log in and out on Django's login page. There is no sign-up page.
- The three role groups are created automatically.
- The project's conventions are written down in a `CLAUDE.md` file and a testing guide, so later phases can follow them.
- A `seed` command creates one user per role.
- A shared way of refusing changes from Interviewers is in place for later phases to reuse.

### Acceptance criteria

- [x] `uv run pytest` and `uv run ruff check .` both pass on the empty project.
- [x] Anonymous users are redirected to the login page, and there is no sign-up URL.
- [x] The Recruiter, Hiring Manager and Interviewer groups exist after `migrate`.
- [x] `seed` creates an Admin, a Recruiter, a Hiring Manager and an Interviewer, and running it twice changes nothing.
- [x] Logged-in users see the base layout with their name and role, and can log out.
- [x] The shared role check refuses changes (403) from Interviewers.

### TDD

**No TDD expected.** This phase is mostly setup and configuration. The login redirect and Interviewer refusal get ordinary tests.

---

## Phase 2: Candidates

**User stories:** 10–15

### What to build

Recruiters and Admins add and edit candidates: first name, last name, email, and optional phone and notes. Everyone can browse the candidate list, search it by name or email, and open a candidate's detail page. The applications section on that page stays empty until Phase 5. Hiring Managers and Interviewers see the pages without the add and edit actions.

### Acceptance criteria

- [x] Recruiters and Admins can create and edit candidates, and Hiring Managers and Interviewers are refused.
- [x] Email is required, stored in lowercase, and unique regardless of capital letters (`Ann@X.com` clashes with `ann@x.com`), and the form shows a clear error.
- [x] A candidate can exist without any applications.
- [x] The list searches by name and by email.
- [x] `seed` adds sample candidates.

### TDD

**Candidates:**
1. **Email stored lowercase and unique regardless of case.** A database constraint where a mistake would quietly create duplicates.
2. **Only Recruiters and Admins can create or edit candidates.** This is the first real permission rule, and later phases copy its pattern.

---

## Phase 3: Sources

**User stories:** 24–27

### What to build

A sources page where Recruiters and Admins add a source with a name and category, rename it, and retire or reactivate it. A source is never deleted. Everyone else sees the page as read-only.

### Acceptance criteria

- [x] Recruiters and Admins can add, rename and retire sources, and other roles are refused.
- [x] Source names are unique regardless of capital letters.
- [x] The category is one of Company website, Job board, Referral or Other.
- [x] No action deletes a source, and a source can be retired and reactivated.
- [x] `seed` adds sample sources in every category.

### TDD

**Candidates:**
1. **Source names unique regardless of case.** A database constraint on the lowercased name, which is easy to get wrong.
2. **Retired sources are left out of the "active" choices but still exist.** Phase 5's application form depends on this rule.

---

## Phase 4: Job openings

**User stories:** 4–7, 31–33

### What to build

Recruiters, Hiring Managers and Admins create and edit openings: title, department, optional location, description and status, with a required designated authority.

The Openings list has a My openings / All toggle. It defaults to My openings for Hiring Managers and to All for everyone else, and each row is labelled with its designated authority. The opening detail page shows the opening's details. The list layout is chosen from the variants in `prototypes/openings-ownership.html` at the start of this phase.

### Acceptance criteria

- [x] Recruiters, Hiring Managers and Admins can create and edit openings, and Interviewers are refused.
- [x] The designated authority is required, and only active staff who aren't Interviewers can be picked.
- [x] Hiring Managers default to My openings, everyone else defaults to All, and the toggle works both ways.
- [x] "My openings" never hides anything: every opening is still reachable through All and by its URL.
- [x] Each opening shows its designated authority.
- [x] `seed` adds open and closed sample openings with different designated authorities.

### TDD

**Candidates:**
1. **Designated authority eligibility** (active and not an Interviewer). A rule that every closure and offer decision later depends on.
2. **Default list filter by role** (My openings for Hiring Managers, All for others). A role-based rule with an edge case for users who have no group.

---

## Phase 5: Record applications

**User stories:** 23, 28–30, 42–44

### What to build

Recruiters and Admins record that a candidate has applied for an open opening, with a source.

- The source is pre-filled from the candidate's most recent application.
- A "referred by" field appears through HTMX when the chosen source is a Referral.
- Saving creates the application at Applied and writes the first StageChange row (no stage → Applied).
- Applications show up on the candidate detail page and the opening detail page.
- An existing application's form still shows its retired source.

### Acceptance criteria

- [ ] A second application for the same candidate and opening is refused, by the form and by the database.
- [ ] Applications can't be created for closed openings.
- [ ] Creating an application writes exactly one StageChange row (no stage → Applied) in the same database transaction.
- [ ] The source is pre-filled from the candidate's previous application, if there is one.
- [ ] "Referred by" shows only for Referral sources.
- [ ] New applications can only pick active sources, but an old application's retired source still shows on its form.
- [ ] Only Recruiters and Admins can record applications.

### TDD

**Candidates:**
1. **One application per candidate per opening.** A database constraint plus a friendly form error.
2. **No applications for closed openings.** An eligibility rule that later phases (archiving, closing and reopening) build on.
3. **Source pre-fill picks the candidate's most recent application.** A query with edge cases: no earlier applications, or several.

---

## Phase 6: Pipeline board and Move menu

**User stories:** 45–47, 49–57

### What to build

A board at `/openings/<pk>/board/` for one opening:

- One column per active stage, with Rejected and Withdrawn collapsed to an expandable count.
- Each card has a Move ▾ menu listing only the legal targets for the current user, tagged when a note is needed.
- Picking a target posts to the HTMX move endpoint, and moves that need a note open a DaisyUI modal first.
- Every move goes through `move_application`, which checks the stage rules and `can_make_offer`, writes a StageChange row and updates the cached stage atomically.
- The board updates without a full page reload, and each application's stage history is visible.

### Acceptance criteria

- [ ] The allowed-transitions table matches the PRD:
  - any active stage moves to any other active stage, Rejected or Withdrawn;
  - Rejected and Withdrawn can be reopened to an active stage;
  - Hired is reachable only from Offer and is final.
- [ ] A note is required for skips, backward moves and reopens; optional for Rejected or Withdrawn; not needed for a one-step forward move.
- [ ] Only Admins, Hiring Managers or the opening's designated authority can move into Offer or Hired.
- [ ] Illegal or unauthorised moves posted straight to the endpoint are refused with a clear message, and nothing is written.
- [ ] Each move writes exactly one StageChange row (from, to, by, at, note, cause = manual) and updates the cached stage in the same transaction.
- [ ] The Move menu lists only legal targets for the current user, tagged when a note is needed.
- [ ] A move swaps only the affected part of the board, with no full reload.
- [ ] Rejected and Withdrawn show as counts and expand to list their cards.
- [ ] Interviewers see the board with no Move controls.

### TDD

**Candidates (this is the most important TDD phase):**
1. **`can_move` and `requires_note` across the full transition table.** Pure functions that suit parametrized tests, and the core rule of the system.
2. **`can_make_offer`.** A permission rule where a mistake would let the wrong person make an offer.
3. **`move_application` writes the history row and updates the stage atomically, or writes nothing when refused.** An invariant that every later phase depends on.

---

## Phase 7: Drag-and-drop on the board

**User stories:** 48

### What to build

Adds built-in browser drag-and-drop (no SortableJS) to the board's cards and columns. A drop posts to the same move endpoint as the Move menu, opens the note modal when a note is needed, and snaps the card back when the move is illegal. A manual browser checklist covers drag-and-drop.

### Acceptance criteria

- [ ] Dragging a card onto a legal column moves it through the existing endpoint.
- [ ] Dropping onto a column that needs a note opens the note modal first.
- [ ] Dropping onto an illegal column is refused, and the card goes back where it was.
- [ ] The Move menu keeps working, and Interviewers can't drag.
- [ ] A manual browser checklist for drag-and-drop exists and has been followed.

### TDD

**No TDD expected.** The behavior is in the browser, and the server endpoint it uses was already test-driven in Phase 6. It's covered by the manual checklist instead of browser automation.

---

## Phase 8: Skills on openings

**User stories:** 37–41

### What to build

A Skills section on the opening detail page, separate from the edit form.

- Users allowed by `can_manage_opening_skills` attach and detach skills, and create new ones inline, all through HTMX.
- Admins and Hiring Managers can retire a skill.
- Recruiters and Interviewers see the section as read-only.

### Acceptance criteria

- [ ] Admins, Hiring Managers and the opening's designated authority can attach, detach and create skills without a page reload.
- [ ] Recruiters and Interviewers see skills read-only, and posting directly is refused.
- [ ] Skill names are unique regardless of capital letters, and creating "python" when "Python" exists reuses the existing skill.
- [ ] Only Admins and Hiring Managers can retire a skill. Retired skills can't be attached, but stay on openings that already have them.
- [ ] The same skill can be attached to many openings.

### TDD

**Candidates:**
1. **`can_manage_opening_skills`, and the narrower rule for retiring.** Two related permission rules that are easy to mix up.
2. **Inline create reuses an existing skill regardless of case.** An edge case that would otherwise create duplicates.

---

## Phase 9: Candidate lifecycle

**User stories:** 16–22

### What to build

Recruiters and Admins archive and unarchive candidates.

- Archiving is blocked while the candidate has an active application.
- Archived candidates are hidden from the list behind a "Show archived" toggle, can't receive new applications, and still appear on pipeline boards.
- Admins can permanently delete a candidate from a confirmation page that lists everything that will be destroyed.

### Acceptance criteria

- [ ] Archiving sets `is_archived` and `archived_at`, and is refused while the candidate has any active application.
- [ ] Unarchiving reverses it.
- [ ] Archived candidates are hidden by default and shown with "Show archived".
- [ ] New applications for archived candidates are refused.
- [ ] Archived candidates' existing applications still show on boards.
- [ ] Only Admins can permanently delete. The confirmation page lists the applications, stage history and messages that will be removed.

### TDD

**Candidates:**
1. **Archiving is blocked while an application is active.** A business rule with edge cases (an application in a terminal stage versus an active one).
2. **Archived candidates can't receive new applications.** Extends Phase 5's eligibility rule.
3. **Permanent delete is Admin-only.** It can't be undone, so the permission must be right.

---

## Phase 10: Closing an opening and "cancel now"

**User stories:** 36, 58–60, 64, 65, 67, 69

### What to build

Anyone who can edit an opening can close it.

- Closing writes an OpeningEvent and stops new applications, but existing applications keep moving, including into Offer and Hired.
- If any applications are active, the designated authority is notified in the Needs attention panel at `/attention/` and by email.
- A user allowed by `can_decide_closure` can choose **cancel now**. `cancel_remaining_applications` moves each active application to Rejected with cause closure and the note "Position closed.", and emails each candidate through the candidate messaging service, which logs a CandidateMessage.
- The opening page shows its event history.

### Acceptance criteria

- [ ] Closing writes a "closed" OpeningEvent and blocks new applications.
- [ ] Moves for existing applications still work after closing.
- [ ] With active applications, the designated authority sees the opening in Needs attention and gets one staff email.
- [ ] Recruiters can close an opening but don't see, and can't post, the closure decision actions.
- [ ] Cancel now moves every active application to Rejected (cause = closure, note "Position closed."), using `move_application`, in one transaction.
- [ ] Each cancelled candidate gets exactly one cancellation email, logged as a CandidateMessage, and running the action again doesn't resend it.
- [ ] The opening page lists its OpeningEvents.

### TDD

**Candidates:**
1. **`can_decide_closure`, including "a Recruiter can close but not decide".** A subtle permission split.
2. **`cancel_remaining_applications` rejects only the active applications, with cause closure and the standard note.** A state transition across many rows.
3. **A candidate message is never sent twice.** An invariant that the reminder schedule in Phase 11 relies on.

---

## Phase 11: Grace periods and reminders

**User stories:** 61–63, 66, 68, 70, 72

### What to build

Instead of cancelling, a decision-maker can set a grace period of N days, with an expiry action of auto-cancel or flag overdue. They can extend it later with a note.

- Candidates get emails when the grace period is set, 3 days before it ends and 1 day before it ends. The emails say "will be closed" or "may be closed" to match the expiry action, and tell them "our team will be in touch to complete the next step".
- A daily `process_grace_periods` command sends any reminders that are due, auto-cancels expired auto-cancel grace periods, and marks expired flag-only grace periods as overdue. Overdue openings notify the designated authority in Needs attention and by email.
- Running the command more than once is safe.

### Acceptance criteria

- [ ] Setting a grace period stores the end date (in the project time zone) and expiry action, writes an OpeningEvent and emails every active candidate once.
- [ ] Extending needs a note, moves the end date and writes an OpeningEvent.
- [ ] The 3-day and 1-day reminders are sent on the right days, with wording that matches the expiry action. Reminders whose date has already passed (grace periods under 3 days) are skipped.
- [ ] On expiry, auto-cancel runs the cancel-now flow, and flag-only marks the opening overdue and notifies staff.
- [ ] Running `process_grace_periods` twice on the same day sends no duplicate emails and makes no extra changes.
- [ ] Tests control "today" so that the schedule can be checked without waiting.

### TDD

**Candidates:**
1. **Which reminders are due on a given date** (3-day and 1-day, skipping those already past). A date calculation with edge cases.
2. **`process_grace_periods` is safe to run twice.** A must-have for a scheduled command.
3. **Expiry action:** auto-cancel rejects the applications, and flag-only marks the opening overdue. A business rule with two branches.

---

## Phase 12: Admin in-progress view

**User stories:** 71

### What to build

An Admin-only page at `/in-progress/` listing closed openings that still have active applicants. Each shows its designated authority, the number of active applicants and a status of Awaiting decision, In grace period or Overdue, and links to the opening.

### Acceptance criteria

- [ ] Only Admins can open the page.
- [ ] Only closed openings with at least one active application appear.
- [ ] The status is Awaiting decision (no grace period set), In grace period (before the end date) or Overdue (a flag-only grace period that has expired).
- [ ] Openings drop off the list once they have no active applicants.

### TDD

**Candidate:**
1. **Working out the status** (Awaiting decision, In grace period or Overdue). A query with edge cases at the end date.

---

## Phase 13: Reopening and restoring applicants

**User stories:** 73–80

### What to build

Anyone who can close an opening can reopen it. Reopening writes an OpeningEvent, clears the grace period and stops reminders.

- A decision-maker sees the applicants cancelled at the **latest** closure as a checklist and ticks which to restore.
- Each restored application goes back to its stage before the closure, read from its closure-cause StageChange row, through `move_application`. The candidate gets a "position reopened" email.
- Restoring into Offer still requires `can_make_offer`.
- Archived candidates appear in the checklist but are disabled, marked "Archived; unarchive first".
- When a Recruiter reopens, the restore choice goes to the designated authority's Needs attention panel.

### Acceptance criteria

- [ ] Reopening writes a "reopened" OpeningEvent, clears the grace period fields and stops reminders.
- [ ] The restore list includes only applications cancelled by the latest closure.
- [ ] Each restored application goes back to its stage before the closure, with a StageChange row, and its candidate gets one "position reopened" email.
- [ ] Restoring into Offer is refused for users without `can_make_offer`.
- [ ] Archived candidates are shown but can't be selected, and posting them directly is refused.
- [ ] A reopen by a Recruiter puts the restore choice in the designated authority's Needs attention panel.

### TDD

**Candidates:**
1. **Restore goes back to the stage before the latest closure.** A history query with edge cases (several closures, or a reopened application that was cancelled again).
2. **Restoring into Offer needs `can_make_offer`.** Stops the restore flow from getting around the offer rule.
3. **Archived candidates can't be restored.** An eligibility rule enforced on the server, not only in the checkbox.

---

## Phase 14: Authority reassignment and staff departure

**User stories:** 34, 35, 81–83

### What to build

Recruiters and Admins change an opening's designated authority. This writes an OpeningEvent and emails the new authority.

Admins deactivate a departing staff member through `deactivate_staff`. The form needs a new eligible authority for each of that person's openings, and applies every reassignment plus the deactivation in one transaction. In the Django admin, `is_active` is read-only so this flow can't be bypassed.

### Acceptance criteria

- [ ] Only Recruiters and Admins can change the designated authority. Each change writes an "authority changed" OpeningEvent and emails the new authority.
- [ ] `deactivate_staff` refuses to run unless every opening the user is responsible for gets an eligible new authority.
- [ ] All reassignments and the deactivation succeed together or not at all.
- [ ] Deactivated users can't log in and no longer appear as authority choices.
- [ ] `is_active` is read-only in the Django admin.

### TDD

**Candidates:**
1. **`deactivate_staff` needs a reassignment for every opening, and is all-or-nothing.** A workflow across many tables where a partial failure would leave openings without an authority.
2. **A new authority must be eligible** (active and not an Interviewer). Reuses Phase 4's rule at a new entry point.
