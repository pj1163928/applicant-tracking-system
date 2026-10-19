# CLAUDE.md

An internal, staff-only Django applicant tracking system for CIDM 3312; candidates never log in.

## Stack
- Python, Django, SQLite, Tailwind CSS + DaisyUI via django-tailwind-cli, HTMX, Ruff, Pytest with pytest-django. All required.
- Package manager: **uv**.
- Email goes through Django's mail framework: console backend in development, locmem in tests.

## Architecture decisions (from the PRD)
- Roles are Django Groups (Recruiter, Hiring Manager, Interviewer); Admin is `is_superuser`. No self-registration.
- Every role can view everything; Interviewers are view-only. Ownership changes default filters and labels, never visibility.
- Permission rules live in pure, separately testable functions. Views and templates call them; they don't duplicate the logic.
- Stage rules live in a pure module (allowed-transitions table, `can_move`, `requires_note`).
- Business logic lives in service functions, not views. `move_application()` is the only way an application's stage changes.
- Illegal actions are refused on the server even when the UI already hides them.
- Partial page updates use HTMX; drag-and-drop uses native browser events (no SortableJS).
- Sources and skills are retired, not deleted; foreign keys to them use PROTECT.

## References
- PRD (requirements, data model, rules): [prd/applicant-tracking-system.md](prd/applicant-tracking-system.md)
- Implementation plan (phases, TDD candidates): [plans/applicant-tracking-system.md](plans/applicant-tracking-system.md)
- Prototypes: [prototypes/](prototypes/). Reference only; never promote them to production code.
- Design decisions and session history: [HANDOFF.md](HANDOFF.md), [PROMPTS.md](PROMPTS.md)
