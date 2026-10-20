"""Solver test: Cross-department floating dynamically absorbs staffing shortages caused by leave."""
from datetime import date
from src.solver.model import SchedulingContext
from src.solver.engine import solve_roster
from src.db.models import Department, ShiftType, Employee

def test_vacation_absorption_via_floating():
    dept_a = Department(id=1, code="ICU", name="ICU")
    dept_b = Department(id=2, code="ER", name="ER")

    shift_day = ShiftType(id=1, code="DAY", name="Day Shift", start_time="08:00:00", end_time="16:00:00", duration_hours=8.0, min_rest_hours_after=14)

    # Dept A has 1 worker: emp_a
    # Dept B has 2 workers: emp_b1, emp_b2
    emp_a = Employee(id=1, employee_code="EMP_A", name="Alice (ICU)", primary_department_id=1, max_hours_week=40.0)
    emp_b1 = Employee(id=2, employee_code="EMP_B1", name="Bob (ER Floater)", primary_department_id=2, max_hours_week=40.0)
    emp_b2 = Employee(id=3, employee_code="EMP_B2", name="Charlie (ER)", primary_department_id=2, max_hours_week=40.0)

    # 3-day horizon
    demand = {}
    for t in range(3):
        demand[(1, 1, t)] = 1  # ICU needs 1
        demand[(2, 1, t)] = 1  # ER needs 1

    # Eligibilities:
    # Alice: ICU only (Rank 1)
    # Bob: ER (Rank 1), ICU (Rank 2 Floater)
    # Charlie: ER only (Rank 1)
    eligibilities = {
        (1, 1): (1, True),
        (2, 2): (1, True),
        (2, 1): (2, True),  # Bob can float to ICU
        (3, 2): (1, True),
    }

    # Scenario: Alice is on approved leave for all 3 days (t=0, 1, 2)
    leaves = {(1, 0), (1, 1), (1, 2)}

    ctx = SchedulingContext(
        employees=[emp_a, emp_b1, emp_b2],
        departments=[dept_a, dept_b],
        shifts=[shift_day],
        horizon_days=3,
        start_date=date(2026, 11, 1),
        demand_matrix=demand,
        eligibilities=eligibilities,
        preferences={},
        approved_leaves=leaves,
        pinned_assignments={},
        pinned_offs=set(),
        max_consecutive_days=5,
        min_rest_days_per_week=1
    )

    res = solve_roster(ctx, timeout_seconds=10)

    assert res.status in ["OPTIMAL", "FEASIBLE"]
    assert len(res.deficits) == 0  # Zero deficits because Bob floats to cover ICU!

    # Verify Bob floated to ICU
    bob_floated = any(a["employee_id"] == 2 and a["department_id"] == 1 and a["is_floating"] for a in res.assignments)
    assert bob_floated is True

    # Alice has 0 worked shifts
    alice_worked = any(a["employee_id"] == 1 for a in res.assignments)
    assert alice_worked is False
