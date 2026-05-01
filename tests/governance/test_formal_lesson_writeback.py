import os
from pathlib import Path
from nexus.core.state_contracts import NexusState, NexusDerivation, AuditResult
from nexus.services.continuous_learning import finalize_learning_loop

def test_formal_lesson_writeback():
    project_root = Path(".")
    event_path = project_root / ".nexus" / "events" / "lessonevents.jsonl"
    
    # 清理舊資料（或記錄當前行數）
    initial_count = 0
    if event_path.exists():
        initial_count = len(event_path.read_text().splitlines())
    
    # 模擬一個 FORMAL 任務狀態
    task_id = "test-formal-writeback"
    derivation = NexusDerivation(
        task_id=task_id,
        goal="Test Writeback",
        invariants=["test_inv == True"],
        steps=[]
    )
    
    audit = AuditResult(
        audit_id="aud-test",
        reasoning_mode="FORMAL",
        formal_gate_passed=True,
        repair_status="PASS",
        smoke_status="PASS",
        summary="Test formal success"
    )
    
    state = NexusState(
        task_id=task_id,
        derivation=derivation,
        last_audit=audit.model_dump()
    )
    
    # 執行 finalize_learning_loop
    finalize_learning_loop(project_root, state, success=True, source="test-runner")
    
    # 驗證 lessonevents.jsonl
    assert event_path.exists()
    new_content = event_path.read_text().splitlines()
    assert len(new_content) > initial_count
    
    import json
    last_event = json.loads(new_content[-1]) # 使用 json.loads 代替 eval
    assert last_event["type"] == "FORMAL_REASONING_OUTCOME"
    assert last_event["details"]["task_id"] == task_id
    assert last_event["details"]["gate_passed"] is True
    
    print("Formal Lesson Writeback verified.")

if __name__ == "__main__":
    test_formal_lesson_writeback()
