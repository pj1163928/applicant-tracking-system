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

## 2026-10-20 — Applicant Tracking System: Phase 9/14, Candidate lifecycle

### Prompts

1. The `/implement` skill, given `applicant-tracking-system phase 9`.
2. Looks good also ensure that move_refusal blocks archived candidates on the server side, not just hiddent on the board.
3. looks good move to next
4. Looks good continue
5. Looks good move to next

### Summary

- **Outcome:** Candidate lifecycle: archive, unarchive and permanent delete.
  - **Archive and unarchive.** Recruiters and Admins get Archive and Unarchive buttons on a candidate's page.
    - Archiving is refused while any application is at Applied, Screening, Interview, Final Review or Offer. The page hides the button and says why.
    - An archived candidate's page shows an "Archived on …" banner and can't record a new application.
  - **The list.** Archived candidates are hidden by default. The count says how many are hidden, and a "Show archived" toggle (HTMX, combined with the search) lists them with an "Archived" badge. They're always reachable by URL.
  - **No new applications.** They're refused in four places:
    - `application_refusal` (shared by the form and `record_application`, which now re-reads the candidate under a lock);
    - the form's candidate dropdown;
    - the create page started with `?candidate=`;
    - the "Record application" action.
  - **Boards and opening pages** keep an archived candidate's cards, with an "Archived" badge.
    - Their cards have no Move menu and can't be dragged, and staff who could move them see "Unarchive Kai to move this card."
    - **Server-side refusal (prompt 2):** `move_refusal` itself refuses any move for an archived candidate, so a hand-made POST gets a 400 with "… is archived, so their applications can't be moved. Unarchive them first."
  - **Permanent delete (Admins only).** A "Delete permanently" area on the candidate page links to `/candidates/<pk>/delete/`.
    - The confirmation page lists each application with its stage, source and full stage history, plus counts.
    - Confirming deletes everything in one transaction and returns to the list, with a message saying what was removed.
    - Everyone else gets a 403 for GET and POST, and the Django admin lets only Admins delete.
  - **Seed:** a new candidate, Kai Moreno, withdraws from Backend Developer and is then archived.
  - **Checks:** 657 tests pass (64 new). `ruff check` and `ruff format` are clean. One migration (`candidates/0003_candidate_archiving`). The dev database was migrated and seeded twice; the second run changed nothing.
  - **Criteria:** five of six are ticked. The delete criterion stays unticked until Phase 10 adds candidate messages to the confirmation page.
- **Changes:**
  - `candidates/models.py`:
    - `is_archived` and `archived_at`, and a `candidate_archived_has_date` check constraint that keeps them in step;
    - `CandidateQuerySet.unarchived()`.
  - `candidates/migrations/0003_candidate_archiving.py`: the two fields and the constraint.
  - `candidates/services.py` (new): `archive_refusal`, `archive_candidate`, `unarchive_candidate`, `DeletionSummary`, `deletion_summary` and `delete_candidate`. Each one checks its permission on the server.
  - `accounts/permissions.py`:
    - `CANDIDATE_DELETER_ROLES = ()` and `can_delete_candidates` (active Admins only; `is_staff` never counts);
    - `can_manage_candidates` now also covers archiving.
  - `accounts/templatetags/accounts_tags.py`: the `can_delete_candidates` filter.
  - `applications/services.py`:
    - the `ARCHIVED_CANDIDATE` reason, in `application_refusal` and `move_refusal`;
    - `openings_open_to` returns nothing for an archived candidate;
    - `record_application` locks and re-reads the candidate.
  - `applications/forms.py`: the candidate dropdown uses `Candidate.objects.unarchived()`, with its own invalid-choice message.
  - `applications/views.py`: the create page refuses `?candidate=` for an archived candidate.
  - `applications/board.py`: each card gets `movable` (its column has Move targets and its candidate isn't archived).
  - `applications/templates/applications/partials/card.html`: uses `movable`, and adds the badge and the "Unarchive … to move" line.
  - `candidates/views.py`:
    - the list's `?archived=1` toggle and its counts;
    - `archive_refusal` on the detail page;
    - `CandidateArchiveView` (archive and unarchive) and `CandidateDeleteView`.
  - `candidates/urls.py`: `archive`, `unarchive` and `delete`.
  - Templates:
    - `candidate_list.html` (the toggle), `partials/results.html` (counts and badges) and `candidate_detail.html` (banner, buttons, the delete area);
    - new `candidate_confirm_delete.html` and `partials/archived_badge.html`;
    - a badge on `openings/jobopening_detail.html`;
    - icons `trash-2.svg` and `triangle-alert.svg`, copied from lucide-static v1.49.0.
  - `candidates/admin.py`: the archive fields are read-only, and only Admins can delete.
  - `accounts/management/commands/seed.py`: Kai Moreno's candidate, application and move, `SEED_ARCHIVED` and `seed_archived`.
  - Tests:
    - new `candidates/tests/test_services.py`, `test_lifecycle_views.py` and `conftest.py` (`kai`, `application_at`);
    - archived cases added to `applications/tests/test_services.py`, `test_moves.py`, `test_board.py`, `test_forms.py` and `test_views.py`;
    - `accounts/tests/test_permissions.py` and `test_seed.py`.
  - Docs:
    - `CLAUDE.md`: the lifecycle conventions;
    - `docs/TESTING.md`: the new fixtures;
    - `docs/MANUAL_CHECKS.md`: an archived-card check, and the Reopen check now names Chloe's card;
    - `plans/applicant-tracking-system.md`: ticks, and a Phase 10 criterion for messages on the delete page.
- **TDD:** the plan's three candidates, as approved.
  1. **Archiving is blocked while an application is active.** One test, run for each of the eight stages. The candidate has a Rejected application plus one at the stage being tested. RED against a placeholder `archive_candidate` that did nothing.
  2. **Archived candidates can't receive new applications.** `record_application` gets a stale copy of the candidate, who was archived in the database. It must refuse with the exact message and write nothing, then succeed once the candidate is unarchived. RED with "DID NOT RAISE".
  3. **Permanent delete is Admin-only.** Run for six users (every role, plus an `is_staff` user with no role). Only the Admin removes the candidate, application and history; everyone else gets `PermissionDenied` and nothing changes. RED against a placeholder `delete_candidate`.
- **Decisions:**
  - "Active" means `ACTIVE_STAGES` (Applied through Offer); Hired, Rejected and Withdrawn never block archiving.
  - Archiving reuses `can_manage_candidates` (the PRD matrix gives it to Admins and Recruiters). Deleting gets its own empty roles tuple, so only Admins pass.
  - Archive and unarchive are plain POSTs that redirect with a message, since the whole page changes state.
  - Deleting needs neither archiving first nor finished applications, as the PRD asks only for the confirmation page.
  - Archived candidates can still be edited (to correct mistakes).
  - Seed archives Kai only in the run that creates Kai, so a re-run never re-archives a candidate staff have unarchived.
  - Messages can't appear on the delete page until `CandidateMessage` exists (Phase 10). That part is left open and carried into Phase 10's criteria.
- **Deviations:**
  - Prompt 2 confirmed the recommendation to refuse moves for archived candidates, and asked that the refusal live in `move_refusal` on the server, not only in the hidden board controls. Done, with service and endpoint tests.
- **Sideways:**
  - Making cards "movable" at first ignored whether the column had any Move targets, so a Hired card got a drop form. `test_a_hired_card_cant_be_dragged` caught it, and the rule now needs targets as well.
  - My first board test looked for `data-move-targets` in the whole page, but the board's script contains that text. The test now checks the card only.
  - A list test matched "1 archived hidden" as plain text, but those words sit inside a `<span>`. The test now strips tags first.
  - `ruff check` flagged two unsorted import blocks (`seed.py`, `candidates/services.py`); `ruff check --fix` sorted them.

## 2026-10-20 — Applicant Tracking System: Phase 8/14, Skills on openings

### Prompts

1. The `/implement` skill, given `applicant-tracking-system phase 8`.
2. Ok looks good go to first phase
3. Looks good make sure that the distinction between opning authority exists where it grands permission to manage skills only on that openin, never to retire skills.
4. Ok go ahead and impllement can_manage_opening_skills(user, opening) and can_retire_skills(user) and make sure the match the nine-row testing matrix, use existing roles and authority checks whenever possible. Other than that continue on to building

### Summary

- **Outcome:** Skills on openings.
  - Each opening's page has a **Skills** section, separate from the Edit form. Skills show as chips, and a retired skill still listed there is marked "Retired".
  - **Managers** are Admins, Hiring Managers, and the opening's designated authority (on that opening only). They get an "Add a skill" box that suggests active skills the opening doesn't list yet, plus an × on each chip.
    - Typing a name finds the existing skill ignoring capitals and extra spaces ("python" adds "Python"). A new skill is created only when nothing matches, and keeps the capitals it was typed with.
    - Retired, already-listed, blank or overlong names are refused with a message under the box.
    - Adding and removing swap only the Skills section through HTMX. Without HTMX, they redirect back with a message.
  - **Everyone else** sees the skills with a read-only note, and a direct POST gets a 403.
  - **A new `/skills/` page** (nav: Skills) lists active and retired skills, each with how many openings list it. Only Admins and Hiring Managers can retire or reactivate a skill there (HTMX swaps the table). A retired skill stays on the openings that already list it, but no opening can add it.
  - **Deleting:** a skill can't be deleted, in the Django admin or in the database (PROTECT).
  - **Seed:** 11 skills. Python, SQL, Accessibility and User research are shared across openings. jQuery is retired but still on Backend Developer.
  - **Checks:** 593 tests pass (73 new). `ruff check` and `ruff format` are clean. One migration (`openings/0002_skill`). Seed was run twice on the dev database; the second run changed nothing. All five Phase 8 criteria are ticked.
- **Changes:**
  - `accounts/permissions.py`:
    - new `SKILL_MANAGER_ROLES` and `can_manage_opening_skills(user, opening)`, and `SKILL_RETIRER_ROLES` and `can_retire_skills(user)`;
    - new `is_eligible_authority_of(user, opening)`, now shared by `can_make_offer` and `can_manage_opening_skills` (prompt 4: reuse the existing authority check).
  - `accounts/templatetags/accounts_tags.py`: the filters `can_manage_opening_skills:opening` and `can_retire_skills`.
  - `openings/models.py`:
    - `Skill`: name unique ignoring case through a `Lower("name")` constraint, `is_active`, `retire()` and `reactivate()`, a field-level duplicate error, and a queryset with `active()`, `retired()` and `named()`;
    - `OpeningSkill`, the through table, with PROTECT on the skill and a unique (opening, skill) pair;
    - `JobOpening.skills`.
  - `openings/migrations/0002_skill.py`: the new tables.
  - `openings/services.py` (new): `clean_skill_name`, `find_or_create_skill`, `manage_refusal`, `attach_skill` and `detach_skill`.
  - `openings/forms.py`: `SkillAttachForm` (one name box linked to the suggestions list).
  - `openings/views.py`:
    - `skills_section_context`, and the opening detail page now shows the section;
    - `OpeningSkillsMixin`, which gives a 403 unless `can_manage_opening_skills` allows the user on that opening;
    - `OpeningSkillAttachView`, `OpeningSkillDetachView`, `SkillListView` and `SkillActivationView` (`allowed_roles = SKILL_RETIRER_ROLES`).
  - `openings/urls.py`: `skill_attach` and `skill_detach`. New `openings/skill_urls.py` (`skills:` namespace), mounted at `/skills/` in `config/urls.py`.
  - Templates:
    - `openings/partials/skills_section.html` (new), included in `jobopening_detail.html`;
    - `openings/skill_list.html`, `partials/skill_table.html` and `partials/skill_row.html` (new);
    - a Skills link in `templates/partials/nav_links.html`;
    - `templates/icons/graduation-cap.svg`, copied from lucide-static v1.49.0.
  - `openings/admin.py`: `SkillAdmin`, with deleting turned off.
  - `accounts/management/commands/seed.py`: `SEED_SKILLS`, `SEED_OPENING_SKILLS`, `seed_skill` and `seed_opening_skills`.
  - Tests:
    - `accounts/tests/test_permissions.py`: the skills permission matrix;
    - `openings/tests/test_skill_models.py`, `test_skill_services.py` and `test_skill_views.py` (new);
    - `openings/tests/conftest.py`: the fixtures `authority` and `skilled_opening`;
    - `accounts/tests/test_seed.py`: skills added to the run-twice snapshot, plus two new tests.
  - `CLAUDE.md`: the skills conventions (the permission rules, the services, the `skills:` namespace, the new filters).
  - `plans/applicant-tracking-system.md`: Phase 8's criteria ticked.
- **TDD:** the plan's two candidates, as approved.
  1. **`can_manage_opening_skills` and `can_retire_skills`:** one parametrized test, RED on 3 rows with stubs that always returned False. After prompt 3, it gained a column for someone else's opening, so it proves the authority's right stops at their own opening and never covers retiring. The final table covers Admin, Hiring Manager, the authority, another Recruiter, an authority later changed to Interviewer, Interviewer, no role, inactive Hiring Manager and inactive Admin.
  2. **Adding by name reuses the existing skill regardless of case:** "python", "PYTHON" and "  Python  " each attach the existing "Python", with no near-duplicate. RED against a stub `attach_skill` that returned None.
- **Decisions:**
  - Retiring happens on a separate `/skills/` page modelled on Sources, not on the opening page, since retiring affects every opening. Reactivating was added there to match Sources.
  - One box both adds and creates. Refusals (blank, too long, retired, already listed) come back with a 200 and the message under the box; permission refusals are 403s.
  - A retired skill that's already on an opening can still be removed, but can't be added back.
  - `OpeningSkill` was added as the through table so the skill side can use PROTECT, as the PRD says.
  - Seed gives an opening its sample skills only if it lists none yet, so staff changes survive a re-run. The one edge case: if staff remove every skill from a seeded opening, the next seed run adds the samples back. Seed links skills directly, not through `attach_skill`, so a retired skill can already be on an opening.
- **Deviations:**
  - Prompt 3 asked for the permission test to make the "authority only on their own opening" rule explicit, so a someone-else's-opening column was added before GREEN.
  - Prompt 4 asked for both permission functions to be implemented against the matrix. They already were (GREEN in cycle 1), so the work went into pulling the shared authority check into `is_eligible_authority_of`.
- **Sideways:**
  - Two Bash heredocs containing Python with apostrophes failed to parse ("unexpected EOF"), and nothing ran. The edits were redone through script files and the Write tool.
  - `ruff check` flagged one import-block blank line in `openings/models.py`; `ruff check --fix` fixed it.
  - `plans/applicant-tracking-system.md` already had the user's own tick on Phase 7's last criterion before this phase began. It was left as it was.

## 2026-10-20 — Applicant Tracking System: Phase 7/14, Drag-and-drop on the board

### Prompts

1. The `/implement` skill, given `applicant-tracking-system phase 7`.
2. Ok go ahead and build it: also I would like to make sure the the pipeline board fits well on any screen size and does not have to used a horizontal scroll bar. And have the rejected and withdrawn fields seperately. Essentially have arrows pointing to each of the phases, but keep the layout in a way that uses the pages space rather than horizontal scrolling.
3. Ok drag and drop functions as intended, however in terms of looks I feel that it could look more responsive like having animations when hovering an employee card over, also I notice that a user may accidentally make a mistake if theey do choose to drag and drop, can we add a confirmation message stating what the user is doing rather than just immediately moving their employee card.
4. Ok I beleive you misunderstood me when I mentioned how the move behavior works so far I see no visible change when I move and employee card to another box. I also feel that instructions for every box: Release to move hereRelease to move here, with a noteNot allowed here Not necessary. I wanted to see the actual area that it was being hovered over in be highlighted giveing the person a visual cue about how it was being dropped into the menu. Also when I pick up a card I would like to to travvel with the cursor, it feels like now I am picking it up and carrying a hard to see ghost copy of that employee card and I dont really know whats going on I hust have to guess. Please ask me questions if you need further clarification about what design I intend to go for before implementation if required.
5. (Answer to "When you pick up a card, how should it travel with your cursor?") Show me a prototype first.
6. Ok I like the layout with the way you positioned the arrows, I prefer the card lifting iteself mouse and touch and light up every allowed stage while dragging, go ahead and implement this design into the final product
7. Ok I beleive I found the sourec of the confusion my VSCode browser seems to be loading old CSS data as when I open it in another browser it looks different. I am not sure of this but would potentially like some troubleshooting on this, additionally I would like to have the menus contract and expand automatically when the threshold of users in a board section is higher than 3, to where it will give the user an option to expand the cards view and search for applicants in that cards view. One other thing is some Iconography for No one at Screening would be nice rather than just an empty card section. This should expand dynamicall based on the other cards height at most 3.
8. (Answer to "When a stage has more than 3 applicants … how should you see the rest and search them?") Expand in place (Recommended).
9. (Answer to "While a busy stage is folded to 3 cards, which 3 should it show?") Newest arrivals first (Recommended).

### Summary

- **Outcome:** Drag-and-drop on the pipeline board, with a mouse or by touch, plus a board layout with no sideways scrolling.
  - **Picking up:** Admins, Recruiters and Hiring Managers press a card and move the mouse, or press and hold it on a touch screen. The card lifts out (tilted, with a deep shadow) and travels with the pointer, leaving a dashed slot behind. It's built on pointer events, not the browser's drag-and-drop, so there is no faint ghost, and it works on phones. The page scrolls when the card nears the top or bottom edge.
  - **While carrying:**
    - Every other stage lights up from the card's own Move targets: a green dashed outline (one step forward), amber (a note is asked for) or faded grey (refused).
    - The stage under the pointer grows slightly and gets a solid ring and tint in its colour (red when refused).
    - A card-shaped gap opens where the card would land.
    - There's no text inside the columns.
  - **Dropping:**
    - A legal drop settles the card into the gap, outlined, and posts the card's hidden drop form (with `dropped`) to `applications:move`, the endpoint the Move menu uses.
    - The server answers with a dialog before anything moves. A one-step move gets a plain confirmation ("You dropped … on Screening. This moves them one step forward, from Applied to Screening."); moves that need a note get the note dialog.
    - Cancel, Escape or the backdrop slides the card back home. Confirming swaps in the redrawn columns, and the moved card lands with a green glow.
    - A drop on a faded stage flies the card home and is posted anyway, so the server refuses it with its message and the card shakes.
    - Dropping back home, or pressing Escape mid-drag, just flies the card home.
  - **Unchanged:** the Move menu's one-step moves still happen at once.
  - **Who can drag:** only cards with Move targets can be picked up. Interviewers, users with no role and Hired cards have no grip, no drop form and nothing to pick up, and a hand-made drop POST from them is refused with 403.
  - **Layout (from prompt 2):** the six pipeline stages sit in a grid with an arrow between each. Phones stack them with ↓ arrows. From `md` up there are two rows of three with → arrows, and a connector from Interview down to Final Review. Rejected and Withdrawn have their own "Out of the pipeline" area below, still collapsed to counts that expand, and they take drops while collapsed.
  - **Busy and empty stages (prompts 7–9):**
    - Cards are newest first, so a moved card goes to the top and the drop gap opens there.
    - A stage with more than three cards (Rejected and Withdrawn included) shows the newest three and a "+N more · Show all" button.
    - Expanding shows every card, with a search box that filters by name as you type and says when nobody matches. "Show fewer" folds it again and clears the search.
    - The expanded state and the search text survive moves.
    - An empty stage shows an inbox icon and "No one at …", in a box that stretches to match the other stages in its row, capped at about three cards' height.
  - **Stale CSS (prompt 7):**
    - Diagnosis: in development the stylesheet was served at a fixed address with no caching instructions, so browsers could keep an old copy. VS Code's built-in browser does this across sessions and has no reliable hard reload.
    - Fix: `skeleton.html` now links it as `tailwind.css?v=<file modification time>`, so every rebuild gets a new address.
    - README has troubleshooting steps for a browser that cached the stylesheet before the fix.
  - **Checks:** 520 tests pass (33 new this session); `ruff check` and `ruff format` are clean. No migrations, no seed changes. Four of the five Phase 7 criteria are ticked. The last ("checklist followed") waits for the user to run the updated `docs/MANUAL_CHECKS.md` with a real mouse and a phone.
- **Changes:**
  - `applications/templates/applications/board.html`:
    - the pipeline grid, the separate closed-stages section, and a `data-drop-area` wrapper around both;
    - the legend: "Drag a card to another stage (on a touch screen, press and hold it first), or use Move on a card", plus a line on what the colours mean;
    - the pointer-events drag script: lift, follow and autoscroll, the lit stages, hovered stage and gap, the waiting card, the dialog close and swap handling, and touch press-and-hold with scroll and context-menu handling.
  - `applications/templates/applications/partials/card.html`: for movers, `data-move-targets`, `data-note-targets`, a grip icon, `select-none`, `draggable="false"` on its links, and the hidden drop form (CSRF token, `expected_stage`, an empty `to_stage`, `dropped`). Draggable cards lift on hover. After a move, the moved card has `animate-land` and a refused one `animate-shake`.
  - `applications/templates/applications/partials/column.html`: `data-drop-stage` and `drop-target` on every column, with fluid widths. Rejected and Withdrawn are full-width `<details>` bars. `column_cards.html`: a `data-empty` hook on the "No one at …" line.
  - `applications/templates/applications/partials/stage_arrow.html` (new): the arrow between stages, and the row-wrapping connector.
  - `applications/board.py`: `Column.drop_stages` and `Column.note_stages`, from the same `targets` as the Move menu.
  - `applications/views.py`:
    - `board_context()` splits the columns into `pipeline` and `closed`;
    - `ask_first()` (was `ask_for_note()`) also builds a dropped move's plain confirmation;
    - `post()` asks first when `dropped` is set;
    - `board_update()` passes `landed_pk` and `bounced_pk`.
  - `applications/forms.py`: `MoveForm.dropped`.
  - `applications/templates/applications/partials/note_form.html`: the note field only when the move asks for one; otherwise the Move button gets `autofocus`.
  - `assets/css/source.css`: the drag styles (`.drop-target[data-drop…]` with `[data-drop-over]`, `.drag-float`, `.drag-slot`, `.drop-gap`, `.drop-pending`, and the grabbing and not-allowed cursors), and the `land`, `shake` and `gap` keyframes next to `rise`. All have reduced-motion fallbacks.
  - `templates/icons/`: `arrow-right`, `arrow-down` and `grip-vertical`, from lucide-static v1.49.0.
  - Busy and empty stages (prompts 7–9):
    - `applications/board.py`: `FOLD_AT = 3`, `Column.fold_at` and `Column.folded_count`, and cards newest first (`-updated_at`, `-pk`).
    - `partials/column_cards.html`: `data-beyond-fold` past the third card, the "+N more · Show all" / "Show fewer" toggle, and the icon empty state with `data-empty`.
    - `partials/card.html`: `data-name`, for the search.
    - `partials/stage_search.html` (new): the search box and no-match line, in both column types outside the swapped `<ul>` (now marked `data-cards`).
    - `board.html`:
      - `syncColumn()` and `filterColumn()`, the toggle and search listeners, and a re-sync after every HTMX settle;
      - the drop gap and a dropped card now go to the top of the list.
    - `assets/css/source.css`: the fold, search and no-match hiding rules, and the empty box's stretch with its `max-h-[22rem]` cap.
  - Stale CSS (prompt 7): `config/templatetags/stylesheets.py` (new, `{% tailwind_stylesheet %}`), registered by name in `config/settings.py` `TEMPLATES`, and used in `templates/skeleton.html` instead of `{% tailwind_css %}`.
  - `config/tests/test_stylesheets.py` (new, 4 tests) and `applications/tests/test_board_folding.py` (new, 10 tests).
  - `applications/tests/test_drag_and_drop.py` (new, 19 tests), with `drop()` and `submit_dialog()` helpers. `applications/tests/conftest.py`: the `app` fixture moved here from `test_board.py`. `test_board.py`: the collapse test checks for two closed `<details>`.
  - `prototypes/board-drag-feel.html` (new): the throwaway prototype (A: solid copy on browser drag-and-drop, B: the card lifts itself with pointer events, C: today's ghost). It is marked with the decision.
  - `docs/MANUAL_CHECKS.md` (new): the drag-and-drop, touch and layout checklist. `docs/TESTING.md`, `CLAUDE.md` and `README.md` describe the drop convention, pointer events, the layout and the new styles. `plans/applicant-tracking-system.md`: four criteria ticked.
- **TDD:** none, per the plan. The behavior is in the browser, and Phase 6 already test-drove the endpoint. The view tests take the drop form each card renders and post it as the board's script would:
  - a legal drop asks for confirmation and writes nothing, and the plain confirmation has no note field;
  - once confirmed, the card moves, only the two columns are swapped, and the card lands animated;
  - the confirmation can't be submitted twice;
  - the Move menu still makes a one-step move without asking;
  - without HTMX, a drop's confirmation is a page;
  - a note-needing drop returns the note dialog, then moves once confirmed;
  - three illegal drops (Applied → Hired, Rejected → Withdrawn, and a Recruiter into Offer) are refused at once, each leaving the card shaking in its redrawn column;
  - a stale card is refused;
  - each card's hints match its Move menu;
  - cards have no native `draggable` attribute;
  - the columns carry no text hints;
  - the layout checks: stage order, arrows, the wrap, and Rejected and Withdrawn apart, inside the drop area.
- **Decisions:**
  - Drops onto faded stages are posted rather than blocked, so the server's message explains the refusal.
  - The drop form is a real hidden `<form>` submitted with `requestSubmit()`, so HTMX sends it exactly like the Move menu's forms.
  - The confirmation is built on the server, from the same dialog as the note step, and only after `move_refusal()` passes, so the wording uses real names and stage labels. Only drops are confirmed; a Move-menu pick is already deliberate.
  - While the dialog is open, the card waits in the gap. Closing the dialog slides it home. Any other answer, whether a move or a refusal, puts it back first (in `htmx:beforeSwap`), and the server's columns are then swapped in. So the page always ends up showing what's really saved. A failed request also sends it home.
  - Over a collapsed panel no gap opens, and the card shrinks into the bar.
  - Between columns (on an arrow, say) the last hovered stage stays lit, so the layout shifts from opening gaps can't make the highlight flicker.
  - A drag can start on the candidate's name, and the click that follows a drag is swallowed, so it doesn't open the page. Buttons and the Move menu never start a drag.
  - Touch timings: 280 ms hold; a move over 10 px before then counts as a scroll; mouse drags start after 4 px.
  - Highlight states are data attributes styled outside any CSS layer, so they beat the columns' own utilities.
  - Three stages a row from `md` up, because the page is `max-w-6xl`.
  - Folding is rendered by the server (`data-beyond-fold` and the toggle with its count come with the cards, so every swap redraws them correctly). Only the expanded flag and the search text live in the browser, on the column element that swaps don't replace.
  - The search matches the candidate's name, as you type, within that one stage. Collapsing clears it, and it never hides the "+N more" toggle.
  - The stylesheet version is the built file's modification time, read on each page render. Before the CSS is built (in tests) the link has no version. The library's own `{% tailwind_css %}` adds no version in development, which is why it was replaced.
  - The empty-stage icon is `inbox` (already in the project).
- **Deviations:**
  - Prompt 2 added the no-horizontal-scroll layout, the arrows, and Rejected and Withdrawn set apart. None of these was in the Phase 7 plan. Rejected and Withdrawn stayed collapsed to counts, so story 46 still holds.
  - Prompt 3 changed approved behavior: a drop no longer moves a card at once, and animations were added.
  - Prompt 4 said the second round missed the point:
    - the user saw no visible change while dragging;
    - every box showed all three hint lines;
    - the browser's ghost was hard to follow.
  - Diagnosis and design (prompts 4–6):
    - The hint lines and the missing highlights pointed to a stale cached stylesheet in the user's browser (the built CSS on disk was current).
    - The text hints were dropped anyway, as the user asked.
    - Instead of guessing the design, the agent asked first, and the user chose a prototype.
    - The user picked variant B (pointer events, mouse and touch) with every allowed stage lit.
  - Prompt 7 added folding busy stages, search and the empty-stage icon, none of which was in the Phase 7 plan. The agent asked two questions one at a time, and the user picked both recommended answers: expand in place (not a pop-up or an internal scroll) and newest arrivals first. Newest-first replaced Phase 6's "in the order they reached the column", which no test depended on.
  - This departs from the plan's and PRD's "built-in/native browser drag-and-drop" wording. It still uses no library (SortableJS stays out), and `CLAUDE.md` now says "the browser's own pointer events". The PRD and plan text were left unchanged.
- **Sideways:**
  - Test and tooling fixes during the first build:
    - the `app` fixture moved to `conftest.py`;
    - two test-helper regex bugs were fixed;
    - a ruff long-line fix;
    - the drag styles were moved out of `@layer components`, because the column's own `bg-*` utility beat them there.
  - After prompt 3:
    - an earlier CSS insertion had separated the `animate-rise` comment from its `@theme` block, and both were rewritten in order;
    - the old "legal drop moves at once" test was replaced by confirm-first tests;
    - a long shell heredoc failed to parse, and nothing was written.
  - **The stale-CSS diagnosis (prompt 4):** the built CSS on disk had the hint-hiding rules, so the user's browser was most likely using an old cached copy. The agent suggested Ctrl+Shift+R.
  - **Prototype checks (headless Edge):**
    - The first rerun hung on a headless Edge left over from crashed runs that still held the debugging port. It was killed, and the check moved to a fresh port and profile.
    - Variant B's illegal drop onto Hired did nothing, because the prototype's own "try this" panel covered Hired. Fixed: the panels fade during a drag, and the hit test looks beneath floating elements.
  - **Build checks:** headless Edge with real mouse and touch input against a freshly seeded scratch database. All passed:
    - a confirmed one-step move;
    - a cancelled note move;
    - an illegal drop with a shake;
    - a drop onto the collapsed panel;
    - Escape mid-drag;
    - a drag that starts on a link and opens nothing;
    - press-and-hold touch at 390px;
    - a quick swipe that scrolls rather than drags;
    - Interviewers unable to pick anything up.
  - **Bugs those checks found:**
    - The drop gap reused the columns' `data-drop` attribute. It became `data-gap`.
    - Chrome reports a size for the list inside a closed `<details>`, so a hidden gap opened over the collapsed panel. The check now asks whether the panel is open.
  - **Check-harness problems:**
    - The check server ran with `--noreload`, so Django kept serving the template from before the fix until it was restarted.
    - Copying the dev database brought along the user's own test moves, which broke the script's starting positions. The script switched to a freshly seeded scratch database.
    - The script released over a panel the opening gap had pushed lower. It now re-aims before releasing, as a person would.
  - Synthetic and DevTools input can't fully stand in for a hand on a mouse or a phone, so the last criterion is left for the user.
  - **After prompt 7:**
    - The stale-CSS diagnosis was confirmed against the running server: the stylesheet response had `Last-Modified` but no `Cache-Control`, and the library's tag links it with no version in debug.
    - `config` isn't an installed app, so the new tag library had to be registered by name in `TEMPLATES` before `{% load stylesheets %}` worked.
    - Two new folding tests first failed on a test helper: cutting a swapped column at the first `</ul>` stopped inside a card's own Move menu. The helper now cuts at the next out-of-band swap.
    - Seeding the crowded scratch board by piping a script into `manage.py shell` failed (the interactive console can't take blocks); it ran with `exec` instead.
    - **Browser check:** headless Edge on a scratch board with six cards at Applied and an empty Screening, with real mouse input. All passed:
      - the versioned link;
      - three cards shown with "+3 more";
      - expanding to all six, with `aria-expanded`;
      - searching "ka" (Kai only) and "zzz" (the no-match line);
      - the empty Screening box stretched to the 352px cap beside the taller Applied, and empty Hired matching a one-card row;
      - the gap opening at the top of the empty and the folded columns;
      - a move made while Applied was expanded keeps it expanded with an updated toggle;
      - "Show fewer" back to three;
      - no sideways scroll at 390px.
    - The first drag in that check pressed on a card scrolled below the window, and was re-run after scrolling it into view.

## 2026-10-19 — Applicant Tracking System: Phase 6/14, Pipeline board and Move menu

### Prompts

1. The `/implement` skill, given `applicant-tracking system phase 6`.
2. Looks good just make sure that the tests distinguish a note prompt should open from a note is required for validation. Text the complete transition matrix rather tha the 64 comdiantions of 8 stages. Test that moving to a current stage is rejected and the terminal stages cannot be exited unless defined transition table permits it. Verify that rejected and withdrawn require an optional note prompt while transitions requiring a mandatory note cannot proceed without one. Keep both helpers to where they do not depend on database queries http request or user permissions.
can_make_offer make sure that it includes admins recruiters and hiring managers as well as the designated authority verify that an authority must be active and eligible before the offer is made. Test inactive designate authority, and authority who has become an iterviewer  and an authority with no eligible role. make sure that admins or recruiters cannot bypass the authority requirement because of elevated permissions.  Test this with offer and hired so the 2 destinations cannot accidental acquire different authorization rolse. Make surea succsesful move only creates on stagfe change and updates applicationstage. Test refused move leaves both the cached stage and history unchanges. Cover invalid transitions, missing notes, unauthorized users and offer-permission failures. Ensure that stale card submissions cannot overwrite a newer stage. Make sure that repeated submissions cannot create duplicate history entries or move an application to an unexpected stage.
3. Yes and go through with the next phase
4. Looks good move to next
5. Yes continue to development

### Summary

- **Outcome:** A pipeline board for each opening at `/openings/<pk>/board/`, open to every role.
  - **Columns:** one per stage. Hired gets a green column, and Rejected and Withdrawn are collapsed to a count that expands.
  - **Move menu:** each card has a **Move** menu listing only the moves the user may make, tagged *next*, *note* or *optional note*. Picking one posts to the single endpoint, `/applications/<pk>/move/`. A one-step move happens at once. Skips, backward moves and reopens open a DaisyUI dialog that needs a note, and Rejected and Withdrawn open one with an optional note.
  - **Swaps:** a move swaps only the affected columns' counts and cards, out of band, with a status message and no reload.
  - **Refusals:** illegal moves get a 400 and permission failures a 403. Each comes with a clear message and the columns redrawn as they really are, and nothing is written.
  - **Who can move:** only Admins, Hiring Managers and the opening's still-eligible designated authority can move into Offer or Hired, and Hired is final. Interviewers see the board with no Move controls.
  - **Stale and repeated posts:** every menu entry carries the stage its card showed, so a stale card or a double submission is refused rather than overwriting a newer stage.
  - **History:** each application's full stage history opens as a dialog from its card, or as a page from the candidate and opening pages.
  - **Without JavaScript:** a move redirects, and a move that needs a note gets a page.
  - **Seed:** four more Backend Developer applications, with seven move paths made through `move_application()`, so every column has someone in it. A second run changes nothing.
  - **Checks:** 487 tests pass (135 new); `ruff check` and `ruff format` are clean. All nine Phase 6 acceptance criteria are ticked. No migrations were needed.
- **Changes:**
  - `applications/stages.py`:
    - `ACTIVE_STAGES`, `CLOSED_STAGES`, `PIPELINE`, `OFFER_STAGES` and the `ALLOWED_TRANSITIONS` table.
    - The pure rule functions: `can_move`, `requires_note` (the move can't be made without a note), `prompts_for_note` (the dialog opens), `move_kind` and `skipped_stages`.
    - The menu helpers: the `MoveTarget` dataclass, `move_targets(from_stage, may_offer=...)` and `withholds_offer_targets`.
    - None of these takes a user, a request or the database.
  - `applications/services.py`: `move_refusal()` checks role, then stale card, then table, then offer authority. `move_application()` locks and re-reads the row, checks the refusal and the note, then writes one StageChange row and the cached stage atomically. It also has the error codes and staff-facing messages.
  - `applications/board.py` (new): `Column` and `board_columns(opening, user, stages=None)`, used by both the full board and the endpoint's partial swaps.
  - `applications/forms.py`: `MoveForm` (only checks the request's shape: `to_stage`, the required `expected_stage`, `note`, `confirmed`).
  - `applications/views.py` and `urls.py`: `PipelineBoardView`, `ApplicationMoveView` (`applications:move`) and `ApplicationHistoryView` (`applications:history`). `openings/urls.py` routes `openings:board` to the board view.
  - Templates: `board.html` (with a small script that lets HTMX show 400/403 refusals and opens dialogs with `showModal()`), `move_note.html`, `application_history.html`, and the `column`, `column_cards`, `card`, `move_menu`, `move_result`, `note_form`, `note_dialog`, `history_list` and `history_dialog` partials.
  - `accounts/permissions.py` and `accounts_tags.py`: `STAGE_MOVER_ROLES`, `can_move_applications`, `OFFER_ROLES` and `can_make_offer(user, opening)`, plus their filters.
  - `openings/.../jobopening_detail.html`: a "Pipeline board" button and a History link on each application row. `candidates/.../candidate_detail.html`: a History link on each row. `applications/models.py`: the docstring points to `move_application()`.
  - `accounts/management/commands/seed.py`: four more `SEED_APPLICATIONS`, `SeedMove`/`SEED_MOVES` and `seed_moves()`. A path runs only for an application that has never moved, and inside its own savepoint, so a refused step keeps none of the path.
  - Tests:
    - `applications/tests/test_stages.py` (new, 41, no database).
    - `test_moves.py` (new, 29).
    - `test_board.py` (new, 42).
    - `accounts/tests/test_permissions.py` (+20).
    - `accounts/tests/test_seed.py`: the "everything at Applied" test became "one first row each", plus three new tests.
  - `templates/icons/`: `square-kanban` and `history`, from lucide-static v1.49.0.
  - `CLAUDE.md`, `docs/TESTING.md`, `README.md`: the stage-rule, move and board conventions; the SQL-level "both writes or neither" test pattern, pure-module tests and the stale-submission tests; and the updated status.
  - `plans/applicant-tracking-system.md`: Phase 6 criteria ticked.
- **TDD:** The plan's three candidates. My notes at the brief made each cycle a small group of tests for one behavior. Each was red on assertions against a stub, and then green.
  1. *`can_move` and `requires_note`.*
     - The test: `can_move` checked against a complete transition matrix written out by hand, plus a note table classing every legal move as no note, optional or required.
     - Separate tests cover same-stage moves, leaving terminal stages, prompt versus requirement, and `ValueError` for illegal moves. The file has no `django_db` mark.
     - Red: 24 assertion failures.
     - The fix: the table built from the stage groups, with `requires_note` refusing anything but one step forward, except into Rejected or Withdrawn.
  2. *`can_make_offer`.*
     - The test: roles on someone else's opening; the authority on their own, and on a closed opening; an authority made inactive, turned Interviewer, or left with no role; and `is_staff` or move rights never standing in.
     - Red: 3 failures (Admin, Hiring Manager, the authority).
     - The fix: `has_role(user, *OFFER_ROLES)`, or being the authority while `can_be_designated_authority()` still holds.
  3. *`move_application`.*
     - The tests: exactly one row and the new stage on success; twelve refusals, each leaving the stage and history unchanged; Offer and Hired side by side for nine users; a stale card; a stale copy without `expected_stage`; double submission; and a rollback test that fails the INSERT or the UPDATE at the SQL level.
     - Red: all 29 failed.
     - The fix: lock and re-read, `move_refusal()`, the note check, then both writes in one transaction.
- **Decisions:**
  - Admins, Recruiters and Hiring Managers can move stages, per the PRD's permission summary. Offer and Hired also need `can_make_offer`.
  - Hired is a normal column after Offer, not collapsed.
  - The server decides whether to show the note dialog (`HX-Retarget` to `#dialog-slot`), so Phase 7's drag-and-drop can post the same way.
  - Refusals return 400/403 with the real columns, and the board's script lets HTMX swap them.
  - `expected_stage` is required at the endpoint, and stale moves are refused rather than re-judged.
  - The Move menu is a `<details>` that expands inside the card, because a floating dropdown would be clipped by the board's horizontal scroll container.
  - A non-clickable menu line says who can move into Offer or Hired when those are left out.
  - Seed paths are made by the users who would really make them, with notes wherever the rules need one.
  - Chloe (not Gus) gets the Withdrawn card, so one seeded candidate still has no applications (story 12).
- **Deviations:**
  - At the brief I asked for the stage tests to keep "opens a note prompt" separate from "a note is required", to check against a complete matrix rather than 64 generated cases, to cover same-stage moves and terminal exits, and to keep the helpers free of the database, requests and users. For `can_make_offer` I asked for the inactive, turned-Interviewer and no-role authority cases, a check that elevated permissions can't bypass it, and tests of Offer and Hired side by side. For `move_application` I asked for one row on success, nothing on refusal (invalid moves, missing notes, unauthorized users, offer failures), and protection against stale cards and repeated submissions.
  - My note said `can_make_offer` should "include admins, recruiters and hiring managers", and also that admins and recruiters can't bypass the authority rule. The agent pointed out that this conflicts with the PRD and proposed a reading: Admins and Hiring Managers anywhere, Recruiters only as an opening's eligible authority, with no flag standing in. I confirmed it.
  - `prompts_for_note` was added as a second pure helper, and `expected_stage` was added to `move_application`, to meet these requests.
- **Sideways:**
  - Cycle 1's first implementation of `prompts_for_note` returned early for Rejected and Withdrawn before checking legality, so Hired → Rejected didn't raise. The illegal-move test caught it.
  - Two view-test helper bugs, fixed in the tests: the `menu_stages` regex also matched `data-testid="move-menu"`, and messages with apostrophes are escaped in HTML (`isn&#x27;t`), so a `page()` helper unescapes bodies.
  - The first version of the seed's all-or-nothing test failed the path at its first step, which proved nothing about rollback. It was rewritten so two steps pass before Offer is refused, and checked by temporarily removing the savepoint (it went red) before putting it back.
  - Adding Gus's application would have left no candidate without one, breaking a Phase 5 seed guarantee. He was swapped for Chloe.
  - Ruff flagged the stage-test shorthands `I` and `O` as ambiguous. All eight were renamed (`AP`, `SC`, `IN`, …) with Python's tokenizer, a mechanical change that left the assertions as they were. It also flagged two over-long lines that had `# fmt: skip`; the markers were removed and the lines reformatted.
  - On the dev database the first `seed` run skipped 2 applications (Ben and Farah), because Indeed is still retired from earlier manual testing. This is the intended behavior, so that board has no one at Screening or Rejected until Indeed is reactivated and `seed` re-runs. The second run changed nothing.
  - Headless-Edge screenshots of the seeded board (light, dark, full width, and 360px phone for a manager and an Interviewer) showed the layout working. The first full-width attempt used `max-w-none`, which isn't in the built CSS; it was redone with an inline style.

## 2026-10-19 — Applicant Tracking System: Phase 5/14, Record applications

### Prompts

1. The `/implement` skill, given `applicant-tracking system phase 5`.
2. Alright some samfeguards to consider for our TDD: record_application() must create the application and its initial stage change at the same time, if it fails it must be rolled back. The initial transition should record record no revious stage and the new applied stage.
Use the database constraints and foreign-key protections. Make application and stage-istory record read-only in Django admin so that ithe server that creates the initial history row is not bypassed.
active_or_current(source) should include active sources and the application's existing sources when a source is retired. it should not make every retired source available as a new selection. Clear the referred_by when the selected source in not a referral. Including when saving through code rather than a form. Also make sure the candidate's page and and opening page only show record application action when  a user has permission and the opning is available. Views must also enfore these restrictions too independently.
3. Ok this test looks good move to next
4. Looks good move to next
5. Ok looks good move to development

### Summary

- **Outcome:** A new `applications` app. Recruiters and Admins record that a candidate applied for an open opening through an active source, at `/applications/new/`, started from a candidate's page (`?candidate=`) or an open opening's page (`?opening=`). `record_application()` writes the application at Applied and its first StageChange row (no stage → Applied, cause manual, by the user) in one transaction, and rolls both back if either fails. The source is pre-filled from the candidate's most recent application, and changing the candidate or source refreshes the source fields through HTMX, showing "Referred by" only for Referral sources. A duplicate gets "Ann Lee has already applied for Backend Developer." on the form, and the database's unique constraint backs it up. Closed openings and retired sources aren't offered and a hand-made POST naming one fails validation. An edit page (`/applications/<pk>/edit/`) changes only the source and "Referred by", and still shows and accepts an application's own retired source, but no other retired one. Both detail pages list applications with their stage, source and date. "Record application" appears only for Recruiters and Admins, and only when the opening is open (opening page) or the candidate has an open opening left to apply for (candidate page). The view refuses those cases on its own too. The Django admin shows applications and stage history read-only. `seed` records seven applications through the service, Ann twice so her third pre-fills the referral; a second run changes nothing. 352 tests pass (98 new); `ruff check` and `ruff format` are clean. All seven Phase 5 acceptance criteria are ticked.
- **Changes:**
  - `applications/` (new app): `stages.py` (the eight `Stage` choices; Phase 6 adds the rules here); `models.py` (`Application` with CASCADE to candidate, PROTECT to opening and source, a unique constraint on (candidate, opening), a stage check, `newest_first()`, and a `save()` that clears `referred_by` for non-Referral sources, including `update_fields` saves; `StageChange` with PROTECT to `changed_by`, checks on both stages and the cause, a "must change the stage" check, and a partial unique constraint allowing one initial row per application); `services.py` (`application_refusal()`, `openings_open_to()`, `prefill_source()`, `record_application()`, which also checks the user's role and turns a lost race on the unique constraint into the friendly error); `forms.py` (`ApplicationForm`, `ApplicationSourceForm`, a shared `ReferredByMixin` with `shows_referred_by` and the HTMX `refresh_url`, and labelled choice fields); `views.py` (`ApplicationCreateView`, `ApplicationUpdateView`, and a mixin that returns only the source fields to HTMX GETs with `Vary: HX-Request`); `urls.py` (`applications:create`, `applications:update`); `admin.py` (view-only admins with a read-only history inline); `migrations/0001_initial.py`; templates (`application_form.html`, and the `field`, `source_fields`, `source_line` and `stage_badge` partials); tests (`conftest.py`, `test_models.py`, `test_services.py`, `test_forms.py`, `test_views.py`, `test_detail_pages.py`, `test_admin.py`).
  - `accounts/permissions.py` and `accounts_tags.py`: `APPLICATION_MANAGER_ROLES`, `can_manage_applications`, and its filter.
  - `candidates/models.py`: `SourceQuerySet.active_or_current(source)`. `openings/models.py`: `JobOpeningQuerySet.accepting_applications()`.
  - `candidates/views.py` and `candidate_detail.html`, `openings/views.py` and `jobopening_detail.html`: the Applications sections and the guarded "Record application" action.
  - `accounts/management/commands/seed.py`: `SEED_APPLICATIONS` and `seed_application()`. Missing applications are recorded through `record_application()`; existing ones are never changed; one whose opening was closed or source retired since is skipped and counted. `accounts/tests/test_seed.py` adds applications and stage changes to the idempotency snapshot, plus three new tests.
  - `conftest.py`: `make_opening` moved here from `openings/tests/conftest.py` so the applications tests share it.
  - `config/settings.py`, `config/urls.py`; `templates/icons/` (`file-plus`, `clipboard-list` from lucide-static v1.49.0).
  - `CLAUDE.md`, `docs/TESTING.md`, `README.md`: the new permission, `record_application()` as the only way in, rule-based choice querysets, the moved fixture, the "both rows or neither" test pattern, and the updated status.
  - `plans/applicant-tracking-system.md`: Phase 5 criteria ticked.
- **TDD:** The plan's three candidates, each red on an assertion and then green:
  1. *One application per candidate per opening.* A form test posting Ann's second application for Backend Developer. It was red because only the database constraint's generic `__all__` message appeared. The fix: `application_refusal()` returns a named error, and `ApplicationForm.clean()` puts it on `opening`, which also skips Django's generic message. An ordinary `bulk_create` test proves the database half.
  2. *No applications for closed openings.* A service test, red with `DID NOT RAISE`. The fix: `application_refusal()` checks `opening.is_open` first, and `record_application()` raises it before writing anything.
  3. *Source pre-fill picks the most recent application.* One test with five parametrized cases: none; one; several, with dates out of pk order; a tie on date; and a newest source retired since. Another candidate's newer application must not leak in. It was red because the placeholder returned `None`. The fix: the candidate's applications `newest_first()`, returning the source only if it's still active.
- **Decisions:**
  - The plan had no edit URL, but the retired-source criterion needs one, so `/applications/<pk>/edit/` changes only the source and "Referred by".
  - The pre-fill never falls back to an older application when the newest one's source is retired.
  - The opening dropdown lists every open opening, so a duplicate gets the friendly error instead of disappearing from the list.
  - After saving, you go back to the page you started from (`?from=opening` on edit links from an opening).
  - HTMX refreshes use the form's own URL and `HX-Trigger-Name` to tell a candidate change (re-fill the source) from a source change.
  - CASCADE from candidate is for Phase 9's permanent delete. A view-only admin means a candidate with applications can't be deleted in the Django admin; that's left for Phase 9's own delete page.
  - No nav link, since there's no applications list page.
- **Deviations:** At the brief I asked for extra safeguards:
  - `record_application()` all-or-nothing, with the initial row recording no previous stage → Applied
  - database constraints and PROTECT foreign keys
  - a read-only admin for applications and stage history
  - `active_or_current()` allowing only the application's own retired source
  - `referred_by` cleared on every save, not just through forms
  - the "Record application" action shown only when permitted and available, with the views enforcing it on their own

  These were added as ordinary tests next to the three TDD cycles: a `monkeypatch` rollback test, constraint tests (including a partial unique constraint for one initial row), admin 403 tests, the `active_or_current` tests, `save(update_fields=["source"])` clearing `referred_by`, and view redirects for a closed opening or a candidate with nowhere left to apply. I approved each RED test as written.
- **Sideways:**
  - The first seed run on the dev database reported "1 skipped". Phase 3's manual testing had left Indeed retired, so Ben's Indeed application was skipped instead of undoing that change. This is the intended behavior.
  - The first headless-Edge screenshots were captured mid `animate-rise`, so everything looked faded. They were retaken with `--virtual-time-budget`.
  - The first phone shots were cropped because headless Edge has a minimum window width. They were retaken in a 360px iframe, as in Phase 4.
  - Ruff flagged one docstring over 100 characters in `accounts_tags.py`; it was shortened.
  - A drafted pre-fill test used convoluted date arithmetic. It was rewritten with explicit "days ago" per case before it was run or shown.

## 2026-10-19 — Applicant Tracking System: Phase 4/14, Job openings

### Prompts

1. The `/implement` skill, given `applicant-tracking system phase 4`.
2. *(Openings list layout, picked from the variants in `prototypes/openings-ownership.html`)* A: Table + tabs (Recommended)
3. Lets go ahead and add some addional safeguards the form must valudate the submitted authority against and query that contains them not just of a simple dropdown. A handcrafted post containing an interviewers primary key must fail validation
4. This test is good move to next
5. This test looks good one thing I would change its to make sure that it is using the projects role convention to identify a users role. Do not make a new role or hierarchy just to make this test pass.

### Summary

- **Outcome:** A new `openings` app. Recruiters, Hiring Managers and Admins create and edit job openings: title, department, optional location, description, status, and a required designated authority picked from active Admins, Recruiters and Hiring Managers. Interviewers and users without a role see everything but get a 403 on create or edit. `/openings/` uses layout Variant A: **My openings / All** tabs with counts, which switch through HTMX and update the URL. Rows are listed open first, each with its department, location, authority ("you" on your own) and status, and stack into cards on phones. Hiring Managers start on My openings and everyone else on All. A filtered list says "Showing 3 of 6 openings · Show all", and every opening opens by URL for every role. `seed` adds six openings (four open, two closed) split across manager, recruiter and admin. A re-run changes nothing and keeps staff changes to status and authority. 254 tests pass (86 new); `ruff check` and `ruff format` are clean. All six Phase 4 acceptance criteria are ticked.
- **Changes:**
  - `openings/` (new app): `models.py` (`JobOpening` with `Status` choices and a status check constraint, a PROTECT foreign key to the authority, timestamps, and a queryset with `in_scope()` and `open_first()`); `scopes.py` (`MINE`/`ALL`, `default_scope()`, `resolve_scope()`); `forms.py` (`JobOpeningForm` for editing with no authority field; `JobOpeningCreateForm` adds an `AuthorityChoiceField` whose queryset is `eligible_authorities()`, labelled "Name · Role", with clear required and invalid-choice messages); `views.py` (thin list, detail, create and update views; the list returns only the results partial for HTMX and the full page for history restores); `urls.py` (`openings:list`, `create`, `detail`, `update`); `admin.py` (the admin's authority dropdown uses the same eligible query); `migrations/0001_initial.py`; `templates/openings/` (list, detail, form, plus `results`, `authority` and `status_badge` partials).
  - `accounts/permissions.py`: `OPENING_MANAGER_ROLES` / `can_manage_openings`, plus `AUTHORITY_ROLES`, `can_be_designated_authority()` and `eligible_authorities()`. The query uses `Exists`, so a user in two groups is listed once. `accounts_tags.py`: a `can_manage_openings` filter.
  - `config/htmx.py` (new): `is_htmx_partial`, moved out of `candidates/views.py` so both apps share it.
  - `accounts/management/commands/seed.py`: `SEED_OPENINGS` and `seed_opening()`, keyed on (title, department). Status and authority are set only on creation; location and description are repaired.
  - `config/settings.py`, `config/urls.py`, `templates/partials/nav_links.html` (an Openings link), and `templates/icons/` (map-pin, building-2 and user-check from lucide-static v1.49.0).
  - Tests: `openings/tests/` (`conftest.py`, `test_models.py`, `test_scopes.py`, `test_forms.py`, `test_views.py`); `accounts/tests/test_permissions.py` and `test_seed.py` extended (openings added to the idempotency snapshot).
  - `CLAUDE.md`, `docs/TESTING.md`, `README.md`: the new permission and filter, the authority-queryset rule, the shared HTMX helper, the "post a pk the dropdown never offers" test pattern, and the updated status, features and layout.
  - `plans/applicant-tracking-system.md`: Phase 4 criteria ticked.
- **TDD:** The plan's two candidates, each red on an assertion and then green:
  1. *Designated authority eligibility.* A test parametrized over seven users (Admin, Recruiter, Hiring Manager, Interviewer, no role, inactive Hiring Manager, inactive Admin). It asserts that `can_be_designated_authority()` and membership in `eligible_authorities()` both give the expected answer. It was red because the placeholders refused everyone (`assert False is True`). The fix: `has_role(user, *AUTHORITY_ROLES)`, and the matching query "active and (superuser or in an authority group)".
  2. *Default list filter by role.* A test parametrized over six users, including an Admin who is also in the Hiring Manager group (`has_role` passes Admins for every role, so that would be the obvious bug). It was red because the placeholder always returned "all". The fix: `MINE if role_label(user) == HIRING_MANAGER else ALL`.
- **Decisions:** Eligible authorities are active Admins, Recruiters and Hiring Managers; users without a role are excluded. The edit form shows the authority read-only, because Phase 14 makes changing it a Recruiter/Admin action that logs an event and sends an email; otherwise Hiring Managers could get around that rule. Status stays in the form for now, as the plan says, until Phase 10's Close/Reopen actions. Both tabs appear for every role, and an Interviewer's empty My openings explains why. A bad `?show=` falls back to the role default. Description is required and only location is optional, as the PRD lists them. From Variant A, the agent dropped the "Unassigned" tab (an authority is always required), the edit modal (edit has its own page, like candidates) and the inline owner dropdown (Phase 14). The edit heading uses the form's initial title, so a failed save doesn't rename the heading. The page templates use Django's default `jobopening_*` names.
- **Deviations:** The layout question was the plan's open choice, and I took the recommended Variant A. At the brief I asked for an extra safeguard: the form must validate the authority against a query, not just a dropdown, and a hand-made POST with an Interviewer's pk must fail. The create form's choice field uses `eligible_authorities()` as its queryset, so the same query lists and validates. Ordinary tests post the pks of an Interviewer, a user without a role, an inactive manager and a nonexistent user, at the form and view level. They assert the error "Pick an active Admin, Recruiter or Hiring Manager." and that nothing is saved; the Django admin is checked too. At cycle 2's RED step I asked that the rule use the project's role convention, with no new role helper or ranking. It uses the existing `role_label()` and `HIRING_MANAGER` constant, and the test didn't change.
- **Sideways:** The first view-test run failed with `TemplateDoesNotExist: openings/jobopening_detail.html`: the detail template had been named `opening_detail.html`. Both page templates were renamed to Django's defaults. Two of the agent's assertions expected `&#x27;` for apostrophes, but Django escapes only variables, not literal template text; the assertions were fixed. One shell heredoc writing the templates failed to parse and wrote nothing, so they were written with the file tool instead. The first screenshot loop wrote no files because of a backslash before `$f` in the output path, and was rerun. Headless-Edge screenshots (desktop and a 360px iframe, light and dark) showed the "Show all" link was hard to read in the dark theme (the same dim primary colour as Phase 1), so these links now use the plain text colour. They also showed the detail page's large icon squeezing the title on phones, so it is now hidden below `sm`. On phones, a long authority name next to the "Closed" badge is truncated; noted and left alone.

## 2026-10-19 — Applicant Tracking System: Phase 3/14, Sources

### Prompts

1. The `/implement` skill, given `applicant-tracking system phase 3`.
2. Ok one more test since we are seeding twice can e make a test to ensure that it does not duplicate sources, and that re-running it does not accidentally reactivate a source that an admin intentionally retired.
3. This test looks good go ahead and move to next after greenlighting
4. Ok this test looks good continue to developing, also from now on go ahead an move to next phase instead of moving to green, you can update implement if necessary.

### Summary

- **Outcome:** A `/sources/` page that every role can view. Recruiters and Admins add a source (a name plus one of four categories: Company website, Job board, Referral or Other), rename it, and retire or reactivate it. Retire and Reactivate swap the sources table in place through HTMX. Active sources are listed first, with retired ones in a dimmed section below. Hiring Managers, Interviewers and users without a role see the page read-only, with a note, and get a 403 if they request an action directly. Names are unique regardless of capitals, enforced by the database. The category is enforced by the form and a database check. No URL or admin action deletes a source. `seed` adds six sources in all four categories (one retired). A re-run creates nothing new and never undoes a deliberate retirement or reactivation. 168 tests pass (58 new); `ruff check` and `ruff format` are clean. All five Phase 3 acceptance criteria are ticked.
- **Changes:**
  - `candidates/models.py`: `SourceCategory` (also available as `Source.Category`), `SourceQuerySet` with `active()` and `retired()`, and `Source` with a unique constraint on `Lower("name")`, a category check constraint, case-insensitive name ordering, `retire()` / `reactivate()`, and a `validate_constraints()` override that puts the name-clash error on the name field.
  - `candidates/migrations/0002_source.py` (new).
  - `candidates/forms.py`: `SourceForm` (name and category) and `SourceRenameForm` (name only). `CandidateForm` now uses the shared mixin.
  - `config/forms.py` (new): `DaisyUIFormMixin`, the widget-class and `aria-invalid` code moved out of `CandidateForm` so both forms share it.
  - `candidates/views.py`: `SourceListView`, `SourceCreateView`, `SourceRenameView` (keeps the saved name for the heading when a rename fails), and `SourceActivationView` (POST only; returns the table partial for HTMX, or redirects with a message otherwise).
  - `candidates/source_urls.py` (new, `app_name = "sources"`), mounted at `sources/` in `config/urls.py`.
  - `candidates/templates/candidates/`: `source_list.html`, `source_form.html`, `partials/source_table.html`, `partials/source_row.html` (a category icon and colour per row; actions shrink to icons with `aria-label`s on phones).
  - `candidates/admin.py`: `SourceAdmin` with `has_delete_permission` returning False.
  - `accounts/permissions.py`, `accounts/templatetags/accounts_tags.py`: `SOURCE_MANAGER_ROLES`, `can_manage_sources()` and the matching filter.
  - `accounts/management/commands/seed.py`: `SEED_SOURCES` and `seed_source()`. It finds a source by name ignoring case, sets `is_active` only when creating it, and repairs only the category.
  - `templates/partials/nav_links.html`: a Sources link. `templates/icons/`: 8 Lucide icons from lucide-static v1.49.0 (signpost, plus, archive, archive-restore, globe, newspaper, handshake, ellipsis).
  - Tests: `candidates/tests/test_source_models.py`, `test_source_forms.py`, `test_source_views.py` (new); `accounts/tests/test_permissions.py` and `test_seed.py` extended (sources added to the idempotency snapshot).
  - `.claude/skills/tdd/SKILL.md`, `.claude/skills/implement/SKILL.md`: after GREEN, summarize and carry on; the only stop in each cycle is the RED approval (prompt 4).
  - `CLAUDE.md`, `docs/TESTING.md`, `README.md`: the sources namespace, the new permission and filter, the form mixin, the seed rule about deliberate state changes, the `bulk_create` uniqueness test, and the updated status, features and layout.
  - `plans/applicant-tracking-system.md`: Phase 3 criteria ticked.
- **TDD:** The plan's two candidates, each red on an assertion and then green:
  1. *Source names are unique regardless of case.* The test saves "LinkedIn", then uses `bulk_create` (which skips forms and `save()`) to insert "LinkedIn", "linkedin" and "LINKEDIN", expecting an `IntegrityError` each time. It was red with "DID NOT RAISE". The fix: a `UniqueConstraint(Lower("name"))`. Names keep the capitals they were typed with.
  2. *Retired sources drop out of the active choices but still exist.* The test retires "Indeed" and checks that `active()` leaves it out, `all()` still has it with `is_active=False`, and reactivating brings it back. It was red because the placeholder `active()` returned everything. The fix: filter on `is_active=True`.
- **Decisions:** Extra URLs beyond the plan's `/sources/` (`new/`, `<pk>/edit/`, `<pk>/retire/`, `<pk>/reactivate/`) under a `sources:` namespace, although Source lives in the `candidates` app. Renaming changes the name only: a source keeps the category it was added with, because the PRD's story is "rename to fix typos". Add and Rename use their own form pages, as candidates do; Retire and Reactivate use HTMX. No timestamps on Source, since the PRD lists none. The category is also checked in the database, matching the candidate email rule. The rename heading shows the saved name, because a failed form copies the typed name onto the object.
- **Deviations:** At the brief I asked for an extra seed test: re-running must not duplicate sources or reactivate one an Admin retired. The agent pointed out that the seed's existing "repair drifted records" pattern would cause exactly that bug for sources. So `seed_source()` sets `is_active` only on creation and matches names ignoring case. The test also covers the reverse case (a reactivated seed source stays active) and a change of capitals. It was written before the seed code as an ordinary test, not a third TDD cycle, because a simple correct seed would have passed it with no meaningful red step. Remaining limit: a full rename of a seeded source (say "Indeed" → "Indeed.com") makes a re-run add a new "Indeed". At prompt 4, I asked for TDD to carry on after GREEN instead of stopping, and the agent updated both skills.
- **Sideways:** The first `CheckConstraint` referred to `Category` from inside `Meta`, which Python's class scoping can't see (`NameError` during `makemigrations`). The choices moved to a module-level `SourceCategory`, with `Source.Category` kept as an alias. `0002_source.py` was regenerated twice before it was ever applied. Ruff flagged five long lines; most were in the generated migration and were fixed by `ruff format`, the rest by hand. Headless-Edge screenshots showed yellow "Retire" text and a yellow "Retired" badge with poor contrast in the light theme; both are now neutral. The 360px screenshots first looked cut off. Headless Edge won't lay out narrower than about 492px, so the phone checks were redone inside a 360px iframe, which showed the layout fits. In the dark theme, the blue Company website icon is dim, like the Phase 1 nav contrast issue; noted and left alone.

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