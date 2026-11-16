from datetime import date, timedelta

from app.models import LeaveRequest
from tests.conftest import auth_headers, next_full_workweek


def test_rejects_end_before_start(client, seeded_db):
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    mon, _ = next_full_workweek()

    resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": (mon + timedelta(days=3)).isoformat(),
            "end_date": mon.isoformat(),
            "reason": "Backwards dates",
        },
    )
    assert resp.status_code == 400
    assert "before start date" in resp.json()["detail"].lower()


def test_rejects_cross_year_request(client, seeded_db):
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    next_year = date.today().year + 1

    resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": f"{next_year}-12-30",
            "end_date": f"{next_year + 1}-01-04",
            "reason": "Cross year",
        },
    )
    assert resp.status_code == 400
    assert "same calendar year" in resp.json()["detail"].lower()


def test_rejects_zero_working_days(client, seeded_db):
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    mon, _ = next_full_workweek()
    sat = mon + timedelta(days=5)
    sun = mon + timedelta(days=6)

    resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": sat.isoformat(),
            "end_date": sun.isoformat(),
            "reason": "Weekend only",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Request contains no working days."


def test_min_notice_enforced_for_annual_but_exempt_for_sick(client, seeded_db):
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    sick = seeded_db["sick"]

    tomorrow = date.today() + timedelta(days=1)
    if tomorrow.weekday() >= 5:
        target = date.today()
        while target.weekday() >= 5:
            target -= timedelta(days=1)
    else:
        target = tomorrow

    # Annual with < 2 days notice -> rejected
    resp_annual = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": target.isoformat(),
            "end_date": target.isoformat(),
            "reason": "Short notice annual",
        },
    )
    assert resp_annual.status_code == 400
    assert "advance notice" in resp_annual.json()["detail"].lower()

    # Sick with < 2 days notice -> allowed
    resp_sick = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": sick.id,
            "start_date": target.isoformat(),
            "end_date": target.isoformat(),
            "reason": "Sudden fever",
        },
    )
    assert resp_sick.status_code == 201


def test_balance_counts_approved_plus_pending(client, seeded_db):
    db = seeded_db["db"]
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]

    # Use March of next year: guaranteed future, same year, and free of seeded holidays
    year = date.today().year + 1
    mon = date(year, 3, 1)
    while mon.weekday() != 0:
        mon += timedelta(days=1)
    fri = mon + timedelta(days=4)
    next_mon = mon + timedelta(days=7)

    # Seed 10 approved + 5 pending = 15 used out of 20 -> 5 remaining
    db.add(
        LeaveRequest(
            user_id=emp1.id,
            leave_type_id=annual.id,
            start_date=date(year, 1, 5),
            end_date=date(year, 1, 16),
            days_count=10,
            reason="Past approved",
            status="approved",
        )
    )
    db.add(
        LeaveRequest(
            user_id=emp1.id,
            leave_type_id=annual.id,
            start_date=date(year, 2, 2),
            end_date=date(year, 2, 6),
            days_count=5,
            reason="Existing pending",
            status="pending",
        )
    )
    db.commit()

    # Requesting 6 working days (Mon..next Mon = 6) -> rejected (remaining 5)
    resp_6 = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": mon.isoformat(),
            "end_date": next_mon.isoformat(),
            "reason": "Too many days",
        },
    )
    assert resp_6.status_code == 400
    assert "balance" in resp_6.json()["detail"].lower()

    # Requesting 5 working days (Mon..Fri = 5) -> allowed
    resp_5 = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": mon.isoformat(),
            "end_date": fri.isoformat(),
            "reason": "Exact remaining",
        },
    )
    assert resp_5.status_code == 201
    assert resp_5.json()["days_count"] == 5


def test_same_employee_overlap_ignores_cancelled_and_rejected(client, seeded_db):
    db = seeded_db["db"]
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    sick = seeded_db["sick"]
    mon, fri = next_full_workweek()

    # Cancelled & rejected on the same week must NOT block new requests
    db.add_all([
        LeaveRequest(
            user_id=emp1.id,
            leave_type_id=annual.id,
            start_date=mon,
            end_date=fri,
            days_count=5,
            reason="Cancelled one",
            status="cancelled",
        ),
        LeaveRequest(
            user_id=emp1.id,
            leave_type_id=annual.id,
            start_date=mon,
            end_date=fri,
            days_count=5,
            reason="Rejected one",
            status="rejected",
        ),
    ])
    db.commit()

    # First active request succeeds
    resp_ok = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": mon.isoformat(),
            "end_date": (mon + timedelta(days=2)).isoformat(),
            "reason": "First request",
        },
    )
    assert resp_ok.status_code == 201

    # Overlapping request (even of a different leave type) must fail
    resp_overlap = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": sick.id,
            "start_date": (mon + timedelta(days=1)).isoformat(),
            "end_date": fri.isoformat(),
            "reason": "Overlapping sick",
        },
    )
    assert resp_overlap.status_code == 400
    assert "overlap" in resp_overlap.json()["detail"].lower()


def test_team_cap_blocks_third_teammate_but_allows_other_team(client, seeded_db):
    emp1 = seeded_db["emp1"]  # manager1
    emp2 = seeded_db["emp2"]  # manager1
    emp3 = seeded_db["emp3"]  # manager1
    emp4 = seeded_db["emp4"]  # manager2
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()
    wed = mon + timedelta(days=2)

    # max_off_per_day = 2: emp1 & emp2 take Wed off
    assert client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": wed.isoformat()},
    ).status_code == 201

    assert client.post(
        "/api/leaves",
        headers=auth_headers(emp2),
        json={"leave_type_id": annual.id, "start_date": wed.isoformat(), "end_date": fri.isoformat()},
    ).status_code == 201

    # emp3 (same team) overlapping Wed -> rejected naming Wed
    resp_emp3 = client.post(
        "/api/leaves",
        headers=auth_headers(emp3),
        json={"leave_type_id": annual.id, "start_date": wed.isoformat(), "end_date": fri.isoformat()},
    )
    assert resp_emp3.status_code == 400
    assert wed.isoformat() in resp_emp3.json()["detail"]

    # emp4 (different manager/team) overlapping Wed -> allowed
    resp_emp4 = client.post(
        "/api/leaves",
        headers=auth_headers(emp4),
        json={"leave_type_id": annual.id, "start_date": wed.isoformat(), "end_date": fri.isoformat()},
    )
    assert resp_emp4.status_code == 201