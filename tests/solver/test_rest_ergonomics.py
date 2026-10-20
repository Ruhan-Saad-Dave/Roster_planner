"""Solver test: Ergonomic labor rules and forward-only shift rotation invariants."""
from datetime import date
from src.solver.model import SchedulingContext
from src.solver.engine import solve_roster
from src.db.models import Department, ShiftType, Employee

def test_ergonomic_rest_and_rotation_invariants():
    dept = Department(id=1, code="ICU", name="ICU")

    morn = ShiftType(id=1, code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    night = ShiftType(id=2, code="NIGHT", name="Night", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=16, is_night_shift=True)

    # 4 employees over 14 days
    employees = [
        Employee(id=i, employee_code=f"EMP{i}", name=f"Staff {i}", primary_department_id=1, max_hours_week=40.0)
        for i in range(1, 5)
    ]

    demand = {}
    for s in [1, 2]:
        for t in range(14):
            demand[(1, s, t)] = 1

    eligibilities = {(e.id, 1): (1, True) for e in employees}

    ctx = SchedulingContext(
        employees=employees,
        departments=[dept],
        shifts=[morn, night],
        horizon_days=14,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligibilities,
        preferences={},
        approved_leaves=set(),
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=2
    )

    res = solve_roster(ctx, timeout_seconds=10)
    assert res.status in ["OPTIMAL", "FEASIBLE"]

    # Verify Invariant 1: No employee works Night on day t followed by Morning on day t+1
    assignments_by_emp = {}
    for a in res.assignments:
        assignments_by_emp.setdefault((a["employee_id"], a["day_idx"]), a["shift_type_id"])

    for e in employees:
        for t in range(13):
            shift_today = assignments_by_emp.get((e.id, t))
            shift_tomorrow = assignments_by_emp.get((e.id, t + 1))
            if shift_today == 2:  # Night
                assert shift_tomorrow != 1, f"Ergonomic breach: Employee {e.id} assigned Morning right after Night at t={t}!"

    # Verify Invariant 2: Rolling 7-day window rest days
    for e in employees:
        for t in range(8):
            window_worked = sum(1 for k in range(7) if (e.id, t + k) in assignments_by_emp)
            assert window_worked <= 5, f"Rolling rest breach: Employee {e.id} worked {window_worked} shifts in 7 days starting at t={t}!"
