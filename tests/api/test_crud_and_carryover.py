"""Integration tests for Department & Employee CRUD, color coding, and previous-month carryover."""
import pytest
from datetime import date

def test_department_crud_and_color_customization(client, sample_scenario):
    # 1. Create a new department with custom color
    create_payload = {
        "code": "PED",
        "name": "Pediatrics Unit",
        "color_code": "#8B5CF6",
        "operating_regime": "24_7"
    }
    res = client.post("/api/departments", json=create_payload)
    assert res.status_code == 201
    created = res.json()
    dept_id = created["id"]
    assert created["code"] == "PED"
    assert created["color_code"] == "#8B5CF6"

    # 2. Update department color and name
    update_payload = {
        "name": "Pediatrics & Neonatal Unit",
        "color_code": "#EC4899"
    }
    up_res = client.put(f"/api/departments/{dept_id}", json=update_payload)
    assert up_res.status_code == 200
    updated = up_res.json()
    assert updated["name"] == "Pediatrics & Neonatal Unit"
    assert updated["color_code"] == "#EC4899"

    # 3. Delete department (succeeds because 0 employees assigned)
    del_res = client.delete(f"/api/departments/{dept_id}")
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]


def test_employee_crud_lifecycle(client, sample_scenario):
    depts = client.get("/api/departments").json()
    target_dept_id = depts[0]["id"]

    # 1. Create Employee
    emp_payload = {
        "employee_code": "TEST_EMP_99",
        "name": "Alex Mercer",
        "primary_department_id": target_dept_id,
        "max_hours_week": 36.0,
        "email": "alex@hospital.test"
    }
    create_res = client.post("/api/employees", json=emp_payload)
    assert create_res.status_code == 201
    emp = create_res.json()
    emp_id = emp["id"]
    assert emp["name"] == "Alex Mercer"
    assert emp["max_hours_week"] == 36.0

    # 2. Update Employee
    up_payload = {
        "name": "Alex Mercer, MD",
        "max_hours_week": 42.0
    }
    up_res = client.put(f"/api/employees/{emp_id}", json=up_payload)
    assert up_res.status_code == 200
    assert up_res.json()["name"] == "Alex Mercer, MD"
    assert up_res.json()["max_hours_week"] == 42.0

    # 3. Delete Employee
    del_res = client.delete(f"/api/employees/{emp_id}")
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]


def test_previous_month_carryover_and_trailing_shifts(client, sample_scenario):
    # 1. Generate Month 1: October 2026 (31 days)
    oct_res = client.post("/api/roster/generate", json={
        "name": "October 2026 Roster",
        "planning_year": 2026,
        "planning_month": 10,
        "variant_count": 1,
        "timeout_seconds": 10
    })
    assert oct_res.status_code == 200
    oct_plan_id = oct_res.json()["plan_id"]

    # 2. Check previous month summary endpoint for November 2026
    prev_sum = client.get("/api/roster/previous-month-summary?year=2026&month=11")
    assert prev_sum.status_code == 200
    prev_data = prev_sum.json()
    assert prev_data["has_previous_plan"] is True
    assert prev_data["prev_month"] == 10
    assert prev_data["prev_year"] == 2026
    assert len(prev_data["employees"]) > 0
    assert len(prev_data["trailing_dates"]) == 3

    # 3. Generate Month 2: November 2026 (30 days)
    nov_res = client.post("/api/roster/generate", json={
        "name": "November 2026 Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 10
    })
    assert nov_res.status_code == 200
    nov_plan_id = nov_res.json()["plan_id"]

    # 4. Fetch Staff-Centric schedule for November 2026 and verify previous month context
    nov_schedule = client.get(f"/api/roster/{nov_plan_id}?view=staff_centric").json()
    assert nov_schedule["previous_month_context"] is not None
    assert nov_schedule["previous_month_context"]["has_previous_plan"] is True
    assert nov_schedule["previous_month_context"]["planning_month"] == 10

    # Verify rows include department colors and previous month stats
    for row in nov_schedule["rows"]:
        assert "primary_department_color" in row
        assert row["primary_department_color"].startswith("#")
        assert "previous_month_summary" in row
        if row["previous_month_summary"]:
            assert "worked_hours" in row["previous_month_summary"]
            assert "trailing_3_days" in row["previous_month_summary"]
            assert len(row["previous_month_summary"]["trailing_3_days"]) == 3
