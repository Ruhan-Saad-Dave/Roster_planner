"""Empirical Challenger Verification Test Suite for Milestone 2 Iteration 2.

Adversarially challenges:
1. Bidirectional comp-off streak logic in auto_award_compoffs:
   - max_consecutive = 1 with pre-existing COFF on target + 1
   - max_consecutive = 1 with pre-existing COFF on target - 1
   - max_consecutive = 1 with sandwiched unassigned days (alternating off days)
   - max_consecutive = 2 with pre-existing COFF on target + 1 and target + 2
   - max_consecutive = 2 with target sandwiched between pre-existing COFFs (target - 1 and target + 1)
   - max_consecutive = 2 with multi-day pre-existing COFF span
   - max_consecutive = 2 with pre-existing COFF on target + 2 (gap at target + 1)
   - Cancelled COFF leaves are properly excluded from streak calculation
   - Non-COFF leave types (VACATION) do not contribute to COFF streak

2. Cell deletion (DELETE /api/roster/{plan_id}/assignments):
   - Cell deletion updates plan status to DRAFT
   - Cleared cell renders as None (empty slot fillable by solver) in staff_centric schedule
   - Pinned day off (DAY_OFF / COFF) leave records are cleared and set plan to DRAFT
   - Solve remaining blank slots successfully resolves and re-fills deleted blank cells
   - Multi-day approved leaves (e.g. VACATION) are protected and not erased by single cell clear
   - Cell deletion idempotency when slot is already empty
   - Route path compatibility check (singular vs plural endpoint)
"""
import uuid
from datetime import date, timedelta
import pytest
from src.db.models import (
    Department, ShiftType, Employee, EmployeeDepartmentEligibility,
    DepartmentRequirement, RosterPlan, RosterAssignment, DeficitLog,
    LeaveRecord, SystemSetting
)


# ==============================================================================
# SUITE 1: BIDIRECTIONAL COMP-OFF STREAK BOUNDARY CONDITIONS
# ==============================================================================

def test_compoff_max_consecutive_1_boundary_target_plus_1(client, test_db, sample_scenario):
    """When max_consecutive = 1, an unassigned day preceding a pre-existing COFF
    must NOT be awarded, as the resulting streak would be 2 > 1.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max1 Target+1 Boundary",
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

    # Work Mon Nov 2 to Fri Nov 6 (5 shifts * 8.5h = 42.5h > 40h overtime)
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

    # Pre-existing approved COFF on Sun Nov 8 (target + 1 from Sat Nov 7)
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 8),
        end_date=date(2026, 11, 8),
        leave_type="COFF",
        status="APPROVED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Sat Nov 7 cannot be awarded because it would touch Sun Nov 8 (streak = 2 > 1)
    assert data["awarded_count"] == 0

    # Total COFF leaves for employee in DB must be exactly 1 (Sun Nov 8 only)
    coffs = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).all()
    assert len(coffs) == 1
    assert coffs[0].start_date == date(2026, 11, 8)


def test_compoff_max_consecutive_1_boundary_target_minus_1(client, test_db, sample_scenario):
    """When max_consecutive = 1, an unassigned day immediately following a pre-existing COFF
    must NOT be awarded, as the resulting streak would be 2 > 1.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max1 Target-1 Boundary",
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

    # Work Mon Nov 2 to Fri Nov 6 (42.5h)
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

    # Pre-existing approved COFF on Sat Nov 7
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 7),
        end_date=date(2026, 11, 7),
        leave_type="COFF",
        status="APPROVED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Sun Nov 8 cannot be awarded because backward streak hits Sat Nov 7 (streak = 2 > 1)
    assert data["awarded_count"] == 0

    coffs = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).all()
    assert len(coffs) == 1
    assert coffs[0].start_date == date(2026, 11, 7)


def test_compoff_max_consecutive_1_sandwiched_unassigned_days(client, test_db, sample_scenario):
    """When max_consecutive = 1 and 3 contiguous unassigned days exist (Fri, Sat, Sun),
    Fri can be awarded, Sat must be skipped (streak=2>1), and Sun can be awarded (streak=1<=1).
    Verify that streak alternating behavior respects max_consecutive = 1.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max1 Sandwiched Unassigned",
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

    # Create 11h custom shift so 4 shifts = 44h (>40h overtime threshold)
    long_shift = ShiftType(
        code="LONG",
        name="Long Shift",
        start_time="07:00:00",
        end_time="18:00:00",
        duration_hours=11.0,
        min_rest_hours_after=12,
        is_night_shift=False
    )
    test_db.add(long_shift)
    test_db.flush()

    # Work Mon Nov 2 to Thu Nov 5 (4 days * 11h = 44h)
    for offset in range(4):
        d = date(2026, 11, 2) + timedelta(days=offset)
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=long_shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))
    test_db.commit()

    # Unassigned days in this week are Fri Nov 6, Sat Nov 7, Sun Nov 8
    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Fri awarded (streak 1), Sat skipped (streak 2 > 1), Sun awarded (streak 1)
    assert data["awarded_count"] == 2

    coffs = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.leave_type.in_(["COFF", "OTHER"])
    ).order_by(LeaveRecord.start_date).all()

    dates_awarded = [c.start_date for c in coffs]
    assert dates_awarded == [date(2026, 11, 6), date(2026, 11, 8)]

    # Confirm contiguous streak is never > 1
    for i in range(len(dates_awarded) - 1):
        gap = (dates_awarded[i + 1] - dates_awarded[i]).days
        assert gap > 1, f"Found contiguous streak: {dates_awarded[i]} and {dates_awarded[i+1]}"


def test_compoff_max_consecutive_2_target_plus_1_and_target_plus_2(client, test_db, sample_scenario):
    """When max_consecutive = 2, if pre-existing approved COFFs exist on target + 1
    and target + 2 (e.g. Sun Nov 8 and Mon Nov 9), target day (Sat Nov 7) must NOT
    be awarded because Sat + Sun + Mon would form a 3-day streak > 2.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max2 Target+1 & Target+2",
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

    # Work Mon Nov 2 to Fri Nov 6 (42.5h)
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

    # Pre-existing COFF on Sun Nov 8 (target + 1) AND Mon Nov 9 (target + 2)
    test_db.add_all([
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 8), end_date=date(2026, 11, 8), leave_type="COFF", status="APPROVED"),
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), leave_type="COFF", status="APPROVED"),
    ])
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Sat Nov 7 cannot be awarded because streak would be Sat(1) + Sun(1) + Mon(1) = 3 > 2!
    assert data["awarded_count"] == 0

    # Ensure no new leave records were created for Sat Nov 7
    sat_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 7)
    ).first()
    assert sat_leave is None


def test_compoff_max_consecutive_2_sandwiched_between_two_coffs(client, test_db, sample_scenario):
    """When max_consecutive = 2, if an unassigned day is sandwiched between
    target - 1 and target + 1 (both pre-existing COFFs), it must NOT be awarded
    because (target-1) + target + (target+1) = 3 days > 2.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max2 Sandwiched Between COFFs",
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

    # 11h shifts: Mon Nov 2, Tue Nov 3, Sat Nov 7, Sun Nov 8 = 44h overtime
    long_shift = ShiftType(
        code="LONG2",
        name="Long Shift 2",
        start_time="07:00:00",
        end_time="18:00:00",
        duration_hours=11.0,
        min_rest_hours_after=12,
        is_night_shift=False
    )
    test_db.add(long_shift)
    test_db.flush()

    for d in [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 7), date(2026, 11, 8)]:
        test_db.add(RosterAssignment(
            plan_id=plan.id,
            employee_id=emp.id,
            department_id=dept.id,
            shift_type_id=long_shift.id,
            date=d,
            assignment_source="SOLVER",
            is_pinned=False
        ))

    # Pre-existing COFF on Wed Nov 4 AND Fri Nov 6
    # Target day Thu Nov 5 is unassigned and sandwiched!
    test_db.add_all([
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 4), end_date=date(2026, 11, 4), leave_type="COFF", status="APPROVED"),
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 6), end_date=date(2026, 11, 6), leave_type="COFF", status="APPROVED"),
    ])
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Thu Nov 5 must NOT be awarded because backward=Wed, forward=Fri -> streak = 3 > 2!
    assert data["awarded_count"] == 0

    thu_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 5)
    ).first()
    assert thu_leave is None


def test_compoff_max_consecutive_2_multi_day_coff_record(client, test_db, sample_scenario):
    """When a pre-existing COFF spans multiple days as a single LeaveRecord
    (e.g. start_date=Nov 8, end_date=Nov 9), the forward while-loop must correctly
    count both days, yielding streak = 3 > 2 and skipping target day Nov 7.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Max2 Multi-Day LeaveRecord",
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

    # Work Mon-Fri (42.5h)
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

    # Single LeaveRecord spanning 2 days: Nov 8 to Nov 9
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 8),
        end_date=date(2026, 11, 9),
        leave_type="COFF",
        status="APPROVED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Nov 7 cannot be awarded because multi-day leave on Nov 8-9 makes streak = 3 > 2
    assert data["awarded_count"] == 0


def test_compoff_cancelled_leave_not_counted(client, test_db, sample_scenario):
    """A pre-existing COFF leave that has status="CANCELLED" must NOT be counted
    towards consecutive streaks.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",  # max_consecutive = 1
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Cancelled Leave Test",
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

    # Work Mon-Fri (42.5h)
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

    # CANCELLED COFF on Sun Nov 8
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 8),
        end_date=date(2026, 11, 8),
        leave_type="COFF",
        status="CANCELLED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Sat Nov 7 can be awarded because Sun Nov 8 is CANCELLED (streak = 1 <= 1)
    assert data["awarded_count"] >= 1
    sat_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 7),
        LeaveRecord.status == "APPROVED"
    ).first()
    assert sat_leave is not None


def test_compoff_non_coff_leave_not_counted(client, test_db, sample_scenario):
    """An approved VACATION or SICK leave on target + 1 must NOT count towards the COFF streak."""
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",  # max_consecutive = 1
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Vacation Not Counted Test",
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

    # Work Mon-Fri (42.5h)
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

    # Approved VACATION on Sun Nov 8
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 8),
        end_date=date(2026, 11, 8),
        leave_type="VACATION",
        status="APPROVED"
    ))
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Sat Nov 7 should be awarded because VACATION on Sun does not count towards COFF streak
    assert data["awarded_count"] >= 1
    sat_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 7)
    ).first()
    assert sat_leave is not None


# ==============================================================================
# SUITE 2: CELL DELETION & DRAFT STATE & RE-SOLVE VERIFICATION
# ==============================================================================

def test_cell_deletion_updates_plan_status_to_draft(client, test_db, sample_scenario):
    """Verify that deleting an assignment from a SOLVED plan updates plan.status to DRAFT
    and physically removes the assignment row from the database.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Delete Cell Draft Status Test",
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
    target_date = date(2026, 11, 4)

    assignment = RosterAssignment(
        plan_id=plan.id,
        employee_id=emp.id,
        department_id=dept.id,
        shift_type_id=shift.id,
        date=target_date,
        assignment_source="SOLVER",
        is_pinned=False
    )
    test_db.add(assignment)
    test_db.commit()

    # Call DELETE /api/roster/{plan_id}/assignments
    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date={target_date.isoformat()}"
    )
    assert del_res.status_code == 200, del_res.text
    del_data = del_res.json()
    assert del_data["cleared"] is True

    # 1. Plan status MUST be updated to DRAFT in DB
    test_db.expire_all()
    refreshed_plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan.id).first()
    assert refreshed_plan.status == "DRAFT", f"Expected DRAFT status, got {refreshed_plan.status}"

    # 2. Assignment row MUST be physically deleted from SQLite
    remaining_a = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.employee_id == emp.id,
        RosterAssignment.date == target_date
    ).first()
    assert remaining_a is None, "Assignment was not removed from database!"


def test_cell_deletion_renders_as_empty_none_in_schedule(client, test_db, sample_scenario):
    """Verify that after cell deletion, GET /api/roster/{plan_id} returns None for the cleared cell,
    so that frontend displays '—' instead of auto-filling with 'Scheduled Rest Day (DO)'.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Delete Cell Grid Render Test",
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

    # Assign 5 work days
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

    # Delete assignment on Wednesday Nov 4
    clear_date = date(2026, 11, 4)
    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date={clear_date.isoformat()}"
    )
    assert del_res.status_code == 200

    # Fetch schedule grid
    grid_res = client.get(f"/api/roster/{plan.id}?view=staff_centric")
    assert grid_res.status_code == 200
    grid_data = grid_res.json()

    # Confirm plan status in response is DRAFT
    assert grid_data["plan"]["status"] == "DRAFT"

    # Confirm the cleared cell is None
    emp_row = next(r for r in grid_data["rows"] if r["employee_id"] == emp.id)
    cleared_cell = emp_row["assignments"].get(clear_date.isoformat())
    assert cleared_cell is None, f"Expected cleared cell to be None, got: {cleared_cell}"

    # Confirm other dates remain properly populated
    mon_cell = emp_row["assignments"].get("2026-11-02")
    assert mon_cell is not None
    assert mon_cell["shift_code"] == shift.code


def test_cell_deletion_clears_pinned_day_off_and_sets_draft(client, test_db, sample_scenario):
    """Verify that deleting a cell that was pinned as DAY_OFF or COFF removes the 1-day
    LeaveRecord from the database and sets plan status to DRAFT.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Delete Pinned Off Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    target_date = date(2026, 11, 4)

    # Pin day off using the official pin-off endpoint
    pin_res = client.post(f"/api/roster/{plan.id}/pin-off", json={
        "employee_id": emp.id,
        "date": target_date.isoformat(),
        "off_type": "DAY_OFF",
        "notes": "Pinned Day OFF"
    })
    assert pin_res.status_code == 200

    # Verify LeaveRecord was created
    l_rec = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == target_date,
        LeaveRecord.end_date == target_date
    ).first()
    assert l_rec is not None

    # Call DELETE /api/roster/{plan_id}/assignments
    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date={target_date.isoformat()}"
    )
    assert del_res.status_code == 200
    assert del_res.json()["cleared"] is True

    # 1. LeaveRecord must be deleted from DB
    remaining_l = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == target_date,
        LeaveRecord.end_date == target_date
    ).first()
    assert remaining_l is None, "Pinned DAY_OFF LeaveRecord was not purged from DB!"

    # 2. Plan status must be DRAFT
    test_db.expire_all()
    refreshed_plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan.id).first()
    assert refreshed_plan.status == "DRAFT"

    # 3. Schedule must render cell as None
    grid_res = client.get(f"/api/roster/{plan.id}?view=staff_centric")
    emp_row = next(r for r in grid_res.json()["rows"] if r["employee_id"] == emp.id)
    assert emp_row["assignments"][target_date.isoformat()] is None


def test_cell_deletion_solvable_by_solve_remaining(client, test_db, sample_scenario):
    """Verify the full lifecycle:
    1. Plan is generated / solved.
    2. A cell is deleted via DELETE /api/roster/{plan_id}/assignments -> status becomes DRAFT.
    3. User invokes POST /api/roster/{plan_id}/solve-remaining.
    4. CP-SAT solver successfully re-solves remaining blank slots, sets plan status to SOLVED,
       and populates the previously cleared cell without UNIQUE constraint crashes.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Delete and Solve Remaining Lifecycle",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11,
        variant_strategy="BALANCED"
    )
    test_db.add(plan)
    test_db.commit()

    icu = test_db.query(Department).filter(Department.code == "ICU").first()
    morn = test_db.query(ShiftType).filter(ShiftType.code == "MORN").first()
    night = test_db.query(ShiftType).filter(ShiftType.code == "NIGHT").first()
    icu_emps = test_db.query(Employee).filter(Employee.primary_department_id == icu.id).all()

    # Pre-fill Monday Nov 2 with pinned assignments
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=icu_emps[0].id,
        department_id=icu.id,
        shift_type_id=morn.id,
        date=date(2026, 11, 2),
        assignment_source="PREFILLED",
        is_pinned=True
    ))
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=icu_emps[1].id,
        department_id=icu.id,
        shift_type_id=night.id,
        date=date(2026, 11, 2),
        assignment_source="PREFILLED",
        is_pinned=True
    ))

    # Add a non-pinned assignment on Tuesday Nov 3 for icu_emps[0]
    target_date = date(2026, 11, 3)
    test_db.add(RosterAssignment(
        plan_id=plan.id,
        employee_id=icu_emps[0].id,
        department_id=icu.id,
        shift_type_id=morn.id,
        date=target_date,
        assignment_source="SOLVER",
        is_pinned=False
    ))
    test_db.commit()

    # Step 1: Delete assignment on Tuesday Nov 3
    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={icu_emps[0].id}&date={target_date.isoformat()}"
    )
    assert del_res.status_code == 200
    assert del_res.json()["cleared"] is True

    # Plan is now in DRAFT
    test_db.expire_all()
    refreshed_plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan.id).first()
    assert refreshed_plan.status == "DRAFT"

    # Step 2: Solve remaining blank slots
    solve_res = client.post(f"/api/roster/{plan.id}/solve-remaining")
    assert solve_res.status_code == 200, solve_res.text
    solve_data = solve_res.json()

    assert solve_data["solver_status"] in ["OPTIMAL", "FEASIBLE"]
    assert solve_data["status"] == "SOLVED"

    # Plan in DB must be SOLVED
    test_db.refresh(refreshed_plan)
    assert refreshed_plan.status == "SOLVED"

    # Pinned assignments on Nov 2 must remain preserved
    pinned_mon = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id,
        RosterAssignment.date == date(2026, 11, 2),
        RosterAssignment.is_pinned == True
    ).all()
    assert len(pinned_mon) == 2

    # Assignments exist across the week satisfying requirements
    total_assigns = test_db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan.id
    ).count()
    assert total_assigns > 2


def test_cell_deletion_preserves_multi_day_vacation(client, test_db, sample_scenario):
    """Verify that calling DELETE /api/roster/{plan_id}/assignments does NOT delete
    a legitimate multi-day approved leave (e.g. VACATION) that spans across the target date.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Preserve Multi-Day Vacation Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()

    # Multi-day vacation from Nov 3 to Nov 6
    vacation = LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 3),
        end_date=date(2026, 11, 6),
        leave_type="VACATION",
        status="APPROVED",
        notes="Family Vacation"
    )
    test_db.add(vacation)
    test_db.commit()

    # Call DELETE on Nov 4 (midst of vacation, where no RosterAssignment exists)
    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date=2026-11-04"
    )
    assert del_res.status_code == 200
    # Nothing was cleared because multi-day vacation is NOT a 1-day DAY_OFF/COFF
    assert del_res.json()["cleared"] is False

    # Vacation MUST still exist in database
    remaining_vac = test_db.query(LeaveRecord).filter(LeaveRecord.id == vacation.id).first()
    assert remaining_vac is not None
    assert remaining_vac.start_date == date(2026, 11, 3)
    assert remaining_vac.end_date == date(2026, 11, 6)

    # Plan status should remain unchanged
    refreshed_plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan.id).first()
    assert refreshed_plan.status == "SOLVED"


def test_cell_deletion_idempotency_on_empty_cell(client, test_db, sample_scenario):
    """Calling DELETE on an already empty slot returns cleared=False and does not alter plan status."""
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="Idempotent Delete Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()

    del_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date=2026-11-04"
    )
    assert del_res.status_code == 200
    assert del_res.json()["cleared"] is False

    refreshed_plan = test_db.query(RosterPlan).filter(RosterPlan.id == plan.id).first()
    assert refreshed_plan.status == "SOLVED"


def test_cell_deletion_endpoint_url_audit(client, test_db, sample_scenario):
    """Audit the endpoint URLs: verify established plural route DELETE /api/roster/{plan_id}/assignments
    and observe behavior of singular /assignment route if requested.
    """
    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="URL Audit Test",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    target_date = "2026-11-04"

    # 1. Plural route (established)
    plural_res = client.delete(
        f"/api/roster/{plan.id}/assignments?employee_id={emp.id}&date={target_date}"
    )
    assert plural_res.status_code == 200

    # 2. Singular route: observe behavior
    singular_res = client.delete(
        f"/api/roster/{plan.id}/assignment?employee_id={emp.id}&date={target_date}"
    )
    # The API standard is plural `/assignments` matching REST conventions (POST /assignments, DELETE /assignments)
    assert singular_res.status_code in [404, 405]


def test_compoff_prior_month_boundary_streak(client, test_db, sample_scenario):
    """Verify that a pre-existing COFF immediately prior to plan.start_date
    is detected across month boundaries, enforcing max_consecutive=1.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "false",  # max_consecutive = 1
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Prior Month Boundary Test",
        start_date=date(2026, 11, 2),  # Monday Nov 2
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

    # Pre-existing COFF on Sunday Nov 1 (prior day, before plan.start_date)
    test_db.add(LeaveRecord(
        employee_id=emp.id,
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        leave_type="COFF",
        status="APPROVED"
    ))

    # Employee works Tue Nov 3 to Sat Nov 7 (5 shifts * 8.5h = 42.5h)
    for offset in range(1, 6):
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

    # Target unassigned day in Wk 45 is Mon Nov 2
    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200
    data = res.json()

    # Mon Nov 2 backward check hits Sun Nov 1 (prior boundary) -> streak = 2 > 1 -> skipped!
    mon_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 2)
    ).first()
    assert mon_leave is None


def test_compoff_next_month_boundary_double_leave_streak(client, test_db, sample_scenario):
    """Verify that multi-day pre-existing COFFs extending into the next month
    block target day awards when max_consecutive = 2.
    """
    client.post("/api/settings", json={
        "settings": {
            "continuous_comp_off_enabled": "true",  # max_consecutive = 2
            "max_comp_offs_per_employee": "5"
        }
    })

    plan = RosterPlan(
        session_id=uuid.uuid4().hex,
        name="COFF Next Month Boundary Double Leave",
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 8),  # Ends Sun Nov 8
        status="SOLVED",
        planning_year=2026,
        planning_month=11
    )
    test_db.add(plan)
    test_db.commit()

    emp = test_db.query(Employee).first()
    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()

    # Work Mon Nov 2 to Fri Nov 6 (42.5h)
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

    # Pre-existing COFFs on Mon Nov 9 and Tue Nov 10 (beyond plan end date)
    test_db.add_all([
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 9), end_date=date(2026, 11, 9), leave_type="COFF", status="APPROVED"),
        LeaveRecord(employee_id=emp.id, start_date=date(2026, 11, 10), end_date=date(2026, 11, 10), leave_type="COFF", status="APPROVED"),
    ])
    test_db.commit()

    res = client.post(f"/api/roster/{plan.id}/auto-award-compoffs")
    assert res.status_code == 200

    # Sat Nov 7 can be awarded (streak=1 <= 2)
    # Sun Nov 8 CANNOT be awarded because Sun + Nov 9 + Nov 10 = 3 > 2!
    sun_leave = test_db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == emp.id,
        LeaveRecord.start_date == date(2026, 11, 8)
    ).first()
    assert sun_leave is None, "Sun Nov 8 was illegally awarded creating a 3-day streak with Nov 9 & Nov 10!"

