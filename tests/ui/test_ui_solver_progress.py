"""Empirical & Static Verification Suite for Solver Progress Modal & AI Thought Stream.

Validates:
1. Presence of accurate loading bar elements, expected time counters, and AI thought box in index.html.
2. onSolveRemaining invocation of runSolverWithEngagingProgress with { mode: 'solve_remaining' }.
3. AI thought feed configuration for both 'solve_remaining' and 'generate_new' modes.
4. CSS styling for dark terminal thought stream, smooth scroll, and animated thought entry.
"""
import re
import pytest


def test_solver_progress_modal_html_structure():
    """Verify index.html contains all required elements for accurate progress, expected time, and AI thoughts."""
    with open("src/ui/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    required_ids = [
        "modal-solver-progress",
        "solver-progress-pct",
        "solver-progress-fill",
        "solver-expected-time",
        "solver-time-remaining",
        "solver-elapsed-sec",
        "solver-baseline-sec",
        "solver-timeout-limit",
        "solver-thoughts-list",
        "solver-dynamic-status-text",
        "solver-stage-pill",
        "solver-modal-title",
        "solver-mode-badge"
    ]

    for elem_id in required_ids:
        assert f'id="{elem_id}"' in html, f"Missing required element id='{elem_id}' in index.html"


def test_on_solve_remaining_invokes_engaging_progress():
    """Verify onSolveRemaining wraps apiPost in runSolverWithEngagingProgress with mode: 'solve_remaining'."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Match onSolveRemaining definition
    m = re.search(r'const onSolveRemaining\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};', js)
    assert m, "onSolveRemaining handler not found in app.js"
    body = m.group(1)

    assert "runSolverWithEngagingProgress" in body, "onSolveRemaining does not call runSolverWithEngagingProgress"
    assert "solve_remaining" in body, "onSolveRemaining does not specify mode 'solve_remaining'"
    assert "apiPost" in body, "onSolveRemaining does not make API call"
    assert "loadSchedule()" in body, "onSolveRemaining does not reload schedule"


def test_ai_thought_scripts_present_in_solver_progress():
    """Verify runSolverWithEngagingProgress configures specialized thought streams for solve remaining and new plan."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    m = re.search(r'async function runSolverWithEngagingProgress[\s\S]*?\n\}\n\nasync function executeRosterGeneration', js)
    assert m, "runSolverWithEngagingProgress not found in app.js"
    body = m.group(0)

    # Verify both thought streams exist
    assert "solveRemainingThoughts" in body, "Missing solveRemainingThoughts script"
    assert "generateNewThoughts" in body, "Missing generateNewThoughts script"
    assert "appendThought" in body, "Missing appendThought stream function"
    assert "baselineSec" in body, "Missing dynamic baseline duration calculation"


def test_solver_progress_css_styles():
    """Verify styles.css includes styling for dark terminal thought stream, animations, and custom scrollbar."""
    with open("src/ui/styles.css", "r", encoding="utf-8") as f:
        css = f.read()

    assert ".solver-ai-thought-box" in css, "Missing .solver-ai-thought-box in styles.css"
    assert "#solver-thoughts-list::-webkit-scrollbar" in css, "Missing custom scrollbar in styles.css"
    assert "@keyframes thought-fade-in" in css, "Missing thought-fade-in animation in styles.css"
    assert ".solver-progress-bar" in css, "Missing .solver-progress-bar in styles.css"


def test_solver_progress_elapsed_ms_initialization_order():
    """Verify elapsedMs is declared before appendThought is called to prevent TDZ ReferenceError."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    m = re.search(r'async function runSolverWithEngagingProgress[\s\S]*?\n\}\n\nasync function executeRosterGeneration', js)
    assert m, "runSolverWithEngagingProgress not found in app.js"
    body = m.group(0)

    elapsed_idx = body.find("let elapsedMs = 0;")
    append_call_idx = body.find("appendThought(thoughtScript[0]);")

    assert elapsed_idx != -1, "let elapsedMs = 0; declaration not found"
    assert append_call_idx != -1, "appendThought(thoughtScript[0]) call not found"
    assert elapsed_idx < append_call_idx, (
        f"Temporal Dead Zone error: elapsedMs declared at index {elapsed_idx} after appendThought call at {append_call_idx}"
    )


def test_on_solve_remaining_guards_against_missing_active_plan():
    """Verify onSolveRemaining displays a helpful alert when no active plan is selected."""
    with open("src/ui/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    m = re.search(r'const onSolveRemaining\s*=\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\n\s*\};', js)
    assert m, "onSolveRemaining handler not found"
    body = m.group(1)

    assert "!state.activePlanId" in body, "Missing activePlanId check"
    assert "alert(" in body, "Missing user alert when activePlanId is falsy"

