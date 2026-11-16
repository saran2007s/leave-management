# Leave Management System

A full-stack Leave Management web application built with **Python 3.11+**, **FastAPI**, **SQLAlchemy 2.x**, **SQLite**, **JWT authentication**, **Jinja2**, **Chart.js**, and **FullCalendar**.

## Features & Business Rules

1. **Working Days Calculation**: Counts days from `start_date` to `end_date` inclusive, excluding Saturdays, Sundays, and dates configured in `PublicHoliday`. Requests with `0` working days are rejected.
2. **Date Validation**: `end_date` cannot be before `start_date`, and requests must stay within a single calendar year.
3. **Minimum Notice**: `start_date - today >= min_notice_days` (loaded dynamically from the database `Setting` table). **Assumption:** *Sick leave is exempt from the minimum notice rule* so employees can log sudden illnesses on the same day.
4. **Yearly Leave Balance**: Computed per `(employee, leave_type, calendar_year)` as `yearly_allowance - (approved + pending days)`.
5. **No Self-Overlap**: An employee cannot submit overlapping `pending` or `approved` requests across any leave type (`rejected` and `cancelled` requests do not block).
6. **Team Capacity Cap**: A team consists of all employees sharing the same `manager_id`. On every working day of a request, `(other teammates off + 1) <= max_off_per_day`. Violations name the first offending date.
7. **Approval & Cancellation Workflow**:
   - Requests start as `pending` and run all rule checks at creation.
   - Managers can `approve` or `reject` only `pending` requests of their direct reports (`403` otherwise). Approval re-checks balance, overlap, and team cap (excluding the request itself).
   - Employees can `cancel` their own `pending` requests or `approved` requests whose `start_date` is strictly in the future, automatically returning days to their balance.
8. **Server-Enforced Roles**: `employee`, `manager`, and `admin` permissions are enforced on the server via FastAPI dependencies (`require_role`), returning `403 Forbidden` on unauthorized actions.
9. **Live Admin Configuration**: Admins can update `LeaveType.yearly_allowance`, `min_notice_days`, `max_off_per_day`, and `PublicHoliday` dates via the Admin UI/API, taking effect immediately without restarting or editing code.
10. **Team Availability Summary (Optional Gemini AI)**: Uses `GEMINI_API_KEY` if configured, or automatically falls back to a deterministic template summary when no API key is set.

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy 2.x, Pydantic v2, SQLite (`leave.db`)
- **Auth**: JWT (`python-jose`), PBKDF2-HMAC-SHA256 password hashing (`hashlib`)
- **Frontend**: Jinja2 templates, vanilla JS (`fetch`), Chart.js & FullCalendar (CDN)
- **Tests**: `pytest` + FastAPI `TestClient` with an isolated in-memory SQLite DB

## Setup & Running

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed demo data (creates leave.db; safe to re-run)
python seed.py

# 4. Run the automated test suite
pytest -v

# 5. (Optional) Enable Gemini AI team summary
# PowerShell: $env:GEMINI_API_KEY="your-key"
# macOS/Linux: export GEMINI_API_KEY="your-key"

# 6. Start the server
uvicorn app.main:app --reload