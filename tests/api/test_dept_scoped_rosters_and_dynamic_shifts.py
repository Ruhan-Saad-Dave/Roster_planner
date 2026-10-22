"""Integration & Regression Tests for Department-Scoped Rosters & Dynamic Shift Definitions.

Tests:
1. Dynamic shift types CRUD & validation (start/end times, durations, rest hours).
2. Department-scoped CP-SAT roster generation (scoping to 1 or more departments).
3. Roster plans listing & scope_label formatting.
4. Schedule retrieval with department scope filtering.
5. Plan duplication carrying over department scope.
6. Safe shift type deletion (active assignment protection / soft-deactivation).
"""
import pytest
from src.db.models import ShiftType, Department, RosterPlan, RosterAssignment


def test_no_d1_commit_artifact_in_shift_types(client):
    """Verify that legacy stray artifact 'D1_COMMIT' is not present in active or inactive shift types."""
    res = client.get("/api/shift-types?active_only=false")
    assert res.status_code == 200
    shifts = res.json()
    codes = [s["code"].upper() for s in shifts]
    assert "D1_COMMIT" not in codes
    assert "D1" not in codes


def test_dynamic_shift_types_crud(client):
    """Verify creating, updating, and deactivating a dynamic shift type with operating hours."""
    # 1. Create a custom twilight shift
    payload = {
        "code": "TWILIGHT_TEST",
        "name": "Twilight Shift",
        "start_time": "16:00:00",
        "end_time": "00:30:00",
        "duration_hours": 8.5,
        "min_rest_hours_after": 14,
        "is_night_shift": True
    }
    res = client.post("/api/shift-types", json=payload)
    assert res.status_code in [200, 201], res.text
    created = res.json()
    shift_id = created["id"]
    assert created["code"] == "TWILIGHT_TEST"
    assert created["duration_hours"] == 8.5
    assert created["is_night_shift"] is True

    # 2. Update operating hours
    update_payload = {
        "name": "Evening Twilight Extended",
        "start_time": "15:00:00",
        "end_time": "00:00:00",
        "duration_hours": 9.0
    }
    res_up = client.put(f"/api/shift-types/{shift_id}", json=update_payload)
    assert res_up.status_code == 200
    updated = res_up.json()
    assert updated["name"] == "Evening Twilight Extended"
    assert updated["duration_hours"] == 9.0

    # 3. Safe delete / deactivate (no assignments exist)
    res_del = client.delete(f"/api/shift-types/{shift_id}")
    assert res_del.status_code == 200
    assert "deleted" in res_del.json()["message"].lower() or "deactivated" in res_del.json()["message"].lower()


def test_department_scoped_roster_generation_and_hub_metadata(client, sample_scenario):
    """Verify generating a roster scoped to a single department, checking scope_label and filtering."""
    # Fetch existing departments from sample scenario
    res_depts = client.get("/api/departments")
    assert res_depts.status_code == 200
    depts = res_depts.json()
    assert len(depts) >= 1
    target_dept = depts[0]
    target_dept_id = target_dept["id"]

    # 1. Generate roster scoped strictly to target_dept_id
    gen_payload = {
        "name": f"Scoped Test Roster ({target_dept['code']})",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 10,
        "department_ids": [target_dept_id]
    }
    res_gen = client.post("/api/roster/generate", json=gen_payload)
    assert res_gen.status_code == 200, res_gen.text
    gen_result = res_gen.json()
    plan_id = gen_result["plan_id"]

    # 2. Verify plans listing returns department_ids and scope_label
    res_plans = client.get("/api/roster/plans")
    assert res_plans.status_code == 200
    plans = res_plans.json()
    matching_plan = next((p for p in plans if p["id"] == plan_id), None)
    assert matching_plan is not None
    assert matching_plan["department_ids"] == [target_dept_id]
    assert target_dept["name"] in matching_plan["scope_label"] or target_dept["code"] in matching_plan["scope_label"]

    # 3. Verify get_plan_schedule returns department scope metadata
    res_sched = client.get(f"/api/roster/{plan_id}")
    assert res_sched.status_code == 200
    sched = res_sched.json()
    assert sched["department_ids"] == [target_dept_id]
    assert sched["scope_label"] is not None

    # Verify all employees in the schedule belong to the scoped department
    for emp_row in sched.get("schedule", []):
        for assign in emp_row.get("assignments", []):
            if assign.get("department_id"):
                assert assign["department_id"] == target_dept_id

    # 4. Verify duplicate plan carries over department_ids
    res_dup = client.post(f"/api/roster/{plan_id}/duplicate", json={})
    assert res_dup.status_code == 200
    dup_plan = res_dup.json()
    dup_sched = client.get(f"/api/roster/{dup_plan['id']}").json()
    assert dup_sched["department_ids"] == [target_dept_id]

    # 5. Cleanup test plans
    client.delete(f"/api/roster/{dup_plan['id']}")
    client.delete(f"/api/roster/{plan_id}")
