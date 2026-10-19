# Handoff: ATS design → PRD

**Next session goal:** run `/to-prd` to turn the design decisions below into a PRD. No application code exists yet.

## Where things stand

- Repo contains only scaffolding: `PROMPTS.md`, `.claude/skills/`, `.gitignore`, `README.md`.
- A full `/grill-me` design interview (23 questions) is complete. **The decisions exist only in this file and in the session log at the top of [PROMPTS.md](PROMPTS.md)**; nothing else records them yet.
- Throwaway prototypes (reference only, never promote to production):
  - [prototypes/openings-ownership.html](prototypes/openings-ownership.html): Openings list with hybrid ownership, 3 layout variants. **No layout chosen yet.**
  - [prototypes/candidate-source.html](prototypes/candidate-source.html): source rules walkthrough. Shows the *rejected* fixed-choice approach; the user then chose a Source table.
  - [prototypes/pipeline-board.html](prototypes/pipeline-board.html): pipeline board; its rules match decisions Q10–Q13. Variants A and B combined is the chosen direction.
- Uncommitted: `prototypes/`, the `.claude/skills/prototype/SKILL.md` edit (removed `disable-model-invocation`), `PROMPTS.md`, this file. The user hasn't asked for a commit.

## Fixed inputs (from the user)

**Stack (required):** Python, Django, SQLite, uv, Tailwind CSS + DaisyUI via django-tailwind-cli, HTMX, Ruff, Pytest (required).

**Business requirements:** the verbatim text is in prompt 1 of the 2026-10-19 entry in [PROMPTS.md](PROMPTS.md). In short: an internal staff-only system (candidates never log in); candidates with sources; job openings that are open or closed; one application per candidate per opening; 8 fixed stages (Applied, Screening, Interview, Final Review, Offer, Hired, Rejected, Withdrawn); a pipeline that moves applicants without a full page reload; many-to-many skills on openings; candidate lifecycle rules; rules for closing and reopening openings.

## Decisions (all user-confirmed)

**Users and permissions**
1. Named roles via Django Groups: **Recruiter, Hiring Manager, Interviewer**. Admin = `is_superuser`. Accounts are created by admins only (no sign-up page).
2. **Hybrid access:** ownership drives filters and labels ("My openings" is the default view for Hiring Managers; Recruiters and Interviewers default to All), but never blocks viewing.
3. Permission matrix:

   | Action | Admin | Recruiter | Hiring Mgr | Interviewer |
   |---|---|---|---|---|
   | View everything | ✅ | ✅ | ✅ | 👁 view only |
   | Add/edit candidates | ✅ | ✅ | ❌ | ❌ |
   | Create/edit openings (excluding skills) | ✅ | ✅ | ✅ | ❌ |
   | Close/reopen openings | ✅ | ✅ | ✅ | ❌ |
   | Assign designated authority | ✅ | ✅ | ❌ | ❌ |
   | Record applications | ✅ | ✅ | ❌ | ❌ |
   | Move stages (excluding Offer/Hired) | ✅ | ✅ | ✅ | ❌ |
   | Move into Offer/Hired | see Q10 | | | |
   | Manage sources | ✅ | ✅ | ❌ | ❌ |
   | Skills | see Q15 | | | |
   | Closure decisions (grace period, cancel, restore) | see Q20 | | | |
   | Archive candidates | ✅ | ✅ | ❌ | ❌ |
   | Permanently delete candidates; manage staff | ✅ | ❌ | ❌ | ❌ |

   Interviewers have no feedback or notes feature.

**Candidates and sources**

4. `Candidate`: first_name, last_name, **email (required, unique, stored lowercased)**, phone?, notes?, created_at, updated_at. No résumé, LinkedIn or location fields. A candidate can exist without any application.
5. Sources live in a **`Source` table** that Admins and Recruiters can add to. The goal is reporting on which channels are worth the hiring effort.
6. The source is stored **per application** (`Application.source` FK), pre-filled from the candidate's previous application. Optional `referred_by` text field, shown when the source's category is Referral.
7. `Source(name, category)`: name unique ignoring case (`UniqueConstraint` on `Lower("name")`); category is a `TextChoices` with Company website / Job board / Referral / Other.
8. Sources are never deleted: `is_active` plus `on_delete=PROTECT`, names can be edited, and an old application's form still shows its inactive source.

**Openings**

9. `JobOpening`: title, department (text), location (text, optional), description, status (open/closed), **required `designated_authority`** (FK to User, PROTECT; any active staff member *except Interviewers*), skills, timestamps.
10. `can_make_offer(user, opening)`: Admin **or** the Hiring Manager group **or** this opening's designated authority.

**Applications and pipeline**

11. `UniqueConstraint(candidate, opening)`. Transitions:
    - Any active stage (Applied through Offer) can move to any other active stage.
    - Any active stage can move to Rejected or Withdrawn.
    - Rejected or Withdrawn can be **reopened** to an active stage.
    - **Hired** is reachable only from Offer and is final.
    - A **note is required** for skips, backward moves and reopens; it's optional for Rejected or Withdrawn; it isn't needed for a one-step forward move.
    - Implemented as pure functions `can_move()` and `requires_note()` plus an allowed-transitions table.
12. **`StageChange(application, from_stage, to_stage, changed_by, changed_at, note, cause)`** log, where `cause` is `manual` or `closure`. `Application.stage` is a cached copy of the current stage. *All* moves go through `move_application()` inside `transaction.atomic`. Creating an application writes a `None → Applied` row.
13. Pipeline board for **one opening at a time**, with stage columns. Rejected and Withdrawn are collapsed to a count and can be expanded. Every card has a **Move ▾ menu** (lists only legal targets, tagged when a note is needed) **plus built-in browser drag-and-drop** (no SortableJS), both posting to one HTMX endpoint. Non-linear moves open a DaisyUI modal for the note. Drag-and-drop is covered by a manual browser checklist, not Playwright.

**Skills**

14. Plain M2M `JobOpening.skills → Skill(name)`, name unique ignoring case. Skills are retired with `is_active` plus PROTECT.
15. `can_manage_opening_skills(user, opening)` (Admin, the Hiring Manager group, or the designated authority) covers attaching, detaching and creating skills, inline via HTMX on the opening page. **Retiring** a skill is limited to Admin and the Hiring Manager group. Skills are a separate section from the opening edit form, and Recruiters see it as read-only.

**Lifecycle**

16. Candidates are edited for corrections. **Archive** (`is_archived`, `archived_at`) is the single "deactivate" concept: reversible, **blocked while the candidate has an active application**, and archived candidates can't receive new applications. They're hidden from lists behind a "Show archived" toggle, but their past applications still appear on boards. **Permanent delete** is Admin-only, behind a confirmation page that lists what will be destroyed.
17. **Closing** stops new applications; existing applications keep moving, including into Offer and Hired. If any are in progress, the designated authority must decide:
    - **grace period** (N days, extendable with a note), or
    - **cancel now**: `cancel_remaining_applications()` moves them to **Rejected** with `cause=closure` and the note "Position closed."
18. Each grace period has an expiry action chosen per opening: **auto-cancel** or **flag overdue** (`grace_period_ends`, `grace_expiry_action` on `JobOpening`). A daily management command, **`process_grace_periods`**, runs auto-cancels and sends reminders, and is safe to run more than once.
19. Candidate emails via `django.core.mail` (console backend in development, locmem in tests), each logged in **`CandidateMessage(candidate, application, kind, subject, body, sent_at)`** with no duplicates. Schedule:
    - when a grace period is set;
    - **3 days** before the end (states the consequence: "will be closed" for auto-cancel, "may be closed" for flag-only);
    - **1 day** before the end;
    - on cancellation;
    - on restore (see Q21).

    Wording: "our team will be in touch to complete the next step." Candidates take no action in the system.
20. Staff are notified through an **in-app "Needs attention" panel plus email**: when an opening is closed with active applications, and when a flag-only grace period becomes overdue. An **Admin in-progress view** lists closed openings with active applicants and a status of Awaiting decision, In grace period or Overdue. `can_decide_closure(user, opening)` (Admin, the Hiring Manager group, or the designated authority) controls grace period, cancel, extend and restore. Recruiters can close an opening but not decide what happens to its applicants. There is no default timeout when nobody decides.

**Reopening and staff**

21. Reopening is allowed for anyone who can close. It clears the grace period and stops reminders. The decision-maker **ticks which applicants from the latest closure** to restore; each is moved back to its pre-closure stage (from the `cause=closure` row) and sent a "position reopened" email. Restoring into Offer still requires `can_make_offer()`. If a Recruiter reopens, the restore choice goes to the authority's panel. **`OpeningEvent(opening, kind, by, at, note)`** logs closed, reopened, grace period set, extended or expired, and authority changes.
22. Archived candidates appear in the restore list but are **disabled** ("Archived; unarchive first").
23. Staff leave through **`deactivate_staff(user, reassignments, by)`**, which requires picking a new designated authority for each of their openings, in one transaction. The Django admin's `is_active` checkbox is read-only. Every authority reassignment is logged as an `OpeningEvent` and emails the new authority.

## Defaults assumed, not explicitly confirmed

Raise these during the PRD session if useful:
- If a grace period is shorter than 3 days, reminders whose date has passed are skipped.
- `grace_period_ends` is a date in the project's `TIME_ZONE`.
- Normal rejections and hires send no candidate email.
- The candidate list has name and email search.
- Testing uses `pytest-django` with plain fixtures and parametrized tests for the pure rule and permission functions.

## Not yet decided

- Layout of the Openings list (variants in `prototypes/openings-ownership.html`).
- Production SMTP settings, and how the daily command gets scheduled (Windows Task Scheduler or cron).
- How Django apps are split, URL design, and seed or demo data.

## Working with this user

- Beginner. Explain options plainly, ask one question at a time, and always give a recommendation.
- Learns visually: offer `/prototype` for UI or rules decisions.
- Logs every session in `PROMPTS.md`, but only when they ask (see the rules at the top of that file).

## Suggested skills

- **`to-prd`**: next step. Feed it this file. Ask about the gaps under "Not yet decided" only if the PRD needs them.
- **`prd-to-plan`**: after the PRD, to break it into tracer-bullet phases in `./plans/`.
- **`prototype`**: if a PRD section is still hard for the user to picture.
- **`implement` / `tdd`**: later, once a plan phase is approved.
