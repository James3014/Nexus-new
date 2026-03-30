import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class IncidentPack:
    """📦 事故重播包 (P1-B Incident Pack)"""
    task_id: str
    task_desc: str
    terminal_state: str
    run_dir_snapshot: Dict[str, Any]
    trace_events: list[Dict[str, Any]]
    outcome_event: Optional[Dict[str, Any]] = None

def collect_incident_pack(run_dir: Path, task_id: str, task_desc: str, terminal_state: str, project_root: Path) -> Optional[Path]:
    """收集指定 task_id 的事故重播包"""
    pack = IncidentPack(
        task_id=task_id,
        task_desc=task_desc,
        terminal_state=terminal_state,
        run_dir_snapshot={},
        trace_events=[]
    )
    
    # 1. 收集 run_dir 的 JSON 檔案
    target_files = ["plan.json", "diagnosis.json", "repairfinal.json", "auditresult.json", "manifest.json", "events_sourced.jsonl"]
    for file_name in target_files:
        file_path = run_dir / file_name
        if file_path.exists():
            try:
                if file_name.endswith(".jsonl"):
                    lines = file_path.read_text().splitlines()
                    pack.run_dir_snapshot[file_name] = [json.loads(l) for l in lines if l.strip()]
                else:
                    pack.run_dir_snapshot[file_name] = json.loads(file_path.read_text())
            except Exception as e:
                logger.warning(f"Failed to read {file_name}: {e}")

    # 2. 收集 trace events (.nexus/traces/traces.jsonl)
    trace_file = project_root / ".nexus" / "traces" / "traces.jsonl"
    if trace_file.exists():
        try:
            for line in trace_file.read_text().splitlines():
                if not line.strip(): continue
                evt = json.loads(line)
                if evt.get("task_id") == task_id or evt.get("attributes", {}).get("task_id") == task_id:
                    pack.trace_events.append(evt)
        except Exception as e:
            logger.warning(f"Failed to read traces: {e}")

    # 3. 收集 outcome event (.nexus/telemetry/skill_outcome_events.jsonl)
    outcome_file = project_root / ".nexus" / "telemetry" / "skill_outcome_events.jsonl"
    if outcome_file.exists():
        try:
            for line in outcome_file.read_text().splitlines():
                if not line.strip(): continue
                evt = json.loads(line)
                if evt.get("task_id") == task_id:
                    pack.outcome_event = evt
                    # 假定最新的就是我們要的 (如果同 task_id 有多筆)
        except Exception as e:
            logger.warning(f"Failed to read outcome events: {e}")
            
    # 寫入 incidents 目錄
    incident_dir = project_root / ".nexus" / "incidents"
    incident_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = incident_dir / f"incident_{task_id}.json"
    with open(out_path, "w") as f:
        json.dump(asdict(pack), f, indent=2)
        
    logger.info(f"📦 Incident Pack collected for {task_id}: {out_path}")
    return out_path
