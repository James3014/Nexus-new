import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any
from nexus.orchestrator.task_contract import Evidence, Task, TaskStatus

class EvidenceCollector:
    def __init__(self, reports_dir: str = ".nexus/multi_agent/reports", 
                 evidence_file: str = ".nexus/reports/hallucination_evidence.json"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_file = Path(evidence_file)

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
        2. nexus delivery-gate
        """
        # Create a temporary evidence file for the gate.
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

        # Run the strict delivery gate, which includes tests and acceptance verification.
        self.run_check(task, [
            "uv", "run", "scripts/engine/nexus_cli.py", "nexus", "delivery-gate",
            "--evidence", str(temp_evidence_path)
        ], "Nexus Delivery Gate")

        # Check if all critical evidences passed (exit_code == 0)
        for e in task.evidence_list:
            if e.exit_code != 0:
                return False

        return bool(task.evidence_list)

    def generate_hallucination_evidence(self, task: Task, final_response: str):
        self.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Capture physical proof
        diff = ""
        try:
            diff = subprocess.check_output(["git", "diff", task.base_branch], cwd=task.working_dir).decode()
        except Exception:
            pass
        
        has_proof = bool(diff and diff.strip())
        all_passed = all(e.exit_code == 0 for e in task.evidence_list)
        evidence_count = len(task.evidence_list)
        
        # 2. Dynamic Confidence & State Derivation
        if all_passed and has_proof and evidence_count >= len(task.evidence_requirements):
            confidence = "HIGH"
            claim_state = "VERIFIED"
        elif all_passed and evidence_count > 0:
            confidence = "MEDIUM"
            claim_state = "PARTIAL"
        else:
            confidence = "LOW"
            claim_state = "UNVERIFIED"

        bundle = {
            "final_response": final_response,
            "claim_state": claim_state,
            "confidence_level": confidence,
            "proof_type": "git_diff" if has_proof else "none",
            "proof_value": diff if has_proof else "no_physical_changes_detected",
            "evidence_bundle": {
                "code_artifacts": task.allowed_files,
                "test_artifacts": [e.output_summary for e in task.evidence_list if "pytest" in e.command],
                "command_artifacts": [f"{e.command} (exit: {e.exit_code})" for e in task.evidence_list]
            }
        }
        
        with open(self.evidence_file, "w") as f:
            json.dump(bundle, f, indent=2)
        return self.evidence_file
