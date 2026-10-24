"""Tests for Multi-Select Employee Bulk Operations, Canvas Reset, Distinct Cell States, and CP-SAT Edge Cases."""
from datetime import date
from src.db.models import Employee, ShiftType, RosterPlan, RosterAssignment, LeaveRecord, DeficitLog, Department

def test_bulk_update_employees(client, test_db, sample_scenario):
    """Verify updating department, hours, fixed days off, and active state across multiple employees."""
    emps = test_db.query(Employee).limit(3).all()
    emp_ids = [e.id for e in emps]
    assert len(emp_ids) == 3

    target_dept = test_db.query(Department).filter(Department.code == "ER").first()
    assert target_dept is not None

    res = client.post("/api/employees/bulk-update", json={
        "employee_ids": emp_ids,
        "primary_department_id": target_dept.id,
        "max_hours_week": 36.0,
        "fixed_off_days": "1,2",
        "is_active": True
    })
    assert res.status_code == 200
    assert res.json()["updated_count"] == 3

    # Verify employees in database
    for eid in emp_ids:
        test_db.expire_all()
        e = test_db.query(Employee).filter(Employee.id == eid).first()
        assert e.primary_department_id == target_dept.id
        assert e.max_hours_week == 36.0
        assert e.fixed_off_days == "1,2"


def test_bulk_delete_employees(client, test_db, sample_scenario):
    """Verify deleting multiple employees in a single atomic bulk operation."""
    # Create two temporary employees
    e1_res = client.post("/api/employees", json={
        "employee_code": "TEMP_DEL_1",
        "name": "Temporary Delete 1",
        "primary_department_id": 1
    })
    e2_res = client.post("/api/employees", json={
        "employee_code": "TEMP_DEL_2",
        "name": "Temporary Delete 2",
        "primary_department_id": 1
    })
    id1 = e1_res.json()["id"]
    id2 = e2_res.json()["id"]

    del_res = client.post("/api/employees/bulk-delete", json={
        "employee_ids": [id1, id2]
    })
    assert del_res.status_code == 200
    assert del_res.json()["deleted_count"] == 2

    # Verify they no longer exist
    test_db.expire_all()
    assert test_db.query(Employee).filter(Employee.id.in_([id1, id2])).count() == 0


def test_clear_all_canvas_and_reset(client, test_db, sample_scenario):
    """Verify clearing all assignments and deficits from an active roster plan."""
    # First generate a plan
    gen_res = client.post("/api/roster/generate", json={
        "name": "Plan to Clear",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    # Ensure plan has assignments
    assign_count_before = test_db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).count()
    assert assign_count_before > 0

    # Clear all cells
    clear_res = client.delete(f"/api/roster/{plan_id}/clear-all")
    assert clear_res.status_code == 200
    data = clear_res.json()
    assert data["cleared"] is True
    assert data["deleted_assignments"] == assign_count_before

    # Verify zero assignments and zero deficits remain
    test_db.expire_all()
    assert test_db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).count() == 0
    assert test_db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).count() == 0

    plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    assert plan.status == "DRAFT"
    assert plan.solver_status == "RESET"


def test_distinct_cell_actions_empty_vs_dayoff_vs_compoff(client, test_db, sample_scenario):
    """Verify distinct behavior between Empty (fillable), Pinned Day OFF, and Pinned Comp Off."""
    emp = test_db.query(Employee).first()
    target_date = "2026-11-15"

    gen_res = client.post("/api/roster/generate", json={
        "name": "Distinct Actions Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # 1. Pin as Day OFF (DO)
    dayoff_res = client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": target_date,
        "off_type": "DAY_OFF"
    })
    assert dayoff_res.status_code == 200
    assert dayoff_res.json()["off_type"] == "DAY_OFF"

    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    cell = emp_row["assignments"][target_date]
    assert cell is not None
    assert cell["shift_code"] == "DO"
    assert cell["is_day_off"] is True
    assert cell["is_pinned"] is True

    # 2. Pin as Comp Off (COFF)
    coff_res = client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": target_date,
        "off_type": "COFF"
    })
    assert coff_res.status_code == 200
    assert coff_res.json()["off_type"] == "COFF"

    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    cell = emp_row["assignments"][target_date]
    assert cell is not None
    assert cell["shift_code"] == "COFF"
    assert cell["is_comp_off"] is True

    # 3. Clear cell as Empty (Fillable by Solver)
    del_res = client.delete(f"/api/roster/{plan_id}/assignments?employee_id={emp.id}&date={target_date}")
    assert del_res.status_code == 200

    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    cell = emp_row["assignments"][target_date]
    # If the target date was not a fixed recurring day off, it is now None (empty)
    if not (emp.fixed_off_days and str(date.fromisoformat(target_date).weekday()) in emp.fixed_off_days.split(",")):
        assert cell is None, "Cell should be completely empty and fillable by the solver!"


def test_planner_generation_and_solve_remaining_edge_cases(client, test_db, sample_scenario):
    """Verify CP-SAT solver edge cases: solve from scratch, solve remaining with pinned shifts & offs, and shortages."""
    emp = test_db.query(Employee).first()
    test_dept = test_db.query(Department).first()
    test_shift = test_db.query(ShiftType).first()

    # Step 1: Create a plan, then clear canvas
    gen_res = client.post("/api/roster/generate", json={
        "name": "Edge Cases Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]
    client.delete(f"/api/roster/{plan_id}/clear-all")

    # Step 2: Manually pre-pin a shift on Nov 10
    pin_shift_res = client.post(f"/api/roster/{plan_id}/assignments", json={
        "employee_id": emp.id,
        "department_id": test_dept.id,
        "shift_type_id": test_shift.id,
        "date": "2026-11-10",
        "force_override": True,
        "is_pinned": True
    })
    assert pin_shift_res.status_code == 200

    # Step 3: Pin a Day OFF on Nov 11
    client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": "2026-11-11",
        "off_type": "DAY_OFF"
    })

    # Step 4: Pin a Comp Off on Nov 12
    client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": "2026-11-12",
        "off_type": "COFF"
    })

    # Step 5: Solve remaining blank slots
    solve_res = client.post(f"/api/roster/{plan_id}/solve-remaining?timeout_seconds=5")
    assert solve_res.status_code == 200
    assert solve_res.json()["status"] == "SOLVED"

    # Step 6: Verify pinned slots remain strictly intact
    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    assigns = emp_row["assignments"]

    # Nov 10 must be the pinned shift
    assert assigns["2026-11-10"] is not None
    assert assigns["2026-11-10"]["shift_id"] == test_shift.id
    assert assigns["2026-11-10"]["is_pinned"] is True

    # Nov 11 must be DO
    assert assigns["2026-11-11"]["shift_code"] == "DO"

    # Nov 12 must be COFF
    assert assigns["2026-11-12"]["shift_code"] == "COFF"


def test_pinned_shift_overrides_fixed_off_day(client, test_db, sample_scenario):
    """Verify that a manual pinned shift on an employee's fixed day off takes precedence and CP-SAT solves."""
    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()

    # Set employee to have fixed off days on Monday (0)
    emp.fixed_off_days = "0"
    test_db.commit()

    # Generate a plan
    gen_res = client.post("/api/roster/generate", json={
        "name": "Override Day Off Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # 2026-11-02 is a Monday. Manually pin a shift on this Monday.
    pin_res = client.post(f"/api/roster/{plan_id}/assignments", json={
        "employee_id": emp.id,
        "department_id": dept.id,
        "shift_type_id": shift.id,
        "date": "2026-11-02",
        "force_override": True,
        "is_pinned": True
    })
    assert pin_res.status_code == 200

    # Solve remaining blank slots
    solve_res = client.post(f"/api/roster/{plan_id}/solve-remaining?timeout_seconds=5")
    assert solve_res.status_code == 200
    assert solve_res.json()["status"] == "SOLVED"

    sched_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row = next(r for r in sched_res.json()["rows"] if r["employee_id"] == emp.id)
    cell = emp_row["assignments"]["2026-11-02"]
    assert cell is not None
    assert cell["shift_id"] == shift.id
    assert cell["is_pinned"] is True


def test_empty_cell_after_clearing_pinned_off(client, test_db, sample_scenario):
    """Verify that clearing a pinned Day OFF makes the cell empty and fillable by the solver."""
    emp = test_db.query(Employee).first()
    test_date = "2026-11-17"  # Tuesday (weekday 1)
    emp.fixed_off_days = None  # no fixed days off
    test_db.commit()

    gen_res = client.post("/api/roster/generate", json={
        "name": "Clear Pinned Off Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    # 1. Pin a Day OFF
    client.post(f"/api/roster/{plan_id}/pin-off", json={
        "employee_id": emp.id,
        "date": test_date,
        "off_type": "DAY_OFF"
    })

    # Verify grid shows DO
    sched1 = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row1 = next(r for r in sched1.json()["rows"] if r["employee_id"] == emp.id)
    assert emp_row1["assignments"][test_date]["shift_code"] == "DO"

    # 2. Empty the cell
    del_res = client.delete(f"/api/roster/{plan_id}/assignments?employee_id={emp.id}&date={test_date}")
    assert del_res.status_code == 200

    # Verify grid shows cell is genuinely empty (None)
    sched2 = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    emp_row2 = next(r for r in sched2.json()["rows"] if r["employee_id"] == emp.id)
    assert emp_row2["assignments"][test_date] is None

    # 3. Solve remaining - CP-SAT solves without errors
    solve_res = client.post(f"/api/roster/{plan_id}/solve-remaining?timeout_seconds=5")
    assert solve_res.status_code == 200
    assert solve_res.json()["status"] == "SOLVED"


def test_solve_remaining_unique_constraint_shield(client, test_db, sample_scenario):
    """Verify that solve-remaining never triggers UNIQUE constraint IntegrityError,
    even when called iteratively with pinned, unpinned, and manual shifts."""
    gen_res = client.post("/api/roster/generate", json={
        "name": "Unique Shield Plan",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    emps = test_db.query(Employee).limit(3).all()
    shifts = test_db.query(ShiftType).all()
    assert len(emps) >= 3 and len(shifts) >= 2

    # Pin several shifts explicitly
    for i, emp in enumerate(emps):
        d_str = f"2026-11-{10 + i:02d}"
        s = shifts[i % len(shifts)]
        assign_res = client.post(f"/api/roster/{plan_id}/assignments", json={
            "employee_id": emp.id,
            "department_id": emp.primary_department_id,
            "shift_type_id": s.id,
            "date": d_str,
            "is_pinned": True,
            "force_override": True
        })
        assert assign_res.status_code == 200

    # 1. Execute solve-remaining first time
    solve1 = client.post(f"/api/roster/{plan_id}/solve-remaining?timeout_seconds=5")
    assert solve1.status_code == 200
    assert solve1.json()["status"] == "SOLVED"

    # Verify no duplicate (employee_id, date) exists in DB
    all_assigns = test_db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    emp_date_pairs = [(a.employee_id, a.date) for a in all_assigns]
    assert len(emp_date_pairs) == len(set(emp_date_pairs)), "Duplicate (employee, date) found in DB!"

    # 2. Execute solve-remaining a second time immediately (idempotence test)
    solve2 = client.post(f"/api/roster/{plan_id}/solve-remaining?timeout_seconds=5")
    assert solve2.status_code == 200
    assert solve2.json()["status"] == "SOLVED"

    # Verify again
    test_db.expire_all()
    all_assigns2 = test_db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    emp_date_pairs2 = [(a.employee_id, a.date) for a in all_assigns2]
    assert len(emp_date_pairs2) == len(set(emp_date_pairs2)), "Duplicate (employee, date) found on second solve!"


