# LocalRoster v2 — Enhancements & Reliability Release Notes

## 1. Dedicated Shift Preferences & Shift Stability Optimization
- **Operational Requirement:** In many healthcare and enterprise operations, staff have a designated shift rhythm (e.g. permanent Morning, Evening, or Night). Workers should stick to their dedicated shift consistently throughout the month, and only be assigned to a different shift if there is an unavoidable shortage/deficit that cannot otherwise be filled.
- **Model Formulation in CP-SAT (`src/solver/model.py`):**
  - **Dedicated Shift Deviation Penalty (Weight: 2,500):**
    For each worker $e$ with a configured `preferred_shift_type_id = s^*$, assigning any non-dedicated shift $s \neq s^*$ incurs a 2,500 penalty. Since deficit penalty is 1,000,000 >> 2,500, the solver will only divert a worker from their dedicated shift when an unstaffed deficit would otherwise occur.
  - **Consecutive Shift Stability Penalty (Weight: 50):**
    Prevents erratic day-to-day hopping between morning, evening, and night for flexible workers. The solver tracks consecutive day transitions $t \to t+1$ and penalizes switching shift types between adjacent workdays.

## 2. Dedicated Day Off Clearing & Live Canvas Synchronization
- **Bug Fix:** When switching an employee from fixed recurring days off (e.g. Saturday/Sunday) to "Flexible / Dynamic" (None), the API previously skipped falsy values or `None` checks, preventing `fixed_off_days` from being cleared in the database.
- **Resolution:**
  - `update_employee` and `bulk_update_employees` (`src/api/routes_employees.py`) now track explicit field presence (`"fixed_off_days" in emp_in.model_fields_set`) and allow empty strings (`""`) to set `emp.fixed_off_days = None`.
  - Grid render engine (`src/api/routes_roster.py`) dynamically computes fixed day-off status; as soon as `fixed_off_days` is cleared, cells revert from locked `DO` to empty / fillable cells immediately on canvas refresh.
  - Added conflict checking: If an assignment exists on a day that is newly designated as an employee's fixed day off, the cell flags a conflict alert (`Violation: Assigned to work on employee's dedicated regular day off`).

## 3. Secondary Floating Departments UI & Multi-Rank Floating
- **Feature:** Managers can now designate secondary backup departments for employees (Rank 2 floaters) directly from the Employee Add/Edit card and Bulk Edit modal.
- **Workflow:**
  - In Employee profile: Select home department (Rank 1). Checkboxes dynamically present all other organization departments. Checking a department registers an `EmployeeDepartmentEligibility` entry with `preference_rank=2, can_float=True`.
  - In Roster Table & Tooltip: Displays dedicated shift badge (`☀️ Morning Shift`) and secondary floating badges (`⚓ ICU`, `⚓ ER`).
  - In Solver: Secondary floaters are strictly governed by floating penalties (`float_rank2: 1,000`, `float_rank3: 5,000`) below shortage penalties (1,000,000). Employees will only float to secondary departments when a shortage demands backup coverage.

## 4. Comprehensive Excel & Printable PDF Export Overhaul
- **Excel Export (`/api/export/{plan_id}/excel`):**
  - **Staff-Centric Sheet:** Displays Employee Code, Name, Primary Dept, Dedicated Shift, Backup Floats, daily cell schedule, and detailed workload summary (Worked Shifts, Hours Scheduled, Monthly Contract Target, Variance with red overtime alerts, Regular DOs, Comp Offs, Leaves, and Float counts).
  - **Cell Statuses & Badges:** Distinct formatting and styling for `MORN`, `EVE`, `NIGHT`, `DO` (Regular/Pinned Day Off), `COFF` (Earned Comp Off / Overtime Holiday), and `VAC` (Vacation/Leave).
  - **Legend & Glossary:** Full color and code legend embedded directly on the sheet.
  - **Slot-Centric Sheet:** Daily department slot breakdown with worker names, floater markers (`*`), and shortage diagnostics.
  - **Workload Audit Sheet:** Ergonomics and contract variance tracking.
  - **Deficits Sheet:** Root cause analysis and deficit summaries.
- **Printable Vector PDF Export (`/api/export/{plan_id}/pdf`):**
  - Removed 14-day truncation limit. Supports complete monthly schedule horizons (28-31 days) formatted across clean landscape pagination tables (Part 1, Part 2).
  - Compact employee and department codes, shift status badges (`MO`, `EV`, `NI`, `DO`, `CO`, `VA`), and summary legend.

## 5. Flexible Day Off vs. Compensatory Off (`COFF`) Classification
- **Issue:** Previously, unassigned days on solved plans for employees with flexible days off were inappropriately converted into Earned Comp Off (`COFF`) whenever weekly hours reached standard contract levels ($\ge 40$h / 5 shifts). This caused employees with regular 40-hour work weeks to receive all their rest days as `COFF` instead of regular Days Off (`DO`).
- **Correction:**
  - Standard weekly contract fulfillment ($\le 5$ shifts / $\le 40$h) strictly yields **Scheduled Rest Days (`DO`)** with code `DO` and slate badge styling (`#64748B`).
  - **Earned Compensatory Off (`COFF`)** is reserved strictly for overtime worked ($> 5$ shifts or $> 40$ hours in a single calendar week), up to a configurable monthly cap (`max_comp_offs_per_employee`).
  - Empty slots created when managers delete an assignment remain `None` (open fillable slots) so the CP-SAT solver or manager can fill them.

## 6. Continuous Comp Off & Maximum Comp Off Limit
- **Operational Policy:** Real-world operations avoid fragmented single rest days by clustering earned compensatory offs adjacent to scheduled days off, providing employees with restorative multi-day rest blocks.
- **Implementation:**
  - Added system settings:
    - `max_comp_offs_per_employee` (default: 2 per month).
    - `continuous_comp_off_enabled` (default: `true`).
  - When awarding `COFF`, the scheduler places it contiguous with existing rest days (`DO` or `COFF`) wherever possible, forming uninterrupted recovery intervals.
  - The maximum comp off limit prevents excessive unbudgeted paid time off, routing any additional overtime hours to standard paid overtime tracking in the Workload Audit Scorecard.

## 7. Dynamic Shift Allocation Regimes (3 Shifts vs 2 Shifts)
- **Operational Need:** Due to fluctuating patient/customer volume or lower weekend staffing, departments frequently operate on 3 shifts during high-volume weekdays and collapse to 2 shifts on weekends or understaffed periods.
- **Implementation:**
  - New API endpoint `POST /api/departments/{dept_id}/apply-shift-regime?regime={regime}`:
    - **`3_shifts` (Standard 24/7):** Morning, Evening, and Night shifts active daily (min staff = 1).
    - **`hybrid_weekday3_weekend2` (Dynamic Hybrid):** 3 shifts (Morning, Evening, Night) on Monday through Friday; dynamically collapses Evening shift on Saturday and Sunday (min staff = 0 for Evening, Morning & Night active).
    - **`2_shifts` (Lean Operations):** Morning and Night active daily, Evening shift collapsed.
  - **1-Click UI Controls:** Added quick preset buttons in the Shift Staffing Demand modal (`Standard 3 Shifts`, `⚡ Dynamic 3Wk/2Wknd`, `🌙 Lean 2 Shifts`) to instantly reconfigure requirements without manual cell edits.

## 8. Labor Conflict Detection & One-Click Auto-Resolver
- **Detection Engine:** Real-time alignment between the CP-SAT solver invariants and UI grid validator:
  - Exact turnaround rest interval calculation (`calculate_inter_shift_rest_hours < min_rest_hours_after`) evaluated strictly between consecutive calendar days ($t$ and $t+1$).
  - Consecutive work days streak tracking with automatic resets on every rest day (`DO`, `COFF`, `VAC`, or empty slots).
  - Dedicated regular day-off violation checks.
- **One-Click Auto-Resolver (`POST /api/roster/{plan_id}/resolve-conflicts`):**
  - Identifies and automatically cleanses clashing assignments caused by manual overrides or staffing shifts.
  - Interactive Health Banner displays a vibrant amber warning and **"⚡ Auto-Resolve Conflicts"** button whenever rule conflicts are detected.

## 9. Verification & Test Suite
- Comprehensive automated test suite passing with 34/34 tests:
  - `tests/api/test_adv_features.py`: 8 tests covering flexible `DO` classification, auto-resolve conflicts API, dynamic shift regimes, advanced comp off settings, dedicated days off, vacations, find-replace, and system settings.
  - `tests/api/test_dedicated_shifts_and_export.py`: 4 tests for dedicated shift preference, clearing fixed off days, secondary float CRUD, and Excel/PDF generation.
  - `tests/api/test_bulk_and_canvas.py`: 7 tests covering bulk employee operations, canvas clearing, and distinct cell actions.
  - All existing unit, solver, and crawler regression tests passing 100%.
