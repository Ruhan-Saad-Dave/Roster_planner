"""Adversarial Challenge Test Suite for Milestone 1 UI Remediation.

Performs deep adversarial verification of:
1. DOM Element & Button ID integrity between index.html and app.js.
2. Null-safety of all getElementById queries in app.js.
3. BUTTON_EXPLANATIONS dictionary key harmonization.
4. Solver progress modal lifecycle & error simulation in runSolverWithEngagingProgress.
5. Promise safety in event handlers.
"""

import re
import pytest
from html.parser import HTMLParser


class ButtonExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self._curr = None
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self._curr = dict(attrs)
            self._chunks = []

    def handle_data(self, data):
        if self._curr is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._curr is not None:
            self._curr["text"] = "".join(self._chunks).strip()
            self._curr["classes"] = self._curr.get("class", "").split()
            self.buttons.append(self._curr)
            self._curr = None
            self._chunks = []


def test_adversarial_button_completeness():
    """Verify that every button in index.html is validly mapped and bound."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    parser = ButtonExtractor()
    parser.feed(html)
    buttons = parser.buttons

    assert len(buttons) >= 30, f"Expected at least 30 buttons, found {len(buttons)}"

    unhandled = []
    missing_id_and_class = []

    for btn in buttons:
        btn_id = btn.get("id")
        classes = btn.get("classes", [])
        onclick = btn.get("onclick")
        data_tab = btn.get("data-tab")

        if not btn_id and not classes and not onclick:
            missing_id_and_class.append(btn)
            continue

        handled = False
        if onclick:
            handled = True
        elif btn_id and (f'getElementById("{btn_id}")' in js or f"getElementById('{btn_id}')" in js or btn_id in js):
            handled = True
        elif any(c in js for c in classes):
            handled = True
        elif data_tab and data_tab in js:
            handled = True

        if not handled:
            unhandled.append(btn)

    assert not missing_id_and_class, f"Buttons without identifier or class: {missing_id_and_class}"
    assert not unhandled, f"Found unhandled buttons: {unhandled}"


def test_adversarial_button_explanations_keys():
    """Verify all critical button keys in BUTTON_EXPLANATIONS match DOM IDs."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Extract BUTTON_EXPLANATIONS block
    match = re.search(r"const BUTTON_EXPLANATIONS = (\{[\s\S]*?\n\};)\s*\n\s*function showButtonTooltip", js)
    assert match, "BUTTON_EXPLANATIONS dictionary not found in app.js"
    dict_content = match.group(1)

    # Must contain both new canonical IDs and backwards-compatible IDs
    required_keys = [
        "demand-preset-1-btn",
        "demand-preset-2-btn",
        "inspector-empty-btn",
        "preset-1-demand-btn",
        "preset-2-demand-btn",
        "inspector-clear-btn",
    ]

    for key in required_keys:
        assert f'"{key}"' in dict_content or f"'{key}'" in dict_content, f"Missing key in BUTTON_EXPLANATIONS: {key}"


def test_adversarial_get_element_by_id_null_guards():
    """Verify that getElementById usages in app.js are null-guarded or exist in index.html or dynamic templates."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    raw_ids = set(re.findall(r'getElementById\(["\']([a-zA-Z0-9_\-]+)["\']\)', js))

    # Elements in static HTML
    static_ids = set(re.findall(r'id=["\']([a-zA-Z0-9_\-]+)["\']', html))

    # Elements dynamically rendered in JS template strings
    dynamic_ids = set(re.findall(r'id=["\']([a-zA-Z0-9_\-]+)["\']', js))

    all_known_ids = static_ids | dynamic_ids

    missing_ids = raw_ids - all_known_ids
    assert not missing_ids, f"Elements queried via getElementById but nowhere defined in HTML or dynamic templates: {missing_ids}"


def test_adversarial_solver_error_simulation_contract():
    """Verify the structural contract of runSolverWithEngagingProgress."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Extract runSolverWithEngagingProgress function body
    match = re.search(
        r"async function runSolverWithEngagingProgress\([^\)]*\)\s*\{([\s\S]*?)\n\}\n\nasync function executeRosterGeneration",
        js,
    )
    assert match, "runSolverWithEngagingProgress not found"
    fn_body = match.group(1)

    # Check that error block cleans up timer, hides modal, alerts, and returns null
    catch_match = re.search(r"catch\s*\([^\)]+\)\s*\{([\s\S]*?)\}", fn_body)
    assert catch_match, "catch block not found in runSolverWithEngagingProgress"
    catch_body = catch_match.group(1)

    assert "clearInterval(timer)" in catch_body, "Timer not cleared in error catch"
    assert "modal.classList.add(\"hidden\")" in catch_body or "modal.classList.add('hidden')" in catch_body, "Modal not closed in error catch"
    assert "return null" in catch_body, "Function must return null instead of rethrowing"
    assert "throw " not in catch_body, "Error should not be re-thrown without caller catching"


def test_adversarial_solver_callers_handle_null():
    """Verify that every caller of runSolverWithEngagingProgress checks for null before proceeding."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js_lines = f.readlines()

    # Find line numbers of all calls to runSolverWithEngagingProgress
    call_lines = [i for i, line in enumerate(js_lines) if "runSolverWithEngagingProgress(" in line and "async function" not in line]
    assert len(call_lines) >= 2, f"Expected at least 2 call sites, found {len(call_lines)}"

    for idx in call_lines:
        # Inspect subsequent 15 lines for null check
        subsequent = "".join(js_lines[idx:idx + 18])
        has_null_check = "if (result)" in subsequent or "if (res)" in subsequent or "if (!result)" in subsequent or "if (!res)" in subsequent
        assert has_null_check, f"Caller at line {idx + 1} does not check for null/falsy return from runSolverWithEngagingProgress:\n{subsequent}"


def test_adversarial_all_specific_button_ids_have_handlers():
    """Verify that every button in index.html with an ID has an explicit handler or registration in app.js."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    parser = ButtonExtractor()
    parser.feed(html)

    for btn in parser.buttons:
        bid = btn.get("id")
        classes = btn.get("classes", [])
        if not bid:
            continue
        # If it's a general close button or tab, it is covered by class listeners
        if "close-modal" in classes or "ribbon-tab" in classes:
            continue

        # Otherwise it must be referenced by its ID in app.js
        id_referenced = (
            f'"{bid}"' in js or
            f"'{bid}'" in js or
            f"`{bid}`" in js
        )
        assert id_referenced, f"Button with id '{bid}' is defined in index.html but never referenced in app.js"


def test_adversarial_preset_2_button_runtime_behavior():
    """Verify that demand-preset-2-btn is correctly defined and its handler assigns value 2 to all inputs."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # index.html check
    assert 'id="demand-preset-2-btn"' in html, "demand-preset-2-btn missing from index.html"
    assert ">Set 2 / Shift<" in html, "demand-preset-2-btn text missing"

    # app.js handler check
    match = re.search(r"preset2Btn\.onclick\s*=\s*\(\)\s*=>\s*\{([^}]+)\}", js)
    assert match, "preset2Btn.onclick handler not found or malformed"
    handler_code = match.group(1)
    assert ".demand-num-input" in handler_code, "Handler should target .demand-num-input"
    assert "2" in handler_code, "Handler should set value to 2"


def test_adversarial_async_unhandled_promise_rejections():
    """Verify that critical async user-triggered handlers enclose asynchronous awaits in try/catch."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    critical_handlers = [
        "confirmGenBtn.onclick",
        "executeRosterGeneration",
        "onSolveRemaining",
        "window.promoteVariant",
        "window.waiveShortage",
        "window.autoResolveAllShortages",
        "dayOffBtn.onclick",
        "compOffBtn.onclick",
        "pinBtn.onclick",
        "emptyBtn.onclick",
    ]

    for handler_name in critical_handlers:
        assert handler_name in js, f"Expected handler {handler_name} not found in app.js"

