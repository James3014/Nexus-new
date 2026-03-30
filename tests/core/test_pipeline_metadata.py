import pytest
from nexus.core.pipeline_metadata import PipelineMetadata

def test_pipeline_metadata_instantiation():
    """驗證 PipelineMetadata (TypedDict) 的實例化。"""
    # TypedDict 在執行期是普通的 dict，主要用於靜態類型檢查
    meta: PipelineMetadata = {
        "task_description": "Fix bug",
        "pipeline_success": True,
        "escalation_count": 0,
        "human_review_required": False
    }
    assert meta["task_description"] == "Fix bug"
    assert meta.get("pipeline_success") is True
    assert meta.get("escalation_count") == 0

def test_pipeline_metadata_nested_fields():
    """驗證巢狀字典欄位的存取。"""
    meta: PipelineMetadata = {
        "nexus_outcome_v2": {"exit_code": 0, "terminal_state": "SUCCESS"},
        "health_snapshot": {"disk_ok": True},
        "phantom_pattern_history": ["p1", "p2"]
    }
    assert meta["nexus_outcome_v2"]["exit_code"] == 0
    assert meta["health_snapshot"]["disk_ok"] is True
    assert "p1" in meta["phantom_pattern_history"]

def test_pipeline_metadata_optional_fields():
    """驗證 Optional 欄位。"""
    meta: PipelineMetadata = {}
    assert meta.get("task_type") is None
    meta["task_type"] = "repair"
    assert meta["task_type"] == "repair"
