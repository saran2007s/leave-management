from tests.conftest import auth_headers, next_full_workweek


def test_unauthenticated_access_returns_401(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/leaves/my").status_code == 401
    assert client.get("/api/admin/settings").status_code == 401


def test_employee_and_admin_cannot_approve_or_reject(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    emp2 = seeded_db["emp2"]
    mgr2 = seeded_db["mgr2"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    create_resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    req_id = create_resp.json()["id"]

    # Employee cannot approve or view team approvals queue
    assert client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(emp2)).status_code == 403
    assert client.post(f"/api/leaves/{req_id}/reject", headers=auth_headers(emp1)).status_code == 403
    assert client.get("/api/leaves/team", headers=auth_headers(emp1)).status_code == 403

    # Admin does not approve/reject requests
    assert client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(admin)).status_code == 403
    assert client.post(f"/api/leaves/{req_id}/reject", headers=auth_headers(admin)).status_code == 403

    # Manager 2 cannot approve/reject Manager 1's report
    assert client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(mgr2)).status_code == 403
    assert client.post(f"/api/leaves/{req_id}/reject", headers=auth_headers(mgr2)).status_code == 403


def test_employee_cannot_cancel_another_employees_request(client, seeded_db):
    emp1 = seeded_db["emp1"]
    emp2 = seeded_db["emp2"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    create_resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    req_id = create_resp.json()["id"]

    assert client.post(f"/api/leaves/{req_id}/cancel", headers=auth_headers(emp2)).status_code == 403


def test_non_admins_cannot_access_admin_endpoints(client, seeded_db):
    emp1 = seeded_db["emp1"]
    mgr1 = seeded_db["mgr1"]

    for user in (emp1, mgr1):
        headers = auth_headers(user)
        assert client.get("/api/admin/settings", headers=headers).status_code == 403
        assert client.put("/api/admin/settings", headers=headers, json={"min_notice_days": 5}).status_code == 403
        assert client.get("/api/admin/leave-types", headers=headers).status_code == 403


def test_calendar_scoping_by_role(client, seeded_db):
    admin = seeded_db["admin"]
    mgr1 = seeded_db["mgr1"]
    emp1 = seeded_db["emp1"]  # team 1
    emp4 = seeded_db["emp4"]  # team 2
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    # Create one request in Team 1 and one in Team 2
    assert client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": mon.isoformat()},
    ).status_code == 201
    assert client.post(
        "/api/leaves",
        headers=auth_headers(emp4),
        json={"leave_type_id": annual.id, "start_date": fri.isoformat(), "end_date": fri.isoformat()},
    ).status_code == 201

    # emp1 & mgr1 only see Team 1 events
    emp1_events = client.get("/api/team/calendar", headers=auth_headers(emp1)).json()["events"]
    assert {e["user_id"] for e in emp1_events} == {emp1.id}

    mgr1_events = client.get("/api/team/calendar", headers=auth_headers(mgr1)).json()["events"]
    assert {e["user_id"] for e in mgr1_events} == {emp1.id}

    # admin sees all teams
    admin_events = client.get("/api/team/calendar", headers=auth_headers(admin)).json()["events"]
    assert {e["user_id"] for e in admin_events} == {emp1.id, emp4.id}