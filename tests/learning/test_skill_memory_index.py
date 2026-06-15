from __future__ import annotations
import json
from pathlib import Path
from nexus.learning.skill_memory_index import SkillMemoryIndex, SkillHistoryRecord

def test_skill_memory_index_load_and_query(tmp_path) -> None:
    # 建立模擬指標檔案與資料夾
    metrics_dir = tmp_path / ".nexus/metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    
    skills_dir = tmp_path / ".agents/skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 寫入 outcome 記錄 (2次成功，1次失敗)
    outcome_file = metrics_dir / "skill_outcome_events.jsonl"
    outcomes = [
        {"skill_id": "test-skill-1", "pass": True, "status": "success", "evidence_refs": ["ref-1"]},
        {"skill_id": "test-skill-1", "pass": False, "status": "assertion_error", "evidence_refs": []},
        {"skill_id": "test-skill-1", "pass": True, "status": "success", "evidence_refs": ["ref-2", "ref-1"]},
        {"skill_id": "test-skill-2", "pass": False, "status": "syntax_error", "evidence_refs": []}
    ]
    with outcome_file.open("w", encoding="utf-8") as f:
        for out in outcomes:
            f.write(json.dumps(out) + "\n")
            
    # 2. 寫入 usage 記錄
    usage_file = skills_dir / ".usage_log.jsonl"
    usages = [
        {"skill_id": "test-skill-1", "used_at": "2026-06-15T00:00:00Z"},
        {"skill_id": "test-skill-1", "used_at": "2026-06-15T01:00:00Z"},
        {"skill_id": "test-skill-2", "used_at": "2026-06-15T02:00:00Z"}
    ]
    with usage_file.open("w", encoding="utf-8") as f:
        for usg in usages:
            f.write(json.dumps(usg) + "\n")
            
    # 3. 寫入 skill frontmatter md 檔案
    skill_md = skills_dir / "test-skill-1.md"
    skill_md.write_text("""---
title: Test Skill 1
trust_level: L2-promoted
---
# Content here
""")

    # 執行測試
    index = SkillMemoryIndex(tmp_path)
    
    # 測試 test-skill-1 查詢
    rec1 = index.query_skill_history("test-skill-1")
    assert rec1.skill_id == "test-skill-1"
    assert rec1.reuse_count == 2
    assert rec1.recent_success_rate == 2.0 / 3.0
    assert rec1.recent_failure_modes == ["assertion_error"]
    assert rec1.last_used_at == "2026-06-15T01:00:00Z"
    assert rec1.trust_level == "L2-promoted"
    assert set(rec1.evidence_refs) == {"ref-1", "ref-2"}
    
    # 測試 test-skill-2 查詢
    rec2 = index.query_skill_history("test-skill-2")
    assert rec2.skill_id == "test-skill-2"
    assert rec2.reuse_count == 1
    assert rec2.recent_success_rate == 0.0
    assert rec2.recent_failure_modes == ["syntax_error"]
    assert rec2.trust_level == "auto-generated"

    # 測試 build_context_injection
    ctx = index.build_context_injection("test-skill-1")
    assert "Success rate: 66.7%" in ctx
    assert "Used 2 times" in ctx
    assert "Failure modes: assertion_error" in ctx
    assert "Trust level: L2-promoted" in ctx

def test_skill_memory_index_empty_fallback(tmp_path) -> None:
    # 測試在完全沒有任何檔案的情況下，不應崩潰且正常回傳空記錄
    index = SkillMemoryIndex(tmp_path)
    rec = index.query_skill_history("non-existent")
    assert rec.skill_id == "non-existent"
    assert rec.reuse_count == 0
    assert rec.recent_success_rate == 0.0
    assert rec.recent_failure_modes == []
    assert rec.trust_level == "auto-generated"
    assert rec.evidence_refs == []
