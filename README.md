# LocalRoster v2: Dynamic Offline Workforce Roster Planner

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Optimization: Google OR-Tools CP-SAT](https://img.shields.io/badge/Optimization-OR--Tools%20CP--SAT-green.svg)](https://developers.google.com/optimization)
[![Architecture: Standalone Offline](https://img.shields.io/badge/Architecture-100%25%20Offline-success.svg)](#)
[![Test Coverage: 15/15 Passed](https://img.shields.io/badge/Tests-15%2F15%20Passing-brightgreen.svg)](#)

**LocalRoster v2** is a production-grade, mathematically optimal, 100% offline workforce roster scheduling and management system. Built specifically for high-stakes operational environments (such as hospitals, clinics, emergency services, and 24/7 facilities), it pairs Google OR-Tools CP-SAT constraint programming with an Excel-inspired desktop interface that runs entirely on local machines without cloud dependencies or CDN calls.

---

## 🌟 Key Capabilities & Features

### 1. Mathematical Optimization Engine (Google OR-Tools CP-SAT)
* **Zero Unhandled Infeasibility:** Uses integer deficit slack variables to guarantee that an optimal, executable schedule is always produced, even under severe workforce starvation.
* **Ergonomic Safety Invariants:** Strict enforcement of maximum consecutive working days (e.g., 5-day limit), mandatory minimum rest intervals (16 hours post-night shifts), forbidden backward rotations (Night $\to$ Morning is strictly blocked), and rolling 7-day rest guarantees.
* **Cross-Ward Floater Allocation:** Employees can float across multiple departments based on preference ranks and eligibility matrices.
* **Multi-Variant Generation & Comparison:** Solves multiple candidate schedules with varying objective weights (Standard Balanced, Float-Averse, Maximum Preference) for side-by-side manager comparison and 1-click promotion.
* **Pre-Filling & "Solve Remaining":** Managers can pre-lock specific shift assignments or days off (e.g. employee vacation requests), and the solver will dynamically optimize all remaining blank slots around them.

### 2. Excel-Style Desktop Interface & Workflow
* **Excel-Style Ribbon Navigation:** Organized into clear operational tabs:
  - **`📋 Schedule & Solve`:** Roster generation, solve remaining slots, prefill toggles, variant comparisons, and view switches.
  - **`🏢 Organization & Staff`:** In-app department operating regime setup (24/7 vs. Weekdays-only), staff contracts, and CSV/Excel bulk import.
  - **`📊 Reports & Exports`:** One-click downloads of formatted multi-tab Excel workbooks (`.xlsx`) and printable landscape vector PDFs.
  - **`👁️ View Options`:** Sidebar toggles and splitter pane reset controls.
* **Excel-Style Bottom Status Bar:**
  - Real-time health badge (`🟢 100% Staffed`), active plan telemetry, and department/staff counts.
  - Quick view mode shortcuts (Staff-Centric, Slot-Centric, Workload Audit Scorecard).
  - Dynamic **Zoom Engine**: continuous slider (65% to 160%), step buttons `[−]` / `[+]`, and one-click `[100%]` reset.
* **Dual Roster Views:**
  - **Staff-Centric View:** Employees as rows, calendar dates as columns, sticky headers, and department color badges.
  - **Slot-Centric View:** Coverage requirements per ward and shift slot with assigned worker badges and deficit indicators.
  - **Workload Audit Scorecard:** Automatic tracking of total scheduled hours, overtime variance, night shift distribution, and weekend rest equity.
* **Resizable Splitters & Responsive Panes:** Left department filters, central matrix grid, and right-hand shift inspector can be fluidly resized via drag handles.
* **Month-to-Month Carryover:** Full context awareness of trailing shifts from the preceding month, highlighting prior night shifts on Day 1 to avoid turnaround fatigue.
* **First-Time Manager Onboarding Wizard:** Modal on initial launch offering instant choice between CSV template import or pre-loaded hospital template.

### 3. Standards, Formats & Integration
* **Model Context Protocol (MCP) Server:** Native endpoints allowing local and online AI agents to audit rosters, run queries, and schedule shifts with real-time constraint validation.
* **Spreadsheet Ingestion & Export:** Standard CSV/Excel templates for employees, departments, and shift demands, with row-level validation before commit.
* **Zero Cloud Dependencies:** 100% offline, self-contained assets (HTML5, compiled CSS, inline SVG, SQLite WAL database).

---

## 🏗️ Project Architecture

```
Roster_planner/
├── docs/                                  # Complete Technical Specifications
│   ├── API_SPEC.md                        # REST API contracts & MCP endpoints
│   ├── AUDIT_AND_PERFORMANCE_REPORT.md    # Performance benchmarks, crawler audit, and resolved bugs
│   ├── DATABASE_SCHEMA.md                 # SQLite relational schema & indexes
│   ├── MATHEMATICAL_MODEL.md              # CP-SAT constraint formulation & proofs
│   ├── PRD.md                             # Product requirements & business rules
│   ├── TESTING_AND_EDGE_CASES.md          # Edge-case matrix & verification plans
│   └── UI_UX_SPEC.md                      # UI/UX design, ribbon layout, and ergonomics
├── src/
│   ├── api/                               # FastAPI Web Server & Routing
│   │   ├── main.py                        # App factory & static asset mounting
│   │   ├── routes_analytics.py            # Workload audits & scorecard endpoints
│   │   ├── routes_departments.py          # Department CRUD & live color customization
│   │   ├── routes_employees.py            # Staff CRUD & floating preference ranks
│   │   ├── routes_export.py               # Formatted openpyxl Excel & ReportLab PDF generators
│   │   ├── routes_import.py               # CSV/Excel parsing & row validation
│   │   ├── routes_mcp.py                  # Model Context Protocol (MCP) agent tools
│   │   └── routes_roster.py               # CP-SAT solver invocation, prefill, pin/clear
│   ├── db/                                # SQLite Relational Engine
│   │   ├── models.py                      # SQLAlchemy ORM declarative models
│   │   ├── seed.py                        # Default hospital ward & staff topology seeder
│   │   └── session.py                     # SQLite engine with WAL mode & foreign keys
│   ├── desktop/                           # Standalone Launcher
│   │   └── run.py                         # Desktop runner (spawns server & opens default browser)
│   ├── services/                          # Core Domain & Optimization Services
│   │   ├── import_service.py              # File ingestion & schema validation
│   │   ├── mcp_service.py                 # AI agent tool execution registry
│   │   ├── roster_service.py              # Orchestration & drag-and-drop validation
│   │   └── rules_engine.py                # Ergonomic rule validation algorithms
│   ├── solver/                            # Google OR-Tools Mathematical Engine
│   │   └── cp_sat_solver.py               # CP-SAT formulation, deficit slacks & objectives
│   └── ui/                                # Offline Single-Page Frontend
│       ├── app.js                         # Reactive UI logic, ribbon tabs, zoom, & API bindings
│       ├── index.html                     # Excel Ribbon layout, modals, splitters, & status bar
│       └── styles.css                     # Responsive styles, zoom scaling, & color badges
└── tests/                                 # 100% Automated Test Suite (pytest)
    ├── api/                               # REST API & MCP integration tests
    ├── solver/                            # CP-SAT shortage, floating & rest invariant tests
    ├── ui/                                # Automated UI button crawler audit tests
    └── unit/                              # Ergonomic rule & import validation tests
```

---

## 🚀 Quick Start Guide

### Prerequisites
* Windows 10/11 (or Linux / macOS)
* Python **3.12.x** installed

### 1. Launch the Desktop Application
Open PowerShell and run the desktop launcher:

```powershell
cd C:\Users\HEllo\Roster_planner
py -3.12 src/desktop/run.py
```

The launcher will verify the database, start the local server on `http://127.0.0.1:8000`, and immediately open your default web browser.

---

## 🧪 Running Automated Tests

To run the complete automated test suite (including mathematical solver proofs, API lifecycles, and the UI button crawler audit):

```powershell
py -3.12 -m pytest -v
```

### Current Test Suite Verification (15/15 Passed):
* `test_full_roster_generation_and_export_lifecycle`: Verifies multi-variant generation, promotion, and Excel/PDF download.
* `test_department_crud_and_color_customization`: Verifies runtime department creation, hex color customization, and cascade protection.
* `test_employee_crud_lifecycle`: Verifies staff creation, floating preference updates, and soft deletion.
* `test_previous_month_carryover_and_trailing_shifts`: Verifies 3-day history carryover, trailing hours, and Day 1 turnaround warnings.
* `test_mcp_tools_and_execution`: Verifies Model Context Protocol tools for AI agent integrations.
* `test_vacation_absorption_via_floating`: Verifies that 100% staff leave in one department is automatically absorbed by eligible floaters from another department.
* `test_ergonomic_rest_and_rotation_invariants`: Verifies zero forbidden rotations (Night $\to$ Morning) and rolling 7-day rest compliance.
* `test_extreme_workforce_starvation`: Verifies CP-SAT slack deficit formulation under severe workforce shortages (zero solver crashes).
* `test_audit_all_buttons_bound_in_app_js`: Crawler audit verifying that every `<button>` in the HTML is bound to an active handler.
* `test_crawler_executes_all_button_backend_endpoints`: End-to-end execution of all UI button API actions.
* `test_template_generation`: Verifies downloadable CSV templates for staff, departments, and demands.
* `test_csv_validation_duplicate_code`: Verifies row-level CSV schema validation.
* `test_forbidden_transition_night_to_morning`: Verifies immediate rejection of hazardous shift turnaround.
* `test_permitted_transition_morning_to_night`: Verifies approval of valid forward shift rotation.
* `test_consecutive_days_violation`: Verifies enforcement of consecutive working day thresholds.

---

## 📋 Technical Documentation Index
* [API Specification (`docs/API_SPEC.md`)](docs/API_SPEC.md)
* [Mathematical Model & CP-SAT Formulation (`docs/MATHEMATICAL_MODEL.md`)](docs/MATHEMATICAL_MODEL.md)
* [Database Schema (`docs/DATABASE_SCHEMA.md`)](docs/DATABASE_SCHEMA.md)
* [UI/UX Specification (`docs/UI_UX_SPEC.md`)](docs/UI_UX_SPEC.md)
* [Testing & Edge Cases Matrix (`docs/TESTING_AND_EDGE_CASES.md`)](docs/TESTING_AND_EDGE_CASES.md)
* [Audit, Bug Findings & Performance Report (`docs/AUDIT_AND_PERFORMANCE_REPORT.md`)](docs/AUDIT_AND_PERFORMANCE_REPORT.md)
