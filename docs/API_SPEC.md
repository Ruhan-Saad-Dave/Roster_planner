# REST API Contract & Interface Specification
## LocalRoster v2: Dynamic Offline Workforce Roster Planner

---

### 1. API Architecture & Standards

* **Base URL:** `http://127.0.0.1:8000/api`
* **Protocol:** HTTP/1.1 RESTful JSON
* **Authentication:** Localhost trust model (no remote authentication required in offline standalone mode).
* **Standard Response Envelope (Errors):**
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Department with ID 4 does not exist.",
    "details": {}
  }
}
```

---

### 2. Department & Demand Matrix Endpoints

#### 2.1 List & Create Departments
* **`GET /api/departments`**
  - **Query Parameters:** `active_only: bool = true`
  - **Response 200 OK:**
  ```json
  [
    {
      "id": 1,
      "code": "ICU",
      "name": "Intensive Care Unit",
      "color_code": "#EF4444",
      "operating_regime": "24_7",
      "is_active": true,
      "employee_count": 14
    },
    {
      "id": 2,
      "code": "OUTPATIENT",
      "name": "Outpatient Clinic",
      "color_code": "#10B981",
      "operating_regime": "WEEKDAYS_ONLY",
      "is_active": true,
      "employee_count": 6
    }
  ]
  ```

* **`POST /api/departments`**
  - **Request Body:**
  ```json
  {
    "code": "SURG",
    "name": "Surgical Ward",
    "color_code": "#10B981",
    "operating_regime": "24_7"
  }
  ```
  - **Response 201 Created:** Returns created department object.

#### 2.2 Configure Shift Types
* **`GET /api/shift-types`**
  - **Response 200 OK:**
  ```json
  [
    {
      "id": 1,
      "code": "MORN",
      "name": "Morning Shift",
      "start_time": "07:00:00",
      "end_time": "15:30:00",
      "duration_hours": 8.5,
      "min_rest_hours_after": 14,
      "is_night_shift": false,
      "is_active": true
    },
    {
      "id": 2,
      "code": "NIGHT",
      "name": "Night Shift",
      "start_time": "23:00:00",
      "end_time": "07:30:00",
      "duration_hours": 8.5,
      "min_rest_hours_after": 16,
      "is_night_shift": true,
      "is_active": true
    }
  ]
  ```

* **`POST /api/shift-types`**
  - **Request Body:**
  ```json
  {
    "code": "EVE",
    "name": "Evening Shift",
    "start_time": "15:00:00",
    "end_time": "23:30:00",
    "duration_hours": 8.5,
    "min_rest_hours_after": 14,
    "is_night_shift": false
  }
  ```
  - **Response 201 Created:** Returns created shift type.

#### 2.3 Department Staffing Demand Matrix
* **`GET /api/departments/{id}/requirements`**
  - **Response 200 OK:**
  ```json
  [
    {
      "id": 101,
      "department_id": 1,
      "shift_type_id": 1,
      "shift_code": "MORN",
      "day_of_week": 0,
      "min_staff": 3,
      "optimal_staff": 4
    },
    {
      "id": 102,
      "department_id": 1,
      "shift_type_id": 2,
      "shift_code": "NIGHT",
      "day_of_week": 0,
      "min_staff": 2,
      "optimal_staff": 2
    }
  ]
  ```

* **`PUT /api/departments/{id}/requirements`**
  - **Request Body:**
  ```json
  {
    "requirements": [
      {
        "shift_type_id": 1,
        "day_of_week": 0,
        "min_staff": 3,
        "optimal_staff": 4
      },
      {
        "shift_type_id": 2,
        "day_of_week": 0,
        "min_staff": 2,
        "optimal_staff": 2
      }
    ]
  }
  ```
  - **Response 200 OK:** Returns updated requirement records.

---

### 3. Employee, Eligibility & Preference Endpoints

#### 3.1 Employee Directory
* **`GET /api/employees`**
  - **Query Parameters:** `department_id: Optional[int]`, `active_only: bool = true`
  - **Response 200 OK:**
  ```json
  [
    {
      "id": 10,
      "employee_code": "EMP010",
      "name": "Sarah Connor",
      "email": "sarah@localroster.internal",
      "primary_department_id": 1,
      "primary_department_name": "Intensive Care Unit",
      "max_hours_week": 40.0,
      "is_active": true,
      "secondary_departments": [
        {
          "department_id": 2,
          "department_name": "Emergency Room",
          "preference_rank": 2,
          "can_float": true
        }
      ]
    }
  ]
  ```

* **`POST /api/employees`**
  - **Request Body:**
  ```json
  {
    "employee_code": "EMP011",
    "name": "John Doe",
    "email": "john@localroster.internal",
    "primary_department_id": 2,
    "max_hours_week": 40.0
  }
  ```
  - **Response 201 Created:** Returns created employee.

#### 3.2 Update Floating Eligibility & Department Ranks
* **`PUT /api/employees/{id}/eligibility`**
  - **Request Body:**
  ```json
  {
    "eligibilities": [
      {
        "department_id": 1,
        "preference_rank": 1,
        "can_float": true
      },
      {
        "department_id": 2,
        "preference_rank": 2,
        "can_float": true
      },
      {
        "department_id": 3,
        "preference_rank": 3,
        "can_float": true
      }
    ]
  }
  ```
  - **Response 200 OK:** Returns updated eligibility list.

#### 3.3 Employee Shift Preferences Matrix
* **`PUT /api/employees/{id}/preferences`**
  - **Request Body:**
  ```json
  {
    "preferences": [
      { "shift_type_id": 1, "day_of_week": 0, "preference_score": 5 },
      { "shift_type_id": 2, "day_of_week": 4, "preference_score": -4 }
    ]
  }
  ```
  - **Response 200 OK:** Returns saved preference scores.

#### 3.4 Leave & Absence Management
* **`GET /api/leaves`**
  - **Query Parameters:** `start_date: str`, `end_date: str`, `employee_id: Optional[int]`
  - **Response 200 OK:**
  ```json
  [
    {
      "id": 45,
      "employee_id": 10,
      "employee_name": "Sarah Connor",
      "start_date": "2026-11-05",
      "end_date": "2026-11-09",
      "leave_type": "VACATION",
      "status": "APPROVED",
      "notes": "Approved annual holiday"
    }
  ]
  ```

* **`POST /api/leaves`**
  - **Request Body:**
  ```json
  {
    "employee_id": 10,
    "start_date": "2026-11-05",
    "end_date": "2026-11-09",
    "leave_type": "VACATION",
    "status": "APPROVED",
    "notes": "Annual Leave"
  }
  ```
  - **Response 201 Created:** Returns leave record.

---

### 4. Roster Planning, Solver Execution & Diagnostics

#### 4.1 Trigger Solver Generation & Multi-Variant Exploration
* **`POST /api/roster/generate`**
  - **Request Body:**
  ```json
  {
    "name": "November 2026 Roster",
    "planning_year": 2026,
    "planning_month": 11,
    "start_date": "2026-11-01",
    "end_date": "2026-11-30",
    "variant_count": 3,
    "variant_strategies": ["BALANCED", "FLOAT_AVERSE", "PREFERENCE_MAX"],
    "timeout_seconds": 15,
    "max_consecutive_days": 5,
    "min_rest_days_per_week": 2
  }
  ```
  - **Response 200 OK:**
  ```json
  {
    "session_id": "sess_202611_abc123",
    "planning_year": 2026,
    "planning_month": 11,
    "variants_generated": [
      {
        "plan_id": 12,
        "variant_name": "Variant A (Balanced)",
        "variant_strategy": "BALANCED",
        "is_active_variant": true,
        "status": "SOLVED",
        "solve_time_seconds": 3.82,
        "total_deficits": 0,
        "total_floats": 6,
        "preference_score": 142
      },
      {
        "plan_id": 13,
        "variant_name": "Variant B (Float-Averse)",
        "variant_strategy": "FLOAT_AVERSE",
        "is_active_variant": false,
        "status": "SOLVED",
        "solve_time_seconds": 4.12,
        "total_deficits": 1,
        "total_floats": 2,
        "preference_score": 118
      },
      {
        "plan_id": 14,
        "variant_name": "Variant C (Max Preference)",
        "variant_strategy": "PREFERENCE_MAX",
        "is_active_variant": false,
        "status": "SOLVED",
        "solve_time_seconds": 4.05,
        "total_deficits": 0,
        "total_floats": 8,
        "preference_score": 210
      }
    ]
  }
  ```

* **`POST /api/roster/compare-variants`**
  - **Request Body:**
  ```json
  {
    "variant_plan_ids": [12, 13, 14]
  }
  ```
  - **Response 200 OK (Side-by-Side Metrics & Cell Discrepancies):**
  ```json
  {
    "metrics_comparison": [
      { "plan_id": 12, "name": "Variant A", "deficits": 0, "floats": 6, "preference_score": 142, "variance": 0.45 },
      { "plan_id": 13, "name": "Variant B", "deficits": 1, "floats": 2, "preference_score": 118, "variance": 0.58 },
      { "plan_id": 14, "name": "Variant C", "deficits": 0, "floats": 8, "preference_score": 210, "variance": 0.72 }
    ],
    "discrepancy_count_between_12_and_14": 18,
    "cell_differences": [
      {
        "date": "2026-11-04",
        "employee_id": 10,
        "employee_name": "Sarah Connor",
        "assignment_by_plan": {
          "12": { "shift": "MORN", "dept": "ICU" },
          "13": { "shift": "OFF", "dept": null },
          "14": { "shift": "EVE", "dept": "ICU" }
        }
      }
    ]
  }
  ```

* **`POST /api/roster/{id}/promote`**
  - **Response 200 OK:** Sets specified plan ID as `is_active_variant = TRUE`, archives or demotes sibling variants in the same session, and marks plan ready for publishing.

#### 4.2 Fetch Roster Plan Details & Dual View Data
* **`GET /api/roster/{id}`**
  - **Query Parameters:**
    - `department_id: Optional[int]`
    - `view: Optional[str] = "staff_centric"` (Options: `"staff_centric"` or `"slot_centric"`)
  - **Response 200 OK (when `view=staff_centric`):**
  ```json
  {
    "plan": {
      "id": 12,
      "name": "November 2026 Roster",
      "start_date": "2026-11-01",
      "end_date": "2026-11-30",
      "status": "SOLVED",
      "total_deficits": 2,
      "total_floats": 7
    },
    "view_type": "staff_centric",
    "rows": [
      {
        "employee_id": 10,
        "employee_code": "EMP010",
        "employee_name": "Sarah Connor",
        "primary_department_id": 1,
        "primary_department_name": "ICU",
        "assignments": {
          "2026-11-01": {
            "shift_id": 1,
            "shift_code": "MORN",
            "department_id": 2,
            "department_code": "ER",
            "is_floating": true,
            "float_rank": 2,
            "is_pinned": false,
            "is_manual_override": false
          },
          "2026-11-02": {
            "shift_id": 1,
            "shift_code": "MORN",
            "department_id": 1,
            "department_code": "ICU",
            "is_floating": false,
            "float_rank": 1,
            "is_pinned": true,
            "is_manual_override": true
          }
        }
      }
    ],
    "coverage_summary": [
      {
        "date": "2026-11-01",
        "department_id": 1,
        "shift_type_id": 1,
        "required": 3,
        "assigned": 3,
        "deficit": 0,
        "floating_count": 0
      }
    ]
  }
  ```
  - **Response 200 OK (when `view=slot_centric`):**
  ```json
  {
    "plan_id": 12,
    "view_type": "slot_centric",
    "slots": [
      {
        "date": "2026-11-01",
        "department_id": 1,
        "department_code": "ICU",
        "shift_type_id": 1,
        "shift_code": "MORN",
        "required_staff": 3,
        "assigned_staff": [
          { "employee_id": 10, "name": "Sarah Connor", "is_floating": false, "is_pinned": false },
          { "employee_id": 11, "name": "John Doe", "is_floating": false, "is_pinned": true },
          { "employee_id": 14, "name": "Marcus Vance", "is_floating": true, "float_rank": 2, "is_pinned": false }
        ],
        "deficit": 0
      }
    ]
  }
  ```

#### 4.3 Pre-Filling & Partial Roster Completion ("Fill Remaining Slots")
* **`POST /api/roster/{id}/prefill`**
  - **Request Body:**
  ```json
  {
    "assignments": [
      {
        "employee_id": 10,
        "department_id": 1,
        "shift_type_id": 1,
        "date": "2026-11-02",
        "is_pinned": true
      },
      {
        "employee_id": 11,
        "department_id": null,
        "shift_type_id": null,
        "date": "2026-11-03",
        "is_pinned": true,
        "is_locked_off": true
      }
    ]
  }
  ```
  - **Response 200 OK:** Returns count of successfully pinned slots and pre-solve conflict check result.

* **`POST /api/roster/{id}/solve-remaining`**
  - **Request Body:**
  ```json
  {
    "timeout_seconds": 15,
    "preserve_all_pinned": true,
    "weights": {
      "deficit": 1000000,
      "float_rank2": 1000,
      "float_rank3": 5000,
      "fairness": 50,
      "preferences": 10
    }
  }
  ```
  - **Response 200 OK:** Executes CP-SAT on all non-pinned cells, maintaining every prefilled slot as a hard constraint.

* **`DELETE /api/roster/{id}/prefill`**
  - **Query Parameters:** `employee_id: Optional[int]`, `date: Optional[str]`
  - **Response 200 OK:** Unpins specified slots (or all pinned slots if parameters omitted).

* **`DELETE /api/roster/{id}/assignments`**
  - **Query Parameters:** `employee_id: int`, `date: str`
  - **Response 200 OK:** Removes assignment on specified date and marks worker as Day OFF.
  ```json
  {
    "plan_id": 12,
    "employee_id": 10,
    "date": "2026-11-01",
    "cleared": true
  }
  ```

* **`POST /api/roster/{id}/assignments/toggle-pin`**
  - **Query Parameters:** `employee_id: int`, `date: str`
  - **Response 200 OK:** Toggles assignment between pinned (`📌`) and unpinned.
  ```json
  {
    "plan_id": 12,
    "employee_id": 10,
    "date": "2026-11-01",
    "is_pinned": true
  }
  ```

#### 4.4 Solver Diagnostics & Deficit Root-Cause Analysis
* **`GET /api/roster/{id}/diagnostics`**
  - **Response 200 OK:**
  ```json
  {
    "plan_id": 12,
    "total_deficits": 2,
    "deficit_slots": [
      {
        "date": "2026-11-01",
        "department_id": 2,
        "department_name": "Emergency Room",
        "shift_type_id": 2,
        "shift_name": "Night Shift",
        "shortage_count": 1,
        "reason_code": "CONCURRENT_LEAVES",
        "diagnosis": "2 of 4 regular ER staff on approved leave; remaining 2 staff blocked by 16h mandatory post-night rest interval. No eligible floaters available across other wards."
      }
    ],
    "workload_equity": {
      "avg_nights_per_employee": 4.2,
      "max_nights": 5,
      "min_nights": 3,
      "equity_status": "EXCELLENT"
    }
  }
  ```

#### 4.5 Manager's Workload Cross-Check Audit Scorecard
* **`GET /api/roster/{id}/summary`**
  - **Query Parameters:** `department_id: Optional[int]`
  - **Response 200 OK:**
  ```json
  {
    "plan_id": 12,
    "planning_year": 2026,
    "planning_month": 11,
    "total_calendar_days": 30,
    "employee_scorecards": [
      {
        "employee_id": 10,
        "employee_code": "EMP010",
        "name": "Sarah Connor",
        "primary_department": "ICU",
        "contracted_hours_week": 40.0,
        "target_hours_month": 171.4,
        "scheduled_hours": 168.0,
        "variance_hours": -3.4,
        "total_shifts": 20,
        "shift_breakdown": {
          "MORN": 10,
          "EVE": 6,
          "NIGHT": 4
        },
        "days_off_count": 10,
        "weekend_days_off_count": 4,
        "max_consecutive_days_worked": 5,
        "floating_shifts_count": 2,
        "preference_satisfaction_score": 18
      },
      {
        "employee_id": 11,
        "employee_code": "EMP011",
        "name": "John Doe",
        "primary_department": "ICU",
        "contracted_hours_week": 40.0,
        "target_hours_month": 171.4,
        "scheduled_hours": 170.0,
        "variance_hours": -1.4,
        "total_shifts": 20,
        "shift_breakdown": {
          "MORN": 12,
          "EVE": 5,
          "NIGHT": 3
        },
        "days_off_count": 10,
        "weekend_days_off_count": 4,
        "max_consecutive_days_worked": 4,
        "floating_shifts_count": 0,
        "preference_satisfaction_score": 15
      }
    ]
  }
  ```

---

### 5. Real-Time Drag-and-Drop Constraint Validation

When a user attempts to manually reassign a shift in the UI, the frontend calls this endpoint to validate against ergonomic and labor rules before applying the update.

* **`POST /api/roster/validate-assignment`**
  - **Request Body:**
  ```json
  {
    "plan_id": 12,
    "employee_id": 10,
    "target_department_id": 2,
    "target_shift_type_id": 1,
    "target_date": "2026-11-03"
  }
  ```
  - **Response 200 OK (Clean / Valid):**
  ```json
  {
    "is_valid": true,
    "can_override": true,
    "violations": [],
    "warnings": [
      {
        "code": "FLOAT_ASSIGNMENT",
        "message": "Sarah Connor will be floating to ER (Rank 2 backup skill)."
      }
    ]
  }
  ```
  - **Response 200 OK (Hard Constraint Breach):**
  ```json
  {
    "is_valid": false,
    "can_override": true,
    "violations": [
      {
        "code": "REST_INTERVAL_VIOLATION",
        "type": "HARD",
        "message": "Insufficient rest: Employee works Night Shift on 2026-11-02 (ends 07:30); target Morning Shift on 2026-11-03 starts 07:00 (rest interval: -0.5 hrs, minimum required: 16 hrs)."
      },
      {
        "code": "MAX_CONSECUTIVE_DAYS",
        "type": "HARD",
        "message": "Exceeds maximum 5 consecutive working days (would create 6 consecutive shifts)."
      }
    ],
    "warnings": []
  }
  ```

* **`POST /api/roster/{id}/assignments` (Commit Manual Assignment)**
  - **Request Body:**
  ```json
  {
    "employee_id": 10,
    "department_id": 2,
    "shift_type_id": 1,
    "date": "2026-11-03",
    "force_override": true
  }
  ```
  - **Response 200 OK:** Updates assignment, recalculates coverage and deficit logs.

---

### 6. Export Endpoints

* **`GET /api/export/{id}/excel`**
  - **Query Parameters:**
    - `view: Optional[str] = "both"` (Options: `"staff_centric"`, `"slot_centric"`, `"both"`)
  - Generates multi-tab workbook with openpyxl:
    - Tab 1: Staff-Centric Master Schedule (Rows = Staff, Columns = Dates, color badges, floater tags).
    - Tab 2: Slot-Centric Schedule (Rows = Dates/Shifts, Columns = Required/Assigned staff names).
    - Tab 3 to N: Individual Department Views.
    - Tab N+1: Deficit & Floating Audit Log.
  - **Response 200 OK:** Binary stream `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
  - Header: `Content-Disposition: attachment; filename="Roster_Plan_12.xlsx"`

* **`GET /api/export/{id}/pdf`**
  - **Query Parameters:**
    - `view: Optional[str] = "staff_centric"` (Options: `"staff_centric"` or `"slot_centric"`)
  - Generates high-density vector-rendered printable PDF schedule formatted in landscape.
  - **Response 200 OK:** Binary stream `application/pdf`.
  - Header: `Content-Disposition: attachment; filename="Roster_Plan_12.pdf"`

---

### 7. Bulk Data Onboarding & Import Endpoints

Enables managers to bootstrap the system rapidly via spreadsheets rather than manual entry.

* **`GET /api/import/template/{entity_type}`**
  - **Path Parameter:** `entity_type` $\in$ `['departments', 'shifts', 'employees', 'demands', 'leaves']`
  - **Response 200 OK:** Pre-formatted `.xlsx` or `.csv` template with column headers, sample data, and validation annotations.

* **`POST /api/import/preview/{entity_type}`**
  - **Payload:** `multipart/form-data` with `file: UploadFile`
  - **Response 200 OK (Staging & Validation Summary):**
  ```json
  {
    "entity_type": "employees",
    "total_rows": 25,
    "valid_rows": 23,
    "invalid_rows": 2,
    "errors": [
      {
        "row_number": 4,
        "employee_code": "EMP004",
        "field": "primary_department_code",
        "error": "Referenced department 'NEURO' does not exist."
      },
      {
        "row_number": 12,
        "employee_code": "EMP012",
        "field": "max_hours_week",
        "error": "Value '-10' must be a positive number."
      }
    ],
    "preview_sample": [
      {
        "employee_code": "EMP001",
        "name": "Alice Morgan",
        "primary_department": "ICU",
        "max_hours_week": 40.0,
        "status": "VALID"
      }
    ]
  }
  ```

* **`POST /api/import/commit/{entity_type}`**
  - **Payload:** `multipart/form-data` with `file: UploadFile` and `skip_invalid: bool = false`
  - **Response 201 Created:** Returns count of successfully imported records.

---

### 8. Historical Analytics & Visualization Endpoints

Provides aggregated data for charts and past/current roster comparisons.

* **`GET /api/analytics/summary`**
  - **Response 200 OK:**
  ```json
  {
    "total_plans_generated": 14,
    "historical_coverage_rate": 98.4,
    "total_deficits_recorded": 18,
    "total_floating_hours": 342.5,
    "average_solve_time_seconds": 3.8
  }
  ```

* **`GET /api/analytics/department-trends`**
  - **Query Parameters:** `start_date: str`, `end_date: str`
  - **Response 200 OK:**
  ```json
  [
    {
      "department_id": 1,
      "department_code": "ICU",
      "monthly_coverage": [
        { "month": "2026-08", "demand_slots": 180, "fulfilled_slots": 180, "deficits": 0, "floater_absorbed": 12 },
        { "month": "2026-09", "demand_slots": 180, "fulfilled_slots": 178, "deficits": 2, "floater_absorbed": 15 }
      ]
    }
  ]
  ```

* **`GET /api/analytics/equity`**
  - **Query Parameters:** `plan_id: Optional[int]`
  - **Response 200 OK:**
  ```json
  {
    "night_shift_distribution": [
      { "employee_id": 10, "employee_name": "Sarah Connor", "night_count": 4, "weekend_count": 3, "float_count": 1 },
      { "employee_id": 11, "employee_name": "John Doe", "night_count": 4, "weekend_count": 2, "float_count": 0 }
    ],
    "variance_score": 0.42,
    "fairness_rating": "HIGH"
  }
  ```

---

### 9. Native Model Context Protocol (MCP) & AI Agent Integration Specification

LocalRoster v2 natively implements the **Model Context Protocol (MCP)** standard. External AI agents (such as Claude Desktop, local LLMs running on Ollama / llama.cpp, or custom multi-agent workflows) can interface with the rostering system via JSON-RPC or REST endpoints.

#### 9.1 Discovery Endpoints
* **`GET /api/mcp/manifest`**
  - Returns server identity, protocol version (`2024-11-05`), and list of supported capabilities (Tools, Resources, Prompts).
* **`GET /api/mcp/tools`**
  - Returns tool descriptions and JSON schemas conforming to the MCP Tool specification.

#### 9.2 Registered MCP Tool Definitions

```json
[
  {
    "name": "roster_get_departments",
    "description": "Retrieve all departments, operational regimes (24x7 or weekdays), and active staff counts.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "active_only": { "type": "boolean", "default": true }
      }
    }
  },
  {
    "name": "roster_get_schedule",
    "description": "Fetch the roster schedule for a given plan and optional department or date range.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "plan_id": { "type": "integer", "description": "ID of the roster plan" },
        "department_id": { "type": "integer", "description": "Optional department filter" },
        "view": { "type": "string", "enum": ["staff_centric", "slot_centric"], "default": "staff_centric" }
      },
      "required": ["plan_id"]
    }
  },
  {
    "name": "roster_validate_assignment",
    "description": "Validate whether assigning an employee to a shift violates ergonomic rules, rest intervals, or maximum consecutive days.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "plan_id": { "type": "integer" },
        "employee_id": { "type": "integer" },
        "target_department_id": { "type": "integer" },
        "target_shift_type_id": { "type": "integer" },
        "target_date": { "type": "string", "format": "date" }
      },
      "required": ["plan_id", "employee_id", "target_department_id", "target_shift_type_id", "target_date"]
    }
  },
  {
    "name": "roster_generate_variants",
    "description": "Trigger CP-SAT solver to generate 1 to 4 candidate roster variants for a given year and month.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "planning_year": { "type": "integer" },
        "planning_month": { "type": "integer" },
        "variant_count": { "type": "integer", "default": 3 },
        "timeout_seconds": { "type": "integer", "default": 15 }
      },
      "required": ["planning_year", "planning_month"]
    }
  },
  {
    "name": "roster_compare_variants",
    "description": "Compare metrics (deficits, floats, fairness, preferences) and cell assignment discrepancies across multiple variants.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "variant_plan_ids": { "type": "array", "items": { "type": "integer" } }
      },
      "required": ["variant_plan_ids"]
    }
  },
  {
    "name": "roster_promote_variant",
    "description": "Promote a candidate variant to be the active published roster plan.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "plan_id": { "type": "integer" }
      },
      "required": ["plan_id"]
    }
  },
  {
    "name": "roster_prefill_shifts",
    "description": "Pre-fill or pin specific shifts or requested days off before solving remaining blank slots.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "plan_id": { "type": "integer" },
        "assignments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "employee_id": { "type": "integer" },
              "department_id": { "type": "integer" },
              "shift_type_id": { "type": "integer" },
              "date": { "type": "string" },
              "is_locked_off": { "type": "boolean", "default": false }
            },
            "required": ["employee_id", "date"]
          }
        }
      },
      "required": ["plan_id", "assignments"]
    }
  },
  {
    "name": "roster_get_workload_audit",
    "description": "Retrieve the manager's workload audit scorecard (scheduled hours, overtime variance, shift counts, days off) per employee.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "plan_id": { "type": "integer" },
        "department_id": { "type": "integer" }
      },
      "required": ["plan_id"]
    }
  }
]
```

#### 9.3 MCP Tool Execution Handler
* **`POST /api/mcp/execute`**
  - **Request Body (Standard JSON-RPC 2.0 / MCP):**
  ```json
  {
    "tool": "roster_validate_assignment",
    "arguments": {
      "plan_id": 12,
      "employee_id": 10,
      "target_department_id": 2,
      "target_shift_type_id": 1,
      "target_date": "2026-11-03"
    }
  }
  ```
  - **Response 200 OK:**
  ```json
  {
    "isError": false,
    "content": [
      {
        "type": "text",
        "text": "Assignment valid. Warning: Sarah Connor will float to ER (Rank 2 backup skill)."
      }
    ]
  }
  ```
