"""Analytics and manager audit scorecard endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.services.analytics_service import (
    get_workload_audit_scorecard, get_historical_analytics_summary
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Audit"])

@router.get("/summary")
def get_analytics_summary(db: Session = Depends(get_db)):
    return get_historical_analytics_summary(db)

@router.get("/plan/{plan_id}/scorecard")
def get_plan_audit_scorecard(plan_id: int, db: Session = Depends(get_db)):
    try:
        return get_workload_audit_scorecard(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
