import pytest
import asyncio
from unittest.mock import MagicMock, patch
from nexus.core.dual_loop_orchestrator import DualLoopOrchestrator

@pytest.mark.asyncio
async def test_dual_diagnose_physical_veto():
    """驗證當物理審核失敗時，共識結果為 FAIL (物理一票否決)"""
    orchestrator = DualLoopOrchestrator(project_root=".")
    
    # 模擬 ExecutorInput
    mock_input = MagicMock()
    mock_input.task_id = "TASK-VETO-TEST"

    # Mock 物理診斷失敗 (X-Ray 偵測到風險)
    with patch("nexus.core.dual_loop_orchestrator.XRayObserver") as MockObserver:
        mock_instance = MockObserver.return_value
        mock_report = MagicMock()
        mock_report.risks = ["External dependency found"]
        mock_instance.scan.return_value = mock_report
        
        result = await orchestrator.dual_diagnose(mock_input)
        
        assert result["status"] == "FAIL"
        assert "Dependency Risk" in result["reason"]
        assert result["provider"] == "physical-auditor"

@pytest.mark.asyncio
async def test_dual_diagnose_consensus_pass():
    """驗證當大腦與物理都 PASS 時，共識結果為 PASS"""
    orchestrator = DualLoopOrchestrator(project_root=".")
    mock_input = MagicMock()
    mock_input.task_id = "TASK-PASS-TEST"

    # Mock 物理診斷成功
    with patch("nexus.core.dual_loop_orchestrator.XRayObserver") as MockObserver:
        mock_instance = MockObserver.return_value
        mock_report = MagicMock()
        mock_report.risks = []
        mock_instance.scan.return_value = mock_report
        
        result = await orchestrator.dual_diagnose(mock_input)
        
        assert result["status"] == "PASS"
        assert result["provider"] == "gemini-3-flash"

if __name__ == "__main__":
    pytest.main([__file__])
