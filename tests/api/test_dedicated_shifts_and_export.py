"""Test suite verifying dedicated shifts, flexible off clearing, secondary float departments, and enhanced exports."""
import pytest
from datetime import date
from src.db.models import (
    Employee, Department, ShiftType, RosterPlan, RosterAssignment,
    LeaveRecord, EmployeeDepartmentEligibility
)

def test_clear_fixed_off_days_to_flexible(client, test_db, sample_scenario):
    """Verify that an employee's dedicated day off can be cleared to Flexible (None)."""
    emp = test_db.query(Employee).first()
    
    # 1. Set fixed days off to weekends "5,6"
    update_res = client.put(f"/api/employees/{emp.id}", json={
        "fixed_off_days": "5,6"
    })
    assert update_res.status_code == 200
    assert update_res.json()["fixed_off_days"] == "5,6"

    # Verify DB
    test_db.refresh(emp)
    assert emp.fixed_off_days == "5,6"

    # 2. Clear fixed days off to flexible (empty string "")
    clear_res = client.put(f"/api/employees/{emp.id}", json={
        "fixed_off_days": ""
    })
    assert clear_res.status_code == 200
    assert clear_res.json()["fixed_off_days"] is None

    test_db.refresh(emp)
    assert emp.fixed_off_days is None

    # 3. Test bulk update clearing fixed days off
    client.put(f"/api/employees/{emp.id}", json={"fixed_off_days": "0,1"})
    test_db.refresh(emp)
    assert emp.fixed_off_days == "0,1"

    bulk_res = client.post("/api/employees/bulk-update", json={
        "employee_ids": [emp.id],
        "fixed_off_days": ""
    })
    assert bulk_res.status_code == 200
    test_db.refresh(emp)
    assert emp.fixed_off_days is None


def test_dedicated_shift_and_secondary_departments_crud(client, test_db, sample_scenario):
    """Verify CRUD operations for dedicated shift and secondary floating department eligibility."""
    depts = test_db.query(Department).all()
    shifts = test_db.query(ShiftType).all()
    primary_dept = depts[0]
    secondary_dept = depts[1]
    morn_shift = next(s for s in shifts if "MORN" in s.code)

    # Create employee with dedicated morning shift and secondary department eligibility
    create_res = client.post("/api/employees", json={
        "employee_code": "TEST_DED_01",
        "name": "Dedicated Worker",
        "primary_department_id": primary_dept.id,
        "preferred_shift_type_id": morn_shift.id,
        "secondary_department_ids": [secondary_dept.id]
    })
    assert create_res.status_code == 201
    data = create_res.json()
    emp_id = data["id"]
    assert data["preferred_shift_type_id"] == morn_shift.id
    assert data["preferred_shift_code"] == morn_shift.code
    assert secondary_dept.id in data["secondary_department_ids"]

    # Verify retrieval
    get_res = client.get(f"/api/employees/{emp_id}")
    assert get_res.status_code == 200
    assert get_res.json()["preferred_shift_type_id"] == morn_shift.id

    # Update: Change to flexible shift (None) and remove secondary floats
    put_res = client.put(f"/api/employees/{emp_id}", json={
        "preferred_shift_type_id": None,
        "secondary_department_ids": []
    })
    assert put_res.status_code == 200
    assert put_res.json()["preferred_shift_type_id"] is None
    assert put_res.json()["secondary_department_ids"] == []


def test_solver_dedicated_shift_adherence(client, test_db, sample_scenario):
    """Verify CP-SAT solver prioritizes worker's dedicated shift throughout the schedule."""
    shifts = test_db.query(ShiftType).all()
    morn_shift = next(s for s in shifts if "MORN" in s.code)
    icu = test_db.query(Department).filter(Department.code == "ICU").first()

    # Add a 4th ICU employee so ICU has sufficient coverage without forcing shift changes
    emp4 = Employee(employee_code="ICU_4", name="ICU Staff 4", primary_department_id=icu.id, max_hours_week=40.0)
    test_db.add(emp4)
    test_db.flush()
    test_db.add(EmployeeDepartmentEligibility(employee_id=emp4.id, department_id=icu.id, preference_rank=1, can_float=False))
    test_db.commit()

    emp1 = test_db.query(Employee).filter(Employee.employee_code == "ICU_1").first()
    client.put(f"/api/employees/{emp1.id}", json={
        "preferred_shift_type_id": morn_shift.id
    })

    gen_res = client.post("/api/roster/generate", json={
        "name": "Dedicated Shift Adherence Test",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 6
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    # Inspect assignments for emp1
    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp1.id)
    assigned_shifts = [a["shift_code"] for a in emp_row["assignments"].values() if a and a.get("shift_code") and not a.get("is_day_off") and not a.get("is_comp_off")]

    # Check that worker received MORNING shifts predominantly (sticking to dedicated shift unless covering shortage)
    morn_count = sum(1 for sc in assigned_shifts if "MORN" in sc)
    assert morn_count > 0, "Worker with dedicated shift should be assigned their dedicated shift!"
    assert morn_count >= int(len(assigned_shifts) * 0.70), f"Expected at least 70% dedicated MORN shifts, got {morn_count}/{len(assigned_shifts)}: {assigned_shifts}"


def test_excel_and_pdf_enhanced_export(client, test_db, sample_scenario):
    """Verify Excel and PDF exports generate properly with DO, COFF, leaves, and full month."""
    gen_res = client.post("/api/roster/generate", json={
        "name": "Export Audit Test Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    # Pin a DO and COFF
    emp = test_db.query(Employee).first()
    client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": "2026-11-10",
        "off_type": "DAY_OFF"
    })
    client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": "2026-11-11",
        "off_type": "COFF"
    })

    # Test Excel Export
    excel_res = client.get(f"/api/export/{plan_id}/excel?view=both")
    assert excel_res.status_code == 200
    assert len(excel_res.content) > 1000
    assert excel_res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Test PDF Export
    pdf_res = client.get(f"/api/export/{plan_id}/pdf")
    assert pdf_res.status_code == 200
    assert len(pdf_res.content) > 1000
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")
