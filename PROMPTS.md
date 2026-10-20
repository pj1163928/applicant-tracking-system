# PROMPTS.md — AI Usage Log

This file is the record of AI use on this codebase. At the end of every
agent session, direct the agent to write the session log with this prompt:

> Append a session log to PROMPTS.md at the repo root, under today's date,
> newest entry at the top. Record every prompt I gave you this session, in
> order, including any corrections. End the entry with a short summary:
> the outcome, any places where I deviated from a recommended answer or
> asked follow-up questions, and anything that went sideways.

Two rules:

- Entries are added only by that prompt, never unprompted.
- New entries go at the top. Never rewrite or delete an old entry — the
  log is part of your work, and an honest log of a session that went
  sideways is worth more than a tidy one.

Each entry has this shape:

    ## YYYY-MM-DD — <one-line summary>

    ### Prompts
    1. ...

    ### Summary
    - **Outcome:** what was built and what was kept
    - **Deviations:** recommendations overridden, follow-up questions asked
    - **Sideways:** failures, wrong turns, and how they were caught

## 2026-10-19 — Applicant Tracking System: Phase 2/14, Candidates

### Prompts

1. The `/implement` skill, given `applicant-tracking system phase 2`.
2. Yes I approve continue development
3. Yes continue to the next test
4. Ok one minor suggestion for the test make sure that the test isolates the databse state for each role. Also you can use PermissionDenied or an equivalent authorization check tomake sure it runs HTTP 403 rather than redirecting unauthorized user to a login page.
5. Yes go ahead and continue
6. Ok everything looks good, this is strictly for futre purposes but I would like to change implement slightly i the way that it uses pytest and full suite checks. It seems to be taking a long time for test to be run, and for the sake of quicker development can we save full suite tests till then end or when issues are abhorently apparent, othersiwe only run tests associated with the feature that is being developed then run a full suite test at the end.
7. Go ahead and implement conftest.py
8. Go ahead and append this part of the conversation to prompts.md as well

### Summary

- **Outcome:** A new `candidates` app. Recruiters and Admins add and edit candidates (first name, last name, email, optional phone and notes). Everyone can browse the list, search it by name or email (live, through HTMX), and open a detail page, which has an empty Applications section until Phase 5. Hiring Managers, Interviewers and users without a role don't see Add or Edit, and get a 403 if they request those pages directly. Emails are stored in lowercase and are unique regardless of capitals, enforced by the database, and the form shows "A candidate with this email already exists." `seed` adds 10 sample candidates and stays idempotent. 110 tests pass (60 new); `ruff check` and `ruff format` are clean. All five Phase 2 acceptance criteria are ticked.
- **Changes:**
  - `candidates/` (new app): `models.py` (`Candidate` with `unique=True` on email, a `candidate_email_lowercase` check constraint, lowercasing in `clean()` and `save()`, and a `search()` queryset that matches every word against first name, last name or email); `forms.py` (`CandidateForm` with DaisyUI classes, marking invalid inputs with `input-error` and `aria-invalid`); `views.py` (thin class-based list, detail, create and update views; the list returns only the results partial for HTMX requests, but the full page for history restores, and sends `Vary: HX-Request`); `urls.py` (`candidates:list`, `create`, `detail`, `update`); `admin.py`; `migrations/0001_initial.py`; `templates/candidates/` (list, results partial, detail, form).
  - `accounts/permissions.py` (new): `CANDIDATE_MANAGER_ROLES` and `can_manage_candidates(user)`, the first action rule and the pattern for later ones.
  - `accounts/templatetags/accounts_tags.py`: a `can_manage_candidates` filter, so templates hide Add and Edit using the same rule.
  - `accounts/management/commands/seed.py`: `SEED_CANDIDATES` (10 people, some without a phone or notes) and `seed_candidate()`, found by email and updated only where fields differ.
  - `config/settings.py`, `config/urls.py`: register the app and mount it at `/candidates/`.
  - `templates/partials/nav_links.html`: a Candidates link, marked current on any candidates page.
  - `templates/icons/`: 9 Lucide icons copied from lucide-static v1.49.0 (search, user-plus, pencil, mail, phone, arrow-left, notebook-pen, inbox, save).
  - Tests: `candidates/tests/test_models.py`, `test_forms.py`, `test_views.py`; `accounts/tests/test_permissions.py` (new); `accounts/tests/test_seed.py` (candidates added to the idempotency snapshot, plus creation and repair tests).
  - `CLAUDE.md`, `docs/TESTING.md`, `README.md`: document `accounts.permissions` and the new filter, and update the status, features and layout.
  - `plans/applicant-tracking-system.md`: Phase 2 criteria ticked.
- **TDD:** The plan's two candidates, each red on an assertion and then green:
  1. *Email stored lowercase and unique regardless of case.* The test creates `Ann@X.com`, checks it's stored as `ann@x.com`, then adds `ANN@x.COM` with `bulk_create` (which skips `save()`) and expects an `IntegrityError`. So only a real database rule can pass it. The fix: lowercase in `save()`, plus a check constraint that the email equals its lowercase, alongside `unique=True`.
  2. *Only Recruiters and Admins can create or edit candidates.* A test parametrized over five roles, each making a GET and a POST to both Add and Edit. It checks the statuses (`[200, 302, 200, 302]` or four 403s) and that refused roles changed nothing. The fix: `RoleRequiredMixin` with `allowed_roles = CANDIDATE_MANAGER_ROLES` on both views.
- **Decisions:** Archive fields (`is_archived`, `archived_at`) wait for Phase 9, as the plan says each phase adds only what it needs. Case-insensitive uniqueness uses "always lowercase" (a check constraint) plus `unique=True`, so the form's error lands on the email field. Search requires every word to match somewhere, so "ann lee" finds Ann Lee. The list is sorted by last name with no pagination yet. Saving redirects to the detail page with a success message. Delete stays in Phase 9. The agent regenerated `0001_initial` twice while building, as it hadn't been applied anywhere yet.
- **Deviations:** None from the plan. At the RED step of TDD cycle 2, I asked for two things. First, prove that each role's run starts from an isolated database: the agent added a starting-state assertion, since pytest-django already rolls back each parametrized run. Second, make refusal an HTTP 403 rather than a redirect to login: this was already the case, because `RoleRequiredMixin` sets `raise_exception = True`, so Django raises `PermissionDenied`, and the test asserts exactly 403.
- **Sideways:** Ruff's DJ012 rule flagged the model's method order (`save` and `get_absolute_url` must come before custom methods); fixed by moving `full_name` to the end. The first headless-Edge screenshots looked washed out because they caught the `animate-rise` fade mid-way; they were retaken with a virtual time budget. The screenshots also showed the duplicate-email input wasn't outlined in red, so the form now adds `input-error`. The first version built that class name with an f-string, which Tailwind couldn't see (`textarea-error` was missing from the built CSS), so the class names are now written out in full. The first attempt to write this log hung on a stray `cat` waiting for input; it was stopped before touching PROMPTS.md and redone. The dark theme's active nav link (from Phase 1) has low-contrast text; it was noted and left alone.
- **Follow-up (prompts 6–8), faster test runs:** 110 tests pass in 0.53s, down from about 48s; Ruff is clean.
  - `.claude/skills/implement/SKILL.md`: during a build, run only the tests for what the phase touches (its app, one file, or `-k`, plus tests of any shared module changed). Run the full suite once at the end, or earlier only when something points to a cross-app break, such as a failing import or migration, or a change to settings, `base.html`, `accounts.roles`, `RoleRequiredMixin` or `conftest.py`. The full suite must still be green before finishing.
  - `.claude/skills/tdd/SKILL.md`: the regression check after each GREEN covers the changed app or module, not the full suite.
  - `conftest.py`: an autouse `fast_password_hashing` fixture switches tests to Django's MD5 hasher. The agent traced the slowness to password hashing: the 5 seed tests took about 24s of the 48s, because the default hasher is deliberately slow. Real logins and the `seed` command still use the secure default.
  - `docs/TESTING.md`: notes the fixture and why it exists.
  - **Deviations:** None. I asked to change the skill, and the agent offered the hasher fix as a further speed-up, which I accepted.

## 2026-10-19 — Applicant Tracking System: Phase 1/14, Project skeleton, staff login and roles

### Prompts

1. The `/implement` skill, given `applicant-tracking-system phase 1`.
2. Continue on with the build
3. Ok the page loaded good but I do want to improve the look of the ATS slightly as it looks sort of bland and boring. maybe including some iconography subtle animations and logos, also I would like you to edit the README. For the layout I would like it to be accesible on large or small screens so I feel this is a good time to mention this before we get to far into things. Ideally a sidebar menu on smaller screens and topbar naviation manu on other screens

### Summary

- **Outcome:** A running Django 6.1 project (Python 3.13, uv) with Ruff, Pytest/pytest-django and Tailwind + DaisyUI v5 through django-tailwind-cli 4.8. It has staff login and logout with no sign-up page, and every view requires a login. The three role groups are created by a data migration. The base layout has a navbar with the user's name, role badge, logout button and light/dark toggle, and loads HTMX. A shared `RoleRequiredMixin` returns 403 to Interviewers, and an idempotent `seed` command creates one user per role. 43 tests pass; `ruff check` and `ruff format` are clean. All six Phase 1 acceptance criteria are ticked.
- **Changes:**
  - `pyproject.toml`, `uv.lock`, `.python-version`: the uv project, dependencies, and Ruff and pytest settings.
  - `manage.py`, `config/settings.py`, `config/urls.py`, `config/asgi.py`, `config/wsgi.py`: project settings, including `LoginRequiredMiddleware`, `TIME_ZONE = "America/Chicago"`, Tailwind/DaisyUI settings and the console email backend.
  - `accounts/roles.py`: pure role checks (`is_admin`, `has_role`, `can_make_changes`, `role_label`) and the role constants.
  - `accounts/mixins.py`: `RoleRequiredMixin`, the shared server-side refusal (403) for Interviewers, which later views narrow with `allowed_roles`.
  - `accounts/templatetags/accounts_tags.py`: the `role_label` and `can_make_changes` filters, so templates reuse the same rules.
  - `accounts/views.py`, `accounts/urls.py`: the home page (`accounts:home`), login and logout. There is no sign-up route.
  - `accounts/migrations/0001_create_role_groups.py`: a data migration that creates Recruiter, Hiring Manager and Interviewer.
  - `accounts/management/commands/seed.py`: an idempotent seed that creates admin, recruiter, manager and interviewer with the password `demo-pass-123`.
  - `templates/base.html`, `templates/registration/login.html`, `templates/accounts/home.html`: the layout, the login page and the welcome page.
  - `assets/css/source.css`: the Tailwind source with the DaisyUI `corporate`/`business` themes. `static/css/.gitkeep` holds the built-CSS folder.
  - `conftest.py`, `accounts/tests/`: role fixtures plus tests for the role functions, groups, mixin (through the test-only `accounts/tests/urls.py`), login/logout/no-sign-up/layout, and seed idempotency.
  - `docs/TESTING.md`: the new testing guide. `CLAUDE.md`: new Conventions, Commands and "Read before…" sections.
  - `.gitignore`: ignores the downloaded Tailwind binary and the built CSS.
  - `plans/applicant-tracking-system.md`: Phase 1 criteria ticked.
- **Follow-up (prompt 3), visual polish and responsive layout:** 49 tests pass; Ruff is clean.
  - `templates/skeleton.html` (new): the page shell, with the theme script, HTMX, the favicon and a skip link. Login extends it directly.
  - `templates/base.html`: now a DaisyUI drawer. Below `lg` there is a menu button and a slide-in sidebar with the logo, a user card, nav, Manage staff and Log out; at `lg` and up there is a sticky top bar with horizontal nav. Content enters with a subtle `animate-rise`, and there is a footer.
  - `templates/partials/` (new): `nav_links.html` (one list shared by both menus, with `aria-current` on the active link), `logo.html` (a gradient briefcase mark that tilts on hover), `avatar.html` (initials), `theme_toggle.html` and `messages.html`.
  - `templates/registration/login.html`: a gradient brand panel on large screens, plus inputs with icons and a log-in icon button.
  - `templates/accounts/home.html`: a welcome card with an accent stripe, avatar and role badge, and an info alert with an eye icon for view-only users.
  - `config/templatetags/icons.py` (new): the builtin `{% icon %}` tag, which inlines SVGs from `templates/icons/` (14 icons from lucide-static v1.49.0, downloaded at a pinned version, ISC license). `config/settings.py` registers it.
  - `static/img/logo.svg` (new): the favicon. `assets/css/source.css` defines the `rise` keyframes, with `motion-reduce:` fallbacks throughout.
  - `config/tests/test_icons.py` (new), `accounts/tests/test_auth_views.py`: tests for the icon tag, the drawer and sidebar markup, and the login page having no nav.
  - `README.md` rewritten (features, stack, setup, demo accounts, layout, credits). `CLAUDE.md` conventions now cover templates, icons and motion.
- **TDD:** Skipped, as the plan says: Phase 1 is setup and configuration. The login redirect and the Interviewer 403 got ordinary tests.
- **Decisions:** Kept Django's built-in `User` model. Required a login everywhere through `LoginRequiredMiddleware`. Put the home page at `/` as `accounts:home`. `RoleRequiredMixin` refuses Interviewers and users without a role by default, and is tested through a test-only URLconf instead of a dummy app view. Logout is a POST form. Used DaisyUI `corporate` (light) and `business` (dark) to match the prototypes, with the choice remembered in localStorage. HTMX is pinned to 2.0.4 on jsDelivr, with CSRF sent through `hx-headers`. Seed usernames are admin, recruiter, manager and interviewer; re-running only fixes fields that differ. Used Django 6.1's generated `MAILERS` email setting.
- **Deviations:** None. The brief was approved as proposed. After the build, I asked for more visual polish (icons, subtle animations, a logo), a README rewrite, and a responsive layout: a sidebar on small screens and a top bar on larger ones. The agent used lg (1024px) as the switch point, Lucide for icons, and a gradient briefcase logo mark.
- **Sideways:** The first login template used DaisyUI v4 classes (`form-control`, `label-text`, `input-bordered`), which v5 removed. This was caught before building and switched to v5 `fieldset` markup. The first `tailwind build` seemed to hang and was stopped. It was downloading the 112 MB Tailwind CLI with no visible output, and a re-run in the background finished fine. During the polish, headless-Edge screenshots caught a stretched, pill-shaped avatar: DaisyUI only styles `div` children of `.avatar`, so the `span` markup was switched to `div`. They also caught a stray period after the role badge and a harsh black active-nav pill, now tinted with the primary color. Phone screenshots first looked cropped; headless Edge can't make a window narrower than about 500px, so they were retaken inside a 390px iframe. One shell heredoc failed to parse, wrote nothing, and was redone with the file tool.

## 2026-10-19 — /to-prd and /prd-to-plan: PRD and 14-phase plan with TDD candidates

### Prompts
1. `@HANDOFF.md /to-prd`
2. Ok the PRD looks good now move to planning using /prd-to-plan then write the conversation log to PROMPTS.md as well as any message here-after
3. Alright this plan looks good, another thing I would like to settle is phases that would require TDD using the /tdd skill can you include which parts of the plan may require TDD

### Summary
- **Outcome:** Wrote `prd/applicant-tracking-system.md` from HANDOFF.md: 83 user stories, implementation decisions, out of scope, and open questions. Ran `/prd-to-plan` and wrote `plans/applicant-tracking-system.md`: architectural decisions (5 Django apps: accounts, candidates, openings, applications, notifications; namespaced pk-based URLs; Groups-based auth; deep modules; a `seed` command) and 14 tracer-bullet phases with acceptance criteria. At my request each phase now has a **TDD** section listing up to three candidate behaviors for `/tdd`, following that skill's limit, or the reason it has none. Phases 1 (setup) and 7 (browser drag-and-drop) have no TDD; Phase 6 (stage rules, `can_make_offer`, `move_application`) is marked as the most important TDD phase.
- **Decisions:** The agent filled gaps HANDOFF.md had left open: the app split and URL design; a `seed` command from Phase 1 (the `/implement` skill expects one); and `CLAUDE.md` plus a testing guide in Phase 1 (`/implement` reads both). The Openings list layout is deferred to the start of Phase 4.
- **Deviations:** None. The PRD and the 14-phase breakdown were accepted as proposed.
- **Sideways:** None.

## 2026-10-19 — /grill-me design interview for the ATS (23 decisions, 3 prototypes)

### Prompts
1. `/grill-me` I would like you to guide me over some design decisions for my new project which is an applicant tracking system ATS. before questioning there are a few technological and functional requirements that must be met before we go onto the design.
   Technology Stack: Python, Django, SQLite, UV, Tailwind CSS with DaisyUI using django-tailwind-cli, HTMX, Ruff, Pytest - For testing which is a requirement.
   Business Requirements:
   1. This is an internal hiring system. It will be used by employees involved in the hiring process. Candidates will not log in to the system.
   2. Staff need to keep track of candidates and their basic information. Candidates may come from the company website, job boards, referrals, or other outside sources.
   3. Staff need to create and edit job openings. A job opening can be open or closed.
   4. Staff need to record when a candidate applies for a job opening. A candidate may apply for several different jobs, but should not have more than one application for the same opening.
   5. Applications move through a defined hiring process. The system must include these stages: Applied, Screening, Interview, Final Review, Offer, Hired, Rejected, and Withdrawn.
   6. Staff need an easy way to see where applicants are in the hiring process and move them from one stage to another. Moving an applicant should not require reloading the entire page.
   7. The system needs to keep track of the skills associated with each job opening. The same skill may apply to many different openings.
   8. We need to decide how candidate records should be managed over time. For example, we have not decided when a candidate should be edited, archived, deactivated, or removed.
   9. We need to decide what happens when a job opening closes. Existing applications may still be in progress, and an opening may or may not be allowed to reopen.
2. C *(Q1 roles)*
3. Regarding hybrid permisssions and assigning an owner to a staff opening, would /prototype help visualize this view and what it may look like?
4. I have the prototype folder with a SKILL.md file in it can you please check again and make sure that the formatting is correct and re-answer my question
5. Go ahead and prototype your reccomended outlook also edit the delimeter so you do not have trouble accessing it in future conversations
6. I like option C the hybrid approach *(Q2 access)*
7. A *(Q3 permission matrix)*
8. A *(Q4 candidate identity)*
9. I am leaning towards A but am having a hard time visualizing it can you use /prototype to give me an idea of the rules and how it would look
10. I feel like for this one B would not be a bad idea, I feel that a companies hiring decisions actually may change and there sources may be something they want to keep track of to prioritize where they should focust there hiring efforts. So for this one I will lock in B allowing Admins and Recruiters to add additional sources for applicants to choose from. *(Q5 sources)*
11. B *(Q6 source on application)*
12. A *(Q7 source categories)*
13. A *(Q8 retiring sources)*
14. A - I feel for this one it is company dependent, some may not have a hiring manager, I think this would be good to expand on slightly by adding another option as a designate authority and selecting a member of staff from the list. *(Q9 opening owner)*
15. B *(Q10 designated authority powers)*
16. C - For this one I do want to keep it somewhat noted as to why they are backtracking or why they are being expedited, for this decision please make it a requirement that a note be placed if a non-linear advancement is being made. *(Q11 stage transitions)*
17. B *(Q12 stage history)*
18. B - One opening - Collapsed with count and expandable, So far I like your reccomendations, but it is hard for me to visualize, can you give me a prototype of each of these to give me an idea of how the hiring stages would work visually with Kanban boards. *(Q13 pipeline UI)*
19. Ok after testing this I think that a combination of A and B would be a good fit despite neeing some extra code, as it would fit the needs of power users and people just wanting to quickly move candidates through drag and drop *(Q13 final)*
20. A - Hiring Managers and Designate Authorities should be the ones who add or retire skills, as most recruiters know only a littlle about the position qualifications *(Q14 skills)*
21. B *(Q15 skill permissions)*
22. B *(Q16 candidate lifecycle)*
23. B - I feel that this one is also about grace periods, if an application is in progress it should notify the hiring manager of designee that there are X amount of pending applications, it should then given them the option to provide a grace period specifying how many days they have to complete the application, or to outright cancel their application and send the applicant a message that the position has been closed, it should also let admins see who is still on the board as well and is listed as In-Progress. *(Q17 closing)*
24. Lets have a combination of A and B - This allows the hiring manager or designee to statewhat they would like to do auto cancel or set an overdue flag at the end of the grace period. There should also be sufficient messages before a closing date, stating to the applicant that a position is closing and any consequences of not completing their application. *(Q18 grace expiry)*
25. A - with the provided schedule *(Q19 candidate messaging)*
26. C *(Q20 staff notifications)*
27. C - This would allow the hiring manager or designee to select/checkbox which employees they would like to add back to the hiring pool if they exist. Sub Question: Yes *(Q21 reopening)*
28. A *(Q22 archived applicants on restore)*
29. B *(Q23 staff departure)*
30. `/handoff` The next session will use the /to-prd skill to begin creating a PRD. Please append the conversations in this chatlog to PROMPTS.md according to the source formatting.

### Summary
- **Outcome:** Completed a 23-question design interview covering all nine business requirements; no application code was written. Built three throwaway prototypes in `prototypes/`: `openings-ownership.html` (hybrid ownership, 3 UI variants), `candidate-source.html` (source rules, logic walkthrough), `pipeline-board.html` (kanban drag-and-drop vs move menu vs table, shared transition rules). Removed `disable-model-invocation: true` from `.claude/skills/prototype/SKILL.md` at my request. Wrote `HANDOFF.md` with the full decision list for the `/to-prd` session.
- **Deviations:** Overrode recommendations on Q1 (named roles, C, instead of single role A), Q5 (Source table, B, instead of fixed choices A), Q13 (move menu plus drag-and-drop instead of menu only), Q21 (selective restore on reopen, C, instead of B). Expanded recommendations on Q9 (designated authority can be any non-Interviewer staff, not only Hiring Managers), Q11 (required note for skip, backward and reopen moves), Q14/15 (skills managed by Hiring Managers and designated authority, not Recruiters), Q17/18 (grace periods with per-opening auto-cancel or overdue flag, candidate warning emails, Admin in-progress view). Asked for prototypes three times to visualize decisions (Q2, Q5, Q13). Several sub-questions went unanswered and were taken as the agent's recommended defaults (listed in `HANDOFF.md`).
- **Sideways:** The agent first said no `/prototype` skill existed. It did, but `disable-model-invocation: true` hid it from the agent's skill list; caught when I asked it to check the folder, and fixed by removing that line. The agent did not visually verify any prototype in a browser; a dropdown-reset bug in `candidate-source.html` was found by code review and fixed after the file had already been opened, so a refresh was needed. In prompt 27 I wrote "employees" meaning applicants; the agent assumed that reading and said so.