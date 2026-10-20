# UI/UX & Desktop Interface Specification
## LocalRoster v2: Dynamic Offline Workforce Roster Planner

---

### 1. Design Principles & Technical Architecture

* **Core UX Philosophy: Progressive Disclosure (Zero Information Overload):**
  - **Simple Mode (Default):** 3-click workflow: Pick Month $\to$ Click "Generate Roster" $\to$ Review Health Banner $\to$ Export/Publish.
  - **Operations Cockpit Mode (On Demand):** Advanced mathematical weights, multi-variant exploration, raw constraint matrices, and MCP developer consoles are tucked inside sliding drawers or toggles.
* **Instant Clarity via Traffic-Light Roster Health Banner:**
  - 🟢 **Green (All Clear):** 100% shifts covered, zero ergonomic breaches, single-click publish.
  - 🟡 **Yellow (Operational Notice):** Covered using floaters or minor overtime variances.
  - 🔴 **Red (Action Required):** Unstaffed shifts accompanied by 1-click guided resolution cards.
* **Offline Asset Bundle:** Zero external dependencies. All CSS (Tailwind bundle), icons (inline SVG symbols), and JavaScript run directly from the local file bundle or local FastAPI static mount.
* **Component Framework:** Responsive HTML5 + compiled Tailwind CSS + Vanilla Reactive JavaScript state store (Alpine.js or lightweight reactive state controller).
* **Color System:** Dark/Light theme support with high-contrast accessibility compliance (WCAG AA).
  - **Success / Satisfied:** Emerald `#10B981`
  - **Warning / Floater Active:** Amber `#F59E0B`
  - **Danger / Staffing Deficit:** Crimson `#EF4444`
  - **Neutral / Backgrounds:** Slate `#0F172A` / `#F8FAFC`

---

### 2. Desktop Window Layout Architecture

The user interface provides a persistent top control bar, quick view switchers, collapsible department navigation, and responsive dual schedule rendering.

#### 2.1 The Persistent Traffic-Light Health Banner (Top of Screen)

```
+----------------------------------------------------------------------------------------------------------+
| [LocalRoster v2]  Plan: [November 2026 v]  [Mode: Simple v]               [Export v] [Settings] [Theme]  |
+----------------------------------------------------------------------------------------------------------+
| 🟢 ROSTER HEALTH: ALL CLEAR                                                                              |
| 180 of 180 shifts staffed. 0 ergonomic violations. 100% contracted hours met.   [ Publish Plan (1-Click) ]|
+----------------------------------------------------------------------------------------------------------+
  -- OR WHEN A DEFICIT OCCURS --
+----------------------------------------------------------------------------------------------------------+
| 🔴 ROSTER HEALTH: 1 SHORTAGE DETECTED (ICU Night Shift - Nov 14)                                         |
| [1-Click Fix 1: Borrow Floater Elena Rostova (ER)]  [1-Click Fix 2: Overtime for John Doe] [Ignore/Keep] |
+----------------------------------------------------------------------------------------------------------+
```

#### 2.2 Staff-Centric Layout (Rows = Employees, Columns = Dates)

```
+----------------------------------------------------------------------------------------------------------+
| [LocalRoster v2] Plan: [Nov 2026 Roster v] [Status: SOLVED] | [View: Staff-Centric v] [Export v] [Theme] |
| Toolbar: [Prefill Mode: OFF/ON] [Solve Remaining] [Regenerate All] [Import Wizard] [Analytics]          |
+----------------------------------------------------------------------------------------------------------+
| DEPARTMENTS (Toggles)      |  TIMELINE HEADER:  Nov 01 (Mo)  Nov 02 (Tu)  Nov 03 (We) ... Nov 30 (Th)     |
| [x] ICU (14)   [x] ER (12) |-----------------------------------------------------------------------------|
| [x] Surgical (8)           |  STAFF-CENTRIC GRID (Sticky Employee Column, Horizontal Virtual Scroll)      |
+----------------------------+                                                                             |
| EMPLOYEE ROSTER MATRIX     |  ICU (Department Section - Collapsible)                                     |
| Sarah Connor      [ICU]    |  [ MORN ]    [ 📌MORN ]   [ OFF  ]    [ NIGHT ]   [ OFF  ] (📌=Pinned)       |
| John Doe          [ICU]    |  [ NIGHT ]   [ OFF  ]    [ 📌OFF ]   [ MORN ]    [ MORN ]                   |
| Marcus Vance     *[ER]*    |  [ MORN*]    [ MORN*]    [ OFF  ]    [ OFF  ]    [ NIGHT ] (*Floater Badge) |
|                            |-----------------------------------------------------------------------------|
|                            |  COVERAGE SUMMARY FOOTER (Per Department)                                   |
|                            |  ICU Req: 3/3 [OK]   3/3 [OK]    2/3 [WARN]  3/3 [OK]                       |
|                            |  Deficit: 0          0           1 [DEFICIT] 0                              |
+----------------------------+-----------------------------------------------------------------------------+
| SIDEBAR / DRAWER: REAL-TIME CONSTRAINT INSPECTOR & CONFLICT DETECTOR                                     |
| Selected: Marcus Vance -> Nov 03 (Wed)                                                                   |
| [!] Warning: Floater from ER (Rank 2 Skill)                                                              |
| [X] Hard Conflict: Violates 14h Rest Interval (Previous: Night ends 07:30, Proposed: Morning starts 07:00) |
| [ Actions ]: [Pin Slot 📌]  [Revert Move]  [Force Override (Admin Lock)]                                 |
+----------------------------------------------------------------------------------------------------------+
```

#### 2.2 Demand/Slot-Centric Layout (Rows = Dates & Shift Slots, Cells = Assigned Staff)

```
+----------------------------------------------------------------------------------------------------------+
| [LocalRoster v2] Plan: [Nov 2026 Roster v] [Status: SOLVED] | [View: Slot-Centric v]  [Export v] [Theme] |
+----------------------------------------------------------------------------------------------------------+
| DATE / SHIFT SLOT       | REQUIRED | ASSIGNED WORKERS (Tags / Chips)                      | STATUS       |
|-------------------------+----------+------------------------------------------------------+--------------|
| Nov 01 (Mon) - ICU Morn | 3        | [Sarah Connor]  [John Doe]  [Marcus Vance (ER Floater)] | [3/3 OK]     |
| Nov 01 (Mon) - ICU Eve  | 2        | [Elena Rostova] [David Kim]                          | [2/2 OK]     |
| Nov 01 (Mon) - ICU Ngt  | 2        | [Alex Thorne]   [Unassigned Vacancy!]                | [1/2 DEFICIT]|
|-------------------------+----------+------------------------------------------------------+--------------|
| Nov 02 (Tue) - ICU Morn | 3        | [📌Sarah Connor] [John Doe] [Michael Chang]           | [3/3 OK]     |
| Nov 02 (Tue) - ICU Eve  | 2        | [Elena Rostova] [David Kim]                          | [2/2 OK]     |
+----------------------------------------------------------------------------------------------------------+
```

#### 2.3 Manager's Cross-Check Workload Audit Scorecard Layout

```
+----------------------------------------------------------------------------------------------------------------------+
| [LocalRoster v2] Plan: [Nov 2026 Roster v] | [View: Workload Audit Scorecard v] | [Export Audit to Excel]            |
| Search Staff: [             ]  Filter Dept: [All Depts v]   Sort By: [Variance (Overtime) v]                         |
+----------------------------------------------------------------------------------------------------------------------+
| EMPLOYEE NAME | DEPT | CONTRACT | TARGET | SCHED  | VARIANCE | SHIFTS (M/E/N) | DAYS OFF | WKND OFF | MAX STREAK | FLOATS |
|---------------+------+----------+--------+--------+----------+----------------+----------+----------+------------+--------|
| Sarah Connor  | ICU  | 40.0h/wk | 171.4h | 168.0h | -3.4h    | 20 (10/6/4)    | 10 days  | 4 days   | 5 consec   | 2 flt  |
| John Doe      | ICU  | 40.0h/wk | 171.4h | 170.0h | -1.4h    | 20 (12/5/3)    | 10 days  | 4 days   | 4 consec   | 0 flt  |
| Marcus Vance  | ER   | 40.0h/wk | 171.4h | 176.5h | +5.1h [!]| 21 (8/8/5)     | 9 days   | 3 days   | 5 consec   | 4 flt  |
| Elena Rostova | ICU  | 30.0h/wk | 128.5h | 127.5h | -1.0h    | 15 (8/7/0)     | 15 days  | 6 days   | 3 consec   | 0 flt  |
+----------------------------------------------------------------------------------------------------------------------+
| SUMMARY: 4 Employees Audited | Total Scheduled: 642.0 hrs | Overtime Flagged: 1 | Zero Ergonomic Violations Detected |
+----------------------------------------------------------------------------------------------------------------------+
```

#### 2.4 Multi-Variant Comparison & Promotion Modal Layout

```
+----------------------------------------------------------------------------------------------------------+
| CANDIDATE VARIANTS COMPARISON: November 2026 Planning Session (3 Generated)                            |
+----------------------------------------------------------------------------------------------------------+
| METRIC                    | VARIANT A (Balanced) [Active] | VARIANT B (Min Float) | VARIANT C (Max Pref) |
|---------------------------+-------------------------------+-----------------------+----------------------|
| Total Deficits (Shortage) | 0 [Clean]                     | 1 slot [Red]          | 0 [Clean]            |
| Cross-Department Floats   | 6 shifts                      | 2 shifts [Best]       | 8 shifts             |
| Night Shift Spread (Var)  | 0.45 [Very Fair]              | 0.58                  | 0.72                 |
| Total Employee Preference | +142 pts                      | +118 pts              | +210 pts [Highest]   |
| Solver Runtime            | 3.82s                         | 4.12s                 | 4.05s                |
| Discrepancy vs Active     | --- (Baseline)                | 24 cells differ       | 18 cells differ      |
|---------------------------+-------------------------------+-----------------------+----------------------|
| ACTION                    | [✓ Currently Selected]        | [Promote to Active]   | [Promote to Active]  |
+----------------------------------------------------------------------------------------------------------+
| [x] Highlight Differences in Schedule Grid: Differences glow in subtle cyan outline                     |
+----------------------------------------------------------------------------------------------------------+
```

---

### 3. Core Interface Views & Components

#### 3.1 Dual View Switcher (Staff-Centric vs. Slot-Centric)
- **Instant Toggle:** Top toolbar switch lets users toggle between Staff-Centric and Slot-Centric representations without reloading.
- **Staff-Centric View:** Ideal for assessing employee workload, consecutive streaks, and days off.
- **Slot-Centric View:** Ideal for operational dispatchers and shift heads verifying on-the-ground coverage per shift.

#### 3.2 Pre-Filling & "Solve Remaining Slots" Workflow
- **Prefill Toggle:** When active, clicking any cell opens a quick-assignment selector (e.g., assign specific shift or lock as "Requested Day Off").
- **Pin Badge `[📌]`:** Visually indicates that a cell is locked. The automated solver will never move, overwrite, or delete a pinned slot.
- **"Solve Remaining Blank Slots" Button:** Runs the CP-SAT engine strictly over empty cells while respecting all pre-filled constraints and labor rules.
- **Pre-Solve Conflict Alert Banner:** If a manager pins conflicting assignments (e.g., Night shift followed immediately by Morning shift), a warning banner appears detailing the conflict before triggering the solve.

#### 3.3 Historical Analytics & Trends Dashboard
A dedicated tab or view providing operational workforce analytics:
- **Coverage & Deficit Trends:** Multi-month bar/line charts showing demand vs. fulfillment and deficit frequency by department.
- **Floater Utilization Heatmap:** Tracks how often secondary floaters are pulled into other departments.
- **Workload Fairness & Equity Histogram:** Visualizes the distribution of unsociable shifts (Nights, Weekends) to confirm equitable burden-sharing.
- **Preference Satisfaction Gauge:** Measures what percentage of positive employee preferences were granted.

#### 3.4 Fast Data Onboarding & Import Wizard
A modal wizard simplifying initial setup:
- **Step 1: Download Templates:** One-click downloads for Department, Shift, Employee Directory, and Demand Matrix spreadsheet templates (`.xlsx` / `.csv`).
- **Step 2: Drag-and-Drop Dropzone:** Simple upload area accepting files.
- **Step 3: Interactive Validation Staging:** Displays a preview grid with red highlights for missing foreign keys or syntax errors, and a "Commit Import" button once validated.

#### 3.5 Extensible LLM Assistant Drawer (Future-Proofing Architecture)
- A sliding side drawer designed for natural language queries and edits.
- Architecture isolates UI actions into standardized commands:
  - *"Who is covering ICU Night on Saturday?"* $\to$ translates to `GET /api/roster/{id}?department_id=1&date=2026-11-07`.
  - *"Swap Sarah and John on Tuesday"* $\to$ executes validation checks and prompts manager confirmation.
- Connectable to local models (e.g. Ollama / llama.cpp on `localhost`) or external LLM APIs via configurable settings.

#### 3.2 Coverage Heatmap & Summary Bar
Directly beneath each department section, a live summary row computes:
- **Coverage Status Bar:**
  - **Green (Met):** Actual assigned staff $\ge RequiredStaff$.
  - **Yellow / Orange (Covered via Float):** Minimum demand met, but one or more slots are filled by floating staff.
  - **Red (Deficit):** Actual assigned staff $< RequiredStaff$. Displays clear numeric pill: `"-1 Worker Required"`.
- Clicking on a Red Deficit cell instantly opens the **Deficit Diagnostic Drawer**.

#### 3.3 Manual Assignment & Drag-and-Drop Conflict Inspector
* **Drag-and-Drop Interaction:**
  - Users can drag a shift badge to another date/slot or drag an employee into a vacant shift slot.
  - As soon as the drag begins, valid target cells highlight with subtle green borders, while forbidden cells (e.g. employee on approved leave or violating rest hours) show amber/red hatch patterns.
* **Instant Inspector Sidebar:**
  - Automatically pops up whenever an assignment is dragged or clicked.
  - Evaluates both **Hard Ergonomic Constraints** and **Soft Preference Impacts**:
    - *Hard Constraint Failure:* Displays red alert card with exact hourly calculation (e.g., `"Rest violation: Only 8.5 hours between shifts. Minimum required: 14.0 hours"`).
    - *Consecutive Days Warning:* `"Assigning this shift results in 6 consecutive working days (limit: 5)"`.
    - *Preference Warning:* `"Employee preference score for this shift is -4 (Strongly dislikes Wednesday nights)"`.
  - Buttons: **Cancel**, **Apply Regular**, **Force Override (with Audit Note)**.

#### 3.4 Multi-Skill & Floater Configuration Matrix
* A dedicated tab for setting cross-department agility:
  - Table listing all employees as rows and all departments as columns.
  - Each cell contains an interactive dropdown / toggle:
    - `Primary (Home)` (Locked to primary department)
    - `Rank 2: Qualified Floater`
    - `Rank 3: Emergency Only`
    - `Ineligible` (Cannot be assigned)
  - Batch editing tools (e.g., "Set all ICU nurses as Rank 2 in ER").

#### 3.5 Employee Shift Affinity Matrix
* Visual grid allowing managers or staff to record weekly preference profiles:
  - 5-point slider or colored pill selector for each shift type and day of week:
    - `+5` (Strongly Preferred / Green)
    - `+2` (Preferred / Light Green)
    - `0` (Neutral / Gray)
    - `-2` (Avoid if Possible / Light Amber)
    - `-5` (Strongly Dislike / Red)

#### 3.6 Deficit Diagnostic & Bottleneck Drawer
* When reviewing an infeasible-mitigated plan with deficits:
  - Comprehensive report listing every unstaffed shift.
  - Root Cause Analysis breakdown:
    - *Example:* "3 staff on simultaneous annual leave; remaining 2 staff blocked by 16h mandatory post-night rest interval. 0 qualified floaters available."
  - Suggested Resolution Options:
    1. Relax `min_staff` threshold for this single shift.
    2. Authorize an overtime override for an off-duty employee.
    3. Grant temporary floating eligibility to another department.

#### 3.7 Calendar-Aware Plan Creation Modal (Year & Month Picker)
* Clean setup dialog for generating a new roster:
  - **Year & Month Selectors:** Dropdown for Target Year (`2026`, `2027`, etc.) and Target Month (`November`).
  - **Auto-Calculated Horizon:** Automatically computes start date (`2026-11-01`), end date (`2026-11-30`), total days (30), and weekend counts (8 weekend days).
  - **Pre-fill Option:** Toggle between `"Start Empty (Full Solve)"` and `"Initialize Blank Canvas (For Pre-filling)"`.
  - **Solver Tuning:** Sliders for timeout (default: 15s), maximum consecutive working days (default: 5), and mandatory weekly rest days (default: 2).

#### 3.8 Department Operating Regime & Non-24x7 Schedule Editor
* Department configuration panel supporting diverse business operating hours:
  - **Operating Mode Toggle:**
    - `24x7 Continuous` (ICU, Inpatient, Security, 24h Customer Support).
    - `Weekdays Only (Mon–Fri)` (Outpatient Clinics, Administrative, Day Surgery).
    - `Custom Days & Shifts` (e.g. Mon–Sat 06:00–22:00, closed Sundays).
  - Selecting `Weekdays Only` or inactive shifts automatically zeros out weekend requirements and prevents shifts from being scheduled on non-operational days.

#### 3.9 Fast-Find Hierarchical Plan Storage & Search Navigator
* Dedicated Plan Management browser accessible from the top toolbar:
  - **Tree Taxonomy:** Indexed by `Year (e.g. 2026) -> Month (e.g. November) -> Sessions -> Variants`.
  - **Quick Search & Filter:** Instant search box to locate plans by name, date range, or creator. Quick chips for `[All]`, `[Published]`, `[Drafts]`, `[With Deficits]`.
  - **Variant Badges:** Sibling variants within a planning session are displayed as interactive chips (`Variant A [Active]`, `Variant B`, `Variant C`), allowing one-click preview and promotion without losing historical iterations.

#### 3.10 Native Model Context Protocol (MCP) & AI Assistant Drawer
* Slide-out AI Operations Console:
  - **Connection Status Indicator:** Displays `MCP Server: Active (Localhost:8000/api/mcp)` with tool call audit logging.
  - **Interactive Assistant Bar:** Allows managers or connected external agents to execute natural-language queries (e.g., *"Show me all floaters in ICU this weekend"*, *"Check if John Doe can work Friday night"*, *"Generate 3 variants for December 2026 prioritizing preference satisfaction"*).
  - **Dry-Run Confirmation Card:** Displays what an agent proposes to change (with real-time constraint validation) before applying changes to the database.

#### 3.11 Excel-Style Categorized Ribbon Navigation
* Replaces monolithic multi-button toolbars with clean contextual tabs:
  - **`📋 Schedule & Solve` Tab:** Roster generation (`+ New Roster`), active solve operations (`Solve Remaining`, `Prefill Mode`), variant comparison (`Compare Variants`), view selectors (Staff/Slot/Scorecard), preceding month toggle (`📅 Prev Month`), and display density modes.
  - **`🏢 Organization & Staff` Tab:** Direct database administration (`⚙️ Manage Org` for department operating regimes, staff contracts, and live color pickers) and spreadsheet data ingestion (`📥 Import CSV / Excel Data`).
  - **`📊 Reports & Exports` Tab:** Instant distribution formats: multi-tab Excel workbooks (`Export Formatted Excel .xlsx`) and printable landscape vectors (`Export PDF`).
  - **`👁️ View Options` Tab:** Layout toggles (`Toggle Dept Sidebar`, `Toggle Inspector`) and pane geometry reset (`Reset Sidebar Widths`).

#### 3.12 Excel-Style Bottom Status Bar & Dynamic Zoom Engine
* Persistent footer modeled after modern productivity spreadsheets:
  - **Left Section (Health & Plan Telemetry):** Real-time health badge (`🟢 100% Staffed`), active roster plan code, and department/staff headcounts.
  - **Middle Section (View Mode Shortcuts):** Quick-switch icons for Staff-Centric matrix, Slot-Centric matrix, and Workload Audit Scorecard.
  - **Right Section (Interactive Zoom Engine):**
    - Continuous zoom slider spanning 65% (bird's-eye monthly overview) to 160% (high-visibility shift inspection).
    - Discrete step buttons `[−]` and `[+]` (10% increments).
    - One-click `[100%]` reset button.
    - Synchronized dual-scaling via CSS custom variable `--zoom-factor` and document zoom styling.

#### 3.13 Resizable Drag-Splitters & Pane Management
* Vertical splitter handles separating the Department Filter panel, Central Schedule Grid, and Shift Inspector panel:
  - Smooth pointer-drag resizing with min/max safety limits (160px–500px).
  - Immediate responsive reflow of schedule grid columns.
  - Instant reset button to restore default proportions.

#### 3.14 First-Time Manager Onboarding Wizard
* Welcoming modal prompt for clean database installations:
  - Offers immediate choice between **"📥 Import My Data"** (CSV template upload) and **"⚡ Start from Scratch"** (pre-loaded sample hospital wards and medical staff).
  - Includes interactive help documentation and 3-step quick start guide.

#### 3.15 Manage Organization Multi-Select & Bulk Operations
* Comprehensive batch management in the Staff Directory table:
  - Header "Select All" checkbox with automatic indeterminate state tracking.
  - Row checkboxes on every employee entry.
  - Floating bulk actions toolbar displaying selected headcount (`{N} employees selected`).
  - **`✏️ Bulk Edit Selected` Modal:** Allows bulk-updating primary department, max weekly contracted hours, recurring dedicated days off, and active status in one click.
  - **`🗑️ Bulk Delete Selected` Action:** Protected confirmation dialog for fast clean-up of staff entries and related eligibility records.

#### 3.16 Clear All Cells / Reset Canvas
* Ribbon action (`🗑️ Clear Canvas`) in the Schedule & Solve pane:
  - Opens a confirmation dialog allowing managers to wipe all shift assignments and deficits from the active roster plan.
  - Provides a clean slate for manual painting or re-solving while preserving employees, departments, demand rules, and vacation records.

#### 3.17 Distinct Cell States in Shift Inspector (Empty vs Pinned Day Off vs Pinned Comp Off)
* Replaces ambiguous clear buttons with three distinct actions:
  - **`🗑️ Set as Empty (Fillable by Solver)`:** Removes assignments and single-day off records; cell is marked blank so the CP-SAT optimization algorithm can assign shifts to satisfy demand.
  - **`📌 Pin as Day OFF (DO)`:** Locks the cell as an explicit Day OFF badge (`📌 DO`). Enforces hard constraint $Y_{e, t} = 0$, guaranteeing the solver never schedules the worker.
  - **`☕ Pin as Comp Off (Coff)`:** Locks the cell as a Compensatory Off badge (`☕ COFF`). Enforces hard constraint $Y_{e, t} = 0$, guaranteeing the solver never schedules the worker.
  - **`Pin Shift 📌`:** Locks the assigned work shift (e.g. MORN, EVE, NIGHT) so the solver does not alter or reassign it.

#### 3.18 Cell Hover Preview Popover Engine
* Eliminates visual clutter (removed raw `*` and bracket `*(DEPT)` notation from cell badges) in favor of clean badges with elegant floating tags (`⇄ ICU`).
* **Delayed Hover Popover (`#cell-hover-popover`):**
  - Triggers smoothly after a 280ms hover delay (preventing distracting flickers during rapid grid scrolling).
  - Displays comprehensive telemetry:
    - Employee Full Name, Code, and Home Department.
    - Full Date and Day of Week (e.g., `Nov 15, 2026 (Sun)`).
    - Shift Type, Official Name, and exact operating hours (`07:00 – 15:30 (8.5h)`).
    - Floating Coverage Details (Target Ward & Tier-2 Floater rank).
    - Manager Lock Status (`📌 Pinned by Manager` vs `⚡ Solved by CP-SAT`).
    - Ergonomic Conflict Warning Banner (with specific violation reasons).
  - Closes automatically on `mouseleave` or when the cell is clicked for editing.

#### 3.19 Direct Sidebar Collapse & Expand Controls (AI Workspace Style)
* Relocates sidebar toggles directly onto the sidebars and workspace edges, modeled after modern AI agent developer interfaces (ChatGPT, Claude, Cursor, Antigravity IDE):
  - **Left Departments Sidebar (`#dept-sidebar`):**
    - Collapse icon button `[◀]` located directly in the sidebar header row (`#sidebar-left-collapse-btn`).
    - When collapsed, a subtle floating expand tab (`#sidebar-left-expand-btn`) docks neatly on the left workspace edge.
  - **Right Inspector Panel (`#inspector-panel`):**
    - Collapse icon button `[▶]` located directly in the inspector header row (`#sidebar-right-collapse-btn`).
    - When collapsed, a subtle floating expand tab (`#sidebar-right-expand-btn`) docks neatly on the right workspace edge.
  - Selecting any grid cell automatically re-expands the inspector panel for immediate shift editing.
  - Ribbon toggle buttons remain synchronized as secondary global shortcuts.

---

### 4. Offline State Management & Resilience Patterns

1. **Zero External CDN Dependencies:**
   - Fonts: Bundled System UI stack (`system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`).
   - CSS: Pre-compiled Tailwind CSS static stylesheet.
   - Icons: Inline SVG component library.
2. **Optimistic UI Updates:**
   - Manual drag-and-drop actions update the client state immediately.
   - Background API call validates and persists to SQLite.
   - If the server rejects the assignment (due to an un-overridden hard constraint), the badge snaps back to its original position with an explanatory toast notification.
3. **Solver Progress Polling / SSE:**
   - During generation, an animated progress modal displays solver phases: `Building Model...` $\to$ `Searching Integer Solutions...` $\to$ `Optimizing Fairness & Floating...` $\to$ `Finalizing Roster`.
   - Elapsed timer and progress bar with automatic cancellation button.
