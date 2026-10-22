"""SQLAlchemy models for LocalRoster v2."""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, CheckConstraint, Text, Index
)
from sqlalchemy.orm import relationship
from src.db.session import Base

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    color_code = Column(String(7), nullable=False, default="#3B82F6")
    operating_regime = Column(String(16), nullable=False, default="24_7")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    primary_employees = relationship("Employee", back_populates="primary_department", foreign_keys="Employee.primary_department_id")
    requirements = relationship("DepartmentRequirement", back_populates="department", cascade="all, delete-orphan")
    eligibilities = relationship("EmployeeDepartmentEligibility", back_populates="department", cascade="all, delete-orphan")
    assignments = relationship("RosterAssignment", back_populates="department")
    deficits = relationship("DeficitLog", back_populates="department", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("operating_regime IN ('24_7', 'WEEKDAYS_ONLY', 'CUSTOM')", name="ck_dept_regime"),
    )


class ShiftType(Base):
    __tablename__ = "shift_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False, index=True)
    name = Column(String(64), nullable=False)
    start_time = Column(String(8), nullable=False)  # 'HH:MM:SS'
    end_time = Column(String(8), nullable=False)    # 'HH:MM:SS'
    duration_hours = Column(Float, nullable=False)
    min_rest_hours_after = Column(Integer, nullable=False, default=14)
    is_night_shift = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    requirements = relationship("DepartmentRequirement", back_populates="shift_type", cascade="all, delete-orphan")
    preferences = relationship("EmployeeShiftPreference", back_populates="shift_type", cascade="all, delete-orphan")
    assignments = relationship("RosterAssignment", back_populates="shift_type")
    deficits = relationship("DeficitLog", back_populates="shift_type", cascade="all, delete-orphan")


class DepartmentRequirement(Base):
    __tablename__ = "department_requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    shift_type_id = Column(Integer, ForeignKey("shift_types.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday, 6 = Sunday
    min_staff = Column(Integer, nullable=False, default=1)
    optimal_staff = Column(Integer, nullable=False, default=1)

    department = relationship("Department", back_populates="requirements")
    shift_type = relationship("ShiftType", back_populates="requirements")

    __table_args__ = (
        UniqueConstraint("department_id", "shift_type_id", "day_of_week", name="uq_dept_shift_dow"),
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_req_dow"),
        CheckConstraint("min_staff >= 0", name="ck_req_min_staff"),
        CheckConstraint("optimal_staff >= min_staff", name="ck_req_optimal_staff"),
        Index("idx_dept_req_lookup", "department_id", "day_of_week"),
    )


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    email = Column(String(128), nullable=True)
    primary_department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    max_hours_week = Column(Float, nullable=False, default=40.0)
    fixed_off_days = Column(String(64), nullable=True, default=None)  # Comma-separated day indices (0=Mon..6=Sun)
    preferred_shift_type_id = Column(Integer, ForeignKey("shift_types.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    primary_department = relationship("Department", back_populates="primary_employees", foreign_keys=[primary_department_id])
    preferred_shift_type = relationship("ShiftType", foreign_keys=[preferred_shift_type_id])
    eligibilities = relationship("EmployeeDepartmentEligibility", back_populates="employee", cascade="all, delete-orphan")
    preferences = relationship("EmployeeShiftPreference", back_populates="employee", cascade="all, delete-orphan")
    leaves = relationship("LeaveRecord", back_populates="employee", cascade="all, delete-orphan")
    assignments = relationship("RosterAssignment", back_populates="employee", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("max_hours_week > 0", name="ck_emp_max_hours"),
        Index("idx_employees_active_dept", "is_active", "primary_department_id"),
    )


class EmployeeDepartmentEligibility(Base):
    __tablename__ = "employee_department_eligibility"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    preference_rank = Column(Integer, nullable=False, default=2)  # 1=Home, 2=Backup, 3=Emergency
    can_float = Column(Boolean, nullable=False, default=True)

    employee = relationship("Employee", back_populates="eligibilities")
    department = relationship("Department", back_populates="eligibilities")

    __table_args__ = (
        UniqueConstraint("employee_id", "department_id", name="uq_emp_dept"),
        CheckConstraint("preference_rank IN (1, 2, 3)", name="ck_elig_rank"),
        Index("idx_emp_dept_elig", "employee_id", "department_id"),
    )


class EmployeeShiftPreference(Base):
    __tablename__ = "employee_shift_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    shift_type_id = Column(Integer, ForeignKey("shift_types.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = Monday, 6 = Sunday
    preference_score = Column(Integer, nullable=False, default=0)  # -5 to +5

    employee = relationship("Employee", back_populates="preferences")
    shift_type = relationship("ShiftType", back_populates="preferences")

    __table_args__ = (
        UniqueConstraint("employee_id", "shift_type_id", "day_of_week", name="uq_emp_shift_dow"),
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_pref_dow"),
        CheckConstraint("preference_score BETWEEN -5 AND 5", name="ck_pref_score"),
        Index("idx_emp_pref", "employee_id"),
    )


class LeaveRecord(Base):
    __tablename__ = "leave_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    leave_type = Column(String(32), nullable=False, default="VACATION")
    status = Column(String(16), nullable=False, default="APPROVED")
    notes = Column(Text, nullable=True)

    employee = relationship("Employee", back_populates="leaves")

    __table_args__ = (
        CheckConstraint("leave_type IN ('VACATION', 'SICK', 'TRAINING', 'UNPAID', 'OTHER', 'DAY_OFF', 'COFF')", name="ck_leave_type"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'CANCELLED')", name="ck_leave_status"),
        CheckConstraint("end_date >= start_date", name="ck_leave_dates"),
        Index("idx_leave_dates", "employee_id", "start_date", "end_date"),
    )


class RosterPlan(Base):
    __tablename__ = "roster_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_plan_id = Column(Integer, ForeignKey("roster_plans.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String(64), nullable=False, index=True)
    variant_name = Column(String(64), nullable=False, default="Variant A")
    variant_strategy = Column(String(64), nullable=False, default="BALANCED")
    is_active_variant = Column(Boolean, nullable=False, default=True)
    name = Column(String(128), nullable=False)
    department_ids = Column(String(256), nullable=True)  # Comma-separated department IDs (e.g. '1,2'), or None for All Depts
    planning_year = Column(Integer, nullable=True)
    planning_month = Column(Integer, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")  # DRAFT, GENERATING, SOLVED, PUBLISHED, ARCHIVED
    solver_status = Column(String(32), nullable=True)
    solve_time_seconds = Column(Float, nullable=True)
    total_deficits = Column(Integer, nullable=False, default=0)
    total_floats = Column(Integer, nullable=False, default=0)
    objective_score = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    assignments = relationship("RosterAssignment", back_populates="plan", cascade="all, delete-orphan")
    deficits = relationship("DeficitLog", back_populates="plan", cascade="all, delete-orphan")
    child_variants = relationship("RosterPlan", backref="parent_plan", remote_side=[id])

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'GENERATING', 'SOLVED', 'PUBLISHED', 'ARCHIVED')", name="ck_plan_status"),
        CheckConstraint("end_date >= start_date", name="ck_plan_dates"),
        Index("idx_roster_plans_session", "session_id"),
        Index("idx_roster_plans_lookup", "planning_year", "planning_month", "is_active_variant"),
        Index("idx_roster_plans_dates", "start_date", "end_date"),
    )


class RosterAssignment(Base):
    __tablename__ = "roster_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("roster_plans.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False)
    shift_type_id = Column(Integer, ForeignKey("shift_types.id", ondelete="RESTRICT"), nullable=False)
    date = Column(Date, nullable=False)
    assignment_source = Column(String(16), nullable=False, default="SOLVER")  # SOLVER, PREFILLED, MANUAL_OVERRIDE
    is_pinned = Column(Boolean, nullable=False, default=False)
    is_manual_override = Column(Boolean, nullable=False, default=False)
    is_floating = Column(Boolean, nullable=False, default=False)
    float_rank = Column(Integer, nullable=True, default=1)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    plan = relationship("RosterPlan", back_populates="assignments")
    employee = relationship("Employee", back_populates="assignments")
    department = relationship("Department", back_populates="assignments")
    shift_type = relationship("ShiftType", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("plan_id", "employee_id", "date", name="uq_plan_emp_date"),
        CheckConstraint("assignment_source IN ('SOLVER', 'PREFILLED', 'MANUAL_OVERRIDE')", name="ck_assign_source"),
        Index("idx_assignment_plan_date", "plan_id", "date"),
        Index("idx_assignment_dept_date", "department_id", "date"),
        Index("idx_assignment_emp_date", "employee_id", "date"),
        Index("idx_assignment_pinned", "plan_id", "is_pinned"),
    )


class DeficitLog(Base):
    __tablename__ = "deficit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("roster_plans.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    shift_type_id = Column(Integer, ForeignKey("shift_types.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    shortage_count = Column(Integer, nullable=False)
    reason_code = Column(String(64), nullable=False)

    plan = relationship("RosterPlan", back_populates="deficits")
    department = relationship("Department", back_populates="deficits")
    shift_type = relationship("ShiftType", back_populates="deficits")

    __table_args__ = (
        CheckConstraint("shortage_count > 0", name="ck_shortage_positive"),
        Index("idx_deficit_plan", "plan_id", "department_id", "date"),
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

