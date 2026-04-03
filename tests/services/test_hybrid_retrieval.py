import pytest
import json
from pathlib import Path
from nexus.services.memory_indexer import rebuild_memory_index
from nexus.services.lesson_retrieval import retrieve_with_resolution
from nexus.services.continuous_learning import LessonEvent

@pytest.fixture
def mock_repo(tmp_path):
    # 建立精簡 Nexus 結構
    (tmp_path / ".nexus/knowledge").mkdir(parents=True)
    (tmp_path / ".nexus/learning").mkdir(parents=True)
    (tmp_path / ".nexus/runs/run1").mkdir(parents=True)
    
    # 1. 寫入 Local Lesson
    lesson = {
        "lesson_id": "L1",
        "category": "PYTHON",
        "root_cause": "Syntax error in list comprehension",
        "corrective_action": "Use proper bracket syntax",
        "timestamp_utc": "2026-04-01T10:00:00Z",
        "confidence": 0.9,
    }
    (tmp_path / ".nexus/knowledge/lesson_events.jsonl").write_text(json.dumps(lesson) + "\n")
    
    # 2. 寫入 Shared Lesson
    shared = {
        "cache_id": "S1",
        "trust_tier": "peer",
        "local_weight": 0.85,
        "lesson": {
            "lesson_id": "L2",
            "category": "OS",
            "root_cause": "Permissions denied on /tmp/nexus",
            "corrective_action": "chmod 755 /tmp/nexus",
            "timestamp_utc": "2026-04-02T10:00:00Z",
        }
    }
    (tmp_path / ".nexus/learning/shared_lessons.jsonl").write_text(json.dumps(shared) + "\n")
    
    return tmp_path

def test_index_rebuild_and_semantic_recall(mock_repo):
    """驗證索引重建與語義召回（純向量路徑）"""
    # 1. 執行重建
    res = rebuild_memory_index(mock_repo)
    assert res["status"] == "ok"
    assert res["records_processed"] >= 2, f"Expected >=2 records, got {res['records_processed']}"

    # 2. 純向量路徑：直接呼叫 candidate generator
    from nexus.services.lesson_retrieval import retrieve_lancedb_candidates
    candidates = retrieve_lancedb_candidates(
        mock_repo,
        "Fixing permission denied errors on tmp directories",
        limit=3
    )
    # 必須有候選集 (Vector 路徑工作中)
    assert len(candidates) > 0, "Vector search returned no candidates"
    
    # 候選集中至少包含一個 OS 教訓 (L2)
    lesson_ids = [c.get("lesson_id") for c in candidates]
    assert "L2" in lesson_ids, f"Expected OS lesson L2 in candidates, got: {lesson_ids}"

    # 3. 驗證混合檢索 (Hybrid) 最終結果
    result_ctx = retrieve_with_resolution(
        mock_repo,
        "Fixing permission denied errors on tmp directories",
        diagnosis={"category": "OS"}
    )
    content = result_ctx["prompt_context"]
    assert "Permissions denied" in content or "chmod 755" in content, f"OS lesson not in context: {content}"
    assert result_ctx["consensus_score"] > 0.4

def test_index_idempotency(mock_repo):
    """驗證冪等性：重複 rebuild 記錄數不應倒増。
    
    注：P2-A v0.1 使用 Full Rebuild，所以兩次結果應相同。
    """
    res1 = rebuild_memory_index(mock_repo)
    res2 = rebuild_memory_index(mock_repo)
    assert res1["records_processed"] == res2["records_processed"], (
        f"Idempotency failed: {res1['records_processed']} != {res2['records_processed']}"
    )

def test_hybrid_fallback_on_db_missing(mock_repo):
    """驗證當資料庫缺失時，自動回退至 Lexical 檢索"""
    # 刪除 LanceDB
    import shutil
    shutil.rmtree(mock_repo / ".nexus/memory", ignore_errors=True)
    
    # 檢索 (提問：Syntax error)
    result_ctx = retrieve_with_resolution(
        mock_repo, 
        "Python list comprehension syntax fix"
    )
    
    # 斷言：雖然 DB 沒了，但 Lexical Fallback 應能抓到 L1
    assert "Syntax error" in result_ctx["prompt_context"]
    assert result_ctx["consensus_score"] > 0.4
