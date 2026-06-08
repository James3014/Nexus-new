import pytest
from pathlib import Path
from nexus.engine.contracts.replay import ReplayArtifact
from nexus.engine.replay_runner import ReplayRunner, ReceiptWriter

def test_same_input_same_verdict(tmp_path):
    """驗證同輸入同判決的決定論性質。"""
    project_root = tmp_path / "repo"
    project_root.mkdir()
    
    artifact = ReplayArtifact(
        input_digest="sha_abc",
        slice_spec={"depth": 5},
        context_digest="ctx_123",
        candidate_hash="patch_999",
        verifier_verdicts={"SYNTAX": "PASS", "CONTRACT": "PASS"},
        memory_trace_ids=["evt_1"],
        final_action="APPROVE"
    )
    
    # 寫入
    writer = ReceiptWriter(tmp_path / "reports")
    receipt_path = writer.write(artifact)
    assert receipt_path.exists()
    
    # 重放
    runner = ReplayRunner(project_root)
    assert runner.replay(artifact) is True

def test_replay_comparison_diff(tmp_path):
    """驗證兩次執行的差異化比較能力。"""
    artifact_a = ReplayArtifact(
        input_digest="sha_1",
        slice_spec={},
        context_digest="ctx_a",
        candidate_hash="p1",
        verifier_verdicts={"SEMANTIC": "FAIL"},
        memory_trace_ids=[],
        final_action="REJECT"
    )
    
    artifact_b = ReplayArtifact(
        input_digest="sha_1", # Same input
        slice_spec={},
        context_digest="ctx_b", # Different context (e.g. after optimization)
        candidate_hash="p2",
        verifier_verdicts={"SEMANTIC": "PASS"},
        memory_trace_ids=[],
        final_action="APPROVE"
    )
    
    # 計算簽名差異
    sig_a = artifact_a.compute_replay_signature()
    sig_b = artifact_b.compute_replay_signature()
    
    assert sig_a != sig_b # 證明架構變更能被簽名識別
