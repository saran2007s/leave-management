from datetime import date, timedelta

from tests.conftest import auth_headers, next_full_workweek


def test_changing_allowance_changes_behavior_immediately(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    # Lower Annual allowance from 20 to 3
    assert client.put(
        f"/api/admin/leave-types/{annual.id}",
        headers=auth_headers(admin),
        json={"yearly_allowance": 3},
    ).status_code == 200

    # 5-day request must fail immediately
    resp_fail = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    assert resp_fail.status_code == 400

    # Raise Annual allowance to 5 -> same 5-day request succeeds immediately
    assert client.put(
        f"/api/admin/leave-types/{annual.id}",
        headers=auth_headers(admin),
        json={"yearly_allowance": 5},
    ).status_code == 200

    resp_ok = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    assert resp_ok.status_code == 201


def test_changing_min_notice_changes_behavior_immediately(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    mon, _ = next_full_workweek(min_days_ahead=5)
    days_until_mon = (mon - date.today()).days

    # Set min_notice_days higher than `days_until_mon`
    assert client.put(
        "/api/admin/settings",
        headers=auth_headers(admin),
        json={"min_notice_days": days_until_mon + 3},
    ).status_code == 200

    resp_fail = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": mon.isoformat()},
    )
    assert resp_fail.status_code == 400
    assert "advance notice" in resp_fail.json()["detail"].lower()


def test_changing_max_off_per_day_changes_behavior_immediately(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    emp2 = seeded_db["emp2"]
    annual = seeded_db["annual"]
    mon, _ = next_full_workweek()

    # Lower team cap from 2 to 1
    assert client.put(
        "/api/admin/settings",
        headers=auth_headers(admin),
        json={"max_off_per_day": 1},
    ).status_code == 200

    assert client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": mon.isoformat()},
    ).status_code == 201

    resp_emp2 = client.post(
        "/api/leaves",
        headers=auth_headers(emp2),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": mon.isoformat()},
    )
    assert resp_emp2.status_code == 400
    assert mon.isoformat() in resp_emp2.json()["detail"]


def test_adding_and_deleting_holiday_changes_working_days_immediately(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()
    wed = mon + timedelta(days=2)

    # Add Wednesday as a public holiday
    add_resp = client.post(
        "/api/admin/holidays",
        headers=auth_headers(admin),
        json={"date": wed.isoformat(), "name": "Midweek Festival"},
    )
    assert add_resp.status_code == 201
    holiday_id = add_resp.json()["id"]

    # Mon..Fri should now count 4 working days instead of 5
    preview = client.get(
        f"/api/leaves/preview-days?start_date={mon.isoformat()}&end_date={fri.isoformat()}",
        headers=auth_headers(emp1),
    )
    assert preview.status_code == 200
    assert preview.json()["working_days"] == 4

    # Delete the holiday -> preview immediately returns 5 again
    assert client.delete(f"/api/admin/holidays/{holiday_id}", headers=auth_headers(admin)).status_code == 204
    preview_after = client.get(
        f"/api/leaves/preview-days?start_date={mon.isoformat()}&end_date={fri.isoformat()}",
        headers=auth_headers(emp1),
    )
    assert preview_after.json()["working_days"] == 5