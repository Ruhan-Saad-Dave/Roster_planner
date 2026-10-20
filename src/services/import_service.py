"""Data import service for template downloads, spreadsheet staging preview, and database commit."""
import io
import csv
from datetime import datetime, date
from typing import Dict, List, Any, Tuple
import openpyxl
from sqlalchemy.orm import Session
from src.db.models import Department, ShiftType, Employee, DepartmentRequirement, LeaveRecord

def generate_sample_template(entity_type: str) -> bytes:
    """Generate sample downloadable .csv template with headers and instructions."""
    output = io.StringIO()
    writer = csv.writer(output)

    if entity_type == "departments":
        writer.writerow(["code", "name", "color_code", "operating_regime"])
        writer.writerow(["ICU", "Intensive Care Unit", "#EF4444", "24_7"])
        writer.writerow(["CLINIC", "Outpatient Clinic", "#10B981", "WEEKDAYS_ONLY"])
    elif entity_type == "shifts":
        writer.writerow(["code", "name", "start_time", "end_time", "duration_hours", "min_rest_hours", "is_night"])
        writer.writerow(["MORN", "Morning Shift", "07:00:00", "15:30:00", "8.5", "14", "FALSE"])
        writer.writerow(["NIGHT", "Night Shift", "23:00:00", "07:30:00", "8.5", "16", "TRUE"])
    elif entity_type == "employees":
        writer.writerow(["employee_code", "name", "email", "primary_department_code", "max_hours_week"])
        writer.writerow(["EMP101", "Alice Morgan", "alice@example.com", "ICU", "40.0"])
        writer.writerow(["EMP102", "Robert Chen", "robert@example.com", "CLINIC", "37.5"])
    elif entity_type == "demands":
        writer.writerow(["department_code", "shift_code", "day_of_week", "min_staff", "optimal_staff"])
        writer.writerow(["ICU", "MORN", "0", "3", "4"])
        writer.writerow(["ICU", "NIGHT", "0", "2", "2"])
    elif entity_type == "leaves":
        writer.writerow(["employee_code", "start_date", "end_date", "leave_type", "notes"])
        writer.writerow(["EMP101", "2026-11-05", "2026-11-09", "VACATION", "Annual Holiday"])
    else:
        writer.writerow(["unknown_entity"])

    return output.getvalue().encode("utf-8")

def parse_and_validate_file(
    db: Session,
    entity_type: str,
    file_bytes: bytes,
    filename: str
) -> Dict[str, Any]:
    """Parse CSV/Excel and validate each row before database insertion."""
    rows = []
    # Check if CSV or Excel
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        raw_rows = list(ws.iter_rows(values_only=True))
        if not raw_rows:
            return {"valid_rows": 0, "invalid_rows": 0, "errors": ["File is empty."]}
        headers = [str(h).strip().lower() for h in raw_rows[0] if h is not None]
        for r in raw_rows[1:]:
            if any(cell is not None for cell in r):
                row_dict = {headers[i]: r[i] for i in range(min(len(headers), len(r)))}
                rows.append(row_dict)
    else:
        # CSV
        text = file_bytes.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            cleaned = {k.strip().lower(): (v.strip() if v else "") for k, v in r.items() if k}
            rows.append(cleaned)

    errors = []
    valid_count = 0
    preview_sample = []

    # Validation rules
    dept_codes = {d.code: d.id for d in db.query(Department).all()}
    shift_codes = {s.code: s.id for s in db.query(ShiftType).all()}
    emp_codes = {e.employee_code: e.id for e in db.query(Employee).all()}

    for row_idx, r in enumerate(rows, start=2):
        row_errors = []

        if entity_type == "departments":
            code = str(r.get("code", "")).strip()
            name = str(r.get("name", "")).strip()
            regime = str(r.get("operating_regime", "24_7")).strip()
            if not code or not name:
                row_errors.append("Code and Name are required.")
            if regime not in ["24_7", "WEEKDAYS_ONLY", "CUSTOM"]:
                row_errors.append("Operating regime must be 24_7, WEEKDAYS_ONLY, or CUSTOM.")
            if code in dept_codes:
                row_errors.append(f"Department code '{code}' already exists.")

        elif entity_type == "employees":
            code = str(r.get("employee_code", "")).strip()
            name = str(r.get("name", "")).strip()
            dept_code = str(r.get("primary_department_code", "")).strip()
            try:
                max_hrs = float(r.get("max_hours_week", 40.0))
                if max_hrs <= 0:
                    row_errors.append("max_hours_week must be > 0.")
            except ValueError:
                row_errors.append("max_hours_week must be a valid number.")

            if not code or not name:
                row_errors.append("Employee code and Name are required.")
            if dept_code not in dept_codes:
                row_errors.append(f"Referenced department '{dept_code}' does not exist.")
            if code in emp_codes:
                row_errors.append(f"Employee code '{code}' already exists.")

        if row_errors:
            errors.append({
                "row_number": row_idx,
                "data": r,
                "error": "; ".join(row_errors)
            })
        else:
            valid_count += 1
            if len(preview_sample) < 5:
                preview_sample.append(r)

    return {
        "entity_type": entity_type,
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "invalid_rows": len(errors),
        "errors": errors,
        "preview_sample": preview_sample,
        "raw_parsed_rows": rows if len(errors) == 0 else []
    }

def commit_import_rows(db: Session, entity_type: str, parsed_rows: List[Dict[str, Any]]) -> int:
    """Commit pre-validated rows into SQLite database atomically."""
    dept_codes = {d.code: d.id for d in db.query(Department).all()}
    inserted = 0

    if entity_type == "departments":
        for r in parsed_rows:
            d = Department(
                code=r["code"].strip(),
                name=r["name"].strip(),
                color_code=r.get("color_code", "#3B82F6").strip() or "#3B82F6",
                operating_regime=r.get("operating_regime", "24_7").strip()
            )
            db.add(d)
            inserted += 1

    elif entity_type == "employees":
        for r in parsed_rows:
            dept_id = dept_codes[r["primary_department_code"].strip()]
            emp = Employee(
                employee_code=r["employee_code"].strip(),
                name=r["name"].strip(),
                email=r.get("email", None),
                primary_department_id=dept_id,
                max_hours_week=float(r.get("max_hours_week", 40.0))
            )
            db.add(emp)
            inserted += 1

    db.commit()
    return inserted
