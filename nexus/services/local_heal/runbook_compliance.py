"""V4-C.2 Runbook Compliance Checker / Receipt Schema Guard

Validates repair artifact directories against:
- V4-C.1 runbook gates
- Roadmap v3 invariants
- V4-A/V4-B evidence rules
- V4-D.2 model policy
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIRED_RECEIPT_FIELDS = [
    'task_id', 'repo', 'source_git_sha', 'execution_mode',
    'provider', 'model', 'model_calls', 'cloud_api_used',
    'deterministic_fallback_used', 'match_authority', 'success_attribution',
    'export_classification', 'task_scoped', 'verifier_status',
    'blocker_type', 'public_claim_allowed', 'training_eligible',
    'final_lane', 'final_status',
]

EXPECTED_ARTIFACTS = [
    'real_replay_result.json',
]

OPTIONAL_ARTIFACTS = [
    'environment_preflight.json',
    'baseline_reproduction.json',
    'model_execution.json',
    'patch_authority_receipt.json',
    'final_verification.json',
    'receipt_audit.md',
    'final_report.md',
]


@dataclass
class ComplianceResult:
    """Result of runbook compliance check."""
    compliance_status: str = "UNKNOWN"
    passed_gates: List[str] = field(default_factory=list)
    failed_gates: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    governance_violations: List[str] = field(default_factory=list)
    attribution_violations: List[str] = field(default_factory=list)
    verifier_violations: List[str] = field(default_factory=list)
    lane_violations: List[str] = field(default_factory=list)
    model_policy_violations: List[str] = field(default_factory=list)
    recommended_final_status: str = "UNKNOWN"
    caveats: List[str] = field(default_factory=list)

    @property
    def is_pass(self) -> bool:
        return self.compliance_status in ("COMPLIANCE_PASS", "COMPLIANCE_PASS_WITH_CAVEATS")


def check_artifact_presence(artifact_dir: Path) -> tuple[List[str], List[str]]:
    """Check expected artifacts exist. Returns (missing_required, missing_optional)."""
    missing_required = []
    for artifact in EXPECTED_ARTIFACTS:
        if not (artifact_dir / artifact).exists():
            missing_required.append(artifact)
    missing_optional = []
    for artifact in OPTIONAL_ARTIFACTS:
        if not (artifact_dir / artifact).exists():
            missing_optional.append(artifact)
    return missing_required, missing_optional


def check_receipt_schema(receipt: Dict[str, Any]) -> List[str]:
    """Validate minimum receipt fields."""
    missing = []
    for field_name in REQUIRED_RECEIPT_FIELDS:
        if field_name not in receipt:
            missing.append(field_name)
    return missing


def check_attribution_rules(receipt: Dict[str, Any]) -> List[str]:
    """Check attribution rules — hard fail on violations."""
    violations = []

    success = receipt.get('final_status', '').startswith('INTERNAL_REPAIR_PASS') or \
              receipt.get('final_status', '').startswith('V4B') or \
              receipt.get('final_status', '').startswith('V4A') or \
              receipt.get('match_authority') is not None

    # Rule 1: success with match_authority=None
    # Env-blocked tasks legitimately have match_authority=None — not a violation
    is_env_blocked = receipt.get('final_lane') in ('env_blocked_but_review_verified', 'human_review_required', 'internal_infra_failure')
    if success and receipt.get('match_authority') is None and not is_env_blocked:
        violations.append("success_with_null_authority")

    # Rule 2: FUZZY_CANDIDATE_ONLY success
    if receipt.get('match_authority') == 'fuzzy_candidate_only' and success:
        violations.append("fuzzy_candidate_only_success")

    # Rule 3: canonical recovery collapsed into direct model_patch_success
    if receipt.get('match_authority') == 'canonical_recovery' and \
       receipt.get('export_classification') == 'model_patch_success_candidate':
        violations.append("canonical_recovery_collapsed_into_model_success")

    # Rule 4: cross-file recovery collapsed into direct model_patch_success
    if receipt.get('match_authority') == 'cross_file_correction' and \
       receipt.get('export_classification') == 'model_patch_success_candidate':
        violations.append("cross_file_recovery_collapsed_into_model_success")

    # Rule 5: deterministic fallback counted as model success
    if receipt.get('deterministic_fallback_used') and \
       receipt.get('export_classification') == 'model_patch_success_candidate':
        violations.append("deterministic_fallback_counted_as_model_success")

    # Rule 6: model_calls=0 with model success claimed
    if receipt.get('model_calls', 0) == 0 and \
       receipt.get('export_classification') == 'model_patch_success_candidate':
        violations.append("model_calls_zero_with_model_success_claimed")

    return violations


def check_verifier_rules(receipt: Dict[str, Any]) -> List[str]:
    """Check verifier rules."""
    violations = []

    # Rule: task_scoped=false on verifier-backed pass
    if receipt.get('verifier_status') == 'passed' and receipt.get('task_scoped') is False:
        violations.append("task_scoped_false_on_verifier_pass")

    return violations


def check_governance_rules(receipt: Dict[str, Any]) -> List[str]:
    """Check governance rules — hard fail."""
    violations = []

    if receipt.get('public_claim_allowed') is True:
        violations.append("public_claim_allowed_true")

    if receipt.get('training_eligible') is True:
        violations.append("training_eligible_true")

    if receipt.get('runtime_integration_enabled') is True:
        violations.append("runtime_integration_enabled_true")

    if receipt.get('routing_integration_enabled') is True:
        violations.append("routing_integration_enabled_true")

    if receipt.get('cloud_api_used') is True:
        violations.append("cloud_api_used_true")

    return violations


def check_model_policy(receipt: Dict[str, Any]) -> List[str]:
    """Check model policy rules."""
    violations = []
    model = receipt.get('model', '')

    # Rule: 3B must not be treated as validated
    if '3b' in model.lower() and 'validated' in str(receipt.get('final_status', '')).lower():
        violations.append("3b_treated_as_validated")

    return violations


def check_lane_classification(receipt: Dict[str, Any]) -> List[str]:
    """Check lane classification consistency."""
    violations = []

    lane = receipt.get('final_lane', '')
    authority = receipt.get('match_authority')
    classification = receipt.get('export_classification', '')

    # Rule: direct patch lane should have verbatim or cross_file authority
    if lane == 'verifier_passed_by_execution' and \
       authority not in ('verbatim', 'cross_file_correction', None):
        violations.append("direct_patch_lane_wrong_authority")

    # Rule: canonical recovery lane should have canonical_recovery authority
    if lane == 'canonical_recovery_success' and \
       authority != 'canonical_recovery':
        violations.append("canonical_lane_wrong_authority")

    # Rule: env-blocked lane should not have model success classification
    if lane in ('env_blocked_but_review_verified', 'human_review_required') and \
       classification == 'model_patch_success_candidate':
        violations.append("env_blocked_classified_as_model_success")

    return violations


def check_env_sensitive_rules(receipt: Dict[str, Any]) -> List[str]:
    """Check env-sensitive rules."""
    violations = []
    lane = receipt.get('final_lane', '')

    # Rule: env blocker should not be counted as model success
    if lane in ('env_blocked_but_review_verified', 'human_review_required') and \
       receipt.get('model_success_claimed') is True:
        violations.append("env_blocker_counted_as_model_success")

    # Rule: blocker_type should be present for env-blocked lanes
    if lane in ('env_blocked_but_review_verified', 'human_review_required',
                'internal_infra_failure') and \
       receipt.get('blocker_type') is None:
        violations.append("blocker_type_missing_for_env_lane")

    return violations


def determine_status(result: ComplianceResult) -> str:
    """Map violations to compliance status."""
    all_violations = (
        result.governance_violations + result.attribution_violations +
        result.verifier_violations + result.lane_violations +
        result.model_policy_violations
    )

    if result.missing_fields:
        return "BLOCKED_BY_SCHEMA_DRIFT"
    if result.governance_violations:
        return "BLOCKED_BY_GOVERNANCE_REGRESSION"
    if result.attribution_violations:
        return "BLOCKED_BY_ATTRIBUTION_REGRESSION"
    if result.verifier_violations:
        return "BLOCKED_BY_VERIFIER_REGRESSION"
    if result.model_policy_violations:
        return "BLOCKED_BY_MODEL_POLICY_REGRESSION"
    if result.lane_violations:
        return "BLOCKED_BY_LANE_CLASSIFICATION_VIOLATION"
    if all_violations:
        return "BLOCKED_BY_VIOLATION"
    if result.failed_gates:
        return "BLOCKED_BY_MISSING_ARTIFACT"
    return "COMPLIANCE_PASS"


def check_compliance(
    artifact_dir: Path,
    expected_task_id: Optional[str] = None,
    expected_lane: Optional[str] = None,
    strict: bool = False,
) -> ComplianceResult:
    """Run full compliance check on artifact directory."""
    result = ComplianceResult()

    # 1. Artifact presence
    missing_required, missing_optional = check_artifact_presence(artifact_dir)
    if missing_required:
        result.missing_fields.extend([f"artifact:{a}" for a in missing_required])
        result.failed_gates.append("artifact_presence")
    else:
        result.passed_gates.append("artifact_presence")
    if missing_optional:
        result.caveats = getattr(result, 'caveats', []) or []
        result.caveats.extend([f"optional:{a}" for a in missing_optional])

    # 2. Load receipt
    receipt_path = artifact_dir / 'real_replay_result.json'
    receipt = {}
    if receipt_path.exists():
        with open(receipt_path) as f:
            receipt = json.load(f)
    else:
        result.missing_fields.append("real_replay_result.json")
        result.failed_gates.append("receipt_load")

    # 3. Receipt schema
    if receipt:
        missing_fields = check_receipt_schema(receipt)
        if missing_fields:
            result.missing_fields.extend(missing_fields)
            result.failed_gates.append("receipt_schema")
        else:
            result.passed_gates.append("receipt_schema")

    # 4. Expected task_id
    if expected_task_id and receipt.get('task_id') != expected_task_id:
        result.lane_violations.append(f"task_id_mismatch: expected {expected_task_id}, got {receipt.get('task_id')}")

    # 5. Expected lane
    if expected_lane and receipt.get('final_lane') != expected_lane:
        result.lane_violations.append(f"lane_mismatch: expected {expected_lane}, got {receipt.get('final_lane')}")

    # 6. Attribution rules
    if receipt:
        attr_violations = check_attribution_rules(receipt)
        result.attribution_violations.extend(attr_violations)
        if attr_violations:
            result.failed_gates.append("attribution_rules")
        else:
            result.passed_gates.append("attribution_rules")

    # 7. Verifier rules
    if receipt:
        verifier_violations = check_verifier_rules(receipt)
        result.verifier_violations.extend(verifier_violations)
        if verifier_violations:
            result.failed_gates.append("verifier_rules")
        else:
            result.passed_gates.append("verifier_rules")

    # 8. Env-sensitive rules
    if receipt:
        env_violations = check_env_sensitive_rules(receipt)
        result.lane_violations.extend(env_violations)
        if env_violations:
            result.failed_gates.append("env_sensitive_rules")
        else:
            result.passed_gates.append("env_sensitive_rules")

    # 9. Governance rules
    if receipt:
        gov_violations = check_governance_rules(receipt)
        result.governance_violations.extend(gov_violations)
        if gov_violations:
            result.failed_gates.append("governance_rules")
        else:
            result.passed_gates.append("governance_rules")

    # 10. Model policy
    if receipt:
        model_violations = check_model_policy(receipt)
        result.model_policy_violations.extend(model_violations)
        if model_violations:
            result.failed_gates.append("model_policy")
        else:
            result.passed_gates.append("model_policy")

    # 11. Lane classification
    if receipt:
        lane_violations = check_lane_classification(receipt)
        result.lane_violations.extend(lane_violations)
        if lane_violations:
            result.failed_gates.append("lane_classification")
        else:
            result.passed_gates.append("lane_classification")

    # Determine status
    result.compliance_status = determine_status(result)
    result.recommended_final_status = receipt.get('final_status', 'UNKNOWN')

    return result
