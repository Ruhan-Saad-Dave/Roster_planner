"""Roster planning, solver execution, drag-and-drop validation, and variants API."""
import calendar
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import RosterPlan, RosterAssignment, DeficitLog, Department, ShiftType, Employee, LeaveRecord
from src.api.schemas import (
    GenerateRosterRequest, ValidateAssignmentRequest,
    ManualAssignmentRequest, PrefillShiftsRequest, FindReplaceRequest
)
from src.services.roster_service import (
    generate_roster_plan, solve_remaining_blank_slots,
    validate_drag_and_drop_move, generate_shortage_fix_recommendations
)

router = APIRouter(prefix="/api/roster", tags=["Roster Planning"])

@router.get("/plans")
def list_plans(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db)
):
    q = db.query(RosterPlan).order_by(RosterPlan.created_at.desc())
    if year:
        q = q.filter(RosterPlan.planning_year == year)
    if month:
        q = q.filter(RosterPlan.planning_month == month)
    plans = q.all()
    return [
        {
            "id": p.id,
            "session_id": p.session_id,
            "name": p.name,
            "variant_name": p.variant_name,
            "variant_strategy": p.variant_strategy,
            "is_active_variant": p.is_active_variant,
            "planning_year": p.planning_year,
            "planning_month": p.planning_month,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
            "status": p.status,
            "solver_status": p.solver_status,
            "total_deficits": p.total_deficits,
            "total_floats": p.total_floats,
            "solve_time_seconds": p.solve_time_seconds,
            "created_at": p.created_at.isoformat()
        }
        for p in plans
    ]

@router.get("/previous-month-summary")
def get_previous_month_summary(
    year: int = Query(..., description="Target year"),
    month: int = Query(..., description="Target month"),
    db: Session = Depends(get_db)
):
    """Retrieve trailing assignments and statistics from the preceding calendar month."""
    if month == 1:
        prev_year = year - 1
        prev_month = 12
    else:
        prev_year = year
        prev_month = month - 1

    prev_plan = db.query(RosterPlan).filter(
        RosterPlan.planning_year == prev_year,
        RosterPlan.planning_month == prev_month,
        RosterPlan.is_active_variant == True
    ).first()
    if not prev_plan:
        prev_plan = db.query(RosterPlan).filter(
            RosterPlan.planning_year == prev_year,
            RosterPlan.planning_month == prev_month
        ).order_by(RosterPlan.id.desc()).first()

    if not prev_plan:
        return {
            "has_previous_plan": False,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "employees": []
        }

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    shifts = {s.id: s for s in db.query(ShiftType).all()}
    prev_assigns = db.query(RosterAssignment).filter(RosterAssignment.plan_id == prev_plan.id).all()
    prev_by_emp = {}
    for pa in prev_assigns:
        prev_by_emp.setdefault(pa.employee_id, []).append(pa)

    prev_end = prev_plan.end_date
    last_3_dates = [prev_end - timedelta(days=i) for i in reversed(range(3))]

    emp_list = []
    for emp in employees:
        e_assigns = prev_by_emp.get(emp.id, [])
        total_hours = sum(shifts[pa.shift_type_id].duration_hours for pa in e_assigns if pa.shift_type_id in shifts)
        total_nights = sum(1 for pa in e_assigns if pa.shift_type_id in shifts and shifts[pa.shift_type_id].is_night_shift)

        e_assign_dates = {pa.date: pa for pa in e_assigns}
        trailing_days = 0
        check_d = prev_end
        while check_d in e_assign_dates:
            trailing_days += 1
            check_d -= timedelta(days=1)

        last_day_assign = e_assign_dates.get(prev_end)
        last_day_shift = shifts[last_day_assign.shift_type_id].code if last_day_assign and last_day_assign.shift_type_id in shifts else "OFF"

        trailing_3_days = []
        for td in last_3_dates:
            td_assign = e_assign_dates.get(td)
            sc = shifts[td_assign.shift_type_id].code if td_assign and td_assign.shift_type_id in shifts else "OFF"
            trailing_3_days.append({"date": td.isoformat(), "shift_code": sc})

        emp_list.append({
            "employee_id": emp.id,
            "employee_name": emp.name,
            "employee_code": emp.employee_code,
            "primary_department_id": emp.primary_department_id,
            "worked_hours": round(total_hours, 1),
            "total_shifts": len(e_assigns),
            "night_shifts": total_nights,
            "last_day_shift": last_day_shift,
            "trailing_consecutive_days": trailing_days,
            "trailing_3_days": trailing_3_days
        })

    return {
        "has_previous_plan": True,
        "plan_id": prev_plan.id,
        "plan_name": prev_plan.name,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "start_date": prev_plan.start_date.isoformat(),
        "end_date": prev_plan.end_date.isoformat(),
        "trailing_dates": [d.isoformat() for d in last_3_dates],
        "employees": emp_list
    }

@router.post("/generate")
def trigger_generation(req: GenerateRosterRequest, db: Session = Depends(get_db)):
    # Calculate dates from year and month if provided
    if req.planning_year and req.planning_month:
        num_days = calendar.monthrange(req.planning_year, req.planning_month)[1]
        start_date = date(req.planning_year, req.planning_month, 1)
        end_date = date(req.planning_year, req.planning_month, num_days)
    elif req.start_date and req.end_date:
        start_date = req.start_date
        end_date = req.end_date
    else:
        # Default to current month or next month
        today = date.today()
        num_days = calendar.monthrange(today.year, today.month)[1]
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, num_days)

    result = generate_roster_plan(
        db=db,
        name=req.name,
        start_date=start_date,
        end_date=end_date,
        planning_year=req.planning_year,
        planning_month=req.planning_month,
        variant_count=req.variant_count,
        variant_strategies=req.variant_strategies,
        timeout_seconds=req.timeout_seconds,
        max_consecutive_days=req.max_consecutive_days,
        min_rest_days_per_week=req.min_rest_days_per_week,
        weights=req.weights
    )

    primary = result["primary_plan"]
    variants_resp = [
        {
            "plan_id": p.id,
            "variant_name": p.variant_name,
            "variant_strategy": p.variant_strategy,
            "is_active_variant": p.is_active_variant,
            "status": p.status,
            "solver_status": p.solver_status,
            "solve_time_seconds": p.solve_time_seconds,
            "total_deficits": p.total_deficits,
            "total_floats": p.total_floats,
            "objective_score": p.objective_score
        }
        for p in result["variants"]
    ]

    return {
        "session_id": result["session_id"],
        "plan_id": primary.id,
        "name": primary.name,
        "status": primary.status,
        "solver_status": primary.solver_status,
        "total_deficits": primary.total_deficits,
        "total_floats": primary.total_floats,
        "variants": variants_resp
    }

@router.get("/{plan_id}")
def get_plan_schedule(
    plan_id: int,
    department_id: Optional[int] = None,
    view: str = Query("staff_centric", enum=["staff_centric", "slot_centric"]),
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    departments = {d.id: d for d in db.query(Department).all()}
    shifts = {s.id: s for s in db.query(ShiftType).all()}
    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).all()

    horizon_days = (plan.end_date - plan.start_date).days + 1
    dates = [plan.start_date + timedelta(days=t) for t in range(horizon_days)]

    # Compute preceding month context if planning_year/month available
    prev_context = None
    prev_emp_summaries = {}
    if plan.planning_year and plan.planning_month:
        if plan.planning_month == 1:
            p_year = plan.planning_year - 1
            p_month = 12
        else:
            p_year = plan.planning_year
            p_month = plan.planning_month - 1

        prev_plan = db.query(RosterPlan).filter(
            RosterPlan.planning_year == p_year,
            RosterPlan.planning_month == p_month,
            RosterPlan.is_active_variant == True
        ).first()
        if not prev_plan:
            prev_plan = db.query(RosterPlan).filter(
                RosterPlan.planning_year == p_year,
                RosterPlan.planning_month == p_month
            ).order_by(RosterPlan.id.desc()).first()

        if prev_plan:
            prev_assigns = db.query(RosterAssignment).filter(RosterAssignment.plan_id == prev_plan.id).all()
            prev_by_emp = {}
            for pa in prev_assigns:
                prev_by_emp.setdefault(pa.employee_id, []).append(pa)

            prev_end = prev_plan.end_date
            last_3_dates = [prev_end - timedelta(days=i) for i in reversed(range(3))]
            prev_context = {
                "has_previous_plan": True,
                "plan_id": prev_plan.id,
                "name": prev_plan.name,
                "planning_year": p_year,
                "planning_month": p_month,
                "trailing_dates": [d.isoformat() for d in last_3_dates]
            }

            for emp in employees:
                e_assigns = prev_by_emp.get(emp.id, [])
                total_hours = sum(shifts[pa.shift_type_id].duration_hours for pa in e_assigns if pa.shift_type_id in shifts)
                total_nights = sum(1 for pa in e_assigns if pa.shift_type_id in shifts and shifts[pa.shift_type_id].is_night_shift)

                e_dates = {pa.date: pa for pa in e_assigns}
                trailing_days = 0
                check_d = prev_end
                while check_d in e_dates:
                    trailing_days += 1
                    check_d -= timedelta(days=1)

                last_day_assign = e_dates.get(prev_end)
                last_day_shift = shifts[last_day_assign.shift_type_id].code if last_day_assign and last_day_assign.shift_type_id in shifts else "OFF"

                trailing_3_days = []
                for td in last_3_dates:
                    td_assign = e_dates.get(td)
                    sc = shifts[td_assign.shift_type_id].code if td_assign and td_assign.shift_type_id in shifts else "OFF"
                    trailing_3_days.append({"date": td.isoformat(), "shift_code": sc})

                prev_emp_summaries[emp.id] = {
                    "worked_hours": round(total_hours, 1),
                    "total_shifts": len(e_assigns),
                    "night_shifts": total_nights,
                    "last_day_shift": last_day_shift,
                    "trailing_consecutive_days": trailing_days,
                    "trailing_3_days": trailing_3_days
                }

    if view == "staff_centric":
        # Load approved leaves for horizon
        leaves = db.query(LeaveRecord).filter(
            LeaveRecord.status == "APPROVED",
            LeaveRecord.start_date <= plan.end_date,
            LeaveRecord.end_date >= plan.start_date
        ).all()
        leave_by_emp_date = {}
        for l in leaves:
            for t in range(horizon_days):
                cur_date = plan.start_date + timedelta(days=t)
                if l.start_date <= cur_date <= l.end_date:
                    leave_by_emp_date[(l.employee_id, cur_date)] = l

        # Group by employee
        rows = []
        assign_by_emp_date = {(a.employee_id, a.date): a for a in assignments}

        for emp in employees:
            if department_id and emp.primary_department_id != department_id:
                continue

            emp_fixed_days = []
            if emp.fixed_off_days:
                try:
                    emp_fixed_days = [int(x.strip()) for x in emp.fixed_off_days.split(",") if x.strip().isdigit()]
                except Exception:
                    pass

            emp_assigns = {}
            consecutive_work_days = 0
            prev_shift = None

            for d in dates:
                if (emp.id, d) in assign_by_emp_date:
                    a = assign_by_emp_date[(emp.id, d)]
                    s = shifts.get(a.shift_type_id)
                    dept = departments.get(a.department_id)
                    consecutive_work_days += 1

                    has_conflict = False
                    conflict_reason = None

                    # Turnaround check: Previous night shift followed by non-night or morning
                    if prev_shift and prev_shift.is_night_shift and s and not s.is_night_shift:
                        has_conflict = True
                        conflict_reason = "Mandatory 14h rest interval after Night Shift violated"

                    # Consecutive days check
                    if consecutive_work_days > 5:
                        has_conflict = True
                        conflict_reason = f"Exceeds ergonomic 5-consecutive work day limit ({consecutive_work_days} days)"

                    emp_assigns[d.isoformat()] = {
                        "assignment_id": a.id,
                        "shift_id": a.shift_type_id,
                        "shift_code": s.code if s else "",
                        "shift_name": s.name if s else "",
                        "department_id": a.department_id,
                        "department_code": dept.code if dept else "",
                        "department_color": dept.color_code if dept else "#3B82F6",
                        "is_floating": a.is_floating,
                        "float_rank": a.float_rank,
                        "is_pinned": a.is_pinned,
                        "is_manual_override": a.is_manual_override,
                        "has_conflict": has_conflict,
                        "conflict_reason": conflict_reason,
                        "is_leave": False,
                        "is_fixed_off": False
                    }
                    prev_shift = s

                elif (emp.id, d) in leave_by_emp_date:
                    consecutive_work_days = 0
                    prev_shift = None
                    l = leave_by_emp_date[(emp.id, d)]
                    emp_assigns[d.isoformat()] = {
                        "assignment_id": None,
                        "shift_id": None,
                        "shift_code": "VAC" if l.leave_type == "VACATION" else (l.leave_type or "LEAVE"),
                        "shift_name": l.notes or l.leave_type,
                        "department_id": None,
                        "department_code": "",
                        "department_color": "#8B5CF6",
                        "is_floating": False,
                        "float_rank": 1,
                        "is_pinned": True,
                        "is_manual_override": False,
                        "has_conflict": False,
                        "conflict_reason": None,
                        "is_leave": True,
                        "leave_type": l.leave_type,
                        "is_fixed_off": False
                    }
                elif d.weekday() in emp_fixed_days:
                    consecutive_work_days = 0
                    prev_shift = None
                    emp_assigns[d.isoformat()] = {
                        "assignment_id": None,
                        "shift_id": None,
                        "shift_code": "DO",
                        "shift_name": "Dedicated Regular Day Off",
                        "department_id": None,
                        "department_code": "",
                        "department_color": "#64748B",
                        "is_floating": False,
                        "float_rank": 1,
                        "is_pinned": True,
                        "is_manual_override": False,
                        "has_conflict": False,
                        "conflict_reason": None,
                        "is_leave": False,
                        "is_fixed_off": True
                    }
                else:
                    consecutive_work_days = 0
                    prev_shift = None
                    emp_assigns[d.isoformat()] = None  # Empty cell

            dept_obj = departments.get(emp.primary_department_id)
            dept_color = dept_obj.color_code if dept_obj else "#3B82F6"

            rows.append({
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "employee_name": emp.name,
                "primary_department_id": emp.primary_department_id,
                "primary_department_name": dept_obj.name if dept_obj else "",
                "primary_department_code": dept_obj.code if dept_obj else "",
                "primary_department_color": dept_color,
                "fixed_off_days": emp.fixed_off_days,
                "assignments": emp_assigns,
                "previous_month_summary": prev_emp_summaries.get(emp.id)
            })

        return {
            "plan": {
                "id": plan.id,
                "session_id": plan.session_id,
                "name": plan.name,
                "variant_name": plan.variant_name,
                "planning_year": plan.planning_year,
                "planning_month": plan.planning_month,
                "start_date": plan.start_date.isoformat(),
                "end_date": plan.end_date.isoformat(),
                "status": plan.status,
                "solver_status": plan.solver_status,
                "total_deficits": plan.total_deficits,
                "total_floats": plan.total_floats
            },
            "previous_month_context": prev_context,
            "view_type": "staff_centric",
            "dates": [d.isoformat() for d in dates],
            "rows": rows
        }

    else:
        # Slot-centric
        slot_map = {}
        for a in assignments:
            key = (a.date.isoformat(), a.department_id, a.shift_type_id)
            slot_map.setdefault(key, []).append(a)

        slots = []
        for d in dates:
            d_str = d.isoformat()
            for dept_id, dept in departments.items():
                if department_id and dept_id != department_id:
                    continue
                for s_id, shift in shifts.items():
                    assigned_list = slot_map.get((d_str, dept_id, s_id), [])
                    worker_data = [
                        {
                            "assignment_id": a.id,
                            "employee_id": a.employee_id,
                            "name": a.employee.name,
                            "is_floating": a.is_floating,
                            "float_rank": a.float_rank,
                            "is_pinned": a.is_pinned,
                            "primary_department_id": a.employee.primary_department_id,
                            "primary_department_code": departments[a.employee.primary_department_id].code if a.employee.primary_department_id in departments else "",
                            "primary_department_color": departments[a.employee.primary_department_id].color_code if a.employee.primary_department_id in departments else "#3B82F6",
                            "department_color": dept.color_code
                        }
                        for a in assigned_list
                    ]
                    # Check deficit
                    def_entry = next((df for df in deficits if df.date == d and df.department_id == dept_id and df.shift_type_id == s_id), None)
                    slots.append({
                        "date": d_str,
                        "day_name": d.strftime("%a"),
                        "department_id": dept_id,
                        "department_code": dept.code,
                        "department_name": dept.name,
                        "department_color": dept.color_code,
                        "shift_type_id": s_id,
                        "shift_code": shift.code,
                        "shift_name": shift.name,
                        "assigned_staff": worker_data,
                        "assigned_count": len(worker_data),
                        "deficit": def_entry.shortage_count if def_entry else 0
                    })

        return {
            "plan_id": plan.id,
            "previous_month_context": prev_context,
            "view_type": "slot_centric",
            "slots": slots
        }

@router.post("/validate-assignment")
def validate_assignment(req: ValidateAssignmentRequest, db: Session = Depends(get_db)):
    return validate_drag_and_drop_move(
        db,
        plan_id=req.plan_id,
        employee_id=req.employee_id,
        target_dept_id=req.target_department_id,
        target_shift_id=req.target_shift_type_id,
        target_date=req.target_date
    )

@router.post("/{plan_id}/assignments")
def save_manual_assignment(
    plan_id: int,
    req: ManualAssignmentRequest,
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Validate move
    val = validate_drag_and_drop_move(
        db,
        plan_id=plan_id,
        employee_id=req.employee_id,
        target_dept_id=req.department_id,
        target_shift_id=req.shift_type_id,
        target_date=req.date
    )
    if not val["is_valid"] and not req.force_override:
        raise HTTPException(status_code=400, detail={"message": "Ergonomic violation.", "violations": val["violations"]})

    # Check existing assignment for this employee on this date
    existing = db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.employee_id == req.employee_id,
        RosterAssignment.date == req.date
    ).first()

    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    is_float = (emp.primary_department_id != req.department_id)

    if existing:
        existing.department_id = req.department_id
        existing.shift_type_id = req.shift_type_id
        existing.is_manual_override = True
        existing.is_pinned = req.is_pinned
        existing.is_floating = is_float
        existing.assignment_source = "MANUAL_OVERRIDE"
    else:
        new_assign = RosterAssignment(
            plan_id=plan_id,
            employee_id=req.employee_id,
            department_id=req.department_id,
            shift_type_id=req.shift_type_id,
            date=req.date,
            assignment_source="MANUAL_OVERRIDE",
            is_pinned=req.is_pinned,
            is_manual_override=True,
            is_floating=is_float
        )
        db.add(new_assign)

    db.commit()
    return {"message": "Assignment updated successfully.", "is_valid": val["is_valid"]}

@router.delete("/{plan_id}/assignments")
def remove_assignment(
    plan_id: int,
    employee_id: int = Query(...),
    date: date = Query(...),
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    existing = db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.employee_id == employee_id,
        RosterAssignment.date == date
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"message": "Assignment cleared (set as OFF).", "cleared": True}
    return {"message": "No assignment existed on this date.", "cleared": False}

@router.post("/{plan_id}/assignments/toggle-pin")
def toggle_pin_assignment(
    plan_id: int,
    employee_id: int = Query(...),
    date: date = Query(...),
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    existing = db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.employee_id == employee_id,
        RosterAssignment.date == date
    ).first()
    if not existing:
        raise HTTPException(status_code=404, detail="No assignment exists to pin on this date.")

    existing.is_pinned = not existing.is_pinned
    db.commit()
    return {"is_pinned": existing.is_pinned, "message": "Shift pinned" if existing.is_pinned else "Shift unpinned"}

@router.post("/{plan_id}/solve-remaining")
def solve_remaining(plan_id: int, timeout_seconds: int = 15, db: Session = Depends(get_db)):
    plan = solve_remaining_blank_slots(db, plan_id, timeout_seconds=timeout_seconds)
    return {
        "plan_id": plan.id,
        "status": plan.status,
        "solver_status": plan.solver_status,
        "total_deficits": plan.total_deficits,
        "total_floats": plan.total_floats
    }

@router.get("/{plan_id}/deficits")
def get_plan_deficits(plan_id: int, db: Session = Depends(get_db)):
    deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).all()
    res = []
    for d in deficits:
        recs = generate_shortage_fix_recommendations(db, plan_id, d.id)
        res.append({
            "deficit_id": d.id,
            "department_id": d.department_id,
            "department_name": d.department.name,
            "shift_type_id": d.shift_type_id,
            "shift_name": d.shift_type.name,
            "date": d.date.isoformat(),
            "shortage_count": d.shortage_count,
            "reason_code": d.reason_code,
            "recommended_fixes": recs
        })
    return res

@router.post("/{plan_id}/promote")
def promote_plan_variant(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Demote all sibling variants in the same session
    db.query(RosterPlan).filter(
        RosterPlan.session_id == plan.session_id
    ).update({"is_active_variant": False})

    plan.is_active_variant = True
    plan.status = "PUBLISHED"
    db.commit()
    return {"message": f"Variant '{plan.variant_name}' promoted to Active Published plan."}

@router.post("/{plan_id}/find-replace")
def find_replace_assignments(
    plan_id: int,
    req: FindReplaceRequest,
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    shifts = {s.code.upper(): s for s in db.query(ShiftType).all()}
    find_upper = req.find_shift_code.strip().upper()
    replace_upper = req.replace_shift_code.strip().upper()

    q = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id)
    if req.department_id:
        q = q.filter(RosterAssignment.department_id == req.department_id)

    replaced_count = 0
    if replace_upper in ["OFF", "CLEAR", "DAY_OFF", "DO"]:
        # Delete matching assignments to set to Day OFF
        assigns = q.all()
        for a in assigns:
            if a.shift_type.code.upper() == find_upper:
                db.delete(a)
                replaced_count += 1
    elif replace_upper in shifts:
        target_shift = shifts[replace_upper]
        assigns = q.all()
        for a in assigns:
            if a.shift_type.code.upper() == find_upper:
                a.shift_type_id = target_shift.id
                a.is_manual_override = True
                replaced_count += 1
    else:
        raise HTTPException(status_code=400, detail=f"Target shift '{req.replace_shift_code}' does not exist.")

    db.commit()
    return {"replaced_count": replaced_count, "message": f"Replaced {replaced_count} instance(s) of '{find_upper}' with '{replace_upper}'."}
