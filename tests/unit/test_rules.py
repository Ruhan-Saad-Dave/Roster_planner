"""Unit tests for ergonomic rest calculations and real-time candidate validation."""
from datetime import date, timedelta
from src.solver.rules import calculate_inter_shift_rest_hours, is_transition_forbidden, validate_assignment_candidate
from src.db.models import ShiftType, Department, Employee, EmployeeDepartmentEligibility, RosterAssignment

def test_forbidden_transition_night_to_morning():
    # Morning: 07:00 to 15:30
    morn = ShiftType(code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    # Night: 23:00 to 07:30 (crosses midnight)
    night = ShiftType(code="NIGHT", name="Night", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=16)

    # Night on day t ends at 07:30 on day t+1.
    # Morning on day t+1 starts at 07:00 on day t+1.
    # Inter-shift rest interval is -0.5 hours!
    rest = calculate_inter_shift_rest_hours(night, morn)
    assert rest < 1.0
    assert is_transition_forbidden(night, morn) is True

def test_permitted_transition_morning_to_night():
    morn = ShiftType(code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    night = ShiftType(code="NIGHT", name="Night", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=16)

    # Morning on day t ends 15:30.
    # Night on day t+1 starts 23:00.
    # Rest is 8.5 hours on day t + 23.0 hours on day t+1 = 31.5 hours > 14.
    rest = calculate_inter_shift_rest_hours(morn, night)
    assert rest >= 14.0
    assert is_transition_forbidden(morn, night) is False

def test_consecutive_days_violation():
    dept = Department(id=1, code="ICU", name="ICU")
    shift = ShiftType(id=1, code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14)
    emp = Employee(id=10, employee_code="EMP10", name="Sarah", primary_department_id=1, max_hours_week=40.0)
    emp.eligibilities = [EmployeeDepartmentEligibility(employee_id=10, department_id=1, preference_rank=1, can_float=True)]

    # Employee already worked 5 consecutive days: Nov 1 to Nov 5
    assignments = []
    base_d = date(2026, 11, 1)
    for i in range(5):
        a = RosterAssignment(plan_id=1, employee_id=10, department_id=1, shift_type_id=1, date=base_d + timedelta(days=i))
        a.shift_type = shift
        assignments.append(a)

    # Attempt to assign Day 6 (Nov 6)
    target_date = base_d + timedelta(days=5)
    res = validate_assignment_candidate(emp, dept, shift, target_date, assignments, [], max_consecutive_days=5)

    assert res["is_valid"] is False
    assert any(v["code"] == "MAX_CONSECUTIVE_DAYS" for v in res["violations"])
