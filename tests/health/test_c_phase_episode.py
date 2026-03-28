from nexus.core.policy_manager import PolicyManager
from nexus.core.state_contracts import NexusState


def test_record_episode_prefers_pipeline_success_flag(tmp_path):
    pm = PolicyManager(str(tmp_path))
    state = NexusState(task_id="ep-success-1")
    state.health_score = 0.0
    state.metadata["pipeline_success"] = True
    state.metadata["last_review_status"] = "REJECTED"
    state.metadata["metabolizer_interval"] = 1

    policy_path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    old_row = {
        "rule_id": "POL-OLD",
        "confidence": 0.1,
        "created_at": "2020-01-01T00:00:00+00:00",
        "semantic_drift": 90.0,
        "zero_decay": False,
    }
    with open(policy_path, "w", encoding="utf-8") as handle:
        import json
        handle.write(json.dumps(old_row) + "\n")

    pm.record_episode(state)

    assert state.metadata["lesson_quality"] >= 85.0
    assert state.metadata["next_run_hit_rate"] >= 75.0
    assert "memory_lock_wait_last_ms" in state.metadata
    assert "memory_lock_wait_p95_ms" in state.metadata
    assert state.metadata["metabolizer_status"] == "executed"
    assert "metabolizer_result" in state.metadata
    assert "memory_health_current" in state.metadata
    assert "negative_transfer_rate" in state.metadata


def test_record_episode_falls_back_to_review_status_when_flag_missing(tmp_path):
    pm = PolicyManager(str(tmp_path))
    state = NexusState(task_id="ep-success-2")
    state.health_score = 0.0
    state.metadata["last_review_status"] = "APPROVED"

    pm.record_episode(state)

    assert state.metadata["lesson_quality"] >= 85.0
    assert state.metadata["next_run_hit_rate"] >= 75.0
    assert "memory_lock_wait_last_ms" in state.metadata
