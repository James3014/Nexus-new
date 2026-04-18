import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any
from nexus.orchestrator.task_contract import Evidence, Task, TaskStatus

class EvidenceCollector:
    def __init__(self, reports_dir: str = ".nexus/multi_agent/reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run_check(self, task: Task, command: List[str], description: str) -> Evidence:
        """Runs a check command and returns an Evidence object."""
        result = subprocess.run(command, capture_output=True, text=True)
        evidence = Evidence(
            command=" ".join(command),
            exit_code=result.returncode,
            output_summary=result.stdout[-1000:] if result.stdout else result.stderr[-1000:]
        )
        task.add_evidence(evidence)
        return evidence

    def verify_gate(self, task: Task) -> bool:
        """
        Runs mandatory gates:
        1. pytest (if specified in criteria)
        2. nexus acceptance-check
        """
        # 1. Run pytest
        self.run_check(task, ["pytest"], "Mandatory unit tests")
        
        # 2. Run nexus acceptance-check
        # Create a temporary evidence file for the CLI
        temp_evidence_path = self.reports_dir / f"{task.task_id}_temp_evidence.json"
        with open(temp_evidence_path, "w") as f:
            json.dump({
                "final_response": "Automated verification",
                "evidence_bundle": {
                    "code_artifacts": task.allowed_files,
                    "test_artifacts": ["pytest results in evidence_list"],
                    "command_artifacts": [e.command for e in task.evidence_list]
                }
            }, f)
        
        self.run_check(task, [
            "uv", "run", "scripts/engine/nexus_cli.py", "nexus", "acceptance-check",
            "--evidence", str(temp_evidence_path)
        ], "Nexus Acceptance Check")

        # Check if all critical evidences passed (exit_code == 0)
        # Note: Some criteria might allow failure, but for P0 we enforce success.
        for e in task.evidence_list:
            if e.exit_code != 0:
                return False
        
        return task.is_done_ready()

    def generate_hallucination_evidence(self, task: Task, final_response: str):
        evidence_path = Path(".nexus/reports/hallucination_evidence.json")
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        
        bundle = {
            "final_response": final_response,
            "evidence_bundle": {
                "code_artifacts": task.allowed_files,
                "test_artifacts": [e.output_summary for e in task.evidence_list if "pytest" in e.command],
                "command_artifacts": [f"{e.command} (exit: {e.exit_code})" for e in task.evidence_list]
            }
        }
        
        with open(evidence_path, "w") as f:
            json.dump(bundle, f, indent=2)
        return evidence_path
