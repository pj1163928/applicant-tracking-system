# ATS: Applicant Tracking System

CIDM 3312 Project #1. An internal, staff-only web app for tracking job
applicants from **Applied** to **Hired**. Recruiters, hiring managers and
interviewers sign in with accounts an Admin creates; candidates never log in.

> **Status:** Phases 1–7 of 14 are complete: project setup, staff login, roles,
> the responsive layout, candidates, sources, job openings, recording applications and
> the pipeline board with its Move menu and drag-and-drop. See the [implementation plan](plans/applicant-tracking-system.md)
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
- Pipeline board: each opening has a board with a column per stage. Rejected and
  Withdrawn are collapsed to a count that expands. Each card's **Move** menu lists only
  the moves the user may make, tagged *next*, *note* or *optional note*. Skips, backward
  moves and reopens need a note, asked for in a dialog; Rejected and Withdrawn ask for an
  optional one. Only Admins, Hiring Managers and the opening's designated authority can
  move applicants into Offer or Hired, and Hired is final. A move updates only the
  affected columns, with no page reload. Illegal moves are refused on the server, and a
  card that is out of date can't overwrite a newer stage. Interviewers see the board
  without Move controls.
- Drag-and-drop: movers can also pick a card up and carry it to another stage, with a
  mouse or on a touch screen (press and hold first). The card lifts out and travels
  with the pointer, leaving a dashed slot behind. While it's carried, every stage it may
  go to is outlined green (one step forward) or amber (asks for a note) and the rest
  fade; the stage under the pointer grows, with a card-shaped gap where it would land.
  Every drop is confirmed in a dialog before anything moves (with a note where the move
  needs one), and the moved card lands with a brief glow. An illegal drop flies home,
  shakes, and is refused with a message.
- Busy stages: cards are listed newest first. A stage with more than three applicants
  shows the newest three and a "+N more · Show all" button; expanding it shows them all
  with a search box that filters by name as you type. Empty stages show an icon, sized to
  match the other stages in their row. The board fits any screen without sideways scrolling: the stages
  flow with arrows between them (stacked on phones), and Rejected and Withdrawn sit
  apart below the pipeline. A manual checklist is in [docs/MANUAL_CHECKS.md](docs/MANUAL_CHECKS.md).
- Stage history: every move is kept (from, to, who, when, note and cause), and each
  application's history opens from its card or its row on the candidate and opening pages.
- A `seed` command that creates one demo user per role, ten sample candidates, six
  sample sources (one of them retired), six openings (open and closed, split across
  three designated authorities) and eleven applications, most of them moved along the
  pipeline so the Backend Developer board has someone in every column.

**Planned** (see the [PRD](prd/applicant-tracking-system.md))

- Skills on openings.
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

**Pages look out of date?** Every page links the stylesheet as
`/static/css/tailwind.css?v=<build time>`, so a rebuilt stylesheet gets a new
address and browsers fetch it. If a page still looks old (VS Code's built-in
browser keeps its cache across sessions):

1. Check that `tailwind runserver` is running. It rebuilds the CSS when you
   save a template; plain `runserver` doesn't.
2. Reload the page. In VS Code's Simple Browser, use the reload button in its
   address bar.
3. Still old? Open the page in another browser. If that one looks right, the
   first browser is serving its cached copy from before this fix: open the
   stylesheet's address in it once (`http://127.0.0.1:8000/static/css/tailwind.css`)
   and reload that, or close and reopen VS Code.

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
applications/    applications, the stage rules, moves, stage history and the pipeline board
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
