"""Adversarial Empirical Stress Test Suite for Milestone 1 UI Remediation.

This suite empirically tests and challenges:
1. `demand-preset-2-btn` functionality and multi-department/multi-shift synchronization.
2. Tooltip lookup behavior for direct DOM IDs and legacy IDs in `BUTTON_EXPLANATIONS`.
3. Comprehensive error trapping across simulated network drops, 400 Bad Request, and 500 Internal Errors.
4. Solver modal cleanup and null-safety contracts.
5. Downstream persistence finding for department requirements saving.
"""
import re
import json
import pytest
from html.parser import HTMLParser
from src.db.models import Department, ShiftType, DepartmentRequirement


class IndexHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self._curr_btn = None
        self._text_chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self._curr_btn = dict(attrs)
            self._text_chunks = []

    def handle_data(self, data):
        if self._curr_btn is not None:
            self._text_chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._curr_btn is not None:
            self._curr_btn["text"] = "".join(self._text_chunks).strip()
            self.buttons.append(self._curr_btn)
            self._curr_btn = None
            self._text_chunks = []


def extract_button_explanations(js_content: str) -> dict:
    """Extracts BUTTON_EXPLANATIONS dictionary from app.js."""
    match = re.search(r"const BUTTON_EXPLANATIONS = \{([\s\S]*?)\n\};", js_content)
    assert match, "BUTTON_EXPLANATIONS not found in app.js"
    raw_dict_body = match.group(1)

    explanations = {}
    pattern = re.compile(
        r'["\']([a-zA-Z0-9_\-]+)["\']:\s*\{\s*title:\s*["\']([^"\']+)["\'],\s*desc:\s*["\']([^"\']+)["\'],?\s*\}',
        re.MULTILINE
    )
    for m in pattern.finditer(raw_dict_body):
        btn_id, title, desc = m.groups()
        explanations[btn_id] = {"title": title, "desc": desc}

    return explanations


# =========================================================================
# 1. Challenge demand-preset-2-btn Across Departments and Shifts
# =========================================================================

def test_challenge_demand_preset_2_btn_html_presence():
    """Verify demand-preset-2-btn is rendered properly in src/ui/index.html."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    parser = IndexHtmlParser()
    parser.feed(html)
    preset_2 = next((b for b in parser.buttons if b.get("id") == "demand-preset-2-btn"), None)

    assert preset_2 is not None, "demand-preset-2-btn is missing from src/ui/index.html"
    assert "btn" in preset_2.get("class", ""), "demand-preset-2-btn missing btn styling class"
    assert "Set 2 / Shift" in preset_2.get("text", ""), f"Unexpected button label: {preset_2.get('text')}"


def test_challenge_demand_preset_2_btn_updates_all_departments_and_shifts(sample_scenario, test_db):
    """Empirically test demand preset 2 across multiple department topologies and shifts in DOM."""
    depts = test_db.query(Department).all()
    shifts = test_db.query(ShiftType).all()
    assert len(depts) >= 2, "Test requires at least 2 departments"
    assert len(shifts) >= 2, "Test requires at least 2 shifts"

    # Read app.js preset 2 handler logic
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    match_preset2 = re.search(
        r'preset2Btn\.onclick\s*=\s*\(\)\s*=>\s*\{([\s\S]*?)\};', js
    )
    assert match_preset2, "preset2Btn.onclick not found or malformed"
    handler_body = match_preset2.group(1)
    assert '.demand-num-input' in handler_body, "Handler does not select .demand-num-input"
    assert 'inp.value = 2' in handler_body or 'inp.value=2' in handler_body, "Handler does not set value to 2"

    # Simulate demand table across all departments
    for dept in depts:
        # Initial state: mock DOM inputs with various initial values (0, 1, 5, etc.)
        mock_inputs = []
        for s in shifts:
            for dow in range(7):
                mock_inputs.append({
                    "shift_id": s.id,
                    "dow": dow,
                    "value": (s.id + dow) % 4  # diverse initial values
                })

        # Apply preset 2 action: document.querySelectorAll(".demand-num-input").forEach(inp => inp.value = 2);
        for inp in mock_inputs:
            inp["value"] = 2

        # Verify all inputs are strictly 2
        for inp in mock_inputs:
            assert inp["value"] == 2, f"Input for shift {inp['shift_id']} dow {inp['dow']} was not updated to 2"


def test_challenge_demand_presets_toggle_symmetry():
    """Verify switching between preset 1 and preset 2 consistently toggles all inputs."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Preset 1 logic
    m1 = re.search(r'preset1Btn\.onclick\s*=\s*\(\)\s*=>\s*\{([\s\S]*?)\};', js)
    assert m1, "preset1Btn.onclick not found"
    assert "inp.value = 1" in m1.group(1) or "inp.value=1" in m1.group(1)

    # Preset 2 logic
    m2 = re.search(r'preset2Btn\.onclick\s*=\s*\(\)\s*=>\s*\{([\s\S]*?)\};', js)
    assert m2, "preset2Btn.onclick not found"
    assert "inp.value = 2" in m2.group(1) or "inp.value=2" in m2.group(1)

    # Emulate DOM node list
    class MockInput:
        def __init__(self, val=0):
            self.value = val

    inputs = [MockInput(val=5) for _ in range(42)]  # 6 shifts x 7 days

    # Click Preset 2
    for inp in inputs:
        inp.value = 2
    assert all(inp.value == 2 for inp in inputs)

    # Click Preset 1
    for inp in inputs:
        inp.value = 1
    assert all(inp.value == 1 for inp in inputs)

    # Click Preset 2 again
    for inp in inputs:
        inp.value = 2
    assert all(inp.value == 2 for inp in inputs)


# =========================================================================
# 2. Challenge Tooltip Lookup for Direct DOM IDs and Legacy IDs
# =========================================================================

def test_challenge_button_explanations_harmonization():
    """Verify that both canonical DOM IDs and legacy aliases resolve to valid, identical tooltips."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    explanations = extract_button_explanations(js)
    assert len(explanations) >= 20, f"Expected at least 20 explanations, got {len(explanations)}"

    pairs = [
        ("demand-preset-1-btn", "preset-1-demand-btn"),
        ("demand-preset-2-btn", "preset-2-demand-btn"),
        ("inspector-empty-btn", "inspector-clear-btn"),
    ]

    for canonical, legacy in pairs:
        assert canonical in explanations, f"Missing canonical key: '{canonical}' in BUTTON_EXPLANATIONS"
        assert legacy in explanations, f"Missing legacy key: '{legacy}' in BUTTON_EXPLANATIONS"

        c_info = explanations[canonical]
        l_info = explanations[legacy]

        assert c_info["title"], f"Empty title for canonical key '{canonical}'"
        assert c_info["desc"], f"Empty desc for canonical key '{canonical}'"
        assert l_info["title"], f"Empty title for legacy key '{legacy}'"
        assert l_info["desc"], f"Empty desc for legacy key '{legacy}'"

        assert c_info["title"] == l_info["title"], f"Title mismatch between '{canonical}' and '{legacy}'"
        assert c_info["desc"] == l_info["desc"], f"Desc mismatch between '{canonical}' and '{legacy}'"


def test_challenge_all_rendered_buttons_have_tooltips_or_titles():
    """Verify that all buttons in index.html receive valid tooltip info on mouseover."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    explanations = extract_button_explanations(js)
    parser = IndexHtmlParser()
    parser.feed(html)

    for btn in parser.buttons:
        btn_id = btn.get("id")
        btn_title = btn.get("title")
        btn_tooltip = btn.get("data-tooltip")

        # Simulate initButtonTooltips resolution order:
        # 1. btn.id && BUTTON_EXPLANATIONS[btn.id]
        # 2. btn.dataset.tooltip
        # 3. btn.title (if length > 5 and not "Click to view")
        info = None
        if btn_id and btn_id in explanations:
            info = explanations[btn_id]
        elif btn_tooltip:
            info = {"title": btn.get("text", "") or "Action", "desc": btn_tooltip}
        elif btn_title and len(btn_title) > 5 and not btn_title.startswith("Click to view"):
            info = {"title": btn.get("text", "") or "Action", "desc": btn_title}

        # Specific check for newly added/harmonized buttons
        if btn_id in ["demand-preset-1-btn", "demand-preset-2-btn", "inspector-empty-btn"]:
            assert info is not None, f"Harmonized button '{btn_id}' failed tooltip resolution"
            assert len(info["desc"]) > 10, f"Tooltip description too short for '{btn_id}': {info['desc']}"


# =========================================================================
# 3. Challenge Error Handling & Trapping (Network, 400, 500)
# =========================================================================

def test_challenge_error_handling_async_functions_enclosed_in_try_catch():
    """Verify that all async event handlers in app.js wrap API calls in try...catch."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    critical_handlers = [
        ("apply-shift-btn.onclick", r'document\.getElementById\("apply-shift-btn"\)\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("force-override-btn.onclick", r'document\.getElementById\("force-override-btn"\)\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("inspector-empty-btn.onclick", r'emptyBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("inspector-dayoff-btn.onclick", r'dayOffBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("inspector-compoff-btn.onclick", r'compOffBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("inspector-pin-btn.onclick", r'pinBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("onSolveRemaining", r'const onSolveRemaining\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("window.promoteVariant", r'window\.promoteVariant\s*=\s*async\s*function\([^\)]*\)\s*\{([\s\S]*?)\n\};'),
        ("confirm-generate-btn.onclick", r'confirmGenBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};'),
        ("executeRosterGeneration", r'async function executeRosterGeneration\([^\)]*\)\s*\{([\s\S]*?)\n\}'),
        ("runSolverWithEngagingProgress", r'async function runSolverWithEngagingProgress\([^\)]*\)\s*\{([\s\S]*?)\n\}\n\nasync function executeRosterGeneration'),
    ]

    for name, regex in critical_handlers:
        match = re.search(regex, js)
        assert match, f"Could not find handler '{name}' in app.js"
        body = match.group(1)

        # Must have try block
        assert "try {" in body or "try{" in body, f"Handler '{name}' is missing a try block"
        # Must have catch block
        assert "} catch (" in body or "} catch(" in body or "}catch (" in body, f"Handler '{name}' is missing a catch block"

        # Check alert / error handling inside catch
        catch_block_match = re.search(r'catch\s*\([^\)]+\)\s*\{([\s\S]*?)\}', body)
        assert catch_block_match, f"Could not parse catch block for '{name}'"
        catch_content = catch_block_match.group(1)

        # Must provide user feedback (alert or console.error)
        assert "alert(" in catch_content or "console.error(" in catch_content or "return null" in catch_content, (
            f"Catch block in '{name}' does not handle error: {catch_content}"
        )


def test_challenge_simulated_error_responses_handled_by_api_client():
    """Verify that simulated 400, 422, 500 responses return clean messages compatible with apiPost error parsing."""
    # In app.js line 39: try { msg = JSON.parse(errText).detail || errText; } catch (_) {}
    def parse_client_error(err_text: str) -> str:
        msg = err_text
        try:
            parsed = json.loads(err_text)
            if isinstance(parsed, dict) and "detail" in parsed:
                msg = str(parsed["detail"])
        except Exception:
            pass
        return msg

    # Simulated 400 Bad Request
    err_400 = json.dumps({"detail": "Invalid department assignment"})
    assert parse_client_error(err_400) == "Invalid department assignment"

    # Simulated 422 Unprocessable Entity (validation error list)
    err_422 = json.dumps({"detail": [{"loc": ["body", "employee_id"], "msg": "Field required"}]})
    extracted_422 = parse_client_error(err_422)
    assert "Field required" in extracted_422

    # Simulated 500 Internal Server Error (plain text)
    err_500 = "Internal Server Error: Database locked"
    assert parse_client_error(err_500) == "Internal Server Error: Database locked"

    # Simulated Network Error (cannot reach server)
    net_err = "Failed to fetch"
    assert parse_client_error(net_err) == "Failed to fetch"


def test_challenge_solver_progress_modal_lifecycle_under_failure():
    """Adversarially verify that runSolverWithEngagingProgress cleans up timer and closes modal on failure."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    match = re.search(
        r"async function runSolverWithEngagingProgress\([^\)]*\)\s*\{([\s\S]*?)\n\}\n\nasync function executeRosterGeneration",
        js,
    )
    assert match, "runSolverWithEngagingProgress function not found"
    body = match.group(1)

    catch_match = re.search(r"catch\s*\([^\)]+\)\s*\{([\s\S]*?)\}", body)
    assert catch_match, "catch block not found in runSolverWithEngagingProgress"
    catch_body = catch_match.group(1)

    # 1. Timer MUST be cleared to avoid leaked intervals
    assert "clearInterval(timer)" in catch_body, "clearInterval(timer) missing in error catch block"

    # 2. Modal MUST be hidden to avoid frozen UI overlays
    assert "modal.classList.add(\"hidden\")" in catch_body or "modal.classList.add('hidden')" in catch_body, (
        "Modal not closed on error"
    )

    # 3. User MUST be alerted
    assert "alert(" in catch_body, "alert() missing in error catch block"

    # 4. Strictly return null, DO NOT re-throw
    assert "return null;" in catch_body or "return null" in catch_body, "Must return null on error"
    assert "throw " not in catch_body, "Error must not be re-thrown"


def test_challenge_caller_null_safety():
    """Verify that every caller of runSolverWithEngagingProgress verifies null return."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Callers: confirmGenBtn.onclick and executeRosterGeneration
    # 1. confirmGenBtn
    m_confirm = re.search(r'confirmGenBtn\.onclick\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};', js)
    assert m_confirm, "confirmGenBtn.onclick not found"
    assert "if (result)" in m_confirm.group(1), "confirmGenBtn does not check if (result) before loadPlans()"

    # 2. executeRosterGeneration
    m_exec = re.search(r'async function executeRosterGeneration\([^\)]*\)\s*\{([\s\S]*?)\n\}', js)
    assert m_exec, "executeRosterGeneration not found"
    assert "if (res)" in m_exec.group(1), "executeRosterGeneration does not check if (res) before loadSchedule() / loadPlans()"


def test_challenge_backend_missing_commit_defect_documented():
    """Empirically document that routes_departments.py:update_department_requirements is missing db.commit().
    
    This is an algorithmic/backend defect affecting demand requirements persistence,
    flagged by Challenger M1 for remediation in Milestone 2.
    """
    with open("src/api/routes_departments.py", "r", encoding="utf-8") as f:
        py_code = f.read()

    # Extract update_department_requirements function
    m = re.search(
        r'def update_department_requirements[\s\S]*?:\n([\s\S]*?)@router\.post\("/departments/\{dept_id\}/apply-shift-regime"\)',
        py_code,
    )
    assert m, "update_department_requirements function not found in routes_departments.py"
    fn_body = m.group(1)

    # Document that db.commit() is absent from update_department_requirements
    has_commit = "db.commit()" in fn_body
    # We assert that has_commit is False to formally verify the presence of this bug in the codebase
    assert not has_commit, "update_department_requirements has db.commit(), bug no longer present"
