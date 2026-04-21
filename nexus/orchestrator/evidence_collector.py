import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any
from nexus.orchestrator.task_contract import Evidence, EvidenceRequirement, Task, TaskStatus
from nexus.orchestrator.evidence_policy import build_temp_evidence_payload
from nexus.orchestrator.evidence_policy import derive_claim_bundle
from nexus.orchestrator.evidence_policy import missing_pre_gate_requirements

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
        missing_pre_gate = missing_pre_gate_requirements(task)
        if missing_pre_gate:
            task.add_evidence(Evidence(
                command="evidence-precheck",
                exit_code=2,
                output_summary=(
                    "Missing required evidence before delivery gate: "
                    + ", ".join(
                        req.value if isinstance(req, EvidenceRequirement) else str(req)
                        for req in missing_pre_gate
                    )
                ),
            ))
            return False

        # Create a temporary evidence file for the gate.
        temp_evidence_path = self.reports_dir / f"{task.task_id}_temp_evidence.json"
        with open(temp_evidence_path, "w") as f:
            json.dump(build_temp_evidence_payload(task), f)

        # Run the strict delivery gate, which includes tests and acceptance verification.
        self.run_check(task, [
            "uv", "run", "scripts/engine/nexus_cli.py", "nexus", "delivery-gate",
            "--evidence", str(temp_evidence_path)
        ], "Nexus Delivery Gate")

        # Check if all critical evidences passed (exit_code == 0)
        for e in task.evidence_list:
            if e.exit_code != 0:
                return False

        return bool(task.evidence_list) and not task.missing_evidence_requirements()

    def generate_hallucination_evidence(self, task: Task, final_response: str):
        self.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Capture physical proof
        diff = ""
        try:
            diff = subprocess.check_output(["git", "diff", task.base_branch], cwd=task.working_dir).decode()
        except Exception:
            pass
        bundle = derive_claim_bundle(task, final_response, diff)
        
        with open(self.evidence_file, "w") as f:
            json.dump(bundle, f, indent=2)
        return self.evidence_file
# integrity-seal: 1776512137
