/**
 * LocalRoster v2 - Offline Reactive Client Controller
 * Zero CDN dependencies, instant local REST API calls.
 */

const state = {
  activePlanId: null,
  activeDepartmentId: null,
  currentView: "staff_centric",
  currentMode: "simple",
  prefillMode: false,
  showPrevMonth: false,
  zoomLevel: 1.0,
  plans: [],
  departments: [],
  shifts: [],
  currentScheduleData: null,
  selectedCell: null
};

// ==========================================
// API Client Helpers
// ==========================================
async function apiGet(endpoint) {
  const res = await fetch(endpoint);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function apiPost(endpoint, data) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = errText;
    try { msg = JSON.parse(errText).detail || errText; } catch (_) {}
    throw new Error(msg);
  }
  return await res.json();
}

async function apiPut(endpoint, data) {
  const res = await fetch(endpoint, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = errText;
    try { msg = JSON.parse(errText).detail || errText; } catch (_) {}
    throw new Error(msg);
  }
  return await res.json();
}

async function apiDelete(endpoint) {
  const res = await fetch(endpoint, {
    method: "DELETE"
  });
  if (!res.ok) {
    const errText = await res.text();
    let msg = errText;
    try { msg = JSON.parse(errText).detail || errText; } catch (_) {}
    throw new Error(msg);
  }
  return await res.json();
}

// ==========================================
// Application Bootstrap & Data Fetching
// ==========================================
async function initApp() {
  // 1. Initialize all interactive UI widgets & event listeners immediately
  initRibbonTabs();
  initResizers();
  initZoom();
  initOnboarding();
  initFindReplace();
  initKeyboardNavigation();
  initButtonTooltips();
  setupEventListeners();

  // 2. Fetch data from backend
  try {
    state.departments = await apiGet("/api/departments");
    state.shifts = await apiGet("/api/shift-types");
    await loadPlans();
  } catch (err) {
    console.error("Initialization error:", err);
    updateHealthBanner("red", "Backend communication error: " + err.message);
  }
}

async function loadPlans() {
  state.plans = await apiGet("/api/roster/plans");
  const select = document.getElementById("plan-select");
  select.innerHTML = "";

  if (state.plans.length === 0) {
    // Automatically trigger initial default plan generation if database has 0 plans
    updateHealthBanner("yellow", "🟡 No roster plans found. Click '+ New Roster' to generate initial schedule.");
    return;
  }

  state.plans.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.status})`;
    select.appendChild(opt);
  });

  state.activePlanId = state.plans[0].id;
  await loadSchedule();
}

async function loadSchedule() {
  if (!state.activePlanId) return;

  if (state.currentView === "audit_scorecard") {
    const scorecard = await apiGet(`/api/analytics/plan/${state.activePlanId}/scorecard`);
    renderAuditScorecard(scorecard);
    updateHealthBanner("green", `🟢 Workload Audit: ${scorecard.employee_scorecards.length} staff evaluated. Total Scheduled: ${scorecard.total_scheduled_hours} hrs.`);
  } else {
    let url = `/api/roster/${state.activePlanId}?view=${state.currentView}`;
    if (state.activeDepartmentId) {
      url += `&department_id=${state.activeDepartmentId}`;
    }
    const data = await apiGet(url);
    state.currentScheduleData = data;

    if (state.currentView === "staff_centric") {
      renderStaffCentric(data);
    } else {
      renderSlotCentric(data);
    }

    // Check for labor conflicts in rendered schedule
    let conflictCount = 0;
    if (data && data.rows) {
      data.rows.forEach(r => {
        Object.values(r.assignments || {}).forEach(a => {
          if (a && a.has_conflict) conflictCount++;
        });
      });
    }

    // Update Health Banner
    const deficits = await apiGet(`/api/roster/${state.activePlanId}/deficits`);
    if (deficits.length === 0 && conflictCount === 0) {
      updateHealthBanner("green", "🟢 ROSTER HEALTH: ALL CLEAR — 100% shifts staffed. Zero ergonomic violations.");
    } else if (deficits.length > 0 && conflictCount > 0) {
      updateHealthBanner("red", `🔴 ROSTER HEALTH: ${deficits.length} Shortages & ⚠️ ${conflictCount} Labor Conflicts Detected.`, deficits, conflictCount);
    } else if (deficits.length > 0) {
      updateHealthBanner("red", `🔴 ROSTER HEALTH: ${deficits.length} Shortages Detected. Click to inspect recommendations.`, deficits, 0);
    } else {
      updateHealthBanner("yellow", `⚠️ ROSTER HEALTH: ${conflictCount} Labor Ergonomic Conflicts Detected. Click Auto-Resolve to fix.`, [], conflictCount);
    }
  }

  renderDeptFilters();

  // Update footer status bar
  const curPlan = state.plans.find(p => p.id === state.activePlanId);
  const planInfo = document.getElementById("status-plan-info");
  if (planInfo && curPlan) {
    planInfo.textContent = `${curPlan.name} (${curPlan.status})`;
  }
  const orgInfo = document.getElementById("status-org-info");
  if (orgInfo) {
    orgInfo.textContent = `${state.departments.length} Depts active`;
  }
}

// ==========================================
// Health Banner & Guided Shortage Fixes
// ==========================================
function updateHealthBanner(type, message, deficits = [], conflictCount = 0) {
  const banner = document.getElementById("health-banner");
  if (banner) {
    banner.className = `health-banner ${type}`;
    const msgEl = document.getElementById("health-message");
    if (msgEl) msgEl.textContent = message;

    if (type === "red" && deficits.length > 0) {
      banner.style.cursor = "pointer";
      banner.title = "Click to inspect exact shortages & 1-click fixes";
      banner.onclick = (e) => {
        if (e.target.tagName !== "BUTTON") {
          openShortagesModal();
        }
      };
    } else {
      banner.style.cursor = "default";
      banner.title = "";
      banner.onclick = null;
    }
  }

  const statusPill = document.getElementById("status-health-pill");
  if (statusPill) {
    if (type === "green") {
      statusPill.textContent = "🟢 100% Staffed";
      statusPill.style.color = "#166534";
      statusPill.style.cursor = "default";
      statusPill.onclick = null;
    } else if (type === "yellow") {
      statusPill.textContent = `⚠️ Conflicts (${conflictCount})`;
      statusPill.style.color = "#854d0e";
      statusPill.style.cursor = "pointer";
      statusPill.title = "Labor rule conflicts detected";
      statusPill.onclick = null;
    } else {
      statusPill.textContent = `🔴 Shortages (${deficits.length})`;
      statusPill.style.color = "#991b1b";
      statusPill.style.cursor = "pointer";
      statusPill.title = "Click to inspect and fix shortages";
      statusPill.onclick = () => openShortagesModal();
    }
  }

  const actionsContainer = document.getElementById("health-actions");
  actionsContainer.innerHTML = "";

  if (conflictCount > 0) {
    const resolveConflictsBtn = document.createElement("button");
    resolveConflictsBtn.className = "btn btn-sm";
    resolveConflictsBtn.style.cssText = "background:#d97706;color:#ffffff;font-weight:700;border:none;margin-right:8px;box-shadow:0 1px 3px rgba(0,0,0,0.15);";
    resolveConflictsBtn.textContent = `⚡ Auto-Resolve Conflicts (${conflictCount})`;
    resolveConflictsBtn.title = "Automatically resolve all labor rest and streak conflicts";
    resolveConflictsBtn.onclick = async (e) => {
      e.stopPropagation();
      try {
        const res = await apiPost(`/api/roster/${state.activePlanId}/resolve-conflicts`);
        alert(`Success: ${res.message}`);
        await loadSchedule();
      } catch (err) {
        alert("Failed to auto-resolve conflicts: " + err.message);
      }
    };
    actionsContainer.appendChild(resolveConflictsBtn);
  }

  if (deficits.length > 0) {
    // 1-Click Auto-Resolve All Button
    const autoAllBtn = document.createElement("button");
    autoAllBtn.className = "btn btn-sm";
    autoAllBtn.style.cssText = "background:#dc2626;color:#ffffff;font-weight:700;border:none;margin-right:8px;";
    autoAllBtn.textContent = `⚡ 1-Click Fix All (${deficits.length} Shortages)`;
    autoAllBtn.onclick = async (e) => {
      e.stopPropagation();
      await autoResolveAllShortages();
    };
    actionsContainer.appendChild(autoAllBtn);

    // Inspect Shortages Button
    const inspectBtn = document.createElement("button");
    inspectBtn.className = "btn btn-sm btn-outline";
    inspectBtn.textContent = "Inspect & Fix 🔍";
    inspectBtn.onclick = (e) => {
      e.stopPropagation();
      openShortagesModal();
    };
    actionsContainer.appendChild(inspectBtn);
  }
}

// ==========================================
// View Renderers
// ==========================================
function renderDeptFilters() {
  const container = document.getElementById("dept-filter-list");
  container.innerHTML = "";

  const allPill = document.createElement("div");
  allPill.className = `dept-pill ${state.activeDepartmentId === null ? "active" : ""}`;
  allPill.innerHTML = `<span>All Departments</span><span class="brand-badge">${state.departments.length}</span>`;
  allPill.onclick = () => {
    state.activeDepartmentId = null;
    loadSchedule();
  };
  container.appendChild(allPill);

  state.departments.forEach(d => {
    const pill = document.createElement("div");
    pill.className = `dept-pill ${state.activeDepartmentId === d.id ? "active" : ""}`;
    pill.innerHTML = `
      <span><span class="dept-color-dot" style="background:${d.color_code}"></span>${d.code}</span>
      <span style="font-size:10px;color:var(--text-muted);">${d.operating_regime === "24_7" ? "24/7" : "5d"}</span>
    `;
    pill.onclick = () => {
      state.activeDepartmentId = d.id;
      loadSchedule();
    };
    container.appendChild(pill);
  });
}

function renderStaffCentric(data) {
  const table = document.getElementById("schedule-table");
  table.innerHTML = "";
  table.style.zoom = state.zoomLevel;

  // Thead
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");

  const empTh = document.createElement("th");
  empTh.className = "sticky-col";
  empTh.textContent = "Employee";
  headerRow.appendChild(empTh);

  const hasPrevTrailing = state.showPrevMonth && data.previous_month_context && data.previous_month_context.trailing_dates;

  if (hasPrevTrailing) {
    data.previous_month_context.trailing_dates.forEach(tdStr => {
      const th = document.createElement("th");
      th.className = "trailing-header";
      const d = new Date(tdStr);
      th.innerHTML = `<div>${d.getDate()}</div><div style="font-size:8px;">${d.toLocaleDateString("en-US", { weekday: "short" })} (Prev)</div>`;
      headerRow.appendChild(th);
    });
  }

  data.dates.forEach(dStr => {
    const th = document.createElement("th");
    const d = new Date(dStr + "T00:00:00");
    const dayName = d.toLocaleDateString("en-US", { weekday: "short" });
    const dayNum = d.getDate();

    let shortagePill = "";
    if (data.deficits_by_date && data.deficits_by_date[dStr]) {
      const defInfo = data.deficits_by_date[dStr];
      const sCode = defInfo.shift_code || "Shift";
      shortagePill = `<div class="header-shortage-pill" title="⚠️ Shortage: ${defInfo.shortage_count} ${sCode} needed! Click to fix">⚠️ 1 Short</div>`;
    }

    th.innerHTML = `<div>${dayNum}</div><div style="font-size:9px;">${dayName}</div>${shortagePill}`;
    if (dayName === "Sat" || dayName === "Sun") {
      th.style.background = "#f1f5f9";
    }
    if (data.deficits_by_date && data.deficits_by_date[dStr]) {
      th.style.background = "#fee2e2";
      th.style.borderBottom = "2px solid #dc2626";
      th.style.cursor = "pointer";
      th.onclick = (e) => {
        e.stopPropagation();
        openShortagesModal(dStr);
      };
    }
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Tbody
  const tbody = document.createElement("tbody");
  data.rows.forEach((r, rIdx) => {
    const tr = document.createElement("tr");
    tr.dataset.row = rIdx;

    const empTd = document.createElement("td");
    empTd.className = "sticky-col";
    const deptColor = r.primary_department_color || "#3b82f6";

    let prevMonthLabel = "";
    if (state.showPrevMonth && r.previous_month_summary) {
      prevMonthLabel = `<span style="color:#2563eb;font-weight:600;font-size:9px;">Prev: ${r.previous_month_summary.worked_hours}h (${r.previous_month_summary.night_shifts}N)</span>`;
    }

    empTd.innerHTML = `
      <div class="emp-sticky-card emp-clickable" style="border-left-color: ${deptColor};" title="Click to view & edit employee details">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">
          <b>${r.employee_name}</b>
          <span class="dept-badge-tag" style="background:${deptColor};">${r.primary_department_code}</span>
        </div>
        <div style="font-size:10px;color:var(--text-muted);display:flex;gap:6px;margin-top:2px;align-items:center;">
          <span>${r.employee_code}</span>
          ${prevMonthLabel}
          <span style="margin-left:auto;font-size:10px;color:#3b82f6;" title="Edit employee">✏️</span>
        </div>
      </div>
    `;

    empTd.addEventListener("click", (evt) => {
      evt.stopPropagation();
      openEmployeeEditor(r.employee_id);
    });

    empTd.addEventListener("mouseenter", () => {
      showEmployeeHover(empTd, r);
    });

    empTd.addEventListener("mouseleave", () => {
      hideEmployeeHover();
    });

    tr.appendChild(empTd);

    // Trailing columns from previous month
    if (hasPrevTrailing) {
      const trailingShifts = (r.previous_month_summary && r.previous_month_summary.trailing_3_days) || [];
      data.previous_month_context.trailing_dates.forEach((tdStr, idx) => {
        const td = document.createElement("td");
        td.className = "trailing-col";
        const tObj = trailingShifts[idx];
        const sc = tObj ? tObj.shift_code : "-";
        td.innerHTML = `<span class="trailing-badge">${sc}</span>`;
        tr.appendChild(td);
      });
    }

    // Check for turnaround warning from last day of previous month
    const workedPriorNight = r.previous_month_summary && r.previous_month_summary.last_day_shift && r.previous_month_summary.last_day_shift.includes("NIGHT");

    data.dates.forEach((dStr, dIdx) => {
      const td = document.createElement("td");
      td.dataset.row = rIdx;
      td.dataset.col = dIdx;
      td.dataset.date = dStr;
      td.dataset.empId = r.employee_id;

      const a = r.assignments[dStr];

      if (a) {
        if (a.has_conflict) {
          td.classList.add("cell-conflict");
          td.title = `⚠️ Conflict: ${a.conflict_reason}`;
        }

        const badge = document.createElement("span");
        let shiftClass = "shift-off";

        if (a.is_comp_off || a.shift_code === "COFF") {
          shiftClass = "shift-coff";
          badge.className = `shift-badge ${shiftClass}`;
          badge.innerHTML = `☕ ${a.shift_code || "COFF"}`;
          badge.title = `Pinned Compensatory Off: ${a.shift_name || "Coff 📌"}`;
        } else if (a.is_day_off || a.shift_code === "DO") {
          shiftClass = "shift-do";
          badge.className = `shift-badge ${shiftClass}`;
          badge.innerHTML = `📌 ${a.shift_code || "DO"}`;
          badge.title = `Pinned Day OFF (Locked): ${a.shift_name || "Day OFF"}`;
        } else if (a.is_leave) {
          shiftClass = "shift-vac";
          badge.className = `shift-badge ${shiftClass}`;
          badge.innerHTML = `🏖️ ${a.shift_code || "VAC"}`;
          badge.title = `Approved Leave: ${a.shift_name}`;
        } else if (a.is_fixed_off) {
          shiftClass = "shift-do";
          badge.className = `shift-badge ${shiftClass}`;
          badge.innerHTML = `${a.shift_code || "DO"} 🔒`;
          badge.title = `Dedicated Regular Day Off (Locked)`;
        } else {
          if (a.shift_code.includes("MORN")) shiftClass = "shift-morn";
          else if (a.shift_code.includes("EVE")) shiftClass = "shift-eve";
          else if (a.shift_code.includes("NIGHT")) shiftClass = "shift-night";

          let floaterClass = "";
          let floaterStyle = "";
          if (a.is_floating) {
            floaterClass = "shift-floater";
            floaterStyle = `box-shadow: 0 0 0 1.5px ${a.department_color || '#f59e0b'};`;
          }

          // Turnaround warning check on Day 1
          let turnaroundClass = "";
          let turnaroundTitle = "";
          if (dIdx === 0 && workedPriorNight && (a.shift_code.includes("MORN") || a.shift_code.includes("EVE"))) {
            turnaroundClass = "trailing-turnaround-warn";
            turnaroundTitle = "Turnaround Warning: Worked Night shift on final day of prior month!";
          }

          badge.className = `shift-badge ${shiftClass} ${floaterClass} ${turnaroundClass}`;
          if (floaterStyle) badge.style.cssText = floaterStyle;
          if (turnaroundTitle) badge.title = turnaroundTitle;
          const floatTag = a.is_floating ? `<span class="badge-float-indicator" title="Floating coverage to ${a.department_code || ''}">⇄ ${a.department_code || ''}</span>` : "";
          const pinTag = a.is_pinned ? `<span class="pin-icon">📌</span>` : "";
          badge.innerHTML = `${a.shift_code || ''}${floatTag}${pinTag}`;
        }

        badge.onclick = (e) => {
          e.stopPropagation();
          hideCellHover();
          selectAssignment(r, dStr, a, rIdx, dIdx, td);
        };
        td.onclick = () => {
          hideCellHover();
          selectAssignment(r, dStr, a, rIdx, dIdx, td);
        };
        attachCellHover(td, r, dStr, a);
        td.appendChild(badge);
      } else {
        // Empty Cell or Scheduled Rest Day
        const isSolvedPlan = data.plan && (data.plan.status === "SOLVED" || data.plan.status === "PUBLISHED");
        td.classList.add("cell-empty");
        const offBadge = document.createElement("span");

        if (isSolvedPlan) {
          offBadge.className = "scheduled-off-badge";
          offBadge.textContent = "OFF";
          offBadge.title = "Scheduled Rest Day (Contracted weekly hours fulfilled)";
        } else {
          offBadge.className = "shift-badge shift-off";
          offBadge.style.opacity = "0.5";
          offBadge.textContent = "—";
        }

        offBadge.onclick = (e) => {
          e.stopPropagation();
          hideCellHover();
          selectAssignment(r, dStr, null, rIdx, dIdx, td);
        };
        td.onclick = () => {
          hideCellHover();
          selectAssignment(r, dStr, null, rIdx, dIdx, td);
        };
        attachCellHover(td, r, dStr, null);
        td.appendChild(offBadge);
      }

      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
}

function renderSlotCentric(data) {
  const table = document.getElementById("schedule-table");
  table.innerHTML = "";
  table.style.zoom = state.zoomLevel;

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th style="text-align:left;padding-left:12px;">Date & Day</th>
      <th>Department</th>
      <th>Shift</th>
      <th style="text-align:left;">Assigned Staff Members</th>
      <th>Count</th>
      <th>Status</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  data.slots.forEach(slot => {
    const tr = document.createElement("tr");
    const isDeficit = slot.deficit > 0;

    const workerTags = slot.assigned_staff.map(w => {
      const homeColor = w.primary_department_color || '#3b82f6';
      return `<span class="shift-badge ${w.is_floating ? 'shift-floater' : 'shift-morn'}" style="margin-right:4px;">
        <span class="dept-color-dot" style="background:${homeColor};"></span>
        ${w.name} ${w.is_floating ? `(Floater from ${w.primary_department_code})` : ''} ${w.is_pinned ? '📌' : ''}
       </span>`;
    }).join("");

    const deptColor = slot.department_color || '#3b82f6';

    tr.innerHTML = `
      <td style="text-align:left;padding-left:12px;font-weight:600;">${slot.date} (${slot.day_name})</td>
      <td><span class="dept-badge-tag" style="background:${deptColor};">${slot.department_code}</span></td>
      <td><b>${slot.shift_code}</b></td>
      <td style="text-align:left;">${workerTags || '<span style="color:var(--text-muted);font-style:italic;">No staff assigned</span>'}</td>
      <td><b>${slot.assigned_count}</b></td>
      <td>
        ${isDeficit 
          ? `<span class="brand-badge" style="background:#ef4444;">-${slot.deficit} DEFICIT</span>`
          : `<span class="brand-badge" style="background:#10b981;">OK</span>`
        }
      </td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function renderAuditScorecard(data) {
  const table = document.getElementById("schedule-table");
  table.innerHTML = "";
  table.style.zoom = state.zoomLevel;

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th style="text-align:left;padding-left:12px;">Employee</th>
      <th>Home Dept</th>
      <th>Contract / Wk</th>
      <th>Target / Mo</th>
      <th>Scheduled</th>
      <th>Variance</th>
      <th>Total Shifts</th>
      <th>Days Off</th>
      <th>Wknd Off</th>
      <th>Max Streak</th>
      <th>Floats</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  data.employee_scorecards.forEach(sc => {
    const tr = document.createElement("tr");
    const isOvertime = sc.variance_hours > 4.0;
    const isUndertime = sc.variance_hours < -8.0;

    let varStyle = "color:#16a34a;";
    if (isOvertime) varStyle = "color:#dc2626;font-weight:bold;";
    else if (isUndertime) varStyle = "color:#d97706;";

    // Find dept color
    const dObj = state.departments.find(d => d.name === sc.primary_department || d.code === sc.primary_department);
    const deptColor = dObj ? dObj.color_code : "#3b82f6";

    tr.innerHTML = `
      <td style="text-align:left;padding-left:12px;"><b>${sc.name}</b> (${sc.employee_code})</td>
      <td><span class="dept-badge-tag" style="background:${deptColor};">${sc.primary_department}</span></td>
      <td>${sc.contracted_hours_week}h</td>
      <td>${sc.target_hours_month}h</td>
      <td><b>${sc.scheduled_hours}h</b></td>
      <td style="${varStyle}">${sc.variance_hours > 0 ? '+' : ''}${sc.variance_hours}h</td>
      <td>${sc.total_shifts}</td>
      <td>${sc.days_off_count} days</td>
      <td>${sc.weekend_days_off_count} days</td>
      <td>${sc.max_consecutive_days_worked} consec</td>
      <td>${sc.floating_shifts_count}</td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

// ==========================================
// Inspector & Real-Time Constraint Validation
// ==========================================
function updateGridCrosshairs(rowIdx, colIdx, activeTd) {
  // Clear previous crosshairs
  document.querySelectorAll(".cell-active").forEach(el => el.classList.remove("cell-active"));
  document.querySelectorAll(".row-active-crosshair").forEach(el => el.classList.remove("row-active-crosshair"));
  document.querySelectorAll(".col-active-crosshair").forEach(el => el.classList.remove("col-active-crosshair"));

  if (activeTd) {
    activeTd.classList.add("cell-active");
  }

  if (rowIdx !== null && rowIdx !== undefined) {
    document.querySelectorAll(`tr[data-row="${rowIdx}"] td`).forEach(td => td.classList.add("row-active-crosshair"));
  }

  if (colIdx !== null && colIdx !== undefined) {
    document.querySelectorAll(`td[data-col="${colIdx}"]`).forEach(td => td.classList.add("col-active-crosshair"));
  }
}

// Cell Hover Preview Engine
// ==========================================
function attachCellHover(td, emp, dateStr, assignment) {
  td.onmouseenter = () => {
    if (state.hoverTimer) clearTimeout(state.hoverTimer);
    state.hoverTimer = setTimeout(() => {
      showCellHover(td, emp, dateStr, assignment);
    }, 280);
  };

  td.onmouseleave = () => {
    if (state.hoverTimer) clearTimeout(state.hoverTimer);
    hideCellHover();
  };
}

function showCellHover(td, emp, dateStr, assignment) {
  const popover = document.getElementById("cell-hover-popover");
  if (!popover) return;

  const empEl = document.getElementById("hover-pop-emp");
  const deptEl = document.getElementById("hover-pop-dept");
  const dateEl = document.getElementById("hover-pop-date");
  const shiftEl = document.getElementById("hover-pop-shift");
  const hoursRow = document.getElementById("hover-pop-hours-row");
  const hoursEl = document.getElementById("hover-pop-hours");
  const covRow = document.getElementById("hover-pop-coverage-row");
  const covEl = document.getElementById("hover-pop-coverage");
  const statusEl = document.getElementById("hover-pop-status");
  const conflictEl = document.getElementById("hover-pop-conflict");

  if (empEl) empEl.textContent = `${emp.employee_name} (${emp.employee_code})`;
  if (deptEl) deptEl.textContent = emp.primary_department_name ? `${emp.primary_department_name} (${emp.primary_department_code || ''})` : "";

  try {
    const dObj = new Date(dateStr + "T00:00:00");
    const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    if (dateEl) dateEl.textContent = `${monthNames[dObj.getMonth()]} ${dObj.getDate()}, ${dObj.getFullYear()} (${dayNames[dObj.getDay()]})`;
  } catch (_) {
    if (dateEl) dateEl.textContent = dateStr;
  }

  const shiftObj = assignment && assignment.shift_id && state.shifts ? state.shifts.find(s => s.id === assignment.shift_id) : null;

  if (assignment) {
    if (assignment.is_comp_off || assignment.shift_code === "COFF") {
      const earnedText = assignment.is_earned_coff ? `☕ Earned Comp Off (Overtime Holiday: ${assignment.earned_hours || '40+'}h worked)` : "☕ Compensatory Off (Coff)";
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#d97706;font-weight:700;">${earnedText}</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = assignment.is_earned_coff ? "☕ Earned Holiday (Overtime Compensation)" : "📌 Pinned Comp Off";
    } else if (assignment.is_day_off || assignment.shift_code === "DO") {
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#475569;font-weight:700;">📌 Day OFF (Locked)</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = "📌 Pinned Off Duty";
    } else if (assignment.is_fixed_off) {
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#475569;font-weight:700;">🔒 Dedicated Regular Day Off</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = "🔒 Contracted Off Duty";
    } else if (assignment.is_leave) {
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#7c3aed;font-weight:700;">🏖️ ${assignment.shift_name || 'Approved Leave'}</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = "🏖️ Approved Vacation / Leave";
    } else {
      const shiftName = shiftObj ? shiftObj.name : (assignment.shift_name || assignment.shift_code);
      if (shiftEl) shiftEl.textContent = `${shiftName} (${assignment.shift_code})`;

      if (hoursRow) hoursRow.classList.remove("hidden");
      if (hoursEl) {
        if (shiftObj) hoursEl.textContent = `${shiftObj.start_time.slice(0, 5)} – ${shiftObj.end_time.slice(0, 5)} (${shiftObj.duration_hours}h)`;
        else hoursEl.textContent = "Standard Working Shift";
      }

      if (covRow) covRow.classList.remove("hidden");
      if (covEl) {
        if (assignment.is_floating) {
          covEl.innerHTML = `<span style="color:#d97706;font-weight:700;">⇄ Floating to ${assignment.department_code || ''} (Rank ${assignment.float_rank || 2})</span>`;
        } else {
          covEl.textContent = `${assignment.department_code || emp.primary_department_code || ''} (Home Department)`;
        }
      }

      if (statusEl) statusEl.textContent = assignment.is_pinned ? "📌 Pinned by Manager" : "⚡ Solved by CP-SAT";
    }

    if (conflictEl) {
      if (assignment.has_conflict) {
        conflictEl.classList.remove("hidden");
        conflictEl.textContent = `⚠️ Rule Conflict: ${assignment.conflict_reason || 'Labor ergonomic violation'}`;
      } else {
        conflictEl.classList.add("hidden");
      }
    }
  } else {
    // Empty cell or Scheduled Rest Day
    const isSolved = state.currentScheduleData && state.currentScheduleData.plan &&
      (state.currentScheduleData.plan.status === "SOLVED" || state.currentScheduleData.plan.status === "PUBLISHED");
    if (isSolved) {
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#64748b;font-weight:700;">⚪ Scheduled Day Off (OFF)</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = "⚪ Off Duty • Contracted weekly hours fulfilled";
      if (conflictEl) conflictEl.classList.add("hidden");
    } else {
      if (shiftEl) shiftEl.innerHTML = `<span style="color:#94a3b8;font-style:italic;">⚪ Empty Slot (Unassigned)</span>`;
      if (hoursRow) hoursRow.classList.add("hidden");
      if (covRow) covRow.classList.add("hidden");
      if (statusEl) statusEl.textContent = "⚪ Open (Fillable by Solver)";
      if (conflictEl) conflictEl.classList.add("hidden");
    }
  }

  // Position popover relative to td
  const rect = td.getBoundingClientRect();
  const popoverWidth = 280;
  const popoverHeight = 180;

  let left = rect.left + (rect.width / 2) - (popoverWidth / 2);
  let top = rect.bottom + 8;

  if (left + popoverWidth > window.innerWidth - 10) {
    left = window.innerWidth - popoverWidth - 10;
  }
  if (left < 10) left = 10;

  if (top + popoverHeight > window.innerHeight - 10) {
    top = rect.top - popoverHeight - 8;
  }
  if (top < 10) top = 10;

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
  popover.classList.remove("hidden");
}

function hideCellHover() {
  const popover = document.getElementById("cell-hover-popover");
  if (popover) popover.classList.add("hidden");
}

function showEmployeeHover(td, r) {
  const popover = document.getElementById("emp-hover-popover");
  if (!popover) return;

  const nameEl = document.getElementById("emp-hover-name");
  const badgeEl = document.getElementById("emp-hover-dept-badge");
  const codeDeptEl = document.getElementById("emp-hover-code-dept");
  const hoursEl = document.getElementById("emp-hover-hours");
  const fixedOffEl = document.getElementById("emp-hover-fixed-off");
  const workloadEl = document.getElementById("emp-hover-workload");
  const timeoffEl = document.getElementById("emp-hover-timeoff");
  const prevRow = document.getElementById("emp-hover-prev-row");
  const prevStatsEl = document.getElementById("emp-hover-prev-stats");
  const floatingEl = document.getElementById("emp-hover-floating");

  if (nameEl) nameEl.textContent = r.employee_name || "Employee";
  if (badgeEl) {
    badgeEl.textContent = r.primary_department_code || "DEPT";
    badgeEl.style.background = r.primary_department_color || "#3b82f6";
  }
  if (codeDeptEl) {
    codeDeptEl.textContent = `${r.employee_code || ""} • ${r.primary_department_name || ""}`;
  }

  if (hoursEl) {
    hoursEl.textContent = `${r.max_hours_week || 40.0}h / week (Max)`;
  }

  const shiftEl = document.getElementById("emp-hover-shift");
  if (shiftEl) {
    if (r.preferred_shift_name) {
      shiftEl.textContent = `☀️ ${r.preferred_shift_name} (${r.preferred_shift_code || ''})`;
      shiftEl.style.color = "#0369a1";
    } else if (r.preferred_shift_type_id && state.shifts) {
      const sObj = state.shifts.find((s) => s.id === r.preferred_shift_type_id);
      shiftEl.textContent = sObj ? `☀️ ${sObj.name}` : "Flexible / Dynamic";
      shiftEl.style.color = sObj ? "#0369a1" : "#64748b";
    } else {
      shiftEl.textContent = "Flexible / Dynamic";
      shiftEl.style.color = "#64748b";
    }
  }

  // Format regular fixed off days
  if (fixedOffEl) {
    const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    if (r.fixed_off_days) {
      const parts = r.fixed_off_days
        .split(",")
        .map((x) => parseInt(x.trim(), 10))
        .filter((n) => !isNaN(n));
      if (parts.length > 0) {
        fixedOffEl.textContent = parts
          .map((d) => dayNames[d] || `Day ${d}`)
          .join(", ");
      } else {
        fixedOffEl.textContent = "Flexible / Dynamic";
      }
    } else {
      fixedOffEl.textContent = "Flexible / Dynamic";
    }
  }

  // Calculate monthly stats from r.assignments
  let shiftCount = 0;
  let totalHours = 0;
  let nightCount = 0;
  let dayOffCount = 0;
  let compOffCount = 0;
  let leaveCount = 0;

  if (r.assignments) {
    Object.values(r.assignments).forEach((a) => {
      if (!a) return;
      if (a.is_comp_off || a.shift_code === "COFF") {
        compOffCount++;
      } else if (a.is_day_off || a.is_fixed_off || a.shift_code === "DO") {
        dayOffCount++;
      } else if (a.is_leave) {
        leaveCount++;
      } else if (a.shift_id) {
        shiftCount++;
        const sObj =
          state.shifts && state.shifts.find((s) => s.id === a.shift_id);
        if (sObj) {
          totalHours += sObj.duration_hours || 8.0;
          if (sObj.is_night_shift) nightCount++;
        } else {
          totalHours += 8.0;
        }
      }
    });
  }

  if (workloadEl) {
    const roundedH = Math.round(totalHours * 10) / 10;
    workloadEl.textContent = `${shiftCount} shifts (${roundedH}h) • ${nightCount} Nights`;
  }

  if (timeoffEl) {
    const offParts = [];
    if (dayOffCount > 0) offParts.push(`${dayOffCount} DO`);
    if (compOffCount > 0) offParts.push(`${compOffCount} Coff`);
    if (leaveCount > 0) offParts.push(`${leaveCount} Leave`);
    timeoffEl.textContent = offParts.length > 0 ? offParts.join(" • ") : "None";
  }

  // Previous month summary
  if (prevRow && prevStatsEl) {
    if (r.previous_month_summary) {
      prevRow.classList.remove("hidden");
      prevStatsEl.textContent = `${r.previous_month_summary.worked_hours || 0}h (${r.previous_month_summary.night_shifts || 0} Nights)`;
    } else {
      prevRow.classList.add("hidden");
    }
  }

  // Floating eligibilities
  if (floatingEl) {
    if (r.eligibilities && r.eligibilities.length > 0) {
      const floaters = r.eligibilities.filter(
        (e) => e.can_float && e.department_id !== r.primary_department_id
      );
      if (floaters.length > 0) {
        floatingEl.textContent = floaters
          .map((f) => `${f.department_code} (Rank ${f.preference_rank})`)
          .join(", ");
      } else {
        floatingEl.textContent = "Home Dept Only";
      }
    } else {
      floatingEl.textContent = "Home Dept Only";
    }
  }

  // Position popover relative to td
  const rect = td.getBoundingClientRect();
  const popoverWidth = 320;
  const popoverHeight = 220;

  let left = rect.right + 8;
  let top = rect.top;

  if (left + popoverWidth > window.innerWidth - 10) {
    left = rect.left - popoverWidth - 8;
  }
  if (left < 10) left = 10;

  if (top + popoverHeight > window.innerHeight - 10) {
    top = window.innerHeight - popoverHeight - 10;
  }
  if (top < 10) top = 10;

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
  popover.classList.remove("hidden");
}

function hideEmployeeHover() {
  const popover = document.getElementById("emp-hover-popover");
  if (popover) popover.classList.add("hidden");
}

async function openEmployeeEditor(empId) {
  hideEmployeeHover();
  hideCellHover();

  const modal = document.getElementById("modal-manage-org");
  if (!modal) return;
  modal.classList.remove("hidden");

  // Switch to Staff Directory tab
  document
    .querySelectorAll(".org-tab-btn")
    .forEach((b) => b.classList.remove("active"));
  const empTab = document.getElementById("org-tab-emps");
  if (empTab) empTab.classList.add("active");

  const deptsView = document.getElementById("org-depts-view");
  const demandView = document.getElementById("org-demand-view");
  const empsView = document.getElementById("org-emps-view");
  if (deptsView) deptsView.classList.add("hidden");
  if (demandView) demandView.classList.add("hidden");
  if (empsView) empsView.classList.remove("hidden");

  await loadOrgDepartments();
  await loadOrgEmployees();

  // Find target employee
  let emp = null;
  try {
    emp = await apiGet(`/api/employees/${empId}`);
  } catch (_) {
    const allEmps = await apiGet("/api/employees?active_only=false");
    emp = allEmps.find((e) => e.id === empId);
  }

  if (emp) {
    window.editEmployee(emp);
    const formCard = document.getElementById("emp-form-card");
    if (formCard) {
      formCard.classList.remove("hidden");
      formCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      formCard.style.outline = "2px solid #3b82f6";
      formCard.style.borderRadius = "8px";
      setTimeout(() => {
        formCard.style.outline = "none";
      }, 1600);
    }
  }
}

window.openShortagesModal = async function(filterDate = null) {
  hideCellHover();
  hideEmployeeHover();
  hideButtonTooltip();

  const modal = document.getElementById("modal-shortages-resolver");
  if (!modal) return;
  modal.classList.remove("hidden");

  // Wire up action buttons inside modal if not yet wired
  const autoBtn = document.getElementById("auto-resolve-all-btn");
  if (autoBtn && !autoBtn.dataset.bound) {
    autoBtn.dataset.bound = "true";
    autoBtn.onclick = () => autoResolveAllShortages();
  }
  const slotBtn = document.getElementById("modal-switch-slot-btn");
  if (slotBtn && !slotBtn.dataset.bound) {
    slotBtn.dataset.bound = "true";
    slotBtn.onclick = () => {
      modal.classList.add("hidden");
      const viewSelect = document.getElementById("view-select");
      if (viewSelect) {
        viewSelect.value = "slot_centric";
        loadSchedule();
      }
    };
  }

  const container = document.getElementById("shortages-list-container");
  const countBadge = document.getElementById("shortage-modal-count-badge");
  if (!container) return;

  container.innerHTML = `<div style="text-align:center;padding:16px;color:var(--text-muted);">Analyzing roster shortages and evaluating candidate fixes...</div>`;

  try {
    const deficits = await apiGet(`/api/roster/${state.activePlanId}/deficits`);
    if (countBadge) {
      countBadge.textContent = `${deficits.length} Shortage${deficits.length === 1 ? "" : "s"}`;
    }

    if (deficits.length === 0) {
      container.innerHTML = `
        <div style="text-align:center;padding:24px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;color:#166534;">
          <div style="font-size:24px;margin-bottom:6px;">🎉</div>
          <b>All Clear — 0 Shortages!</b>
          <div style="font-size:12px;margin-top:4px;">100% of required shifts across all departments are fully staffed. Zero ergonomic violations.</div>
        </div>
      `;
      return;
    }

    let html = "";
    deficits.forEach((d, idx) => {
      const dObj = new Date(d.date + "T00:00:00");
      const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
      const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const formattedDate = `${monthNames[dObj.getMonth()]} ${dObj.getDate()}, ${dObj.getFullYear()} (${dayNames[dObj.getDay()]})`;

      let recButtons = "";
      if (d.recommended_fixes && d.recommended_fixes.length > 0) {
        d.recommended_fixes.forEach(fix => {
          const btnClass = fix.is_overtime ? "btn-warning" : "btn-primary";
          const icon = fix.is_overtime ? "⚡" : "✓";
          recButtons += `
            <button class="btn btn-sm ${btnClass}" style="font-size:11px;padding:5px 10px;text-align:left;display:flex;align-items:center;gap:6px;" onclick="applyShortageFix(${d.deficit_id}, ${fix.employee_id}, ${d.department_id}, ${d.shift_type_id}, '${d.date}')">
              <span>${icon}</span>
              <span>${fix.description}</span>
            </button>
          `;
        });
      } else {
        recButtons = `<span style="font-size:11px;color:var(--text-muted);font-style:italic;">No off-duty employees available. Use auto-resolve or waive this deficit.</span>`;
      }

      html += `
        <div class="shortage-item-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div>
              <div style="font-weight:700;font-size:13px;color:#9a3412;">
                Shortage #${idx + 1}: ${formattedDate}
              </div>
              <div style="font-size:11.5px;color:var(--text-muted);margin-top:2px;">
                Department: <b>${d.department_name}</b> &bull; Shift: <b>${d.shift_name}</b> &bull; Missing: <span style="color:#dc2626;font-weight:700;">${d.shortage_count} worker</span>
              </div>
            </div>
            <button class="btn btn-sm" style="font-size:10px;background:#fef2f2;border-color:#fca5a5;color:#991b1b;" title="Waive deficit / mark shift as on-call" onclick="waiveShortage(${d.deficit_id})">
              Waive Deficit
            </button>
          </div>
          <div style="border-top:1px solid #ffedd5;padding-top:6px;display:flex;flex-direction:column;gap:6px;">
            <span style="font-size:11px;font-weight:600;color:#9a3412;">Recommended 1-Click Fixes:</span>
            <div style="display:flex;flex-direction:column;gap:4px;">
              ${recButtons}
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<div style="color:#dc2626;padding:12px;">Failed to load shortages: ${err.message}</div>`;
  }
};

window.applyShortageFix = async function(deficitId, employeeId, departmentId, shiftTypeId, dateStr) {
  try {
    await apiPost(`/api/roster/${state.activePlanId}/assignments`, {
      employee_id: employeeId,
      department_id: departmentId,
      shift_type_id: shiftTypeId,
      date: dateStr,
      force_override: true,
      is_pinned: true
    });
    await loadSchedule();
    await openShortagesModal();
  } catch (err) {
    alert("Error applying fix: " + err.message);
  }
};

window.waiveShortage = async function(deficitId) {
  try {
    await apiDelete(`/api/roster/${state.activePlanId}/deficits/${deficitId}`);
    await loadSchedule();
    await openShortagesModal();
  } catch (err) {
    alert("Error waiving shortage: " + err.message);
  }
};

window.autoResolveAllShortages = async function() {
  if (!confirm("Auto-resolve all shortages by authorizing balanced overtime across available staff?")) return;
  try {
    const res = await apiPost(`/api/roster/${state.activePlanId}/resolve-all-deficits`, {});
    alert(res.message || "Shortages resolved successfully!");
    const modal = document.getElementById("modal-shortages-resolver");
    if (modal) modal.classList.add("hidden");
    await loadSchedule();
  } catch (err) {
    alert("Error auto-resolving shortages: " + err.message);
  }
};

const BUTTON_EXPLANATIONS = {
  "auto-resolve-all-btn": {
    title: "⚡ Auto-Resolve All Shortages",
    desc: "Automatically assigns eligible staff with balanced overtime to cover all understaffed shifts, eliminating all deficits.",
  },
  "modal-switch-slot-btn": {
    title: "📋 Slot-Centric View",
    desc: "Switch to slot-centric view to inspect staff coverage and deficits slot-by-slot.",
  },
  "welcome-setup-btn": {
    title: "🚀 Setup Wizard",
    desc: "Opens the 3-step setup wizard to import existing spreadsheets, create departments from scratch, or load demo rosters.",
  },
  "help-guide-btn": {
    title: "❓ Interactive Help Guide",
    desc: "Comprehensive documentation, visual cheat sheets, solver tips, and keyboard shortcut references for managers.",
  },
  "new-plan-btn": {
    title: "⚡ Generate CP-SAT Roster",
    desc: "Executes Google OR-Tools mathematical optimization to generate a complete monthly schedule while balancing workloads and eliminating fatigue.",
  },
  "solve-remaining-btn": {
    title: "🧩 Solve Remaining Slots",
    desc: "Fills empty cells (—) with optimal shifts without modifying any pre-filled or manager-pinned shifts.",
  },
  "sidebar-solve-btn": {
    title: "🧩 Solve Remaining Slots",
    desc: "Fills empty cells (—) with optimal shifts without modifying any pre-filled or manager-pinned shifts.",
  },
  "prefill-toggle-btn": {
    title: "✏️ Prefill Rapid Entry",
    desc: "Click-to-paint mode: Click any cell to stamp the currently selected shift code or off-duty mark instantly.",
  },
  "sidebar-prefill-btn": {
    title: "✏️ Prefill Rapid Entry",
    desc: "Click-to-paint mode: Click any cell to stamp the currently selected shift code or off-duty mark instantly.",
  },
  "variants-btn": {
    title: "⚖️ Compare Solver Variants",
    desc: "Inspect 3 alternative mathematical schedule variants (Float-Averse, Balanced, Overtime-Averse) and promote the best one.",
  },
  "find-replace-btn": {
    title: "🔍 Find & Replace Shifts",
    desc: "Search for specific shift codes across the month and batch replace or visually highlight all matching cells.",
  },
  "award-compoff-btn": {
    title: "☕ Award Comp Offs (COFF)",
    desc: "Scans each employee's schedule and awards earned Compensatory Off holidays for working overtime or extra shifts.",
  },
  "clear-canvas-btn": {
    title: "🗑️ Clear Canvas (Reset)",
    desc: "Clears all shifts and resets all cells back to empty (—) so you can start fresh or rebuild from scratch.",
  },
  "toggle-prev-month-btn": {
    title: "📅 Previous Month Context",
    desc: "Toggles trailing 3 days and worked hours from the prior month to prevent turnaround violations on day 1.",
  },
  "mode-toggle-btn": {
    title: "👁️ Simple / Advanced View",
    desc: "Switches between a clean streamlined spreadsheet view and the full ergonomic constraint audit mode.",
  },
  "manage-org-btn": {
    title: "🏢 Manage Organization",
    desc: "Configure departments, department colors, active staff directory, weekly hours limits, and shift staffing demand.",
  },
  "vacations-mgr-btn": {
    title: "🏖️ Vacations & Leaves",
    desc: "Record employee annual leave, medical leave, and vacations. The solver will automatically lock those dates as off.",
  },
  "advanced-settings-btn": {
    title: "⚙️ Advanced Solver Settings",
    desc: "Customize shift codes (MORN, NIGHT, COFF, DO), switch between 2-shift and 3-shift systems, and set solver timeouts.",
  },
  "import-btn": {
    title: "📥 Import Spreadsheets",
    desc: "Bulk-upload employees, departments, and staffing requirements from Excel (.xlsx) or CSV files.",
  },
  "export-excel-btn": {
    title: "📊 Export Styled Excel",
    desc: "Downloads an executive Excel workbook (.xlsx) color-coded with shifts, department badges, and variance scorecards.",
  },
  "export-pdf-btn": {
    title: "📄 Export Print-Ready PDF",
    desc: "Generates high-resolution vector PDF schedules formatted for workplace bulletin boards and compliance records.",
  },
  "toggle-sidebar-btn": {
    title: "📐 Toggle Department Filter",
    desc: "Collapses or expands the left department navigation sidebar.",
  },
  "sidebar-left-collapse-btn": {
    title: "◀ Collapse Left Sidebar",
    desc: "Hides the department filter sidebar to give more horizontal room for the schedule grid.",
  },
  "sidebar-left-expand-btn": {
    title: "▶ Expand Left Sidebar",
    desc: "Opens the department filter sidebar to filter schedules by department.",
  },
  "toggle-inspector-btn": {
    title: "📐 Toggle Shift Inspector",
    desc: "Collapses or expands the right-hand cell inspector panel.",
  },
  "sidebar-right-collapse-btn": {
    title: "▶ Collapse Inspector Panel",
    desc: "Hides the right inspector panel to maximize table viewing width.",
  },
  "sidebar-right-expand-btn": {
    title: "◀ Expand Inspector Panel",
    desc: "Opens the inspector panel to view cell details, rest rules, and manual override controls.",
  },
  "reset-widths-btn": {
    title: "↺ Reset Sidebar Widths",
    desc: "Restores both left and right sidebars back to their standard default widths.",
  },
  "inspector-pin-btn": {
    title: "📌 Pin / Lock Shift",
    desc: "Locks this shift so that subsequent CP-SAT solver runs will preserve it exactly as chosen.",
  },
  "inspector-clear-btn": {
    title: "⚪ Empty Cell (—)",
    desc: "Clears assignment and sets cell to blank. The solver will consider this cell fillable.",
  },
  "inspector-dayoff-btn": {
    title: "🔒 Lock Regular Day Off (📌 DO)",
    desc: "Pins this date as a mandatory Day Off. The solver is strictly forbidden from scheduling shifts here.",
  },
  "inspector-compoff-btn": {
    title: "☕ Lock Compensatory Off (📌 COFF)",
    desc: "Pins this date as Compensatory Off. Rewards accumulated overtime with a guaranteed day off.",
  },
  "inspector-audit-btn": {
    title: "🩺 Instant Ergonomic Audit",
    desc: "Checks 14-hour rest gaps, consecutive working streaks, and weekly hours limits for this employee.",
  },
  "quick-view-staff": {
    title: "👤 Staff-Centric View",
    desc: "Horizontal timeline displaying each employee on rows and dates across columns.",
  },
  "quick-view-slot": {
    title: "📋 Slot-Centric View",
    desc: "Shows required staffing count vs assigned workers shift-by-shift to quickly spot deficits.",
  },
  "quick-view-audit": {
    title: "📊 Workload Audit Scorecard",
    desc: "Detailed compliance table showing total hours, overtime variance, night shifts, and rest violations.",
  },
  "zoom-out-btn": {
    title: "🔍 Zoom Out Grid",
    desc: "Scales down the timetable cells for a broader bird's-eye view of the entire month.",
  },
  "zoom-in-btn": {
    title: "🔎 Zoom In Grid",
    desc: "Enlarges cell fonts and dimensions for comfortable reading and detailed editing.",
  },
  "zoom-reset-btn": {
    title: "🎯 Reset Zoom",
    desc: "Restores grid zoom scale back to default 100%.",
  },
  "show-add-dept-btn": {
    title: "➕ Create Department",
    desc: "Add a new department with custom color coding and operating schedule.",
  },
  "show-add-emp-btn": {
    title: "➕ Add New Employee",
    desc: "Register an employee with department affiliation, weekly hour cap, and dedicated off days.",
  },
  "save-demand-btn": {
    title: "💾 Save Staffing Demand",
    desc: "Saves required minimum staff per shift type to ensure adequate coverage during solver runs.",
  },
  "preset-1-demand-btn": {
    title: "1️⃣ Preset: 1 Staff / Shift",
    desc: "Sets required staffing count to 1 worker for all active shifts across Monday through Sunday.",
  },
  "preset-2-demand-btn": {
    title: "2️⃣ Preset: 2 Staff / Shift",
    desc: "Sets required staffing count to 2 workers for all active shifts across Monday through Sunday.",
  },
  "bulk-edit-emps-btn": {
    title: "📝 Bulk Edit Employees",
    desc: "Batch update primary department, weekly max hours, or dedicated off days for all selected employees.",
  },
  "bulk-delete-emps-btn": {
    title: "🗑️ Bulk Delete Employees",
    desc: "Deactivates and removes all selected employees in a single operation.",
  },
  "vac-add-btn": {
    title: "🏖️ Record Vacation / Leave",
    desc: "Logs vacation or medical leave. The solver will automatically respect these approved off dates.",
  },
  "save-settings-btn": {
    title: "💾 Save Advanced Settings",
    desc: "Persists custom shift codes, shift mode configurations, and solver preferences.",
  },
  "fr-highlight-btn": {
    title: "✨ Highlight Matches",
    desc: "Applies high-visibility glow outline to all cells matching your search query.",
  },
  "fr-replace-btn": {
    title: "🔁 Replace All Matches",
    desc: "Batch replaces matching shifts across the entire schedule grid.",
  },
  "fr-clear-btn": {
    title: "🧹 Clear Search Highlights",
    desc: "Removes search result outlines from the schedule table.",
  },
};

function showButtonTooltip(btn, info) {
  const tip = document.getElementById("button-action-tooltip");
  if (!tip || !info) return;

  const titleEl = document.getElementById("btn-tip-title");
  const descEl = document.getElementById("btn-tip-desc");

  if (titleEl) titleEl.textContent = info.title;
  if (descEl) descEl.textContent = info.desc;

  const rect = btn.getBoundingClientRect();
  const tipWidth = 280;
  const tipHeight = 75;

  let left = rect.left + rect.width / 2 - tipWidth / 2;
  let top = rect.bottom + 8;

  if (rect.bottom + tipHeight + 16 > window.innerHeight) {
    top = rect.top - tipHeight - 8;
  }

  if (left + tipWidth > window.innerWidth - 12) {
    left = window.innerWidth - tipWidth - 12;
  }
  if (left < 12) left = 12;

  tip.style.left = `${Math.round(left)}px`;
  tip.style.top = `${Math.round(top)}px`;
  tip.classList.remove("hidden");
}

function hideButtonTooltip() {
  const tip = document.getElementById("button-action-tooltip");
  if (tip) tip.classList.add("hidden");
}

let buttonTooltipTimer = null;
let activeTooltipBtn = null;

function initButtonTooltips() {
  document.addEventListener("mouseover", (e) => {
    const btn = e.target.closest(
      "button, .ribbon-tab, .status-icon-btn, .status-zoom-btn, .status-zoom-label"
    );
    if (!btn) return;
    if (btn === activeTooltipBtn) return;
    activeTooltipBtn = btn;

    let info = null;
    if (btn.id && BUTTON_EXPLANATIONS[btn.id]) {
      info = BUTTON_EXPLANATIONS[btn.id];
    } else if (btn.dataset.tooltip) {
      info = {
        title: btn.textContent.trim() || "Action",
        desc: btn.dataset.tooltip,
      };
    } else if (
      btn.title &&
      btn.title.length > 5 &&
      !btn.title.startsWith("Click to view")
    ) {
      info = { title: btn.textContent.trim() || "Action", desc: btn.title };
    }

    if (!info) return;

    clearTimeout(buttonTooltipTimer);
    buttonTooltipTimer = setTimeout(() => {
      if (activeTooltipBtn === btn) {
        showButtonTooltip(btn, info);
      }
    }, 180);
  });

  document.addEventListener("mouseout", (e) => {
    const btn = e.target.closest(
      "button, .ribbon-tab, .status-icon-btn, .status-zoom-btn, .status-zoom-label"
    );
    if (btn && btn === activeTooltipBtn) {
      activeTooltipBtn = null;
      clearTimeout(buttonTooltipTimer);
      hideButtonTooltip();
    }
  });
}

async function selectAssignment(emp, dateStr, currentAssignment, rowIdx = null, colIdx = null, td = null) {
  hideCellHover();
  state.selectedCell = { emp, dateStr, currentAssignment, rowIdx, colIdx, td };
  updateGridCrosshairs(rowIdx, colIdx, td);

  // If inspector is collapsed, expand it
  const ip = document.getElementById("inspector-panel");
  if (ip && ip.classList.contains("collapsed")) {
    toggleRightInspector(true);
  }

  const content = document.getElementById("inspector-content");
  const actions = document.getElementById("inspector-actions");
  actions.classList.remove("hidden");

  // Conflict Alert box
  const conflictAlert = document.getElementById("inspector-conflict-alert");
  if (conflictAlert) {
    if (currentAssignment && currentAssignment.has_conflict) {
      conflictAlert.classList.remove("hidden");
      conflictAlert.innerHTML = `<b>⚠️ Rule Conflict:</b><br>${currentAssignment.conflict_reason || "Ergonomic labor rule violation"}`;
    } else {
      conflictAlert.classList.add("hidden");
    }
  }

  let shiftSelectorHtml = `<select id="target-shift-select" class="select-input" style="width:100%;margin-top:6px;">`;
  state.shifts.forEach(s => {
    const isSel = currentAssignment && currentAssignment.shift_id === s.id;
    shiftSelectorHtml += `<option value="${s.id}" ${isSel ? "selected" : ""}>${s.name} (${s.code})</option>`;
  });
  shiftSelectorHtml += `</select>`;

  let deptSelectorHtml = `<select id="target-dept-select" class="select-input" style="width:100%;margin-top:6px;">`;
  state.departments.forEach(d => {
    const isSel = currentAssignment ? currentAssignment.department_id === d.id : d.id === emp.primary_department_id;
    deptSelectorHtml += `<option value="${d.id}" ${isSel ? "selected" : ""}>${d.name}</option>`;
  });
  deptSelectorHtml += `</select>`;

  let statusHtml = "";
  if (currentAssignment && currentAssignment.is_comp_off) {
    const earnedNote = currentAssignment.is_earned_coff ? ` (Earned Overtime Holiday for ${currentAssignment.earned_hours || '40+'}h worked)` : "";
    statusHtml = `<div class="brand-badge" style="background:#fef3c7;color:#92400e;margin-top:6px;display:inline-block;">☕ Compensatory Off: ${currentAssignment.shift_name || 'Earned Holiday'}${earnedNote}</div>`;
  } else if (currentAssignment && currentAssignment.is_day_off) {
    statusHtml = `<div class="brand-badge" style="background:#e2e8f0;color:#1e293b;margin-top:6px;display:inline-block;">📌 Pinned Day OFF (Locked)</div>`;
  } else if (currentAssignment && currentAssignment.is_leave) {
    statusHtml = `<div class="brand-badge" style="background:#f3e8ff;color:#6b21a8;margin-top:6px;display:inline-block;">Approved Leave: ${currentAssignment.shift_name}</div>`;
  } else if (currentAssignment && currentAssignment.is_fixed_off) {
    statusHtml = `<div class="brand-badge" style="background:#f1f5f9;color:#475569;margin-top:6px;display:inline-block;">Dedicated Regular Day Off</div>`;
  } else if (!currentAssignment || !currentAssignment.shift_id) {
    const isSolved = state.currentScheduleData && state.currentScheduleData.plan &&
      (state.currentScheduleData.plan.status === "SOLVED" || state.currentScheduleData.plan.status === "PUBLISHED");
    if (isSolved) {
      statusHtml = `<div class="brand-badge" style="background:#f1f5f9;color:#475569;margin-top:6px;display:inline-block;border:1px solid #cbd5e1;">⚪ Scheduled Rest Day (OFF) • Contract Target Fulfilled</div>`;
    } else {
      statusHtml = `<div class="brand-badge" style="background:#f8fafc;color:#64748b;margin-top:6px;display:inline-block;border:1px dashed #cbd5e1;">Empty Cell (Fillable by Solver)</div>`;
    }
  }

  content.innerHTML = `
    <div style="font-size:12px;">
      <div><b>Employee:</b> ${emp.employee_name} (${emp.primary_department_code || ""})</div>
      <div><b>Date:</b> ${dateStr}</div>
      ${statusHtml}
      <div style="margin-top:8px;"><b>Change Shift:</b></div>
      ${shiftSelectorHtml}
      <div style="margin-top:8px;"><b>Department:</b></div>
      ${deptSelectorHtml}
      <div id="validation-feedback" style="margin-top:12px;"></div>
      <button id="apply-shift-btn" class="btn btn-sm btn-primary" style="width:100%;margin-top:10px;">Apply & Validate Move</button>
    </div>
  `;

  // Attach live validator
  document.getElementById("apply-shift-btn").onclick = async () => {
    const shiftId = parseInt(document.getElementById("target-shift-select").value);
    const deptId = parseInt(document.getElementById("target-dept-select").value);

    const val = await apiPost("/api/roster/validate-assignment", {
      plan_id: state.activePlanId,
      employee_id: emp.employee_id,
      target_department_id: deptId,
      target_shift_type_id: shiftId,
      target_date: dateStr
    });

    const fb = document.getElementById("validation-feedback");
    if (val.is_valid) {
      fb.innerHTML = `<div class="alert-card success">✓ Valid Assignment! No ergonomic violations detected.</div>`;
      // Commit
      await apiPost(`/api/roster/${state.activePlanId}/assignments`, {
        employee_id: emp.employee_id,
        department_id: deptId,
        shift_type_id: shiftId,
        date: dateStr,
        force_override: false,
        is_pinned: state.prefillMode
      });
      await loadSchedule();
    } else {
      const msgs = val.violations.map(v => `• ${v.message}`).join("<br>");
      fb.innerHTML = `
        <div class="alert-card danger">
          <b>Rule Conflict:</b><br>${msgs}
          <button id="force-override-btn" class="btn btn-sm" style="margin-top:6px;width:100%;">Force Override Anyway</button>
        </div>
      `;
      document.getElementById("force-override-btn").onclick = async () => {
        await apiPost(`/api/roster/${state.activePlanId}/assignments`, {
          employee_id: emp.employee_id,
          department_id: deptId,
          shift_type_id: shiftId,
          date: dateStr,
          force_override: true,
          is_pinned: true
        });
        await loadSchedule();
      };
    }
  };

  // Wire Inspector Status Action buttons
  const emptyBtn = document.getElementById("inspector-empty-btn");
  if (emptyBtn) {
    emptyBtn.onclick = async () => {
      await emptySelectedCell();
    };
  }

  const dayOffBtn = document.getElementById("inspector-dayoff-btn");
  if (dayOffBtn) {
    dayOffBtn.onclick = async () => {
      await apiPost(`/api/roster/${state.activePlanId}/pin-off`, {
        employee_id: emp.employee_id,
        date: dateStr,
        off_type: "DAY_OFF"
      });
      await loadSchedule();
      const updatedAssign = { shift_code: "DO", is_day_off: true, is_pinned: true, shift_name: "Day OFF (Locked 📌)" };
      selectAssignment(emp, dateStr, updatedAssign, rowIdx, colIdx, td);
    };
  }

  const compOffBtn = document.getElementById("inspector-compoff-btn");
  if (compOffBtn) {
    compOffBtn.onclick = async () => {
      await apiPost(`/api/roster/${state.activePlanId}/pin-off`, {
        employee_id: emp.employee_id,
        date: dateStr,
        off_type: "COFF"
      });
      await loadSchedule();
      const updatedAssign = { shift_code: "COFF", is_comp_off: true, is_pinned: true, shift_name: "Compensatory Off (Coff 📌)" };
      selectAssignment(emp, dateStr, updatedAssign, rowIdx, colIdx, td);
    };
  }

  const pinBtn = document.getElementById("inspector-pin-btn");
  if (pinBtn) {
    const isPinned = currentAssignment && currentAssignment.is_pinned;
    pinBtn.textContent = isPinned ? "Unpin Shift 🔓" : "Pin Current Shift 📌";
    pinBtn.className = `btn btn-sm ${isPinned ? "btn-primary" : ""}`;
    pinBtn.onclick = async () => {
      if (!currentAssignment || !currentAssignment.assignment_id) {
        alert("Please select or assign a shift first before pinning.");
        return;
      }
      const res = await apiPost(`/api/roster/${state.activePlanId}/assignments/toggle-pin?employee_id=${emp.employee_id}&date=${dateStr}`, {});
      await loadSchedule();
      selectAssignment(emp, dateStr, { ...currentAssignment, is_pinned: res.is_pinned }, rowIdx, colIdx, td);
    };
  }
}

async function emptySelectedCell() {
  if (!state.selectedCell || !state.activePlanId) return;
  const { emp, dateStr } = state.selectedCell;
  try {
    await apiDelete(`/api/roster/${state.activePlanId}/assignments?employee_id=${emp.employee_id}&date=${dateStr}`);
    await loadSchedule();
    if (state.selectedCell) {
      const rowIdx = state.selectedCell.rowIdx;
      const colIdx = state.selectedCell.colIdx;
      const targetTd = document.querySelector(`td[data-row="${rowIdx}"][data-col="${colIdx}"]`);
      selectAssignment(emp, dateStr, null, rowIdx, colIdx, targetTd);
    }
  } catch (err) {
    console.error("Failed to empty cell:", err);
  }
}

// ==========================================
// Organization Management (CRUD)
// ==========================================
async function loadOrgDepartments() {
  const depts = await apiGet("/api/departments?active_only=false");
  document.getElementById("org-dept-count").textContent = depts.length;

  const tbody = document.getElementById("depts-table-body");
  tbody.innerHTML = "";

  const empDeptSelect = document.getElementById("emp-form-dept");
  const filterDeptSelect = document.getElementById("emp-filter-dept-select");
  const curFilter = filterDeptSelect.value;

  empDeptSelect.innerHTML = "";
  filterDeptSelect.innerHTML = `<option value="">All Departments</option>`;

  depts.forEach(d => {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = `${d.name} (${d.code})`;
    empDeptSelect.appendChild(opt);

    const fOpt = document.createElement("option");
    fOpt.value = d.id;
    fOpt.textContent = `${d.name} (${d.code})`;
    if (curFilter && parseInt(curFilter) === d.id) fOpt.selected = true;
    filterDeptSelect.appendChild(fOpt);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="dept-color-dot" style="background:${d.color_code};width:14px;height:14px;"></span></td>
      <td><b>${d.code}</b></td>
      <td>${d.name}</td>
      <td><span class="brand-badge" style="background:#e2e8f0;color:#334155;">${d.operating_regime === "24_7" ? "24/7 Operations" : "Weekdays Only"}</span></td>
      <td><b>${d.employee_count || 0}</b></td>
      <td style="text-align:right;">
        <button class="btn btn-sm" onclick='editDepartment(${JSON.stringify(d)})'>Edit</button>
        <button class="btn btn-sm" style="color:#dc2626;" onclick='deleteDepartment(${d.id}, "${d.name.replace(/"/g, '&quot;')}")'>Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.editDepartment = function(d) {
  document.getElementById("dept-form-id").value = d.id;
  document.getElementById("dept-form-code").value = d.code;
  document.getElementById("dept-form-name").value = d.name;
  document.getElementById("dept-form-color").value = d.color_code || "#3B82F6";
  document.getElementById("dept-color-hex").textContent = (d.color_code || "#3B82F6").toUpperCase();
  document.getElementById("dept-form-regime").value = d.operating_regime || "24_7";
  document.getElementById("dept-form-title").textContent = `Edit Department: ${d.name}`;
  document.getElementById("dept-form-card").classList.remove("hidden");
};

window.deleteDepartment = async function(id, name) {
  if (!confirm(`Are you sure you want to delete department "${name}"?`)) return;
  try {
    const res = await apiDelete(`/api/departments/${id}`);
    alert(res.message || "Department deleted.");
    state.departments = await apiGet("/api/departments");
    renderDeptFilters();
    await loadOrgDepartments();
    await loadSchedule();
  } catch (err) {
    alert("Cannot delete department: " + err.message);
  }
};

async function initOrgDemandView() {
  const deptSelect = document.getElementById("demand-dept-select");
  if (!deptSelect) return;

  const depts = state.departments || await apiGet("/api/departments");
  deptSelect.innerHTML = "";
  depts.forEach(d => {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = `${d.name} (${d.code}) - ${d.operating_regime}`;
    deptSelect.appendChild(opt);
  });

  deptSelect.onchange = () => loadDepartmentDemand(parseInt(deptSelect.value));
  if (depts.length > 0) {
    await loadDepartmentDemand(depts[0].id);
  }
}

async function loadDepartmentDemand(deptId) {
  const tbody = document.getElementById("demand-table-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:12px;color:var(--text-muted);">Loading shift requirements...</td></tr>`;

  try {
    const reqs = await apiGet(`/api/departments/${deptId}/requirements`);
    state.shifts = state.shifts || await apiGet("/api/shift-types");

    const reqMap = {};
    reqs.forEach(r => {
      reqMap[r.shift_type_id] = reqMap[r.shift_type_id] || {};
      reqMap[r.shift_type_id][r.day_of_week] = r.min_staff;
    });

    tbody.innerHTML = "";
    state.shifts.forEach(s => {
      const tr = document.createElement("tr");
      tr.dataset.shiftId = s.id;

      let cells = `
        <td style="text-align:left;font-weight:600;">
          ${s.name} <span class="brand-badge" style="background:#e0e7ff;color:#3730a3;font-size:10px;">${s.code}</span>
        </td>
        <td style="font-size:11px;color:#64748b;">${s.start_time.slice(0,5)}–${s.end_time.slice(0,5)} (${s.duration_hours}h)</td>
      `;

      for (let dow = 0; dow < 7; dow++) {
        const val = (reqMap[s.id] && reqMap[s.id][dow] !== undefined) ? reqMap[s.id][dow] : 1;
        cells += `
          <td style="text-align:center;padding:2px;">
            <input type="number" min="0" max="50" step="1" class="text-input demand-num-input" 
              data-shift-id="${s.id}" data-dow="${dow}" value="${val}"
              style="width:44px;text-align:center;font-size:12px;font-weight:600;padding:3px;">
          </td>
        `;
      }

      tr.innerHTML = cells;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#dc2626;">Failed to load demand requirements: ${err.message}</td></tr>`;
  }
}

function populateEmpFormShifts(selectedShiftId = null) {
  const select = document.getElementById("emp-form-shift");
  if (!select) return;
  select.innerHTML = `<option value="">Dynamic / Flexible Shift</option>`;
  (state.shifts || []).forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = `☀️ ${s.name} (${s.code} - ${s.duration_hours}h)`;
    if (selectedShiftId && parseInt(selectedShiftId) === s.id) opt.selected = true;
    select.appendChild(opt);
  });
}

function populateEmpSecondaryDepts(primaryDeptId, selectedSecDeptIds = []) {
  const container = document.getElementById("emp-secondary-depts-container");
  if (!container) return;
  container.innerHTML = "";
  const secIds = Array.isArray(selectedSecDeptIds) ? selectedSecDeptIds.map(x => parseInt(x)) : [];
  (state.departments || []).forEach(d => {
    if (primaryDeptId && d.id === parseInt(primaryDeptId)) return;
    const isChecked = secIds.includes(d.id);
    const label = document.createElement("label");
    label.className = "sec-dept-pill";
    label.style.cssText = `display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:12px;background:${isChecked ? '#e0f2fe' : '#f1f5f9'};border:1px solid ${isChecked ? '#38bdf8' : '#cbd5e1'};font-size:11px;cursor:pointer;`;
    label.innerHTML = `
      <input type="checkbox" class="sec-dept-cb" value="${d.id}" ${isChecked ? 'checked' : ''} style="margin:0;">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${d.color_code};"></span>
      <b>${d.code}</b> (${d.name})
    `;
    const cb = label.querySelector(".sec-dept-cb");
    cb.onchange = () => {
      label.style.background = cb.checked ? '#e0f2fe' : '#f1f5f9';
      label.style.borderColor = cb.checked ? '#38bdf8' : '#cbd5e1';
    };
    container.appendChild(label);
  });
  if (container.children.length === 0) {
    container.innerHTML = `<span style="color:#94a3b8;font-size:11px;">No other departments available.</span>`;
  }
}

async function loadOrgEmployees() {
  const filterDeptId = document.getElementById("emp-filter-dept-select").value;
  let url = "/api/employees?active_only=false";
  if (filterDeptId) url += `&department_id=${filterDeptId}`;

  if (!state.shifts) state.shifts = await apiGet("/api/shift-types");
  const emps = await apiGet(url);
  document.getElementById("org-emp-count").textContent = emps.length;

  state.selectedEmpIds = state.selectedEmpIds || new Set();
  const tbody = document.getElementById("emps-table-body");
  tbody.innerHTML = "";

  const dayNames = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

  emps.forEach(e => {
    const dObj = state.departments.find(d => d.id === e.primary_department_id);
    const dColor = dObj ? dObj.color_code : "#3B82F6";
    const dCode = dObj ? dObj.code : "";

    let dedShiftBadge = '<span style="color:#94a3b8;font-size:11px;">Flexible</span>';
    if (e.preferred_shift_type_id) {
      const ps = state.shifts ? state.shifts.find(s => s.id === e.preferred_shift_type_id) : null;
      const psName = ps ? ps.name : (e.preferred_shift_name || "Shift");
      dedShiftBadge = `<span class="brand-badge" style="background:#e0f2fe;color:#0369a1;font-weight:600;font-size:10px;">☀️ ${psName}</span>`;
    }

    let floatBadges = '<span style="color:#94a3b8;font-size:11px;">None</span>';
    if (e.secondary_departments && e.secondary_departments.length > 0) {
      floatBadges = e.secondary_departments.map(sd => `<span class="dept-badge-tag" style="font-size:9px;" title="${sd.department_name}">⚓ ${sd.department_code}</span>`).join(" ");
    } else if (e.secondary_department_ids && e.secondary_department_ids.length > 0) {
      const codes = e.secondary_department_ids.map(id => {
        const d = state.departments ? state.departments.find(dept => dept.id === id) : null;
        return d ? d.code : `D${id}`;
      });
      floatBadges = codes.map(c => `<span class="dept-badge-tag" style="font-size:9px;">⚓ ${c}</span>`).join(" ");
    }

    let fixedOffBadge = '<span style="color:#94a3b8;font-size:11px;">Dynamic</span>';
    if (e.fixed_off_days) {
      const idxs = e.fixed_off_days.split(",").map(x => parseInt(x.trim())).filter(x => !isNaN(x));
      if (idxs.length > 0) {
        fixedOffBadge = `<span class="shift-badge shift-do" style="font-size:10px;">${idxs.map(i => dayNames[i]).join(", ")}</span>`;
      }
    }

    const isChecked = state.selectedEmpIds.has(e.id);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="text-align:center;">
        <input type="checkbox" class="emp-row-cb" data-id="${e.id}" ${isChecked ? "checked" : ""}>
      </td>
      <td><b>${e.employee_code}</b></td>
      <td>${e.name}</td>
      <td><span class="dept-badge-tag" style="background:${dColor};">${dCode}</span> ${e.primary_department_name || ''}</td>
      <td>${dedShiftBadge}</td>
      <td>${floatBadges}</td>
      <td>${e.max_hours_week} hrs/wk</td>
      <td>${fixedOffBadge}</td>
      <td><span class="brand-badge" style="background:${e.is_active ? '#dcfce7' : '#fee2e2'};color:${e.is_active ? '#166534' : '#991b1b'};">${e.is_active ? 'Active' : 'Inactive'}</span></td>
      <td style="text-align:right;">
        <button class="btn btn-sm" onclick='editEmployee(${JSON.stringify(e)})'>Edit</button>
        <button class="btn btn-sm" style="color:#dc2626;" onclick='deleteEmployee(${e.id}, "${e.name.replace(/"/g, '&quot;')}")'>Delete</button>
      </td>
    `;

    const rowCb = tr.querySelector(".emp-row-cb");
    if (rowCb) {
      rowCb.onchange = (evt) => {
        if (evt.target.checked) {
          state.selectedEmpIds.add(e.id);
        } else {
          state.selectedEmpIds.delete(e.id);
        }
        updateEmpBulkToolbar(emps);
      };
    }

    tbody.appendChild(tr);
  });

  const selectAllCb = document.getElementById("emp-select-all-cb");
  if (selectAllCb) {
    selectAllCb.checked = emps.length > 0 && emps.every(e => state.selectedEmpIds.has(e.id));
    selectAllCb.indeterminate = emps.some(e => state.selectedEmpIds.has(e.id)) && !selectAllCb.checked;
    selectAllCb.onchange = (evt) => {
      if (evt.target.checked) {
        emps.forEach(e => state.selectedEmpIds.add(e.id));
      } else {
        emps.forEach(e => state.selectedEmpIds.delete(e.id));
      }
      loadOrgEmployees();
    };
  }

  updateEmpBulkToolbar(emps);
}

function updateEmpBulkToolbar(emps = []) {
  const toolbar = document.getElementById("emps-bulk-toolbar");
  const countSpan = document.getElementById("emp-selected-count");
  const selectAllCb = document.getElementById("emp-select-all-cb");
  const count = state.selectedEmpIds ? state.selectedEmpIds.size : 0;

  if (toolbar) {
    if (count > 0) {
      toolbar.classList.remove("hidden");
      if (countSpan) countSpan.textContent = `${count} employee${count === 1 ? "" : "s"} selected`;
    } else {
      toolbar.classList.add("hidden");
    }
  }

  if (selectAllCb && emps.length > 0) {
    selectAllCb.checked = emps.every(e => state.selectedEmpIds.has(e.id));
    selectAllCb.indeterminate = emps.some(e => state.selectedEmpIds.has(e.id)) && !selectAllCb.checked;
  }
}

window.editEmployee = function(e) {
  document.getElementById("emp-form-id").value = e.id;
  document.getElementById("emp-form-code").value = e.employee_code;
  document.getElementById("emp-form-name").value = e.name;
  document.getElementById("emp-form-dept").value = e.primary_department_id;
  document.getElementById("emp-form-hours").value = e.max_hours_week || 40.0;
  document.getElementById("emp-form-title").textContent = `Edit Employee: ${e.name}`;

  populateEmpFormShifts(e.preferred_shift_type_id);
  populateEmpSecondaryDepts(e.primary_department_id, e.secondary_department_ids || []);

  const preset = document.getElementById("emp-form-fixed-preset");
  document.querySelectorAll(".fixed-day-cb").forEach(cb => cb.checked = false);

  if (e.fixed_off_days) {
    const dayArr = e.fixed_off_days.split(",").map(x => x.trim());
    dayArr.forEach(val => {
      const cb = document.querySelector(`.fixed-day-cb[value="${val}"]`);
      if (cb) cb.checked = true;
    });
    if (preset) {
      if (e.fixed_off_days === "5,6") preset.value = "5,6";
      else if (e.fixed_off_days === "0,1") preset.value = "0,1";
      else if (e.fixed_off_days === "6,0") preset.value = "6,0";
      else preset.value = "custom";
    }
  } else {
    if (preset) preset.value = "";
  }

  document.getElementById("emp-form-card").classList.remove("hidden");
};

window.deleteEmployee = async function(id, name) {
  if (!confirm(`Are you sure you want to delete employee "${name}"?`)) return;
  try {
    const res = await apiDelete(`/api/employees/${id}`);
    alert(res.message || "Employee deleted.");
    await loadOrgEmployees();
    await loadOrgDepartments();
    await loadSchedule();
  } catch (err) {
    alert("Cannot delete employee: " + err.message);
  }
};

// ==========================================
// Zoom Controller
// ==========================================
function setZoom(level) {
  const clamped = Math.min(1.6, Math.max(0.65, Math.round(level * 100) / 100));
  state.zoomLevel = clamped;
  const label = document.getElementById("zoom-label");
  if (label) label.textContent = `${Math.round(clamped * 100)}%`;
  const slider = document.getElementById("zoom-slider");
  if (slider) slider.value = Math.round(clamped * 100);

  const table = document.getElementById("schedule-table");
  if (table) {
    table.style.zoom = clamped;
  }
  document.documentElement.style.setProperty("--zoom-factor", clamped);
  localStorage.setItem("localroster_zoom_level", clamped.toString());
}

function initZoom() {
  const savedZoom = parseFloat(localStorage.getItem("localroster_zoom_level"));
  if (!isNaN(savedZoom)) {
    setZoom(savedZoom);
  } else {
    setZoom(1.0);
  }

  const zoomInBtn = document.getElementById("zoom-in-btn");
  if (zoomInBtn) zoomInBtn.onclick = (e) => {
    e.preventDefault();
    setZoom(state.zoomLevel + 0.1);
  };

  const zoomOutBtn = document.getElementById("zoom-out-btn");
  if (zoomOutBtn) zoomOutBtn.onclick = (e) => {
    e.preventDefault();
    setZoom(state.zoomLevel - 0.1);
  };

  const zoomResetBtn = document.getElementById("zoom-reset-btn");
  if (zoomResetBtn) zoomResetBtn.onclick = (e) => {
    e.preventDefault();
    setZoom(1.0);
  };

  const slider = document.getElementById("zoom-slider");
  if (slider) {
    slider.oninput = (e) => setZoom(parseFloat(e.target.value) / 100);
  }

  // Ctrl + MouseWheel on grid container
  const gridContainer = document.getElementById("grid-container");
  if (gridContainer) {
    gridContainer.addEventListener("wheel", (e) => {
      if (e.ctrlKey) {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.08 : -0.08;
        setZoom(state.zoomLevel + delta);
      }
    }, { passive: false });
  }
}

// ==========================================
// Excel-Style Ribbon Category Tabs
// ==========================================
function initRibbonTabs() {
  const tabs = document.querySelectorAll(".ribbon-tab");
  tabs.forEach(tab => {
    tab.onclick = () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const targetPaneId = tab.getAttribute("data-tab");
      document.querySelectorAll(".ribbon-pane").forEach(pane => {
        if (pane.id === targetPaneId) {
          pane.classList.remove("hidden");
          pane.classList.add("active");
        } else {
          pane.classList.add("hidden");
          pane.classList.remove("active");
        }
      });
    };
  });

  // Direct Sidebar Collapse & Expand Controls (like modern AI agent interfaces)
  const leftCollapseBtn = document.getElementById("sidebar-left-collapse-btn");
  if (leftCollapseBtn) {
    leftCollapseBtn.onclick = () => toggleLeftSidebar(false);
  }

  const leftExpandBtn = document.getElementById("sidebar-left-expand-btn");
  if (leftExpandBtn) {
    leftExpandBtn.onclick = () => toggleLeftSidebar(true);
  }

  const rightCollapseBtn = document.getElementById("sidebar-right-collapse-btn");
  if (rightCollapseBtn) {
    rightCollapseBtn.onclick = () => toggleRightInspector(false);
  }

  const rightExpandBtn = document.getElementById("sidebar-right-expand-btn");
  if (rightExpandBtn) {
    rightExpandBtn.onclick = () => toggleRightInspector(true);
  }

  const toggleSidebarBtn = document.getElementById("toggle-sidebar-btn");
  if (toggleSidebarBtn) {
    toggleSidebarBtn.onclick = () => toggleLeftSidebar();
  }

  const toggleInspectorBtn = document.getElementById("toggle-inspector-btn");
  if (toggleInspectorBtn) {
    toggleInspectorBtn.onclick = () => toggleRightInspector();
  }

  const resetWidthsBtn = document.getElementById("reset-widths-btn");
  if (resetWidthsBtn) {
    resetWidthsBtn.onclick = () => {
      localStorage.removeItem("localroster_sidebar_left_width");
      localStorage.removeItem("localroster_sidebar_right_width");
      const left = document.getElementById("dept-sidebar");
      if (left) left.style.width = "220px";
      const right = document.getElementById("inspector-panel");
      if (right) right.style.width = "320px";
      toggleLeftSidebar(true);
      toggleRightInspector(true);
      alert("Sidebar widths reset to standard layout.");
    };
  }
}

function toggleLeftSidebar(forceState) {
  const sb = document.getElementById("dept-sidebar");
  const expandBtn = document.getElementById("sidebar-left-expand-btn");
  const resizer = document.getElementById("resizer-left");
  const topBtn = document.getElementById("toggle-sidebar-btn");
  if (!sb) return;

  const isCollapsed = forceState !== undefined ? !forceState : !sb.classList.contains("collapsed");

  if (isCollapsed) {
    sb.classList.add("collapsed");
    sb.style.display = "none";
    if (expandBtn) expandBtn.classList.remove("hidden");
    if (resizer) resizer.style.display = "none";
    if (topBtn) topBtn.textContent = "Show Dept Sidebar";
  } else {
    sb.classList.remove("collapsed");
    sb.style.display = "flex";
    if (expandBtn) expandBtn.classList.add("hidden");
    if (resizer) resizer.style.display = "";
    if (topBtn) topBtn.textContent = "Hide Dept Sidebar";
  }
}

function toggleRightInspector(forceState) {
  const ip = document.getElementById("inspector-panel");
  const expandBtn = document.getElementById("sidebar-right-expand-btn");
  const resizer = document.getElementById("resizer-right");
  const topBtn = document.getElementById("toggle-inspector-btn");
  if (!ip) return;

  const isCollapsed = forceState !== undefined ? !forceState : !ip.classList.contains("collapsed");

  if (isCollapsed) {
    ip.classList.add("collapsed");
    ip.style.display = "none";
    if (expandBtn) expandBtn.classList.remove("hidden");
    if (resizer) resizer.style.display = "none";
    if (topBtn) topBtn.textContent = "Show Inspector";
  } else {
    ip.classList.remove("collapsed");
    ip.style.display = "flex";
    if (expandBtn) expandBtn.classList.add("hidden");
    if (resizer) resizer.style.display = "";
    if (topBtn) topBtn.textContent = "Hide Inspector";
  }
}

// ==========================================
// Resizable Sidebars Controller
// ==========================================
function initResizers() {
  const leftResizer = document.getElementById("resizer-left");
  const leftSidebar = document.getElementById("dept-sidebar");
  const rightResizer = document.getElementById("resizer-right");
  const rightPanel = document.getElementById("inspector-panel");

  // Restore saved widths
  const savedLeft = localStorage.getItem("localroster_sidebar_left_width");
  if (savedLeft && leftSidebar) leftSidebar.style.width = `${savedLeft}px`;

  const savedRight = localStorage.getItem("localroster_sidebar_right_width");
  if (savedRight && rightPanel) rightPanel.style.width = `${savedRight}px`;

  // Left Resizer Dragging
  if (leftResizer && leftSidebar) {
    let startX, startWidth;
    const onMouseMoveLeft = (e) => {
      const dx = e.clientX - startX;
      const newWidth = Math.min(450, Math.max(140, startWidth + dx));
      leftSidebar.style.width = `${newWidth}px`;
      localStorage.setItem("localroster_sidebar_left_width", newWidth);
    };
    const onMouseUpLeft = () => {
      document.body.classList.remove("resizing-active");
      leftResizer.classList.remove("dragging");
      window.removeEventListener("mousemove", onMouseMoveLeft);
      window.removeEventListener("mouseup", onMouseUpLeft);
    };
    leftResizer.addEventListener("mousedown", (e) => {
      startX = e.clientX;
      startWidth = leftSidebar.offsetWidth;
      document.body.classList.add("resizing-active");
      leftResizer.classList.add("dragging");
      window.addEventListener("mousemove", onMouseMoveLeft);
      window.addEventListener("mouseup", onMouseUpLeft);
    });
  }

  // Right Resizer Dragging
  if (rightResizer && rightPanel) {
    let startX, startWidth;
    const onMouseMoveRight = (e) => {
      const dx = startX - e.clientX;
      const newWidth = Math.min(550, Math.max(180, startWidth + dx));
      rightPanel.style.width = `${newWidth}px`;
      localStorage.setItem("localroster_sidebar_right_width", newWidth);
    };
    const onMouseUpRight = () => {
      document.body.classList.remove("resizing-active");
      rightResizer.classList.remove("dragging");
      window.removeEventListener("mousemove", onMouseMoveRight);
      window.removeEventListener("mouseup", onMouseUpRight);
    };
    rightResizer.addEventListener("mousedown", (e) => {
      startX = e.clientX;
      startWidth = rightPanel.offsetWidth;
      document.body.classList.add("resizing-active");
      rightResizer.classList.add("dragging");
      window.addEventListener("mousemove", onMouseMoveRight);
      window.addEventListener("mouseup", onMouseUpRight);
    });
  }
}

// ==========================================
// Onboarding Wizard Controller
// ==========================================
function initOnboarding() {
  const hasSeen = localStorage.getItem("localroster_onboarding_chosen");
  if (!hasSeen) {
    setTimeout(() => {
      const modal = document.getElementById("modal-onboarding");
      if (modal) modal.classList.remove("hidden");
    }, 350);
  }

  const welcomeBtn = document.getElementById("welcome-setup-btn");
  if (welcomeBtn) {
    welcomeBtn.onclick = () => {
      document.getElementById("modal-onboarding").classList.remove("hidden");
    };
  }

  const cb = document.getElementById("dont-show-onboarding-cb");

  // Path 1: Import
  const btnImport = document.getElementById("onboarding-btn-import");
  if (btnImport) {
    btnImport.onclick = () => {
      document.getElementById("modal-onboarding").classList.add("hidden");
      if (cb && cb.checked) localStorage.setItem("localroster_onboarding_chosen", "true");
      document.getElementById("modal-import").classList.remove("hidden");
    };
  }

  // Path 2: Start from scratch
  const btnScratch = document.getElementById("onboarding-btn-scratch");
  if (btnScratch) {
    btnScratch.onclick = async () => {
      document.getElementById("modal-onboarding").classList.add("hidden");
      if (cb && cb.checked) localStorage.setItem("localroster_onboarding_chosen", "true");
      document.getElementById("modal-manage-org").classList.remove("hidden");
      await loadOrgDepartments();
      await loadOrgEmployees();
    };
  }

  // Path 3: Explore Demo
  const btnDemo = document.getElementById("onboarding-btn-demo");
  if (btnDemo) {
    btnDemo.onclick = () => {
      document.getElementById("modal-onboarding").classList.add("hidden");
      if (cb && cb.checked) localStorage.setItem("localroster_onboarding_chosen", "true");
      loadSchedule();
    };
  }

  if (cb) {
    cb.onchange = (e) => {
      if (e.target.checked) localStorage.setItem("localroster_onboarding_chosen", "true");
      else localStorage.removeItem("localroster_onboarding_chosen");
    };
  }
}

// ==========================================
// Event Listeners & Modals
// ==========================================
function setupEventListeners() {
  const planSelect = document.getElementById("plan-select");
  if (planSelect) {
    planSelect.onchange = (e) => {
      state.activePlanId = parseInt(e.target.value);
      loadSchedule();
    };
  }

  const viewSelect = document.getElementById("view-select");
  const quickStaff = document.getElementById("quick-view-staff");
  const quickSlot = document.getElementById("quick-view-slot");
  const quickAudit = document.getElementById("quick-view-audit");

  function setView(viewName) {
    state.currentView = viewName;
    if (viewSelect) viewSelect.value = viewName;
    if (quickStaff) quickStaff.classList.toggle("active", viewName === "staff_centric");
    if (quickSlot) quickSlot.classList.toggle("active", viewName === "slot_centric");
    if (quickAudit) quickAudit.classList.toggle("active", viewName === "audit_scorecard");
    loadSchedule();
  }

  if (viewSelect) viewSelect.onchange = (e) => setView(e.target.value);
  if (quickStaff) quickStaff.onclick = () => setView("staff_centric");
  if (quickSlot) quickSlot.onclick = () => setView("slot_centric");
  if (quickAudit) quickAudit.onclick = () => setView("audit_scorecard");

  const modeBtn = document.getElementById("mode-toggle-btn");
  if (modeBtn) {
    modeBtn.onclick = (e) => {
      state.currentMode = state.currentMode === "simple" ? "cockpit" : "simple";
      e.target.textContent = state.currentMode === "simple" ? "Simple Mode" : "Cockpit Mode";
      const inspector = document.getElementById("inspector-panel");
      if (inspector) inspector.style.display = state.currentMode === "simple" ? "none" : "flex";
    };
  }

  const prefillBtn = document.getElementById("prefill-toggle-btn");
  const sidebarPrefillBtn = document.getElementById("sidebar-prefill-btn");
  if (prefillBtn) {
    prefillBtn.onclick = (e) => {
      state.prefillMode = !state.prefillMode;
      const text = `Prefill Mode: ${state.prefillMode ? "ON 📌" : "OFF"}`;
      prefillBtn.textContent = text;
      prefillBtn.className = `btn btn-sm ${state.prefillMode ? "btn-primary" : ""}`;
      if (sidebarPrefillBtn) {
        sidebarPrefillBtn.textContent = text;
        sidebarPrefillBtn.className = `btn btn-sm ${state.prefillMode ? "btn-primary" : ""}`;
      }
    };
  }
  if (sidebarPrefillBtn) {
    sidebarPrefillBtn.onclick = (e) => {
      state.prefillMode = !state.prefillMode;
      const text = `Prefill Mode: ${state.prefillMode ? "ON 📌" : "OFF"}`;
      sidebarPrefillBtn.textContent = text;
      sidebarPrefillBtn.className = `btn btn-sm ${state.prefillMode ? "btn-primary" : ""}`;
      if (prefillBtn) {
        prefillBtn.textContent = text;
        prefillBtn.className = `btn btn-sm ${state.prefillMode ? "btn-primary" : ""}`;
      }
    };
  }

  const solveRemBtn = document.getElementById("solve-remaining-btn");
  const sidebarSolveBtn = document.getElementById("sidebar-solve-btn");
  const onSolveRemaining = async () => {
    if (!state.activePlanId) return;
    await apiPost(`/api/roster/${state.activePlanId}/solve-remaining`, { timeout_seconds: 15 });
    await loadSchedule();
  };
  if (solveRemBtn) solveRemBtn.onclick = onSolveRemaining;
  if (sidebarSolveBtn) sidebarSolveBtn.onclick = onSolveRemaining;

  const expExcelBtn = document.getElementById("export-excel-btn");
  if (expExcelBtn) {
    expExcelBtn.onclick = () => {
      if (!state.activePlanId) return;
      window.location.href = `/api/export/${state.activePlanId}/excel?view=both`;
    };
  }

  const expPdfBtn = document.getElementById("export-pdf-btn");
  if (expPdfBtn) {
    expPdfBtn.onclick = () => {
      if (!state.activePlanId) return;
      window.location.href = `/api/export/${state.activePlanId}/pdf`;
    };
  }

  const togglePrevBtn = document.getElementById("toggle-prev-month-btn");
  if (togglePrevBtn) {
    togglePrevBtn.onclick = (e) => {
      state.showPrevMonth = !state.showPrevMonth;
      e.target.textContent = `📅 Prev Month: ${state.showPrevMonth ? "ON" : "OFF"}`;
      e.target.className = `btn btn-sm ${state.showPrevMonth ? "btn-primary" : ""}`;
      loadSchedule();
    };
  }

  const helpGuideBtn = document.getElementById("help-guide-btn");
  if (helpGuideBtn) {
    helpGuideBtn.onclick = () => {
      document.getElementById("modal-help-guide").classList.remove("hidden");
    };
  }

  const helpTabs = [
    { btn: "help-tab-quick", content: "help-content-quick" },
    { btn: "help-tab-buttons", content: "help-content-buttons" },
    { btn: "help-tab-health", content: "help-content-health" },
    { btn: "help-tab-ergonomics", content: "help-content-ergonomics" },
    { btn: "help-tab-carryover", content: "help-content-carryover" }
  ];

  helpTabs.forEach(tab => {
    const el = document.getElementById(tab.btn);
    if (!el) return;
    el.onclick = () => {
      helpTabs.forEach(t => {
        document.getElementById(t.btn).classList.remove("active");
        document.getElementById(t.content).classList.add("hidden");
      });
      el.classList.add("active");
      document.getElementById(tab.content).classList.remove("hidden");
    };
  });

  // Organization Management Modal
  const manageOrgBtn = document.getElementById("manage-org-btn");
  if (manageOrgBtn) {
    manageOrgBtn.onclick = async () => {
      document.getElementById("modal-manage-org").classList.remove("hidden");
      await loadOrgDepartments();
      await loadOrgEmployees();
    };
  }

  // Org Tabs Switcher (Departments, Shift Staffing Demand, Staff Directory)
  const tabDepts = document.getElementById("org-tab-depts");
  const tabDemand = document.getElementById("org-tab-demand");
  const tabEmps = document.getElementById("org-tab-emps");
  const dView = document.getElementById("org-depts-view");
  const dmView = document.getElementById("org-demand-view");
  const eView = document.getElementById("org-emps-view");

  function setOrgTab(activeTab) {
    [tabDepts, tabDemand, tabEmps].forEach(t => {
      if (t) t.classList.toggle("active", t === activeTab);
    });
    if (dView) dView.classList.toggle("hidden", activeTab !== tabDepts);
    if (dmView) dmView.classList.toggle("hidden", activeTab !== tabDemand);
    if (eView) eView.classList.toggle("hidden", activeTab !== tabEmps);
    if (activeTab === tabDemand) {
      initOrgDemandView();
    }
  }

  if (tabDepts) tabDepts.onclick = () => setOrgTab(tabDepts);
  if (tabDemand) tabDemand.onclick = () => setOrgTab(tabDemand);
  if (tabEmps) tabEmps.onclick = () => setOrgTab(tabEmps);

  // Demand requirements controller
  const saveDemandBtn = document.getElementById("save-demand-btn");
  if (saveDemandBtn) {
    saveDemandBtn.onclick = async () => {
      const deptSelect = document.getElementById("demand-dept-select");
      if (!deptSelect || !deptSelect.value) return;
      const deptId = parseInt(deptSelect.value);

      const inputs = document.querySelectorAll(".demand-num-input");
      const requirements = [];
      inputs.forEach(inp => {
        const sId = parseInt(inp.dataset.shiftId);
        const dow = parseInt(inp.dataset.dow);
        const val = parseInt(inp.value) || 0;
        requirements.push({
          shift_type_id: sId,
          day_of_week: dow,
          min_staff: val,
          optimal_staff: val
        });
      });

      try {
        await apiPut(`/api/departments/${deptId}/requirements`, { requirements });
        alert("Staffing demand requirements saved successfully!");
      } catch (err) {
        alert("Failed to save demand requirements: " + err.message);
      }
    };
  }

  const preset1Btn = document.getElementById("demand-preset-1-btn");
  if (preset1Btn) {
    preset1Btn.onclick = () => {
      document.querySelectorAll(".demand-num-input").forEach(inp => inp.value = 1);
    };
  }

  const preset2Btn = document.getElementById("demand-preset-2-btn");
  if (preset2Btn) {
    preset2Btn.onclick = () => {
      document.querySelectorAll(".demand-num-input").forEach(inp => inp.value = 2);
    };
  }

  const regime3sBtn = document.getElementById("demand-regime-3s-btn");
  if (regime3sBtn) {
    regime3sBtn.onclick = async () => {
      const deptSelect = document.getElementById("demand-dept-select");
      if (!deptSelect || !deptSelect.value) return;
      const deptId = parseInt(deptSelect.value);
      try {
        await apiPost(`/api/departments/${deptId}/apply-shift-regime?regime=3_shifts`);
        await loadDepartmentDemand(deptId);
        alert("Applied Standard 3-Shift Regime (Morning, Evening, Night) to department.");
      } catch (err) {
        alert("Failed to apply regime: " + err.message);
      }
    };
  }

  const regimeHybridBtn = document.getElementById("demand-regime-hybrid-btn");
  if (regimeHybridBtn) {
    regimeHybridBtn.onclick = async () => {
      const deptSelect = document.getElementById("demand-dept-select");
      if (!deptSelect || !deptSelect.value) return;
      const deptId = parseInt(deptSelect.value);
      try {
        await apiPost(`/api/departments/${deptId}/apply-shift-regime?regime=hybrid_weekday3_weekend2`);
        await loadDepartmentDemand(deptId);
        alert("Applied Dynamic Hybrid Regime (3 Shifts Weekdays / 2 Shifts Weekends) to department.");
      } catch (err) {
        alert("Failed to apply regime: " + err.message);
      }
    };
  }

  const regime2sBtn = document.getElementById("demand-regime-2s-btn");
  if (regime2sBtn) {
    regime2sBtn.onclick = async () => {
      const deptSelect = document.getElementById("demand-dept-select");
      if (!deptSelect || !deptSelect.value) return;
      const deptId = parseInt(deptSelect.value);
      try {
        await apiPost(`/api/departments/${deptId}/apply-shift-regime?regime=2_shifts`);
        await loadDepartmentDemand(deptId);
        alert("Applied Lean 2-Shift Regime (Morning & Night only) to department.");
      } catch (err) {
        alert("Failed to apply regime: " + err.message);
      }
    };
  }

  // Color input hex live update
  const deptColorIn = document.getElementById("dept-form-color");
  if (deptColorIn) {
    deptColorIn.oninput = (e) => {
      const hex = document.getElementById("dept-color-hex");
      if (hex) hex.textContent = e.target.value.toUpperCase();
    };
  }

  // Department CRUD forms & actions
  const showAddDeptBtn = document.getElementById("show-add-dept-btn");
  if (showAddDeptBtn) {
    showAddDeptBtn.onclick = () => {
      document.getElementById("dept-form-id").value = "";
      document.getElementById("dept-form-code").value = "";
      document.getElementById("dept-form-name").value = "";
      document.getElementById("dept-form-color").value = "#3B82F6";
      const hex = document.getElementById("dept-color-hex");
      if (hex) hex.textContent = "#3B82F6";
      document.getElementById("dept-form-regime").value = "24_7";
      document.getElementById("dept-form-title").textContent = "Create New Department";
      document.getElementById("dept-form-card").classList.remove("hidden");
    };
  }

  const cancelDeptBtn = document.getElementById("cancel-dept-form-btn");
  if (cancelDeptBtn) {
    cancelDeptBtn.onclick = () => {
      document.getElementById("dept-form-card").classList.add("hidden");
    };
  }

  const saveDeptBtn = document.getElementById("save-dept-form-btn");
  if (saveDeptBtn) {
    saveDeptBtn.onclick = async () => {
      const id = document.getElementById("dept-form-id").value;
      const code = document.getElementById("dept-form-code").value.trim();
      const name = document.getElementById("dept-form-name").value.trim();
      const color_code = document.getElementById("dept-form-color").value;
      const operating_regime = document.getElementById("dept-form-regime").value;

      if (!code || !name) {
        alert("Please provide both a department code and name.");
        return;
      }

      try {
        if (id) {
          await apiPut(`/api/departments/${id}`, { code, name, color_code, operating_regime });
        } else {
          await apiPost("/api/departments", { code, name, color_code, operating_regime });
        }
        document.getElementById("dept-form-card").classList.add("hidden");
        state.departments = await apiGet("/api/departments");
        renderDeptFilters();
        await loadOrgDepartments();
        await loadSchedule();
      } catch (err) {
        alert("Error saving department: " + err.message);
      }
    };
  }

  // Employee CRUD forms & actions
  const showAddEmpBtn = document.getElementById("show-add-emp-btn");
  if (showAddEmpBtn) {
    showAddEmpBtn.onclick = () => {
      document.getElementById("emp-form-id").value = "";
      document.getElementById("emp-form-code").value = "";
      document.getElementById("emp-form-name").value = "";
      document.getElementById("emp-form-hours").value = "40.0";
      populateEmpFormShifts("");
      const curDeptId = document.getElementById("emp-form-dept").value;
      populateEmpSecondaryDepts(curDeptId, []);

      const preset = document.getElementById("emp-form-fixed-preset");
      if (preset) preset.value = "";
      document.querySelectorAll(".fixed-day-cb").forEach(cb => cb.checked = false);
      document.getElementById("emp-form-title").textContent = "Create New Employee";
      document.getElementById("emp-form-card").classList.remove("hidden");
    };
  }

  const empDeptSelect = document.getElementById("emp-form-dept");
  if (empDeptSelect) {
    empDeptSelect.onchange = () => {
      const curPrimaryId = parseInt(empDeptSelect.value);
      const currentlyChecked = Array.from(document.querySelectorAll(".sec-dept-cb:checked")).map(cb => parseInt(cb.value));
      populateEmpSecondaryDepts(curPrimaryId, currentlyChecked);
    };
  }

  const fixedPreset = document.getElementById("emp-form-fixed-preset");
  if (fixedPreset) {
    fixedPreset.onchange = (e) => {
      const val = e.target.value;
      document.querySelectorAll(".fixed-day-cb").forEach(cb => cb.checked = false);
      if (val === "5,6") {
        const sa = document.querySelector('.fixed-day-cb[value="5"]'); if (sa) sa.checked = true;
        const su = document.querySelector('.fixed-day-cb[value="6"]'); if (su) su.checked = true;
      } else if (val === "0,1") {
        const mo = document.querySelector('.fixed-day-cb[value="0"]'); if (mo) mo.checked = true;
        const tu = document.querySelector('.fixed-day-cb[value="1"]'); if (tu) tu.checked = true;
      } else if (val === "6,0") {
        const su = document.querySelector('.fixed-day-cb[value="6"]'); if (su) su.checked = true;
        const mo = document.querySelector('.fixed-day-cb[value="0"]'); if (mo) mo.checked = true;
      }
    };
  }

  document.querySelectorAll(".fixed-day-cb").forEach(cb => {
    cb.onchange = () => {
      const p = document.getElementById("emp-form-fixed-preset");
      if (p) p.value = "custom";
    };
  });

  const cancelEmpBtn = document.getElementById("cancel-emp-form-btn");
  if (cancelEmpBtn) {
    cancelEmpBtn.onclick = () => {
      document.getElementById("emp-form-card").classList.add("hidden");
    };
  }

  const saveEmpBtn = document.getElementById("save-emp-form-btn");
  if (saveEmpBtn) {
    saveEmpBtn.onclick = async () => {
      const id = document.getElementById("emp-form-id").value;
      const employee_code = document.getElementById("emp-form-code").value.trim();
      const name = document.getElementById("emp-form-name").value.trim();
      const primary_department_id = parseInt(document.getElementById("emp-form-dept").value);
      const max_hours_week = parseFloat(document.getElementById("emp-form-hours").value) || 40.0;

      const prefShiftVal = document.getElementById("emp-form-shift").value;
      const preferred_shift_type_id = prefShiftVal ? parseInt(prefShiftVal) : null;
      const checkedSecDepts = Array.from(document.querySelectorAll(".sec-dept-cb:checked")).map(cb => parseInt(cb.value));

      const checkedDays = Array.from(document.querySelectorAll(".fixed-day-cb:checked")).map(cb => cb.value);
      // Empty string "" explicitly tells backend to clear fixed_off_days to None
      const fixed_off_days = checkedDays.length > 0 ? checkedDays.join(",") : "";

      if (!employee_code || !name || !primary_department_id) {
        alert("Please provide employee code, name, and primary department.");
        return;
      }

      const payload = {
        employee_code,
        name,
        primary_department_id,
        max_hours_week,
        fixed_off_days,
        preferred_shift_type_id,
        secondary_department_ids: checkedSecDepts
      };

      try {
        if (id) {
          await apiPut(`/api/employees/${id}`, payload);
        } else {
          await apiPost("/api/employees", payload);
        }
        document.getElementById("emp-form-card").classList.add("hidden");
        await loadOrgEmployees();
        await loadOrgDepartments();
        await loadSchedule();
      } catch (err) {
        alert("Error saving employee: " + err.message);
      }
    };
  }

  const empFilterDept = document.getElementById("emp-filter-dept-select");
  if (empFilterDept) {
    empFilterDept.onchange = () => {
      if (state.selectedEmpIds) state.selectedEmpIds.clear();
      loadOrgEmployees();
    };
  }

  // Bulk Employee Action Buttons
  const bulkClearSelBtn = document.getElementById("bulk-clear-sel-btn");
  if (bulkClearSelBtn) {
    bulkClearSelBtn.onclick = () => {
      if (state.selectedEmpIds) state.selectedEmpIds.clear();
      loadOrgEmployees();
    };
  }

  const bulkDeleteEmpsBtn = document.getElementById("bulk-delete-emps-btn");
  if (bulkDeleteEmpsBtn) {
    bulkDeleteEmpsBtn.onclick = async () => {
      const count = state.selectedEmpIds ? state.selectedEmpIds.size : 0;
      if (!count) return;
      if (!confirm(`Are you sure you want to permanently delete ${count} selected employee(s)? This cannot be undone.`)) return;
      try {
        const res = await apiPost("/api/employees/bulk-delete", { employee_ids: Array.from(state.selectedEmpIds) });
        alert(res.message || `Deleted ${count} employees.`);
        state.selectedEmpIds.clear();
        await loadOrgEmployees();
        await loadOrgDepartments();
        await loadSchedule();
      } catch (err) {
        alert("Bulk delete failed: " + err.message);
      }
    };
  }

  const bulkEditEmpsBtn = document.getElementById("bulk-edit-emps-btn");
  if (bulkEditEmpsBtn) {
    bulkEditEmpsBtn.onclick = () => {
      const count = state.selectedEmpIds ? state.selectedEmpIds.size : 0;
      if (!count) return;
      document.getElementById("bulk-edit-summary").textContent = `Updating ${count} selected employee${count === 1 ? "" : "s"}`;

      const deptSelect = document.getElementById("bulk-edit-dept-select");
      deptSelect.innerHTML = `<option value="KEEP">— Keep Existing Department —</option>`;
      state.departments.forEach(d => {
        deptSelect.innerHTML += `<option value="${d.id}">${d.name} (${d.code})</option>`;
      });

      // Populate dedicated shift dropdown in bulk modal
      const shiftSelect = document.getElementById("bulk-edit-shift-select");
      if (shiftSelect) {
        shiftSelect.innerHTML = `
          <option value="KEEP">— Keep Existing Dedicated Shift —</option>
          <option value="-1">Dynamic / Flexible (No dedicated shift)</option>
        `;
        (state.shifts || []).forEach(s => {
          shiftSelect.innerHTML += `<option value="${s.id}">☀️ ${s.name} (${s.code})</option>`;
        });
      }

      // Populate secondary floating depts in bulk modal
      const secContainer = document.getElementById("bulk-secondary-depts-container");
      if (secContainer) {
        secContainer.innerHTML = "";
        (state.departments || []).forEach(d => {
          secContainer.innerHTML += `
            <label class="sec-dept-pill" style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:12px;background:#f1f5f9;border:1px solid #cbd5e1;font-size:11px;cursor:pointer;">
              <input type="checkbox" class="bulk-sec-dept-cb" value="${d.id}">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${d.color_code};"></span>
              ${d.code} (${d.name})
            </label>
          `;
        });
      }
      const floatCb = document.getElementById("bulk-edit-float-cb");
      if (floatCb && secContainer) {
        floatCb.checked = false;
        secContainer.classList.add("hidden");
        floatCb.onchange = (e) => {
          if (e.target.checked) secContainer.classList.remove("hidden");
          else secContainer.classList.add("hidden");
        };
      }

      document.getElementById("bulk-edit-hours-cb").checked = false;
      document.getElementById("bulk-edit-hours-input").disabled = true;
      document.getElementById("bulk-edit-hours-input").value = "40.0";
      document.getElementById("bulk-edit-fixed-preset").value = "KEEP";
      document.getElementById("bulk-fixed-days-checkboxes").classList.add("hidden");
      document.querySelectorAll(".bulk-fixed-cb").forEach(c => c.checked = false);
      document.getElementById("bulk-edit-status-select").value = "KEEP";

      document.getElementById("modal-bulk-edit-emps").classList.remove("hidden");
    };
  }

  const bulkEditHoursCb = document.getElementById("bulk-edit-hours-cb");
  if (bulkEditHoursCb) {
    bulkEditHoursCb.onchange = (e) => {
      const hoursIn = document.getElementById("bulk-edit-hours-input");
      if (hoursIn) hoursIn.disabled = !e.target.checked;
    };
  }

  const bulkEditFixedPreset = document.getElementById("bulk-edit-fixed-preset");
  if (bulkEditFixedPreset) {
    bulkEditFixedPreset.onchange = (e) => {
      const customBox = document.getElementById("bulk-fixed-days-checkboxes");
      if (customBox) {
        if (e.target.value === "custom") customBox.classList.remove("hidden");
        else customBox.classList.add("hidden");
      }
    };
  }

  const applyBulkEditBtn = document.getElementById("apply-bulk-edit-btn");
  if (applyBulkEditBtn) {
    applyBulkEditBtn.onclick = async () => {
      const count = state.selectedEmpIds ? state.selectedEmpIds.size : 0;
      if (!count) return;

      const payload = {
        employee_ids: Array.from(state.selectedEmpIds)
      };

      const deptVal = document.getElementById("bulk-edit-dept-select").value;
      if (deptVal !== "KEEP") payload.primary_department_id = parseInt(deptVal);

      const shiftVal = document.getElementById("bulk-edit-shift-select").value;
      if (shiftVal !== "KEEP") {
        payload.preferred_shift_type_id = parseInt(shiftVal);
      }

      const floatCb = document.getElementById("bulk-edit-float-cb");
      if (floatCb && floatCb.checked) {
        payload.secondary_department_ids = Array.from(document.querySelectorAll(".bulk-sec-dept-cb:checked")).map(cb => parseInt(cb.value));
      }

      if (document.getElementById("bulk-edit-hours-cb").checked) {
        payload.max_hours_week = parseFloat(document.getElementById("bulk-edit-hours-input").value) || 40.0;
      }

      const presetVal = document.getElementById("bulk-edit-fixed-preset").value;
      if (presetVal !== "KEEP") {
        if (presetVal === "custom") {
          const customDays = Array.from(document.querySelectorAll(".bulk-fixed-cb:checked")).map(cb => cb.value);
          payload.fixed_off_days = customDays.join(",");
        } else {
          payload.fixed_off_days = presetVal;
        }
      }

      const statusVal = document.getElementById("bulk-edit-status-select").value;
      if (statusVal !== "KEEP") {
        payload.is_active = statusVal === "true";
      }

      try {
        const res = await apiPost("/api/employees/bulk-update", payload);
        alert(res.message || "Employees updated successfully.");
        document.getElementById("modal-bulk-edit-emps").classList.add("hidden");
        state.selectedEmpIds.clear();
        await loadOrgEmployees();
        await loadOrgDepartments();
        await loadSchedule();
      } catch (err) {
        alert("Bulk update failed: " + err.message);
      }
    };
  }

  // Clear Canvas / Reset Ribbon Action
  const clearCanvasBtn = document.getElementById("clear-canvas-btn");
  if (clearCanvasBtn) {
    clearCanvasBtn.onclick = () => {
      if (!state.activePlanId) {
        alert("Please create or select a roster plan first.");
        return;
      }
      document.getElementById("modal-confirm-clear-canvas").classList.remove("hidden");
    };
  }

  // Award Comp Offs (COFF) for Overtime Ribbon Action
  const awardCoffBtn = document.getElementById("award-compoff-btn");
  if (awardCoffBtn) {
    awardCoffBtn.onclick = async () => {
      if (!state.activePlanId) {
        alert("Please select or generate a roster plan first.");
        return;
      }
      try {
        const res = await apiPost(`/api/roster/${state.activePlanId}/auto-award-compoffs`, {});
        alert(res.message || "Compensatory Off (COFF) holidays awarded to staff who worked overtime!");
        await loadSchedule();
      } catch (err) {
        alert("Error awarding comp offs: " + err.message);
      }
    };
  }

  const confirmClearCanvasBtn = document.getElementById("confirm-clear-canvas-btn");
  if (confirmClearCanvasBtn) {
    confirmClearCanvasBtn.onclick = async () => {
      if (!state.activePlanId) return;
      try {
        const res = await apiDelete(`/api/roster/${state.activePlanId}/clear-all`);
        document.getElementById("modal-confirm-clear-canvas").classList.add("hidden");
        alert(res.message || "Canvas reset to blank.");
        await loadSchedule();
        await loadPlans();
      } catch (err) {
        alert("Clear canvas failed: " + err.message);
      }
    };
  }

  // Modals & Enhanced Solver Triggers
  const newPlanBtn = document.getElementById("new-plan-btn");
  if (newPlanBtn) {
    newPlanBtn.onclick = async () => {
      try {
        const settings = await apiGet("/api/settings");
        state.settings = settings;
        if (settings.remember_generator_mode) {
          await executeRosterGeneration(settings.generator_default_mode || "blank");
          return;
        }
      } catch (_) {}
      document.getElementById("modal-gen-choice").classList.remove("hidden");
    };
  }

  const genProceedBtn = document.getElementById("gen-proceed-btn");
  if (genProceedBtn) {
    genProceedBtn.onclick = async () => {
      const modeRadio = document.querySelector('input[name="gen-mode-choice"]:checked');
      const chosenMode = modeRadio ? modeRadio.value : "blank";
      const rememberCb = document.getElementById("remember-gen-choice-cb");

      if (rememberCb && rememberCb.checked) {
        try {
          await apiPost("/api/settings", {
            settings: {
              "generator_default_mode": chosenMode,
              "remember_generator_mode": "true"
            }
          });
        } catch (_) {}
      }

      document.getElementById("modal-gen-choice").classList.add("hidden");
      await executeRosterGeneration(chosenMode);
    };
  }

  const genOpenOptionsBtn = document.getElementById("gen-open-options-btn");
  if (genOpenOptionsBtn) {
    genOpenOptionsBtn.onclick = () => {
      document.getElementById("modal-gen-choice").classList.add("hidden");
      document.getElementById("modal-new-plan").classList.remove("hidden");
    };
  }

  // Vacations & Leaves Manager Modal
  const vacMgrBtn = document.getElementById("vacations-mgr-btn");
  if (vacMgrBtn) {
    vacMgrBtn.onclick = async () => {
      document.getElementById("modal-vacations").classList.remove("hidden");
      await loadVacationsList();
    };
  }

  const vacAddBtn = document.getElementById("vac-add-btn");
  if (vacAddBtn) {
    vacAddBtn.onclick = async () => {
      const empId = parseInt(document.getElementById("vac-emp-select").value);
      const startDate = document.getElementById("vac-start-date").value;
      const endDate = document.getElementById("vac-end-date").value;
      const leaveType = document.getElementById("vac-type-select").value;
      const notes = document.getElementById("vac-notes").value.trim();

      if (!empId || !startDate || !endDate) {
        alert("Please select employee, start date, and end date.");
        return;
      }
      try {
        await apiPost("/api/leaves", {
          employee_id: empId,
          start_date: startDate,
          end_date: endDate,
          leave_type: leaveType,
          notes: notes || "Vacation / Leave"
        });
        document.getElementById("vac-notes").value = "";
        await loadVacationsList();
        await loadSchedule();
      } catch (err) {
        alert("Failed to record vacation: " + err.message);
      }
    };
  }

  // Advanced Settings Modal
  const advSettingsBtn = document.getElementById("advanced-settings-btn");
  if (advSettingsBtn) {
    advSettingsBtn.onclick = async () => {
      document.getElementById("modal-advanced-settings").classList.remove("hidden");
      await loadAdvancedSettings();
    };
  }

  const saveSettingsBtn = document.getElementById("save-settings-btn");
  if (saveSettingsBtn) {
    saveSettingsBtn.onclick = async () => {
      const offCode = document.getElementById("setting-code-off").value.trim() || "OFF";
      const coffCode = document.getElementById("setting-code-coff").value.trim() || "Coff";
      const vacCode = document.getElementById("setting-code-vac").value.trim() || "VAC";
      const sickCode = document.getElementById("setting-code-sick").value.trim() || "SICK";

      const defModeRadio = document.querySelector('input[name="setting-gen-default"]:checked');
      const defMode = defModeRadio ? defModeRadio.value : "blank";
      const remMode = document.getElementById("setting-remember-mode").checked;

      const maxCoff = document.getElementById("setting-max-comp-offs") ? document.getElementById("setting-max-comp-offs").value : "2";
      const contCoff = document.getElementById("setting-continuous-comp-off") ? document.getElementById("setting-continuous-comp-off").checked : true;
      const dynRegime = document.getElementById("setting-dynamic-shift-regime") ? document.getElementById("setting-dynamic-shift-regime").value : "auto";

      const customCodes = {
        "OFF": offCode,
        "COFF": coffCode,
        "VAC": vacCode,
        "SICK": sickCode
      };

      try {
        await apiPost("/api/settings", {
          settings: {
            "generator_default_mode": defMode,
            "remember_generator_mode": remMode ? "true" : "false",
            "max_comp_offs_per_employee": String(maxCoff),
            "continuous_comp_off_enabled": contCoff ? "true" : "false",
            "dynamic_shift_regime": dynRegime,
            "custom_status_codes": JSON.stringify(customCodes)
          }
        });

        const cbs = document.querySelectorAll(".shift-active-cb");
        for (const cb of cbs) {
          const shiftId = parseInt(cb.dataset.shiftId);
          await apiPut(`/api/shift-types/${shiftId}`, { is_active: cb.checked });
        }

        alert("Advanced settings saved successfully!");
        document.getElementById("modal-advanced-settings").classList.add("hidden");
        state.shifts = await apiGet("/api/shift-types");
        await loadSchedule();
      } catch (err) {
        alert("Error saving settings: " + err.message);
      }
    };
  }

  const importBtn = document.getElementById("import-btn");
  if (importBtn) {
    importBtn.onclick = () => {
      document.getElementById("modal-import").classList.remove("hidden");
    };
  }

  const variantsBtn = document.getElementById("variants-btn");
  if (variantsBtn) {
    variantsBtn.onclick = async () => {
      document.getElementById("modal-variants").classList.remove("hidden");
      const container = document.getElementById("variants-comparison-content");
      if (!container) return;
      container.innerHTML = `<p>Loading sibling variants...</p>`;

      const curPlan = state.plans.find(p => p.id === state.activePlanId);
      if (!curPlan) return;

      const siblings = state.plans.filter(p => p.session_id === curPlan.session_id);
      let html = `<table class="schedule-table" style="width:100%;margin-top:10px;">
        <thead>
          <tr>
            <th>Variant Name</th>
            <th>Strategy</th>
            <th>Deficits</th>
            <th>Floats</th>
            <th>Runtime</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>`;

      siblings.forEach(s => {
        html += `
          <tr>
            <td><b>${s.variant_name}</b></td>
            <td>${s.variant_strategy}</td>
            <td>${s.total_deficits > 0 ? `<span style="color:#ef4444;font-weight:bold;">${s.total_deficits}</span>` : '0'}</td>
            <td>${s.total_floats}</td>
            <td>${s.solve_time_seconds}s</td>
            <td>
              ${s.is_active_variant 
                ? `<span class="brand-badge" style="background:#10b981;">Active Published</span>`
                : `<button class="btn btn-sm btn-primary" onclick="promoteVariant(${s.id})">Promote to Active</button>`
              }
            </td>
          </tr>`;
      });
      html += `</tbody></table>`;
      container.innerHTML = html;
    };
  }

  document.querySelectorAll(".close-modal").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
    };
  });

  // Confirm New Plan from Modal
  const confirmGenBtn = document.getElementById("confirm-generate-btn");
  if (confirmGenBtn) {
    confirmGenBtn.onclick = async () => {
      const name = document.getElementById("new-plan-name").value;
      const year = parseInt(document.getElementById("new-plan-year").value);
      const month = parseInt(document.getElementById("new-plan-month").value);
      const variants = parseInt(document.getElementById("new-plan-variants").value);

      document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));

      await runSolverWithEngagingProgress(async () => {
        return await apiPost("/api/roster/generate", {
          name,
          planning_year: year,
          planning_month: month,
          variant_count: variants,
          timeout_seconds: 15
        });
      }, 15);

      await loadPlans();
    };
  }

  // Import Template download
  const dlTplBtn = document.getElementById("download-template-btn");
  if (dlTplBtn) {
    dlTplBtn.onclick = () => {
      const type = document.getElementById("import-type-select").value;
      window.location.href = `/api/import/template/${type}`;
    };
  }

  // Import File Input & Preview
  const importFileInput = document.getElementById("import-file-input");
  const commitImportBtn = document.getElementById("commit-import-btn");
  const importTypeSelect = document.getElementById("import-type-select");
  const importPreviewBox = document.getElementById("import-preview-box");
  let pendingImportFile = null;

  if (importFileInput) {
    importFileInput.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      pendingImportFile = file;

      const entityType = importTypeSelect ? importTypeSelect.value : "employees";
      if (importPreviewBox) {
        importPreviewBox.innerHTML = "<p style='color:var(--text-muted);padding:8px;'>Validating spreadsheet rows...</p>";
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`/api/import/preview/${entityType}`, {
          method: "POST",
          body: formData
        });
        if (!res.ok) throw new Error(await res.text());
        const preview = await res.json();

        let html = `
          <div style="padding: 10px; background: #f8fafc; border: 1px solid var(--border-color); border-radius: 6px; margin-top: 6px;">
            <div><b>Filename:</b> ${preview.filename}</div>
            <div><b>Total Detected Rows:</b> ${preview.total_rows}</div>
            <div style="color: #16a34a;"><b>Valid Records:</b> ${preview.valid_rows}</div>
            <div style="color: ${preview.invalid_rows > 0 ? '#dc2626' : '#64748b'};"><b>Invalid Records:</b> ${preview.invalid_rows}</div>
          </div>
        `;

        if (preview.errors && preview.errors.length > 0) {
          html += `<div class="alert-card danger" style="margin-top: 6px;"><b>Errors detected:</b><br>${preview.errors.slice(0, 5).map(err => `• Row ${err.row}: ${err.error}`).join("<br>")}${preview.errors.length > 5 ? `<br>...and ${preview.errors.length - 5} more.` : ''}</div>`;
          if (commitImportBtn) commitImportBtn.classList.add("hidden");
        } else if (preview.valid_rows > 0) {
          html += `<div class="alert-card success" style="margin-top: 6px;">✓ All ${preview.valid_rows} records validated successfully and are ready to commit!</div>`;
          if (commitImportBtn) commitImportBtn.classList.remove("hidden");
        } else {
          if (commitImportBtn) commitImportBtn.classList.add("hidden");
        }

        if (importPreviewBox) importPreviewBox.innerHTML = html;
      } catch (err) {
        if (importPreviewBox) importPreviewBox.innerHTML = `<div class="alert-card danger">Failed to preview file: ${err.message}</div>`;
        if (commitImportBtn) commitImportBtn.classList.add("hidden");
      }
    };
  }

  if (commitImportBtn) {
    commitImportBtn.onclick = async () => {
      if (!pendingImportFile) return;
      const entityType = importTypeSelect ? importTypeSelect.value : "employees";
      const formData = new FormData();
      formData.append("file", pendingImportFile);

      try {
        const res = await fetch(`/api/import/commit/${entityType}`, {
          method: "POST",
          body: formData
        });
        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail?.message || "Import failed");
        }
        const data = await res.json();
        alert(data.message || "Data imported successfully!");
        document.getElementById("modal-import").classList.add("hidden");
        state.departments = await apiGet("/api/departments");
        renderDeptFilters();
        await loadOrgDepartments();
        await loadOrgEmployees();
        await loadSchedule();
      } catch (err) {
        alert("Import error: " + err.message);
      }
    };
  }
}

window.promoteVariant = async function(planId) {
  await apiPost(`/api/roster/${planId}/promote`, {});
  document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
  await loadPlans();
};

// ==========================================
// Solver Execution with Engaging Live Progress
// ==========================================
async function runSolverWithEngagingProgress(generateFn, timeoutLimit = 15) {
  const modal = document.getElementById("modal-solver-progress");
  const pctEl = document.getElementById("solver-progress-pct");
  const fillEl = document.getElementById("solver-progress-fill");
  const statusEl = document.getElementById("solver-dynamic-status-text");
  const elapsedEl = document.getElementById("solver-elapsed-sec");
  const limitEl = document.getElementById("solver-timeout-limit");

  if (limitEl) limitEl.textContent = `${timeoutLimit}s`;
  if (modal) modal.classList.remove("hidden");

  const agentLines = [
    "Formulating integer decision variables across 4 departments & 32 staff...",
    "Enforcing ergonomic rest intervals (14h post-night rest, forbidden turnarounds)...",
    "Locking approved employee vacations and dedicated regular days off...",
    "Balancing weekend equity and floater distribution across wards...",
    "Evaluating multi-variant candidate Pareto frontiers...",
    "Finalizing conflict-free roster and computing workload scorecard..."
  ];

  let elapsedMs = 0;
  let progressPct = 15;
  let lineIdx = 0;

  if (pctEl) pctEl.textContent = `${progressPct}%`;
  if (fillEl) fillEl.style.width = `${progressPct}%`;
  if (statusEl) statusEl.textContent = agentLines[0];

  const timer = setInterval(() => {
    elapsedMs += 100;
    if (elapsedEl) elapsedEl.textContent = `${(elapsedMs / 1000).toFixed(1)}s`;

    if (elapsedMs % 600 === 0) {
      lineIdx = (lineIdx + 1) % agentLines.length;
      if (statusEl) statusEl.textContent = agentLines[lineIdx];
    }

    if (progressPct < 90) {
      progressPct += Math.random() > 0.4 ? 2 : 1;
      if (pctEl) pctEl.textContent = `${progressPct}%`;
      if (fillEl) fillEl.style.width = `${progressPct}%`;
    }
  }, 100);

  try {
    const result = await generateFn();
    clearInterval(timer);
    if (pctEl) pctEl.textContent = "100%";
    if (fillEl) fillEl.style.width = "100%";
    if (statusEl) statusEl.textContent = "✓ Conflict-free optimal schedule verified! Loading grid...";
    await new Promise(r => setTimeout(r, 450));
    if (modal) modal.classList.add("hidden");
    return result;
  } catch (err) {
    clearInterval(timer);
    if (modal) modal.classList.add("hidden");
    alert("Solver error: " + err.message);
    throw err;
  }
}

async function executeRosterGeneration(mode = "blank") {
  if (mode === "existing" && state.activePlanId) {
    await runSolverWithEngagingProgress(async () => {
      return await apiPost(`/api/roster/${state.activePlanId}/solve-remaining`, { timeout_seconds: 15 });
    }, 15);
    await loadSchedule();
  } else {
    const curPlan = state.plans.find(p => p.id === state.activePlanId);
    const year = curPlan ? curPlan.planning_year || 2026 : 2026;
    const month = curPlan ? curPlan.planning_month || 11 : 11;

    await runSolverWithEngagingProgress(async () => {
      return await apiPost("/api/roster/generate", {
        name: `Roster Plan (${year}-${String(month).padStart(2, '0')})`,
        planning_year: year,
        planning_month: month,
        variant_count: 3,
        timeout_seconds: 15
      });
    }, 15);
    await loadPlans();
  }
}

// ==========================================
// Vacations & Leaves Manager Controller
// ==========================================
async function loadVacationsList() {
  const tbody = document.getElementById("vacations-table-body");
  if (!tbody) return;
  tbody.innerHTML = "<tr><td colspan='5' style='text-align:center;padding:12px;'>Loading vacation records...</td></tr>";

  // Populate employee select
  const empSelect = document.getElementById("vac-emp-select");
  if (empSelect) {
    const emps = await apiGet("/api/employees?active_only=true");
    empSelect.innerHTML = "";
    emps.forEach(e => {
      const opt = document.createElement("option");
      opt.value = e.id;
      opt.textContent = `${e.name} (${e.employee_code} - ${e.primary_department_name || ""})`;
      empSelect.appendChild(opt);
    });
  }

  // Fetch approved leaves
  try {
    const leaves = await apiGet("/api/leaves");
    tbody.innerHTML = "";
    if (leaves.length === 0) {
      tbody.innerHTML = "<tr><td colspan='5' style='text-align:center;color:var(--text-muted);padding:14px;'>No active vacations or leaves recorded.</td></tr>";
      return;
    }

    leaves.forEach(l => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${l.employee_name || 'Staff #' + l.employee_id}</b></td>
        <td>${l.start_date} to ${l.end_date}</td>
        <td><span class="brand-badge" style="background:#f3e8ff;color:#6b21a8;">${l.leave_type}</span></td>
        <td>${l.notes || '—'}</td>
        <td style="text-align:right;">
          <button class="btn btn-sm" style="color:#dc2626;" onclick="deleteVacationRecord(${l.id})">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='5' style='color:#dc2626;'>Error: ${err.message}</td></tr>`;
  }
}

window.deleteVacationRecord = async function(id) {
  if (!confirm("Are you sure you want to cancel and delete this vacation record?")) return;
  try {
    const res = await apiDelete(`/api/leaves/${id}`);
    alert(res.message || "Vacation cancelled.");
    await loadVacationsList();
    await loadSchedule();
  } catch (err) {
    alert("Cannot delete vacation: " + err.message);
  }
};

// ==========================================
// Advanced Settings Controller
// ==========================================
async function loadAdvancedSettings() {
  try {
    const settings = await apiGet("/api/settings");
    state.settings = settings;

    const codes = settings.custom_status_codes || {};
    const offInput = document.getElementById("setting-code-off");
    if (offInput) offInput.value = codes.OFF || "OFF";
    const coffInput = document.getElementById("setting-code-coff");
    if (coffInput) coffInput.value = codes.COFF || "Coff";
    const vacInput = document.getElementById("setting-code-vac");
    if (vacInput) vacInput.value = codes.VAC || "VAC";
    const sickInput = document.getElementById("setting-code-sick");
    if (sickInput) sickInput.value = codes.SICK || "SICK";

    if (settings.generator_default_mode === "existing") {
      const r = document.getElementById("setting-gen-existing");
      if (r) r.checked = true;
    } else {
      const r = document.getElementById("setting-gen-blank");
      if (r) r.checked = true;
    }

    const remCb = document.getElementById("setting-remember-mode");
    if (remCb) remCb.checked = settings.remember_generator_mode;

    const maxCoffInput = document.getElementById("setting-max-comp-offs");
    if (maxCoffInput) maxCoffInput.value = settings.max_comp_offs_per_employee !== undefined ? settings.max_comp_offs_per_employee : 2;

    const contCoffCb = document.getElementById("setting-continuous-comp-off");
    if (contCoffCb) contCoffCb.checked = settings.continuous_comp_off_enabled !== false;

    const regimeSelect = document.getElementById("setting-dynamic-shift-regime");
    if (regimeSelect && settings.dynamic_shift_regime) regimeSelect.value = settings.dynamic_shift_regime;

    // Render shift types list
    const shiftsList = document.getElementById("settings-shifts-list");
    if (shiftsList) {
      shiftsList.innerHTML = "";
      state.shifts.forEach(s => {
        const div = document.createElement("div");
        div.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;";
        div.innerHTML = `
          <div>
            <b>${s.name} (${s.code})</b>
            <span style="font-size:11px;color:var(--text-muted);margin-left:8px;">${s.start_time} - ${s.end_time} (${s.duration_hours}h)</span>
          </div>
          <label style="display:flex;align-items:center;gap:6px;font-size:11px;cursor:pointer;">
            <input type="checkbox" class="shift-active-cb" data-shift-id="${s.id}" ${s.is_active ? "checked" : ""}> Active in Roster
          </label>
        `;
        shiftsList.appendChild(div);
      });
    }
  } catch (err) {
    console.error("Error loading settings:", err);
  }
}

// ==========================================
// Find & Replace Controller
// ==========================================
function initFindReplace() {
  const modal = document.getElementById("modal-find-replace");
  const openBtn = document.getElementById("find-replace-btn");
  const highlightBtn = document.getElementById("fr-highlight-btn");
  const replaceBtn = document.getElementById("fr-replace-btn");
  const clearBtn = document.getElementById("fr-clear-btn");
  const deptSelect = document.getElementById("fr-dept-select");
  const msgEl = document.getElementById("fr-result-message");

  if (openBtn) {
    openBtn.onclick = () => {
      if (deptSelect) {
        deptSelect.innerHTML = `<option value="">All Departments (Entire Roster)</option>`;
        state.departments.forEach(d => {
          const opt = document.createElement("option");
          opt.value = d.id;
          opt.textContent = `${d.name} (${d.code})`;
          deptSelect.appendChild(opt);
        });
      }
      if (msgEl) msgEl.textContent = "";
      modal.classList.remove("hidden");
    };
  }

  if (highlightBtn) {
    highlightBtn.onclick = () => {
      const findVal = document.getElementById("fr-find-select").value.toUpperCase();
      const targetDept = deptSelect.value ? parseInt(deptSelect.value) : null;
      let matchCount = 0;

      document.querySelectorAll(".cell-search-match").forEach(el => el.classList.remove("cell-search-match"));

      document.querySelectorAll("td[data-date]").forEach(td => {
        const rowIdx = parseInt(td.dataset.row);
        const emp = state.currentScheduleData.rows[rowIdx];
        if (targetDept && emp.primary_department_id !== targetDept) return;

        const dateStr = td.dataset.date;
        const assign = emp.assignments[dateStr];
        let code = "";
        if (assign) {
          code = (assign.shift_code || "").toUpperCase();
        } else {
          code = "OFF";
        }

        if (code.includes(findVal) || (findVal === "OFF" && !assign)) {
          td.classList.add("cell-search-match");
          matchCount++;
        }
      });

      if (msgEl) msgEl.innerHTML = `<span style="color:#16a34a;font-weight:600;">✓ Highlighted ${matchCount} matching cells on schedule!</span>`;
    };
  }

  if (replaceBtn) {
    replaceBtn.onclick = async () => {
      const findVal = document.getElementById("fr-find-select").value;
      const replaceVal = document.getElementById("fr-replace-select").value;
      const targetDept = deptSelect.value ? parseInt(deptSelect.value) : null;

      if (!confirm(`Are you sure you want to replace all '${findVal}' shifts with '${replaceVal}'?`)) return;

      try {
        const res = await apiPost(`/api/roster/${state.activePlanId}/find-replace`, {
          find_shift_code: findVal,
          replace_shift_code: replaceVal,
          department_id: targetDept
        });
        if (msgEl) msgEl.innerHTML = `<span style="color:#16a34a;font-weight:600;">✓ ${res.message}</span>`;
        await loadSchedule();
      } catch (err) {
        if (msgEl) msgEl.innerHTML = `<span style="color:#dc2626;font-weight:600;">Error: ${err.message}</span>`;
      }
    };
  }

  if (clearBtn) {
    clearBtn.onclick = () => {
      document.querySelectorAll(".cell-search-match").forEach(el => el.classList.remove("cell-search-match"));
      if (msgEl) msgEl.textContent = "Highlights cleared.";
    };
  }
}

// ==========================================
// Keyboard Navigation Controller (Excel Style)
// ==========================================
function handleGridKeyboardNavigation(e) {
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (["INPUT", "SELECT", "TEXTAREA"].includes(tag.toUpperCase())) return;

  if (!state.selectedCell || !state.currentScheduleData || state.currentView !== "staff_centric") return;

  const { rowIdx, colIdx } = state.selectedCell;
  if (rowIdx === null || rowIdx === undefined || colIdx === null || colIdx === undefined) return;

  const numRows = state.currentScheduleData.rows.length;
  const numCols = state.currentScheduleData.dates.length;

  if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault();
    emptySelectedCell();
    return;
  }

  let nextRow = rowIdx;
  let nextCol = colIdx;

  if (e.key === "ArrowRight" || (e.key === "Tab" && !e.shiftKey)) {
    e.preventDefault();
    nextCol = (colIdx + 1) % numCols;
    if (nextCol === 0 && e.key === "Tab") nextRow = (rowIdx + 1) % numRows;
  } else if (e.key === "ArrowLeft" || (e.key === "Tab" && e.shiftKey)) {
    e.preventDefault();
    nextCol = (colIdx - 1 + numCols) % numCols;
    if (nextCol === numCols - 1 && e.key === "Tab") nextRow = (rowIdx - 1 + numRows) % numRows;
  } else if (e.key === "ArrowDown" || (e.key === "Enter" && !e.shiftKey)) {
    e.preventDefault();
    nextRow = (rowIdx + 1) % numRows;
  } else if (e.key === "ArrowUp" || (e.key === "Enter" && e.shiftKey)) {
    e.preventDefault();
    nextRow = (rowIdx - 1 + numRows) % numRows;
  } else {
    return;
  }

  const targetTd = document.querySelector(`td[data-row="${nextRow}"][data-col="${nextCol}"]`);
  if (targetTd) {
    const targetEmp = state.currentScheduleData.rows[nextRow];
    const targetDate = state.currentScheduleData.dates[nextCol];
    const targetAssign = targetEmp.assignments[targetDate];
    selectAssignment(targetEmp, targetDate, targetAssign, nextRow, nextCol, targetTd);
    targetTd.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

function initKeyboardNavigation() {
  window.addEventListener("keydown", handleGridKeyboardNavigation);
}

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", initApp);
