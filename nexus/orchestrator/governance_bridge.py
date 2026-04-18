import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict

def append_governance_event(project_root: str, payload: Dict[str, Any]):
    log_path = Path(project_root) / ".nexus/metrics/skill_outcome_events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    event = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_id": payload.get("task_id", "unknown"),
        "phase": payload.get("phase", "M"), # M for Multi-agent
        "decision_id": payload.get("decision_id", "dec_multi_agent"),
        "skill_id": payload.get("skill_id", "orchestrator"),
        "pass": payload.get("pass", True),
        "fail": not payload.get("pass", True),
        "phantom_blocked": payload.get("phantom_blocked", False),
        "regression_pass_rate": payload.get("regression_pass_rate", 100.0),
        "proof_present": payload.get("proof_present", True),
        "source": "multi_agent.orchestrator"
    }
    
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")
