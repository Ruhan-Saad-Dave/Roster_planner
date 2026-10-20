"""Export service generating formatted multi-sheet Excel (.xlsx) and printable PDF schedules."""
import io
from datetime import timedelta
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Excel Color Palette
COLOR_HEADER_BG = "1E293B"       # Slate 800
COLOR_HEADER_TEXT = "FFFFFF"
COLOR_MORN_BG = "DBEAFE"         # Blue 100
COLOR_MORN_TEXT = "1E40AF"       # Blue 800
COLOR_EVE_BG = "FEF3C7"          # Amber 100
COLOR_EVE_TEXT = "92400E"        # Amber 800
COLOR_NIGHT_BG = "E0E7FF"        # Indigo 100
COLOR_NIGHT_TEXT = "3730A3"      # Indigo 800
COLOR_OFF_BG = "F1F5F9"          # Slate 100
COLOR_OFF_TEXT = "64748B"        # Slate 500
COLOR_DEFICIT_BG = "FEE2E2"      # Red 100
COLOR_DEFICIT_TEXT = "991B1B"    # Red 800
COLOR_FLOAT_BORDER = "F59E0B"    # Amber 500

def get_shift_fill_and_font(shift_code: Optional[str], is_floating: bool = False):
    border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )
    if is_floating:
        border = Border(
            left=Side(style="medium", color=COLOR_FLOAT_BORDER),
            right=Side(style="medium", color=COLOR_FLOAT_BORDER),
            top=Side(style="medium", color=COLOR_FLOAT_BORDER),
            bottom=Side(style="medium", color=COLOR_FLOAT_BORDER)
        )

    if not shift_code or shift_code == "OFF":
        return PatternFill("solid", fgColor=COLOR_OFF_BG), Font(name="Calibri", size=10, color=COLOR_OFF_TEXT), border
    elif "MORN" in shift_code.upper():
        return PatternFill("solid", fgColor=COLOR_MORN_BG), Font(name="Calibri", size=10, bold=True, color=COLOR_MORN_TEXT), border
    elif "EVE" in shift_code.upper():
        return PatternFill("solid", fgColor=COLOR_EVE_BG), Font(name="Calibri", size=10, bold=True, color=COLOR_EVE_TEXT), border
    elif "NIGHT" in shift_code.upper():
        return PatternFill("solid", fgColor=COLOR_NIGHT_BG), Font(name="Calibri", size=10, bold=True, color=COLOR_NIGHT_TEXT), border
    return PatternFill("solid", fgColor="E2E8F0"), Font(name="Calibri", size=10, color="334155"), border

def generate_excel_export(
    plan: Any,
    assignments: List[Any],
    deficits: List[Any],
    employees: List[Any],
    departments: List[Any],
    shifts: List[Any],
    view: str = "both"
) -> bytes:
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    horizon_days = (plan.end_date - plan.start_date).days + 1
    dates = [plan.start_date + timedelta(days=t) for t in range(horizon_days)]

    # Lookup maps
    emp_map = {e.id: e for e in employees}
    dept_map = {d.id: d for d in departments}
    shift_map = {s.id: s for s in shifts}

    # Group assignments: (emp_id, date) -> assign
    assign_by_emp_date = {(a.employee_id, a.date): a for a in assignments}

    # ==========================================
    # TAB 1: Staff-Centric Schedule
    # ==========================================
    if view in ["staff_centric", "both"]:
        ws_staff = wb.create_sheet(title="Staff Schedule")
        ws_staff.views.sheetView[0].showGridLines = True

        # Header Title
        ws_staff.cell(row=1, column=1, value=f"LocalRoster v2 - {plan.name} (Staff-Centric View)")
        ws_staff.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="1E293B")

        # Table Header
        headers = ["Employee Code", "Name", "Home Dept"]
        for d in dates:
            headers.append(d.strftime("%b %d (%a)"))
        headers.extend(["Total Shifts", "Hours Sched", "Days Off", "Floats"])

        for col_idx, h in enumerate(headers, start=1):
            cell = ws_staff.cell(row=3, column=col_idx, value=h)
            cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_HEADER_TEXT)
            cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Data Rows
        row_idx = 4
        for emp in employees:
            ws_staff.cell(row=row_idx, column=1, value=emp.employee_code).alignment = Alignment(horizontal="center")
            ws_staff.cell(row=row_idx, column=2, value=emp.name).font = Font(bold=True)
            ws_staff.cell(row=row_idx, column=3, value=dept_map.get(emp.primary_department_id, None).code if emp.primary_department_id in dept_map else "")

            shifts_worked = 0
            hours_worked = 0.0
            float_count = 0

            for d_idx, cur_date in enumerate(dates, start=4):
                cell = ws_staff.cell(row=row_idx, column=d_idx)
                if (emp.id, cur_date) in assign_by_emp_date:
                    a = assign_by_emp_date[(emp.id, cur_date)]
                    s = shift_map.get(a.shift_type_id)
                    d_code = dept_map.get(a.department_id).code if a.department_id in dept_map else ""
                    val = s.code if s else "WORK"
                    if a.is_floating:
                        val += f" ({d_code}*)"
                        float_count += 1
                    if a.is_pinned:
                        val += " [P]"

                    cell.value = val
                    shifts_worked += 1
                    if s:
                        hours_worked += s.duration_hours

                    fill, font, border = get_shift_fill_and_font(s.code if s else "MORN", a.is_floating)
                    cell.fill = fill
                    cell.font = font
                    cell.border = border
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.value = "OFF"
                    fill, font, border = get_shift_fill_and_font("OFF")
                    cell.fill = fill
                    cell.font = font
                    cell.border = border
                    cell.alignment = Alignment(horizontal="center", vertical="center")

            # Totals
            days_off = horizon_days - shifts_worked
            ws_staff.cell(row=row_idx, column=len(dates) + 4, value=shifts_worked).alignment = Alignment(horizontal="center")
            ws_staff.cell(row=row_idx, column=len(dates) + 5, value=hours_worked).alignment = Alignment(horizontal="center")
            ws_staff.cell(row=row_idx, column=len(dates) + 6, value=days_off).alignment = Alignment(horizontal="center")
            ws_staff.cell(row=row_idx, column=len(dates) + 7, value=float_count).alignment = Alignment(horizontal="center")

            row_idx += 1

        # Auto-adjust column widths
        for col in ws_staff.columns:
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws_staff.column_dimensions[col_letter].width = 13

    # ==========================================
    # TAB 2: Slot-Centric Schedule
    # ==========================================
    if view in ["slot_centric", "both"]:
        ws_slot = wb.create_sheet(title="Coverage by Slot")
        ws_slot.views.sheetView[0].showGridLines = True

        ws_slot.cell(row=1, column=1, value=f"LocalRoster v2 - {plan.name} (Department & Slot View)")
        ws_slot.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="1E293B")

        slot_headers = ["Date", "Day", "Department", "Shift", "Assigned Staff", "Total Assigned"]
        for col_idx, h in enumerate(slot_headers, start=1):
            cell = ws_slot.cell(row=3, column=col_idx, value=h)
            cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_HEADER_TEXT)
            cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
            cell.alignment = Alignment(horizontal="center", vertical="center")

        slot_row = 4
        # Group by (date, dept_id, shift_id)
        assign_by_slot = {}
        for a in assignments:
            key = (a.date, a.department_id, a.shift_type_id)
            assign_by_slot.setdefault(key, []).append(a)

        for cur_date in dates:
            for dept in departments:
                for shift in shifts:
                    key = (cur_date, dept.id, shift.id)
                    slot_assigns = assign_by_slot.get(key, [])
                    if slot_assigns:
                        worker_names = []
                        for sa in slot_assigns:
                            e_name = emp_map[sa.employee_id].name if sa.employee_id in emp_map else f"Emp {sa.employee_id}"
                            if sa.is_floating:
                                e_name += " (Floater*)"
                            worker_names.append(e_name)

                        ws_slot.cell(row=slot_row, column=1, value=cur_date.strftime("%Y-%m-%d"))
                        ws_slot.cell(row=slot_row, column=2, value=cur_date.strftime("%a"))
                        ws_slot.cell(row=slot_row, column=3, value=dept.name)
                        ws_slot.cell(row=slot_row, column=4, value=shift.name)
                        ws_slot.cell(row=slot_row, column=5, value=", ".join(worker_names))
                        ws_slot.cell(row=slot_row, column=6, value=len(worker_names)).alignment = Alignment(horizontal="center")
                        slot_row += 1

        for col in ws_slot.columns:
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws_slot.column_dimensions[col_letter].width = 18

    # ==========================================
    # TAB 3: Workload & Ergonomics Audit
    # ==========================================
    ws_audit = wb.create_sheet(title="Workload Audit")
    ws_audit.views.sheetView[0].showGridLines = True
    ws_audit.cell(row=1, column=1, value=f"LocalRoster v2 - Cross-Check Audit Scorecard ({plan.name})")
    ws_audit.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="1E293B")

    audit_headers = ["Employee Code", "Name", "Department", "Contracted (Wk)", "Target (Mo)", "Scheduled", "Variance", "Shifts", "Days Off", "Weekend Off", "Floats"]
    for col_idx, h in enumerate(audit_headers, start=1):
        cell = ws_audit.cell(row=3, column=col_idx, value=h)
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_HEADER_TEXT)
        cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    audit_row = 4
    for emp in employees:
        emp_assigns = [a for a in assignments if a.employee_id == emp.id]
        total_shifts = len(emp_assigns)
        total_hours = sum(shift_map[a.shift_type_id].duration_hours for a in emp_assigns if a.shift_type_id in shift_map)
        days_off = horizon_days - total_shifts
        weekend_off = sum(1 for d in dates if d.weekday() in [5, 6] and (emp.id, d) not in assign_by_emp_date)
        floats = sum(1 for a in emp_assigns if a.is_floating)

        target_month_hours = round(emp.max_hours_week * (horizon_days / 7.0), 1)
        variance = round(total_hours - target_month_hours, 1)

        ws_audit.cell(row=audit_row, column=1, value=emp.employee_code).alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=2, value=emp.name)
        ws_audit.cell(row=audit_row, column=3, value=dept_map.get(emp.primary_department_id).name if emp.primary_department_id in dept_map else "")
        ws_audit.cell(row=audit_row, column=4, value=f"{emp.max_hours_week}h").alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=5, value=f"{target_month_hours}h").alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=6, value=f"{total_hours:.1f}h").alignment = Alignment(horizontal="center")

        var_cell = ws_audit.cell(row=audit_row, column=7, value=f"{'+' if variance > 0 else ''}{variance:.1f}h")
        var_cell.alignment = Alignment(horizontal="center")
        if variance > 8.0:
            var_cell.font = Font(bold=True, color="DC2626")  # High overtime warning
        elif variance < -8.0:
            var_cell.font = Font(color="D97706")

        ws_audit.cell(row=audit_row, column=8, value=total_shifts).alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=9, value=days_off).alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=10, value=weekend_off).alignment = Alignment(horizontal="center")
        ws_audit.cell(row=audit_row, column=11, value=floats).alignment = Alignment(horizontal="center")

        audit_row += 1

    for col in ws_audit.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_audit.column_dimensions[col_letter].width = 16

    # ==========================================
    # TAB 4: Deficits & Gap Diagnostics
    # ==========================================
    ws_def = wb.create_sheet(title="Deficits & Bottlenecks")
    ws_def.views.sheetView[0].showGridLines = True
    ws_def.cell(row=1, column=1, value=f"LocalRoster v2 - Deficit & Shortage Diagnostics ({plan.name})")
    ws_def.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="1E293B")

    def_headers = ["Date", "Day", "Department", "Shift", "Shortage Count", "Root Cause Reason Code"]
    for col_idx, h in enumerate(def_headers, start=1):
        cell = ws_def.cell(row=3, column=col_idx, value=h)
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_HEADER_TEXT)
        cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    def_row = 4
    if deficits:
        for d in deficits:
            ws_def.cell(row=def_row, column=1, value=d.date.strftime("%Y-%m-%d"))
            ws_def.cell(row=def_row, column=2, value=d.date.strftime("%a"))
            ws_def.cell(row=def_row, column=3, value=dept_map.get(d.department_id).name if d.department_id in dept_map else "")
            ws_def.cell(row=def_row, column=4, value=shift_map.get(d.shift_type_id).name if d.shift_type_id in shift_map else "")
            short_cell = ws_def.cell(row=def_row, column=5, value=d.shortage_count)
            short_cell.font = Font(bold=True, color=COLOR_DEFICIT_TEXT)
            short_cell.fill = PatternFill("solid", fgColor=COLOR_DEFICIT_BG)
            short_cell.alignment = Alignment(horizontal="center")
            ws_def.cell(row=def_row, column=6, value=d.reason_code)
            def_row += 1
    else:
        ws_def.cell(row=4, column=1, value="Clean Roster: 0 staffing deficits detected. Full demand satisfied.")
        ws_def.cell(row=4, column=1).font = Font(bold=True, color="16A34A")

    for col in ws_def.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_def.column_dimensions[col_letter].width = 20

    # Write to memory buffer
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

def generate_pdf_export(
    plan: Any,
    assignments: List[Any],
    employees: List[Any],
    departments: List[Any],
    shifts: List[Any]
) -> bytes:
    """Generate high-density, vector-rendered printable PDF schedule."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20, leftMargin=20,
        topMargin=20, bottomMargin=20
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0F172A")
    )
    meta_style = ParagraphStyle(
        "MetaStyle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748B")
    )

    elements = []
    elements.append(Paragraph(f"<b>LocalRoster v2</b> — {plan.name}", title_style))
    elements.append(Paragraph(f"Horizon: {plan.start_date} to {plan.end_date} | Solver Status: {plan.solver_status} | Total Shifts: {len(assignments)} | Deficits: {plan.total_deficits}", meta_style))
    elements.append(Spacer(1, 10))

    horizon_days = min((plan.end_date - plan.start_date).days + 1, 14)  # Show first 14 days on printable sheet
    dates = [plan.start_date + timedelta(days=t) for t in range(horizon_days)]
    assign_by_emp_date = {(a.employee_id, a.date): a for a in assignments}
    shift_map = {s.id: s for s in shifts}

    table_data = [["Employee"] + [d.strftime("%d\n%a") for d in dates] + ["Total"]]
    for emp in employees:
        row = [emp.name]
        worked = 0
        for d in dates:
            if (emp.id, d) in assign_by_emp_date:
                a = assign_by_emp_date[(emp.id, d)]
                s = shift_map.get(a.shift_type_id)
                code = s.code[:2] if s else "W"
                if a.is_floating:
                    code += "*"
                row.append(code)
                worked += 1
            else:
                row.append("-")
        row.append(str(worked))
        table_data.append(row)

    pdf_table = Table(table_data)
    pdf_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))

    elements.append(pdf_table)
    doc.build(elements)
    return buffer.getvalue()
