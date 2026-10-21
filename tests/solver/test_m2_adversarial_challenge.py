"""Adversarial challenge test suite for Milestone 2 algorithmic solver fixes.

Covers:
1. Micro-department deficit diagnostics (1-worker and 2-worker departments with leaves vs no leaves).
2. Multi-department leave isolation in deficit diagnostics.
3. Floating vs dedicated shift preference (zero floats when no shortage exists, even with secondary eligibility and conflicting preferred shifts).
4. Shortage-induced floating activation.
5. Night shift turnaround ergonomics (Night -> Night permitted and solves, Night -> Morning strictly blocked).
"""
from datetime import date
import pytest
from src.solver.model import SchedulingContext
from src.solver.engine import diagnose_deficit_reason, solve_roster, generate_roster_variants
from src.solver.rules import calculate_inter_shift_rest_hours, is_transition_forbidden
from src.db.models import Department, ShiftType, Employee


# ==============================================================================
# 1. Micro-Department Deficit Diagnostics Challenge
# ==============================================================================

def test_micro_department_1_worker_zero_leaves():
    """1-worker department with 0 leaves and demand=2 must diagnose deficit as EXHAUSTED_ELIGIBLE_STAFF."""
    d = Department(id=1, code="MICRO1", name="Micro 1")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e = Employee(id=1, employee_code="EMP1", name="Solo Staff", primary_department_id=1, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 2},
        eligibilities={(1, 1): (1, True)},
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
    )
    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 1
    assert res.deficits[0]["shortage_count"] == 1
    assert res.deficits[0]["reason_code"] == "EXHAUSTED_ELIGIBLE_STAFF"


def test_micro_department_1_worker_with_approved_leave():
    """1-worker department where sole worker has approved leave must diagnose deficit as CONCURRENT_LEAVES."""
    d = Department(id=1, code="MICRO1", name="Micro 1")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e = Employee(id=1, employee_code="EMP1", name="Solo Staff", primary_department_id=1, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 1},
        eligibilities={(1, 1): (1, True)},
        preferences={},
        approved_leaves={(1, 0)},
        pinned_assignments={},
        pinned_offs=set(),
    )
    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 1
    assert res.deficits[0]["reason_code"] == "CONCURRENT_LEAVES"


def test_micro_department_2_workers_zero_leaves():
    """2-worker department with 0 leaves and demand=3 must diagnose deficit as EXHAUSTED_ELIGIBLE_STAFF."""
    d = Department(id=1, code="MICRO2", name="Micro 2")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e1 = Employee(id=1, employee_code="EMP1", name="Staff 1", primary_department_id=1, max_hours_week=40.0)
    e2 = Employee(id=2, employee_code="EMP2", name="Staff 2", primary_department_id=1, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 3},
        eligibilities={(1, 1): (1, True), (2, 1): (1, True)},
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
    )
    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 1
    assert res.deficits[0]["shortage_count"] == 1
    assert res.deficits[0]["reason_code"] == "EXHAUSTED_ELIGIBLE_STAFF"


def test_micro_department_2_workers_with_one_leave():
    """2-worker department with 1 leave and demand=2 must diagnose deficit as CONCURRENT_LEAVES."""
    d = Department(id=1, code="MICRO2", name="Micro 2")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e1 = Employee(id=1, employee_code="EMP1", name="Staff 1", primary_department_id=1, max_hours_week=40.0)
    e2 = Employee(id=2, employee_code="EMP2", name="Staff 2", primary_department_id=1, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 2},
        eligibilities={(1, 1): (1, True), (2, 1): (1, True)},
        preferences={},
        approved_leaves={(1, 0)},
        pinned_assignments={},
        pinned_offs=set(),
    )
    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 1
    assert res.deficits[0]["reason_code"] == "CONCURRENT_LEAVES"


def test_micro_department_2_workers_with_both_on_leave():
    """2-worker department with both workers on leave and demand=1 must diagnose deficit as CONCURRENT_LEAVES."""
    d = Department(id=1, code="MICRO2", name="Micro 2")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e1 = Employee(id=1, employee_code="EMP1", name="Staff 1", primary_department_id=1, max_hours_week=40.0)
    e2 = Employee(id=2, employee_code="EMP2", name="Staff 2", primary_department_id=1, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 1},
        eligibilities={(1, 1): (1, True), (2, 1): (1, True)},
        preferences={},
        approved_leaves={(1, 0), (2, 0)},
        pinned_assignments={},
        pinned_offs=set(),
    )
    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 1
    assert res.deficits[0]["reason_code"] == "CONCURRENT_LEAVES"


def test_zero_qualified_staff_diagnostic():
    """Department with 0 eligible staff must diagnose deficit as ZERO_QUALIFIED_STAFF."""
    d = Department(id=1, code="NOSTAFF", name="No Staff Dept")
    s = ShiftType(id=1, code="MORN", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0)
    e = Employee(id=1, employee_code="EMP1", name="Staff", primary_department_id=2, max_hours_week=40.0)

    ctx = SchedulingContext(
        employees=[e],
        departments=[d],
        shifts=[s],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 1},
        eligibilities={(1, 2): (1, True)},
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
    )
    reason = diagnose_deficit_reason(1, 1, 0, ctx)
    assert reason == "ZERO_QUALIFIED_STAFF"


# ==============================================================================
# 2. Floating vs Dedicated Shift Preference Challenge
# ==============================================================================

def test_floating_suppression_when_demand_and_preferences_conflict():
    """Adversarial test: 2 departments where workers have inverted preferred shifts and secondary eligibility.

    Even though swapping departments would fulfill each worker's preferred shift,
    the penalty hierarchy (float_rank2=5000 > dedicated_shift=2500) ensures neither worker floats.
    Total float count must be exactly 0.
    """
    d1 = Department(id=1, code="D1", name="Dept 1")
    d2 = Department(id=2, code="D2", name="Dept 2")
    morn = ShiftType(id=1, code="MORN", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    eve = ShiftType(id=2, code="EVE", start_time="15:00:00", end_time="23:30:00", duration_hours=8.5, min_rest_hours_after=14)

    # Worker 1 prefers MORN (Shift 1), Worker 2 prefers EVE (Shift 2)
    e1 = Employee(id=1, employee_code="E1", name="Alice", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=1)
    e2 = Employee(id=2, employee_code="E2", name="Bob", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=2)

    # Both workers have secondary floating eligibility in the other department
    eligs = {
        (1, 1): (1, True),
        (1, 2): (2, True),  # Alice can float to D2
        (2, 2): (1, True),
        (2, 1): (2, True),  # Bob can float to D1
    }

    # Inverted demand: D1 needs EVE (Shift 2), D2 needs MORN (Shift 1)
    # If Alice floats to D2: she gets MORN (her preferred shift), Bob floats to D1: he gets EVE (his preferred shift)
    # But floating penalty is 5000 vs dedicated shift deviation penalty 2500.
    # Therefore, both workers MUST remain in their home department.
    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d1, d2],
        shifts=[morn, eve],
        horizon_days=5,
        start_date=date(2026, 11, 1),
        demand_matrix={
            (1, 1, t): 0 for t in range(5)
        } | {
            (1, 2, t): 1 for t in range(5)
        } | {
            (2, 1, t): 1 for t in range(5)
        } | {
            (2, 2, t): 0 for t in range(5)
        },
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2,
    )

    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0

    floating_assignments = [a for a in res.assignments if a["is_floating"]]
    assert len(floating_assignments) == 0, f"Unnecessary floats detected: {floating_assignments}"

    # Verify workers stayed in home department
    for a in res.assignments:
        if a["employee_id"] == 1:
            assert a["department_id"] == 1
            assert a["shift_type_id"] == 2  # Worked EVE instead of floating
        elif a["employee_id"] == 2:
            assert a["department_id"] == 2
            assert a["shift_type_id"] == 1  # Worked MORN instead of floating


def test_floating_activates_when_genuine_shortage_occurs():
    """When a department has an actual staffing shortage due to leave, the floater MUST float."""
    d1 = Department(id=1, code="D1", name="Dept 1")
    d2 = Department(id=2, code="D2", name="Dept 2")
    morn = ShiftType(id=1, code="MORN", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)

    e1 = Employee(id=1, employee_code="E1", name="Alice", primary_department_id=1, max_hours_week=40.0)
    e2 = Employee(id=2, employee_code="E2", name="Bob", primary_department_id=2, max_hours_week=40.0)

    eligs = {
        (1, 1): (1, True),
        (2, 2): (1, True),
        (2, 1): (2, True),  # Bob can float to D1
    }

    # D1 needs 1 staff, D2 needs 0 staff. Alice is on leave.
    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d1, d2],
        shifts=[morn],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 1, (2, 1, 0): 0},
        eligibilities=eligs,
        preferences={},
        approved_leaves={(1, 0)},
        pinned_assignments={},
        pinned_offs=set(),
    )

    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0
    assert len(res.assignments) == 1
    assigned = res.assignments[0]
    assert assigned["employee_id"] == 2
    assert assigned["department_id"] == 1
    assert assigned["is_floating"] is True
    assert assigned["float_rank"] == 2


def test_floating_suppressed_across_all_variants():
    """Verify that BALANCED, FLOAT_AVERSE, and PREFERENCE_MAX variants all suppress unnecessary floating."""
    d1 = Department(id=1, code="D1", name="Dept 1")
    d2 = Department(id=2, code="D2", name="Dept 2")
    morn = ShiftType(id=1, code="MORN", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    eve = ShiftType(id=2, code="EVE", start_time="15:00:00", end_time="23:30:00", duration_hours=8.5, min_rest_hours_after=14)

    e1 = Employee(id=1, employee_code="E1", name="Alice", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=1)
    e2 = Employee(id=2, employee_code="E2", name="Bob", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=2)

    eligs = {
        (1, 1): (1, True),
        (1, 2): (2, True),
        (2, 2): (1, True),
        (2, 1): (2, True),
    }

    # Strong soft preferences aligning with preferred shifts
    prefs = {
        (1, 1, dow): 5 for dow in range(7)
    }
    prefs.update({
        (2, 2, dow): 5 for dow in range(7)
    })

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[d1, d2],
        shifts=[morn, eve],
        horizon_days=2,
        start_date=date(2026, 11, 1),
        demand_matrix={
            (1, 1, t): 0 for t in range(2)
        } | {
            (1, 2, t): 1 for t in range(2)
        } | {
            (2, 1, t): 1 for t in range(2)
        } | {
            (2, 2, t): 0 for t in range(2)
        },
        eligibilities=eligs,
        preferences=prefs,
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2,
    )

    variants = generate_roster_variants(ctx)
    assert len(variants) == 3
    for v in variants:
        assert v.status in ["OPTIMAL", "FEASIBLE"]
        floats = [a for a in v.assignments if a["is_floating"]]
        assert len(floats) == 0, f"Variant {v.strategy_name} had unexpected floating: {floats}"


# ==============================================================================
# 3. Night Shift Turnaround Ergonomics Challenge
# ==============================================================================

def test_night_to_night_turnaround_calculation():
    """Verify mathematical calculation: Night (23:00 to 07:30) with min_rest_hours_after=15."""
    night = ShiftType(id=1, code="NIGHT", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=15)
    rest_hrs = calculate_inter_shift_rest_hours(night, night)
    assert rest_hrs == 15.5
    assert is_transition_forbidden(night, night) is False


def test_night_to_morning_turnaround_calculation():
    """Verify mathematical calculation: Night (23:00 to 07:30) followed by Morning (07:00 to 15:30)."""
    night = ShiftType(id=1, code="NIGHT", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=15)
    morn = ShiftType(id=2, code="MORN", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    rest_hrs = calculate_inter_shift_rest_hours(night, morn)
    assert rest_hrs == -0.5
    assert is_transition_forbidden(night, morn) is True


def test_consecutive_night_shifts_solve_successfully():
    """CP-SAT solver must successfully schedule an employee for consecutive Night shifts."""
    dept = Department(id=1, code="ICU", name="ICU")
    night = ShiftType(id=1, code="NIGHT", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=15)
    emp = Employee(id=1, employee_code="E1", name="Night Specialist", primary_department_id=1, max_hours_week=40.0)

    # 4 consecutive nights
    ctx = SchedulingContext(
        employees=[emp],
        departments=[dept],
        shifts=[night],
        horizon_days=4,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, t): 1 for t in range(4)},
        eligibilities={(1, 1): (1, True)},
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2,
    )

    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0
    assert len(res.assignments) == 4
    for t, a in enumerate(res.assignments):
        assert a["day_idx"] == t
        assert a["shift_type_id"] == 1


def test_night_to_morning_transition_strictly_blocked_by_solver():
    """CP-SAT solver must refuse to schedule Night on day t followed by Morning on day t+1 for the same employee."""
    dept = Department(id=1, code="ICU", name="ICU")
    night = ShiftType(id=1, code="NIGHT", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=15)
    morn = ShiftType(id=2, code="MORN", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    emp = Employee(id=1, employee_code="E1", name="Lone Nurse", primary_department_id=1, max_hours_week=40.0)

    # Day 0 needs Night, Day 1 needs Morning. Only 1 worker available.
    ctx = SchedulingContext(
        employees=[emp],
        departments=[dept],
        shifts=[night, morn],
        horizon_days=2,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, 1, 0): 1, (1, 2, 0): 0, (1, 1, 1): 0, (1, 2, 1): 1},
        eligibilities={(1, 1): (1, True)},
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2,
    )

    res = solve_roster(ctx)
    assert res.status in ["OPTIMAL", "FEASIBLE"]

    # Exactly 1 assignment and 1 deficit (cannot fulfill both due to forbidden transition)
    assert len(res.assignments) == 1
    assert len(res.deficits) == 1
    assert res.deficits[0]["shortage_count"] == 1
    assert res.deficits[0]["reason_code"] == "EXHAUSTED_ELIGIBLE_STAFF"
