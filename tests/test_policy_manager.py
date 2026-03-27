import pytest
from unittest.mock import patch
from nexus.core.policy_manager import PolicyManager
from nexus.core.state_contracts import NexusState

def test_policy_hit_os_rule():
    """驗證 PolicyManager 能根據任務描述命中規則 (Week 2 M2)"""
    pm = PolicyManager(".")
    state = NexusState(task_id="test-os-task")
    
    # 模擬包含 'os' 的任務描述
    with patch.object(
        pm,
        "propose_policy",
        return_value=[{"rule_id": "POL-001", "content": "use os.path", "confidence": 0.9, "status": "validated"}],
    ):
        pm.apply_policy_to_state(state, "Fix missing os.path imports in utils.py")
    
    # 驗證
    assert state.policy_applied is True
    assert "POL-001" in state.policy_hit_ids
    print(f"✅ Policy hit success: {state.policy_hit_ids}")

def test_episode_recording():
    """驗證 Episode 能正確寫入文件 (Week 1 M1)"""
    pm = PolicyManager(".")
    state = NexusState(task_id="test-episode-1")
    state.health_score = 95.0
    
    pm.record_episode(state)
    
    assert pm.episode_file.exists()
    print(f"✅ Episode recorded to: {pm.episode_file}")


def test_policy_manager_ingests_episode_when_learning_not_frozen():
    pm = PolicyManager(".")
    state = NexusState(task_id="test-episode-ingest")
    state.metadata["pipeline_success"] = True
    state.metadata["last_patch_generated"] = False

    with patch.object(pm.memory_service, "ingest_episode") as ingest:
        pm.record_episode(state)

    ingest.assert_called_once()
    assert state.metadata["learning_ingest_status"] == "ingested"


def test_policy_manager_skips_ingest_when_learning_frozen():
    pm = PolicyManager(".")
    state = NexusState(task_id="test-episode-freeze")
    state.metadata["pipeline_success"] = True
    state.metadata["last_review_status"] = "APPROVED"
    state.metadata["last_patch_generated"] = True
    state.metadata["last_patch_apply_success"] = True
    state.metadata["last_proof_type"] = ""
    state.metadata["last_proof_value"] = ""

    with patch.object(pm.memory_service, "ingest_episode") as ingest:
        pm.record_episode(state)

    ingest.assert_not_called()
    assert state.metadata["learning_ingest_status"] == "skipped_frozen"
