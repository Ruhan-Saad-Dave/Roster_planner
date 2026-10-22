"""Core business service for plan creation, solving, variants, and drag-and-drop editing."""
import uuid
from datetime import date, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from sqlalchemy.orm import Session
from src.db.models import (
    RosterPlan, RosterAssignment, DeficitLog,
    Department, ShiftType, DepartmentRequirement,
    Employee, EmployeeDepartmentEligibility, EmployeeShiftPreference,
    LeaveRecord
)
from src.solver.model import SchedulingContext
from src.solver.engine import solve_roster, generate_roster_variants, SolveResult
from src.solver.rules import validate_assignment_candidate

def build_context_from_db(
    db: Session,
    start_date: date,
    end_date: date,
    pinned_assignments: Optional[Dict[Tuple, Tuple]] = None,
    pinned_offs: Optional[Set] = None,
    weights: Optional[Dict[str, int]] = None,
    max_consecutive_days: int = 5,
    min_rest_days_per_week: int = 2,
    target_department_ids: Optional[List[int]] = None
) -> SchedulingContext:
    horizon_days = (end_date - start_date).days + 1

    departments_q = db.query(Department).filter(Department.is_active == True)
    if target_department_ids:
        departments_q = departments_q.filter(Department.id.in_(target_department_ids))
    departments = departments_q.all()
    active_dept_ids = {d.id for d in departments}

    all_employees = db.query(Employee).filter(Employee.is_active == True).all()
    if target_department_ids:
        eligs_for_target = db.query(EmployeeDepartmentEligibility).filter(
            EmployeeDepartmentEligibility.department_id.in_(target_department_ids)
        ).all()
        target_eligible_emp_ids = {e.employee_id for e in eligs_for_target}
        employees = [e for e in all_employees if e.primary_department_id in active_dept_ids or e.id in target_eligible_emp_ids]
    else:
        employees = all_employees

    shifts = db.query(ShiftType).filter(ShiftType.is_active == True).all()

    # 1. Demand Matrix
    reqs = db.query(DepartmentRequirement).all()
    req_map = {}  # (dept_id, shift_id, dow) -> min_staff
    for r in reqs:
        req_map[(r.department_id, r.shift_type_id, r.day_of_week)] = r.min_staff

    demand_matrix = {}
    for d in departments:
        dept_has_reqs = any(dept_id == d.id for (dept_id, s_id, dow) in req_map.keys())
        for s in shifts:
            for t in range(horizon_days):
                cur_date = start_date + timedelta(days=t)
                dow = cur_date.weekday()

                # If department is closed (e.g. weekdays-only on weekend), demand is 0
                if d.operating_regime == "WEEKDAYS_ONLY" and dow in [5, 6]:
                    demand_matrix[(d.id, s.id, t)] = 0
                else:
                    if dept_has_reqs:
                        demand_matrix[(d.id, s.id, t)] = req_map.get((d.id, s.id, dow), 0)
                    else:
                        # Auto-default for newly created / unconfigured departments:
                        # Minimum 1 staff per shift so active workforce gets scheduled!
                        demand_matrix[(d.id, s.id, t)] = 1

    # 2. Eligibilities
    eligs = db.query(EmployeeDepartmentEligibility).all()
    elig_dict = {}
    for e in eligs:
        elig_dict[(e.employee_id, e.department_id)] = (e.preference_rank, e.can_float)

    # 3. Preferences
    prefs = db.query(EmployeeShiftPreference).all()
    pref_dict = {}
    for p in prefs:
        pref_dict[(p.employee_id, p.shift_type_id, p.day_of_week)] = p.preference_score

    # 4. Approved Leaves
    leaves = db.query(LeaveRecord).filter(
        LeaveRecord.status == "APPROVED",
        LeaveRecord.start_date <= end_date,
        LeaveRecord.end_date >= start_date
    ).all()
    approved_leaves = set()
    for l in leaves:
        for t in range(horizon_days):
            cur_date = start_date + timedelta(days=t)
            if l.start_date <= cur_date <= l.end_date:
                approved_leaves.add((l.employee_id, t))

    # 5. Dedicated Recurring Days Off from Employee Profile
    combined_pinned_offs = set(pinned_offs or set())
    for e in employees:
        if e.fixed_off_days:
            try:
                fixed_days = [int(x.strip()) for x in e.fixed_off_days.split(",") if x.strip().isdigit()]
                for t in range(horizon_days):
                    cur_date = start_date + timedelta(days=t)
                    if cur_date.weekday() in fixed_days:
                        combined_pinned_offs.add((e.id, t))
            except Exception:
                pass

    # Pinned work shifts take precedence over off-locks
    for (emp_id, t) in (pinned_assignments or {}).keys():
        approved_leaves.discard((emp_id, t))
        combined_pinned_offs.discard((emp_id, t))

    return SchedulingContext(
        employees=employees,
        departments=departments,
        shifts=shifts,
        horizon_days=horizon_days,
        start_date=start_date,
        demand_matrix=demand_matrix,
        eligibilities=elig_dict,
        preferences=pref_dict,
        approved_leaves=approved_leaves,
        pinned_assignments=pinned_assignments or {},
        pinned_offs=combined_pinned_offs,
        max_consecutive_days=max_consecutive_days,
        min_rest_days_per_week=min_rest_days_per_week,
        weights=weights
    )

def save_solve_result_to_db(
    db: Session,
    plan_name: str,
    start_date: date,
    end_date: date,
    result: SolveResult,
    session_id: str,
    planning_year: Optional[int] = None,
    planning_month: Optional[int] = None,
    is_active: bool = True,
    department_ids: Optional[str] = None
) -> RosterPlan:
    plan = RosterPlan(
        name=plan_name,
        department_ids=department_ids,
        session_id=session_id,
        variant_name=f"Variant ({result.strategy_name.title()})",
        variant_strategy=result.strategy_name,
        is_active_variant=is_active,
        planning_year=planning_year or start_date.year,
        planning_month=planning_month or start_date.month,
        start_date=start_date,
        end_date=end_date,
        status="SOLVED",
        solver_status=result.status,
        solve_time_seconds=result.solve_time_seconds,
        objective_score=result.objective_score,
        total_deficits=len(result.deficits),
        total_floats=sum(1 for a in result.assignments if a["is_floating"])
    )
    db.add(plan)
    db.flush()

    # Save assignments
    for a in result.assignments:
        assign = RosterAssignment(
            plan_id=plan.id,
            employee_id=a["employee_id"],
            department_id=a["department_id"],
            shift_type_id=a["shift_type_id"],
            date=a["date"],
            assignment_source="PREFILLED" if a.get("is_pinned") else "SOLVER",
            is_pinned=a.get("is_pinned", False),
            is_manual_override=False,
            is_floating=a["is_floating"],
            float_rank=a["float_rank"]
        )
        db.add(assign)

    # Save deficit logs
    for d in result.deficits:
        deficit_log = DeficitLog(
            plan_id=plan.id,
            department_id=d["department_id"],
            shift_type_id=d["shift_type_id"],
            date=d["date"],
            shortage_count=d["shortage_count"],
            reason_code=d["reason_code"]
        )
        db.add(deficit_log)

    db.commit()
    return plan

def generate_roster_plan(
    db: Session,
    name: str,
    start_date: date,
    end_date: date,
    planning_year: Optional[int] = None,
    planning_month: Optional[int] = None,
    target_department_ids: Optional[List[int]] = None,
    variant_count: int = 1,
    variant_strategies: Optional[List[str]] = None,
    timeout_seconds: int = 15,
    max_consecutive_days: int = 5,
    min_rest_days_per_week: int = 2,
    weights: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    ctx = build_context_from_db(
        db, start_date, end_date,
        weights=weights,
        max_consecutive_days=max_consecutive_days,
        min_rest_days_per_week=min_rest_days_per_week,
        target_department_ids=target_department_ids
    )

    dept_ids_str = ",".join(str(x) for x in sorted(target_department_ids)) if target_department_ids else None

    if variant_count <= 1:
        res = solve_roster(ctx, timeout_seconds=timeout_seconds, strategy_name="BALANCED")
        plan = save_solve_result_to_db(
            db, name, start_date, end_date, res, session_id,
            planning_year, planning_month, is_active=True,
            department_ids=dept_ids_str
        )
        return {
            "session_id": session_id,
            "primary_plan": plan,
            "variants": [plan]
        }
    else:
        strats = variant_strategies or ["BALANCED", "FLOAT_AVERSE", "PREFERENCE_MAX"][:variant_count]
        results = generate_roster_variants(ctx, strategies=strats, timeout_seconds=timeout_seconds)
        plans = []
        for i, res in enumerate(results):
            p = save_solve_result_to_db(
                db, f"{name} - {res.strategy_name}", start_date, end_date, res, session_id,
                planning_year, planning_month, is_active=(i == 0),
                department_ids=dept_ids_str
            )
            plans.append(p)
        return {
            "session_id": session_id,
            "primary_plan": plans[0],
            "variants": plans
        }

def solve_remaining_blank_slots(
    db: Session,
    plan_id: int,
    timeout_seconds: int = 15
) -> RosterPlan:
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise ValueError(f"Plan {plan_id} not found.")

    # Collect pinned assignments
    existing_assignments = db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.is_pinned == True
    ).order_by(RosterAssignment.employee_id, RosterAssignment.date).all()

    # Pre-solve sanitization: sanitize conflicting pinned shifts to prevent INFEASIBLE solver crash
    from src.solver.rules import calculate_inter_shift_rest_hours
    target_depts = [int(x) for x in plan.department_ids.split(",") if x.isdigit()] if plan.department_ids else None
    base_ctx = build_context_from_db(db, plan.start_date, plan.end_date, target_department_ids=target_depts)
    shifts_map = {s.id: s for s in base_ctx.shifts}
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
    for a in existing_assignments:
        assign_by_emp.setdefault(a.employee_id, []).append(a)

    sanitized_pinned = []
    conflicted_pinned = []
    slot_pinned_counts = {}

    for emp_id, emp_pins in assign_by_emp.items():
        emp_pins.sort(key=lambda x: x.date)
        valid_dates = []
        valid_shifts_by_date = {}

        for a in emp_pins:
            is_conflicted = False
            t = (a.date - plan.start_date).days
            slot_key = (a.department_id, a.shift_type_id, t)
            req_demand = base_ctx.demand.get(slot_key, 0)

            # 0. Zero demand, slot capacity, or employee department eligibility
            if req_demand <= 0:
                is_conflicted = True
            elif slot_pinned_counts.get(slot_key, 0) >= req_demand:
                is_conflicted = True
            elif not base_ctx.is_eligible(emp_id, a.department_id):
                is_conflicted = True

            # 1. Leave overlap
            elif (emp_id, a.date) in leave_set:
                is_conflicted = True

            # 2. Duplicate assignment on same date
            elif a.date in valid_shifts_by_date:
                is_conflicted = True

            else:
                # 3. Inter-shift turnaround rest interval with preceding day
                prev_d = a.date - timedelta(days=1)
                if prev_d in valid_shifts_by_date:
                    prev_s = shifts_map.get(valid_shifts_by_date[prev_d].shift_type_id)
                    curr_s = shifts_map.get(a.shift_type_id)
                    if prev_s and curr_s:
                        rest_hrs = calculate_inter_shift_rest_hours(prev_s, curr_s)
                        min_rest = getattr(prev_s, "min_rest_hours_after", 14) or 14
                        if rest_hrs < min_rest:
                            is_conflicted = True

                # 4. Turnaround rest interval with following day (if already in valid)
                next_d = a.date + timedelta(days=1)
                if not is_conflicted and next_d in valid_shifts_by_date:
                    next_s = shifts_map.get(valid_shifts_by_date[next_d].shift_type_id)
                    curr_s = shifts_map.get(a.shift_type_id)
                    if curr_s and next_s:
                        rest_hrs = calculate_inter_shift_rest_hours(curr_s, next_s)
                        min_rest = getattr(curr_s, "min_rest_hours_after", 14) or 14
                        if rest_hrs < min_rest:
                            is_conflicted = True

                # 5. Consecutive streak > 5
                if not is_conflicted:
                    streak = 1
                    chk = a.date - timedelta(days=1)
                    while chk in valid_shifts_by_date:
                        streak += 1
                        chk -= timedelta(days=1)
                    chk = a.date + timedelta(days=1)
                    while chk in valid_shifts_by_date:
                        streak += 1
                        chk += timedelta(days=1)
                    if streak > 5:
                        is_conflicted = True

                # 6. Rolling 7-day window rest: in any 7-day window containing a.date, sum <= 5
                if not is_conflicted:
                    all_dates_sim = set(valid_dates) | {a.date}
                    for start_offset in range(7):
                        win_start = a.date - timedelta(days=start_offset)
                        win_count = sum(1 for k in range(7) if (win_start + timedelta(days=k)) in all_dates_sim)
                        if win_count > 5:
                            is_conflicted = True
                            break

            if is_conflicted:
                conflicted_pinned.append(a)
            else:
                valid_dates.append(a.date)
                valid_shifts_by_date[a.date] = a
                slot_pinned_counts[slot_key] = slot_pinned_counts.get(slot_key, 0) + 1
                sanitized_pinned.append(a)

    # Purge conflicting assignments from DB and session
    for ca in conflicted_pinned:
        ca.is_pinned = False
        db.delete(ca)
    db.flush()

    pinned_dict = {}
    for a in sanitized_pinned:
        t = (a.date - plan.start_date).days
        pinned_dict[(a.employee_id, t)] = (a.department_id, a.shift_type_id)

    ctx = build_context_from_db(
        db, plan.start_date, plan.end_date,
        pinned_assignments=pinned_dict,
        target_department_ids=target_depts
    )

    res = solve_roster(ctx, timeout_seconds=timeout_seconds, strategy_name=plan.variant_strategy)

    # Fallback shield: if CP-SAT still returns INFEASIBLE, solve with base context
    if res.status == "INFEASIBLE":
        # Clear all assignments for this plan to avoid UNIQUE constraint violations on relaxed insert
        for p_obj in db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all():
            db.delete(p_obj)
        db.flush()
        ctx_relaxed = build_context_from_db(db, plan.start_date, plan.end_date)
        res = solve_roster(ctx_relaxed, timeout_seconds=timeout_seconds, strategy_name=plan.variant_strategy)

    # Delete non-pinned assignments and deficits
    db.query(RosterAssignment).filter(
        RosterAssignment.plan_id == plan_id,
        RosterAssignment.is_pinned == False
    ).delete()
    db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).delete()

    # Insert newly solved non-pinned assignments
    for a in res.assignments:
        if not a.get("is_pinned"):
            assign = RosterAssignment(
                plan_id=plan.id,
                employee_id=a["employee_id"],
                department_id=a["department_id"],
                shift_type_id=a["shift_type_id"],
                date=a["date"],
                assignment_source="SOLVER",
                is_pinned=False,
                is_manual_override=False,
                is_floating=a["is_floating"],
                float_rank=a["float_rank"]
            )
            db.add(assign)

    for d in res.deficits:
        deficit_log = DeficitLog(
            plan_id=plan.id,
            department_id=d["department_id"],
            shift_type_id=d["shift_type_id"],
            date=d["date"],
            shortage_count=d["shortage_count"],
            reason_code=d["reason_code"]
        )
        db.add(deficit_log)

    plan.status = "SOLVED"
    plan.solver_status = res.status
    plan.solve_time_seconds = res.solve_time_seconds
    plan.objective_score = res.objective_score
    plan.total_deficits = len(res.deficits)
    plan.total_floats = sum(1 for a in res.assignments if a["is_floating"])

    db.commit()
    db.refresh(plan)
    return plan

def validate_drag_and_drop_move(
    db: Session,
    plan_id: int,
    employee_id: int,
    target_dept_id: int,
    target_shift_id: int,
    target_date: date
) -> Dict[str, Any]:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    target_dept = db.query(Department).filter(Department.id == target_dept_id).first()
    target_shift = db.query(ShiftType).filter(ShiftType.id == target_shift_id).first()
    if not emp or not target_dept or not target_shift:
        raise ValueError("Invalid employee, department, or shift ID.")

    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    leaves = db.query(LeaveRecord).filter(LeaveRecord.employee_id == employee_id).all()

    return validate_assignment_candidate(emp, target_dept, target_shift, target_date, assignments, leaves)

def generate_shortage_fix_recommendations(
    db: Session,
    plan_id: int,
    deficit_id: int
) -> List[Dict[str, Any]]:
    deficit = db.query(DeficitLog).filter(DeficitLog.id == deficit_id).first()
    if not deficit:
        return []

    dept = deficit.department
    shift = deficit.shift_type
    target_date = deficit.date

    # Find off-duty employees who are eligible and produce 0 hard violations
    all_emps = db.query(Employee).filter(Employee.is_active == True).all()
    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    leaves = db.query(LeaveRecord).all()

    working_emps_today = {a.employee_id for a in assignments if a.date == target_date}

    recommendations = []
    overtime_candidates = []

    for emp in all_emps:
        if emp.id in working_emps_today:
            continue

        # Skip if on approved leave
        has_vacation = any(
            l.employee_id == emp.id and l.start_date <= target_date <= l.end_date and l.status == "APPROVED"
            for l in leaves
        )
        if has_vacation:
            continue

        eval_res = validate_assignment_candidate(emp, dept, shift, target_date, assignments, leaves)
        is_float = (emp.primary_department_id != dept.id)
        rank = 1
        if is_float:
            eligs = {el.department_id: el.preference_rank for el in emp.eligibilities}
            rank = eligs.get(dept.id, 2)

        if eval_res["is_valid"]:
            recommendations.append({
                "employee_id": emp.id,
                "employee_name": emp.name,
                "primary_dept": emp.primary_department.name,
                "is_floating": is_float,
                "float_rank": rank,
                "is_overtime": False,
                "description": f"Assign {emp.name} ({'Floater from ' + emp.primary_department.code if is_float else 'Off-duty Staff'}). Zero ergonomic conflicts."
            })
            if len(recommendations) >= 3:
                break
        else:
            v_msgs = [v["message"] for v in eval_res.get("violations", [])]
            summary_msg = "; ".join(v_msgs)
            if len(summary_msg) > 80:
                summary_msg = summary_msg[:77] + "..."
            overtime_candidates.append({
                "employee_id": emp.id,
                "employee_name": emp.name,
                "primary_dept": emp.primary_department.name,
                "is_floating": is_float,
                "float_rank": rank,
                "is_overtime": True,
                "violation_count": len(eval_res.get("violations", [])),
                "description": f"Authorize Overtime for {emp.name} ({summary_msg})"
            })

    # If no zero-conflict candidates exist, offer the best overtime/exception candidates!
    if not recommendations and overtime_candidates:
        overtime_candidates.sort(key=lambda x: x["violation_count"])
        recommendations.extend(overtime_candidates[:3])

    return recommendations
