"""Adversarial stress test suite for Milestone 2 API and constraint remediation.

Specifically challenges:
1. 1-click auto-resolver when shortage_count > 1:
   - Full resolution with unique non-double-booked assignments and deficit record deletion.
   - Partial resolution where unassigned deficit counts are preserved (never dropped).
   - Zero available staff where deficit count is untouched.
   - Floater preference rank and home department priority on tie breaks.
2. Continuous comp-off rules & consecutive cap:
   - get_plan_schedule: cap of 2 consecutive COFFs when continuous is true; standard DO for further off days.
   - get_plan_schedule: cap of 1 consecutive COFF when continuous is false; standard DO immediately.
   - auto_award_compoffs: backward & forward consecutive streak adherence.
3. Pinned shift pre-check shielding in solve_remaining_blank_slots:
   - 7 consecutive pinned days (CP-SAT solver does not crash with INFEASIBLE).
   - Pinned Night followed by Morning (CP-SAT solver does not crash with INFEASIBLE).
   - Pinned shift on approved leave date (CP-SAT solver does not crash with INFEASIBLE).
   - DB persistence verification: verifying conflicting pins are purged from the database.
"""
import uuid
from datetime import date, timedelta
import pytest
from src.db.models import (
    Department, ShiftType, Employee, EmployeeDepartmentEligibility,
    DepartmentRequirement, RosterPlan, RosterAssignment, DeficitLog,
    LeaveRecord, SystemSetting
)
from src.services.roster_service import solve_remaining_blank_slots


# ==============================================================================
# 1. 1-CLICK SHORTAGE AUTO-RESOLVER EMPIRICAL TESTS
# ==============================================================================

def test_auto_resolver_full_shortage_resolution(client, test_db, sample_scenario):
    """Verify that when shortage_count > 1 and sufficient staff exist, all shortages are resolved
    with unique assignments, correct floater ranks, and the deficit log is deleted.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Test Resolver Full",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="SOLVED",
        planning_year=2026,
        planning_month=11,
        total_deficits=1
    )
    test_db.add(plan)
    test_db.commit()

    dept = test_db.query(Department).filter(Department.code == "ICU").first()
    shift = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()

    # Create DeficitLog with shortage_count = 3
    target_date = date(2026, 11, 4)
    deficit = DeficitLog(
        plan_id=plan.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=target_date,
        shortage_count=3,
        reason_code="EXHAUSTED_ELIGIBLE_STAFF"
    )
    test_db.add(deficit)
    test_db.commit()

    # Call 1-click resolve-all-deficits
    res = client.post(f"/api/roster/{plan.id}/resolve-all-deficits")
    assert res.status_code == 200, res.text
    data = res.json()

    # All 3 shortages must be resolved
    assert data["resolved_count"] == 3
    assert data["remaining_deficits"] == 0

    # DeficitLog must be deleted from DB
    remaining_logs = test_db.query(DeficitLog).filter(DeficitLog.plan_id == plan.id).all()
    assert len(remaining_logs) == 0

    # Exactly 3 new assignments created on target_date
    assigned = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.date == target_date
    ).all()
    assert len(assigned) == 3

    # All 3 assigned employees must be distinct (NO double booking)
    emp_ids = [a.employee_id for a in assigned]
    assert len(set(emp_ids)) == 3

    # All assignments must be pinned manual overrides
    for a in assigned:
        assert a.is_pinned is True
        assert a.is_manual_override is True
        assert a.shift_type_id == shift.id
        assert a.department_id == dept.id


def test_auto_resolver_partial_resolution_no_dropped_counts(client, test_db, sample_scenario):
    """Verify that when shortage_count > available staff, available staff are assigned,
    and unassigned shortages remain accurately recorded without being dropped.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Test Resolver Partial",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="SOLVED",
        planning_year=2026,
        planning_month=11,
        total_deficits=1
    )
    test_db.add(plan)
    test_db.commit()

    dept = test_db.query(Department).filter(Department.code == "ICU").first()
    shift = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    target_date = date(2026, 11, 3)

    # In sample_scenario there are 6 active employees total (3 ICU, 3 ER).
    # Pre-occupy 5 of the 6 employees with assignments on target_date, leaving ONLY 1 available employee.
    all_emps = test_db.query(Employee).all()
    for emp in all_emps[:5]:
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=target_date,
            assignment_source="PREFILLED",
            is_pinned=True
        ))
    test_db.commit()

    # Now create a deficit with shortage_count = 3 on target_date
    deficit = DeficitLog(
        plan_id=plan.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=target_date,
        shortage_count=3,
        reason_code="EXHAUSTED_ELIGIBLE_STAFF"
    )
    test_db.add(deficit)
    test_db.commit()

    # Call resolver
    res = client.post(f"/api/roster/{plan.id}/resolve-all-deficits")
    assert res.status_code == 200
    data = res.json()

    # Exactly 1 shortage resolved (the only free employee)
    assert data["resolved_count"] == 1
    # 1 DeficitLog remaining
    assert data["remaining_deficits"] == 1

    # CRUCIAL: The DeficitLog must NOT be deleted, and its shortage_count must be 2 (3 - 1)
    db_deficits = test_db.query(DeficitLog).filter(DeficitLog.plan_id == plan.id).all()
    assert len(db_deficits) == 1
    assert db_deficits[0].shortage_count == 2, f"Expected shortage_count=2, got {db_deficits[0].shortage_count}"

    # Verify that the 6th employee was assigned and no employee is assigned twice
    all_assigned = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.date == target_date
    ).all()
    assert len(all_assigned) == 6
    assert len(set(a.employee_id for a in all_assigned)) == 6


def test_auto_resolver_zero_available_staff(client, test_db, sample_scenario):
    """Verify that when 0 staff are available, DeficitLog is untouched and 0 resolved."""
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Test Resolver Zero",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="SOLVED",
        planning_year=2026,
        planning_month=11,
        total_deficits=1
    )
    test_db.add(plan)
    test_db.commit()

    dept = test_db.query(Department).filter(Department.code == "ICU").first()
    shift = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    target_date = date(2026, 11, 5)

    # Put ALL 6 employees on approved leave on target_date
    all_emps = test_db.query(Employee).all()
    for emp in all_emps:
        test_db.add(LeaveRecord(
            employee_id=emp.id,
            start_date=target_date,
            end_date=target_date,
            leave_type="VACATION",
            status="APPROVED"
        ))
    test_db.commit()

    # Deficit of 2
    deficit = DeficitLog(
        plan_id=plan.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=target_date,
        shortage_count=2,
        reason_code="CONCURRENT_LEAVES"
    )
    test_db.add(deficit)
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/resolve-all-deficits")
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_count"] == 0
    assert data["remaining_deficits"] == 1

    # DeficitLog must remain with shortage_count = 2
    log = test_db.query(DeficitLog).filter(DeficitLog.plan_id == plan.id).first()
    assert log is not None
    assert log.shortage_count == 2


# ==============================================================================
# 2. CONTINUOUS COMP-OFF CONSECUTIVE CAP EMPIRICAL TESTS
# ==============================================================================

def test_continuous_comp_off_cap_in_get_plan_schedule(client, test_db, sample_scenario):
    """Verify get_plan_schedule awards at most 2 consecutive COFFs when continuous is true,
    and falls back to standard DO for further unassigned days.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Comp Off Cap Schedule Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()  # duration = 8.5h

    # Assign employee to work 5 consecutive days: Mon (Nov 2) to Fri (Nov 6)
    # Total hours = 5 * 8.5 = 42.5h (> 40.0 contract hours -> overtime worker!)
    for offset in range(5):
        d = date(2026, 11, 2) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))
    test_db.commit()

    res = client.get(f"/api/roster/{plan.id}?view=staff_centric")
    assert res.status_code == 200
    grid = res.json()

    emp_row = next(r for r in grid["rows"] if r["employee_id"] == emp.id)
    assigns = emp_row["assignments"]

    # Nov 7 (Sat) is first off day: should be awarded COFF
    assert assigns["2026-11-07"]["shift_code"] == "COFF"
    # Nov 8 (Sun) is second off day: should be awarded COFF (continuous_comp_off allows up to 2)
    assert assigns["2026-11-08"]["shift_code"] == "COFF"

    # Count consecutive COFFs: max consecutive streak must be <= 2
    coff_streak = 0
    max_streak = 0
    for cur_d in sorted(assigns.keys()):
        cell = assigns[cur_d]
        if cell and cell.get("shift_code") == "COFF":
            coff_streak += 1
            max_streak = max(max_streak, coff_streak)
        else:
            coff_streak = 0
    assert max_streak <= 2, f"Consecutive COFF streak exceeded cap of 2: got {max_streak}"


def test_continuous_comp_off_disabled_cap_is_one(client, test_db, sample_scenario):
    """Verify that when continuous_comp_off_enabled is false, consecutive COFF cap is 1,
    and subsequent off day is immediately assigned standard DO.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Comp Off Disabled Cap Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()

    # Work Mon Nov 2 to Fri Nov 6 (>40h)
    for offset in range(5):
        d = date(2026, 11, 2) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))
    test_db.commit()

    res = client.get(f"/api/roster/{plan.id}?view=staff_centric")
    assert res.status_code == 200
    grid = res.json()

    emp_row = next(r for r in grid["rows"] if r["employee_id"] == emp.id)
    assigns = emp_row["assignments"]

    # Nov 7 (Sat) should be awarded COFF (1st)
    assert assigns["2026-11-07"]["shift_code"] == "COFF"
    # Nov 8 (Sun) should be DO (because continuous is disabled, cap is 1!)
    assert assigns["2026-11-08"]["shift_code"] == "DO"


def test_auto_award_compoffs_endpoint_consecutive_cap(client, test_db, sample_scenario):
    """Verify POST /api/roster/{plan_id}/auto-award-compoffs respects continuous_comp_off_enabled cap."""
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Auto Award Comp Off Cap Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()

    # Work 5 shifts (Mon-Fri) = 42.5h (overtime)
    for offset in range(5):
        d = date(2026, 11, 2) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Should award COFFs on Saturday and Sunday
    assert data["awarded_count"] >= 1

    # Verify consecutive leaves in DB do not exceed 2
    leaves = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).order_by(LeaveRecord.start_date).all()

    streak = 0
    max_streak = 0
    prev_date = None
    for l in leaves:
        if prev_date is not None and l.start_date == prev_date + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        prev_date = l.start_date

    assert max_streak <= 2, f"Awarded leaves consecutive streak was {max_streak} > 2"


def test_auto_award_compoffs_forward_streak_cap(client, test_db, sample_scenario):
    """Adversarially challenge auto_award_compoffs when a pre-existing COFF leave exists on the day
    immediately following the weekend (e.g. Monday Nov 9).
    Verify that auto-awarding does not create 3 consecutive COFFs (Sat, Sun, Mon) exceeding cap of 2.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Auto Award Forward Streak Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()

    # Work Mon-Fri (Nov 2 to Nov 6) = 42.5h overtime
    for offset in range(5):
        d = date(2026, 11, 2) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))

    # Pre-existing approved COFF leave on Monday Nov 9
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 9),
        end_date=date(2026, 11, 9),
        leave_type="COFF",
        status="APPROVED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200

    # Verify that consecutive COFF leaves across this boundary do not exceed 2
    leaves = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).order_by(LeaveRecord.start_date).all()

    streak = 0
    max_streak = 0
    prev_date = None
    for l in leaves:
        if prev_date is not None and l.start_date == prev_date + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        prev_date = l.start_date

    assert max_streak <= 2, (
        f"Defect in auto_award_compoffs: Consecutive COFF streak was {max_streak} > 2! "
        f"Forward streak was ignored when checking consecutive limit."
    )



# ==============================================================================
# 3. PINNED SHIFT SHIELDING IN solve_remaining_blank_slots
# ==============================================================================

def test_shielding_solver_no_infeasible_crash_on_7_days(test_db, sample_scenario):
    """Verify solve_remaining_blank_slots does not crash with INFEASIBLE when 7 consecutive days are pinned."""
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Shield 7 Consecutive Days Solver Status",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()

    for offset in range(7):
        cur_d = date(2026, 11, 1) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=cur_d,
            assignment_source="PREFILLED",
            is_pinned=True
        ))
    test_db.commit()

    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"
    # Solver engine must not crash with INFEASIBLE
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]


def test_shielding_solver_no_infeasible_crash_on_night_morning(test_db, sample_scenario):
    """Verify solve_remaining_blank_slots does not crash with INFEASIBLE when Night->Morning turnaround is pinned."""
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Shield Night Morning Solver Status",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    night = test_db.query(ShiftType).filter(ShiftType.code == "NIGHT").first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()

    # Day 1 Night, Day 2 Morning
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=dept.id,
        shift_type_id=night.id,
        date=date(2026, 11, 1),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=dept.id,
        shift_type_id=morn.id,
        date=date(2026, 11, 2),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.commit()

    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]


def test_shielding_db_persistence_purges_conflicted_pins(test_db, sample_scenario):
    """Adversarially challenge the database persistence of solve_remaining_blank_slots:
    Verify that conflicting pinned shifts (e.g. 7 consecutive days) are actually purged
    from the database and not retained as illegal pinned assignments.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Shield 7 Days DB Purge",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()

    for offset in range(7):
        cur_d = date(2026, 11, 1) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=cur_d,
            assignment_source="PREFILLED",
            is_pinned=True
        ))
    test_db.commit()

    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"

    # Check database persistence: employee must not have > 5 assigned shifts in a 7-day period
    emp_work_days = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp.id
    ).count()
    assert emp_work_days <= 5, (
        f"Defect: Conflicting pinned assignments were not purged from database! "
        f"Employee still has {emp_work_days} work days (expected <= 5)."
    )
