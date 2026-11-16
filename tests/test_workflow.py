from datetime import date, timedelta

from app.models import LeaveRequest
from tests.conftest import auth_headers, next_full_workweek


def test_create_approve_reject_and_cancel_restores_balance(client, seeded_db):
    emp1 = seeded_db["emp1"]
    mgr1 = seeded_db["mgr1"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    # 1. Create -> pending
    create_resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={
            "leave_type_id": annual.id,
            "start_date": mon.isoformat(),
            "end_date": fri.isoformat(),
            "reason": "Vacation",
        },
    )
    assert create_resp.status_code == 201
    req_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "pending"
    assert create_resp.json()["days_count"] == 5

    # Check balance dropped from 20 to 15 (pending = 5)
    bal_resp = client.get(f"/api/leaves/balances?year={mon.year}", headers=auth_headers(emp1))
    annual_bal = next(b for b in bal_resp.json() if b["leave_type_name"] == "Annual")
    assert annual_bal["remaining_days"] == 15
    assert annual_bal["pending_days"] == 5

    # 2. Manager approves -> approved
    app_resp = client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(mgr1))
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"
    assert app_resp.json()["decided_by"] == mgr1.id

    # 3. Cannot approve or reject an already approved request -> 400
    assert client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(mgr1)).status_code == 400
    assert client.post(f"/api/leaves/{req_id}/reject", headers=auth_headers(mgr1)).status_code == 400

    # 4. Employee cancels future approved request -> cancelled, balance restored to 20
    cancel_resp = client.post(f"/api/leaves/{req_id}/cancel", headers=auth_headers(emp1))
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    bal_after = client.get(f"/api/leaves/balances?year={mon.year}", headers=auth_headers(emp1))
    annual_after = next(b for b in bal_after.json() if b["leave_type_name"] == "Annual")
    assert annual_after["remaining_days"] == 20

    # 5. Cannot cancel an already cancelled request -> 400
    assert client.post(f"/api/leaves/{req_id}/cancel", headers=auth_headers(emp1)).status_code == 400


def test_cannot_cancel_approved_request_on_or_after_start_date(client, seeded_db):
    db = seeded_db["db"]
    emp1 = seeded_db["emp1"]
    mgr1 = seeded_db["mgr1"]
    annual = seeded_db["annual"]

    past_req = LeaveRequest(
        user_id=emp1.id,
        leave_type_id=annual.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        days_count=1,
        reason="Already started",
        status="approved",
        decided_by=mgr1.id,
    )
    db.add(past_req)
    db.commit()

    resp = client.post(f"/api/leaves/{past_req.id}/cancel", headers=auth_headers(emp1))
    assert resp.status_code == 400
    assert "start date" in resp.json()["detail"].lower()


def test_reject_workflow_and_invalid_transitions(client, seeded_db):
    emp1 = seeded_db["emp1"]
    mgr1 = seeded_db["mgr1"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    create_resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    req_id = create_resp.json()["id"]

    rej_resp = client.post(f"/api/leaves/{req_id}/reject", headers=auth_headers(mgr1))
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] == "rejected"

    # Cannot approve or cancel a rejected request
    assert client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(mgr1)).status_code == 400
    assert client.post(f"/api/leaves/{req_id}/cancel", headers=auth_headers(emp1)).status_code == 400


def test_approval_rechecks_balance_when_allowance_reduced(client, seeded_db):
    admin = seeded_db["admin"]
    emp1 = seeded_db["emp1"]
    mgr1 = seeded_db["mgr1"]
    annual = seeded_db["annual"]
    mon, fri = next_full_workweek()

    # Employee creates a 5-day pending request while allowance is 20
    create_resp = client.post(
        "/api/leaves",
        headers=auth_headers(emp1),
        json={"leave_type_id": annual.id, "start_date": mon.isoformat(), "end_date": fri.isoformat()},
    )
    assert create_resp.status_code == 201
    req_id = create_resp.json()["id"]

    # Admin reduces Annual allowance to 3
    upd_resp = client.put(
        f"/api/admin/leave-types/{annual.id}",
        headers=auth_headers(admin),
        json={"yearly_allowance": 3},
    )
    assert upd_resp.status_code == 200

    # Manager tries to approve -> re-check catches insufficient balance (400)
    app_resp = client.post(f"/api/leaves/{req_id}/approve", headers=auth_headers(mgr1))
    assert app_resp.status_code == 400
    assert "balance" in app_resp.json()["detail"].lower()