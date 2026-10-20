# ATS: Applicant Tracking System

CIDM 3312 Project #1. An internal, staff-only web app for tracking job
applicants from **Applied** to **Hired**. Recruiters, hiring managers and
interviewers sign in with accounts an Admin creates; candidates never log in.

> **Status:** Phases 1–5 of 14 are complete: project setup, staff login, roles,
> the responsive layout, candidates, sources, job openings and recording applications. See the [implementation plan](plans/applicant-tracking-system.md)
> for what comes next.

## Features

**Built so far**

- Staff login and logout. There is no public sign-up page, and every page requires a login.
- Four roles: **Admin** (superuser), **Recruiter**, **Hiring Manager** and
  **Interviewer** (view-only), with a shared server-side check that refuses changes from
  view-only users.
- A responsive layout. Large screens get a top navigation bar, and phones and tablets get
  a slide-in sidebar. It has light and dark themes and a skip-to-content link.
- Candidates: Recruiters and Admins add and edit them (name, email, optional phone and
  notes). Emails are stored in lowercase and are unique regardless of capitals. Everyone
  can browse the list, search it by name or email as they type, and open a candidate's page.
- Sources: Recruiters and Admins add a source (a name and one of four categories:
  Company website, Job board, Referral or Other), rename it, and retire or reactivate it
  without a page reload. Names are unique regardless of capitals, and sources are never
  deleted. Everyone else sees the list read-only.
- Job openings: Recruiters, Hiring Managers and Admins create and edit them (title,
  department, optional location, description, status). Every opening has a required
  **designated authority**, chosen from active Admins, Recruiters and Hiring Managers.
  The Openings list has **My openings / All** tabs (Hiring Managers start on My openings,
  everyone else on All) and labels each opening with its authority.
- Applications: Recruiters and Admins record that a candidate applied for an open
  opening, through an active source. The source is pre-filled from the candidate's most
  recent application, and a "Referred by" field appears for Referral sources. Each
  application starts at **Applied** with its first stage-history row, and a candidate can
  apply for each opening only once. Applications are listed on the candidate's and the
  opening's pages, and an old application's form still shows a source retired since.
- A `seed` command that creates one demo user per role, ten sample candidates, six
  sample sources (one of them retired), six openings (open and closed, split across
  three designated authorities) and seven applications.

**Planned** (see the [PRD](prd/applicant-tracking-system.md))

- Skills on openings.
- Moving applications through eight stages on a per-opening pipeline board, by menu or drag-and-drop, with no page reload.
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
config/          Django settings, root URLs, the {% icon %} tag, shared form and HTMX helpers
accounts/        roles, permission rules, login, the role check (RoleRequiredMixin), seed
candidates/      candidates (search, list/detail/add/edit) and sources (/sources/)
openings/        job openings (My openings / All list, detail, create/edit)
applications/    applications and stage history (record, edit source, the stages)
templates/       skeleton.html, base.html (staff layout), partials/, icons/
assets/css/      Tailwind source CSS (themes and animations)
static/          logo and built CSS (tailwind.css is generated and git-ignored)
docs/TESTING.md  how tests are organised and written
prd/, plans/     product requirements and the phase-by-phase plan
prototypes/      throwaway design prototypes (reference only)
```

The `notifications` app arrives in a later phase.

### Documentation

- [CLAUDE.md](CLAUDE.md): architecture decisions and code conventions
- [docs/TESTING.md](docs/TESTING.md): the testing guide
- [prd/applicant-tracking-system.md](prd/applicant-tracking-system.md): requirements
- [plans/applicant-tracking-system.md](plans/applicant-tracking-system.md): implementation plan
- [PROMPTS.md](PROMPTS.md): the log of AI-assisted sessions

## Credits

Icons from [Lucide](https://lucide.dev/) (lucide-static v1.49.0), ISC License.
