# PRD: Internal Applicant Tracking System (ATS)

*Source: the 2026-10-19 `/grill-me` design interview (23 decisions), recorded in HANDOFF.md and PROMPTS.md.*

## Problem Statement

The company's hiring staff (recruiters, hiring managers and interviewers) have no shared system for tracking hiring. They can't easily see who has applied for which job, where each applicant stands, or which recruiting channels produce candidates worth the effort. Nobody agrees on how candidate records should be kept over time (when to edit, archive or delete them), and there's no defined process for what happens to applicants who are still in progress when a job opening closes, or for whether and how that opening can reopen. Moving applicants between hiring stages should be quick, and every move needs to be traceable so the team can see why an applicant skipped ahead or went backward.

## Solution

An internal, staff-only web application built with Django. Candidates never log in. Staff sign in with accounts created by an administrator, and each account has one of three named roles (Recruiter, Hiring Manager, Interviewer) or is an Admin. Everyone can see everything (Interviewers can only view), while ownership decides the default filters and labels.

Staff use it to:

- keep candidate records, and record which source (channel) each application came from, so channels can be compared;
- create job openings with skills, a department, a location, and a required **designated authority**: the staff member responsible for offer and closure decisions on that opening;
- record one application per candidate per opening, then move it through eight fixed stages on a per-opening **pipeline board**, using a Move menu or drag-and-drop, without reloading the page;
- write a note whenever an applicant skips a stage, goes backward or is reopened, with every move kept in a permanent history;
- close an opening and then decide what happens to applicants still in progress: give them a grace period (which ends in an automatic cancellation or an overdue flag) or cancel them now. Candidates get emails about this.
- reopen an opening and pick which applicants from the latest closure to restore to the stage they were at before;
- archive candidates reversibly; only an Admin can permanently delete one;
- hand off a departing staff member's openings to new designated authorities in one step.

## User Stories

### Accounts and access

1. As an Admin, I want to create staff accounts and assign each one a role (Recruiter, Hiring Manager or Interviewer), so that only employees can use the system and each sees the right actions.
2. As a visitor, I want there to be no public sign-up page, so that only accounts an Admin created can get in.
3. As any staff member, I want to log in and out, so that my actions are tied to my account.
4. As a Hiring Manager, I want the Openings list to show "My openings" by default, so that I see the openings I'm responsible for first.
5. As a Recruiter or Interviewer, I want the Openings list to show all openings by default, so that I can work across the whole hiring effort.
6. As any staff member, I want to switch between "My openings" and "All", so that ownership helps me filter without ever hiding anything from me.
7. As any staff member, I want each opening to be labelled with its designated authority, so that I know who makes its decisions.
8. As an Interviewer, I want to view candidates, openings, applications and pipelines without being able to change them, so that I can prepare for interviews safely.
9. As any staff member, I want actions I'm not allowed to take to be hidden or refused, so that I can't accidentally make changes outside my role.

### Candidates

10. As a Recruiter, I want to add a candidate with a first name, last name, email and optional phone and notes, so that I have their basic contact information.
11. As a Recruiter, I want each email address to be stored only once, ignoring capital letters, so that the same person isn't entered twice.
12. As a Recruiter, I want to add a candidate before they have applied for anything, so that I can keep promising people on file.
13. As a Recruiter, I want to edit a candidate's details, so that I can correct mistakes.
14. As any staff member, I want to search the candidate list by name or email, so that I can find someone quickly.
15. As a Recruiter, I want to see all of a candidate's applications and their stages on the candidate's page, so that I understand their history with us.
16. As a Recruiter, I want to archive a candidate who no longer needs to be tracked, so that they drop out of everyday lists without being destroyed.
17. As a Recruiter, I want archiving to be blocked while the candidate still has an active application, so that nobody in progress is archived by mistake.
18. As a Recruiter, I want archived candidates to be hidden behind a "Show archived" toggle, so that lists stay clean but nothing is lost.
19. As a Recruiter, I want to unarchive a candidate, so that a returning applicant can be considered again.
20. As a Recruiter, I want the system to refuse new applications for archived candidates, so that the archive keeps its meaning.
21. As any staff member, I want an archived candidate's past applications to still appear on pipeline boards, so that the history of each opening stays complete.
22. As an Admin, I want to permanently delete a candidate only after a confirmation page lists everything that will be destroyed, so that deletion is deliberate and well informed.

### Sources

23. As a Recruiter, I want to choose a source for each application from a managed list, so that we can report on which channels are worth the hiring effort.
24. As a Recruiter or Admin, I want to add new sources, each with a category (Company website, Job board, Referral or Other), so that the list keeps up with how we actually recruit.
25. As a Recruiter, I want source names to be unique regardless of capital letters, so that the list has no near-duplicates.
26. As a Recruiter, I want to rename a source, so that I can fix typos without losing history.
27. As a Recruiter, I want to retire a source instead of deleting it, so that old applications keep their source while new ones can't pick it.
28. As a Recruiter, I want an old application's form to still show its retired source, so that editing it doesn't silently change the data.
29. As a Recruiter, I want a new application's source to be pre-filled from the candidate's previous application, so that data entry is faster.
30. As a Recruiter, I want a "referred by" field to appear when the chosen source is a Referral, so that we can record who referred the candidate.

### Job openings

31. As a Recruiter or Hiring Manager, I want to create a job opening with a title, department, optional location and description, so that we can start hiring for it.
32. As a Recruiter or Hiring Manager, I want every opening to require a designated authority, chosen from active staff who aren't Interviewers, so that someone is always responsible for its decisions.
33. As a Recruiter or Hiring Manager, I want to edit an opening's details, so that I can keep it accurate.
34. As a Recruiter or Admin, I want to change an opening's designated authority, so that responsibility can move when people's roles change.
35. As a new designated authority, I want to get an email when an opening is assigned to me, so that I know I'm now responsible for it.
36. As any staff member, I want to see an opening's history of events (closed, reopened, grace period set, extended or expired, authority changed), so that I understand what has happened to it.

### Skills

37. As a Hiring Manager or an opening's designated authority, I want to attach and detach skills on the opening's page without reloading it, so that the opening lists the right qualifications.
38. As a Hiring Manager or designated authority, I want to create a new skill inline when it doesn't exist yet, so that I'm not blocked by a missing entry.
39. As a Hiring Manager, I want skill names to be unique regardless of capital letters, and the same skill to be shared across many openings, so that skills stay consistent.
40. As a Hiring Manager or Admin, I want to retire a skill so that it can't be attached to new openings while existing openings keep it, so that outdated skills fade out cleanly.
41. As a Recruiter, I want to see an opening's skills as read-only, so that I know the qualifications without being responsible for defining them.

### Applications and the pipeline

42. As a Recruiter, I want to record that a candidate has applied for an open opening, so that they enter the pipeline at Applied.
43. As a Recruiter, I want the system to stop a second application by the same candidate for the same opening, so that there are no duplicates.
44. As a Recruiter, I want the system to stop applications for closed openings, so that closing an opening means something.
45. As any staff member, I want a pipeline board for one opening with a column for each active stage, so that I can see at a glance where every applicant stands.
46. As any staff member, I want Rejected and Withdrawn to be collapsed to a count that I can expand, so that the board stays focused on active applicants.
47. As a Recruiter or Hiring Manager, I want a Move menu on each card that lists only the stages I'm allowed to move to, with tags showing which moves need a note, so that I can move applicants precisely.
48. As a Recruiter or Hiring Manager, I want to drag a card to another column, so that I can move applicants quickly.
49. As a Recruiter or Hiring Manager, I want a move to update the board without a full page reload, so that my work isn't interrupted.
50. As a Recruiter or Hiring Manager, I want a pop-up asking for a note when I skip stages, move backward or reopen an applicant, so that the reason for each unusual move is recorded.
51. As a Recruiter or Hiring Manager, I want to be able to add a note when rejecting or withdrawing someone, so that I can explain if it's useful.
52. As a Recruiter or Hiring Manager, I want a simple one-step forward move to need no note, so that routine work stays fast.
53. As a Recruiter or Hiring Manager, I want to reopen a Rejected or Withdrawn application to an active stage, so that mistakes and changes of heart can be undone.
54. As a Hiring Manager, Admin or an opening's designated authority, I want to be the only one who can move applicants into Offer or Hired, so that offers are made by people with that authority.
55. As anyone, I want Hired to be reachable only from Offer and to be final, so that hires are deliberate and can't be undone by accident.
56. As any staff member, I want every application to have a complete history of stage changes (from, to, who, when, note and cause), so that every decision can be traced.
57. As any staff member, I want illegal moves to be refused with a clear message even if someone gets around the menu, so that the rules always hold.

### Closing openings

58. As a Recruiter, Hiring Manager or Admin, I want to close an opening, so that it stops taking new applications.
59. As a Hiring Manager, I want applicants already in progress to keep moving after closing, including into Offer and Hired, so that closing doesn't break hires that are underway.
60. As a designated authority, I want to be told when my opening is closed with applicants still in progress, both in an in-app "Needs attention" panel and by email, so that I know a decision is waiting.
61. As a designated authority, I want to give remaining applicants a grace period of a set number of days, so that they have time to finish the process.
62. As a designated authority, I want to choose whether the end of the grace period auto-cancels the remaining applications or just flags them as overdue, so that the outcome fits the role.
63. As a designated authority, I want to extend a grace period with a note, so that I can allow more time when it's justified.
64. As a designated authority, I want to cancel all remaining applications at once, which moves them to Rejected with the note "Position closed." and a closure cause, so that I can end the process cleanly.
65. As a Recruiter, I want to be able to close an opening but leave the decision about its applicants to the people with authority, so that responsibilities stay clear.
66. As a candidate (who never logs in), I want an email when a grace period is set, 3 days before it ends and 1 day before it ends, stating the consequence ("will be closed" or "may be closed"), so that I know what's happening and how long I have.
67. As a candidate, I want an email if my application is cancelled because the position closed, so that I'm not left wondering.
68. As a candidate, I want the emails to say "our team will be in touch to complete the next step", so that I know I don't need to do anything in a system.
69. As a staff member, I want each candidate email to be logged and never sent twice, so that we have a record and candidates aren't spammed.
70. As a designated authority, I want an in-app notice and an email when a flag-only grace period becomes overdue, so that I can follow up.
71. As an Admin, I want an in-progress view of closed openings that still have active applicants, each marked Awaiting decision, In grace period or Overdue, so that nothing falls through the cracks.
72. As an operator, I want a daily command that runs auto-cancellations and sends reminders, and that is safe to run more than once, so that grace periods are enforced reliably.

### Reopening openings

73. As anyone who can close an opening, I want to reopen it, so that hiring can resume.
74. As a designated authority, I want reopening to clear the grace period and stop reminders, so that candidates don't get outdated warnings.
75. As a designated authority, I want to tick which applicants cancelled at the latest closure should be restored, so that I choose who returns to the pool.
76. As a designated authority, I want each restored applicant to go back to the stage they were at before the closure, so that their progress isn't lost.
77. As a candidate, I want a "position reopened" email when I'm restored, so that I know I'm being considered again.
78. As a designated authority, I want restoring someone into Offer to still require offer authority, so that the offer rule can't be bypassed.
79. As a designated authority, I want archived candidates to appear in the restore list but be disabled with "Archived; unarchive first", so that I understand why they can't be restored.
80. As a Recruiter who reopens an opening, I want the restore choice to go to the designated authority's Needs attention panel, so that the right person decides.

### Staff departure

81. As an Admin, I want to deactivate a departing staff member only after picking a new designated authority for each of their openings, all in one step, so that no opening is left without an authority.
82. As an Admin, I want the plain "active" checkbox in the Django admin to be read-only, so that nobody deactivates staff without reassigning their openings.
83. As any staff member, I want each reassignment logged in the opening's event history, so that changes of responsibility are traceable.

## Implementation Decisions

### Stack and tooling
- Python, Django, SQLite, uv, Tailwind CSS with DaisyUI via django-tailwind-cli, HTMX, Ruff, and Pytest (with pytest-django). All of these are required.
- Email goes through Django's mail framework: the console backend in development and the in-memory (locmem) backend in tests.

### Roles and permissions
- Roles are Django Groups: Recruiter, Hiring Manager and Interviewer. Admin is the superuser flag. There is no self-registration.
- Access is hybrid: every role can view everything, and Interviewers can only view. Ownership changes default filters and labels but never blocks viewing.
- The permission matrix is the one recorded in HANDOFF.md (decision 3). In summary: Admins and Recruiters manage candidates, sources, applications, archiving and authority assignment; Admins, Recruiters and Hiring Managers create and edit openings, close and reopen them, and move stages (except into Offer and Hired); only Admins permanently delete candidates and manage staff.
- Permission rules live in pure, separately testable functions, which views and templates call:
  - `can_make_offer(user, opening)`: an Admin, a member of the Hiring Manager group, or the opening's designated authority.
  - `can_manage_opening_skills(user, opening)`: the same three. Covers attaching, detaching and creating skills. Retiring a skill is limited to Admins and the Hiring Manager group.
  - `can_decide_closure(user, opening)`: the same three. Covers setting, extending and cancelling grace periods, and restoring applicants.
- Interviewers have no feedback or notes feature.

### Data model
- **Candidate:** first name, last name, email (required, unique, stored lowercased), optional phone, optional notes, `is_archived`, `archived_at`, and created and updated timestamps. No résumé, LinkedIn or location fields.
- **Source:** name (unique ignoring case, enforced by a database constraint on the lowercased name), category (text choices: Company website, Job board, Referral, Other), and `is_active`. Sources are never deleted; foreign keys to them use PROTECT.
- **Skill:** name (unique ignoring case) and `is_active`. Retired skills use PROTECT.
- **JobOpening:** title, department (text), optional location (text), description, status (open or closed), a required designated authority (a foreign key to User with PROTECT, limited to active staff who aren't Interviewers), a many-to-many link to Skill, `grace_period_ends` (a date in the project time zone, may be empty), `grace_expiry_action` (auto-cancel or flag overdue), and timestamps.
- **Application:** candidate, opening, source (PROTECT), optional `referred_by` text, a cached `stage`, and timestamps. A unique constraint on (candidate, opening).
- **StageChange:** application, from stage (empty for the first row), to stage, changed by, changed at, note, and cause (manual or closure). Creating an application writes an empty → Applied row.
- **OpeningEvent:** opening, kind (closed, reopened, grace period set, grace period extended, grace period expired, authority changed), by, at, note.
- **CandidateMessage:** candidate, application, kind, subject, body, sent at. Uniqueness on the message identity prevents the same email being sent twice.

### Stage rules (a pure module)
- Active stages: Applied, Screening, Interview, Final Review, Offer. Terminal stages: Hired, Rejected, Withdrawn.
- An allowed-transitions table plus pure functions `can_move(from, to)` and `requires_note(from, to)`:
  - any active stage can move to any other active stage;
  - any active stage can move to Rejected or Withdrawn;
  - Rejected or Withdrawn can be reopened to any active stage;
  - Hired is reachable only from Offer and is final.
- A note is required for skips, backward moves and reopens; optional for Rejected or Withdrawn; not needed for a one-step forward move.
- Moving into Offer or Hired also requires `can_make_offer()`.

### Services (the deep modules that hold the business logic)
- `move_application(application, to_stage, by, note, cause)`: the *only* way a stage changes. It checks the rules and permissions, writes the StageChange row and updates the cached stage inside one database transaction.
- `cancel_remaining_applications(opening, by)`: moves every active application to Rejected with cause closure and the note "Position closed.", and queues cancellation emails.
- Closure operations (close, set grace period, extend, cancel now, reopen, restore selected) each write OpeningEvent rows and go through `move_application()`. A restore uses the stage recorded in the application's latest closure-cause StageChange row.
- `deactivate_staff(user, reassignments, by)`: needs a new authority for each of the user's openings, reassigns them, logs OpeningEvents, emails the new authorities and deactivates the user, all in one transaction.
- A candidate-messaging service builds, sends and logs each candidate email and skips any message that has already been sent.
- A management command `process_grace_periods`, run daily, performs auto-cancellations for expired grace periods, marks flag-only grace periods as overdue (with a staff notification) and sends the 3-day and 1-day reminders. Running it more than once changes nothing extra.

### Screens and interactions
- **Openings list:** a My openings / All toggle (the default depends on role) and an authority label on each opening.
- **Opening detail:** a details form (no skills in it), a separate Skills section edited inline with HTMX (read-only for those without permission), the event history, close and reopen actions, and closure decision controls for authorised users.
- **Pipeline board (one opening):** stage columns, with Rejected and Withdrawn collapsed to an expandable count. Each card has a Move ▾ menu listing only legal targets, tagged when a note is needed, plus native browser drag-and-drop (no SortableJS). Both post to one HTMX endpoint, which re-renders the affected cards and columns. Moves that need a note open a DaisyUI modal first. Illegal moves are refused on the server.
- **Candidate list:** name and email search, and a "Show archived" toggle. **Candidate detail:** contact details, applications, and archive or unarchive actions. **Permanent delete:** an Admin-only confirmation page that lists the applications, stage history and messages that will be destroyed.
- **Application form:** the source is pre-filled from the candidate's most recent application, a "referred by" field appears for Referral sources, the form refuses closed openings and archived candidates, and an existing application's retired source is still shown.
- **Needs attention panel:** for designated authorities and decision makers. It shows closures awaiting a decision, overdue grace periods and pending restore choices.
- **Admin in-progress view:** closed openings with active applicants, each with a status of Awaiting decision, In grace period or Overdue.
- The Django admin's `is_active` field on users is read-only; deactivation goes through the staff-departure flow.

### Candidate email schedule
- When a grace period is set; 3 days before it ends ("will be closed" for auto-cancel, "may be closed" for flag-only); 1 day before it ends; on cancellation; on restore after a reopen.
- Wording tells candidates "our team will be in touch to complete the next step". Candidates never take action in the system.
- Normal rejections and hires send no email.
- If a grace period is shorter than 3 days, any reminder whose date has already passed is skipped.

### Testing
- Pytest with pytest-django, plain fixtures, and parametrized tests for the pure stage-rule and permission functions.
- Service-level tests for `move_application`, closure and cancellation, grace-period processing (including running it twice), reopen and restore, candidate messaging (using the locmem outbox, with no duplicates) and `deactivate_staff`.
- View tests for permission enforcement and HTMX responses.
- Drag-and-drop is covered by a manual browser checklist, not browser automation.

## Out of Scope

- Any candidate-facing portal, login or self-service application form.
- Résumé upload, LinkedIn, location or other extra candidate fields.
- Interviewer feedback, scorecards or notes.
- Public sign-up or self-service account creation.
- Pipeline boards that span several openings.
- Emails for normal rejections and hires.
- Browser automation tests (Playwright or similar) for drag-and-drop.
- A default timeout or automatic action when nobody decides what happens to a closed opening's applicants.
- Production deployment details, including SMTP configuration and how the daily command is scheduled.
- Analytics dashboards. Source data is captured for reporting, but no reporting screens are specified here.

## Further Notes

- **Still open (decide before or during planning):**
  - the Openings list layout (three variants in the openings-ownership prototype);
  - how the code is split into Django apps, and the URL design;
  - seed and demo data;
  - production SMTP settings, and whether the daily command is scheduled with Windows Task Scheduler or cron.
- **Assumed defaults, not explicitly confirmed:** reminders are skipped for grace periods shorter than 3 days; `grace_period_ends` is a date in the project time zone; normal rejections and hires send no email; the candidate list has name and email search; tests use pytest-django with plain fixtures.
- The prototypes in the prototypes folder are reference only and must not be promoted to production code. The pipeline-board prototype's variants A and B combined are the chosen direction for the board.
- Suggested next step: `/prd-to-plan` to break this PRD into tracer-bullet phases.
