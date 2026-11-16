# Leave Management System

A full-stack web app where employees request leave, managers approve or reject it, and admins configure the rules. Balance, overlap and team-coverage rules are enforced on the server, and every rule value is read from the database, so changing a setting changes behavior immediately with no code change.

**Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, SQLite, Pydantic v2, JWT auth, Jinja2, vanilla JavaScript, Chart.js, FullCalendar.

Once running, the app is at **http://127.0.0.1:8000** and the interactive API docs are at **http://127.0.0.1:8000/docs**.

---

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed demo data (creates leave.db, safe to re-run)
python seed.py

# 4. Run the automated tests
pytest -v

# 5. Start the server
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and sign in with a demo account below.

**Optional: AI team summary.** Set a free Gemini API key from Google AI Studio before step 5. Without a key, a template-based summary is shown instead, so the feature works either way.

```bash
$env:GEMINI_API_KEY="your-key"      # Windows PowerShell
# export GEMINI_API_KEY="your-key"  # macOS / Linux
```

---

## Demo Accounts

All accounts use the password `password123`.

| Role | Email | Team | What they can do |
|---|---|---|---|
| Admin | `admin@demo.com` | n/a | Edit leave allowances, `min_notice_days`, `max_off_per_day`, public holidays; view all calendars |
| Manager 1 | `manager1@demo.com` | Team 1 (`emp1` to `emp4`) | Approve or reject Team 1 requests; view Team 1 calendar |
| Manager 2 | `manager2@demo.com` | Team 2 (`emp5` to `emp8`) | Approve or reject Team 2 requests; view Team 2 calendar |
| Employees | `emp1@demo.com` to `emp8@demo.com` | Their manager's team | Request and cancel own leave; view own balance, chart and team calendar |

**Seed data:** 1 admin, 2 managers, 8 employees; 3 leave types (Annual 20, Sick 10, Unpaid 30); 10 public holidays; 40 leave requests in mixed states. Settings start at `min_notice_days = 2` and `max_off_per_day = 2`.

---

## Features

- **Roles enforced on the server:** employee, manager and admin permissions are checked by FastAPI dependencies, not just hidden in the UI.
- **Leave request form** with a live working-day preview.
- **Balance summary** per leave type, with a chart.
- **Team calendar** (FullCalendar), scoped by role.
- **Approval workflow:** pending, approved, rejected or cancelled.
- **Admin page** to edit allowances, minimum notice, team cap and public holidays.
- **AI team availability summary** (optional Gemini, with template fallback).

---

## Business Rules

| # | Rule | Details |
|---|---|---|
| 1 | Working days | Counted from start to end date inclusive. Saturdays, Sundays and public holidays are excluded. A request with 0 working days is rejected. |
| 2 | Date validation | End date cannot be before the start date. A request must stay within one calendar year. |
| 3 | Minimum notice | `start_date - today` must be at least `min_notice_days`. Sick leave is exempt. |
| 4 | Balance | Per employee, leave type and year: `remaining = yearly_allowance - (approved + pending days)`. A request larger than `remaining` is rejected. |
| 5 | No self-overlap | An employee cannot have overlapping pending or approved requests (any leave type). Rejected and cancelled requests do not count. |
| 6 | Team cap | A team is everyone with the same manager. On each working day of the request, `other teammates off + 1` must not exceed `max_off_per_day`. The error names the first offending date. |
| 7 | Approval workflow | A new request is `pending`. A manager can approve or reject only pending requests of their own reports (otherwise 403). Approval re-checks balance, overlap and team cap. |
| 8 | Cancellation | An employee can cancel a pending request, or an approved request that starts in the future. Because balance counts only approved and pending days, cancelling returns the days automatically. |
| 9 | Who requests leave | Only employees. Managers and admins get 403 on `POST /api/leaves`. |
| 10 | Live configuration | Allowances, `min_notice_days`, `max_off_per_day` and holidays live in the database and are read on every request. |

All rule violations return JSON like `{"detail": "human readable reason"}` with status 400 (rules), 403 (permissions), 404 (not found) or 401 (not logged in).

### Assumptions

- Sick leave is exempt from the minimum notice rule, so sudden illness can be logged.
- A single request cannot cross a calendar-year boundary (keeps balance accounting simple).
- Managers and admins do not request leave; admins configure, managers approve.
- The default JWT secret is for demo use only. Set `JWT_SECRET_KEY` in the environment for anything real.

---

## Architecture

```text
leave-management/
  app/
    main.py             FastAPI app, DB creation on startup, static files, HTML page routes
    database.py         SQLAlchemy engine (leave.db), session, get_db dependency
    models.py           ORM tables: User, LeaveType, LeaveRequest, PublicHoliday, Setting
    schemas.py          Pydantic request/response models
    auth.py             Password hashing (PBKDF2), JWT, get_current_user, require_role
    services/
      working_days.py   Pure date helpers, no database access
      rules.py          Rule checks (dates, notice, balance, overlap, team cap)
      leave_service.py  Create / approve / reject / cancel in one transaction
      summary.py        Team availability summary (Gemini or template fallback)
    routers/
      auth_router.py    Login and current user
      leave_router.py   Leave requests, balances, previews, approve/reject
      team_router.py    Team calendar, summary, managers list
      admin_router.py   Allowances, settings, holidays (admin only)
    templates/          Jinja2 pages: login, dashboard, request, approvals, calendar, admin
    static/             app.js (fetch helper, JWT, toasts) and style.css
  tests/                27 pytest tests on an isolated in-memory database
  seed.py               Deterministic, re-runnable demo data
  requirements.txt
```

**How a request flows**

1. The browser loads a page from `main.py`. `app.js` reads the JWT from `localStorage` (redirecting to `/login` if missing) and sends it as `Authorization: Bearer <token>` on every call.
2. A router validates the payload with Pydantic and runs `get_current_user` and `require_role(...)`, which return 401 or 403 when needed.
3. `leave_service.py` loads live settings and holidays, computes working days, and runs every check in `rules.py` inside one database transaction. A rule violation rolls back and returns 400.
4. SQLAlchemy reads and writes `leave.db`, and the JSON response updates the tables, chart and calendar.

---

## Data Model

| Table | Columns | Notes |
|---|---|---|
| `users` | `id`, `name`, `email` (unique), `password_hash`, `role`, `manager_id` | `role` is employee, manager or admin. `manager_id` points to another user; it is null for managers and admins. |
| `leave_types` | `id`, `name` (unique), `yearly_allowance` | Annual, Sick, Unpaid. Editable by admins. |
| `leave_requests` | `id`, `user_id`, `leave_type_id`, `start_date`, `end_date`, `days_count`, `reason`, `status`, `created_at`, `decided_by`, `decided_at` | `status` is pending, approved, rejected or cancelled. `days_count` stores working days at creation. |
| `public_holidays` | `id`, `date` (unique), `name` | Excluded from working-day counts. |
| `settings` | `key`, `value` | Holds `min_notice_days` and `max_off_per_day`. |

Relationships: a user has many leave requests; a manager has many reports (`manager_id`); each request belongs to one leave type and may record the manager who decided it.

---

## API Overview

Full interactive docs are at `/docs`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `GET /api/me` |
| Leave (employee) | `POST /api/leaves`, `GET /api/leaves/my`, `POST /api/leaves/{id}/cancel`, `GET /api/leaves/balances?year=`, `GET /api/leaves/preview-days`, `GET /api/leaves/types`, `GET /api/leaves/holidays` |
| Leave (manager) | `GET /api/leaves/team`, `POST /api/leaves/{id}/approve`, `POST /api/leaves/{id}/reject` |
| Team | `GET /api/team/calendar`, `GET /api/team/summary`, `GET /api/team/managers` |
| Admin | `GET/PUT /api/admin/leave-types`, `GET/PUT /api/admin/settings`, `GET/POST/DELETE /api/admin/holidays` |

---

## Tests

27 automated tests run against a fresh in-memory SQLite database (see `tests/conftest.py`):

```bash
pytest -v
```

| File | Tests | Covers |
|---|---|---|
| `test_working_days.py` | 6 | Mon to Fri, Fri to Mon across a weekend, holiday exclusion, weekend-only, single holiday, reversed range |
| `test_rules.py` | 7 | End before start, cross-year, zero working days, notice (with sick exemption), balance with pending counted, overlap ignoring cancelled and rejected, team cap |
| `test_workflow.py` | 4 | Create, approve, cancel restores balance; cannot cancel a started request; reject and invalid transitions; approval re-checks balance |
| `test_roles.py` | 6 | 401 when logged out; 403 for manager or admin requesting leave; 403 on approve for wrong roles or another team's manager; 403 cancelling someone else's request; 403 on admin endpoints; role-scoped calendar |
| `test_config.py` | 4 | Changing allowance, minimum notice, team cap or holidays changes behavior immediately |

---

## Notes for Reviewers

- The balance, overlap and team-cap rules and the cancel-restores-balance behavior are covered by automated tests.
- Roles are enforced on the server; hiding buttons in the UI is only a convenience.
- Changing any configured value in the Admin page changes behavior on the next request, with no restart or code change.
