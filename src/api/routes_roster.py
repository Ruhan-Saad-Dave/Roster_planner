"""Roster planning, solver execution, drag-and-drop validation, and variants API."""
import calendar
import uuid
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import RosterPlan, RosterAssignment, DeficitLog, Department, ShiftType, Employee, LeaveRecord, EmployeeDepartmentEligibility, SystemSetting
from src.api.schemas import (
    GenerateRosterRequest, UpdatePlanRequest, ValidateAssignmentRequest,
    ManualAssignmentRequest, PrefillShiftsRequest, FindReplaceRequest,
    PinOffRequest
)
from src.services.roster_service import (
    generate_roster_plan, solve_remaining_blank_slots,
    validate_drag_and_drop_move, generate_shortage_fix_recommendations
)
from src.solver.rules import validate_assignment_candidate

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
    dept_map = {d.id: d for d in db.query(Department).all()}
    res = []
    for p in plans:
        if p.department_ids:
            dept_id_list = [int(x) for x in p.department_ids.split(",") if x.isdigit()]
            dept_names = [dept_map[did].name for did in dept_id_list if did in dept_map]
            scope_label = ", ".join(dept_names) if dept_names else "Specific Depts"
        else:
            dept_id_list = []
            scope_label = "All Departments"

        res.append({
            "id": p.id,
            "session_id": p.session_id,
            "name": p.name,
            "department_ids": dept_id_list,
            "scope_label": scope_label,
            "variant_name": p.variant_name,
            "variant_strategy": p.variant_strategy,
            "is_active_variant": p.is_active_variant,
            "planning_year": p.planning_year,
            "planning_month": p.planning_month,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
            "horizon_days": (p.end_date - p.start_date).days + 1,
            "assignments_count": len(p.assignments),
            "status": p.status,
            "solver_status": p.solver_status,
            "total_deficits": p.total_deficits,
            "total_floats": p.total_floats,
            "solve_time_seconds": p.solve_time_seconds,
            "created_at": p.created_at.isoformat()
        })
    return res

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
    # Calculate dates: explicit custom date range takes priority
    if req.start_date and req.end_date:
        start_date = req.start_date
        end_date = req.end_date
    elif req.planning_year and req.planning_month:
        num_days = calendar.monthrange(req.planning_year, req.planning_month)[1]
        start_date = date(req.planning_year, req.planning_month, 1)
        end_date = date(req.planning_year, req.planning_month, num_days)
    else:
        # Default to current month
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
        target_department_ids=req.department_ids,
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

@router.patch("/{plan_id}")
def update_plan(plan_id: int, req: UpdatePlanRequest, db: Session = Depends(get_db)):
    """Update roster plan metadata such as name, status, or active variant setting."""
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    if req.name is not None and req.name.strip():
        plan.name = req.name.strip()
    if req.status is not None:
        plan.status = req.status
    if req.department_ids is not None:
        plan.department_ids = req.department_ids.strip() if req.department_ids.strip() else None
    if req.is_active_variant is not None:
        if req.is_active_variant:
            # Deactivate other variants in same session
            db.query(RosterPlan).filter(RosterPlan.session_id == plan.session_id).update({"is_active_variant": False})
        plan.is_active_variant = req.is_active_variant

    db.commit()
    db.refresh(plan)
    return {
        "message": "Plan updated successfully.",
        "id": plan.id,
        "name": plan.name,
        "status": plan.status,
        "department_ids": plan.department_ids,
        "is_active_variant": plan.is_active_variant
    }

@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    """Delete a roster plan and all associated assignments and deficit logs."""
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Unlink any child variants that reference this plan as parent
    db.query(RosterPlan).filter(RosterPlan.parent_plan_id == plan_id).update({"parent_plan_id": None})
    db.delete(plan)
    db.commit()
    return {"message": f"Roster plan '{plan.name}' has been successfully deleted."}

@router.post("/{plan_id}/duplicate")
def duplicate_plan(plan_id: int, db: Session = Depends(get_db)):
    """Clone an existing roster plan with all assignments and deficits for what-if scenario testing."""
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    new_session_id = str(uuid.uuid4())[:16]
    new_plan = RosterPlan(
        session_id=new_session_id,
        name=f"Copy of {plan.name}",
        department_ids=plan.department_ids,
        variant_name=f"{plan.variant_name} (Copy)",
        variant_strategy=plan.variant_strategy,
        is_active_variant=True,
        planning_year=plan.planning_year,
        planning_month=plan.planning_month,
        start_date=plan.start_date,
        end_date=plan.end_date,
        status="DRAFT" if plan.status == "PUBLISHED" else plan.status,
        solver_status=plan.solver_status,
        solve_time_seconds=plan.solve_time_seconds,
        total_deficits=plan.total_deficits,
        total_floats=plan.total_floats,
        objective_score=plan.objective_score
    )
    db.add(new_plan)
    db.flush()

    # Replicate assignments
    for a in plan.assignments:
        db.add(RosterAssignment(
            plan_id=new_plan.id,
            employee_id=a.employee_id,
            department_id=a.department_id,
            shift_type_id=a.shift_type_id,
            date=a.date,
            assignment_source=a.assignment_source,
            is_pinned=a.is_pinned,
            is_manual_override=a.is_manual_override,
            is_floating=a.is_floating,
            float_rank=a.float_rank
        ))

    # Replicate deficit logs
    for d in plan.deficits:
        db.add(DeficitLog(
            plan_id=new_plan.id,
            department_id=d.department_id,
            shift_type_id=d.shift_type_id,
            date=d.date,
            shortage_count=d.shortage_count,
            reason_code=d.reason_code
        ))

    db.commit()
    db.refresh(new_plan)
    return {
        "message": f"Successfully duplicated '{plan.name}'.",
        "id": new_plan.id,
        "plan_id": new_plan.id,
        "name": new_plan.name
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

    if plan.department_ids and not department_id:
        target_did_set = {int(x) for x in plan.department_ids.split(",") if x.isdigit()}
        assigned_emp_ids = {a.employee_id for a in assignments}
        employees = [e for e in employees if e.primary_department_id in target_did_set or e.id in assigned_emp_ids]
    elif department_id:
        employees = [e for e in employees if e.primary_department_id == department_id]
    deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).all()
    raw_eligibilities = db.query(EmployeeDepartmentEligibility).all()
    elig_by_emp = {}
    for el in raw_eligibilities:
        d_name = departments[el.department_id].name if el.department_id in departments else ""
        d_code = departments[el.department_id].code if el.department_id in departments else ""
        elig_by_emp.setdefault(el.employee_id, []).append({
            "department_id": el.department_id,
            "department_code": d_code,
            "department_name": d_name,
            "preference_rank": el.preference_rank,
            "can_float": el.can_float
        })

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

        # Precompute employee weekly hours and shift counts to identify overtime & earned comp offs
        emp_weekly_hours = {}
        emp_weekly_shifts = {}
        for a in assignments:
            if a.shift_type_id in shifts:
                wk_key = (a.employee_id, a.date.isocalendar()[:2])
                dur = shifts[a.shift_type_id].duration_hours or 8.0
                emp_weekly_hours[wk_key] = emp_weekly_hours.get(wk_key, 0.0) + dur
                emp_weekly_shifts[wk_key] = emp_weekly_shifts.get(wk_key, 0) + 1

        # Load system settings for comp off rules
        system_settings = {s.key: s.value for s in db.query(SystemSetting).all()}
        max_comp_offs = int(system_settings.get("max_comp_offs_per_employee", 2))
        continuous_comp_off = system_settings.get("continuous_comp_off_enabled", "true").lower() in ["true", "1", "yes"]

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
            last_worked_date = None
            coff_awarded_count = 0
            consecutive_coff_count = 0

            for d in dates:
                if (emp.id, d) in assign_by_emp_date:
                    consecutive_coff_count = 0
                    a = assign_by_emp_date[(emp.id, d)]
                    s = shifts.get(a.shift_type_id)
                    dept = departments.get(a.department_id)
                    consecutive_work_days += 1

                    has_conflict = False
                    conflict_reason = None

                    # Dedicated fixed off violation check
                    if d.weekday() in emp_fixed_days:
                        has_conflict = True
                        conflict_reason = f"Violation: Assigned to work on employee's dedicated regular day off ({d.strftime('%A')})"

                    # Turnaround check: Rest interval after previous calendar day's shift
                    if last_worked_date == d - timedelta(days=1) and prev_shift and s:
                        from src.solver.rules import calculate_inter_shift_rest_hours
                        rest_hrs = calculate_inter_shift_rest_hours(prev_shift, s)
                        if rest_hrs < prev_shift.min_rest_hours_after:
                            has_conflict = True
                            conflict_reason = f"Mandatory {prev_shift.min_rest_hours_after}h rest interval after {prev_shift.name} violated ({round(rest_hrs, 1)}h rest)"

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
                    last_worked_date = d

                elif (emp.id, d) in leave_by_emp_date:
                    consecutive_work_days = 0
                    prev_shift = None
                    last_worked_date = None
                    l = leave_by_emp_date[(emp.id, d)]
                    ltype = (l.leave_type or "").upper()
                    lnotes = (l.notes or "").upper()
                    is_coff = ltype in ["COFF", "COMP_OFF"] or (ltype == "OTHER" and "COFF" in lnotes)
                    is_day_off = ltype in ["DAY_OFF", "DO"] or (ltype == "OTHER" and any(k in lnotes for k in ["DAY_OFF", "DAY OFF"]))

                    if is_coff:
                        sc_code = "COFF"
                        sc_name = l.notes or "Compensatory Off (Coff 📌)"
                        dept_col = "#D97706"
                    elif is_day_off:
                        sc_code = "DO"
                        sc_name = l.notes or "Day OFF (Locked 📌)"
                        dept_col = "#64748B"
                    else:
                        sc_code = "VAC" if ltype == "VACATION" else (l.leave_type or "LEAVE")
                        sc_name = l.notes or l.leave_type
                        dept_col = "#8B5CF6"

                    emp_assigns[d.isoformat()] = {
                        "assignment_id": None,
                        "shift_id": None,
                        "shift_code": sc_code,
                        "shift_name": sc_name,
                        "department_id": None,
                        "department_code": "",
                        "department_color": dept_col,
                        "is_floating": False,
                        "float_rank": 1,
                        "is_pinned": True,
                        "is_manual_override": False,
                        "has_conflict": False,
                        "conflict_reason": None,
                        "is_leave": not (is_coff or is_day_off),
                        "is_day_off": is_day_off,
                        "is_comp_off": is_coff,
                        "leave_type": l.leave_type,
                        "is_fixed_off": False
                    }
                    consecutive_coff_count = (consecutive_coff_count + 1) if is_coff else 0
                elif d.weekday() in emp_fixed_days:
                    consecutive_work_days = 0
                    consecutive_coff_count = 0
                    prev_shift = None
                    last_worked_date = None
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
                        "is_day_off": True,
                        "is_comp_off": False,
                        "is_fixed_off": True
                    }
                else:
                    consecutive_work_days = 0
                    prev_shift = None
                    last_worked_date = None

                    w_key = (emp.id, d.isocalendar()[:2])
                    w_hours = emp_weekly_hours.get(w_key, 0.0)
                    w_shifts = emp_weekly_shifts.get(w_key, 0)
                    contract_hours = emp.max_hours_week or 40.0
                    is_solved_plan = plan.status in ["SOLVED", "PUBLISHED"]

                    if is_solved_plan and (w_hours >= contract_hours or w_shifts >= 5):
                        # Contract fulfilled for the week!
                        is_overtime_worker = (w_shifts > 5 or w_hours > contract_hours + 0.1)
                        max_consecutive_coff = 2 if continuous_comp_off else 1
                        can_award_coff = (
                            is_overtime_worker and
                            coff_awarded_count < max_comp_offs and
                            consecutive_coff_count < max_consecutive_coff
                        )
                        if can_award_coff:
                            coff_awarded_count += 1
                            consecutive_coff_count += 1
                            emp_assigns[d.isoformat()] = {
                                "assignment_id": None,
                                "shift_id": None,
                                "shift_code": "COFF",
                                "shift_name": f"Earned Comp Off (Overtime Rest: {round(w_hours, 1)}h worked)",
                                "department_id": None,
                                "department_code": "",
                                "department_color": "#D97706",
                                "is_floating": False,
                                "float_rank": 1,
                                "is_pinned": False,
                                "is_manual_override": False,
                                "has_conflict": False,
                                "conflict_reason": None,
                                "is_leave": False,
                                "is_day_off": False,
                                "is_comp_off": True,
                                "is_earned_coff": True,
                                "earned_hours": round(w_hours, 1),
                                "leave_type": "COFF",
                                "is_fixed_off": False
                            }
                        else:
                            consecutive_coff_count = 0
                            # Standard regular Scheduled Day Off for flexible employee
                            emp_assigns[d.isoformat()] = {
                                "assignment_id": None,
                                "shift_id": None,
                                "shift_code": "DO",
                                "shift_name": "Scheduled Rest Day (Day Off)",
                                "department_id": None,
                                "department_code": "",
                                "department_color": "#64748B",
                                "is_floating": False,
                                "float_rank": 1,
                                "is_pinned": False,
                                "is_manual_override": False,
                                "has_conflict": False,
                                "conflict_reason": None,
                                "is_leave": False,
                                "is_day_off": True,
                                "is_comp_off": False,
                                "is_earned_coff": False,
                                "leave_type": "DAY_OFF",
                                "is_fixed_off": False
                            }
                    else:
                        consecutive_coff_count = 0
                        emp_assigns[d.isoformat()] = None  # Empty cell fillable by CP-SAT solver

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
                "max_hours_week": emp.max_hours_week or 40.0,
                "fixed_off_days": emp.fixed_off_days,
                "preferred_shift_type_id": emp.preferred_shift_type_id,
                "preferred_shift_code": shifts[emp.preferred_shift_type_id].code if emp.preferred_shift_type_id in shifts else None,
                "preferred_shift_name": shifts[emp.preferred_shift_type_id].name if emp.preferred_shift_type_id in shifts else None,
                "eligibilities": elig_by_emp.get(emp.id, []),
                "assignments": emp_assigns,
                "previous_month_summary": prev_emp_summaries.get(emp.id)
            })

        deficits_by_date = {}
        deficits_list_by_date = {}
        for d in deficits:
            d_str = d.date.isoformat()
            dept_code = departments[d.department_id].code if d.department_id in departments else ""
            s_code = shifts[d.shift_type_id].code if d.shift_type_id in shifts else ""
            d_dict = {
                "deficit_id": d.id,
                "department_id": d.department_id,
                "department_code": dept_code,
                "shift_type_id": d.shift_type_id,
                "shift_code": s_code,
                "shortage_count": d.shortage_count,
                "reason_code": d.reason_code
            }
            deficits_list_by_date.setdefault(d_str, []).append(d_dict)
            if d_str not in deficits_by_date:
                deficits_by_date[d_str] = {
                    "deficit_id": d.id,
                    "department_id": d.department_id,
                    "department_code": dept_code,
                    "shift_type_id": d.shift_type_id,
                    "shift_code": s_code,
                    "shortage_count": d.shortage_count,
                    "reason_code": d.reason_code,
                    "all_deficits": [d_dict]
                }
            else:
                entry = deficits_by_date[d_str]
                entry["shortage_count"] += d.shortage_count
                if s_code:
                    existing_codes = [c.strip() for c in entry["shift_code"].split(",") if c.strip()]
                    if s_code not in existing_codes:
                        entry["shift_code"] = f"{entry['shift_code']}, {s_code}" if entry["shift_code"] else s_code
                entry["all_deficits"].append(d_dict)

        dept_ids_list = [int(x) for x in plan.department_ids.split(",") if x.isdigit()] if plan.department_ids else []
        scope_lbl = ", ".join(departments[int(x)].name for x in plan.department_ids.split(",") if int(x) in departments) if plan.department_ids else "All Departments"

        return {
            "department_ids": dept_ids_list,
            "scope_label": scope_lbl,
            "plan": {
                "id": plan.id,
                "session_id": plan.session_id,
                "name": plan.name,
                "department_ids": dept_ids_list,
                "scope_label": scope_lbl,
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
            "deficits_by_date": deficits_by_date,
            "deficits_list_by_date": deficits_list_by_date,
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

        dept_ids_list = [int(x) for x in plan.department_ids.split(",") if x.isdigit()] if plan.department_ids else []
        scope_lbl = ", ".join(departments[int(x)].name for x in plan.department_ids.split(",") if int(x) in departments) if plan.department_ids else "All Departments"

        return {
            "plan_id": plan.id,
            "department_ids": dept_ids_list,
            "scope_label": scope_lbl,
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

    # Check if this assignment resolves an existing deficit log
    deficit_match = db.query(DeficitLog).filter(
        DeficitLog.plan_id == plan_id,
        DeficitLog.department_id == req.department_id,
        DeficitLog.shift_type_id == req.shift_type_id,
        DeficitLog.date == req.date
    ).first()
    if deficit_match:
        if deficit_match.shortage_count > 1:
            deficit_match.shortage_count -= 1
        else:
            db.delete(deficit_match)
        db.flush()
        plan.total_deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).count()

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

    cleared = False
    if existing:
        db.delete(existing)
        cleared = True

    # Also remove any 1-day DAY_OFF or COFF leave record so the cell becomes genuinely EMPTY/fillable by the solver
    leaves = db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == employee_id,
        LeaveRecord.start_date == date,
        LeaveRecord.end_date == date
    ).all()
    for l in leaves:
        ltype = (l.leave_type or "").upper()
        lnotes = (l.notes or "").upper()
        if ltype in ["DAY_OFF", "DO", "COFF", "COMP_OFF"] or (ltype == "OTHER" and any(k in lnotes for k in ["DAY_OFF", "DAY OFF", "COFF", "COMP_OFF"])):
            db.delete(l)
            cleared = True

    if cleared:
        plan.status = "DRAFT"

    db.commit()
    return {"message": "Cell cleared and set as empty (fillable by solver).", "cleared": cleared}

@router.post("/{plan_id}/pin-off")
def pin_day_off(plan_id: int, req: PinOffRequest, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found.")

    # Remove any existing RosterAssignment for this employee on this date
    db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.employee_id == req.employee_id,
        RosterAssignment.date == req.date
    ).delete()

    normalized_type = "COFF" if req.off_type.upper() in ["COFF", "COMP_OFF"] else "DAY_OFF"
    notes_val = req.notes or ("Compensatory Off" if normalized_type == "COFF" else "Pinned Day OFF")

    # Update or insert 1-day LeaveRecord
    existing_leave = db.query(LeaveRecord).filter(
        LeaveRecord.employee_id == req.employee_id,
        LeaveRecord.start_date == req.date,
        LeaveRecord.end_date == req.date
    ).first()

    try:
        if existing_leave:
            existing_leave.leave_type = normalized_type
            existing_leave.status = "APPROVED"
            existing_leave.notes = notes_val
        else:
            new_leave = LeaveRecord(
                employee_id=req.employee_id,
                start_date=req.date,
                end_date=req.date,
                leave_type=normalized_type,
                status="APPROVED",
                notes=notes_val
            )
            db.add(new_leave)
        db.commit()
    except Exception:
        db.rollback()
        # Fallback to OTHER with notes indicating off type for older check constraints
        if existing_leave:
            existing_leave.leave_type = "OTHER"
            existing_leave.status = "APPROVED"
            existing_leave.notes = normalized_type
        else:
            new_leave = LeaveRecord(
                employee_id=req.employee_id,
                start_date=req.date,
                end_date=req.date,
                leave_type="OTHER",
                status="APPROVED",
                notes=normalized_type
            )
            db.add(new_leave)
        db.commit()

    return {
        "success": True,
        "employee_id": req.employee_id,
        "date": req.date.isoformat(),
        "off_type": normalized_type,
        "message": f"Cell pinned as {normalized_type} for {emp.name}."
    }

@router.delete("/{plan_id}/clear-all")
@router.post("/{plan_id}/clear-all")
def clear_all_assignments(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    deleted_assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).delete()
    deleted_deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).delete()
    plan.status = "DRAFT"
    plan.solver_status = "RESET"
    plan.total_deficits = 0
    plan.total_floats = 0
    db.commit()
    return {
        "cleared": True,
        "deleted_assignments": deleted_assignments,
        "deleted_deficits": deleted_deficits,
        "message": f"Successfully cleared all {deleted_assignments} assignment(s) and {deleted_deficits} deficit(s). Canvas is reset to blank."
    }


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

@router.post("/{plan_id}/resolve-conflicts")
def resolve_plan_conflicts(plan_id: int, db: Session = Depends(get_db)):
    """Automatically identify and remove conflicting assignments:
    1. Assigned on dedicated fixed day off.
    2. Mandatory rest interval turnaround violation after previous day shift.
    3. Exceeds max 5 consecutive days limit.
    4. Overlaps with approved leave.
    """
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).order_by(RosterAssignment.date).all()
    employees = {e.id: e for e in db.query(Employee).all()}
    shifts = {s.id: s for s in db.query(ShiftType).all()}
    leaves = db.query(LeaveRecord).filter(
        LeaveRecord.status == "APPROVED",
        LeaveRecord.start_date <= plan.end_date,
        LeaveRecord.end_date >= plan.start_date
    ).all()
    leave_set = set()
    for l in leaves:
        cur = l.start_date
        while cur <= l.end_date:
            leave_set.add((l.employee_id, cur))
            cur += timedelta(days=1)

    assign_by_emp = {}
    for a in assignments:
        assign_by_emp.setdefault(a.employee_id, []).append(a)

    resolved = []
    from src.solver.rules import calculate_inter_shift_rest_hours

    for emp_id, emp_assigns in assign_by_emp.items():
        emp = employees.get(emp_id)
        if not emp:
            continue
        fixed_days = []
        if emp.fixed_off_days:
            try:
                fixed_days = [int(x.strip()) for x in emp.fixed_off_days.split(",") if x.strip().isdigit()]
            except Exception:
                pass

        emp_assigns.sort(key=lambda x: x.date)
        prev_a = None
        consecutive_streak = 0
        last_date = None

        for a in list(emp_assigns):
            to_remove = False
            reason = ""

            if (emp_id, a.date) in leave_set:
                to_remove = True
                reason = "Removed shift overlapping with approved leave"
            elif a.date.weekday() in fixed_days:
                to_remove = True
                reason = f"Removed shift on employee's dedicated regular day off ({a.date.strftime('%A')})"
            else:
                if last_date == a.date - timedelta(days=1):
                    consecutive_streak += 1
                else:
                    consecutive_streak = 1
                last_date = a.date

                if consecutive_streak > 5:
                    to_remove = True
                    reason = f"Removed 6th consecutive day shift ({a.date})"
                    consecutive_streak = 0
                    last_date = None
                elif prev_a and prev_a.date == a.date - timedelta(days=1):
                    s_prev = shifts.get(prev_a.shift_type_id)
                    s_curr = shifts.get(a.shift_type_id)
                    if s_prev and s_curr:
                        rest_hrs = calculate_inter_shift_rest_hours(s_prev, s_curr)
                        if rest_hrs < s_prev.min_rest_hours_after:
                            to_remove = True
                            reason = f"Removed shift violating turnaround rest interval ({round(rest_hrs, 1)}h < {s_prev.min_rest_hours_after}h)"

            if to_remove:
                resolved.append({
                    "employee_id": emp_id,
                    "employee_name": emp.name,
                    "date": a.date.isoformat(),
                    "reason": reason
                })
                db.delete(a)
                emp_assigns.remove(a)
            else:
                prev_a = a

    db.commit()
    return {
        "message": f"Successfully auto-resolved {len(resolved)} labor conflicts.",
        "resolved_count": len(resolved),
        "resolved_items": resolved
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

@router.post("/{plan_id}/resolve-all-deficits")
def resolve_all_deficits(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).all()
    if not deficits:
        return {"resolved_count": 0, "message": "No shortages to resolve."}

    all_emps = db.query(Employee).filter(Employee.is_active == True).all()
    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    leaves = db.query(LeaveRecord).all()
    raw_elig = db.query(EmployeeDepartmentEligibility).all()
    eligs = {(e.employee_id, e.department_id): e.preference_rank for e in raw_elig}

    resolved_count = 0
    for d in deficits:
        while d.shortage_count > 0:
            working_today = {a.employee_id for a in assignments if a.date == d.date}
            candidates = []
            for emp in all_emps:
                if emp.id in working_today:
                    continue
                has_vac = any(
                    l.employee_id == emp.id and l.start_date <= d.date <= l.end_date and l.status == "APPROVED"
                    for l in leaves
                )
                if has_vac:
                    continue
                val = validate_assignment_candidate(emp, d.department, d.shift_type, d.date, assignments, leaves)
                is_float = (emp.primary_department_id != d.department_id)
                candidates.append({
                    "emp": emp,
                    "is_float": is_float,
                    "violation_count": 0 if val["is_valid"] else len(val["violations"])
                })

            if not candidates:
                break

            candidates.sort(key=lambda x: (x["violation_count"], 1 if x["is_float"] else 0))
            chosen_cand = candidates[0]
            chosen = chosen_cand["emp"]
            is_float = chosen_cand["is_float"]
            float_rank = eligs.get((chosen.id, d.department_id), 2 if is_float else 1)

            new_a = RosterAssignment(
                plan_id=plan_id,
                employee_id=chosen.id,
                department_id=d.department_id,
                shift_type_id=d.shift_type_id,
                date=d.date,
                assignment_source="MANUAL_OVERRIDE",
                is_pinned=True,
                is_manual_override=True,
                is_floating=is_float,
                float_rank=float_rank
            )
            new_a.shift_type = d.shift_type
            new_a.department = d.department
            db.add(new_a)
            assignments.append(new_a)
            d.shortage_count -= 1
            resolved_count += 1

        if d.shortage_count == 0:
            db.delete(d)

    db.flush()
    plan.total_deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).count()
    db.commit()
    return {
        "resolved_count": resolved_count,
        "remaining_deficits": plan.total_deficits,
        "message": f"Successfully auto-resolved {resolved_count} shortage(s) by authorizing overtime coverage."
    }

@router.delete("/{plan_id}/deficits/{deficit_id}")
def waive_deficit(plan_id: int, deficit_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    deficit = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id, DeficitLog.id == deficit_id).first()
    if not deficit:
        raise HTTPException(status_code=404, detail="Deficit not found.")

    db.delete(deficit)
    db.flush()
    plan.total_deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).count()
    db.commit()
    return {
        "message": "Shortage waived / marked on-call. Deficit removed.",
        "remaining_deficits": plan.total_deficits
    }

@router.post("/{plan_id}/auto-award-compoffs")
def auto_award_compoffs(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    system_settings = {s.key: s.value for s in db.query(SystemSetting).all()}
    max_comp_offs = int(system_settings.get("max_comp_offs_per_employee", 2))
    continuous_comp_off = system_settings.get("continuous_comp_off_enabled", "true").lower() in ["true", "1", "yes"]
    max_consecutive = 2 if continuous_comp_off else 1

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    shifts = {s.id: s for s in db.query(ShiftType).all()}
    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    leaves = db.query(LeaveRecord).all()

    assign_by_emp = {}
    for a in assignments:
        assign_by_emp.setdefault(a.employee_id, {})[a.date] = a

    leave_by_emp_date = set()
    for l in leaves:
        cur = l.start_date
        while cur <= l.end_date:
            leave_by_emp_date.add((l.employee_id, cur))
            cur += timedelta(days=1)

    horizon_days = (plan.end_date - plan.start_date).days + 1
    dates = [plan.start_date + timedelta(days=t) for t in range(horizon_days)]

    awarded_count = 0
    for emp in employees:
        emp_assigns = assign_by_emp.get(emp.id, {})
        emp_coff_count = sum(
            1 for l in leaves
            if l.employee_id == emp.id and l.leave_type in ["COFF", "OTHER"] and plan.start_date <= l.start_date <= plan.end_date
        )

        weeks = {}
        for d in dates:
            iso_yr, iso_wk, _ = d.isocalendar()
            weeks.setdefault((iso_yr, iso_wk), []).append(d)

        for (iso_yr, iso_wk), w_dates in weeks.items():
            if emp_coff_count >= max_comp_offs:
                break

            worked_shifts = [emp_assigns[d] for d in w_dates if d in emp_assigns and emp_assigns[d].shift_type_id in shifts]
            total_hours = sum(shifts[a.shift_type_id].duration_hours for a in worked_shifts)
            shift_count = len(worked_shifts)

            contract_cap = emp.max_hours_week or 40.0
            if total_hours >= contract_cap or shift_count >= 5:
                # Find off days in this week
                unassigned_days = sorted([d for d in w_dates if d not in emp_assigns and (emp.id, d) not in leave_by_emp_date])
                for target_day in unassigned_days:
                    if emp_coff_count >= max_comp_offs:
                        break

                    # Check contiguous consecutive COFF streak (backward and forward) around target_day
                    streak = 1
                    chk = target_day - timedelta(days=1)
                    while any(
                        l.employee_id == emp.id
                        and l.start_date <= chk <= l.end_date
                        and l.leave_type in ["COFF", "OTHER"]
                        and getattr(l, "status", "APPROVED") != "CANCELLED"
                        for l in leaves
                    ):
                        streak += 1
                        chk -= timedelta(days=1)

                    chk = target_day + timedelta(days=1)
                    while any(
                        l.employee_id == emp.id
                        and l.start_date <= chk <= l.end_date
                        and l.leave_type in ["COFF", "OTHER"]
                        and getattr(l, "status", "APPROVED") != "CANCELLED"
                        for l in leaves
                    ):
                        streak += 1
                        chk += timedelta(days=1)

                    if streak > max_consecutive:
                        continue

                    try:
                        new_leave = LeaveRecord(
                            employee_id=emp.id,
                            start_date=target_day,
                            end_date=target_day,
                            leave_type="COFF",
                            notes=f"Earned Comp Off (Overtime Holiday: {round(total_hours, 1)}h worked in Wk {iso_wk})",
                            status="APPROVED"
                        )
                        db.add(new_leave)
                        db.flush()
                        leaves.append(new_leave)
                    except Exception:
                        db.rollback()
                        new_leave = LeaveRecord(
                            employee_id=emp.id,
                            start_date=target_day,
                            end_date=target_day,
                            leave_type="OTHER",
                            notes=f"COFF: Earned Holiday ({round(total_hours, 1)}h overtime worked in Wk {iso_wk})",
                            status="APPROVED"
                        )
                        db.add(new_leave)
                        db.flush()
                        leaves.append(new_leave)
                    leave_by_emp_date.add((emp.id, target_day))
                    emp_coff_count += 1
                    awarded_count += 1

    db.commit()
    return {
        "awarded_count": awarded_count,
        "message": f"Successfully awarded and pinned {awarded_count} Compensatory Off (COFF) holiday(s) for employees who worked overtime."
    }
