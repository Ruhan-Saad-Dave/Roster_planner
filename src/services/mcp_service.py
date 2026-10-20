"""Native Model Context Protocol (MCP) tool registry and execution service."""
from datetime import date
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from src.db.models import Department, ShiftType, Employee, RosterPlan, RosterAssignment, DeficitLog
from src.services.roster_service import (
    generate_roster_plan, validate_drag_and_drop_move, solve_remaining_blank_slots
)
from src.services.analytics_service import get_workload_audit_scorecard

MCP_TOOLS_MANIFEST = [
    {
        "name": "roster_get_departments",
        "description": "Retrieve all departments, operational regimes (24x7 or weekdays), and active staff counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean", "default": True}
            }
        }
    },
    {
        "name": "roster_get_schedule",
        "description": "Fetch the roster schedule for a given plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"}
            },
            "required": ["plan_id"]
        }
    },
    {
        "name": "roster_validate_assignment",
        "description": "Validate whether assigning an employee to a shift violates ergonomic rules or rest intervals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"},
                "employee_id": {"type": "integer"},
                "target_department_id": {"type": "integer"},
                "target_shift_type_id": {"type": "integer"},
                "target_date": {"type": "string", "format": "date"}
            },
            "required": ["plan_id", "employee_id", "target_department_id", "target_shift_type_id", "target_date"]
        }
    },
    {
        "name": "roster_generate_variants",
        "description": "Trigger CP-SAT solver to generate candidate roster variants for a given year and month.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "planning_year": {"type": "integer"},
                "planning_month": {"type": "integer"},
                "variant_count": {"type": "integer", "default": 2}
            },
            "required": ["planning_year", "planning_month"]
        }
    },
    {
        "name": "roster_get_workload_audit",
        "description": "Retrieve the manager's workload audit scorecard per employee.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer"}
            },
            "required": ["plan_id"]
        }
    }
]

def execute_mcp_tool(db: Session, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool call and return standard MCP content structure."""
    try:
        if tool_name == "roster_get_departments":
            active_only = arguments.get("active_only", True)
            query = db.query(Department)
            if active_only:
                query = query.filter(Department.is_active == True)
            depts = query.all()
            result = [{"id": d.id, "code": d.code, "name": d.name, "regime": d.operating_regime} for d in depts]
            return {"isError": False, "content": [{"type": "text", "text": str(result)}]}

        elif tool_name == "roster_validate_assignment":
            target_date = date.fromisoformat(arguments["target_date"])
            val = validate_drag_and_drop_move(
                db,
                plan_id=arguments["plan_id"],
                employee_id=arguments["employee_id"],
                target_dept_id=arguments["target_department_id"],
                target_shift_id=arguments["target_shift_type_id"],
                target_date=target_date
            )
            return {"isError": False, "content": [{"type": "text", "text": str(val)}]}

        elif tool_name == "roster_get_workload_audit":
            audit = get_workload_audit_scorecard(db, plan_id=arguments["plan_id"])
            return {"isError": False, "content": [{"type": "text", "text": str(audit)}]}

        elif tool_name == "roster_generate_variants":
            year = arguments["planning_year"]
            month = arguments["planning_month"]
            import calendar
            num_days = calendar.monthrange(year, month)[1]
            start_date = date(year, month, 1)
            end_date = date(year, month, num_days)
            res = generate_roster_plan(
                db,
                name=f"MCP Generated Roster {year}-{month:02d}",
                start_date=start_date,
                end_date=end_date,
                planning_year=year,
                planning_month=month,
                variant_count=arguments.get("variant_count", 2)
            )
            plans_info = [{"id": p.id, "name": p.name, "deficits": p.total_deficits} for p in res["variants"]]
            return {"isError": False, "content": [{"type": "text", "text": str(plans_info)}]}

        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool '{tool_name}' not found."}]}
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Execution error: {str(e)}"}]}
