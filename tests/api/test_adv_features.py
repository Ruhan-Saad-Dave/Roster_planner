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
