"""Tests for Advanced Settings, Dedicated Regular Days Off, Find & Replace, and Vacations."""
from datetime import date
from src.db.models import Employee, ShiftType, RosterPlan, RosterAssignment, LeaveRecord, SystemSetting

def test_dedicated_regular_days_off_enforcement(client, test_db, sample_scenario):
    """Verify that employees with dedicated recurring days off are never scheduled on those weekdays."""
    emp = test_db.query(Employee).first()
    assert emp is not None

    # Set employee to have fixed days off on Saturday (5) and Sunday (6)
    update_res = client.put(f"/api/employees/{emp.id}", json={
        "fixed_off_days": "5,6"
    })
    assert update_res.status_code == 200
    assert update_res.json()["fixed_off_days"] == "5,6"

    # Generate a roster for November 2026 (Nov 1 is Sunday, Nov 7 is Saturday, etc.)
    gen_res = client.post("/api/roster/generate", json={
        "name": "Fixed Days Off Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    # Verify that the employee is never scheduled on Saturday (5) or Sunday (6)
    schedule_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    assert schedule_res.status_code == 200
    schedule_data = schedule_res.json()

    emp_row = next(r for r in schedule_data["rows"] if r["employee_id"] == emp.id)
    for d_str, assign in emp_row["assignments"].items():
        d_obj = date.fromisoformat(d_str)
        if d_obj.weekday() in [5, 6]:
            # Either None (empty) or marked is_fixed_off
            if assign is not None:
                assert assign.get("is_fixed_off") is True, f"Employee scheduled on weekend {d_str}!"


def test_vacation_leave_crud_and_grid_representation(client, test_db, sample_scenario):
    """Verify leave creation, deletion, and representation in the staff grid."""
    emp = test_db.query(Employee).first()

    # Create a vacation leave for Nov 18-20, 2026
    leave_res = client.post("/api/leaves", json={
        "employee_id": emp.id,
        "start_date": "2026-11-18",
        "end_date": "2026-11-20",
        "leave_type": "VACATION",
        "notes": "Annual Leave Request"
    })
    assert leave_res.status_code == 201
    leave_id = leave_res.json()["id"]

    # List leaves
    list_res = client.get("/api/leaves")
    assert list_res.status_code == 200
    assert any(l["id"] == leave_id for l in list_res.json())

    # Generate roster
    gen_res = client.post("/api/roster/generate", json={
        "name": "Vacation Test Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # Check grid for vacation marker
    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    for target_date in ["2026-11-18", "2026-11-19", "2026-11-20"]:
        cell = emp_row["assignments"].get(target_date)
        assert cell is not None
        assert cell.get("is_leave") is True
        assert cell.get("shift_code") == "VAC"

    # Delete leave
    del_res = client.delete(f"/api/leaves/{leave_id}")
    assert del_res.status_code == 200


def test_find_and_replace_shift_codes(client, sample_scenario):
    """Verify find and replace replaces shift assignments across active plan."""
    # Generate roster
    gen_res = client.post("/api/roster/generate", json={
        "name": "Find Replace Test Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # Replace NIGHT shifts with MORN
    replace_res = client.post(f"/api/roster/{plan_id}/find-replace", json={
        "find_shift_code": "NIGHT",
        "replace_shift_code": "MORN"
    })
    assert replace_res.status_code == 200
    assert "replaced_count" in replace_res.json()

    # Replace with OFF (clear shifts)
    clear_res = client.post(f"/api/roster/{plan_id}/find-replace", json={
        "find_shift_code": "MORN",
        "replace_shift_code": "OFF"
    })
    assert clear_res.status_code == 200
    assert clear_res.json()["replaced_count"] >= 0


def test_system_settings_and_shift_customization(client, sample_scenario):
    """Verify system settings get/post and shift updates."""
    # 1. Update settings
    post_res = client.post("/api/settings", json={
        "settings": {
            "generator_default_mode": "existing",
            "remember_generator_mode": "true",
            "custom_status_codes": '{"OFF":"DO","COFF":"Coff","VAC":"Holiday"}'
        }
    })
    assert post_res.status_code == 200

    # 2. Get settings
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    settings = get_res.json()
    assert settings["generator_default_mode"] == "existing"
    assert settings["remember_generator_mode"] is True
    assert settings["custom_status_codes"]["OFF"] == "DO"

    # 3. Update shift type
    shifts = client.get("/api/shift-types").json()
    assert len(shifts) > 0
    s_id = shifts[0]["id"]
    put_shift_res = client.put(f"/api/shift-types/{s_id}", json={
        "name": "Updated Day Shift",
        "duration_hours": 9.0
    })
    assert put_shift_res.status_code == 200
    assert put_shift_res.json()["name"] == "Updated Day Shift"
    assert put_shift_res.json()["duration_hours"] == 9.0


def test_flexible_day_off_gets_do_not_coff(client, test_db, sample_scenario):
    """Verify that employees with flexible days off receive DO (Scheduled Day Off), not COFF, under normal 40h/5-shift work."""
    # Ensure employee has flexible days off (None)
    emp = test_db.query(Employee).first()
    client.put(f"/api/employees/{emp.id}", json={"fixed_off_days": None})

    gen_res = client.post("/api/roster/generate", json={
        "name": "Flexible DO Verification Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 6
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    assert sched_res.status_code == 200
    data = sched_res.json()

    all_do = sum(
        sum(1 for a in r["assignments"].values() if a and a.get("shift_code") == "DO")
        for r in data["rows"]
    )
    assert all_do > 0, f"Expected standard DO scheduled days off across flexible workforce, got {all_do}"

    # Verify that no employee exceeds the max_comp_offs limit (default 2)
    for r in data["rows"]:
        emp_coff = sum(1 for a in r["assignments"].values() if a and a.get("shift_code") == "COFF")
        assert emp_coff <= 2, f"Employee {r['employee_name']} exceeded max comp offs limit (got {emp_coff})"


def test_auto_resolve_conflicts_endpoint(client, test_db, sample_scenario):
    """Verify POST /api/roster/{plan_id}/resolve-conflicts identifies and removes conflicting assignments."""
    emp = test_db.query(Employee).first()
    shifts = client.get("/api/shift-types").json()
    morn = next(s for s in shifts if "MORN" in s["code"])
    depts = client.get("/api/departments").json()
    dept = depts[0]

    # Set employee with fixed day off on Friday (4)
    client.put(f"/api/employees/{emp.id}", json={"fixed_off_days": "4"})

    gen_res = client.post("/api/roster/generate", json={
        "name": "Conflict Resolution Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # Manually inject a conflicting assignment on a Friday (Nov 6, 2026 is a Friday)
    client.post(f"/api/roster/{plan_id}/assignments", json={
        "employee_id": emp.id,
        "department_id": dept["id"],
        "shift_type_id": morn["id"],
        "date": "2026-11-06",
        "force_override": True,
        "is_pinned": True
    })

    # Verify conflict appears in schedule
    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    fri_assign = emp_row["assignments"]["2026-11-06"]
    assert fri_assign.get("has_conflict") is True

    # Call Auto-Resolve Conflicts endpoint
    resolve_res = client.post(f"/api/roster/{plan_id}/resolve-conflicts")
    assert resolve_res.status_code == 200
    res_data = resolve_res.json()
    assert res_data["resolved_count"] >= 1

    # Verify conflict has been resolved (assignment removed)
    sched_after = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_after = next(r for r in sched_after.json()["rows"] if r["employee_id"] == emp.id)
    fri_after = emp_after["assignments"]["2026-11-06"]
    assert fri_after is None or fri_after.get("shift_code") == "DO"
    if fri_after:
        assert fri_after.get("has_conflict") is False


def test_dynamic_shift_regime_application(client, test_db, sample_scenario):
    """Verify applying 3_shifts, 2_shifts, and hybrid_weekday3_weekend2 shift regimes."""
    depts = client.get("/api/departments").json()
    dept_id = depts[0]["id"]

    # Apply 2-shift regime (Lean operations: Morning & Night, collapse Evening)
    res_2s = client.post(f"/api/departments/{dept_id}/apply-shift-regime?regime=2_shifts")
    assert res_2s.status_code == 200
    assert res_2s.json()["regime"] == "2_shifts"

    reqs = client.get(f"/api/departments/{dept_id}/requirements").json()
    # Check that evening shifts have 0 min staff
    eve_reqs = [r for r in reqs if "EVE" in r["shift_code"]]
    for r in eve_reqs:
        assert r["min_staff"] == 0, f"Expected 0 min_staff for evening shift in 2-shift regime, got {r['min_staff']}"

    # Apply hybrid regime (3 shifts weekdays, 2 shifts weekends)
    res_hybrid = client.post(f"/api/departments/{dept_id}/apply-shift-regime?regime=hybrid_weekday3_weekend2")
    assert res_hybrid.status_code == 200
    reqs_hybrid = client.get(f"/api/departments/{dept_id}/requirements").json()
    eve_hybrid = [r for r in reqs_hybrid if "EVE" in r["shift_code"]]
    for r in eve_hybrid:
        if r["day_of_week"] in [5, 6]:
            assert r["min_staff"] == 0, "Weekend evening shift should be 0 in hybrid regime"
        else:
            assert r["min_staff"] == 1, "Weekday evening shift should be 1 in hybrid regime"


def test_advanced_comp_off_and_regime_settings(client, sample_scenario):
    """Verify getting and saving max comp offs, continuous comp off, and dynamic shift regime settings."""
    put_res = client.post("/api/settings", json={
        "settings": {
            "max_comp_offs_per_employee": "3",
            "continuous_comp_off_enabled": "true",
            "dynamic_shift_regime": "hybrid_weekday3_weekend2"
        }
    })
    assert put_res.status_code == 200

    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["max_comp_offs_per_employee"] == 3
    assert data["continuous_comp_off_enabled"] is True
    assert data["dynamic_shift_regime"] == "hybrid_weekday3_weekend2"

