"""Bulk spreadsheet import and onboarding endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.services.import_service import (
    generate_sample_template, parse_and_validate_file, commit_import_rows
)

router = APIRouter(prefix="/api/import", tags=["Bulk Import"])

@router.get("/template/{entity_type}")
def download_template(entity_type: str):
    allowed = ["departments", "shifts", "employees", "demands", "leaves"]
    if entity_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Entity type must be one of: {allowed}")

    template_bytes = generate_sample_template(entity_type)
    return Response(
        content=template_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=template_{entity_type}.csv"}
    )

@router.post("/preview/{entity_type}")
async def preview_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    result = parse_and_validate_file(db, entity_type, contents, file.filename or "data.csv")
    return result

@router.post("/commit/{entity_type}")
async def commit_import(
    entity_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    preview = parse_and_validate_file(db, entity_type, contents, file.filename or "data.csv")
    if preview["invalid_rows"] > 0:
        raise HTTPException(status_code=400, detail={"message": "File contains validation errors.", "errors": preview["errors"]})

    inserted = commit_import_rows(db, entity_type, preview["raw_parsed_rows"])
    return {"message": f"Successfully imported {inserted} {entity_type} records."}
