"""Excel and PDF export endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import (
    RosterPlan, RosterAssignment, DeficitLog, Employee, Department, ShiftType,
    LeaveRecord, SystemSetting
)
from src.services.export_service import generate_excel_export, generate_pdf_export

router = APIRouter(prefix="/api/export", tags=["Exports"])

@router.get("/{plan_id}/excel")
def export_excel(
    plan_id: int,
    view: str = Query("both", enum=["staff_centric", "slot_centric", "both"]),
    db: Session = Depends(get_db)
):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    deficits = db.query(DeficitLog).filter(DeficitLog.plan_id == plan_id).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    departments = db.query(Department).all()
    shifts = db.query(ShiftType).all()
    leaves = db.query(LeaveRecord).filter(
        LeaveRecord.status == "APPROVED",
        LeaveRecord.start_date <= plan.end_date,
        LeaveRecord.end_date >= plan.start_date
    ).all()
    custom_settings = {s.key: s.value for s in db.query(SystemSetting).all()}

    excel_bytes = generate_excel_export(
        plan=plan,
        assignments=assignments,
        deficits=deficits,
        employees=employees,
        departments=departments,
        shifts=shifts,
        leaves=leaves,
        custom_settings=custom_settings,
        view=view
    )

    clean_filename = f"Roster_{plan.name.replace(' ', '_')}_{plan_id}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={clean_filename}"}
    )

@router.get("/{plan_id}/pdf")
def export_pdf(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(RosterPlan).filter(RosterPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    assignments = db.query(RosterAssignment).filter(RosterAssignment.plan_id == plan_id).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    departments = db.query(Department).all()
    shifts = db.query(ShiftType).all()
    leaves = db.query(LeaveRecord).filter(
        LeaveRecord.status == "APPROVED",
        LeaveRecord.start_date <= plan.end_date,
        LeaveRecord.end_date >= plan.start_date
    ).all()
    custom_settings = {s.key: s.value for s in db.query(SystemSetting).all()}

    pdf_bytes = generate_pdf_export(
        plan=plan,
        assignments=assignments,
        employees=employees,
        departments=departments,
        shifts=shifts,
        leaves=leaves,
        custom_settings=custom_settings
    )

    clean_filename = f"Roster_{plan.name.replace(' ', '_')}_{plan_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={clean_filename}"}
    )
