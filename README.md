# ATS: Applicant Tracking System

CIDM 3312 Project #1. An internal, staff-only web app for tracking job
applicants from **Applied** to **Hired**. Recruiters, hiring managers and
interviewers sign in with accounts an Admin creates; candidates never log in.

> **Status:** Phase 1 of 14 is complete: project setup, staff login, roles and
> the responsive layout. See the [implementation plan](plans/applicant-tracking-system.md)
> for what comes next.

## Features

**Built so far**

- Staff login and logout. There is no public sign-up page, and every page requires a login.
- Four roles: **Admin** (superuser), **Recruiter**, **Hiring Manager** and
  **Interviewer** (view-only), with a shared server-side check that refuses changes from
  view-only users.
- A responsive layout. Large screens get a top navigation bar, and phones and tablets get
  a slide-in sidebar. It has light and dark themes and a skip-to-content link.
- A `seed` command that creates one demo user per role.

**Planned** (see the [PRD](prd/applicant-tracking-system.md))

- Candidates, sources and job openings with skills.
- One application per candidate per opening, moved through eight stages on a
  per-opening pipeline board, by menu or drag-and-drop, with no page reload.
- A full stage history, with notes required for unusual moves.
- Closing and reopening openings, with grace periods and candidate emails.
- Candidate archiving, and handing over a departing staff member's openings.

## Tech stack

| Area | Tool |
|---|---|
| Language and framework | Python 3.13, Django 6.1 |
| Database | SQLite |
| Packages | [uv](https://docs.astral.sh/uv/) |
| Styling | Tailwind CSS 4 + DaisyUI 5 via [django-tailwind-cli](https://github.com/django-commons/django-tailwind-cli) |
| Interactivity | [HTMX](https://htmx.org/) |
| Icons | [Lucide](https://lucide.dev/) (inline SVG) |
| Tests and linting | Pytest + pytest-django, Ruff |

## Getting started

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). It
installs the right Python version for you.

```bash
uv sync                                          # install dependencies
uv run python manage.py migrate                  # create the database and role groups
uv run python manage.py seed                     # add demo users (safe to re-run)
uv run python manage.py tailwind runserver       # build CSS and start the server
```

Then open <http://127.0.0.1:8000/>.

The first `tailwind runserver` downloads the Tailwind CLI (about 110 MB), so it
can take a minute before the server starts. On Windows, a **WinError 4551**
means Smart App Control is blocking that download; the project code is not
the cause.

### Demo accounts

Every seeded account uses the password **`demo-pass-123`** (development only).

| Username | Name | Role |
|---|---|---|
| `admin` | Avery Stone | Admin. Can also manage staff in the Django admin at `/admin/` |
| `recruiter` | Riley Chen | Recruiter |
| `manager` | Morgan Patel | Hiring Manager |
| `interviewer` | Jordan Lee | Interviewer (view-only) |

To add a staff member, sign in as `admin`, open **Manage staff** from the
account menu, add a user, and put them in the Recruiter, Hiring Manager or
Interviewer group.

## Development

```bash
uv run pytest                   # run the test suite
uv run ruff check .             # lint
uv run ruff format .            # format
```

Emails print to the console in development; tests capture them in memory.

### Project layout

```
config/          Django settings, root URLs, and the {% icon %} template tag
accounts/        roles, login, the role check (RoleRequiredMixin), and the seed command
templates/       skeleton.html, base.html (staff layout), partials/, icons/
assets/css/      Tailwind source CSS (themes and animations)
static/          logo and built CSS (tailwind.css is generated and git-ignored)
docs/TESTING.md  how tests are organised and written
prd/, plans/     product requirements and the phase-by-phase plan
prototypes/      throwaway design prototypes (reference only)
```

More apps (`candidates`, `openings`, `applications`, `notifications`) arrive
in later phases.

### Documentation

- [CLAUDE.md](CLAUDE.md): architecture decisions and code conventions
- [docs/TESTING.md](docs/TESTING.md): the testing guide
- [prd/applicant-tracking-system.md](prd/applicant-tracking-system.md): requirements
- [plans/applicant-tracking-system.md](plans/applicant-tracking-system.md): implementation plan
- [PROMPTS.md](PROMPTS.md): the log of AI-assisted sessions

## Credits

Icons from [Lucide](https://lucide.dev/) (lucide-static v1.49.0), ISC License.
