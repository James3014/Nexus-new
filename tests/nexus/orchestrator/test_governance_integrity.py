import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from nexus.orchestrator.governance_bridge import append_governance_event
from nexus.orchestrator.evidence_collector import EvidenceCollector
from nexus.orchestrator.task_contract import Task, Evidence

def test_governance_bridge_strict_schema(tmp_path):
    # Missing mandatory field 'pass'
    payload = {"task_id": "T1", "proof_present": True, "phantom_blocked": False}
    with pytest.raises(ValueError, match="Missing mandatory field 'pass'"):
        append_governance_event(str(tmp_path), payload)

def test_evidence_collector_low_confidence_no_proof(tmp_path):
    isol_evidence = tmp_path / "hallucination_evidence.json"
    collector = EvidenceCollector(reports_dir=str(tmp_path), evidence_file=str(isol_evidence))
    task = Task(
        task_id="T-NO-PROOF", owner="A1", allowed_files=["f1.py"],
        done_criteria=[], evidence_requirements=["pytest"]
    )
    # Add a successful evidence but no physical git diff exists
    task.add_evidence(Evidence(command="pytest", exit_code=0, output_summary="OK"))
    
    # The diff now runs through the hardened runner (#3291); a failing diff gives no proof.
    with patch("nexus.orchestrator.evidence_collector.run_hardened_git") as mock_diff:
        mock_diff.side_effect = OSError("No diff")
        evidence_path = collector.generate_hallucination_evidence(task, "Done")
        
        with open(evidence_path, "r") as f:
            data = json.load(f)
            assert data["confidence_level"] == "LOW" # All passed but no physical proof

            assert data["claim_state"] == "UNVERIFIED"

            assert str(evidence_path) == str(isol_evidence)

def test_evidence_collector_reject_verified_on_failure(tmp_path):
    isol_evidence = tmp_path / "hallucination_evidence.json"
    collector = EvidenceCollector(reports_dir=str(tmp_path), evidence_file=str(isol_evidence))
    task = Task(
        task_id="T-FAIL", owner="A1", allowed_files=["f1.py"],
        done_criteria=[], evidence_requirements=["pytest"]
    )
    # One evidence failed
    task.add_evidence(Evidence(command="pytest", exit_code=1, output_summary="FAIL"))
    
    mod = "nexus.orchestrator.evidence_collector"
    with patch(f"{mod}.repository_git_dir", return_value=tmp_path), patch(
        f"{mod}.repository_config_can_start_a_program", return_value=False
    ), patch(f"{mod}.run_hardened_git") as mock_diff:
        mock_diff.return_value = MagicMock(returncode=0, stdout="some diff")
        evidence_path = collector.generate_hallucination_evidence(task, "Done")
        
        with open(evidence_path, "r") as f:
            data = json.load(f)
            assert data["confidence_level"] == "LOW"
            assert data["claim_state"] == "UNVERIFIED"
            assert data["proof_type"] == "git_diff" # Proof exists but tests failed
            assert str(evidence_path) == str(isol_evidence)
# integrity-seal: 1776512137
