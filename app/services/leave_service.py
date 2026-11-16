from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import LeaveRequest, LeaveType, User
from app.services import rules


def create_leave_request(
    db: Session,
    user: User,
    leave_type_id: int,
    start_date: date,
    end_date: date,
    reason: str = "",
    today: date | None = None,
) -> LeaveRequest:
    """Validate all leave rules and create a pending leave request in one DB transaction."""
    try:
        leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
        if leave_type is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave type not found.",
            )

        holidays = rules.get_holiday_dates(db)
        days_count = rules.validate_dates_and_count_days(start_date, end_date, holidays)

        rules.check_min_notice(db, leave_type, start_date, today=today)
        rules.check_balance(db, user.id, leave_type, start_date.year, days_count)
        rules.check_employee_overlap(db, user.id, start_date, end_date)
        rules.check_team_cap(db, user, start_date, end_date, holidays)

        leave_request = LeaveRequest(
            user_id=user.id,
            leave_type_id=leave_type.id,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason.strip(),
            status="pending",
        )
        db.add(leave_request)
        db.commit()
        db.refresh(leave_request)
        return leave_request
    except Exception:
        db.rollback()
        raise


def approve_leave_request(db: Session, manager: User, request_id: int) -> LeaveRequest:
    """Approve a pending request belonging to one of the manager's direct reports."""
    try:
        leave_request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
        if leave_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found.",
            )

        owner = db.query(User).filter(User.id == leave_request.user_id).first()
        if owner is None or owner.manager_id != manager.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only approve requests for your own direct reports.",
            )

        if leave_request.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve a request with status '{leave_request.status}'.",
            )

        # Re-check balance, overlap, and team cap at approval time (excluding the request itself)
        holidays = rules.get_holiday_dates(db)
        leave_type = db.query(LeaveType).filter(LeaveType.id == leave_request.leave_type_id).first()
        if leave_type is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found.")

        rules.check_balance(
            db,
            owner.id,
            leave_type,
            leave_request.start_date.year,
            leave_request.days_count,
            exclude_request_id=leave_request.id,
        )
        rules.check_employee_overlap(
            db,
            owner.id,
            leave_request.start_date,
            leave_request.end_date,
            exclude_request_id=leave_request.id,
        )
        rules.check_team_cap(
            db,
            owner,
            leave_request.start_date,
            leave_request.end_date,
            holidays,
            exclude_request_id=leave_request.id,
        )

        leave_request.status = "approved"
        leave_request.decided_by = manager.id
        leave_request.decided_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(leave_request)
        return leave_request
    except Exception:
        db.rollback()
        raise


def reject_leave_request(db: Session, manager: User, request_id: int) -> LeaveRequest:
    """Reject a pending request belonging to one of the manager's direct reports."""
    try:
        leave_request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
        if leave_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found.",
            )

        owner = db.query(User).filter(User.id == leave_request.user_id).first()
        if owner is None or owner.manager_id != manager.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only reject requests for your own direct reports.",
            )

        if leave_request.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reject a request with status '{leave_request.status}'.",
            )

        leave_request.status = "rejected"
        leave_request.decided_by = manager.id
        leave_request.decided_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(leave_request)
        return leave_request
    except Exception:
        db.rollback()
        raise


def cancel_leave_request(
    db: Session,
    current_user: User,
    request_id: int,
    today: date | None = None,
) -> LeaveRequest:
    """
    Cancel the user's own request if it is 'pending',
    or 'approved' with a start_date strictly in the future.
    """
    try:
        leave_request = db.query(LeaveRequest).filter(LeaveRequest.id == request_id).first()
        if leave_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Leave request not found.",
            )

        if leave_request.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own leave requests.",
            )

        reference_today = today or date.today()
        if leave_request.status == "pending":
            pass
        elif leave_request.status == "approved":
            if leave_request.start_date <= reference_today:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot cancel an approved request on or after its start date.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a request with status '{leave_request.status}'.",
            )

        leave_request.status = "cancelled"
        db.commit()
        db.refresh(leave_request)
        return leave_request
    except Exception:
        db.rollback()
        raise