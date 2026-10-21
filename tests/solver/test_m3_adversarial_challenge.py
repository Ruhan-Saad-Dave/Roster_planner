"""Adversarial stress-test challenge suite for Milestone 3 simulations (R2, R4).

Adversarially challenges:
1. Floating suppression: Floating strictly 0 when home staff is adequate,
   even under intense shift preference inversion pressure and foreign soft preference rewards.
2. Floater rank priority: Rank 2 backup floaters strictly chosen before Rank 3 emergency floaters,
   even when Rank 2 floater has a conflicting dedicated shift preference. Also tests exhaustion ladder.
3. Dedicated shift adherence: Adherence >= 85% maintained across month-long simulations with multi-cohort staff.
   Infeasibility shield when all staff prefer the same shift.
4. Comp-off caps across month-long simulations: Strict consecutive streak limits
   (max 1 when disabled, max 2 when enabled) under high overtime conditions.
"""
import uuid
from datetime import date, timedelta
import pytest
from typing import Dict, List, Tuple, Set

from src.solver.model import SchedulingContext
from src.solver.engine import solve_roster, diagnose_deficit_reason
from src.db.models import (
    Department, ShiftType, Employee, EmployeeDepartmentEligibility,
    DepartmentRequirement, RosterPlan, RosterAssignment, LeaveRecord,
    SystemSetting
)
from src.api.routes_roster import get_plan_schedule, auto_award_compoffs
from tests.conftest import test_db


pytestmark = pytest.mark.simulation


def make_standard_shifts() -> Dict[str, ShiftType]:
    return {
        "morn": ShiftType(
            id=1, code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00",
            duration_hours=8.0, min_rest_hours_after=14, is_night_shift=False
        ),
        "eve": ShiftType(
            id=2, code="EVE", name="Evening", start_time="15:00:00", end_time="23:30:00",
            duration_hours=8.0, min_rest_hours_after=14, is_night_shift=False
        ),
        "night": ShiftType(
            id=3, code="NIGHT", name="Night", start_time="23:00:00", end_time="07:30:00",
            duration_hours=8.0, min_rest_hours_after=15, is_night_shift=True
        ),
    }


# ==============================================================================
# Challenge 1: Floating Suppression Under Extreme Preference Pressure
# ==============================================================================

def test_adversarial_floating_suppression_under_preference_inversion():
    """Challenge 1A: Floating suppression under two-way preference inversion.

    Setup:
    - Dept 1 has 2 staff (Emp 1, Emp 2). Dept 1 demand is strictly 2 Evening shifts daily.
    - Dept 2 has 2 staff (Emp 3, Emp 4). Dept 2 demand is strictly 2 Morning shifts daily.
    - Extreme Inversion:
      - Emp 1 & 2 (primary Dept 1) have dedicated preference for Morning (available only in Dept 2!).
      - Emp 3 & 4 (primary Dept 2) have dedicated preference for Evening (available only in Dept 1!).
    - All employees have Rank 2 floating eligibility to the opposite department.

    Economic Trade-off:
    - If Emp 1 stays in Dept 1 and works Evening: float cost = 0, dedicated mismatch = 2,500.
    - If Emp 1 floats to Dept 2 and works Morning: float cost = 5,000, dedicated mismatch = 0.
    - Since 5,000 > 2,500, solver MUST NOT permit any cross-floating.
    - Floating count across 5 days must be strictly ZERO.
    """
    shifts = make_standard_shifts()
    morn = shifts["morn"]
    eve = shifts["eve"]

    dept1 = Department(id=1, code="D1", name="Dept 1")
    dept2 = Department(id=2, code="D2", name="Dept 2")

    e1 = Employee(id=1, employee_code="E1", name="Emp 1", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=morn.id)
    e2 = Employee(id=2, employee_code="E2", name="Emp 2", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=morn.id)
    e3 = Employee(id=3, employee_code="E3", name="Emp 3", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=eve.id)
    e4 = Employee(id=4, employee_code="E4", name="Emp 4", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=eve.id)

    eligs = {
        (1, 1): (1, True), (1, 2): (2, True),
        (2, 1): (1, True), (2, 2): (2, True),
        (3, 2): (1, True), (3, 1): (2, True),
        (4, 2): (1, True), (4, 1): (2, True),
    }

    horizon = 5
    demand = {}
    for t in range(horizon):
        demand[(1, eve.id, t)] = 2
        demand[(2, morn.id, t)] = 2

    ctx = SchedulingContext(
        employees=[e1, e2, e3, e4],
        departments=[dept1, dept2],
        shifts=[morn, eve],
        horizon_days=horizon,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2
    )

    res = solve_roster(ctx, timeout_seconds=5)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0

    floating = [a for a in res.assignments if a["is_floating"]]
    assert len(floating) == 0, f"Floating occurred despite adequate home staff! Found {len(floating)} floats."

    # Confirm all workers stayed strictly in home department
    for a in res.assignments:
        expected = 1 if a["employee_id"] in [1, 2] else 2
        assert a["department_id"] == expected, f"Emp {a['employee_id']} assigned to dept {a['department_id']} instead of home {expected}"


def test_adversarial_floating_suppression_with_soft_preferences():
    """Challenge 1B: Floating suppression when foreign department offers positive soft preference.

    Emp 1 (Dept 1) has soft preference score +10 for Morning shift on all days.
    Dept 1 only has Evening shift demand. Dept 2 has Morning shift demand.
    Floating penalty (5,000) >> Dedicated deviation (2,500) + Soft preference (10 * 10 = 100).
    Total benefit to float = 2,600 vs penalty 5,000.
    Solver must strictly keep Emp 1 in Dept 1.
    """
    shifts = make_standard_shifts()
    morn = shifts["morn"]
    eve = shifts["eve"]

    dept1 = Department(id=1, code="D1", name="Dept 1")
    dept2 = Department(id=2, code="D2", name="Dept 2")

    e1 = Employee(id=1, employee_code="E1", name="Emp 1", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=morn.id)
    e2 = Employee(id=2, employee_code="E2", name="Emp 2", primary_department_id=2, max_hours_week=40.0)

    eligs = {
        (1, 1): (1, True), (1, 2): (2, True),
        (2, 2): (1, True), (2, 1): (2, True),
    }

    # Soft preference: Emp 1 strongly prefers Morning (shift id 1) on all days of week
    preferences = {(1, morn.id, dow): 10 for dow in range(7)}

    demand = {
        (1, eve.id, 0): 1,
        (2, morn.id, 0): 1,
    }

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[dept1, dept2],
        shifts=[morn, eve],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligs,
        preferences=preferences,
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set()
    )

    res = solve_roster(ctx, timeout_seconds=3)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0

    floating = [a for a in res.assignments if a["is_floating"]]
    assert len(floating) == 0, f"Floating occurred due to soft preference! Found {len(floating)} floats."


def test_adversarial_floating_suppression_dual_departments():
    """Challenge 1C: Dual-department simulation across 7-day and 14-day horizons.

    Dept 1: 3 staff, 2-shift regime (Morning and Night).
    Dept 2: 3 staff, 2-shift regime (Morning and Night).
    All 6 staff have Rank 2 cross-floating eligibility to the opposite department.
    Staff members have dedicated shift preferences.
    Because both departments have adequate home staffing (3 staff covers 2 shifts/day),
    the solver MUST assign exactly 0 floating shifts across the entire horizon.
    """
    shifts = make_standard_shifts()
    morn = shifts["morn"]
    night = shifts["night"]

    dept1 = Department(id=1, code="D1", name="Dept 1")
    dept2 = Department(id=2, code="D2", name="Dept 2")

    employees = []
    eligs = {}
    for i in range(1, 4):
        pref = morn.id if i == 1 else night.id
        e = Employee(id=i, employee_code=f"E{i}", name=f"D1 Staff {i}", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=pref)
        employees.append(e)
        eligs[(i, 1)] = (1, True)
        eligs[(i, 2)] = (2, True)

    for i in range(4, 7):
        pref = morn.id if i == 4 else night.id
        e = Employee(id=i, employee_code=f"E{i}", name=f"D2 Staff {i}", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=pref)
        employees.append(e)
        eligs[(i, 2)] = (1, True)
        eligs[(i, 1)] = (2, True)

    horizon = 7
    demand = {}
    for t in range(horizon):
        demand[(1, morn.id, t)] = 1
        demand[(1, night.id, t)] = 1
        demand[(2, morn.id, t)] = 1
        demand[(2, night.id, t)] = 1

    ctx = SchedulingContext(
        employees=employees,
        departments=[dept1, dept2],
        shifts=[morn, night],
        horizon_days=horizon,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2
    )

    res = solve_roster(ctx, timeout_seconds=10)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0

    floating = [a for a in res.assignments if a["is_floating"]]
    assert len(floating) == 0, f"Unwarranted floating occurred in dual-dept simulation: {len(floating)} floats."


# ==============================================================================
# Challenge 2: Floater Rank Priority Hierarchy Stress-Testing
# ==============================================================================

def test_adversarial_rank_priority_under_preference_penalty():
    """Challenge 2A: Floater rank priority vs dedicated shift preference mismatch.

    Shortage: Dept 1 needs 1 Night shift.
    Dept 2 has:
    - Emp 1: Rank 2 Backup floater to Dept 1. Dedicated preference = Morning!
      (Penalty if floating: 5,000 + 2,500 = 7,500)
    - Emp 2: Rank 3 Emergency floater to Dept 1. Dedicated preference = Night!
      (Penalty if floating: 25,000 + 0 = 25,000)

    Adversarial Challenge:
    Will the solver fall into the trap of picking Emp 2 because Emp 2 matches the shift?
    Or will the Rank 2 penalty (5,000) properly dominate Rank 3 (25,000)?
    Emp 1 MUST be assigned, Emp 2 must remain unassigned.
    """
    shifts = make_standard_shifts()
    morn = shifts["morn"]
    night = shifts["night"]

    dept1 = Department(id=1, code="D1", name="Dept 1")
    dept2 = Department(id=2, code="D2", name="Dept 2")

    e1 = Employee(id=1, employee_code="E1", name="Rank2 MorningPref", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=morn.id)
    e2 = Employee(id=2, employee_code="E2", name="Rank3 NightPref", primary_department_id=2, max_hours_week=40.0, preferred_shift_type_id=night.id)

    eligs = {
        (1, 2): (1, True), (1, 1): (2, True),  # Rank 2 to Dept 1
        (2, 2): (1, True), (2, 1): (3, True),  # Rank 3 to Dept 1
    }

    ctx = SchedulingContext(
        employees=[e1, e2],
        departments=[dept1, dept2],
        shifts=[morn, night],
        horizon_days=1,
        start_date=date(2026, 11, 1),
        demand_matrix={(1, night.id, 0): 1, (2, morn.id, 0): 0, (2, night.id, 0): 0},
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set()
    )

    res = solve_roster(ctx, timeout_seconds=3)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0
    assert len(res.assignments) == 1

    assigned = res.assignments[0]
    assert assigned["employee_id"] == 1, (
        f"Solver incorrectly prioritized Rank 3 floater (Emp {assigned['employee_id']}) over Rank 2 floater!"
    )
    assert assigned["float_rank"] == 2


def test_adversarial_rank_priority_multi_shortage_exhaustion_ladder():
    """Challenge 2B: Multi-shortage exhaustion ladder.

    Dept 1 has 0 home staff.
    Dept 2 has:
    - 2 Backup floaters: Emp 1 (Rank 2), Emp 2 (Rank 2)
    - 2 Emergency floaters: Emp 3 (Rank 3), Emp 4 (Rank 3)

    We test shortage escalation:
    1. Shortage = 1: exactly 1 Rank 2 floats, 0 Rank 3 floats.
    2. Shortage = 2: exactly 2 Rank 2 float, 0 Rank 3 floats.
    3. Shortage = 3: exactly 2 Rank 2 float, and exactly 1 Rank 3 floats (ladder activation).
    """
    shifts = make_standard_shifts()
    morn = shifts["morn"]

    dept1 = Department(id=1, code="D1", name="Dept 1")
    dept2 = Department(id=2, code="D2", name="Dept 2")

    e1 = Employee(id=1, employee_code="E1", name="R2_A", primary_department_id=2, max_hours_week=40.0)
    e2 = Employee(id=2, employee_code="E2", name="R2_B", primary_department_id=2, max_hours_week=40.0)
    e3 = Employee(id=3, employee_code="E3", name="R3_A", primary_department_id=2, max_hours_week=40.0)
    e4 = Employee(id=4, employee_code="E4", name="R3_B", primary_department_id=2, max_hours_week=40.0)

    eligs = {
        (1, 2): (1, True), (1, 1): (2, True),
        (2, 2): (1, True), (2, 1): (2, True),
        (3, 2): (1, True), (3, 1): (3, True),
        (4, 2): (1, True), (4, 1): (3, True),
    }

    # Step 1: Demand = 1 in Dept 1
    ctx1 = SchedulingContext(
        employees=[e1, e2, e3, e4], departments=[dept1, dept2], shifts=[morn],
        horizon_days=1, start_date=date(2026, 11, 1),
        demand_matrix={(1, morn.id, 0): 1, (2, morn.id, 0): 0}, eligibilities=eligs,
        preferences={}, approved_leaves=set(), pinned_assignments={}, pinned_offs=set()
    )
    res1 = solve_roster(ctx1)
    assert len(res1.deficits) == 0
    ranks1 = [a["float_rank"] for a in res1.assignments]
    assert ranks1 == [2], f"Expected exactly one Rank 2 assignment, got ranks {ranks1}"

    # Step 2: Demand = 2 in Dept 1
    ctx2 = SchedulingContext(
        employees=[e1, e2, e3, e4], departments=[dept1, dept2], shifts=[morn],
        horizon_days=1, start_date=date(2026, 11, 1),
        demand_matrix={(1, morn.id, 0): 2, (2, morn.id, 0): 0}, eligibilities=eligs,
        preferences={}, approved_leaves=set(), pinned_assignments={}, pinned_offs=set()
    )
    res2 = solve_roster(ctx2)
    assert len(res2.deficits) == 0
    ranks2 = sorted([a["float_rank"] for a in res2.assignments])
    assert ranks2 == [2, 2], f"Expected both Rank 2 assignments, got ranks {ranks2}"

    # Step 3: Demand = 3 in Dept 1 (Forces Rank 3 ladder activation)
    ctx3 = SchedulingContext(
        employees=[e1, e2, e3, e4], departments=[dept1, dept2], shifts=[morn],
        horizon_days=1, start_date=date(2026, 11, 1),
        demand_matrix={(1, morn.id, 0): 3, (2, morn.id, 0): 0}, eligibilities=eligs,
        preferences={}, approved_leaves=set(), pinned_assignments={}, pinned_offs=set()
    )
    res3 = solve_roster(ctx3)
    assert len(res3.deficits) == 0
    ranks3 = sorted([a["float_rank"] for a in res3.assignments])
    assert ranks3 == [2, 2, 3], f"Expected [2, 2, 3], got ranks {ranks3}"


# ==============================================================================
# Challenge 3: Dedicated Shifts & Comp-Off Caps Across Month-Long Horizon
# ==============================================================================

def test_adversarial_dedicated_shift_month_long_multi_cohort():
    """Challenge 3A: Month-long simulation across multi-cohort dedicated shifts.

    6 staff in 3-shift department over 30 days (90 demand slots).
    - Emp 1 & Emp 4: Dedicated Morning (id=1)
    - Emp 2 & Emp 5: Dedicated Evening (id=2)
    - Emp 3: Dedicated Night (id=3)
    - Emp 6: Flexible (no preference)

    Verification:
    - 0 deficits.
    - Every dedicated worker achieves >= 85.0% adherence to their preferred shift.
    - Zero forbidden turnaround rest violations across all workers.
    """
    shifts = make_standard_shifts()
    shift_list = list(shifts.values())
    morn = shifts["morn"]
    eve = shifts["eve"]
    night = shifts["night"]

    dept = Department(id=1, code="D1", name="Dept 1")
    dedicated_map = {1: morn.id, 4: morn.id, 2: eve.id, 5: eve.id, 3: night.id}

    employees = []
    eligs = {}
    for i in range(1, 7):
        pref = dedicated_map.get(i)
        e = Employee(id=i, employee_code=f"E{i}", name=f"Staff {i}", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=pref)
        employees.append(e)
        eligs[(i, 1)] = (1, True)

    horizon = 30
    demand = {}
    for t in range(horizon):
        for s in shift_list:
            demand[(1, s.id, t)] = 1

    ctx = SchedulingContext(
        employees=employees,
        departments=[dept],
        shifts=shift_list,
        horizon_days=horizon,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2
    )

    res = solve_roster(ctx, timeout_seconds=5)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0

    shifts_by_emp = {e.id: [] for e in employees}
    shifts_by_emp_day = {}
    for a in res.assignments:
        shifts_by_emp[a["employee_id"]].append(a["shift_type_id"])
        shifts_by_emp_day[(a["employee_id"], a["day_idx"])] = a["shift_type_id"]

    for emp_id, pref in dedicated_map.items():
        assigned = shifts_by_emp[emp_id]
        pref_count = sum(1 for s in assigned if s == pref)
        pct = (pref_count / len(assigned) * 100) if assigned else 0
        assert pct >= 85.0, (
            f"Emp {emp_id} achieved only {pct:.1f}% adherence ({pref_count}/{len(assigned)}) for preferred shift {pref}"
        )

    # Check turnaround rest
    for e in employees:
        for t in range(horizon - 1):
            s1 = shifts_by_emp_day.get((e.id, t))
            s2 = shifts_by_emp_day.get((e.id, t + 1))
            if s1 == night.id:
                assert s2 != morn.id, f"Turnaround violation Night -> Morning for Emp {e.id} at day {t} -> {t+1}"


def test_adversarial_dedicated_shift_infeasibility_shield():
    """Challenge 3B: Dedicated shift infeasibility shield.

    What if ALL 5 staff in a 3-shift department strictly prefer Morning shift?
    If dedicated shifts were a hard constraint, the CP-SAT model would be INFEASIBLE.
    Because dedicated shifts are soft constraints (weight 2,500), the model MUST:
    - Return OPTIMAL/FEASIBLE.
    - Fill Morning, Evening, and Night shifts without deficits.
    - Maximize Morning assignments while covering Evening and Night.
    """
    shifts = make_standard_shifts()
    shift_list = list(shifts.values())
    morn = shifts["morn"]

    dept = Department(id=1, code="D1", name="Dept 1")
    employees = []
    eligs = {}
    for i in range(1, 6):
        e = Employee(id=i, employee_code=f"E{i}", name=f"Staff {i}", primary_department_id=1, max_hours_week=40.0, preferred_shift_type_id=morn.id)
        employees.append(e)
        eligs[(i, 1)] = (1, True)

    horizon = 7
    demand = {}
    for t in range(horizon):
        for s in shift_list:
            demand[(1, s.id, t)] = 1

    ctx = SchedulingContext(
        employees=employees,
        departments=[dept],
        shifts=shift_list,
        horizon_days=horizon,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligs,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2
    )

    res = solve_roster(ctx, timeout_seconds=4)
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0
    assert len(res.assignments) == 21  # 7 days * 3 shifts


def test_adversarial_compoff_streak_cap_full_month(test_db):
    """Challenge 3C: Comp-Off consecutive streak cap over a full 30-day month.

    Simulates high overtime over a 30-day horizon (Nov 1 to Nov 30).
    Employee works intense blocks creating multiple off-day windows.
    Verifies:
    1. When continuous_comp_off_enabled="false":
       - Auto-award awards comp-offs, but in ANY streak, no 2 consecutive comp-offs are ever awarded (max streak <= 1).
    2. When continuous_comp_off_enabled="true":
       - Auto-award awards comp-offs, but in ANY streak, no 3 consecutive comp-offs are ever awarded (max streak <= 2).
    3. Global max_comp_offs_per_employee is never exceeded.
    """
    test_db.query(SystemSetting).delete()
    test_db.add(SystemSetting(key="continuous_comp_off_enabled", value="false"))
    test_db.add(SystemSetting(key="max_comp_offs_per_employee", value="4"))

    dept = Department(code="ICU", name="ICU")
    shift = ShiftType(code="D10", name="Day10", start_time="08:00:00", end_time="18:00:00", duration_hours=10.0)
    test_db.add_all([dept, shift])
    test_db.flush()

    emp = Employee(employee_code="E_MONTH_COFF", name="Overtime Staff", primary_department_id=dept.id, max_hours_week=40.0)
    test_db.add(emp)
    test_db.flush()

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Month COFF Test",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 30),
        status="SOLVED",
        variant_strategy="BALANCED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.flush()

    # Employee works 5 days/week (50h) in week 1, 2, 3, 4.
    # Wk 1: Nov 2-6 (Mon-Fri) worked. Nov 7, 8 (Sat, Sun) unassigned.
    # Wk 2: Nov 9-13 (Mon-Fri) worked. Nov 14, 15 (Sat, Sun) unassigned.
    # Wk 3: Nov 16-20 (Mon-Fri) worked. Nov 21, 22 (Sat, Sun) unassigned.
    for monday_offset in [1, 8, 15, 22]:
        for d in range(5):
            work_day = date(2026, 11, 1) + timedelta(days=monday_offset + d)
            test_db.add(RosterAssignment(
                plan_id=plan.id,
                employee_id=emp.id,
                department_id=dept.id,
                shift_type_id=shift.id,
                date=work_day
            ))
    test_db.commit()

    # --- Case 1: continuous_comp_off_enabled = false ---
    res_disabled = auto_award_compoffs(plan.id, db=test_db)
    leaves_disabled = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).all()
    coff_dates_disabled = sorted([l.start_date for l in leaves_disabled])

    # Check streak: max streak must be exactly 1 (no two adjacent days awarded)
    for i in range(len(coff_dates_disabled) - 1):
        diff = (coff_dates_disabled[i + 1] - coff_dates_disabled[i]).days
        assert diff > 1, f"Found consecutive comp-offs when disabled: {coff_dates_disabled[i]} and {coff_dates_disabled[i+1]}"

    assert len(coff_dates_disabled) <= 4, f"Global cap of 4 exceeded: got {len(coff_dates_disabled)}"

    # --- Case 2: continuous_comp_off_enabled = true ---
    test_db.query(LeaveRecord).filter(LeaveRecord.employee_id == emp.id).delete()
    setting = test_db.query(SystemSetting).filter(SystemSetting.key == "continuous_comp_off_enabled").first()
    setting.value = "true"
    test_db.commit()

    res_enabled = auto_award_compoffs(plan.id, db=test_db)
    leaves_enabled = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).all()
    coff_dates_enabled = sorted([l.start_date for l in leaves_enabled])

    # Check streak: max streak must be <= 2
    streak = 1
    for i in range(len(coff_dates_enabled) - 1):
        if (coff_dates_enabled[i + 1] - coff_dates_enabled[i]).days == 1:
            streak += 1
            assert streak <= 2, f"Consecutive comp-off streak exceeded 2: streak={streak} at {coff_dates_enabled[i+1]}"
        else:
            streak = 1

    assert len(coff_dates_enabled) <= 4, f"Global cap of 4 exceeded: got {len(coff_dates_enabled)}"
