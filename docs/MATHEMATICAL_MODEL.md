# Mathematical Formulation & CP-SAT Solver Specification
## LocalRoster v2: Dynamic Offline Workforce Roster Planner

---

### 1. Mathematical Framework & CP-SAT Overview

LocalRoster v2 models the workforce scheduling problem as a **Constraint Satisfaction and Mixed-Integer Linear Optimization Problem (MIP/CP)**. We implement this using Google OR-Tools `cp_model.CpModel()`.

Because CP-SAT operates natively on **32-bit/64-bit bounded integers**, all variables, constraints, weights, and objective penalties are formalized strictly as integers. Floating-point coefficients are represented via fixed-point scaling factor $K = 100$.

---

### 2. Sets, Indices & Dynamic Parameters

#### 2.1 Index Sets

| Set | Notation | Domain | Description |
| :--- | :--- | :--- | :--- |
| **Employees** | $E$ | $e \in \{1, \dots, |E|\}$ | Total active workforce across all departments. |
| **Departments** | $D$ | $d \in \{1, \dots, |D|\}$ | Dynamic operational business units / wards / zones. |
| **Shift Types** | $S$ | $s \in \{1, \dots, |S|\}$ | User-defined shifts (e.g. Morning, Evening, Night). |
| **Planning Horizon** | $T$ | $t \in \{0, \dots, |T|-1\}$ | Calendar timeline: $t=0$ maps to `start_date` (Year/Month). |
| **Calendar Mapping** | $Date(t)$ | ISO Date | Exact calendar date: $Date(t) = \text{start\_date} + t \text{ days}$. |
| **Days of Week** | $DoW(t)$ | $\delta \in \{0, \dots, 6\}$ | Exact calendar day of week: $0 = \text{Monday}, \dots, 6 = \text{Sunday}$. |
| **Primary Dept** | $Home(e)$ | $d \in D$ | The designated primary home department of employee $e$. |

#### 2.2 Operational & Demand Parameters

* **$Operating_{d, s, t} \in \{0, 1\}$:** Binary flag indicating if department $d$ operates shift $s$ on calendar day $t$.
  - For **24x7 departments** (e.g. ICU, ER): $Operating_{d, s, t} = 1$ for all $s, t$.
  - For **non-24x7 departments** (e.g. Mon–Fri Outpatient Clinics): $Operating_{d, s, t} = 0$ on weekends and outside operational hours.
  - When $Operating_{d, s, t} = 0 \implies RequiredStaff_{d, s, t} = 0$ and $X_{e, d, s, t} = 0$ automatically.
* **$RequiredStaff_{d, s, t} \in \mathbb{Z}_{\ge 0}$:** Minimum required headcount in department $d$ on shift $s$ during day $t$.
* **$OptimalStaff_{d, s, t} \in \mathbb{Z}_{\ge 0}$:** Target desired headcount ($OptimalStaff \ge RequiredStaff$).
* **$Eligible_{e, d} \in \{0, 1\}$:** Binary indicator; $1$ if employee $e$ is qualified to work in department $d$, $0$ otherwise.
* **$Rank_{e, d} \in \{1, 2, 3, \infty\}$:** Priority tier of employee $e$ in department $d$:
  - $Rank = 1$: Primary home department ($d = Home(e)$).
  - $Rank = 2$: Certified secondary / backup floater.
  - $Rank = 3$: Emergency-only floater.
  - $Rank = \infty$: Ineligible ($Eligible_{e, d} = 0$).
* **$LockedOff_{e, t} \in \{0, 1\}$:** Hard lock flag; $1$ if employee $e$ is on approved leave, PTO, or medical off on day $t$.
* **$P^{dept}_{e, d} \in [-5, +5]$:** Integer employee affinity weight toward department $d$.
* **$P^{shift}_{e, s, t} \in [-5, +5]$:** Integer employee preference score for working shift $s$ on day $t$.

#### 2.3 Ergonomic & Shift Transition Parameters

* **$StartMinute(s) \in [0, 1439]$:** Shift start time represented as minutes from midnight ($00:00 = 0$).
* **$DurationMinutes(s) \in [1, 1440]$:** Duration of shift $s$ in minutes.
* **$MinRestMinutes(s) \in \mathbb{Z}_{\ge 0}$:** Minimum mandatory rest interval required following shift $s$ before any subsequent shift may begin.
* **$ForbiddenTransitions \subset S \times S$:** Set of prohibited consecutive-day shift pairs $(s_1, s_2)$ such that if an employee works shift $s_1$ on day $t$, they are prohibited from working shift $s_2$ on day $t+1$.
  $$\Delta t_{rest}(s_1, s_2) = (1440 - (StartMinute(s_1) + DurationMinutes(s_1))) + StartMinute(s_2)$$
  $$(s_1, s_2) \in ForbiddenTransitions \iff \Delta t_{rest}(s_1, s_2) < MinRestMinutes(s_1)$$
* **$R \in \mathbb{Z}_{\ge 0}$:** Mandatory rest days required within any rolling 7-day window (default: $R = 2$).
* **$C_{max} \in \mathbb{Z}_{\ge 0}$:** Maximum allowable consecutive working days without a rest day (default: $C_{max} = 5$).

---

### 3. Decision Variables

#### 3.1 Primary Assignment & Deficit Variables

1. **Assignment Tensor:**
   $$X_{e, d, s, t} \in \{0, 1\} \quad \forall e \in E, \, d \in D, \, s \in S, \, t \in T$$
   Equal to $1$ if employee $e$ is assigned to department $d$ on shift $s$ at day $t$; $0$ otherwise.

2. **Demand Deficit Slack (Integer):**
   $$Deficit_{d, s, t} \in \{0, \dots, RequiredStaff_{d, s, t}\} \quad \forall d \in D, \, s \in S, \, t \in T$$
   Measures the unsatisfied headcount requirement for department $d$, shift $s$, on day $t$.

#### 3.2 Auxiliary Linearization Variables

To express complex ergonomic and floating rules efficiently in CP-SAT, we construct auxiliary Boolean variables:

1. **Daily Working Indicator:**
   $$Y_{e, t} \in \{0, 1\} \quad \forall e \in E, \, t \in T$$
   Indicates whether employee $e$ works any shift on day $t$.

2. **Department Assignment Indicator:**
   $$Z_{e, d, t} \in \{0, 1\} \quad \forall e \in E, \, d \in D, \, t \in T$$
   Indicates whether employee $e$ is active in department $d$ on day $t$.

3. **Floating Assignment Indicator:**
   $$Float_{e, t} \in \{0, 1\} \quad \forall e \in E, \, t \in T$$
   Equal to $1$ if employee $e$ is deployed away from their primary department ($d \neq Home(e)$) on day $t$.

4. **Floating Rank Tracking Variables:**
   $$FloatRank2_{e, t} \in \{0, 1\}, \quad FloatRank3_{e, t} \in \{0, 1\} \quad \forall e \in E, \, t \in T$$
   Tracks whether the float assignment utilizes Rank 2 (qualified) or Rank 3 (emergency) cross-department staffing.

5. **Shift Type Indicator:**
   $$V_{e, s, t} \in \{0, 1\} \quad \forall e \in E, \, s \in S, \, t \in T$$
   Indicates whether employee $e$ performs shift type $s$ on day $t$, regardless of department.

---

### 4. Hard Constraints

#### 4.1 Daily Working Linkage & Single Daily Shift
An employee can work at most **one shift in at most one department** on any given calendar day $t$:

$$\sum_{d \in D} \sum_{s \in S} X_{e, d, s, t} = Y_{e, t} \le 1 \quad \forall e \in E, \, \forall t \in T$$

Linkage to shift indicator $V_{e, s, t}$:
$$\sum_{d \in D} X_{e, d, s, t} = V_{e, s, t} \quad \forall e \in E, \, \forall s \in S, \, \forall t \in T$$

Linkage to department indicator $Z_{e, d, t}$:
$$\sum_{s \in S} X_{e, d, s, t} = Z_{e, d, t} \quad \forall e \in E, \, \forall d \in D, \, \forall t \in T$$

#### 4.2 Department Eligibility Enforcement
An employee cannot be scheduled to any department for which they possess no qualified eligibility ($Eligible_{e, d} = 0$):

$$X_{e, d, s, t} \le Eligible_{e, d} \quad \forall e \in E, \, \forall d \in D, \, \forall s \in S, \, \forall t \in T$$

#### 4.3 Demand Fulfillment with Deficit Slacks
For every department, shift, and day, the sum of assigned workers plus the non-negative deficit slack must exactly equal the minimum staffing threshold:

$$\sum_{e \in E} X_{e, d, s, t} + Deficit_{d, s, t} = RequiredStaff_{d, s, t} \quad \forall d \in D, \, \forall s \in S, \, \forall t \in T$$

> **Crucial Infeasibility Shield:** Because $Deficit_{d, s, t} \ge 0$ can absorb any shortfall up to $RequiredStaff_{d, s, t}$, this equality constraint **can never cause solver infeasibility**. Under total workforce exhaustion, $Deficit_{d, s, t} = RequiredStaff_{d, s, t}$, and the solver cleanly reports the exact gap.

#### 4.4 Approved Leave & Pre-Scheduled Hard Locks
If an employee is locked off on day $t$ (due to approved annual leave, sick leave, or administrative off-status):

$$Y_{e, t} = 0 \quad \forall e \in E, \, \forall t \in T \text{ where } LockedOff_{e, t} = 1$$

#### 4.4.1 Pre-Filled & Pinned Assignments ("Fill Remaining Slots" Formulation)
In real-world operations, managers frequently pre-fill specific assignments (e.g. employee agreed to a specific weekend shift, or was promised a particular duty) or pre-fill requested days off before running the automated solver.

Let:
* $Pinned \subset E \times D \times S \times T$ be the set of quadruplets $(e, d, s, t)$ pre-filled and locked by the manager.
* $PinnedOff \subset E \times T$ be the set of pairs $(e, t)$ pre-filled as locked days off.

When the manager triggers **"Fill Remaining Slots"**, the solver enforces:

$$X_{e, d, s, t} = 1 \quad \forall (e, d, s, t) \in Pinned$$

$$Y_{e, t} = 0 \quad \forall (e, t) \in PinnedOff$$

**Integration with Demand & Ergonomics:**
All pinned assignments contribute directly to satisfying departmental demand:
$$\sum_{e \,:\, (e, d, s, t) \in Pinned} 1 + \sum_{e \,:\, (e, d, s, t) \notin Pinned} X_{e, d, s, t} + Deficit_{d, s, t} = RequiredStaff_{d, s, t}$$

Furthermore, all pinned assignments are counted inside the rolling 7-day rest window and maximum consecutive days sliding windows:
$$\sum_{k=0}^{6} Y_{e, t+k} \le 7 - R \quad \forall e \in E, \, \forall t \in \{0, \dots, |T|-7\}$$
$$\sum_{k=0}^{C_{max}} Y_{e, t+k} \le C_{max} \quad \forall e \in E, \, \forall t \in \{0, \dots, |T|-C_{max}-1\}$$

**Pre-Solve Pinning Conflict Detection:**
Before initiating CP-SAT, a deterministic pre-check verifies whether the set $Pinned \cup PinnedOff$ contains mutual hard contradictions:
1. Double-booking: $\exists e, t$ with multiple pinned shifts.
2. Direct rest violation: Pinned $(s_1, t)$ and pinned $(s_2, t+1)$ with $(s_1, s_2) \in ForbiddenTransitions$.
3. Pinned streak $> C_{max}$: More than $C_{max}$ contiguous pinned working days.

If pre-check violations exist, the manager is alerted immediately with options to unpin conflicting slots or enable an administrative relaxation.

#### 4.5 Forward Shift Rotation & Inter-Shift Rest Periods
For every prohibited consecutive shift transition $(s_1, s_2) \in ForbiddenTransitions$:

$$V_{e, s_1, t} + V_{e, s_2, t+1} \le 1 \quad \forall e \in E, \, \forall t \in \{0, \dots, |T|-2\}$$

*Example:* If $s_1 = \text{Night (22:00–06:00)}$ and $s_2 = \text{Morning (06:00–14:00)}$, rest interval is $0$ hours, violating $MinRest = 14$ hours. Hence, $(Night, Morning) \in ForbiddenTransitions$, preventing back-to-back turnaround.

#### 4.6 Maximum Consecutive Working Days ($C_{max}$)
An employee must not work more than $C_{max}$ days in succession. In every sliding window of length $C_{max} + 1$:

$$\sum_{k=0}^{C_{max}} Y_{e, t+k} \le C_{max} \quad \forall e \in E, \, \forall t \in \{0, \dots, |T| - C_{max} - 1\}$$

*For $C_{max} = 5$, any 6 consecutive days cannot contain 6 worked shifts (forcing at least 1 day off).*

#### 4.7 Rolling Window Rest Requirement ($R$ Days per 7-Day Window)
In any rolling window of 7 consecutive days $[t, t+6]$, each employee must receive at least $R$ rest days (i.e. they can work at most $7 - R$ days):

$$\sum_{k=0}^{6} Y_{e, t+k} \le 7 - R \quad \forall e \in E, \, \forall t \in \{0, \dots, |T| - 7\}$$

*For $R = 2$, this bounds total shifts worked per 7-day window to $\le 5$.*

#### 4.8 Cross-Department Floating Linkage
Deconstruct float assignments into their respective preference tiers:

$$FloatRank2_{e, t} = \sum_{d \in D \,:\, Rank_{e, d} = 2} Z_{e, d, t} \quad \forall e \in E, \, \forall t \in T$$

$$FloatRank3_{e, t} = \sum_{d \in D \,:\, Rank_{e, d} = 3} Z_{e, d, t} \quad \forall e \in E, \, \forall t \in T$$

Total float variable:
$$Float_{e, t} = FloatRank2_{e, t} + FloatRank3_{e, t} \quad \forall e \in E, \, \forall t \in T$$

---

### 5. Multi-Tier Objective Function

To guarantee that business priorities strictly dominate lower-tier preferences without arbitrary interference, we define a lexicographical / geometrically separated integer penalty hierarchy:

$$\min \mathcal{Z} = \mathcal{Z}_{deficit} + \mathcal{Z}_{emergency\_float} + \mathcal{Z}_{backup\_float} + \mathcal{Z}_{fairness} - \mathcal{Z}_{preferences}$$

#### 5.1 Objective Components

1. **Staffing Deficit Penalty ($\mathcal{Z}_{deficit}$):**
   $$\mathcal{Z}_{deficit} = W_{deficit} \sum_{d \in D} \sum_{s \in S} \sum_{t \in T} Deficit_{d, s, t}$$
   *Where $W_{deficit} = 1,000,000$.* A single unstaffed shift incurs a penalty far larger than any combination of float or preference penalties.

2. **Emergency Floating Penalty ($\mathcal{Z}_{emergency\_float}$):**
   $$\mathcal{Z}_{emergency\_float} = W_{float3} \sum_{e \in E} \sum_{t \in T} FloatRank3_{e, t}$$
   *Where $W_{float3} = 5,000$.* Using an emergency floater is allowed to prevent a deficit, but heavily penalized.

3. **Backup Floating Penalty ($\mathcal{Z}_{backup\_float}$):**
   $$\mathcal{Z}_{backup\_float} = W_{float2} \sum_{e \in E} \sum_{t \in T} FloatRank2_{e, t}$$
   *Where $W_{float2} = 1,000$.* Using a qualified secondary floater is favored over an emergency floater or deficit.

4. **Equity & Workload Balancing ($\mathcal{Z}_{fairness}$):**
   Let $Nights_e = \sum_{t \in T} V_{e, \text{Night}, t}$ be the number of night shifts assigned to employee $e$.
   Let $\overline{Nights} = \frac{\sum_{e \in E} Nights_e}{|E|}$ be the target average.
   We introduce auxiliary integer deviations $DevPos_{e}, DevNeg_{e} \ge 0$:
   $$Nights_e - \overline{Nights}_{scaled} = DevPos_{e} - DevNeg_{e} \quad \forall e \in E$$
   $$\mathcal{Z}_{fairness} = W_{fair} \sum_{e \in E} (DevPos_{e} + DevNeg_{e})$$
   *Where $W_{fair} = 50$.* Minimizes $L_1$ absolute spread of unsociable shifts across all eligible employees.

5. **Soft Preferences Reward ($\mathcal{Z}_{preferences}$):**
   $$\mathcal{Z}_{preferences} = W_{pref} \sum_{e \in E} \sum_{t \in T} \left( \sum_{d \in D} P^{dept}_{e, d} \cdot Z_{e, d, t} + \sum_{s \in S} P^{shift}_{e, s, t} \cdot V_{e, s, t} \right)$$
   *Where $W_{pref} = 10$.* Maximizes worker satisfaction scores without sacrificing staffing levels or balance.

#### 5.2 Strict Penalty Hierarchy Proof

| Objective Level | Term | Weight ($W$) | Typical Max Contribution | Dominance Margin |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (Critical)** | Deficit Penalty | $1,000,000$ per slot | $10 \times 1,000,000 = 10,000,000$ | $W_{deficit} \gg 200 \times W_{float3}$ |
| **Tier 2 (Severe)** | Emergency Float (Rank 3) | $5,000$ per shift | $50 \times 5,000 = 250,000$ | $W_{float3} \gg 5 \times W_{float2}$ |
| **Tier 3 (Moderate)**| Backup Float (Rank 2) | $1,000$ per shift | $100 \times 1,000 = 100,000$ | $W_{float2} \gg 20 \times W_{fair}$ |
| **Tier 4 (Fairness)**| Night/Weekend Spread | $50$ per dev unit | $100 \times 50 = 5,000$ | $W_{fair} > W_{pref}$ |
| **Tier 5 (Soft)** | Individual Preferences| $10$ per score point | $1,500 \times 10 = 15,000$ | Fine-tunes allocations |

Because $W_{deficit} = 1,000,000 > \max(\mathcal{Z}_{float} + \mathcal{Z}_{fairness} + \mathcal{Z}_{pref})$, the CP-SAT engine will **never** allow a shift deficit to satisfy employee preferences or reduce float duties.

---

### 6. CP-SAT Implementation Blueprint (Python Pseudocode)

```python
from ortools.sat.python import cp_model

def build_roster_model(scenario_data):
    model = cp_model.CpModel()
    
    # 1. Variables
    X = {}
    for e in scenario_data.employees:
        for d in scenario_data.departments:
            for s in scenario_data.shifts:
                for t in range(scenario_data.horizon_days):
                    if scenario_data.is_eligible(e, d):
                        X[e, d, s, t] = model.NewBoolVar(f"X_{e}_{d}_{s}_{t}")
                    else:
                        X[e, d, s, t] = None
                        
    Deficit = {}
    for d in scenario_data.departments:
        for s in scenario_data.shifts:
            for t in range(scenario_data.horizon_days):
                req = scenario_data.demand[d, s, t]
                Deficit[d, s, t] = model.NewIntVar(0, req, f"Deficit_{d}_{s}_{t}")

    # 2. Hard Demand Constraint with Deficit Slack
    for d in scenario_data.departments:
        for s in scenario_data.shifts:
            for t in range(scenario_data.horizon_days):
                assigned = [X[e, d, s, t] for e in scenario_data.employees if X[e, d, s, t] is not None]
                model.Add(sum(assigned) + Deficit[d, s, t] == scenario_data.demand[d, s, t])

    # 3. Single shift per day
    for e in scenario_data.employees:
        for t in range(scenario_data.horizon_days):
            daily_shifts = [X[e, d, s, t] for d in scenario_data.departments 
                            for s in scenario_data.shifts if X[e, d, s, t] is not None]
            model.Add(sum(daily_shifts) <= 1)

    # 4. Ergonomic Forbidden Rotations (e.g. Night to Morning)
    for e in scenario_data.employees:
        for t in range(scenario_data.horizon_days - 1):
            for (s1, s2) in scenario_data.forbidden_transitions:
                worked_s1 = [X[e, d, s1, t] for d in scenario_data.departments if X[e, d, s1, t] is not None]
                worked_s2 = [X[e, d, s2, t + 1] for d in scenario_data.departments if X[e, d, s2, t + 1] is not None]
                if worked_s1 and worked_s2:
                    model.Add(sum(worked_s1) + sum(worked_s2) <= 1)

    # 5. Consecutive Days Limit (Max C_max)
    C_max = scenario_data.max_consecutive_days
    for e in scenario_data.employees:
        for t in range(scenario_data.horizon_days - C_max):
            window_shifts = [
                X[e, d, s, t + k] 
                for k in range(C_max + 1)
                for d in scenario_data.departments 
                for s in scenario_data.shifts 
                if X[e, d, s, t + k] is not None
            ]
            model.Add(sum(window_shifts) <= C_max)

    # 6. Rolling Window Rest Days (At least R rest days per 7-day window)
    R = scenario_data.min_rest_days_per_week
    for e in scenario_data.employees:
        for t in range(scenario_data.horizon_days - 6):
            window_worked = [
                X[e, d, s, t + k]
                for k in range(7)
                for d in scenario_data.departments
                for s in scenario_data.shifts
                if X[e, d, s, t + k] is not None
            ]
            model.Add(sum(window_worked) <= 7 - R)

    # 7. Objectives Formulation
    obj_terms = []
    
    # Deficit penalties
    for (d, s, t), d_var in Deficit.items():
        obj_terms.append(d_var * 1_000_000)
        
    # Floating penalties & preferences
    for e in scenario_data.employees:
        for d in scenario_data.departments:
            for s in scenario_data.shifts:
                for t in range(scenario_data.horizon_days):
                    var = X[e, d, s, t]
                    if var is None:
                        continue
                    # Float cost
                    rank = scenario_data.get_rank(e, d)
                    if rank == 2:
                        obj_terms.append(var * 1_000)
                    elif rank == 3:
                        obj_terms.append(var * 5_000)
                    
                    # Preference reward (subtracted)
                    pref = scenario_data.get_preference(e, d, s, t)
                    obj_terms.append(var * (-10 * pref))

    model.Minimize(sum(obj_terms))
    return model
```

---

### 7. Warm-Starting & Incremental Re-Solving

When a manager introduces manual overrides on a published roster and requests an incremental re-solve:
1. **Decision Variable Pinning:** Fixed assignments are set as equalities:
   $$X_{e^*, d^*, s^*, t^*} = 1$$
2. **Solution Hinting (`model.AddHint`):** For all non-pinned variables, the previous solution values are supplied to CP-SAT using `model.AddHint(var, previous_value)`. This drastically accelerates convergence ($\le 1.5$ seconds) by guiding the neighborhood search engine.

---

### 8. Post-Solve Workload & Operational Audit Formulation

Once the CP-SAT solver yields optimal or feasible decision variable values $X^*_{e, d, s, t}$, the system executes deterministic post-solve aggregation functions to generate the **Manager's Cross-Check Audit Scorecard**:

1. **Total Hours Worked per Employee ($Hours_e$):**
   $$Hours_e = \sum_{d \in D} \sum_{s \in S} \sum_{t \in T} DurationHours(s) \cdot X^*_{e, d, s, t}$$

2. **Contracted vs. Scheduled Hours Variance ($\Delta Hours_e$):**
   $$\Delta Hours_e = Hours_e - \left( MaxHoursWeek_e \times \frac{|T|}{7} \right)$$
   - $\Delta Hours_e > 0$: Overtime surplus (flagged for review).
   - $\Delta Hours_e < 0$: Undertime deficit.

3. **Shift Count Breakdown by Type ($ShiftsByType_{e, s}$):**
   $$ShiftsByType_{e, s} = \sum_{d \in D} \sum_{t \in T} X^*_{e, d, s, t} \quad \forall s \in S$$

4. **Total Rest Days Granted ($DaysOff_e$):**
   $$DaysOff_e = |T| - \sum_{t \in T} Y^*_{e, t}$$

5. **Weekend Days Off Granted ($WeekendOff_e$):**
   $$WeekendOff_e = \sum_{t \in T \,:\, DoW(t) \in \{5, 6\}} (1 - Y^*_{e, t})$$

6. **Cross-Department Floating Burden ($TotalFloats_e$):**
   $$TotalFloats_e = \sum_{t \in T} Float^*_{e, t}$$

These exact metrics are mapped to `/api/roster/{id}/summary` and embedded directly into the Excel and PDF reports to allow operational cross-checking.

---

### 9. Multi-Variant Roster Generation & Comparison Formulation

To enable managers to evaluate multiple operational trade-offs, the engine supports parameterized multi-variant solving:

#### 9.1 Variant Generation Profiles ($\Pi_k$)
Multiple candidate plans are generated across distinct objective parameter vectors:
1. **Variant 1 (Balanced Standard):** $W_{deficit} = 10^6, W_{float2} = 10^3, W_{float3} = 5 \times 10^3, W_{fair} = 50, W_{pref} = 10$.
2. **Variant 2 (Float-Averse):** Maximizes home department stability by amplifying float penalties: $W_{float2} = 10^4, W_{float3} = 5 \times 10^4$.
3. **Variant 3 (Maximum Preference Satisfaction):** Increases worker satisfaction weighting: $W_{pref} = 80$, aligning schedules closer to staff requests without compromising coverage.
4. **Variant 4 (Alternative Search Exploration):** Varies CP-SAT parameter `random_seed` (e.g. `seed=101, 777`) to traverse alternative branch-and-bound exploration trajectories.

#### 9.2 Variant Comparison Metrics & Hamming Distance
Given two candidate variants $V_a$ and $V_b$, the system calculates:
1. **KPI Comparison Vector:**
   $$\mathbf{KPI}(V) = \left[ \sum Deficit, \; \sum Float, \; Variance(Nights), \; \sum Preferences, \; SolveDuration \right]$$
2. **Assignment Hamming Distance ($\Delta(V_a, V_b)$):**
   $$\Delta(V_a, V_b) = \sum_{e \in E} \sum_{t \in T} \mathbb{I}\left( \text{Assignment}_{V_a}(e, t) \neq \text{Assignment}_{V_b}(e, t) \right)$$
   Where $\mathbb{I}(\cdot) = 1$ if employee $e$ has a different shift or department assignment on day $t$ between the two variants. This highlights exact cell discrepancies in the comparison UI.
