"""Integration test for Model Context Protocol (MCP) tool discovery and execution."""

def test_mcp_tools_and_execution(client, sample_scenario):
    # 1. Verify MCP Manifest
    manifest_res = client.get("/api/mcp/manifest")
    assert manifest_res.status_code == 200
    manifest = manifest_res.json()
    assert manifest["protocolVersion"] == "2024-11-05"
    assert manifest["serverInfo"]["name"] == "LocalRoster v2 MCP Server"

    # 2. Verify Tool Schemas
    tools_res = client.get("/api/mcp/tools")
    assert tools_res.status_code == 200
    tools = tools_res.json()["tools"]
    tool_names = [t["name"] for t in tools]
    assert "roster_get_departments" in tool_names
    assert "roster_validate_assignment" in tool_names
    assert "roster_generate_variants" in tool_names

    # 3. Execute MCP Tool: roster_get_departments
    exec_res = client.post("/api/mcp/execute", json={
        "tool": "roster_get_departments",
        "arguments": {"active_only": True}
    })
    assert exec_res.status_code == 200
    res_data = exec_res.json()
    assert res_data["isError"] is False
    assert "ICU" in res_data["content"][0]["text"]
