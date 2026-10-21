"""OR-Tools CP-SAT formulation for LocalRoster v2 adhering strictly to MATHEMATICAL_MODEL.md."""
from typing import Dict, List, Tuple, Set, Any, Optional
from ortools.sat.python import cp_model
from src.solver.rules import is_transition_forbidden

class SchedulingContext:
    """Encapsulates all relational inputs, eligibility tensors, demands, and weights for CP-SAT."""
    def __init__(
        self,
        employees: List[Any],
        departments: List[Any],
        shifts: List[Any],
        horizon_days: int,
        start_date: Any,
        demand_matrix: Dict[Tuple[int, int, int], int],  # (dept_id, shift_id, t) -> required_staff
        eligibilities: Dict[Tuple[int, int], Tuple[int, bool]],  # (emp_id, dept_id) -> (rank, can_float)
        preferences: Dict[Tuple[int, int, int], int],  # (emp_id, shift_id, dow) -> score (-5 to +5)
        approved_leaves: Set[Tuple[int, int]],  # (emp_id, t)
        pinned_assignments: Dict[Tuple[int, int], Tuple[int, int]],  # (emp_id, t) -> (dept_id, shift_id)
        pinned_offs: Set[Tuple[int, int]],  # (emp_id, t)
        max_consecutive_days: int = 5,
        min_rest_days_per_week: int = 2,
        weights: Optional[Dict[str, int]] = None
    ):
        self.employees = employees
        self.departments = departments
        self.shifts = shifts
        self.horizon_days = horizon_days
        self.start_date = start_date
        self.demand = demand_matrix
        self.eligibilities = eligibilities
        self.preferences = preferences
        self.approved_leaves = approved_leaves
        self.pinned_assignments = pinned_assignments
        self.pinned_offs = pinned_offs
        self.max_consecutive_days = max_consecutive_days
        self.min_rest_days_per_week = min_rest_days_per_week
        self.emp_map = {e.id: e for e in self.employees}

        # Default multi-tier hierarchical weights
        default_weights = {
            "deficit": 1_000_000,
            "float_rank2": 1_000,
            "float_rank3": 5_000,
            "fairness": 50,
            "preferences": 10
        }
        if weights:
            default_weights.update(weights)
        self.weights = default_weights

        # Precalculate forbidden shift transitions
        self.forbidden_transitions = set()
        for s1 in self.shifts:
            for s2 in self.shifts:
                if is_transition_forbidden(s1, s2):
                    self.forbidden_transitions.add((s1.id, s2.id))

    def is_eligible(self, emp_id: int, dept_id: int) -> bool:
        # Home department is always eligible
        emp = self.emp_map.get(emp_id)
        if emp and emp.primary_department_id == dept_id:
            return True
        if (emp_id, dept_id) in self.eligibilities:
            rank, can_float = self.eligibilities[(emp_id, dept_id)]
            return rank == 1 or can_float
        return False

    def get_rank(self, emp_id: int, dept_id: int) -> int:
        emp = self.emp_map.get(emp_id)
        if emp and emp.primary_department_id == dept_id:
            return 1
        if (emp_id, dept_id) in self.eligibilities:
            rank, _ = self.eligibilities[(emp_id, dept_id)]
            return rank
        return 99


class RosterModelBuilder:
    """Builds the CP-SAT optimization model from a SchedulingContext."""

    def __init__(self, context: SchedulingContext):
        self.ctx = context
        self.model = cp_model.CpModel()
        self.X = {}        # (e, d, s, t) -> BoolVar
        self.Deficit = {}  # (d, s, t) -> IntVar
        self.Y = {}        # (e, t) -> BoolVar
        self.V = {}        # (e, s, t) -> BoolVar
        self.Float2 = {}   # (e, t) -> BoolVar
        self.Float3 = {}   # (e, t) -> BoolVar

    def build(self) -> cp_model.CpModel:
        self._create_variables()
        self._add_assignment_linkages()
        self._add_demand_constraints()
        self._add_ergonomic_rest_constraints()
        self._add_consecutive_days_constraints()
        self._add_rolling_window_rest_constraints()
        self._add_leave_and_pinned_locks()
        self._set_objective()
        return self.model

    def _create_variables(self):
        # 1. Primary Decision Variables X[e, d, s, t]
        for e in self.ctx.employees:
            for d in self.ctx.departments:
                if not self.ctx.is_eligible(e.id, d.id):
                    continue
                for s in self.ctx.shifts:
                    for t in range(self.ctx.horizon_days):
                        self.X[e.id, d.id, s.id, t] = self.model.NewBoolVar(f"X_{e.id}_{d.id}_{s.id}_{t}")

        # 2. Deficit Slack Variables Deficit[d, s, t]
        for d in self.ctx.departments:
            for s in self.ctx.shifts:
                for t in range(self.ctx.horizon_days):
                    req = self.ctx.demand.get((d.id, s.id, t), 0)
                    self.Deficit[d.id, s.id, t] = self.model.NewIntVar(0, max(req, 1), f"Deficit_{d.id}_{s.id}_{t}")

        # 3. Daily Working Variable Y[e, t]
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days):
                self.Y[e.id, t] = self.model.NewBoolVar(f"Y_{e.id}_{t}")

        # 4. Daily Shift Indicator V[e, s, t]
        for e in self.ctx.employees:
            for s in self.ctx.shifts:
                for t in range(self.ctx.horizon_days):
                    self.V[e.id, s.id, t] = self.model.NewBoolVar(f"V_{e.id}_{s.id}_{t}")

        # 5. Floating Trackers Float2[e, t], Float3[e, t]
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days):
                self.Float2[e.id, t] = self.model.NewBoolVar(f"Float2_{e.id}_{t}")
                self.Float3[e.id, t] = self.model.NewBoolVar(f"Float3_{e.id}_{t}")

    def _add_assignment_linkages(self):
        # Link Y[e, t] == sum(X[e, d, s, t]) <= 1 (Single assignment per day)
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days):
                assigned_slots = [
                    self.X[e.id, d.id, s.id, t]
                    for d in self.ctx.departments
                    for s in self.ctx.shifts
                    if (e.id, d.id, s.id, t) in self.X
                ]
                self.model.Add(sum(assigned_slots) == self.Y[e.id, t])
                self.model.Add(self.Y[e.id, t] <= 1)

        # Link V[e, s, t] == sum_{d} X[e, d, s, t]
        for e in self.ctx.employees:
            for s in self.ctx.shifts:
                for t in range(self.ctx.horizon_days):
                    slots = [
                        self.X[e.id, d.id, s.id, t]
                        for d in self.ctx.departments
                        if (e.id, d.id, s.id, t) in self.X
                    ]
                    self.model.Add(sum(slots) == self.V[e.id, s.id, t])

        # Link Float tiers
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days):
                rank2_slots = [
                    self.X[e.id, d.id, s.id, t]
                    for d in self.ctx.departments
                    for s in self.ctx.shifts
                    if (e.id, d.id, s.id, t) in self.X and self.ctx.get_rank(e.id, d.id) == 2
                ]
                self.model.Add(sum(rank2_slots) == self.Float2[e.id, t])

                rank3_slots = [
                    self.X[e.id, d.id, s.id, t]
                    for d in self.ctx.departments
                    for s in self.ctx.shifts
                    if (e.id, d.id, s.id, t) in self.X and self.ctx.get_rank(e.id, d.id) == 3
                ]
                self.model.Add(sum(rank3_slots) == self.Float3[e.id, t])

    def _add_demand_constraints(self):
        # Guaranteed Feasibility Equality: sum(X) + Deficit == RequiredStaff
        for d in self.ctx.departments:
            for s in self.ctx.shifts:
                for t in range(self.ctx.horizon_days):
                    req = self.ctx.demand.get((d.id, s.id, t), 0)
                    assigned = [
                        self.X[e.id, d.id, s.id, t]
                        for e in self.ctx.employees
                        if (e.id, d.id, s.id, t) in self.X
                    ]
                    deficit_var = self.Deficit[d.id, s.id, t]
                    self.model.Add(sum(assigned) + deficit_var == req)

    def _add_ergonomic_rest_constraints(self):
        # Forbidden consecutive shift turnaround (e.g. Night -> Morning)
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days - 1):
                for (s1_id, s2_id) in self.ctx.forbidden_transitions:
                    self.model.Add(self.V[e.id, s1_id, t] + self.V[e.id, s2_id, t + 1] <= 1)

    def _add_consecutive_days_constraints(self):
        # In any sliding window of C_max + 1 days, sum(Y) <= C_max
        C = self.ctx.max_consecutive_days
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days - C):
                window = [self.Y[e.id, t + k] for k in range(C + 1)]
                self.model.Add(sum(window) <= C)

    def _add_rolling_window_rest_constraints(self):
        # In any sliding 7-day window, sum(Y) <= 7 - R (at least R rest days)
        R = self.ctx.min_rest_days_per_week
        max_work = 7 - R
        for e in self.ctx.employees:
            for t in range(self.ctx.horizon_days - 6):
                window = [self.Y[e.id, t + k] for k in range(7)]
                self.model.Add(sum(window) <= max_work)

    def _add_leave_and_pinned_locks(self):
        # 1. Approved Leave Hard Locks (Y[e, t] == 0)
        for (emp_id, t) in self.ctx.approved_leaves:
            if (emp_id, t) in self.Y:
                self.model.Add(self.Y[emp_id, t] == 0)

        # 2. Pinned Days Off (Y[e, t] == 0)
        for (emp_id, t) in self.ctx.pinned_offs:
            if (emp_id, t) in self.Y:
                self.model.Add(self.Y[emp_id, t] == 0)

        # 3. Pinned Shifts (X[e, d, s, t] == 1)
        for (emp_id, t), (dept_id, shift_id) in self.ctx.pinned_assignments.items():
            if (emp_id, dept_id, shift_id, t) in self.X:
                self.model.Add(self.X[emp_id, dept_id, shift_id, t] == 1)

    def _set_objective(self):
        obj_terms = []

        # Tier 1: Deficit Penalty (Highest)
        w_deficit = self.ctx.weights["deficit"]
        for d_var in self.Deficit.values():
            obj_terms.append(d_var * w_deficit)

        # Tier 2 & 3: Floating Penalties
        w_f2 = self.ctx.weights["float_rank2"]
        w_f3 = self.ctx.weights["float_rank3"]
        for f2_var in self.Float2.values():
            obj_terms.append(f2_var * w_f2)
        for f3_var in self.Float3.values():
            obj_terms.append(f3_var * w_f3)

        # Tier 4: Soft Preferences (Rewarded / Subtracted)
        w_pref = self.ctx.weights["preferences"]
        for (e_id, d_id, s_id, t), x_var in self.X.items():
            # Preference score for (emp, shift, day_of_week)
            dow = (self.ctx.start_date.weekday() + t) % 7
            pref_score = self.ctx.preferences.get((e_id, s_id, dow), 0)
            if pref_score != 0:
                obj_terms.append(x_var * (-w_pref * pref_score))

        # Tier 5: Fairness on Night Shifts
        w_fair = self.ctx.weights["fairness"]
        night_shift_ids = [s.id for s in self.ctx.shifts if s.is_night_shift]
        if night_shift_ids and len(self.ctx.employees) > 1:
            total_night_vars = {}
            for e in self.ctx.employees:
                n_vars = [
                    self.V[e.id, s_id, t]
                    for s_id in night_shift_ids
                    for t in range(self.ctx.horizon_days)
                ]
                total_night_vars[e.id] = self.model.NewIntVar(0, self.ctx.horizon_days, f"NightTotal_{e.id}")
                self.model.Add(total_night_vars[e.id] == sum(n_vars))

            # Approximate variance minimization via bounding max and min night shifts
            max_nights = self.model.NewIntVar(0, self.ctx.horizon_days, "MaxNights")
            min_nights = self.model.NewIntVar(0, self.ctx.horizon_days, "MinNights")
            for e_id, n_var in total_night_vars.items():
                self.model.Add(max_nights >= n_var)
                self.model.Add(min_nights <= n_var)
            obj_terms.append((max_nights - min_nights) * w_fair)

        self.model.Minimize(sum(obj_terms))
