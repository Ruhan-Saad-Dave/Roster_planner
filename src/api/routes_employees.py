"""Employee management, eligibility, shift affinities, and leave routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from src.db.session import get_db
from src.db.models import (
    Employee, Department, EmployeeDepartmentEligibility,
    EmployeeShiftPreference, LeaveRecord
)
from src.api.schemas import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    UpdateEligibilityRequest, UpdateShiftPreferencesRequest,
    LeaveRecordCreate, LeaveRecordResponse
)

router = APIRouter(prefix="/api", tags=["Employees & Leaves"])

@router.get("/employees", response_model=List[EmployeeResponse])
def list_employees(
    department_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.is_active == True)
    if department_id:
        q = q.filter(Employee.primary_department_id == department_id)
    emps = q.all()
    res = []
    for e in emps:
        resp = EmployeeResponse.model_validate(e)
        resp.primary_department_name = e.primary_department.name if e.primary_department else None
        res.append(resp)
    return res

@router.post("/employees", response_model=EmployeeResponse, status_code=201)
def create_employee(emp_in: EmployeeCreate, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == emp_in.primary_department_id).first()
    if not dept:
        raise HTTPException(status_code=400, detail="Primary department does not exist.")
    existing = db.query(Employee).filter(Employee.employee_code == emp_in.employee_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Employee code already exists.")

    emp = Employee(**emp_in.model_dump())
    db.add(emp)
    db.flush()

    # Automatically add primary eligibility (Rank 1)
    db.add(EmployeeDepartmentEligibility(
        employee_id=emp.id,
        department_id=dept.id,
        preference_rank=1,
        can_float=False
    ))
    db.commit()
    db.refresh(emp)

    resp = EmployeeResponse.model_validate(emp)
    resp.primary_department_name = dept.name
    return resp

@router.put("/employees/{emp_id}", response_model=EmployeeResponse)
def update_employee(emp_id: int, emp_in: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if emp_in.employee_code and emp_in.employee_code != emp.employee_code:
        existing = db.query(Employee).filter(Employee.employee_code == emp_in.employee_code, Employee.id != emp_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee code already taken.")
        emp.employee_code = emp_in.employee_code

    if emp_in.primary_department_id is not None and emp_in.primary_department_id != emp.primary_department_id:
        new_dept = db.query(Department).filter(Department.id == emp_in.primary_department_id).first()
        if not new_dept:
            raise HTTPException(status_code=400, detail="Target primary department does not exist.")
        emp.primary_department_id = emp_in.primary_department_id

        # Update primary eligibility
        home_elig = db.query(EmployeeDepartmentEligibility).filter(
            EmployeeDepartmentEligibility.employee_id == emp.id,
            EmployeeDepartmentEligibility.preference_rank == 1
        ).first()
        if home_elig:
            home_elig.department_id = new_dept.id
        else:
            db.add(EmployeeDepartmentEligibility(employee_id=emp.id, department_id=new_dept.id, preference_rank=1, can_float=False))

    if emp_in.name is not None:
        emp.name = emp_in.name
    if emp_in.email is not None:
        emp.email = emp_in.email
    if emp_in.max_hours_week is not None:
        emp.max_hours_week = emp_in.max_hours_week
    if emp_in.fixed_off_days is not None:
        emp.fixed_off_days = emp_in.fixed_off_days
    if emp_in.is_active is not None:
        emp.is_active = emp_in.is_active

    db.commit()
    db.refresh(emp)
    resp = EmployeeResponse.model_validate(emp)
    resp.primary_department_name = emp.primary_department.name if emp.primary_department else None
    return resp

@router.delete("/employees/{emp_id}")
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found.")

    emp_name = emp.name
    db.delete(emp)
    db.commit()
    return {"message": f"Employee '{emp_name}' deleted successfully."}

@router.get("/employees/{emp_id}/eligibility")
def get_employee_eligibility(emp_id: int, db: Session = Depends(get_db)):
    eligs = db.query(EmployeeDepartmentEligibility).filter(EmployeeDepartmentEligibility.employee_id == emp_id).all()
    return [
        {
            "id": el.id,
            "department_id": el.department_id,
            "department_name": el.department.name,
            "preference_rank": el.preference_rank,
            "can_float": el.can_float
        }
        for el in eligs
    ]

@router.put("/employees/{emp_id}/eligibility")
def update_employee_eligibility(emp_id: int, req_in: UpdateEligibilityRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found.")

    db.query(EmployeeDepartmentEligibility).filter(EmployeeDepartmentEligibility.employee_id == emp_id).delete()
    for el in req_in.eligibilities:
        db.add(EmployeeDepartmentEligibility(
            employee_id=emp_id,
            department_id=el.department_id,
            preference_rank=el.preference_rank,
            can_float=el.can_float
        ))
    db.commit()
    return {"message": "Eligibilities updated successfully."}

@router.get("/employees/{emp_id}/preferences")
def get_employee_preferences(emp_id: int, db: Session = Depends(get_db)):
    prefs = db.query(EmployeeShiftPreference).filter(EmployeeShiftPreference.employee_id == emp_id).all()
    return [
        {
            "id": p.id,
            "shift_type_id": p.shift_type_id,
            "day_of_week": p.day_of_week,
            "preference_score": p.preference_score
        }
        for p in prefs
    ]

@router.put("/employees/{emp_id}/preferences")
def update_employee_preferences(emp_id: int, req_in: UpdateShiftPreferencesRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found.")

    db.query(EmployeeShiftPreference).filter(EmployeeShiftPreference.employee_id == emp_id).delete()
    for p in req_in.preferences:
        db.add(EmployeeShiftPreference(
            employee_id=emp_id,
            shift_type_id=p.shift_type_id,
            day_of_week=p.day_of_week,
            preference_score=p.preference_score
        ))
    db.commit()
    return {"message": "Preferences updated successfully."}

@router.get("/leaves", response_model=List[LeaveRecordResponse])
def list_leaves(
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    q = db.query(LeaveRecord)
    if employee_id:
        q = q.filter(LeaveRecord.employee_id == employee_id)
    return q.all()

@router.post("/leaves", response_model=LeaveRecordResponse, status_code=201)
def create_leave(leave_in: LeaveRecordCreate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == leave_in.employee_id).first()
    if not emp:
        raise HTTPException(status_code=400, detail="Employee not found.")
    if leave_in.end_date < leave_in.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date.")

    leave = LeaveRecord(**leave_in.model_dump())
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave

@router.delete("/leaves/{leave_id}")
def delete_leave(leave_id: int, db: Session = Depends(get_db)):
    leave = db.query(LeaveRecord).filter(LeaveRecord.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found.")
    db.delete(leave)
    db.commit()
    return {"message": "Leave record deleted successfully."}
