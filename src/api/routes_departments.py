"""Department and Shift configuration routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from src.db.session import get_db
from src.db.models import Department, ShiftType, DepartmentRequirement
from src.api.schemas import (
    DepartmentCreate, DepartmentUpdate, DepartmentResponse,
    ShiftTypeCreate, ShiftTypeUpdate, ShiftTypeResponse,
    UpdateRequirementsRequest
)

router = APIRouter(prefix="/api", tags=["Departments & Shifts"])

@router.get("/departments", response_model=List[DepartmentResponse])
def list_departments(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(Department)
    if active_only:
        q = q.filter(Department.is_active == True)
    depts = q.all()
    res = []
    for d in depts:
        resp = DepartmentResponse.model_validate(d)
        resp.employee_count = len(d.primary_employees)
        res.append(resp)
    return res

@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department(dept_in: DepartmentCreate, db: Session = Depends(get_db)):
    existing = db.query(Department).filter(Department.code == dept_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists.")
    dept = Department(**dept_in.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    resp = DepartmentResponse.model_validate(dept)
    resp.employee_count = 0
    return resp

@router.put("/departments/{dept_id}", response_model=DepartmentResponse)
def update_department(dept_id: int, dept_in: DepartmentUpdate, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    
    if dept_in.code and dept_in.code != dept.code:
        existing = db.query(Department).filter(Department.code == dept_in.code, Department.id != dept_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Department code already taken.")
        dept.code = dept_in.code
    
    if dept_in.name is not None:
        dept.name = dept_in.name
    if dept_in.color_code is not None:
        dept.color_code = dept_in.color_code
    if dept_in.operating_regime is not None:
        dept.operating_regime = dept_in.operating_regime
    if dept_in.is_active is not None:
        dept.is_active = dept_in.is_active

    db.commit()
    db.refresh(dept)
    resp = DepartmentResponse.model_validate(dept)
    resp.employee_count = len(dept.primary_employees)
    return resp

@router.delete("/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")
    
    # Check if any employees are primary in this department
    if len(dept.primary_employees) > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete department '{dept.name}' because {len(dept.primary_employees)} employee(s) are assigned to it as their primary department. Reassign them first.")
    
    db.delete(dept)
    db.commit()
    return {"message": f"Department '{dept.name}' deleted successfully."}

@router.get("/shift-types", response_model=List[ShiftTypeResponse])
def list_shift_types(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(ShiftType)
    if active_only:
        q = q.filter(ShiftType.is_active == True)
    return q.all()

@router.post("/shift-types", response_model=ShiftTypeResponse, status_code=201)
def create_shift_type(shift_in: ShiftTypeCreate, db: Session = Depends(get_db)):
    existing = db.query(ShiftType).filter(ShiftType.code == shift_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Shift type code already exists.")
    shift = ShiftType(**shift_in.model_dump())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift

@router.put("/shift-types/{shift_id}", response_model=ShiftTypeResponse)
def update_shift_type(shift_id: int, shift_in: ShiftTypeUpdate, db: Session = Depends(get_db)):
    shift = db.query(ShiftType).filter(ShiftType.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift type not found.")

    if shift_in.code and shift_in.code != shift.code:
        existing = db.query(ShiftType).filter(ShiftType.code == shift_in.code, ShiftType.id != shift_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Shift type code already taken.")
        shift.code = shift_in.code

    if shift_in.name is not None:
        shift.name = shift_in.name
    if shift_in.start_time is not None:
        shift.start_time = shift_in.start_time
    if shift_in.end_time is not None:
        shift.end_time = shift_in.end_time
    if shift_in.duration_hours is not None:
        shift.duration_hours = shift_in.duration_hours
    if shift_in.min_rest_hours_after is not None:
        shift.min_rest_hours_after = shift_in.min_rest_hours_after
    if shift_in.is_night_shift is not None:
        shift.is_night_shift = shift_in.is_night_shift
    if shift_in.is_active is not None:
        shift.is_active = shift_in.is_active

    db.commit()
    db.refresh(shift)
    return shift

@router.get("/departments/{dept_id}/requirements")
def get_department_requirements(dept_id: int, db: Session = Depends(get_db)):
    reqs = db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).all()
    return [
        {
            "id": r.id,
            "department_id": r.department_id,
            "shift_type_id": r.shift_type_id,
            "shift_code": r.shift_type.code,
            "day_of_week": r.day_of_week,
            "min_staff": r.min_staff,
            "optimal_staff": r.optimal_staff
        }
        for r in reqs
    ]

@router.put("/departments/{dept_id}/requirements")
def update_department_requirements(dept_id: int, req_in: UpdateRequirementsRequest, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    # Delete existing requirements
    db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).delete()
    for item in req_in.requirements:
        req = DepartmentRequirement(
            department_id=dept_id,
            shift_type_id=item.shift_type_id,
            day_of_week=item.day_of_week,
            min_staff=item.min_staff,
            optimal_staff=item.optimal_staff
        )
        db.add(req)
    db.commit()
    return {"message": "Requirements updated successfully."}
