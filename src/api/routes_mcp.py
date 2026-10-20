"""Model Context Protocol (MCP) endpoints for external AI agents."""
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from typing import Dict, Any
from src.db.session import get_db
from src.services.mcp_service import MCP_TOOLS_MANIFEST, execute_mcp_tool

router = APIRouter(prefix="/api/mcp", tags=["Model Context Protocol (MCP)"])

@router.get("/manifest")
def get_manifest():
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "LocalRoster v2 MCP Server",
            "version": "2.0.0"
        },
        "capabilities": {
            "tools": {"listChanged": False}
        }
    }

@router.get("/tools")
def list_tools():
    return {"tools": MCP_TOOLS_MANIFEST}

@router.post("/execute")
def execute_tool(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    tool_name = payload.get("tool") or payload.get("name")
    arguments = payload.get("arguments") or payload.get("parameters") or {}
    return execute_mcp_tool(db, tool_name, arguments)
