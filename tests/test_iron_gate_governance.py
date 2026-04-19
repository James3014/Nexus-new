import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# --- T14-A: phantom_detect.py ---
from nexus.core.phantom_detect import detect_inconclusive_success

def test_phantom_rejects_patch_apply_failed():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=True, patch_apply_success=False, no_change_reason=""
    )
    assert reason == "patch_apply_failed"

def test_phantom_rejects_missing_physical_proof():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=True, patch_apply_success=True, no_change_reason="", proof_type=""
    )
    assert reason == "missing_physical_proof"

def test_phantom_rejects_missing_no_change_reason():
    reason = detect_inconclusive_success(
        status="PASS", patch_generated=False, patch_apply_success=False, no_change_reason=""
    )
    assert reason == "missing_no_change_reason"

def test_phantom_rejects_empty_diff_with_claimed_patch():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=True, patch_apply_success=True, no_change_reason="", git_diff_empty=True
    )
    assert reason == "empty_diff_with_claimed_patch"

def test_phantom_rejects_hollow_no_change_claim():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=False, patch_apply_success=False, no_change_reason="verified working"
    )
    assert reason == "hollow_no_change_claim"

def test_phantom_rejects_verification_not_executed():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=False, patch_apply_success=False, no_change_reason="logic works", proof_type="checksum", proof_value="abc", verify_commands_executed=False
    )
    assert reason == "verification_commands_not_executed"

def test_phantom_passes_valid_result():
    reason = detect_inconclusive_success(
        status="APPROVED", patch_generated=True, patch_apply_success=True, no_change_reason="", proof_type="checksum", proof_value="abc"
    )
    assert reason is None

def test_phantom_ignores_non_pass_status():
    reason = detect_inconclusive_success(
        status="REJECTED", patch_generated=True, patch_apply_success=False, no_change_reason=""
    )
    assert reason is None

# --- T14-B: plan_quality_gate.py ---
from nexus.core.plan_quality_gate import PlanQualityGate

def test_plan_gate_rejects_missing_intent():
    gate = PlanQualityGate()
    result = gate.evaluate({"risk_score": 0.5, "handoff_readiness": 0.5, "target_files": ["a.py"]}, {})
    assert result.passed is False
    assert "intent_pass" in result.missing_fields

def test_plan_gate_rejects_low_readiness():
    gate = PlanQualityGate()
    result = gate.evaluate({"intent_pass": True, "risk_score": 0.5, "handoff_readiness": 0.1, "target_files": ["a.py"]}, {})
    assert result.passed is False

def test_plan_gate_rejects_missing_risk():
    gate = PlanQualityGate()
    result = gate.evaluate({"intent_pass": True, "handoff_readiness": 0.5, "target_files": ["a.py"]}, {})
    assert result.passed is False
    assert "risk_score" in result.missing_fields

def test_plan_gate_passes_valid_plan():
    gate = PlanQualityGate()
    # Mocking target_files which is added in T15
    result = gate.evaluate({"intent_pass": True, "risk_score": 0.3, "handoff_readiness": 0.5, "target_files": ["a.py"], "acceptance_criteria": "done", "deliverables": "file"}, {"impact_map": "yes"})
    assert result.passed is True

def test_plan_gate_warns_missing_optional_fields():
    gate = PlanQualityGate()
    result = gate.evaluate({"intent_pass": True, "risk_score": 0.3, "handoff_readiness": 0.5, "target_files": ["a.py"]}, {"impact_map": "yes"})
    assert result.passed is True
    assert len(result.warnings) > 0

# --- T14-C: evidence_verifier.py ---
from nexus.delivery.evidence_verifier import EvidenceVerifier

@patch("subprocess.run")
def test_evidence_verifier_low_trust(mock_run):
    # Mock git ls-files, git diff returns nothing
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    verifier = EvidenceVerifier(Path("."))
    res = verifier.verify({"code_artifacts": ["a.py"]})
    assert res["overall_trust"] == "LOW"

@patch("subprocess.run")
def test_evidence_verifier_high_trust(mock_run):
    def side_effect(*args, **kwargs):
        if "ls-files" in args[0]:
            return MagicMock(stdout="a.py\n", returncode=0)
        elif "diff" in args[0]:
            return MagicMock(stdout=" 1 file changed\n", returncode=0)
        else:
            return MagicMock(stdout="", returncode=0)
    mock_run.side_effect = side_effect
    
    verifier = EvidenceVerifier(Path("."))
    
    # Mock exists
    with patch("pathlib.Path.exists", return_value=True):
        res = verifier.verify({"code_artifacts": ["a.py"], "test_artifacts": ["pytest"]})
        assert res["overall_trust"] == "HIGH"

def test_evidence_verifier_dict_format():
    """T1: 驗證 dict 格式解析"""
    verifier = EvidenceVerifier(Path("."))
    with patch("pathlib.Path.exists", return_value=True):
        res = verifier._verify_code_artifacts([
            {"file_path": "a.py", "modification_type": "modified"},
            "b.py"
        ])
        assert "a.py" in res["normalized_paths"]
        assert "b.py" in res["normalized_paths"]
        assert len(res["invalid_items"]) == 0

def test_evidence_verifier_invalid_items():
    """T1: 驗證無效項處理"""
    verifier = EvidenceVerifier(Path("."))
    res = verifier._verify_code_artifacts([
        {"modification_type": "modified"}, # missing file_path
        "" # empty string
    ])
    assert len(res["invalid_items"]) == 2
    assert res["all_exist"] is False

# --- T14-D: cli_pregate.py logic check ---
# Assuming run_cli_pregate exists and logic is straight forward
# We focus on the fact that if commands are empty, in CLI pregate we might pass or fail based on rules.
# The T7 logic in cli_pregate: missing commands -> False

from nexus.engine.cli_pregate import run_cli_pregate

def test_cli_pregate_empty_commands():
    passed, results = run_cli_pregate(Path("."), [])
    assert passed is False

@patch("subprocess.run")
def test_cli_pregate_rc2_fail(mock_run):
    mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")
    passed, results = run_cli_pregate(Path("."), ["pytest"])
    assert passed is False

# --- T14-E: acceptance_check.py ---
# We can import internal methods to check cold start
import sys
sys.path.append(str(Path(__file__).parent.parent))
from scripts.ops.nexus_acceptance_check import _evaluate_regression_and_side_effects, _evaluate_learning_promotion, _evaluate_ucc_truth_efficiency

def test_acceptance_repair_rate_cold_start():
    # learning promotion uses cold start
    res = _evaluate_learning_promotion([], window=10, pr_min=0.5, nrh_min=0.5, mode="enforce")
    assert res.passed is False
    assert res.detail["status"] == "UNVERIFIED_COLD_START"

def test_acceptance_regression_cold_start():
    res, _ = _evaluate_regression_and_side_effects([{"status": "PASS"}], window=10, regression_min=95.0, retry_abs_max=3.0, retry_spike_factor=2.0)
    assert res.passed is False
    assert res.detail["status"] == "UNVERIFIED_COLD_START"

def test_acceptance_ucc_cold_start():
    res = _evaluate_ucc_truth_efficiency([{"skill_id": "reach.something"}], window=10)
    assert res.passed is False
    assert res.detail["status"] == "UNVERIFIED_COLD_START"



# --- Report Integrity Lock v1 ---
def test_verify_claims_integrity_fail_on_missing_report():
    from scripts.ops.verify_report_claims import verify_claims
    res = verify_claims(Path("."), report_file_rel="non_existent.json")
    integrity_check = next(c for c in res["checks"] if c["name"] == "report_integrity_lock")
    assert integrity_check["passed"] is False
    assert integrity_check["detail"]["error"] == "report_file_not_found"

@patch("scripts.ops.verify_report_claims._run_git")
def test_verify_claims_integrity_fail_on_mismatch(mock_git):
    from scripts.ops.verify_report_claims import verify_claims
    import json
    
    # Mock git show and git diff to return something else
    def side_effect(root, args):
        if "show" in args: return "real_file.py"
        if "diff" in args: return "real_file.py"
        return ""
    mock_git.side_effect = side_effect
    
    report_data = {
        "head_sha": "abc",
        "files_changed_in_this_commit": ["fake_file.py"],
        "base_branch": "main",
        "branch_delta_vs_base": ["fake_file.py"]
    }
    report_file = Path(".nexus/reports/test_mismatch.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report_data))
    
    try:
        res = verify_claims(Path("."), report_file_rel=str(report_file))
        integrity_check = next(c for c in res["checks"] if c["name"] == "report_integrity_lock")
        assert integrity_check["passed"] is False
        assert integrity_check["detail"]["commit_integrity"]["passed"] is False
    finally:
        report_file.unlink()
