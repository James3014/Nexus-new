import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict

def append_governance_event(project_root: str, payload: Dict[str, Any]):
    """
    💎 Strict Governance Event Logger
    Requirements: 'pass', 'proof_present', 'phantom_blocked' must be explicitly provided.
    """
    log_path = Path(project_root) / ".nexus/metrics/skill_outcome_events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Validation: Mandatory fields for governance integrity
    mandatory = ["pass", "proof_present", "phantom_blocked", "task_id"]
    for field in mandatory:
        if field not in payload:
            raise ValueError(f"CRITICAL GOVERNANCE ERROR: Missing mandatory field '{field}' in payload.")
    
    event = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_id": payload["task_id"],
        "phase": payload.get("phase", "M"),
        "decision_id": payload.get("decision_id", "dec_multi_agent"),
        "skill_id": payload.get("skill_id", "orchestrator"),
        "pass": bool(payload["pass"]),
        "fail": not bool(payload["pass"]),
        "phantom_blocked": bool(payload["phantom_blocked"]),
        "regression_pass_rate": float(payload.get("regression_pass_rate", 0.0)),
        "proof_present": bool(payload["proof_present"]),
        "source": payload.get("source", "multi_agent.orchestrator")
    }
    
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")
