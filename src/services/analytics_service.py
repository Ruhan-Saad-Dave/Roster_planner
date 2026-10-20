"""Analytics service calculating manager workload scorecards, fairness metrics, and coverage trends."""
from typing import Dict, List, Any, Optional
from datetime import timedelta
from sqlalchemy.orm import Session
from src.db.models import RosterPlan, RosterAssignment, Employee, Department, ShiftType, DeficitLog

def get_workload_audit_scorecard(db: Session, plan_id: int) -> Dict[str, Any]:
    """Calculate the comprehensive workload audit scorecard for each employee on a given plan."""
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise ValueError(f"Plan {plan_id} not found.")

    horizon_days = (plan.end_date - plan.start_date).days + 1
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    departments = {d.id: d for d in db.query(Department).all()}
    shifts = {s.id: s for s in db.query(ShiftType).all()}
    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()

    # Index by employee
    assign_by_emp = {}
    for a in assignments:
        assign_by_emp.setdefault(a.employee_id, []).append(a)

    scorecards = []
    total_scheduled_hours = 0.0
    high_overtime_count = 0

    for emp in employees:
        emp_assigns = assign_by_emp.get(emp.id, [])
        total_shifts = len(emp_assigns)

        shift_counts = {}
        for a in emp_assigns:
            s_code = shifts[a.shift_type_id].code if a.shift_type_id in shifts else "UNK"
            shift_counts[s_code] = shift_counts.get(s_code, 0) + 1

        sched_hours = sum(shifts[a.shift_type_id].duration_hours for a in emp_assigns if a.shift_type_id in shifts)
        target_hours = round(emp.max_hours_week * (horizon_days / 7.0), 1)
        variance = round(sched_hours - target_hours, 1)

        total_scheduled_hours += sched_hours
        if variance > 8.0:
            high_overtime_count += 1

        # Max consecutive days streak
        worked_dates = sorted([a.date for a in emp_assigns])
        max_streak = 0
        curr_streak = 0
        prev_d = None
        for d in worked_dates:
            if prev_d and (d - prev_d).days == 1:
                curr_streak += 1
            else:
                curr_streak = 1
            max_streak = max(max_streak, curr_streak)
            prev_d = d

        # Days off calculations
        days_off = horizon_days - total_shifts
        worked_dates_set = set(worked_dates)
        weekend_off = 0
        for t in range(horizon_days):
            cur_d = plan.start_date + timedelta(days=t)
            if cur_d.weekday() in [5, 6] and cur_d not in worked_dates_set:
                weekend_off += 1

        floating_shifts = sum(1 for a in emp_assigns if a.is_floating)

        scorecards.append({
            "employee_id": emp.id,
            "employee_code": emp.employee_code,
            "name": emp.name,
            "primary_department": departments[emp.primary_department_id].name if emp.primary_department_id in departments else "",
            "contracted_hours_week": emp.max_hours_week,
            "target_hours_month": target_hours,
            "scheduled_hours": sched_hours,
            "variance_hours": variance,
            "total_shifts": total_shifts,
            "shift_breakdown": shift_counts,
            "days_off_count": days_off,
            "weekend_days_off_count": weekend_off,
            "max_consecutive_days_worked": max_streak,
            "floating_shifts_count": floating_shifts
        })

    return {
        "plan_id": plan.id,
        "planning_year": plan.planning_year,
        "planning_month": plan.planning_month,
        "total_calendar_days": horizon_days,
        "total_scheduled_hours": round(total_scheduled_hours, 1),
        "high_overtime_count": high_overtime_count,
        "employee_scorecards": scorecards
    }

def get_historical_analytics_summary(db: Session) -> Dict[str, Any]:
    """Summary metrics across all plans in the system."""
    plans = db.query(RosterPlan).all()
    total_plans = len(plans)
    total_deficits = sum(p.total_deficits for p in plans)
    total_floats = sum(p.total_floats for p in plans)
    avg_solve_time = (sum(p.solve_time_seconds for p in plans if p.solve_time_seconds) / total_plans) if total_plans > 0 else 0.0

    return {
        "total_plans_generated": total_plans,
        "total_deficits_recorded": total_deficits,
        "total_floats_recorded": total_floats,
        "average_solve_time_seconds": round(avg_solve_time, 2)
    }
