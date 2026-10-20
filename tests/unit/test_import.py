"""Unit tests for spreadsheet import parser and validation staging."""
from src.services.import_service import generate_sample_template, parse_and_validate_file
from src.db.models import Department

def test_template_generation():
    csv_bytes = generate_sample_template("departments")
    text = csv_bytes.decode("utf-8")
    assert "code,name,color_code,operating_regime" in text
    assert "ICU" in text

def test_csv_validation_duplicate_code(test_db):
    # Seed an existing department
    dept = Department(code="ICU", name="Intensive Care Unit", operating_regime="24_7")
    test_db.add(dept)
    test_db.commit()

    # Create CSV attempting to import duplicate ICU code
    csv_content = b"code,name,operating_regime\nICU,Duplicate ICU,24_7\nER,Emergency Room,24_7\n"
    res = parse_and_validate_file(test_db, "departments", csv_content, "test.csv")

    assert res["total_rows"] == 2
    assert res["invalid_rows"] == 1
    assert res["valid_rows"] == 1
    assert "already exists" in res["errors"][0]["error"]
