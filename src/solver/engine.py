"""Solver execution engine, multi-variant generation, and deficit root-cause diagnostics."""
import time
from datetime import timedelta, date
from typing import Dict, List, Any, Optional
from ortools.sat.python import cp_model
from src.solver.model import SchedulingContext, RosterModelBuilder

class SolveResult:
    def __init__(
        self,
        status: str,
        solve_time_seconds: float,
        objective_score: float,
        assignments: List[Dict[str, Any]],
        deficits: List[Dict[str, Any]],
        strategy_name: str = "BALANCED",
        seed: int = 42
    ):
        self.status = status
        self.solve_time_seconds = solve_time_seconds
        self.objective_score = objective_score
        self.assignments = assignments
        self.deficits = deficits
        self.strategy_name = strategy_name
        self.seed = seed

def diagnose_deficit_reason(
    dept_id: int,
    shift_id: int,
    day_idx: int,
    ctx: SchedulingContext
) -> str:
    """Analyze the root cause of an unstaffed shift slot."""
    # Count approved leaves on day_idx
    leaves_today = sum(1 for (e_id, t) in ctx.approved_leaves if t == day_idx)

    # Count eligible staff for this department
    eligible_count = sum(1 for e in ctx.employees if ctx.is_eligible(e.id, dept_id))

    if eligible_count == 0:
        return "ZERO_QUALIFIED_STAFF"
    if leaves_today >= (len(ctx.employees) // 3):
        return "CONCURRENT_LEAVES"
    if eligible_count <= 2:
        return "EXHAUSTED_ELIGIBLE_STAFF"
    return "ERGONOMIC_REST_RESTRICTION"

def solve_roster(
    context: SchedulingContext,
    timeout_seconds: int = 15,
    random_seed: int = 42,
    strategy_name: str = "BALANCED",
    hints: Optional[List[Dict[str, Any]]] = None
) -> SolveResult:
    """Execute CP-SAT solver over the scheduling context."""
    builder = RosterModelBuilder(context)
    model = builder.build()

    # Solution Hinting (Warm Starting)
    if hints:
        for hint in hints:
            key = (hint["employee_id"], hint["department_id"], hint["shift_type_id"], hint["day_idx"])
            if key in builder.X:
                model.AddHint(builder.X[key], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(timeout_seconds)
    solver.parameters.random_seed = random_seed
    solver.parameters.num_workers = 4  # Leverage multi-core search

    start_time = time.time()
    raw_status = solver.Solve(model)
    elapsed_time = round(time.time() - start_time, 3)

    status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "ERROR",
        cp_model.UNKNOWN: "TIMEOUT"
    }
    status = status_map.get(raw_status, "UNKNOWN")

    assignments = []
    deficits = []

    if status in ["OPTIMAL", "FEASIBLE"]:
        # Extract assignments
        for (e_id, d_id, s_id, t), x_var in builder.X.items():
            if solver.Value(x_var) == 1:
                cur_date = context.start_date + timedelta(days=t)
                is_floating = (context.get_rank(e_id, d_id) > 1)
                float_rank = context.get_rank(e_id, d_id)
                assignments.append({
                    "employee_id": e_id,
                    "department_id": d_id,
                    "shift_type_id": s_id,
                    "date": cur_date,
                    "day_idx": t,
                    "is_floating": is_floating,
                    "float_rank": float_rank,
                    "is_pinned": ((e_id, t) in context.pinned_assignments)
                })

        # Extract deficits
        for (d_id, s_id, t), def_var in builder.Deficit.items():
            def_val = solver.Value(def_var)
            if def_val > 0:
                cur_date = context.start_date + timedelta(days=t)
                reason = diagnose_deficit_reason(d_id, s_id, t, context)
                deficits.append({
                    "department_id": d_id,
                    "shift_type_id": s_id,
                    "date": cur_date,
                    "day_idx": t,
                    "shortage_count": def_val,
                    "reason_code": reason
                })

        obj_score = float(solver.ObjectiveValue())
    else:
        obj_score = 0.0

    return SolveResult(
        status=status,
        solve_time_seconds=elapsed_time,
        objective_score=obj_score,
        assignments=assignments,
        deficits=deficits,
        strategy_name=strategy_name,
        seed=random_seed
    )

def generate_roster_variants(
    base_context: SchedulingContext,
    strategies: Optional[List[str]] = None,
    timeout_seconds: int = 15
) -> List[SolveResult]:
    """Generate multiple candidate roster variants under distinct operational objectives."""
    if not strategies:
        strategies = ["BALANCED", "FLOAT_AVERSE", "PREFERENCE_MAX"]

    variants = []
    seeds = [42, 101, 777, 999]

    for i, strat in enumerate(strategies):
        # Configure weight profile
        w = dict(base_context.weights)
        if strat == "FLOAT_AVERSE":
            w["float_rank2"] = 15_000
            w["float_rank3"] = 75_000
            w["preferences"] = 5
        elif strat == "PREFERENCE_MAX":
            w["preferences"] = 80
            w["fairness"] = 25
        elif strat == "BALANCED":
            w["float_rank2"] = 1_000
            w["float_rank3"] = 5_000
            w["preferences"] = 10
            w["fairness"] = 50

        # Create localized context
        ctx = SchedulingContext(
            employees=base_context.employees,
            departments=base_context.departments,
            shifts=base_context.shifts,
            horizon_days=base_context.horizon_days,
            start_date=base_context.start_date,
            demand_matrix=base_context.demand,
            eligibilities=base_context.eligibilities,
            preferences=base_context.preferences,
            approved_leaves=base_context.approved_leaves,
            pinned_assignments=base_context.pinned_assignments,
            pinned_offs=base_context.pinned_offs,
            max_consecutive_days=base_context.max_consecutive_days,
            min_rest_days_per_week=base_context.min_rest_days_per_week,
            weights=w
        )

        seed = seeds[i % len(seeds)]
        result = solve_roster(ctx, timeout_seconds=timeout_seconds, random_seed=seed, strategy_name=strat)
        variants.append(result)

    return variants
