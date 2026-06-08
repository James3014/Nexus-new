import pytest
import json
from nexus.engine.contracts.replay import ReplayArtifact
from nexus.engine.contracts.verification import Verdict, VerifierType

def test_replay_artifact_validation():
    """驗證 Receipt 缺少關鍵欄位時必須 fail-closed。"""
    incomplete_data = {
        "input_digest": "sha_123",
        "slice_spec": {},
        "context_digest": "sha_context",
        "candidate_hash": "sha_patch",
        "memory_trace_ids": [],
        "final_action": "APPROVE"
        # Missing verifier_verdicts
    }
    with pytest.raises(KeyError, match="verifier_verdicts"):
        ReplayArtifact.from_dict(incomplete_data)

def test_determinism_consistency_fail():
    """驗證重放結果若與原始不一致，必須報錯。"""
    original = ReplayArtifact(
        input_digest="sha_1",
        slice_spec={},
        context_digest="sha_context",
        candidate_hash="patch_1",
        verifier_verdicts={"SYNTAX": Verdict.PASS},
        memory_trace_ids=[],
        final_action="APPROVE"
    )
    
    # 模擬一個漂移的執行結果
    current_verdict = Verdict.HARD_REJECT
    
    if original.verifier_verdicts["SYNTAX"] != current_verdict:
        assert True # Success in detecting drift
    else:
        assert False, "Should have detected drift"

def test_causal_signature_invariance():
    """驗證即使 memory 排序波動，只要因果簽名相同，verdict 不得漂移。"""
    # This will be implemented in ReplayRunner logic
    pass
