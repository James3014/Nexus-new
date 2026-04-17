import json
import yaml
from pathlib import Path
from typing import List, Dict, Any

class PlanExecutionManager:
    """📜 Nexus Plan Manager: One-time approval for batch execution."""
    
    def __init__(self, project_root: Path):
        self.root = project_root
        self.contract_path = project_root / ".nexus" / "config" / "execution_contract.json"

    def generate_contract(self, tasks: List[Dict[str, Any]]):
        contract = {
            "version": "v1.0",
            "approved_at": None,
            "status": "DRAFT",
            "allowed_tasks": [t["id"] for t in tasks],
            "forbidden_patterns": ["rm -rf", "git reset --hard"],
            "nodes": tasks
        }
        self.contract_path.parent.mkdir(parents=True, exist_ok=True)
        self.contract_path.write_text(json.dumps(contract, indent=2))
        return self.contract_path

    def is_task_approved(self, task_id: str) -> bool:
        if not self.contract_path.exists():
            return False
        data = json.loads(self.contract_path.read_text())
        return data.get("status") == "APPROVED" and task_id in data.get("allowed_tasks", [])

    def approve_plan(self):
        if not self.contract_path.exists():
            return False
        data = json.loads(self.contract_path.read_text())
        data["status"] = "APPROVED"
        data["approved_at"] = "NOW" # Should be real timestamp
        self.contract_path.write_text(json.dumps(data, indent=2))
        return True
