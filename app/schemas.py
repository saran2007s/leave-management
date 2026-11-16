from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    manager_id: int | None

    model_config = ConfigDict(from_attributes=True)


class LeaveTypeOut(BaseModel):
    id: int
    name: str
    yearly_allowance: int

    model_config = ConfigDict(from_attributes=True)


class LeaveTypeUpdate(BaseModel):
    yearly_allowance: int = Field(ge=0)


class SettingOut(BaseModel):
    key: str
    value: str

    model_config = ConfigDict(from_attributes=True)


class SettingsUpdate(BaseModel):
    min_notice_days: int | None = Field(default=None, ge=0)
    max_off_per_day: int | None = Field(default=None, ge=1)


class HolidayCreate(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=100)


class HolidayOut(BaseModel):
    id: int
    date: date
    name: str

    model_config = ConfigDict(from_attributes=True)


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str = ""


class LeaveRequestOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    leave_type_id: int
    leave_type_name: str
    start_date: date
    end_date: date
    days_count: int
    reason: str
    status: str
    created_at: datetime
    decided_by: int | None
    decided_at: datetime | None


class BalanceOut(BaseModel):
    leave_type_id: int
    leave_type_name: str
    year: int
    yearly_allowance: int
    approved_days: int
    pending_days: int
    remaining_days: int


class WorkingDaysPreviewOut(BaseModel):
    start_date: date
    end_date: date
    working_days: int


class CalendarEventOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    manager_id: int | None
    leave_type_name: str
    start_date: date
    end_date: date
    days_count: int
    status: str


class TeamCalendarOut(BaseModel):
    events: list[CalendarEventOut]
    holidays: list[HolidayOut]
    max_off_per_day: int