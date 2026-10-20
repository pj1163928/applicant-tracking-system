---
name: implement
description: Build one phase of a feature plan end to end — read the PRD and plan, follow the phase's TDD section, implement and test the phase, write a manual browser test guide, and log the session in PROMPTS.md. Never commits. Use when the user runs /implement.
argument-hint: "<feature> [phase <N>] [tdd|no-tdd] [notes]"
disable-model-invocation: true
---

# Implement

Build one phase of `plans/<feature>.md` against `prd/<feature>.md`, from
reading the plan through to the PROMPTS.md entry. Never stage, commit or
push; the user does that themselves.

## 1. Find the phase

- **Feature**: the first argument (`product-reviews`, or
  `@plans/product-reviews.md`). If none was given, list `plans/` and ask
  which one.
- Read `plans/<feature>.md` and `prd/<feature>.md` in full. If either is
  missing, stop and say which.
- **Phase**: the number given. Otherwise, the first phase that still has an
  unticked acceptance criterion. Check it against
  `git log --oneline` (commits named "Phase N/M of …"). If the two disagree,
  ask.
- Anything else in the arguments is an instruction for this phase and
  outranks the plan. Everything not stated comes from the PRD and plan.
- Run `git status --short` and note any files already modified. They do not
  belong to this phase.

## 2. Gather context

- Read the plan's architectural decisions, the phase itself, and the PRD
  sections behind the phase's user stories. Where the plan says "per the
  PRD", the PRD's wording is authoritative.
- Read [docs/TESTING.md](../../../docs/TESTING.md), and every
  "Read before…" doc in `CLAUDE.md` that covers an area this phase touches.
- Read the code that earlier phases built, and the existing pattern closest
  to the one this phase needs. The plan often names that pattern, such as the
  wishlist's template tag.

Fill any gaps from the PRD first, then from the codebase's existing patterns.
Ask only when the answer is genuinely the user's call and it changes what gets
built.

## 3. Follow the phase's TDD section

The TDD decision is already made in the plan. Read the phase's `### TDD`
section and follow it; do not propose candidates of your own.

- **It lists candidates:** delegate to the `tdd` skill with exactly those
  behaviors, and tell it to use them instead of selecting its own.
- **It says no TDD:** skip TDD. The phase gets ordinary tests.

If the user passed `tdd` or `no-tdd`, or named different behaviors, that
overrides the plan.

## 4. Brief, then stop once

Present all of this in one message:

- the phase title, plus a few lines on what will be built
- the areas and files expected to change, including any migrations
- the decisions you made where the plan left a gap
- the TDD decision from the plan: the candidate behaviors, or "no TDD"

**With TDD:** invoke the `tdd` skill now with the plan's candidates and
include them in this message. The approval it asks for is this step's stop.

**Without TDD:** stop for approval.

After approval, the only further stops are the ones the `tdd` cycles require
and any question that is genuinely the user's call.

## 5. Build

- Follow the conventions in `CLAUDE.md`. Logic goes in models and managers,
  cross-model workflows get a service module, views are thin and
  class-based, and every URL is named and namespaced. Every public function
  in a deep module gets a docstring and type hints.
- With TDD, follow the `tdd` skill's rules for the approved behaviors. Every
  other acceptance criterion still gets ordinary tests.
- If the models change, make migrations. If the phase extends the seed, run
  `seed` twice to confirm it is idempotent.
- Stay inside the phase. If you notice something a later phase needs, note
  it; do not build it.
- While building, run only the tests for what this phase touches: the
  phase's own app (`uv run pytest candidates`), one file, or `-k` by name,
  plus the tests of any shared module you changed (for example
  `accounts/tests/test_seed.py` after extending the seed). Do not run the
  full suite after each step or TDD cycle.
- Run the full suite (`uv run pytest`) once, at the end of the build. Run it
  earlier only when something points to a cross-app break: a failing import
  or migration, or a change to shared code such as settings, `base.html`,
  `accounts.roles`, `RoleRequiredMixin` or `conftest.py`.
- Before finishing, the full `uv run pytest` must be green, and
  `uv run ruff check .` and `uv run ruff format .` must be clean. Never
  finish red. If something will not pass, report it with its output.
- In the plan, tick each acceptance criterion (`- [x]`) once it is built and
  either covered by a test or checked by hand. Leave any unmet criterion
  unticked and explain why.

## 6. Manual browser test guide

Write it for the user to follow in a browser, and give it in the reply, not
in a file. Include:

- **Setup**: the commands to run, in order: `migrate` if there are new
  migrations; `seed` if the seed changed (warn that it resets the database);
  then `uv run python manage.py tailwind runserver`, with the URL to open. If
  Tailwind fails with WinError 4551, Windows Smart App Control is blocking
  its binary; the code is not the cause.
- **Accounts**: which seeded users to sign in as, with credentials taken from
  the `seed` command. Never guess them.
- **Walkthroughs**: numbered steps for each scenario: where to go, what to
  click or type, and what should happen. Cover:
  - the happy path
  - each role that sees something different (visitor, customer, staff,
    superuser)
  - validation errors
  - the edge cases named in the acceptance criteria
- **What to look for**: be specific:
  - exact wording
  - which part of the page updates. An HTMX swap should not reload the
    page; the Network tab shows the partial.
  - counts and states after each action
  - light and dark themes, and phone width if the layout changed
- **Signs of a problem**: the symptoms that would mean something is wrong.

Leave out anything a browser cannot show.

## 7. Log the session in PROMPTS.md

When the user runs `/implement`, that is their instruction to log the
session. Add the new entry at the top: right after the `---` that ends the
header, above every earlier entry. Never edit an older entry. Use the file's
established shape, with a **Changes** list added:

    ## YYYY-MM-DD — <Feature>: Phase N/M, <phase title>

    ### Prompts

    1. The `/implement` skill, given `<arguments>`.
    2. Every later prompt, in order, including approvals and corrections.

    ### Summary

    - **Outcome:** what was built; the test count; ruff status
    - **Changes:**
      - `path/to/file` — what changed and why
    - **TDD:** the behaviors driven by tests, or why the phase skipped TDD
    - **Decisions:** gaps in the plan that you filled, and how
    - **Deviations:** recommendations the user overrode, follow-up questions
    - **Sideways:** failures and wrong turns, and how they were caught

## 8. Finish

End with `git status --short` so the user can see what changed, noting any
files that were already modified before the phase began (from step 1). Do
not stage, commit or push.
