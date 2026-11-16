from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import LeaveRequest, LeaveType, PublicHoliday, Setting, User


def count_working_days_local(start: date, end: date, holidays: set[date]) -> int:
    """Count working days (Mon-Fri, excluding public holidays) inclusive."""
    total = 0
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            total += 1
        current += timedelta(days=1)
    return total


def working_dates_in_range(start: date, end: date, holidays: set[date]) -> list[date]:
    """Return every working date between start and end inclusive."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days


def seed():
    # Create tables if they do not exist yet
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Wipe existing data in child-to-parent order so re-runs are clean
        db.query(LeaveRequest).delete()
        db.query(PublicHoliday).delete()
        db.query(Setting).delete()
        db.query(LeaveType).delete()
        db.query(User).delete()
        db.commit()

        default_hash = hash_password("password123")

        # 2. Users: 1 admin, 2 managers, 8 employees (4 per manager)
        admin = User(
            name="System Admin",
            email="admin@demo.com",
            password_hash=default_hash,
            role="admin",
            manager_id=None,
        )
        manager1 = User(
            name="Priya Sharma",
            email="manager1@demo.com",
            password_hash=default_hash,
            role="manager",
            manager_id=None,
        )
        manager2 = User(
            name="Rahul Verma",
            email="manager2@demo.com",
            password_hash=default_hash,
            role="manager",
            manager_id=None,
        )
        db.add_all([admin, manager1, manager2])
        db.flush()  # Populate generated IDs before creating employees

        employees_data = [
            ("Aarav Patel", "emp1@demo.com", manager1.id),
            ("Sneha Iyer", "emp2@demo.com", manager1.id),
            ("Vikram Nair", "emp3@demo.com", manager1.id),
            ("Meera Joshi", "emp4@demo.com", manager1.id),
            ("Karan Mehta", "emp5@demo.com", manager2.id),
            ("Ananya Rao", "emp6@demo.com", manager2.id),
            ("Rohan Gupta", "emp7@demo.com", manager2.id),
            ("Divya Kapoor", "emp8@demo.com", manager2.id),
        ]
        employees: dict[str, User] = {}
        for name, email, mgr_id in employees_data:
            emp = User(
                name=name,
                email=email,
                password_hash=default_hash,
                role="employee",
                manager_id=mgr_id,
            )
            db.add(emp)
            employees[email] = emp
        db.flush()

        # 3. Leave types
        annual = LeaveType(name="Annual", yearly_allowance=20)
        sick = LeaveType(name="Sick", yearly_allowance=10)
        unpaid = LeaveType(name="Unpaid", yearly_allowance=30)
        db.add_all([annual, sick, unpaid])
        db.flush()

        leave_types = {
            "Annual": annual,
            "Sick": sick,
            "Unpaid": unpaid,
        }

        # 4. Settings
        max_off_per_day = 2
        db.add_all([
            Setting(key="min_notice_days", value="2"),
            Setting(key="max_off_per_day", value=str(max_off_per_day)),
        ])

        # 5. Public holidays for 2026 (10 dates including Dec 25)
        holiday_rows = [
            (date(2026, 1, 26), "Republic Day"),
            (date(2026, 3, 4), "Holi"),
            (date(2026, 4, 3), "Good Friday"),
            (date(2026, 5, 1), "May Day"),
            (date(2026, 8, 15), "Independence Day"),
            (date(2026, 10, 2), "Gandhi Jayanti"),
            (date(2026, 10, 20), "Dussehra"),
            (date(2026, 11, 9), "Diwali"),
            (date(2026, 11, 24), "Guru Nanak Jayanti"),
            (date(2026, 12, 25), "Christmas Day"),
        ]
        for h_date, h_name in holiday_rows:
            db.add(PublicHoliday(date=h_date, name=h_name))
        holiday_dates = {h_date for h_date, _ in holiday_rows}

        # 6. 40 leave requests: 15 approved, 12 pending, 6 rejected, 7 cancelled
        # Format: (email, leave_type_name, start_date, end_date, status, reason)
        raw_requests = [
            # --- Team 1 (manager1: emp1..emp4) ---
            ("emp1@demo.com", "Annual", date(2026, 12, 7), date(2026, 12, 9), "approved", "Family trip"),
            ("emp2@demo.com", "Annual", date(2026, 12, 7), date(2026, 12, 11), "approved", "Winter vacation"),
            ("emp3@demo.com", "Sick", date(2026, 12, 14), date(2026, 12, 16), "approved", "Flu recovery"),
            ("emp4@demo.com", "Annual", date(2026, 12, 15), date(2026, 12, 18), "approved", "Wedding attendance"),
            ("emp1@demo.com", "Annual", date(2026, 12, 21), date(2026, 12, 23), "pending", "Year-end travel"),
            ("emp2@demo.com", "Annual", date(2026, 12, 24), date(2026, 12, 28), "approved", "Christmas break"),
            ("emp3@demo.com", "Unpaid", date(2026, 12, 29), date(2026, 12, 31), "rejected", "Peak sprint week"),
            ("emp4@demo.com", "Annual", date(2026, 12, 28), date(2026, 12, 30), "cancelled", "Plans changed"),
            ("emp1@demo.com", "Sick", date(2027, 1, 4), date(2027, 1, 6), "approved", "Dental procedure"),
            ("emp2@demo.com", "Annual", date(2027, 1, 5), date(2027, 1, 8), "pending", "Home visit"),
            ("emp3@demo.com", "Annual", date(2027, 1, 11), date(2027, 1, 15), "approved", "Hill station trip"),
            ("emp4@demo.com", "Sick", date(2027, 1, 13), date(2027, 1, 15), "pending", "Medical checkups"),
            ("emp1@demo.com", "Annual", date(2027, 1, 18), date(2027, 1, 20), "rejected", "Release deadline"),
            ("emp2@demo.com", "Sick", date(2027, 2, 1), date(2027, 2, 3), "cancelled", "Rescheduled appointment"),
            ("emp3@demo.com", "Annual", date(2027, 2, 8), date(2027, 2, 10), "pending", "Personal errands"),
            ("emp4@demo.com", "Annual", date(2027, 2, 9), date(2027, 2, 12), "approved", "Brother's wedding"),
            ("emp1@demo.com", "Annual", date(2027, 2, 15), date(2027, 2, 19), "pending", "Annual holiday"),
            ("emp2@demo.com", "Unpaid", date(2027, 3, 1), date(2027, 3, 3), "pending", "Extended break"),
            ("emp3@demo.com", "Annual", date(2027, 3, 8), date(2027, 3, 10), "cancelled", "Trip postponed"),
            ("emp4@demo.com", "Unpaid", date(2027, 3, 15), date(2027, 3, 17), "rejected", "Client audit week"),
            # --- Team 2 (manager2: emp5..emp8) ---
            ("emp5@demo.com", "Annual", date(2026, 12, 8), date(2026, 12, 10), "approved", "Outstation function"),
            ("emp6@demo.com", "Sick", date(2026, 12, 9), date(2026, 12, 11), "approved", "Migraine rest"),
            ("emp7@demo.com", "Annual", date(2026, 12, 14), date(2026, 12, 18), "approved", "December holiday"),
            ("emp8@demo.com", "Annual", date(2026, 12, 16), date(2026, 12, 17), "pending", "Family event"),
            ("emp5@demo.com", "Annual", date(2026, 12, 21), date(2026, 12, 24), "pending", "Pre-Christmas travel"),
            ("emp6@demo.com", "Annual", date(2026, 12, 28), date(2026, 12, 31), "cancelled", "Decided to work"),
            ("emp7@demo.com", "Sick", date(2026, 12, 29), date(2026, 12, 30), "rejected", "Insufficient details"),
            ("emp8@demo.com", "Annual", date(2027, 1, 4), date(2027, 1, 7), "approved", "New Year trip"),
            ("emp5@demo.com", "Sick", date(2027, 1, 6), date(2027, 1, 8), "pending", "Physiotherapy"),
            ("emp6@demo.com", "Annual", date(2027, 1, 11), date(2027, 1, 13), "approved", "Short break"),
            ("emp7@demo.com", "Unpaid", date(2027, 1, 12), date(2027, 1, 14), "rejected", "Project handover"),
            ("emp8@demo.com", "Annual", date(2027, 1, 18), date(2027, 1, 22), "cancelled", "Flight cancelled"),
            ("emp5@demo.com", "Annual", date(2027, 2, 1), date(2027, 2, 5), "approved", "Trekking trip"),
            ("emp6@demo.com", "Annual", date(2027, 2, 3), date(2027, 2, 5), "pending", "Parents' anniversary"),
            ("emp7@demo.com", "Sick", date(2027, 2, 15), date(2027, 2, 17), "approved", "Eye checkup"),
            ("emp8@demo.com", "Annual", date(2027, 2, 16), date(2027, 2, 18), "cancelled", "Moved to next month"),
            ("emp5@demo.com", "Unpaid", date(2027, 3, 2), date(2027, 3, 4), "rejected", "Team capacity low"),
            ("emp6@demo.com", "Annual", date(2027, 3, 8), date(2027, 3, 11), "pending", "Hometown visit"),
            ("emp7@demo.com", "Annual", date(2027, 3, 9), date(2027, 3, 12), "pending", "Spring break"),
            ("emp8@demo.com", "Sick", date(2027, 3, 22), date(2027, 3, 24), "cancelled", "Appointment moved"),
        ]

        # Trackers to verify seeded active (approved + pending) requests obey all rules
        used_balance: dict[tuple[int, int, int], int] = defaultdict(int)
        user_active_ranges: dict[int, list[tuple[date, date]]] = defaultdict(list)
        team_day_counts: dict[tuple[int, date], int] = defaultdict(int)

        base_created = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

        for idx, (email, type_name, start, end, req_status, reason) in enumerate(raw_requests):
            emp = employees[email]
            lt = leave_types[type_name]
            days_count = count_working_days_local(start, end, holiday_dates)

            assert start <= end, f"Invalid date range for {email}: {start}..{end}"
            assert start.year == end.year, f"Year boundary crossed for {email}: {start}..{end}"
            assert days_count > 0, f"Zero working days for {email}: {start}..{end}"

            if req_status in ("approved", "pending"):
                # Verify balance
                bal_key = (emp.id, lt.id, start.year)
                used_balance[bal_key] += days_count
                assert used_balance[bal_key] <= lt.yearly_allowance, (
                    f"Balance exceeded for {email} ({type_name}, {start.year})"
                )

                # Verify no overlap for same employee
                for ex_start, ex_end in user_active_ranges[emp.id]:
                    assert not (start <= ex_end and end >= ex_start), (
                        f"Overlap for {email}: {start}..{end} vs {ex_start}..{ex_end}"
                    )
                user_active_ranges[emp.id].append((start, end))

                # Verify team cap on every working day
                for w_day in working_dates_in_range(start, end, holiday_dates):
                    cap_key = (emp.manager_id, w_day)
                    team_day_counts[cap_key] += 1
                    assert team_day_counts[cap_key] <= max_off_per_day, (
                        f"Team cap exceeded on {w_day} for manager {emp.manager_id}"
                    )

            created_at = base_created + timedelta(hours=idx * 3)
            decided_by = emp.manager_id if req_status in ("approved", "rejected") else None
            decided_at = created_at + timedelta(days=1) if decided_by else None

            db.add(
                LeaveRequest(
                    user_id=emp.id,
                    leave_type_id=lt.id,
                    start_date=start,
                    end_date=end,
                    days_count=days_count,
                    reason=reason,
                    status=req_status,
                    created_at=created_at,
                    decided_by=decided_by,
                    decided_at=decided_at,
                )
            )

        db.commit()
        print("Seeded: 11 users, 3 leave types, 2 settings, 10 holidays, 40 leave requests.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()