"""Solver test: Understaffing slack variables absorb shortages and prevent INFEASIBLE crash."""
from datetime import date
from src.solver.model import SchedulingContext
from src.solver.engine import solve_roster
from src.db.models import Department, ShiftType, Employee

def test_extreme_workforce_starvation():
    # 2 departments, 2 shifts, 7 days = 28 demand slots
    d1 = Department(id=1, code="D1", name="Dept 1")
    d2 = Department(id=2, code="D2", name="Dept 2")
    s1 = ShiftType(id=1, code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.0, min_rest_hours_after=14)
    s2 = ShiftType(id=2, code="NIGHT", name="Night", start_time="23:00:00", end_time="07:00:00", duration_hours=8.0, min_rest_hours_after=16, is_night_shift=True)

    # Only 1 single employee available in total!
    e1 = Employee(id=1, employee_code="EMP1", name="Lone Worker", primary_department_id=1, max_hours_week=40.0)

    # Demand: 1 staff on every shift in every department for 7 days (28 total slots)
    demand = {}
    for d in [1, 2]:
        for s in [1, 2]:
            for t in range(7):
                demand[(d, s, t)] = 1

    eligibilities = {
        (1, 1): (1, True),
        (1, 2): (2, True)  # Can float
    }

    ctx = SchedulingContext(
        employees=[e1],
        departments=[d1, d2],
        shifts=[s1, s2],
        horizon_days=7,
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

    # Assert Infeasibility Shield holds
    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) > 0
    # Employee cannot work more than 5 days in a 7-day week (mandatory 2 days off)
    assert len(res.assignments) <= 5

    # Sum of assignments + sum of deficits must equal total demand (28)
    total_assigned = len(res.assignments)
    total_deficit = sum(d["shortage_count"] for d in res.deficits)
    assert total_assigned + total_deficit == 28
