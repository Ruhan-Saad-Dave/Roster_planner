"""Settings and organizational preference routes."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import SystemSetting, ShiftType
from src.api.schemas import SystemSettingsUpdate, ShiftTypeResponse
from typing import Dict, Any, List

router = APIRouter(prefix="/api/settings", tags=["System Settings"])

DEFAULT_SETTINGS = {
    "generator_default_mode": "blank",
    "remember_generator_mode": "false",
    "custom_status_codes": json.dumps({
        "OFF": "OFF",
        "COFF": "Coff",
        "VAC": "Vacation",
        "SICK": "Sick"
    })
}

@router.get("")
def get_settings(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve all current system settings with defaults."""
    db_settings = {s.key: s.value for s in db.query(SystemSetting).all()}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(db_settings)

    # Parse JSON custom codes if present
    custom_codes = {}
    try:
        custom_codes = json.loads(merged.get("custom_status_codes", "{}"))
    except Exception:
        custom_codes = {"OFF": "OFF", "COFF": "Coff", "VAC": "Vacation", "SICK": "Sick"}

    return {
        "generator_default_mode": merged.get("generator_default_mode", "blank"),
        "remember_generator_mode": merged.get("remember_generator_mode", "false") == "true",
        "custom_status_codes": custom_codes,
        "raw_settings": merged
    }

@router.post("")
def update_settings(update: SystemSettingsUpdate, db: Session = Depends(get_db)):
    """Update system settings."""
    for key, val in update.settings.items():
        existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if existing:
            existing.value = str(val)
        else:
            db.add(SystemSetting(key=key, value=str(val)))
    db.commit()
    return {"message": "Settings updated successfully."}
