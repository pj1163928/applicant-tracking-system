# Testing guide

Every phase ends with `uv run pytest` green and `uv run ruff check .` plus
`uv run ruff format .` clean. Never finish a phase red.

## Running

    uv run pytest                      # whole suite
    uv run pytest accounts             # one app
    uv run pytest -k seed              # by name
    uv run ruff check . && uv run ruff format .

Pytest settings live in `pyproject.toml` (`DJANGO_SETTINGS_MODULE = "config.settings"`).
The test database is built by running the migrations, so data migrations (such as
the role groups) are present in every test.

## Layout

- Each app keeps its tests in `<app>/tests/`, one file per area: `test_roles.py`,
  `test_views.py`, `test_services.py`, `test_seed.py`, and so on.
- File names start with `test_`. Test functions are plain `def test_...`; no
  `TestCase` classes.
- Shared fixtures live in the root `conftest.py`. App-only fixtures go in
  `<app>/tests/conftest.py`.

## Fixtures

Plain pytest fixtures, no factory libraries. The root `conftest.py` provides:

| Fixture | User |
|---|---|
| `admin` | superuser ("Ada Admin") |
| `recruiter` | Recruiter group ("Rae Recruiter") |
| `hiring_manager` | Hiring Manager group ("Hal Manager") |
| `interviewer` | Interviewer group ("Ivy Interviewer") |
| `no_role_user` | logged-in user with no group |
| `make_user(username, role=None, **fields)` | factory for anything else; password is `"pw"` |

An autouse `fast_password_hashing` fixture switches every test to Django's MD5
hasher. The default hasher is deliberately slow and made the suite about 90×
slower. Settings outside tests are unchanged.

To run one test across roles, parametrize on the fixture name and use
`request.getfixturevalue(name)`. See `accounts/tests/test_mixins.py`.

## What to test, and how

- **Pure rule and permission functions** (`accounts/roles.py`,
  `accounts/permissions.py`, later the stage rules and `can_make_offer`): parametrized
  tests across every role, plus the edge cases: no group, inactive user,
  anonymous user.
- **Services** (`move_application`, closure, messaging, `deactivate_staff`):
  call the function directly and assert on the database rows it writes. For
  "nothing is written when refused", assert that the row counts are unchanged.
- **Views**: use the `client` fixture with `client.force_login(user)`. Check
  - anonymous users get a 302 to `/accounts/login/` (from `LoginRequiredMiddleware`);
  - refused roles get a **403**, for GET and POST alike. The server refuses even when the UI hides the button;
  - allowed roles get a 200 or a redirect, and the database changes.
- **Templates**: assert that hidden actions are absent from the HTML for roles
  that can't use them. Stable hooks such as `data-testid="..."` keep these
  assertions from depending on styling.
- **HTMX**: send the header with `client.post(url, data, HTTP_HX_REQUEST="true")`
  and assert that the response is the partial, not the full page (for example,
  no `<html`).
- **Email**: tests use Django's locmem backend automatically. Assert on
  `django.core.mail.outbox`, including that nothing is sent twice.
- **Dates**: never call `date.today()` inside a rule. Pass "today" in as an
  argument so tests can choose it.
- **`seed`**: call `call_command("seed")` twice and check that the second run
  changes nothing (same pks and same field values). When staff can change a
  seeded record's state on purpose (retiring a source, for example), also test
  that a re-run keeps their change and adds no duplicate.
- **Case-insensitive uniqueness**: prove the database refuses the clash with
  `bulk_create`, which skips `save()` and form validation.

## TDD

Phases that list TDD candidates in `plans/applicant-tracking-system.md` drive
those behaviors with the `/tdd` skill: one failing test (RED on an assertion),
then just enough code to pass it. Everything else gets the ordinary tests above.

Drag-and-drop (Phase 7) gets a manual browser checklist instead of browser
automation.
