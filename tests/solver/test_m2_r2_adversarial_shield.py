"""Adversarial challenge test suite for Milestone 2 Iteration 2:
Solver shielding, zero-demand pins, conflicting pin database purges,
and fallback relaxation shield on INFEASIBLE solver returns.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch
import pytest

from src.db.models import (
    Department, ShiftType, Employee, EmployeeDepartmentEligibility,
    DepartmentRequirement, RosterPlan, RosterAssignment, DeficitLog,
    LeaveRecord
)
from src.services.roster_service import solve_remaining_blank_slots
from src.solver.engine import SolveResult


def test_pinning_shift_on_zero_demand_does_not_crash_infeasible(test_db, sample_scenario):
    """Challenge 1: Empirically verify that pinning shifts on zero-demand days/shifts
    does not cause INFEASIBLE solver crashes, and that the zero-demand pin is purged from SQLite.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Zero Demand Pinning Test",
        start_date=date(2026, 11, 1),  # Sunday (dow = 6)
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    icu = test_db.query(Department).filter(Department.code == "ICU").first()
    night = test_db.query(ShiftType).filter(ShiftType.code == "NIGHT").first()
    emp = test_db.query(Employee).filter(Employee.primary_department_id == icu.id).first()

    # Set requirement for Sunday (dow = 6) Night shift in ICU to 0 (zero demand)
    req = test_db.query(DepartmentRequirement).filter(
        DepartmentRequirement.department_id == icu.id,
        DepartmentRequirement.shift_type_id == night.id,
        DepartmentRequirement.day_of_week == 6  # Sunday
    ).first()
    if req:
        req.min_staff = 0
        req.optimal_staff = 0
        test_db.commit()

    # User pins employee to zero-demand shift on Sunday Nov 1
    zero_demand_pin = RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=icu.id,
        shift_type_id=night.id,
        date=date(2026, 11, 1),
        assignment_source="PREFILLED",
        is_pinned=True
    )
    test_db.add(zero_demand_pin)
    test_db.commit()

    # Run solver shielding
    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)

    # 1. Must solve cleanly without INFEASIBLE crash
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]

    # 2. Pinned assignment on zero-demand slot must be purged from database
    purged_assignment = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp.id,
        RosterAssignment.department_id == icu.id,
        RosterAssignment.shift_type_id == night.id,
        RosterAssignment.date == date(2026, 11, 1)
    ).first()
    assert purged_assignment is None, "Zero-demand pinned shift was NOT purged from SQLite!"

    # 3. No one should be assigned to the zero-demand slot on Sunday Nov 1
    assigned_to_zero_slot = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.department_id == icu.id,
        RosterAssignment.shift_type_id == night.id,
        RosterAssignment.date == date(2026, 11, 1)
    ).all()
    assert len(assigned_to_zero_slot) == 0, "Staff was assigned to a slot with 0 demand!"


def test_pinning_over_capacity_shifts_purges_excess_pins(test_db, sample_scenario):
    """Challenge 1b: When pinned assignments exceed demand requirement for a slot,
    excess pins must be purged cleanly without INFEASIBLE crash or duplicate key collisions.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Over Capacity Pinning Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    icu = test_db.query(Department).filter(Department.code == "ICU").first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    icu_emps = test_db.query(Employee).filter(Employee.primary_department_id == icu.id).all()
    assert len(icu_emps) >= 3

    target_date = date(2026, 11, 2)  # Monday: req = 1

    # Pin ALL 3 employees to the same slot where req = 1
    for emp in icu_emps:
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=icu.id,
            shift_type_id=morn.id,
            date=target_date,
            assignment_source="PREFILLED",
            is_pinned=True
        ))
    test_db.commit()

    # Solve
    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]

    # Only 1 employee should remain assigned to ICU Morning on Monday Nov 2
    assigned_count = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.department_id == icu.id,
        RosterAssignment.shift_type_id == morn.id,
        RosterAssignment.date == target_date
    ).count()
    assert assigned_count == 1, f"Expected 1 assigned staff for req=1, found {assigned_count}"


def test_pinning_ineligible_department_purged_cleanly(test_db, sample_scenario):
    """Challenge 1c: Pinning an employee to a department they are not eligible for
    must be purged from SQLite and not crash the solver.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Ineligible Dept Pinning Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    icu = test_db.query(Department).filter(Department.code == "ICU").first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    # Find ER employee who cannot float to ICU (ER_2 or ER_3)
    ineligible_emp = test_db.query(Employee).filter(Employee.employee_code == "ER_2").first()
    assert ineligible_emp is not None

    # Verify ineligible_emp is indeed not eligible for ICU
    elig = test_db.query(EmployeeDepartmentEligibility).filter(
        EmployeeDepartmentEligibility.employee_id == ineligible_emp.id,
        EmployeeDepartmentEligibility.department_id == icu.id
    ).first()
    assert elig is None

    # Pin ineligible employee to ICU
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=ineligible_emp.id,
        department_id=icu.id,
        shift_type_id=morn.id,
        date=date(2026, 11, 1),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.commit()

    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]

    # Ineligible pin must be purged
    purged = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == ineligible_emp.id,
        RosterAssignment.department_id == icu.id
    ).first()
    assert purged is None, "Ineligible department pin was NOT purged from SQLite!"


def test_clean_purge_of_conflicting_pins_7_days_and_turnaround_and_leaves(test_db, sample_scenario):
    """Challenge 2: Empirically verify that conflicting pinned shifts
    (7-day streaks, turnaround violations, leave overlaps) are cleanly purged
    from SQLite without leaving orphan rows or violating unique constraints.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Multi Conflict Purge Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    dept = test_db.query(Department).first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    night = test_db.query(ShiftType).filter(ShiftType.code == "NIGHT").first()

    # Employee 1: 7-day streak pinned (Mon-Sun)
    emp1 = test_db.query(Employee).filter(Employee.employee_code == "ICU_1").first()
    for offset in range(7):
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp1.id,
            department_id=dept.id,
            shift_type_id=morn.id,
            date=date(2026, 11, 1) + timedelta(days=offset),
            assignment_source="PREFILLED",
            is_pinned=True
        ))

    # Employee 2: Night -> Morning turnaround violation pinned on Nov 1 & Nov 2
    emp2 = test_db.query(Employee).filter(Employee.employee_code == "ICU_2").first()
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp2.id,
        department_id=dept.id,
        shift_type_id=night.id,
        date=date(2026, 11, 1),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp2.id,
        department_id=dept.id,
        shift_type_id=morn.id,
        date=date(2026, 11, 2),
        assignment_source="PREFILLED",
        is_pinned=True
    ))

    # Employee 3: Approved leave on Nov 3, but pinned on Nov 3 Morning
    emp3 = test_db.query(Employee).filter(Employee.employee_code == "ICU_3").first()
    test_db.add(LeaveRecord(
        employee_id=emp3.id,
        start_date=date(2026, 11, 3),
        end_date=date(2026, 11, 3),
        leave_type="VACATION",
        status="APPROVED"
    ))
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp3.id,
        department_id=dept.id,
        shift_type_id=morn.id,
        date=date(2026, 11, 3),
        assignment_source="PREFILLED",
        is_pinned=True
    ))

    test_db.commit()

    # Run solver
    solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]

    # Verify Emp 1: Days worked in DB must be <= 5 (no 7-day streak)
    emp1_shifts = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp1.id
    ).all()
    assert len(emp1_shifts) <= 5, f"Emp1 has {len(emp1_shifts)} shifts, expected <= 5"

    # Verify Emp 2: Turnaround violation purged; no Night immediately followed by Morning
    emp2_d1 = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp2.id,
        RosterAssignment.date == date(2026, 11, 1)
    ).first()
    emp2_d2 = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp2.id,
        RosterAssignment.date == date(2026, 11, 2)
    ).first()
    if emp2_d1 and emp2_d2:
        # If both exist, verify it is NOT Night -> Morning
        assert not (emp2_d1.shift_type_id == night.id and emp2_d2.shift_type_id == morn.id), \
            "Illegal Night -> Morning turnaround preserved in SQLite!"

    # Verify Emp 3: Leave overlap purged; employee must NOT be assigned on Nov 3
    emp3_d3 = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp3.id,
        RosterAssignment.date == date(2026, 11, 3)
    ).first()
    assert emp3_d3 is None, "Leave overlap pin was NOT purged from SQLite!"

    # Verify SQLite unique constraints: no duplicate (employee_id, date)
    all_assignments = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id
    ).all()
    emp_date_pairs = [(a.employee_id, a.date) for a in all_assignments]
    assert len(emp_date_pairs) == len(set(emp_date_pairs)), "Duplicate (employee_id, date) rows exist in SQLite!"


def test_fallback_shield_on_infeasible_solve_inserts_cleanly_without_collision(test_db, sample_scenario):
    """Challenge 3: Empirically stress-test the fallback shield when an initial solve
    returns INFEASIBLE: verify that existing assignments are cleared and relaxed assignments
    insert cleanly without unique key collisions or SQLite integrity errors.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Fallback Shield Infeasible Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()
    emp = test_db.query(Employee).first()

    # Seed 3 pinned assignments and 1 non-pinned assignment and 1 deficit log
    for offset in range(3):
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=shift.id,
            date=date(2026, 11, 1) + timedelta(days=offset),
            assignment_source="PREFILLED",
            is_pinned=True
        ))
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=date(2026, 11, 4),
        assignment_source="PREFILLED",
        is_pinned=False
    ))
    test_db.add(DeficitLog(
        plan_id=plan.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=date(2026, 11, 1),
        shortage_count=1,
        reason_code="EXHAUSTED_STAFF"
    ))
    test_db.commit()

    # Pre-condition check: 4 assignments and 1 deficit log exist
    assert test_db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan.id).count() == 4
    assert test_db.query(DeficitLog).filter(DeficitLog.plan_id == plan.id).count() == 1

    # Mock solve_roster: first call returns INFEASIBLE, second call (fallback relaxed) calls real solve_roster
    real_solve = solve_remaining_blank_slots.__globals__["solve_roster"]
    call_count = {"count": 0}

    def mock_solve_roster(ctx, timeout_seconds=15, strategy_name=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            # First solve simulated as INFEASIBLE
            return SolveResult(
                status="INFEASIBLE",
                solve_time_seconds=0.01,
                objective_score=0.0,
                assignments=[],
                deficits=[],
                strategy_name=strategy_name or "BALANCED"
            )
        else:
            # Second solve (fallback relaxed) runs the real solver
            return real_solve(ctx, timeout_seconds=timeout_seconds, strategy_name=strategy_name)

    with patch("src.services.roster_service.solve_roster", side_effect=mock_solve_roster):
        solved_plan = solve_remaining_blank_slots(test_db, plan.id, timeout_seconds=10)

    # Verify fallback was invoked (2 calls to solve_roster)
    assert call_count["count"] == 2, f"Fallback shield was not called! Call count = {call_count['count']}"

    # Verify plan solved cleanly
    assert solved_plan.status == "SOLVED"
    assert solved_plan.solver_status in ["OPTIMAL", "FEASIBLE"]

    # Verify that all inserted assignments are valid and no UNIQUE constraint violation occurred
    final_assignments = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id
    ).all()
    assert len(final_assignments) > 0, "No assignments inserted after fallback relaxed solve!"

    # Verify uniqueness of (employee_id, date) across all final assignments
    unique_keys = set((a.employee_id, a.date) for a in final_assignments)
    assert len(unique_keys) == len(final_assignments), "Duplicate (employee_id, date) found after fallback relaxed solve!"


def test_solve_remaining_endpoint_handles_conflicts_and_zero_demand_pins(client, test_db, sample_scenario):
    """End-to-end API Challenge: POST /api/roster/{plan_id}/solve-remaining must successfully solve
    and purge invalid pins without 500 error or SQLite IntegrityError.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="API Solve Remaining Conflicts Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 7),
        status="DRAFT",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    icu = test_db.query(Department).filter(Department.code == "ICU").first()
    night = test_db.query(ShiftType).filter(ShiftType.code == "NIGHT").first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    emp = test_db.query(Employee).filter(Employee.primary_department_id == icu.id).first()

    # Zero demand requirement on Sunday (dow = 6) Night
    req = test_db.query(DepartmentRequirement).filter(
        DepartmentRequirement.department_id == icu.id,
        DepartmentRequirement.shift_type_id == night.id,
        DepartmentRequirement.day_of_week == 6
    ).first()
    if req:
        req.min_staff = 0
        req.optimal_staff = 0
        test_db.commit()

    # Pin to zero-demand shift
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=icu.id,
        shift_type_id=night.id,
        date=date(2026, 11, 1),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/solve-remaining?timeout_seconds=10")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["status"] == "SOLVED"
    assert data["solver_status"] in ["OPTIMAL", "FEASIBLE"]

    # Verify zero-demand pin was purged
    purged = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp.id,
        RosterAssignment.department_id == icu.id,
        RosterAssignment.shift_type_id == night.id,
        RosterAssignment.date == date(2026, 11, 1)
    ).first()
    assert purged is None

