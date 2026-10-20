"""Roster planning, solver execution, drag-and-drop validation, and variants API."""
import calendar
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import RosterPlan, RosterAssignment, DeficitLog, Department, ShiftType, Employee
from src.api.schemas import (
    GenerateRosterRequest, ValidateAssignmentRequest,
    ManualAssignmentRequest, PrefillShiftsRequest
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

    if view == "staff_centric":
        # Group by employee
        rows = []
        assign_by_emp_date = {(a.employee_id, a.date): a for a in assignments}

        for emp in employees:
            if department_id and emp.primary_department_id != department_id:
                continue

            emp_assigns = {}
            for d in dates:
                if (emp.id, d) in assign_by_emp_date:
                    a = assign_by_emp_date[(emp.id, d)]
                    s = shifts.get(a.shift_type_id)
                    dept = departments.get(a.department_id)
                    emp_assigns[d.isoformat()] = {
                        "assignment_id": a.id,
                        "shift_id": a.shift_type_id,
                        "shift_code": s.code if s else "",
                        "shift_name": s.name if s else "",
                        "department_id": a.department_id,
                        "department_code": dept.code if dept else "",
                        "is_floating": a.is_floating,
                        "float_rank": a.float_rank,
                        "is_pinned": a.is_pinned,
                        "is_manual_override": a.is_manual_override
                    }
                else:
                    emp_assigns[d.isoformat()] = None

            rows.append({
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "employee_name": emp.name,
                "primary_department_id": emp.primary_department_id,
                "primary_department_name": departments[emp.primary_department_id].name if emp.primary_department_id in departments else "",
                "primary_department_code": departments[emp.primary_department_id].code if emp.primary_department_id in departments else "",
                "assignments": emp_assigns
            })

        return {
            "plan": {
                "id": plan.id,
                "session_id": plan.session_id,
                "name": plan.name,
                "variant_name": plan.variant_name,
                "start_date": plan.start_date.isoformat(),
                "end_date": plan.end_date.isoformat(),
                "status": plan.status,
                "solver_status": plan.solver_status,
                "total_deficits": plan.total_deficits,
                "total_floats": plan.total_floats
            },
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
                            "is_pinned": a.is_pinned
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
                        "shift_type_id": s_id,
                        "shift_code": shift.code,
                        "shift_name": shift.name,
                        "assigned_staff": worker_data,
                        "assigned_count": len(worker_data),
                        "deficit": def_entry.shortage_count if def_entry else 0
                    })

        return {
            "plan_id": plan.id,
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
