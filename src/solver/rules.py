"""Ergonomic labor rules and real-time validation engine for shift assignments."""
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

def time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM:SS' or 'HH:MM' to minutes since midnight."""
    parts = [int(p) for p in time_str.split(":")[:2]]
    return parts[0] * 60 + parts[1]

def calculate_inter_shift_rest_hours(shift1, shift2) -> float:
    """Calculate the rest interval in hours between shift1 on day t

    and shift2 on day t+1.
    """
    s1_start = time_to_minutes(shift1.start_time)
    s1_dur = int(shift1.duration_hours * 60)
    s1_end = s1_start + s1_dur

    s2_start = time_to_minutes(shift2.start_time)

    # Rest from s1_end on day t to s2_start on day t+1:
    # Day t has 1440 minutes.
    # Time remaining on day t after s1_end: (1440 - s1_end)
    # Time before s2_start on day t+1: s2_start
    rest_minutes = (1440 - s1_end) + s2_start
    return rest_minutes / 60.0

def is_transition_forbidden(shift1, shift2) -> bool:
    """Check if shift1 followed by shift2 on the next calendar day violates

    shift1's minimum rest hours requirement.
    """
    rest_hours = calculate_inter_shift_rest_hours(shift1, shift2)
    return rest_hours < shift1.min_rest_hours_after

def validate_assignment_candidate(
    employee,
    target_dept,
    target_shift,
    target_date: date,
    current_assignments: List[Any],
    leaves: List[Any],
    max_consecutive_days: int = 5,
    min_rest_days_per_week: int = 2
) -> Dict[str, Any]:
    """Dynamically evaluate assigning `employee` to `target_dept` on `target_shift` at `target_date`.

    Returns dictionary with `is_valid`, `can_override`, `violations`, and `warnings`.
    """
    violations = []
    warnings = []

    # 1. Check Approved Leaves
    for leave in leaves:
        if leave.employee_id == employee.id and leave.status == "APPROVED":
            if leave.start_date <= target_date <= leave.end_date:
                violations.append({
                    "code": "APPROVED_LEAVE_LOCKED",
                    "type": "HARD",
                    "message": f"{employee.name} is on approved {leave.leave_type} ({leave.start_date} to {leave.end_date})."
                })

    # 2. Check Department Eligibility
    elig_map = {elig.department_id: elig for elig in employee.eligibilities}
    if target_dept.id not in elig_map or not elig_map[target_dept.id].can_float:
        if employee.primary_department_id != target_dept.id:
            violations.append({
                "code": "INELIGIBLE_DEPARTMENT",
                "type": "HARD",
                "message": f"{employee.name} is not certified or eligible to work in {target_dept.name}."
            })
    else:
        rank = elig_map[target_dept.id].preference_rank
        if rank == 2:
            warnings.append({
                "code": "FLOAT_BACKUP",
                "message": f"Cross-department floating assignment: {employee.name} will float to {target_dept.name} (Rank 2 Backup)."
            })
        elif rank == 3:
            warnings.append({
                "code": "FLOAT_EMERGENCY",
                "message": f"Emergency floating assignment: {employee.name} will float to {target_dept.name} (Rank 3 Emergency Only)."
            })

    # Index existing assignments by date
    emp_assignments_by_date = {
        a.date: a for a in current_assignments
        if a.employee_id == employee.id and a.date != target_date
    }

    # 3. Rest Interval from Previous Day's Shift
    prev_date = target_date - timedelta(days=1)
    if prev_date in emp_assignments_by_date:
        prev_shift = emp_assignments_by_date[prev_date].shift_type
        rest_hrs = calculate_inter_shift_rest_hours(prev_shift, target_shift)
        if rest_hrs < prev_shift.min_rest_hours_after:
            violations.append({
                "code": "REST_INTERVAL_VIOLATION",
                "type": "HARD",
                "message": f"Insufficient rest: {employee.name} worked {prev_shift.name} on {prev_date} ({prev_shift.start_time}-{prev_shift.end_time}). Rest interval before {target_shift.name} ({target_shift.start_time}) is {rest_hrs:.1f} hrs (minimum required: {prev_shift.min_rest_hours_after} hrs)."
            })

    # 4. Rest Interval into Next Day's Shift
    next_date = target_date + timedelta(days=1)
    if next_date in emp_assignments_by_date:
        next_shift = emp_assignments_by_date[next_date].shift_type
        rest_hrs = calculate_inter_shift_rest_hours(target_shift, next_shift)
        if rest_hrs < target_shift.min_rest_hours_after:
            violations.append({
                "code": "REST_INTERVAL_VIOLATION",
                "type": "HARD",
                "message": f"Insufficient rest into next day: Proposed {target_shift.name} on {target_date} leaves only {rest_hrs:.1f} hrs before scheduled {next_shift.name} on {next_date} ({next_shift.start_time}) (minimum required: {target_shift.min_rest_hours_after} hrs)."
            })

    # 5. Consecutive Working Days Limit
    # Build a simulated streak including target_date
    worked_dates = set(emp_assignments_by_date.keys())
    worked_dates.add(target_date)

    # Check forward and backward contiguous streaks
    streak = 1
    curr = target_date - timedelta(days=1)
    while curr in worked_dates:
        streak += 1
        curr -= timedelta(days=1)
    curr = target_date + timedelta(days=1)
    while curr in worked_dates:
        streak += 1
        curr += timedelta(days=1)

    if streak > max_consecutive_days:
        violations.append({
            "code": "MAX_CONSECUTIVE_DAYS",
            "type": "HARD",
            "message": f"Consecutive working streak violation: Assigning this shift results in {streak} consecutive days worked (maximum allowed: {max_consecutive_days})."
        })

    # 6. Rolling 7-day Rest Days Requirement
    # In any 7-day window containing target_date, shifts worked cannot exceed 7 - min_rest_days_per_week
    max_worked_per_week = 7 - min_rest_days_per_week
    for offset in range(-6, 1):
        window_start = target_date + timedelta(days=offset)
        window_days = [window_start + timedelta(days=k) for k in range(7)]
        count = sum(1 for d in window_days if d in worked_dates)
        if count > max_worked_per_week:
            violations.append({
                "code": "ROLLING_REST_VIOLATION",
                "type": "HARD",
                "message": f"Rolling 7-day rest violation in window {window_start} to {window_start + timedelta(days=6)}: {count} shifts worked (maximum allowed: {max_worked_per_week}, requiring at least {min_rest_days_per_week} days off)."
            })
            break

    is_valid = len(violations) == 0
    return {
        "is_valid": is_valid,
        "can_override": True,  # Managers can force-override if desired
        "violations": violations,
        "warnings": warnings
    }
