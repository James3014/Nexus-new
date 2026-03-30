import pytest
import os
import pathlib
from unittest.mock import patch, MagicMock
from nexus.pilot_cli.commands import handle_command
from nexus.pilot_cli.session import PilotSession
from nexus.engine.config import EngineConfig
from nexus.engine.coordinator import NexusEngine
from nexus.engine.pipeline import NexusPipeline

@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "nexus_ws"
    ws.mkdir()
    return ws

@patch("nexus.pilot_cli.commands.govern_via_gateway")
def test_full_chain_cli_to_engine(mock_gateway, workspace):
    # 1. Pilot CLI Session initialization
    session = PilotSession(workspace=str(workspace), tenant_id="test-tenant")
    
    # 2. Simulate User asking to "govern" through CLI command
    # Mock gateway to return a realistic task trigger
    mock_gateway.return_value = {
        "task_id": "task-e2e-123",
        "summary": "Initiating E2E Hardening"
    }
    
    cli_response = handle_command("/govern Hardening logic", session)
    assert "Battle Mode engaged" in cli_response
    assert "task-e2e-123" in cli_response

    # 3. Simulate Engine picking up the task (In practice, this happens via EventBus/Gateway)
    # Here we trigger the engine directly for verification
    config = EngineConfig(project_root=workspace)
    engine = NexusEngine(config)
    
    # Run the engine for this task with LLM mocked
    with patch("nexus.services.gateway.BattlesuitGateway.ask") as mock_ask, \
         patch("nexus.services.gateway.BattlesuitGateway.ask_with_template") as mock_ask_tmpl, \
         patch.object(NexusPipeline, "_stage_research", return_value=None) as mock_p_research, \
         patch.object(NexusPipeline, "_stage_diagnose", return_value=None) as mock_p_diagnose:
        
        mock_ask.return_value = ({"status": "PASS", "summary": "Code is clean", "no_change_reason": "already_correct"}, "Raw LLM output")
        mock_ask_tmpl.return_value = ({"status": "PASS", "summary": "Review passed", "no_change_reason": "already_correct"}, "Raw LLM output")
        
        success = engine.run_bug(bug_id="task-e2e-123", desc="Hardening logic")
    
    assert success is True
    assert mock_p_research.called
    assert mock_p_diagnose.called

def test_telemetry_propagation_in_e2e(workspace):
    from nexus.telemetry.tracer import NexusTracer
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry import trace
    
    # Force a real provider for testing
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    
    tracer = NexusTracer()
    with tracer.pipeline_span("e2e-trace-1") as (root_span, tid, sid):
        # Verify trace ID is accessible
        assert tid != "00000000000000000000000000000000"
        assert tracer.current_trace_id() == tid
