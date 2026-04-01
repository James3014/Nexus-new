import pytest
from nexus.core.xray_observer import XRayObserver
from nexus.core.swarm_orchestrator import TypedHandoffAdapter
from nexus.core.state_contracts import NexusState
from nexus.executors.protocol import ExecutorOutput, ExecutorStatusEnum

def test_xray_observer_static_scan():
    """驗證 X-Ray 觀察者能否在 nexus/core/ 下正確掃描依賴"""
    observer = XRayObserver("nexus/core")
    report = observer.scan()
    
    # 斷言 1: 應能識別到 swarm_orchestrator.py
    orchestrator_imports = [c for c in report.crossings if c["source"] == "swarm_orchestrator.py"]
    assert len(orchestrator_imports) > 0, "Should find imports in swarm_orchestrator.py"
    
    # 斷言 2: 應能識別到對 state_contracts 的導入
    targets = [c["target"] for c in orchestrator_imports]
    assert "nexus.core.state_contracts" in targets or "state_contracts" in targets, \
        f"Should identify state_contracts dependency in {targets}"

def test_xray_typed_handoff_mapping():
    """驗證 OBSERVE 階段能正確通過 Typed Handoff 映射至 X"""
    adapter = TypedHandoffAdapter()
    state = NexusState(task_id="POC-XRAY-001")
    
    # 模擬 X-Ray 觀察者的輸出
    mock_output = ExecutorOutput(
        executor_name="XRayObserver",
        phase="OBSERVE",
        status=ExecutorStatusEnum.SUCCESS,
        patch_generated=False,
        evidence_present=True,
        raw_exit_code=0,
        summary="Scan complete.",
        meta={"symbols_found": 42}
    )
    
    updated_state = adapter.sync_output_to_state(state, mock_output)
    
    # 斷言 3: Phase 應映射為 X
    last_step = updated_state.steps_history[-1]
    assert last_step.phase == "X", f"Phase OBSERVE should map to X, but got {last_step.phase}"
    assert last_step.metadata["executor"] == "XRayObserver"

if __name__ == "__main__":
    pytest.main([__file__])
