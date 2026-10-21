"""Pydantic request and response schemas for LocalRoster v2 REST API."""
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Departments
class DepartmentCreate(BaseModel):
    code: str
    name: str
    color_code: Optional[str] = "#3B82F6"
    operating_regime: Optional[str] = "24_7"

class DepartmentUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    color_code: Optional[str] = None
    operating_regime: Optional[str] = None
    is_active: Optional[bool] = None

class DepartmentResponse(BaseModel):
    id: int
    code: str
    name: str
    color_code: str
    operating_regime: str
    is_active: bool
    employee_count: Optional[int] = 0

    model_config = {"from_attributes": True}

# Shift Types
class ShiftTypeCreate(BaseModel):
    code: str
    name: str
    start_time: str
    end_time: str
    duration_hours: float
    min_rest_hours_after: Optional[int] = 14
    is_night_shift: Optional[bool] = False

class ShiftTypeUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_hours: Optional[float] = None
    min_rest_hours_after: Optional[int] = None
    is_night_shift: Optional[bool] = None
    is_active: Optional[bool] = None

class ShiftTypeResponse(BaseModel):
    id: int
    code: str
    name: str
    start_time: str
    end_time: str
    duration_hours: float
    min_rest_hours_after: int
    is_night_shift: bool
    is_active: bool

    model_config = {"from_attributes": True}

# Demand Requirements
class RequirementItem(BaseModel):
    shift_type_id: int
    day_of_week: int
    min_staff: int
    optimal_staff: int

class UpdateRequirementsRequest(BaseModel):
    requirements: List[RequirementItem]

# Employees
class EmployeeCreate(BaseModel):
    employee_code: str
    name: str
    email: Optional[str] = None
    primary_department_id: int
    max_hours_week: Optional[float] = 40.0
    fixed_off_days: Optional[str] = None
    preferred_shift_type_id: Optional[int] = None
    secondary_department_ids: Optional[List[int]] = None

class EmployeeUpdate(BaseModel):
    employee_code: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    primary_department_id: Optional[int] = None
    max_hours_week: Optional[float] = None
    fixed_off_days: Optional[str] = None
    preferred_shift_type_id: Optional[int] = None
    secondary_department_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    name: str
    email: Optional[str] = None
    primary_department_id: int
    primary_department_name: Optional[str] = None
    max_hours_week: float
    fixed_off_days: Optional[str] = None
    preferred_shift_type_id: Optional[int] = None
    preferred_shift_code: Optional[str] = None
    preferred_shift_name: Optional[str] = None
    secondary_department_ids: Optional[List[int]] = None
    secondary_departments: Optional[List[Dict[str, Any]]] = None
    is_active: bool

    model_config = {"from_attributes": True}

# Eligibility & Preferences
class EligibilityItem(BaseModel):
    department_id: int
    preference_rank: int = 2
    can_float: bool = True

class UpdateEligibilityRequest(BaseModel):
    eligibilities: List[EligibilityItem]

class ShiftPreferenceItem(BaseModel):
    shift_type_id: int
    day_of_week: int
    preference_score: int

class UpdateShiftPreferencesRequest(BaseModel):
    preferences: List[ShiftPreferenceItem]

# Leaves
class LeaveRecordCreate(BaseModel):
    employee_id: int
    start_date: date
    end_date: date
    leave_type: Optional[str] = "VACATION"
    notes: Optional[str] = None

class LeaveRecordResponse(BaseModel):
    id: int
    employee_id: int
    start_date: date
    end_date: date
    leave_type: str
    status: str
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

# Solver & Plans
class GenerateRosterRequest(BaseModel):
    name: str = "Workforce Roster Plan"
    planning_year: Optional[int] = None
    planning_month: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    variant_count: int = 1
    variant_strategies: Optional[List[str]] = None
    timeout_seconds: int = 15
    max_consecutive_days: int = 5
    min_rest_days_per_week: int = 2
    weights: Optional[Dict[str, int]] = None

class ValidateAssignmentRequest(BaseModel):
    plan_id: int
    employee_id: int
    target_department_id: int
    target_shift_type_id: int
    target_date: date

class ManualAssignmentRequest(BaseModel):
    employee_id: int
    department_id: int
    shift_type_id: int
    date: date
    force_override: bool = False
    is_pinned: bool = True

class PrefillShiftsRequest(BaseModel):
    assignments: List[Dict[str, Any]]

class FindReplaceRequest(BaseModel):
    find_shift_code: str
    replace_shift_code: str
    department_id: Optional[int] = None

class SystemSettingsUpdate(BaseModel):
    settings: Dict[str, str]

# Bulk Employee Operations
class BulkDeleteEmployeesRequest(BaseModel):
    employee_ids: List[int]

class BulkUpdateEmployeesRequest(BaseModel):
    employee_ids: List[int]
    primary_department_id: Optional[int] = None
    max_hours_week: Optional[float] = None
    fixed_off_days: Optional[str] = None
    preferred_shift_type_id: Optional[int] = None
    secondary_department_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

class PinOffRequest(BaseModel):
    employee_id: int
    date: date
    off_type: str = "DAY_OFF"  # "DAY_OFF", "DO", "COFF", "COMP_OFF"
    notes: Optional[str] = None

