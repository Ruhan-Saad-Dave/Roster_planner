"""Pytest configuration and shared fixtures for LocalRoster v2 test suite."""
import os
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.db.session import Base, get_db
from src.db.models import Department, ShiftType, Employee, EmployeeDepartmentEligibility, DepartmentRequirement
from src.api.main import app

# Use isolated in-memory test database with StaticPool to share connection across threads
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="function")
def test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def sample_scenario(test_db):
    """Seed a 2-department, 2-shift scenario with 6 employees for fast testing."""
    # Shifts
    morn = ShiftType(code="MORN", name="Morning", start_time="07:00:00", end_time="15:30:00", duration_hours=8.5, min_rest_hours_after=14, is_night_shift=False)
    night = ShiftType(code="NIGHT", name="Night", start_time="23:00:00", end_time="07:30:00", duration_hours=8.5, min_rest_hours_after=16, is_night_shift=True)
    test_db.add_all([morn, night])
    test_db.flush()

    # Departments
    icu = Department(code="ICU", name="ICU", operating_regime="24_7")
    er = Department(code="ER", name="ER", operating_regime="24_7")
    test_db.add_all([icu, er])
    test_db.flush()

    # Requirements: 1 morning, 1 night in ICU and ER
    for dow in range(7):
        test_db.add(DepartmentRequirement(department_id=icu.id, shift_type_id=morn.id, day_of_week=dow, min_staff=1, optimal_staff=1))
        test_db.add(DepartmentRequirement(department_id=icu.id, shift_type_id=night.id, day_of_week=dow, min_staff=1, optimal_staff=1))
        test_db.add(DepartmentRequirement(department_id=er.id, shift_type_id=morn.id, day_of_week=dow, min_staff=1, optimal_staff=1))
        test_db.add(DepartmentRequirement(department_id=er.id, shift_type_id=night.id, day_of_week=dow, min_staff=1, optimal_staff=1))

    # Employees: 3 in ICU, 3 in ER
    emps = []
    for i in range(1, 4):
        emp = Employee(employee_code=f"ICU_{i}", name=f"ICU Staff {i}", primary_department_id=icu.id, max_hours_week=40.0)
        test_db.add(emp)
        test_db.flush()
        emps.append(emp)
        test_db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=icu.id, preference_rank=1, can_float=False))
        # ICU_1 can float to ER (Rank 2)
        if i == 1:
            test_db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=er.id, preference_rank=2, can_float=True))

    for i in range(1, 4):
        emp = Employee(employee_code=f"ER_{i}", name=f"ER Staff {i}", primary_department_id=er.id, max_hours_week=40.0)
        test_db.add(emp)
        test_db.flush()
        emps.append(emp)
        test_db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=er.id, preference_rank=1, can_float=False))
        # ER_1 can float to ICU (Rank 2)
        if i == 1:
            test_db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=icu.id, preference_rank=2, can_float=True))

    test_db.commit()
    return {"shifts": [morn, night], "departments": [icu, er], "employees": emps}
