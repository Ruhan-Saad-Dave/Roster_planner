"""Integration test for full roster workflow, dual views, audit scorecard, and exports."""
from datetime import date

def test_full_roster_generation_and_export_lifecycle(client, sample_scenario):
    # 1. Trigger Roster Generation with 2 variants for Nov 2026
    gen_payload = {
        "name": "Integration Test Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 2,
        "variant_strategies": ["BALANCED", "FLOAT_AVERSE"],
        "timeout_seconds": 10
    }
    res = client.post("/api/roster/generate", json=gen_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SOLVED"
    plan_id = data["plan_id"]
    assert len(data["variants"]) == 2

    # 2. Fetch Staff-Centric View
    sc_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    assert sc_res.status_code == 200
    sc_data = sc_res.json()
    assert sc_data["view_type"] == "staff_centric"
    assert len(sc_data["rows"]) == 6  # 6 employees in sample scenario
    assert len(sc_data["dates"]) == 30  # 30 days in November

    # 3. Fetch Slot-Centric View
    slot_res = client.get(f"/api/roster/{plan_id}?view=slot_centric")
    assert slot_res.status_code == 200
    slot_data = slot_res.json()
    assert slot_data["view_type"] == "slot_centric"
    assert len(slot_data["slots"]) > 0

    # 4. Fetch Workload Audit Scorecard
    audit_res = client.get(f"/api/analytics/plan/{plan_id}/scorecard")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert len(audit_data["employee_scorecards"]) == 6
    assert audit_data["total_scheduled_hours"] > 0

    # 5. Export Formatted Excel
    excel_res = client.get(f"/api/export/{plan_id}/excel?view=both")
    assert excel_res.status_code == 200
    assert "spreadsheetml.sheet" in excel_res.headers["content-type"]
    assert len(excel_res.content) > 1000

    # 6. Export Vector PDF
    pdf_res = client.get(f"/api/export/{plan_id}/pdf")
    assert pdf_res.status_code == 200
    assert "pdf" in pdf_res.headers["content-type"]
    assert pdf_res.content.startswith(b"%PDF")


def test_one_click_auto_resolve_all_deficits(client, test_db, sample_scenario):
    """Verify 1-Click Auto-Resolve All Shortages handles chained consecutive deficits without NoneType start_time errors."""
    from src.db.models import DeficitLog, Department, ShiftType
    gen_res = client.post("/api/roster/generate", json={
        "name": "Deficit Resolution Test",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 1,
        "timeout_seconds": 5
    })
    plan_id = gen_res.json()["plan_id"]

    dept = test_db.query(Department).first()
    shift = test_db.query(ShiftType).first()
    d1 = DeficitLog(plan_id=plan_id, department_id=dept.id, shift_type_id=shift.id, date=date(2026, 11, 20), shortage_count=1, reason_code="UNSTAFFED")
    d2 = DeficitLog(plan_id=plan_id, department_id=dept.id, shift_type_id=shift.id, date=date(2026, 11, 21), shortage_count=1, reason_code="UNSTAFFED")
    test_db.add_all([d1, d2])
    test_db.commit()

    fix_res = client.post(f"/api/roster/{plan_id}/resolve-all-deficits")
    assert fix_res.status_code == 200
    res_data = fix_res.json()
    assert "resolved_count" in res_data
    assert res_data["resolved_count"] >= 2
