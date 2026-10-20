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

## Conventions
- Settings live in `config/`. Each owning app (`accounts`, `candidates`, `openings`, `applications`, `notifications`) has its own models, views, `templates/<app>/` and `tests/`. Shared templates (`base.html`, `registration/`) are in `templates/`.
- Forms mix in `config.forms.DaisyUIFormMixin` for DaisyUI widget classes and invalid-input marking; list per-field classes in `CLASSES`, written out in full.
- Views are thin and class-based. Logic goes in models and managers, and cross-model workflows go in a `services.py`. Every public function in a deep module gets a docstring and type hints.
- Every URL is named and app-namespaced (`app_name = "..."`), and records are addressed by pk. Sources live in the `candidates` app but have their own `sources:` namespace at `/sources/`.
- `LoginRequiredMiddleware` makes every view need a login. Only the login page is exempt.
- Roles: use `accounts.roles` (`has_role`, `can_make_changes`, `role_label`, and the `RECRUITER`/`HIRING_MANAGER`/`INTERVIEWER` constants). Never check group names inline.
- Action rules live in `accounts.permissions`: a roles tuple plus a `can_<action>(user)` function (e.g. `CANDIDATE_MANAGER_ROLES`, `can_manage_candidates`; `SOURCE_MANAGER_ROLES`, `can_manage_sources`; `OPENING_MANAGER_ROLES`, `can_manage_openings`). Views pass the tuple as `allowed_roles`; templates use the matching `accounts_tags` filter.
- Designated authorities: `can_be_designated_authority(user)` and `eligible_authorities()` in `accounts.permissions` (active Admins, Recruiters and Hiring Managers). Any field that picks an authority uses `eligible_authorities()` as its queryset, so the same query lists the choices and validates the submitted pk; a hand-made POST naming anyone else fails validation.
- Views that change data use `accounts.mixins.RoleRequiredMixin`. It returns 403 to Interviewers by default; set `allowed_roles` to narrow it.
- Templates load `accounts_tags` (`user|role_label`, `user|can_make_changes`, `user|can_manage_candidates`, `user|can_manage_sources`, `user|can_manage_openings`) to hide actions, and the server still enforces the rule.
- UI uses DaisyUI v5 classes (`fieldset`, `input`, `btn`, …), with the `corporate` (light) and `business` (dark) themes. HTMX is loaded in `skeleton.html` and sends the CSRF token through `hx-headers`. Views that return a fragment for HTMX check `config.htmx.is_htmx_partial(request)` (full page for history restores) and send `Vary: HX-Request`.
- Templates: staff pages extend `base.html`, which has a top nav on `lg` and up and a drawer sidebar below that. Pages without navigation (login) extend `skeleton.html`. Each new section adds one `<li>` to `templates/partials/nav_links.html`, which feeds both menus.
- Icons: `{% icon "name" "size-5" %}` is a builtin, so no `{% load %}` is needed. It inlines `templates/icons/<name>.svg`, copied from lucide-static v1.49.0. Add an icon by copying its SVG there.
- Motion stays subtle: `animate-rise` (defined in `assets/css/source.css`) and hover transitions, always paired with `motion-reduce:` fallbacks. Layouts must work from 360px phones to desktop.
- `seed` (`accounts/management/commands/seed.py`) is idempotent. Each phase adds data by natural key, and a second run must change nothing. Seed never undoes a deliberate staff change to a record's state (for example, it doesn't reactivate a retired source). Every seeded user has the password `demo-pass-123`.

## Commands
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`
- `uv run python manage.py migrate`, `uv run python manage.py seed`
- `uv run python manage.py tailwind runserver` (builds CSS and serves at http://127.0.0.1:8000/)

## Read before…
- writing or changing tests: [docs/TESTING.md](docs/TESTING.md)

## References
- PRD (requirements, data model, rules): [prd/applicant-tracking-system.md](prd/applicant-tracking-system.md)
- Implementation plan (phases, TDD candidates): [plans/applicant-tracking-system.md](plans/applicant-tracking-system.md)
- Prototypes: [prototypes/](prototypes/). Reference only; never promote them to production code.
- Design decisions and session history: [HANDOFF.md](HANDOFF.md), [PROMPTS.md](PROMPTS.md)
