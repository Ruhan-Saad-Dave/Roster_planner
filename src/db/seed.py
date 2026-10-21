"""Seed data generators for testing dynamic organizational topologies."""
from datetime import date, timedelta
import json
from sqlalchemy import text
from src.db.session import engine, SessionLocal, Base
from src.db.models import (
    Department, ShiftType, DepartmentRequirement,
    Employee, EmployeeDepartmentEligibility, EmployeeShiftPreference,
    LeaveRecord, RosterPlan, RosterAssignment, DeficitLog, SystemSetting
)

def init_db():
    """Create all tables in the SQLite database and run backward-compatible schema patches."""
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            cursor = conn.execute(text("PRAGMA table_info(employees)"))
            cols = [row[1] for row in cursor.fetchall()]
            if "fixed_off_days" not in cols:
                conn.execute(text("ALTER TABLE employees ADD COLUMN fixed_off_days VARCHAR(64) DEFAULT NULL"))
                conn.commit()
            if "preferred_shift_type_id" not in cols:
                conn.execute(text("ALTER TABLE employees ADD COLUMN preferred_shift_type_id INTEGER REFERENCES shift_types(id) DEFAULT NULL"))
                conn.commit()
    except Exception as e:
        print(f"Schema check error: {e}")

def seed_standard_hospital(db=None):
    """Seed a realistic multi-department 24x7 hospital scenario with 3 shifts,

    4 departments, and 30 employees with cross-department floating eligibility.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Check if already seeded
        if db.query(Department).count() > 0:
            return

        # 1. Shift Types
        morn = ShiftType(
            code="MORN",
            name="Morning Shift",
            start_time="07:00:00",
            end_time="15:30:00",
            duration_hours=8.5,
            min_rest_hours_after=14,
            is_night_shift=False
        )
        eve = ShiftType(
            code="EVE",
            name="Evening Shift",
            start_time="15:00:00",
            end_time="23:30:00",
            duration_hours=8.5,
            min_rest_hours_after=14,
            is_night_shift=False
        )
        night = ShiftType(
            code="NIGHT",
            name="Night Shift",
            start_time="23:00:00",
            end_time="07:30:00",
            duration_hours=8.5,
            min_rest_hours_after=15,
            is_night_shift=True
        )
        db.add_all([morn, eve, night])
        db.flush()

        shifts = [morn, eve, night]

        # 2. Departments
        icu = Department(code="ICU", name="Intensive Care Unit", color_code="#EF4444", operating_regime="24_7")
        er = Department(code="ER", name="Emergency Room", color_code="#F59E0B", operating_regime="24_7")
        surg = Department(code="SURG", name="Surgical Ward", color_code="#10B981", operating_regime="24_7")
        outpatient = Department(code="OUTPATIENT", name="Outpatient Clinic", color_code="#6366F1", operating_regime="WEEKDAYS_ONLY")
        db.add_all([icu, er, surg, outpatient])
        db.flush()

        depts = [icu, er, surg, outpatient]

        # 3. Department Requirements (Demand Matrix)
        for dept in [icu, er, surg]:
            for dow in range(7):  # Mon through Sun
                # Morning: 2 min, 3 optimal
                db.add(DepartmentRequirement(department_id=dept.id, shift_type_id=morn.id, day_of_week=dow, min_staff=2, optimal_staff=3))
                # Evening: 2 min, 2 optimal
                db.add(DepartmentRequirement(department_id=dept.id, shift_type_id=eve.id, day_of_week=dow, min_staff=2, optimal_staff=2))
                # Night: 1 min, 2 optimal
                db.add(DepartmentRequirement(department_id=dept.id, shift_type_id=night.id, day_of_week=dow, min_staff=1, optimal_staff=2))

        # Outpatient Clinic: Weekdays only, morning and evening, 0 on weekends and night
        for dow in range(5):  # Mon-Fri
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=morn.id, day_of_week=dow, min_staff=2, optimal_staff=2))
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=eve.id, day_of_week=dow, min_staff=1, optimal_staff=1))
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=night.id, day_of_week=dow, min_staff=0, optimal_staff=0))
        for dow in [5, 6]:  # Sat-Sun (Closed)
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=morn.id, day_of_week=dow, min_staff=0, optimal_staff=0))
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=eve.id, day_of_week=dow, min_staff=0, optimal_staff=0))
            db.add(DepartmentRequirement(department_id=outpatient.id, shift_type_id=night.id, day_of_week=dow, min_staff=0, optimal_staff=0))
        db.flush()

        # 4. Employees & Multi-Skilling
        # Create 32 employees (8 primary in ICU, 8 in ER, 8 in SURG, 8 in OUTPATIENT)
        staff_names = [
            # ICU Staff
            ("EMP001", "Sarah Connor", icu.id),
            ("EMP002", "John Doe", icu.id),
            ("EMP003", "Elena Rostova", icu.id),
            ("EMP004", "David Kim", icu.id),
            ("EMP005", "Michael Chang", icu.id),
            ("EMP006", "Rachel Green", icu.id),
            ("EMP007", "James Wilson", icu.id),
            ("EMP008", "Lisa Cuddy", icu.id),
            # ER Staff
            ("EMP009", "Marcus Vance", er.id),
            ("EMP010", "Alex Thorne", er.id),
            ("EMP011", "Maya Lin", er.id),
            ("EMP012", "Chris Evans", er.id),
            ("EMP013", "Natasha Romanoff", er.id),
            ("EMP014", "Bruce Banner", er.id),
            ("EMP015", "Tony Stark", er.id),
            ("EMP016", "Steve Rogers", er.id),
            # Surgical Staff
            ("EMP017", "Stephen Strange", surg.id),
            ("EMP018", "Christine Palmer", surg.id),
            ("EMP019", "Wanda Maximoff", surg.id),
            ("EMP020", "Vision Synthezoid", surg.id),
            ("EMP021", "Sam Wilson", surg.id),
            ("EMP022", "Bucky Barnes", surg.id),
            ("EMP023", "Clint Barton", surg.id),
            ("EMP024", "Peter Parker", surg.id),
            # Outpatient Staff
            ("EMP025", "Jean Grey", outpatient.id),
            ("EMP026", "Scott Summers", outpatient.id),
            ("EMP027", "Charles Xavier", outpatient.id),
            ("EMP028", "Hank McCoy", outpatient.id),
            ("EMP029", "Ororo Munroe", outpatient.id),
            ("EMP030", "Logan Howlett", outpatient.id),
            ("EMP031", "Kurt Wagner", outpatient.id),
            ("EMP032", "Anna Marie", outpatient.id),
        ]

        created_employees = []
        for code, name, dept_id in staff_names:
            emp = Employee(
                employee_code=code,
                name=name,
                email=f"{code.lower()}@localroster.internal",
                primary_department_id=dept_id,
                max_hours_week=40.0,
                is_active=True
            )
            db.add(emp)
            db.flush()
            created_employees.append(emp)

            # Primary eligibility (Rank 1)
            db.add(EmployeeDepartmentEligibility(
                employee_id=emp.id,
                department_id=dept_id,
                preference_rank=1,
                can_float=False
            ))

            # Cross-department floating skills:
            # ICU nurses float to ER (Rank 2)
            if dept_id == icu.id:
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=er.id, preference_rank=2, can_float=True))
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=surg.id, preference_rank=3, can_float=True))
            # ER nurses float to ICU (Rank 2) and Outpatient (Rank 2)
            elif dept_id == er.id:
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=icu.id, preference_rank=2, can_float=True))
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=outpatient.id, preference_rank=2, can_float=True))
            # Surgical nurses float to ICU (Rank 2)
            elif dept_id == surg.id:
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=icu.id, preference_rank=2, can_float=True))
            # Outpatient staff float to ER as emergency floaters (Rank 3)
            elif dept_id == outpatient.id:
                db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=er.id, preference_rank=3, can_float=True))

            # Shift Preferences: sample affinities
            # e.g. First 2 in each dept prefer Mornings, avoid Nights
            if int(code[-2:]) % 3 == 0:
                db.add(EmployeeShiftPreference(employee_id=emp.id, shift_type_id=morn.id, day_of_week=0, preference_score=4))
                db.add(EmployeeShiftPreference(employee_id=emp.id, shift_type_id=night.id, day_of_week=4, preference_score=-5))
            elif int(code[-2:]) % 3 == 1:
                db.add(EmployeeShiftPreference(employee_id=emp.id, shift_type_id=night.id, day_of_week=5, preference_score=3))

        # 5. Add a couple sample approved leaves for Nov 2026
        # Sarah Connor on leave Nov 10-15
        db.add(LeaveRecord(
            employee_id=created_employees[0].id,
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 15),
            leave_type="VACATION",
            status="APPROVED",
            notes="Annual Leave"
        ))
        # John Doe on leave Nov 12-14
        db.add(LeaveRecord(
            employee_id=created_employees[1].id,
            start_date=date(2026, 11, 12),
            end_date=date(2026, 11, 14),
            leave_type="VACATION",
            status="APPROVED",
            notes="Family PTO"
        ))

        # 6. Default System Settings
        default_settings = [
            ("generator_default_mode", "blank"),
            ("remember_generator_mode", "false"),
            ("custom_status_codes", json.dumps({
                "OFF": "OFF",
                "COFF": "Coff",
                "VAC": "Vacation",
                "SICK": "Sick"
            }))
        ]
        for key, val in default_settings:
            existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not existing:
                db.add(SystemSetting(key=key, value=val))

        db.commit()
    finally:
        if close_db:
            db.close()
