"""
🛡️ Nexus Bug Fingerprint: 單元測試 (P2-C)
驗證相似 Traceback 召回與成功修復過濾邏輯。
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from nexus.services.bug_fingerprint import find_similar_bugs, get_repair_recommendations

@pytest.fixture
def mock_successful_candidates():
    """模擬 Hybrid Retrieval 候選清單"""
    return [
        {
            "lesson_id": "L1",
            "outcome": "success",
            "corrective_action": "Replace localtime with UTC",
            "category": "AUTH",
            "root_cause": "Timezone mismatch",
            "success_rate": 0.9,
            "_vector_distance": 0.1
        },
        {
            "lesson_id": "L2",
            "outcome": "fail", # 應過濾掉
            "corrective_action": "Increase timeout",
            "category": "AUTH",
            "root_cause": "Network lag",
            "_vector_distance": 0.2
        },
        {
            "task_id": "T3", # 也支援 task_id
            "outcome": "success",
            "corrective_action": "Add specific close() call",
            "category": "DB",
            "root_cause": "Connection leak",
            "success_rate": 1.0,
            "_vector_distance": 0.3
        }
    ]

@patch("nexus.services.bug_fingerprint.retrieve_hybrid_candidates")
def test_find_similar_bugs_filter(mock_retrieve, mock_successful_candidates):
    """驗證僅召回成功且具備修復模板的記錄"""
    mock_retrieve.return_value = mock_successful_candidates
    
    repo_root = Path("/tmp/mock")
    results = find_similar_bugs(repo_root, "auth timeout", category="AUTH")
    
    # 應僅保留 L1 和 T3
    assert len(results) == 2
    assert results[0]["lesson_id"] == "L1"
    assert results[1]["lesson_id"] == "local_temp" # T3 沒有 lesson_id 但有修正模板
    assert results[0]["similarity"] == 0.1
    print("\n✅ Bug Fingerprint Recall Verified")

@patch("nexus.services.bug_fingerprint.retrieve_hybrid_candidates")
def test_get_repair_recommendations_no_data(mock_retrieve):
    """驗證無資料時不崩潰並回傳 Prompt Context"""
    mock_retrieve.return_value = []
    
    repo_root = Path("/tmp/mock")
    result = get_repair_recommendations(repo_root, {"traceback_snippet": "unknown error"})
    
    assert result["status"] == "ok"
    assert result["total_matches"] == 0
    assert "No similar successful fixes" in result["prompt_context"]
    print("✅ Bug Fingerprint Empty Case Verified")
