"""Department and Shift configuration routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from src.db.session import get_db
from src.db.models import Department, ShiftType, DepartmentRequirement, RosterAssignment
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
    db.flush()

    # Automatically initialize default staffing requirements (min 1 per shift on operating days)
    shifts = db.query(ShiftType).filter(ShiftType.is_active == True).all()
    for s in shifts:
        for dow in range(7):
            min_st = 0 if (dept.operating_regime == "WEEKDAYS_ONLY" and dow in [5, 6]) else 1
            db.add(DepartmentRequirement(
                department_id=dept.id,
                shift_type_id=s.id,
                day_of_week=dow,
                min_staff=min_st,
                optimal_staff=min_st
            ))

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

@router.delete("/shift-types/{shift_id}")
def delete_shift_type(shift_id: int, db: Session = Depends(get_db)):
    shift = db.query(ShiftType).filter(ShiftType.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift type not found.")

    assign_count = db.query(RosterAssignment).filter(RosterAssignment.shift_type_id == shift_id).count()
    if assign_count > 0:
        shift.is_active = False
        db.commit()
        return {"message": f"Shift type '{shift.name}' has existing assignments in rosters, so it has been deactivated.", "deactivated": True}

    db.delete(shift)
    db.commit()
    return {"message": f"Shift type '{shift.name}' deleted successfully.", "deleted": True}

@router.get("/departments/{dept_id}/requirements")
def get_department_requirements(dept_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    reqs = db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).all()
    if not reqs:
        shifts = db.query(ShiftType).filter(ShiftType.is_active == True).all()
        for s in shifts:
            for dow in range(7):
                min_st = 0 if (dept.operating_regime == "WEEKDAYS_ONLY" and dow in [5, 6]) else 1
                db.add(DepartmentRequirement(
                    department_id=dept_id,
                    shift_type_id=s.id,
                    day_of_week=dow,
                    min_staff=min_st,
                    optimal_staff=min_st
                ))
        db.commit()
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

def _persist_requirements(session: Session, department: Department):
    session.commit()
    session.refresh(department)

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

    _persist_requirements(db, dept)
    reqs = db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).all()
    return [
        {
            "id": r.id,
            "department_id": r.department_id,
            "shift_type_id": r.shift_type_id,
            "shift_code": r.shift_type.code if r.shift_type else "",
            "day_of_week": r.day_of_week,
            "min_staff": r.min_staff,
            "optimal_staff": r.optimal_staff
        }
        for r in reqs
    ]


@router.post("/departments/{dept_id}/apply-shift-regime")
def apply_shift_regime(dept_id: int, regime: str = "hybrid_weekday3_weekend2", db: Session = Depends(get_db)):
    """Dynamically configure department staffing requirements for 3 shifts, 2 shifts, or weekday3/weekend2 hybrid."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    shifts = db.query(ShiftType).filter(ShiftType.is_active == True).order_by(ShiftType.start_time).all()
    if not shifts:
        raise HTTPException(status_code=400, detail="No active shift types found.")

    # Classify shifts
    night_shifts = [s for s in shifts if s.is_night_shift]
    day_shifts = [s for s in shifts if not s.is_night_shift]

    morn_shift = day_shifts[0] if len(day_shifts) > 0 else shifts[0]
    eve_shift = day_shifts[1] if len(day_shifts) > 1 else None
    night_shift = night_shifts[0] if len(night_shifts) > 0 else (shifts[-1] if shifts[-1] != morn_shift else None)

    # Delete existing requirements
    db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).delete()

    for dow in range(7):
        is_weekend = dow in [5, 6]
        for s in shifts:
            min_st = 0
            if dept.operating_regime == "WEEKDAYS_ONLY" and is_weekend:
                min_st = 0
            elif regime == "3_shifts":
                min_st = 1
            elif regime == "2_shifts":
                # In 2-shift regime: Morning and Night are active, Evening is collapsed (0)
                if s == morn_shift or s == night_shift:
                    min_st = 1
                else:
                    min_st = 0
            elif regime == "hybrid_weekday3_weekend2":
                if not is_weekend:
                    min_st = 1  # 3 shifts on weekdays
                else:
                    # 2 shifts on weekend (collapse Evening)
                    if s == morn_shift or s == night_shift:
                        min_st = 1
                    else:
                        min_st = 0
            else:
                min_st = 1

            db.add(DepartmentRequirement(
                department_id=dept_id,
                shift_type_id=s.id,
                day_of_week=dow,
                min_staff=min_st,
                optimal_staff=min_st
            ))

    db.commit()
    reqs = db.query(DepartmentRequirement).filter(DepartmentRequirement.department_id == dept_id).all()
    return {
        "message": f"Successfully applied '{regime}' shift allocation regime to {dept.name}.",
        "department_id": dept_id,
        "regime": regime,
        "requirements_count": len(reqs)
    }

