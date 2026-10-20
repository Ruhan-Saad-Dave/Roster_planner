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

    // Update Health Banner
    const deficits = await apiGet(`/api/roster/${state.activePlanId}/deficits`);
    if (deficits.length === 0) {
      updateHealthBanner("green", "🟢 ROSTER HEALTH: ALL CLEAR — 100% shifts staffed. Zero ergonomic violations.");
    } else {
      updateHealthBanner("red", `🔴 ROSTER HEALTH: ${deficits.length} Shortages Detected. Click to inspect recommendations.`, deficits);
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
function updateHealthBanner(type, message, deficits = []) {
  const banner = document.getElementById("health-banner");
  if (banner) {
    banner.className = `health-banner ${type}`;
    const msgEl = document.getElementById("health-message");
    if (msgEl) msgEl.textContent = message;
  }

  const statusPill = document.getElementById("status-health-pill");
  if (statusPill) {
    if (type === "green") {
      statusPill.textContent = "🟢 100% Staffed";
      statusPill.style.color = "#166534";
    } else if (type === "yellow") {
      statusPill.textContent = "🟡 Advisory";
      statusPill.style.color = "#854d0e";
    } else {
      statusPill.textContent = `🔴 Shortages (${deficits.length})`;
      statusPill.style.color = "#991b1b";
    }
  }

  const actionsContainer = document.getElementById("health-actions");
  actionsContainer.innerHTML = "";

  if (deficits.length > 0 && deficits[0].recommended_fixes && deficits[0].recommended_fixes.length > 0) {
    const fix = deficits[0].recommended_fixes[0];
    const fixBtn = document.createElement("button");
    fixBtn.className = "btn btn-sm btn-primary";
    fixBtn.textContent = `1-Click Fix: ${fix.description}`;
    fixBtn.onclick = async () => {
      await apiPost(`/api/roster/${state.activePlanId}/assignments`, {
        employee_id: fix.employee_id,
        department_id: deficits[0].department_id,
        shift_type_id: deficits[0].shift_type_id,
        date: deficits[0].date,
        force_override: true,
        is_pinned: true
      });
      await loadSchedule();
    };
    actionsContainer.appendChild(fixBtn);
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
    const d = new Date(dStr);
    const dayName = d.toLocaleDateString("en-US", { weekday: "short" });
    const dayNum = d.getDate();
    th.innerHTML = `<div>${dayNum}</div><div style="font-size:9px;">${dayName}</div>`;
    if (dayName === "Sat" || dayName === "Sun") {
      th.style.background = "#f1f5f9";
    }
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Tbody
  const tbody = document.createElement("tbody");
  data.rows.forEach(r => {
    const tr = document.createElement("tr");

    const empTd = document.createElement("td");
    empTd.className = "sticky-col";
    const deptColor = r.primary_department_color || "#3b82f6";

    let prevMonthLabel = "";
    if (state.showPrevMonth && r.previous_month_summary) {
      prevMonthLabel = `<span style="color:#2563eb;font-weight:600;font-size:9px;">Prev: ${r.previous_month_summary.worked_hours}h (${r.previous_month_summary.night_shifts}N)</span>`;
    }

    empTd.innerHTML = `
      <div class="emp-sticky-card" style="border-left-color: ${deptColor};">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">
          <b>${r.employee_name}</b>
          <span class="dept-badge-tag" style="background:${deptColor};">${r.primary_department_code}</span>
        </div>
        <div style="font-size:10px;color:var(--text-muted);display:flex;gap:6px;margin-top:2px;align-items:center;">
          <span>${r.employee_code}</span>
          ${prevMonthLabel}
        </div>
      </div>
    `;
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
      const a = r.assignments[dStr];

      if (a) {
        const badge = document.createElement("span");
        let shiftClass = "shift-off";
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
        badge.innerHTML = `${a.shift_code}${a.is_floating ? `*(${a.department_code})` : ""}${a.is_pinned ? " 📌" : ""}`;

        badge.onclick = () => selectAssignment(r, dStr, a);
        td.appendChild(badge);
      } else {
        const offBadge = document.createElement("span");
        offBadge.className = "shift-badge shift-off";
        offBadge.textContent = "OFF";
        offBadge.onclick = () => selectAssignment(r, dStr, null);
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
async function selectAssignment(emp, dateStr, currentAssignment) {
  state.selectedCell = { emp, dateStr, currentAssignment };
  const content = document.getElementById("inspector-content");
  const actions = document.getElementById("inspector-actions");
  actions.classList.remove("hidden");

  let shiftSelectorHtml = `<select id="target-shift-select" class="select-input" style="width:100%;margin-top:6px;">`;
  state.shifts.forEach(s => {
    shiftSelectorHtml += `<option value="${s.id}">${s.name} (${s.code})</option>`;
  });
  shiftSelectorHtml += `</select>`;

  let deptSelectorHtml = `<select id="target-dept-select" class="select-input" style="width:100%;margin-top:6px;">`;
  state.departments.forEach(d => {
    deptSelectorHtml += `<option value="${d.id}" ${d.id === emp.primary_department_id ? "selected" : ""}>${d.name}</option>`;
  });
  deptSelectorHtml += `</select>`;

  content.innerHTML = `
    <div style="font-size:12px;">
      <div><b>Employee:</b> ${emp.employee_name} (${emp.primary_department_code})</div>
      <div><b>Date:</b> ${dateStr}</div>
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

  // Wire Inspector Pin & Clear buttons
  const pinBtn = document.getElementById("inspector-pin-btn");
  if (pinBtn) {
    const isPinned = currentAssignment && currentAssignment.is_pinned;
    pinBtn.textContent = isPinned ? "Unpin Shift 🔓" : "Pin / Lock Shift 📌";
    pinBtn.className = `btn btn-sm ${isPinned ? "btn-primary" : ""}`;
    pinBtn.onclick = async () => {
      if (!currentAssignment) {
        alert("Please select or assign a shift first before pinning.");
        return;
      }
      const res = await apiPost(`/api/roster/${state.activePlanId}/assignments/toggle-pin?employee_id=${emp.employee_id}&date=${dateStr}`, {});
      await loadSchedule();
      selectAssignment(emp, dateStr, { ...currentAssignment, is_pinned: res.is_pinned });
    };
  }

  const clearBtn = document.getElementById("inspector-clear-btn");
  if (clearBtn) {
    clearBtn.disabled = !currentAssignment;
    clearBtn.onclick = async () => {
      if (!currentAssignment) return;
      await apiDelete(`/api/roster/${state.activePlanId}/assignments?employee_id=${emp.employee_id}&date=${dateStr}`);
      await loadSchedule();
      selectAssignment(emp, dateStr, null);
    };
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

async function loadOrgEmployees() {
  const filterDeptId = document.getElementById("emp-filter-dept-select").value;
  let url = "/api/employees?active_only=false";
  if (filterDeptId) url += `&department_id=${filterDeptId}`;

  const emps = await apiGet(url);
  document.getElementById("org-emp-count").textContent = emps.length;

  const tbody = document.getElementById("emps-table-body");
  tbody.innerHTML = "";

  emps.forEach(e => {
    const dObj = state.departments.find(d => d.id === e.primary_department_id);
    const dColor = dObj ? dObj.color_code : "#3B82F6";
    const dCode = dObj ? dObj.code : "";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${e.employee_code}</b></td>
      <td>${e.name}</td>
      <td><span class="dept-badge-tag" style="background:${dColor};">${dCode}</span> ${e.primary_department_name || ''}</td>
      <td>${e.max_hours_week} hrs/wk</td>
      <td><span class="brand-badge" style="background:${e.is_active ? '#dcfce7' : '#fee2e2'};color:${e.is_active ? '#166534' : '#991b1b'};">${e.is_active ? 'Active' : 'Inactive'}</span></td>
      <td style="text-align:right;">
        <button class="btn btn-sm" onclick='editEmployee(${JSON.stringify(e)})'>Edit</button>
        <button class="btn btn-sm" style="color:#dc2626;" onclick='deleteEmployee(${e.id}, "${e.name.replace(/"/g, '&quot;')}")'>Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

window.editEmployee = function(e) {
  document.getElementById("emp-form-id").value = e.id;
  document.getElementById("emp-form-code").value = e.employee_code;
  document.getElementById("emp-form-name").value = e.name;
  document.getElementById("emp-form-dept").value = e.primary_department_id;
  document.getElementById("emp-form-hours").value = e.max_hours_week || 40.0;
  document.getElementById("emp-form-title").textContent = `Edit Employee: ${e.name}`;
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

  const toggleSidebarBtn = document.getElementById("toggle-sidebar-btn");
  if (toggleSidebarBtn) {
    toggleSidebarBtn.onclick = () => {
      const sb = document.getElementById("dept-sidebar");
      if (sb) {
        const isHidden = sb.style.display === "none";
        sb.style.display = isHidden ? "flex" : "none";
        toggleSidebarBtn.textContent = isHidden ? "Hide Dept Sidebar" : "Show Dept Sidebar";
      }
    };
  }

  const toggleInspectorBtn = document.getElementById("toggle-inspector-btn");
  if (toggleInspectorBtn) {
    toggleInspectorBtn.onclick = () => {
      const ip = document.getElementById("inspector-panel");
      if (ip) {
        const isHidden = ip.style.display === "none";
        ip.style.display = isHidden ? "flex" : "none";
        toggleInspectorBtn.textContent = isHidden ? "Hide Inspector" : "Show Inspector";
      }
    };
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
      alert("Sidebar widths reset to standard layout.");
    };
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

  // Org Tabs Switcher
  const tabDepts = document.getElementById("org-tab-depts");
  const tabEmps = document.getElementById("org-tab-emps");
  if (tabDepts) {
    tabDepts.onclick = () => {
      tabDepts.classList.add("active");
      if (tabEmps) tabEmps.classList.remove("active");
      const dView = document.getElementById("org-depts-view");
      const eView = document.getElementById("org-emps-view");
      if (dView) dView.classList.remove("hidden");
      if (eView) eView.classList.add("hidden");
    };
  }

  if (tabEmps) {
    tabEmps.onclick = () => {
      tabEmps.classList.add("active");
      if (tabDepts) tabDepts.classList.remove("active");
      const dView = document.getElementById("org-depts-view");
      const eView = document.getElementById("org-emps-view");
      if (eView) eView.classList.remove("hidden");
      if (dView) dView.classList.add("hidden");
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
      document.getElementById("emp-form-title").textContent = "Create New Employee";
      document.getElementById("emp-form-card").classList.remove("hidden");
    };
  }

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

      if (!employee_code || !name || !primary_department_id) {
        alert("Please provide employee code, name, and primary department.");
        return;
      }

      try {
        if (id) {
          await apiPut(`/api/employees/${id}`, { employee_code, name, primary_department_id, max_hours_week });
        } else {
          await apiPost("/api/employees", { employee_code, name, primary_department_id, max_hours_week });
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
      loadOrgEmployees();
    };
  }

  // Modals
  const newPlanBtn = document.getElementById("new-plan-btn");
  if (newPlanBtn) {
    newPlanBtn.onclick = () => {
      document.getElementById("modal-new-plan").classList.remove("hidden");
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

  // Confirm New Plan
  const confirmGenBtn = document.getElementById("confirm-generate-btn");
  if (confirmGenBtn) {
    confirmGenBtn.onclick = async () => {
      const name = document.getElementById("new-plan-name").value;
      const year = parseInt(document.getElementById("new-plan-year").value);
      const month = parseInt(document.getElementById("new-plan-month").value);
      const variants = parseInt(document.getElementById("new-plan-variants").value);

      document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
      updateHealthBanner("yellow", "🟡 CP-SAT Solver is running integer optimization...");

      await apiPost("/api/roster/generate", {
        name,
        planning_year: year,
        planning_month: month,
        variant_count: variants,
        timeout_seconds: 15
      });

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

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", initApp);
