import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Role is one of: 'employee', 'manager', 'admin'
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Employees point to their manager; managers and admins have manager_id = None
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    manager: Mapped["User | None"] = relationship("User", remote_side=[id], backref="reports")


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    yearly_allowance: Mapped[int] = mapped_column(Integer, nullable=False)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # Number of working days calculated and stored when the request is created
    days_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Status is one of: 'pending', 'approved', 'rejected', 'cancelled'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: dt.datetime.now(dt.timezone.utc),
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    leave_type: Mapped["LeaveType"] = relationship("LeaveType")
    decider: Mapped["User | None"] = relationship("User", foreign_keys=[decided_by])


class PublicHoliday(Base):
    __tablename__ = "public_holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[dt.date] = mapped_column(Date, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    # Keys: 'min_notice_days', 'max_off_per_day'
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)