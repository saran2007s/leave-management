from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import LeaveRequest, LeaveType, PublicHoliday, User
from app.schemas import (
    BalanceOut,
    HolidayOut,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveTypeOut,
    WorkingDaysPreviewOut,
)
from app.services import leave_service, rules
from app.services.working_days import count_working_days

router = APIRouter(prefix="/api/leaves", tags=["leaves"])


def serialize_leave_request(req: LeaveRequest) -> LeaveRequestOut:
    """Convert a LeaveRequest ORM object into a flat JSON-friendly response schema."""
    return LeaveRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=req.user.name if req.user else "",
        leave_type_id=req.leave_type_id,
        leave_type_name=req.leave_type.name if req.leave_type else "",
        start_date=req.start_date,
        end_date=req.end_date,
        days_count=req.days_count,
        reason=req.reason,
        status=req.status,
        created_at=req.created_at,
        decided_by=req.decided_by,
        decided_at=req.decided_at,
    )


@router.get("/types", response_model=list[LeaveTypeOut])
def list_leave_types(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all configured leave types and their yearly allowances."""
    return db.query(LeaveType).order_by(LeaveType.id).all()


@router.get("/holidays", response_model=list[HolidayOut])
def list_public_holidays(
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all public holidays (readable by any authenticated user)."""
    return db.query(PublicHoliday).order_by(PublicHoliday.date).all()


@router.get("/preview-days", response_model=WorkingDaysPreviewOut)
def preview_working_days(
    start_date: date,
    end_date: date,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview how many working days a date range covers after excluding weekends and holidays."""
    holidays = rules.get_holiday_dates(db)
    working_days = count_working_days(start_date, end_date, holidays)
    return WorkingDaysPreviewOut(
        start_date=start_date,
        end_date=end_date,
        working_days=working_days,
    )


@router.get("/balances", response_model=list[BalanceOut])
def get_my_balances(
    year: int = Query(default_factory=lambda: date.today().year),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute remaining leave balance per leave type for the current user and year."""
    leave_types = db.query(LeaveType).order_by(LeaveType.id).all()
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    active_requests = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == current_user.id,
            LeaveRequest.status.in_(["approved", "pending"]),
            LeaveRequest.start_date >= year_start,
            LeaveRequest.end_date <= year_end,
        )
        .all()
    )

    balances: list[BalanceOut] = []
    for lt in leave_types:
        approved_days = sum(
            r.days_count for r in active_requests if r.leave_type_id == lt.id and r.status == "approved"
        )
        pending_days = sum(
            r.days_count for r in active_requests if r.leave_type_id == lt.id and r.status == "pending"
        )
        remaining_days = lt.yearly_allowance - (approved_days + pending_days)
        balances.append(
            BalanceOut(
                leave_type_id=lt.id,
                leave_type_name=lt.name,
                year=year,
                yearly_allowance=lt.yearly_allowance,
                approved_days=approved_days,
                pending_days=pending_days,
                remaining_days=remaining_days,
            )
        )
    return balances


@router.get("/my", response_model=list[LeaveRequestOut])
def get_my_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the logged-in user's own leave requests."""
    query = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.user_id == current_user.id)
    )
    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter)

    requests = query.order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc()).all()
    return [serialize_leave_request(r) for r in requests]


@router.post("", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: LeaveRequestCreate,
    current_user: User = Depends(require_role("employee", "manager")),
    db: Session = Depends(get_db),
):
    """Submit a new leave request (validated against all business rules)."""
    req = leave_service.create_leave_request(
        db=db,
        user=current_user,
        leave_type_id=payload.leave_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )
    # Reload with relationships for serialization
    loaded = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.id == req.id)
        .one()
    )
    return serialize_leave_request(loaded)


@router.post("/{request_id}/cancel", response_model=LeaveRequestOut)
def cancel_request(
    request_id: int,
    current_user: User = Depends(require_role("employee", "manager")),
    db: Session = Depends(get_db),
):
    """Cancel the current user's own pending or future approved request."""
    req = leave_service.cancel_leave_request(db=db, current_user=current_user, request_id=request_id)
    loaded = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.id == req.id)
        .one()
    )
    return serialize_leave_request(loaded)


@router.get("/team", response_model=list[LeaveRequestOut])
def get_team_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """List leave requests submitted by the manager's direct reports."""
    query = (
        db.query(LeaveRequest)
        .join(User, LeaveRequest.user_id == User.id)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(User.manager_id == current_user.id)
    )
    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter)

    requests = query.order_by(LeaveRequest.start_date.asc(), LeaveRequest.id.asc()).all()
    return [serialize_leave_request(r) for r in requests]


@router.post("/{request_id}/approve", response_model=LeaveRequestOut)
def approve_request(
    request_id: int,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """Approve a pending request belonging to one of the manager's direct reports."""
    req = leave_service.approve_leave_request(db=db, manager=current_user, request_id=request_id)
    loaded = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.id == req.id)
        .one()
    )
    return serialize_leave_request(loaded)


@router.post("/{request_id}/reject", response_model=LeaveRequestOut)
def reject_request(
    request_id: int,
    current_user: User = Depends(require_role("manager")),
    db: Session = Depends(get_db),
):
    """Reject a pending request belonging to one of the manager's direct reports."""
    req = leave_service.reject_leave_request(db=db, manager=current_user, request_id=request_id)
    loaded = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.user), joinedload(LeaveRequest.leave_type))
        .filter(LeaveRequest.id == req.id)
        .one()
    )
    return serialize_leave_request(loaded)