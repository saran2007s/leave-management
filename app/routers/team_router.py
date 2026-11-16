from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import LeaveRequest, PublicHoliday, User
from app.schemas import CalendarEventOut, HolidayOut, TeamCalendarOut, UserOut
from app.services import rules

router = APIRouter(prefix="/api/team", tags=["team"])


@router.get("/managers", response_model=list[UserOut])
def list_managers(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all users with the 'manager' role (used for calendar filtering)."""
    return db.query(User).filter(User.role == "manager").order_by(User.id).all()


@router.get("/calendar", response_model=TeamCalendarOut)
def get_team_calendar(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    manager_id: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return active ('approved' + 'pending') leave events and public holidays scoped by role:
    - employee: own team (same manager_id)
    - manager: direct reports (and self)
    - admin: all teams (optionally filtered by manager_id)
    """
    query = (
        db.query(LeaveRequest)
        .join(User, LeaveRequest.user_id == User.id)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.status.in_(["approved", "pending"]))
    )

    if current_user.role == "employee":
        query = query.filter(User.manager_id == current_user.manager_id)
    elif current_user.role == "manager":
        query = query.filter((User.manager_id == current_user.id) | (User.id == current_user.id))
    elif current_user.role == "admin":
        if manager_id is not None:
            query = query.filter(User.manager_id == manager_id)

    if start_date is not None:
        query = query.filter(LeaveRequest.end_date >= start_date)
    if end_date is not None:
        query = query.filter(LeaveRequest.start_date <= end_date)

    requests = query.order_by(LeaveRequest.start_date.asc()).all()

    holiday_query = db.query(PublicHoliday)
    if start_date is not None:
        holiday_query = holiday_query.filter(PublicHoliday.date >= start_date)
    if end_date is not None:
        holiday_query = holiday_query.filter(PublicHoliday.date <= end_date)
    holidays = holiday_query.order_by(PublicHoliday.date.asc()).all()

    max_off = rules.get_int_setting(db, "max_off_per_day")

    events = [
        CalendarEventOut(
            id=req.id,
            user_id=req.user_id,
            user_name=req.user.name,
            manager_id=req.user.manager_id,
            leave_type_name=req.leave_type.name,
            start_date=req.start_date,
            end_date=req.end_date,
            days_count=req.days_count,
            status=req.status,
        )
        for req in requests
    ]

    return TeamCalendarOut(
        events=events,
        holidays=[HolidayOut.model_validate(h) for h in holidays],
        max_off_per_day=max_off,
    )