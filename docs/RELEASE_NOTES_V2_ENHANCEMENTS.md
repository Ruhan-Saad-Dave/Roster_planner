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

## 5. Verification & Test Suite
- Comprehensive automated test suite passing with 30/30 tests:
  - `tests/api/test_dedicated_shifts_and_export.py`: 4 tests for dedicated shift preference, clearing fixed off days, secondary float CRUD, and Excel/PDF generation.
  - `tests/api/test_bulk_and_canvas.py`: 7 tests covering bulk employee operations, canvas clearing, and cell actions.
  - All existing unit, solver, and crawler regression tests passing 100%.
