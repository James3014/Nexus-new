import pytest
import os
import sys
from nexus.services.mcp_delegator import MCPDelegator

@pytest.fixture
def mock_server_env(monkeypatch):
    mock_path = os.path.join(os.path.dirname(__file__), "mock_mcp_server.py")
    monkeypatch.setenv("MCP_DEFAULT_SERVER", f"{sys.executable} {mock_path}")
    monkeypatch.setenv("MCP_DELEGATION_TIMEOUT", "1.0")
    yield

@pytest.mark.asyncio
async def test_delegate_mcp_success(mock_server_env):
    delegator = MCPDelegator()
    result = await delegator.delegate_mcp(
        tool="test_tool",
        tenant_id="tenant_123",
        args={"param": "value"}
    )
    
    assert result["status"] == "SUCCESS"
    assert result["tool"] == "test_tool"
    assert result["tenant_id"] == "tenant_123"
    assert result["data"]["status"] == "executed"
    assert result["data"]["tool"] == "mempalace_test_tool"
    assert result["data"]["args"] == {"param": "value"}
    assert result["tokens_consumed"] == 145

@pytest.mark.asyncio
async def test_delegate_mcp_error_tool(mock_server_env):
    delegator = MCPDelegator()
    result = await delegator.delegate_mcp(
        tool="error_tool",
        tenant_id="tenant_123",
        args={}
    )
    
    assert result["status"] == "FAIL"
    assert "Triggered error" in str(result["error"])

@pytest.mark.asyncio
async def test_delegate_mcp_malformed_output(mock_server_env):
    delegator = MCPDelegator()
    result = await delegator.delegate_mcp(
        tool="malformed_tool",
        tenant_id="tenant_123",
        args={}
    )
    
    assert result["status"] == "FAIL"
    # Delegate may surface malformed response as timeout-style failure.
    err = str(result["error"])
    assert any(msg in err for msg in ["Timeout", "empty response", "Malformed", "TIMEOUT"])

@pytest.mark.asyncio
async def test_delegate_mcp_timeout(mock_server_env, monkeypatch):
    delegator = MCPDelegator()
    # Set a very short timeout for this test
    monkeypatch.setenv("MCP_DELEGATION_TIMEOUT", "0.1")
    delegator.timeout = 0.1
    
    result = await delegator.delegate_mcp(
        tool="timeout_tool",
        tenant_id="tenant_123",
        args={}
    )
    
    assert result["status"] == "FAIL"
    assert "TIMEOUT" in str(result["error"]).upper()


@pytest.mark.asyncio
async def test_serena_no_server_degrades_success(monkeypatch):
    monkeypatch.delenv("MCP_DEFAULT_SERVER", raising=False)
    monkeypatch.setenv("NEXUS_SERENA_FAIL_OPEN", "1")
    delegator = MCPDelegator()
    result = await delegator.delegate_mcp(
        tool="serena_replace_content",
        tenant_id="tenant_123",
        args={"path": "x", "content": "y"},
    )
    assert result["status"] == "SUCCESS"
    assert result["audit_status"] == "DEGRADED_SUCCESS"
    assert result["fallback_used"] is True
    assert "serena_no_server_configured" in result["fallback_reason"]


@pytest.mark.asyncio
async def test_self_hosted_tools_use_bundled_nexus_server_by_default(monkeypatch):
    monkeypatch.delenv("MCP_DEFAULT_SERVER", raising=False)
    delegator = MCPDelegator()

    result = await delegator.delegate_mcp(
        tool="nexus_self_hosted_get_task",
        tenant_id="tenant_123",
        args={"task_id": "missing-task"},
    )

    assert result["status"] == "SUCCESS"
    assert result["tool"] == "nexus_self_hosted_get_task"
    assert result["data"] is None


@pytest.mark.asyncio
async def test_serena_healthcheck_failed_degrades_success(mock_server_env, monkeypatch):
    monkeypatch.setenv("NEXUS_SERENA_FAIL_OPEN", "1")
    delegator = MCPDelegator()

    async def _unhealthy(_command):
        return False, "probe_exception:boom"

    delegator._probe_command_health = _unhealthy  # type: ignore[method-assign]

    result = await delegator.delegate_mcp(
        tool="serena_execute_shell_command",
        tenant_id="tenant_123",
        args={"cmd": "echo hi"},
    )
    assert result["status"] == "SUCCESS"
    assert result["audit_status"] == "DEGRADED_SUCCESS"
    assert result["fallback_used"] is True
    assert "serena_unhealthy" in result["fallback_reason"]
