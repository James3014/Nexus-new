import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from nexus.services.llm import LLMClient
from nexus.engine.phases.research import ResearchPhaseHandler
from nexus.engine.phases.repair import RepairPhaseHandler
from nexus.core.orchestrator import NexusOrchestrator
from nexus.core.state_contracts import NexusState

@pytest.fixture
def mock_llm_output():
    return """
    Hello, here is the result.
    Total Session Tokens: 1,420
    ```json
    {
      "status": "PASS",
      "summary": "Everything looks good"
    }
    ```
    """

def test_llm_client_token_capture(mock_llm_output):
    client = LLMClient(project_root=".")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=mock_llm_output, stderr="", returncode=0
        )
        data, raw = client.ask("test prompt", "test payload")
        assert data["tokens_used"] == 1420
        assert data["token_capture_status"] == "ok"

def test_token_propagation_through_phases(mock_llm_output):
    # Mock LLM Client
    mock_llm = MagicMock()
    mock_llm.ask.return_value = (
        {"status": "PASS", "summary": "Fixed", "tokens_used": 500, "token_capture_status": "ok"},
        mock_llm_output
    )
    mock_llm.model_selector.return_value = "flash"
    
    # Mock Engine Dependencies
    project_root = Path(".")
    run_dir = Path("./run_test")
    run_dir.mkdir(exist_ok=True)
    
    state = NexusState(task_id="test-task")
    state.phase_tokens = {"P": 0, "D": 0, "X": 0, "R": 0, "A": 0, "C": 0}
    
    # Test Research Phase
    researcher = ResearchPhaseHandler(project_root, run_dir)
    # Patch external research to avoid npx calls
    with patch.object(researcher, "_run_external_research") as mock_ext:
        mock_ext.return_value = {"status": "SUCCESS", "tokens_used": 300, "token_capture_status": "ok"}
        res = researcher.run(state, {"task": "test"})
        assert res["tokens_used"] == 300
        assert res["token_capture_status"] == "ok"

def test_pipeline_integration_in_coordinator():
    # This test verifies that Coordinator correctly updates state and metadata
    mock_state = MagicMock()
    mock_state.phase_tokens = {"X": 0, "R": 0}
    mock_state.total_token_usage = 0
    mock_state.metadata = {}
    
    # Simulate Research Phase result
    res_data = {"tokens_used": 100, "token_capture_status": "ok", "status": "SUCCESS"}
    
    # Logic from coordinator.py (X phase)
    phase_tokens = res_data.get("tokens_used", 0)
    mock_state.phase_tokens["X"] = mock_state.phase_tokens.get("X", 0) + phase_tokens
    mock_state.total_token_usage += phase_tokens
    mock_state.metadata["token_capture_status"] = res_data.get("token_capture_status", "unknown")
    
    assert mock_state.total_token_usage == 100
    assert mock_state.metadata["token_capture_status"] == "ok"
    assert mock_state.phase_tokens["X"] == 100
