from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import LeaveType, PublicHoliday, Setting, User

SEEDED_HOLIDAY = date(2026, 12, 25)


def next_full_workweek(min_days_ahead: int = 10) -> tuple[date, date]:
    """
    Return a (Monday, Friday) pair at least `min_days_ahead` in the future
    that does not cross a calendar year boundary or include the seeded holiday,
    keeping tests date-independent.
    """
    candidate = date.today() + timedelta(days=min_days_ahead)
    while candidate.weekday() != 0:
        candidate += timedelta(days=1)

    while True:
        friday = candidate + timedelta(days=4)
        contains_holiday = candidate <= SEEDED_HOLIDAY <= friday
        crosses_year = candidate.year != friday.year
        if not contains_holiday and not crosses_year:
            return candidate, friday
        candidate += timedelta(days=7)


@pytest.fixture()
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def seeded_db(db_session):
    """Populate the in-memory DB with users, leave types, settings, and a sample holiday."""
    pw_hash = hash_password("password123")

    admin = User(name="Admin", email="admin@test.com", password_hash=pw_hash, role="admin")
    mgr1 = User(name="Manager 1", email="mgr1@test.com", password_hash=pw_hash, role="manager")
    mgr2 = User(name="Manager 2", email="mgr2@test.com", password_hash=pw_hash, role="manager")
    db_session.add_all([admin, mgr1, mgr2])
    db_session.flush()

    emp1 = User(name="Emp 1", email="emp1@test.com", password_hash=pw_hash, role="employee", manager_id=mgr1.id)
    emp2 = User(name="Emp 2", email="emp2@test.com", password_hash=pw_hash, role="employee", manager_id=mgr1.id)
    emp3 = User(name="Emp 3", email="emp3@test.com", password_hash=pw_hash, role="employee", manager_id=mgr1.id)
    emp4 = User(name="Emp 4", email="emp4@test.com", password_hash=pw_hash, role="employee", manager_id=mgr2.id)
    db_session.add_all([emp1, emp2, emp3, emp4])

    annual = LeaveType(name="Annual", yearly_allowance=20)
    sick = LeaveType(name="Sick", yearly_allowance=10)
    unpaid = LeaveType(name="Unpaid", yearly_allowance=30)
    db_session.add_all([annual, sick, unpaid])

    db_session.add_all([
        Setting(key="min_notice_days", value="2"),
        Setting(key="max_off_per_day", value="2"),
    ])
    db_session.add(PublicHoliday(date=SEEDED_HOLIDAY, name="Christmas Day"))

    db_session.commit()

    return {
        "db": db_session,
        "admin": admin,
        "mgr1": mgr1,
        "mgr2": mgr2,
        "emp1": emp1,
        "emp2": emp2,
        "emp3": emp3,
        "emp4": emp4,
        "annual": annual,
        "sick": sick,
        "unpaid": unpaid,
    }


@pytest.fixture()
def client(seeded_db):
    """FastAPI TestClient wired to the test in-memory database."""
    db = seeded_db["db"]

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    """Generate Authorization headers for a test user."""
    token = create_access_token(user_id=user.id, role=user.role)
    return {"Authorization": f"Bearer {token}"}