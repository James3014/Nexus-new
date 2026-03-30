import json
from pathlib import Path
from nexus.delivery.incident_pack import collect_incident_pack, IncidentPack

def test_collect_incident_pack_creates_file(tmp_path):
    """測試事故重播包可以正確收集與生成檔案"""
    project_root = tmp_path / "nexus_root"
    run_dir = project_root / ".nexus" / "replays" / "TEST-123"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # 建立假檔案以供收集
    plan_data = {"goal": "Test incident pack", "steps": []}
    (run_dir / "plan.json").write_text(json.dumps(plan_data))
    
    trace_dir = project_root / ".nexus" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.joinpath("traces.jsonl").write_text(
        json.dumps({"task_id": "TEST-123", "event_type": "span"}) + "\n" +
        json.dumps({"task_id": "OTHER-456", "event_type": "span"}) + "\n"
    )
    
    # 執行收集
    out_path = collect_incident_pack(
        run_dir=run_dir,
        task_id="TEST-123",
        task_desc="Test task",
        terminal_state="FAILED",
        project_root=project_root
    )
    
    assert out_path is not None
    assert out_path.exists()
    
    # 驗證內容
    data = json.loads(out_path.read_text())
    assert data["task_id"] == "TEST-123"
    assert data["task_desc"] == "Test task"
    assert data["terminal_state"] == "FAILED"
    
    # run_dir snapshot 必須包含 plan.json
    assert "plan.json" in data["run_dir_snapshot"]
    assert data["run_dir_snapshot"]["plan.json"]["goal"] == "Test incident pack"
    
    # trace events 必須過濾
    assert len(data["trace_events"]) == 1
    assert data["trace_events"][0]["task_id"] == "TEST-123"
