from pathlib import Path
import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch
from nexus.core.dual_loop_orchestrator import DualLoopOrchestrator

@pytest.mark.asyncio
async def test_consensus_pass_normal():
    """Case A: 正常修復路徑，大腦與物理都 PASS"""
    orchestrator = DualLoopOrchestrator(project_root=".")
    mock_input = MagicMock()
    mock_input.task_id = "PASS-TEST"

    # Mock 物理診斷全 PASS
    with patch("nexus.core.dual_loop_orchestrator.XRayObserver") as MockObserver:
        mock_instance = MockObserver.return_value
        mock_report = MagicMock()
        mock_report.risks = []
        mock_instance.scan.return_value = mock_report
        
        # 確保 Spec 檔案存在
        Path("./MUSE-NEXUS-Engine-Specification-v22-Eternal.md").touch()
        
        result = await orchestrator.dual_diagnose(mock_input)
        assert result["status"] == "PASS"
        assert result["provider"] == "gemini-3-flash"

@pytest.mark.asyncio
async def test_consensus_veto_dependency():
    """Case B: 大腦 PASS 但 X-Ray 偵測到違規依賴 (Veto)"""
    orchestrator = DualLoopOrchestrator(project_root=".")
    mock_input = MagicMock()
    mock_input.task_id = "VETO-DEP"

    with patch("nexus.core.dual_loop_orchestrator.XRayObserver") as MockObserver:
        mock_instance = MockObserver.return_value
        mock_report = MagicMock()
        mock_report.risks = ["External dependency found: requests"]
        mock_instance.scan.return_value = mock_report
        
        result = await orchestrator.dual_diagnose(mock_input)
        assert result["status"] == "FAIL"
        assert "Dependency Risk" in result["reason"]

@pytest.mark.asyncio
async def test_consensus_veto_contract():
    """Case C: 大腦 PASS 但核心契約 (Spec) 缺失 (Veto)"""
    # 建立一個暫存目錄模擬缺失 Spec 的環境
    temp_root = "./temp_test_root"
    os.makedirs(temp_root, exist_ok=True)
    orchestrator = DualLoopOrchestrator(project_root=temp_root)
    mock_input = MagicMock()
    
    result = await orchestrator.dual_diagnose(mock_input)
    assert result["status"] == "FAIL"
    assert "Contract Breach" in result["reason"]
    
    # 清理
    os.rmdir(temp_root)

@pytest.mark.asyncio
async def test_consensus_veto_slop():
    """Case D: 大腦 PASS 但物理審核發現 Slop 或空函式 (Veto)"""
    orchestrator = DualLoopOrchestrator(project_root=".")
    mock_input = MagicMock()
    
    # 通過 Patch 注入 aesthetic_result FAIL 模擬 Slop
    with patch("nexus.core.dual_loop_orchestrator.CritiqueEngine") as MockCritique:
        mock_engine = MockCritique.return_value
        # 模擬物理診斷中的美學失敗
        with patch.object(DualLoopOrchestrator, "physical_audit", return_value={"provider": "physical-auditor", "status": "FAIL", "reason": "Aesthetic Deviation (75)"}):
            result = await orchestrator.dual_diagnose(mock_input)
            assert result["status"] == "FAIL"
            assert "Aesthetic Deviation" in result["reason"]

if __name__ == "__main__":
    pytest.main([__file__])
