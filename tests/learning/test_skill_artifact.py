import pytest
from nexus.learning.skill_artifact import build_skill_artifact
import yaml

def test_build_skill_artifact_success_with_research():
    task_id = "bug-123"
    task_desc = "Fix websocket race condition"
    research_pack = {
        "budget_used": {"rounds": 5},
        "winner": {"hypothesis_id": "H3", "content": "use mutex"}
    }
    repair_result = {
        "metrics": {"retry_count": 2},
        "diagnosis": "Missing mutex",
        "patches": [{"file": "main.go", "diff": "+ mutex.Lock()"}]
    }
    outcome_event = {
        "passed": True,
        "task_type": "bug",
        "metrics": {"pattern_reuse_rate": 0.1}
    }
    
    result = build_skill_artifact(task_id, task_desc, research_pack, repair_result, outcome_event)
    assert result is not None
    
    # Check yaml parseable
    parts = result.split("---")
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    
    assert fm["name"] == "fix-websocket-race-condition"
    assert fm["task_id"] == "bug-123"
    assert fm["success_metric"]["repair_success"] is True
    assert fm["success_metric"]["retry_count"] == 2
    assert "bug" in fm["keywords"]
    assert "research" in fm["keywords"]
    
    assert "# 任務描述" in result
    assert "Fix websocket race condition" in result
    assert "# 診斷與修復" in result
    assert "# 實驗與研究證據" in result
    assert "H3" in result

def test_build_skill_artifact_skip_trivial():
    # If retry_count is 0 and no research, it should return None
    result = build_skill_artifact(
        "task-1", "test", None,
        {"metrics": {"retry_count": 0}},
        {"passed": True, "metrics": {"pattern_reuse_rate": 0.0}}
    )
    assert result is None

def test_build_skill_artifact_skip_high_reuse():
    # If reuse rate is >= 0.5, it should return None
    result = build_skill_artifact(
        "task-1", "test", {"dummy": "research"},
        {"metrics": {"retry_count": 0}},
        {"passed": True, "metrics": {"pattern_reuse_rate": 0.6}}
    )
    assert result is None

def test_build_skill_artifact_skip_failed():
    # If passed is False, it should return None
    result = build_skill_artifact(
        "task-1", "test", {"dummy": "research"},
        {"metrics": {"retry_count": 2}},
        {"passed": False, "metrics": {"pattern_reuse_rate": 0.1}}
    )
    assert result is None
