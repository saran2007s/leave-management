from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import LeaveRequest, LeaveType, PublicHoliday, Setting, User
from app.services.working_days import count_working_days, iter_working_days


def get_holiday_dates(db: Session) -> set[date]:
    """Load all public holiday dates from the database."""
    rows = db.query(PublicHoliday.date).all()
    return {row[0] for row in rows}


def get_int_setting(db: Session, key: str) -> int:
    """Read an integer setting from the database (never hardcoded)."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing system setting: '{key}'.",
        )
    try:
        return int(setting.value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid integer value for setting '{key}'.",
        )


def validate_dates_and_count_days(
    start_date: date,
    end_date: date,
    holidays: set[date],
) -> int:
    """Validate date ordering, calendar year boundary, and non-zero working days."""
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date cannot be before start date.",
        )

    if start_date.year != end_date.year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date and end date must be in the same calendar year.",
        )

    days_count = count_working_days(start_date, end_date, holidays)
    if days_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request contains no working days.",
        )

    return days_count


def check_min_notice(
    db: Session,
    leave_type: LeaveType,
    start_date: date,
    today: date | None = None,
) -> None:
    """Enforce min_notice_days from DB. Sick leave is exempt."""
    if leave_type.name.strip().lower() == "sick":
        return

    min_notice_days = get_int_setting(db, "min_notice_days")
    reference_today = today or date.today()
    notice_given = (start_date - reference_today).days

    if notice_given < min_notice_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Leave requests require at least {min_notice_days} day(s) of advance notice.",
        )


def check_balance(
    db: Session,
    user_id: int,
    leave_type: LeaveType,
    year: int,
    requested_days: int,
    exclude_request_id: int | None = None,
) -> None:
    """Ensure requested days do not exceed remaining yearly allowance for the user and type."""
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    query = db.query(func.coalesce(func.sum(LeaveRequest.days_count), 0)).filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.leave_type_id == leave_type.id,
        LeaveRequest.status.in_(["approved", "pending"]),
        LeaveRequest.start_date >= year_start,
        LeaveRequest.end_date <= year_end,
    )
    if exclude_request_id is not None:
        query = query.filter(LeaveRequest.id != exclude_request_id)

    used_days = int(query.scalar() or 0)
    remaining = leave_type.yearly_allowance - used_days

    if requested_days > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient {leave_type.name} leave balance for {year}: "
                f"requested {requested_days} day(s), remaining {remaining} day(s)."
            ),
        )


def check_employee_overlap(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    exclude_request_id: int | None = None,
) -> None:
    """Reject if [start_date, end_date] overlaps any pending or approved request of the same employee."""
    query = db.query(LeaveRequest).filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )
    if exclude_request_id is not None:
        query = query.filter(LeaveRequest.id != exclude_request_id)

    overlapping = query.first()
    if overlapping is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dates overlap with an existing {overlapping.status} request "
                f"({overlapping.start_date.isoformat()} to {overlapping.end_date.isoformat()})."
            ),
        )


def check_team_cap(
    db: Session,
    user: User,
    start_date: date,
    end_date: date,
    holidays: set[date],
    exclude_request_id: int | None = None,
) -> None:
    """
    For every working day in the request, verify that (other teammates off + 1) <= max_off_per_day.
    A team is all users sharing the same manager_id.
    """
    if user.manager_id is None:
        return

    max_off_per_day = get_int_setting(db, "max_off_per_day")

    # Fetch active requests of OTHER members in the same team overlapping [start_date, end_date]
    query = (
        db.query(LeaveRequest)
        .join(User, LeaveRequest.user_id == User.id)
        .filter(
            User.manager_id == user.manager_id,
            LeaveRequest.user_id != user.id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    if exclude_request_id is not None:
        query = query.filter(LeaveRequest.id != exclude_request_id)

    teammate_requests = query.all()

    for day in iter_working_days(start_date, end_date, holidays):
        off_count = sum(1 for req in teammate_requests if req.start_date <= day <= req.end_date)
        if off_count + 1 > max_off_per_day:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Team leave cap ({max_off_per_day} off per day) would be exceeded "
                    f"on {day.isoformat()}."
                ),
            )