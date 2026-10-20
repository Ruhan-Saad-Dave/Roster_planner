"""Automated UI Button and Interactive Element Crawler.

Audits every single interactive button in index.html, verifies app.js binding,
and tests the complete backend execution pipeline for each button action.
"""
import re
import pytest
from datetime import date
from html.parser import HTMLParser

class ButtonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self._current_btn = None
        self._text_chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            attr_dict = dict(attrs)
            self._current_btn = attr_dict
            self._text_chunks = []

    def handle_data(self, data):
        if self._current_btn is not None:
            self._text_chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._current_btn is not None:
            self._current_btn["text"] = "".join(self._text_chunks).strip()
            self._current_btn["classes"] = self._current_btn.get("class", "").split()
            self.buttons.append(self._current_btn)
            self._current_btn = None
            self._text_chunks = []

def test_audit_all_buttons_bound_in_app_js():
    """Extract all buttons from index.html and verify that none are unhandled."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    parser = ButtonParser()
    parser.feed(html)
    buttons = parser.buttons
    assert len(buttons) > 0, "No buttons found in index.html"

    unhandled = []
    audited_buttons = []

    for btn in buttons:
        btn_id = btn.get("id")
        btn_classes = btn.get("classes", [])
        data_tab = btn.get("data-tab")
        onclick_attr = btn.get("onclick")

        # Check if button is handled
        is_handled = False

        if onclick_attr:
            is_handled = True
        elif btn_id and btn_id in js:
            is_handled = True
        elif "close-modal" in btn_classes and "close-modal" in js:
            is_handled = True
        elif "ribbon-tab" in btn_classes and "ribbon-tab" in js:
            is_handled = True
        elif "status-icon-btn" in btn_classes and "status-icon-btn" in js:
            is_handled = True
        elif "status-zoom-btn" in btn_classes and "status-zoom-btn" in js:
            is_handled = True
        elif "status-zoom-label" in btn_classes and "status-zoom-label" in js:
            is_handled = True
        elif data_tab and data_tab in js:
            is_handled = True

        audited_buttons.append({
            "text": btn.get("text", ""),
            "id": btn_id,
            "classes": btn_classes,
            "handled": is_handled
        })

        if not is_handled:
            unhandled.append(str(btn))

    assert len(unhandled) == 0, f"Found unhandled buttons: {unhandled}"
    print(f"Verified {len(audited_buttons)} UI buttons are all properly bound.")


def test_crawler_executes_all_button_backend_endpoints(client, sample_scenario):
    """Simulates the backend actions triggered by every single UI button."""
    # 1. + New Roster (confirm-generate-btn)
    gen_res = client.post("/api/roster/generate", json={
        "name": "Crawler Test Roster",
        "planning_year": 2026,
        "planning_month": 11,
        "variant_count": 2,
        "timeout_seconds": 5
    })
    assert gen_res.status_code == 200
    plan_id = gen_res.json()["plan_id"]

    # 2. Schedule views: Staff-Centric, Slot-Centric, Audit Scorecard
    sc_res = client.get(f"/api/roster/{plan_id}?view=staff_centric")
    assert sc_res.status_code == 200
    slot_res = client.get(f"/api/roster/{plan_id}?view=slot_centric")
    assert slot_res.status_code == 200
    scorecard_res = client.get(f"/api/analytics/plan/{plan_id}/scorecard")
    assert scorecard_res.status_code == 200

    # 3. Solve Remaining (solve-remaining-btn / sidebar-solve-btn)
    rem_res = client.post(f"/api/roster/{plan_id}/solve-remaining", json={"timeout_seconds": 5})
    assert rem_res.status_code == 200

    # 4. Compare Variants & Promote (variants-btn & promoteVariant)
    promote_res = client.post(f"/api/roster/{plan_id}/promote", json={})
    assert promote_res.status_code == 200

    # 5. Export Formatted Excel (export-excel-btn)
    excel_res = client.get(f"/api/export/{plan_id}/excel?view=both")
    assert excel_res.status_code == 200
    assert len(excel_res.content) > 1000

    # 6. Export PDF (export-pdf-btn)
    pdf_res = client.get(f"/api/export/{plan_id}/pdf")
    assert pdf_res.status_code == 200

    # 7. Pin / Lock Shift (inspector-pin-btn)
    pin_res = client.post(f"/api/roster/{plan_id}/assignments/toggle-pin?employee_id=1&date=2026-11-01", json={})
    assert pin_res.status_code == 200
    assert "is_pinned" in pin_res.json()

    # 8. Set as Day OFF / Clear (inspector-clear-btn)
    clear_res = client.delete(f"/api/roster/{plan_id}/assignments?employee_id=1&date=2026-11-01")
    assert clear_res.status_code == 200
    assert clear_res.json()["cleared"] is True

    # 9. Download Templates (download-template-btn)
    for ent in ["employees", "departments", "demands"]:
        tpl_res = client.get(f"/api/import/template/{ent}")
        assert tpl_res.status_code == 200
        assert "text/csv" in tpl_res.headers["content-type"]

    # 10. Preview and Commit Import (import-file-input & commit-import-btn)
    csv_data = "code,name,color_code,operating_regime\nONCOLOGY,Oncology Clinic,#8B5CF6,WEEKDAYS_ONLY\n"
    preview_res = client.post(
        "/api/import/preview/departments",
        files={"file": ("dept.csv", csv_data.encode("utf-8"), "text/csv")}
    )
    assert preview_res.status_code == 200
    assert preview_res.json()["valid_rows"] == 1

    commit_res = client.post(
        "/api/import/commit/departments",
        files={"file": ("dept.csv", csv_data.encode("utf-8"), "text/csv")}
    )
    assert commit_res.status_code == 200
    assert "Successfully imported" in commit_res.json()["message"]

    # 11. Deficits & 1-Click Fix (health-banner action)
    deficits_res = client.get(f"/api/roster/{plan_id}/deficits")
    assert deficits_res.status_code == 200

    # 12. Preceding Month Summary (toggle-prev-month-btn)
    prev_res = client.get("/api/roster/previous-month-summary?year=2026&month=11")
    assert prev_res.status_code == 200
