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
  try {
    state.departments = await apiGet("/api/departments");
    state.shifts = await apiGet("/api/shift-types");
    await loadPlans();
    setupEventListeners();
  } catch (err) {
    console.error("Initialization error:", err);
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
}

// ==========================================
// Health Banner & Guided Shortage Fixes
// ==========================================
function updateHealthBanner(type, message, deficits = []) {
  const banner = document.getElementById("health-banner");
  banner.className = `health-banner ${type}`;
  document.getElementById("health-message").textContent = message;

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
// Event Listeners & Modals
// ==========================================
function setupEventListeners() {
  document.getElementById("plan-select").onchange = (e) => {
    state.activePlanId = parseInt(e.target.value);
    loadSchedule();
  };

  document.getElementById("view-select").onchange = (e) => {
    state.currentView = e.target.value;
    loadSchedule();
  };

  document.getElementById("mode-toggle-btn").onclick = (e) => {
    state.currentMode = state.currentMode === "simple" ? "cockpit" : "simple";
    e.target.textContent = state.currentMode === "simple" ? "Simple Mode" : "Cockpit Mode";
    document.getElementById("inspector-panel").style.display = state.currentMode === "simple" ? "none" : "flex";
  };

  document.getElementById("prefill-toggle-btn").onclick = (e) => {
    state.prefillMode = !state.prefillMode;
    e.target.textContent = `Prefill Mode: ${state.prefillMode ? "ON 📌" : "OFF"}`;
    e.target.className = `btn btn-sm ${state.prefillMode ? "btn-primary" : ""}`;
  };

  document.getElementById("solve-remaining-btn").onclick = async () => {
    if (!state.activePlanId) return;
    await apiPost(`/api/roster/${state.activePlanId}/solve-remaining`, { timeout_seconds: 15 });
    await loadSchedule();
  };

  document.getElementById("export-excel-btn").onclick = () => {
    if (!state.activePlanId) return;
    window.location.href = `/api/export/${state.activePlanId}/excel?view=both`;
  };

  document.getElementById("export-pdf-btn").onclick = () => {
    if (!state.activePlanId) return;
    window.location.href = `/api/export/${state.activePlanId}/pdf`;
  };

  // Prev Month Toggle
  document.getElementById("toggle-prev-month-btn").onclick = (e) => {
    state.showPrevMonth = !state.showPrevMonth;
    e.target.textContent = `📅 Prev Month: ${state.showPrevMonth ? "ON" : "OFF"}`;
    e.target.className = `btn btn-sm ${state.showPrevMonth ? "btn-primary" : ""}`;
    loadSchedule();
  };

  // Help Guide Modal
  document.getElementById("help-guide-btn").onclick = () => {
    document.getElementById("modal-help-guide").classList.remove("hidden");
  };

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
  document.getElementById("manage-org-btn").onclick = async () => {
    document.getElementById("modal-manage-org").classList.remove("hidden");
    await loadOrgDepartments();
    await loadOrgEmployees();
  };

  // Org Tabs Switcher
  document.getElementById("org-tab-depts").onclick = () => {
    document.getElementById("org-tab-depts").classList.add("active");
    document.getElementById("org-tab-emps").classList.remove("active");
    document.getElementById("org-depts-view").classList.remove("hidden");
    document.getElementById("org-emps-view").classList.add("hidden");
  };

  document.getElementById("org-tab-emps").onclick = () => {
    document.getElementById("org-tab-emps").classList.add("active");
    document.getElementById("org-tab-depts").classList.remove("active");
    document.getElementById("org-emps-view").classList.remove("hidden");
    document.getElementById("org-depts-view").classList.add("hidden");
  };

  // Color input hex live update
  document.getElementById("dept-form-color").oninput = (e) => {
    document.getElementById("dept-color-hex").textContent = e.target.value.toUpperCase();
  };

  // Department CRUD forms & actions
  document.getElementById("show-add-dept-btn").onclick = () => {
    document.getElementById("dept-form-id").value = "";
    document.getElementById("dept-form-code").value = "";
    document.getElementById("dept-form-name").value = "";
    document.getElementById("dept-form-color").value = "#3B82F6";
    document.getElementById("dept-color-hex").textContent = "#3B82F6";
    document.getElementById("dept-form-regime").value = "24_7";
    document.getElementById("dept-form-title").textContent = "Create New Department";
    document.getElementById("dept-form-card").classList.remove("hidden");
  };

  document.getElementById("cancel-dept-form-btn").onclick = () => {
    document.getElementById("dept-form-card").classList.add("hidden");
  };

  document.getElementById("save-dept-form-btn").onclick = async () => {
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

  // Employee CRUD forms & actions
  document.getElementById("show-add-emp-btn").onclick = () => {
    document.getElementById("emp-form-id").value = "";
    document.getElementById("emp-form-code").value = "";
    document.getElementById("emp-form-name").value = "";
    document.getElementById("emp-form-hours").value = "40.0";
    document.getElementById("emp-form-title").textContent = "Create New Employee";
    document.getElementById("emp-form-card").classList.remove("hidden");
  };

  document.getElementById("cancel-emp-form-btn").onclick = () => {
    document.getElementById("emp-form-card").classList.add("hidden");
  };

  document.getElementById("save-emp-form-btn").onclick = async () => {
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

  document.getElementById("emp-filter-dept-select").onchange = () => {
    loadOrgEmployees();
  };

  // Modals
  document.getElementById("new-plan-btn").onclick = () => {
    document.getElementById("modal-new-plan").classList.remove("hidden");
  };

  document.getElementById("import-btn").onclick = () => {
    document.getElementById("modal-import").classList.remove("hidden");
  };

  document.getElementById("variants-btn").onclick = async () => {
    document.getElementById("modal-variants").classList.remove("hidden");
    const container = document.getElementById("variants-comparison-content");
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

  document.querySelectorAll(".close-modal").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
    };
  });

  // Confirm New Plan
  document.getElementById("confirm-generate-btn").onclick = async () => {
    const name = document.getElementById("new-plan-name").value;
    const year = parseInt(document.getElementById("new-plan-year").value);
    const month = parseInt(document.getElementById("new-plan-month").value);
    const variants = parseInt(document.getElementById("new-plan-variants").value);

    document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
    updateHealthBanner("yellow", "🟡 CP-SAT Solver is running integer optimization...");

    const res = await apiPost("/api/roster/generate", {
      name,
      planning_year: year,
      planning_month: month,
      variant_count: variants,
      timeout_seconds: 15
    });

    await loadPlans();
  };

  // Import Template download
  document.getElementById("download-template-btn").onclick = () => {
    const type = document.getElementById("import-type-select").value;
    window.location.href = `/api/import/template/${type}`;
  };
}

window.promoteVariant = async function(planId) {
  await apiPost(`/api/roster/${planId}/promote`, {});
  document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
  await loadPlans();
};

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", initApp);
