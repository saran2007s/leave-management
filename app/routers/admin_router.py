from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import LeaveType, PublicHoliday, Setting, User
from app.schemas import (
    HolidayCreate,
    HolidayOut,
    LeaveTypeOut,
    LeaveTypeUpdate,
    SettingOut,
    SettingsUpdate,
)

# Every route in this router requires the 'admin' role
router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/leave-types", response_model=list[LeaveTypeOut])
def admin_list_leave_types(db: Session = Depends(get_db)):
    return db.query(LeaveType).order_by(LeaveType.id).all()


@router.put("/leave-types/{leave_type_id}", response_model=LeaveTypeOut)
def admin_update_leave_type(
    leave_type_id: int,
    payload: LeaveTypeUpdate,
    db: Session = Depends(get_db),
):
    leave_type = db.query(LeaveType).filter(LeaveType.id == leave_type_id).first()
    if leave_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave type not found.",
        )

    leave_type.yearly_allowance = payload.yearly_allowance
    db.commit()
    db.refresh(leave_type)
    return leave_type


@router.get("/settings", response_model=list[SettingOut])
def admin_list_settings(db: Session = Depends(get_db)):
    return db.query(Setting).order_by(Setting.key).all()


@router.put("/settings", response_model=list[SettingOut])
def admin_update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
):
    updates: dict[str, int] = {}
    if payload.min_notice_days is not None:
        updates["min_notice_days"] = payload.min_notice_days
    if payload.max_off_per_day is not None:
        updates["max_off_per_day"] = payload.max_off_per_day

    for key, val in updates.items():
        setting = db.query(Setting).filter(Setting.key == key).first()
        if setting is None:
            db.add(Setting(key=key, value=str(val)))
        else:
            setting.value = str(val)

    db.commit()
    return db.query(Setting).order_by(Setting.key).all()


@router.get("/holidays", response_model=list[HolidayOut])
def admin_list_holidays(db: Session = Depends(get_db)):
    return db.query(PublicHoliday).order_by(PublicHoliday.date).all()


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def admin_add_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(PublicHoliday).filter(PublicHoliday.date == payload.date).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A public holiday already exists on {payload.date.isoformat()}.",
        )

    holiday = PublicHoliday(date=payload.date, name=payload.name.strip())
    db.add(holiday)
    db.commit()
    db.refresh(holiday)
    return holiday


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
):
    holiday = db.query(PublicHoliday).filter(PublicHoliday.id == holiday_id).first()
    if holiday is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public holiday not found.",
        )

    db.delete(holiday)
    db.commit()