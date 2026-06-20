"""Tests for runbook_compliance module (V4-C.2)."""
import json
import pytest
from pathlib import Path

from nexus.services.local_heal.runbook_compliance import (
    check_compliance,
    check_artifact_presence,
    check_receipt_schema,
    check_attribution_rules,
    check_governance_rules,
    check_verifier_rules,
    check_model_policy,
    check_lane_classification,
    check_env_sensitive_rules,
)


def _make_receipt(**overrides):
    """Helper to create a valid receipt with overrides."""
    base = {
        'task_id': 'TEST001', 'repo': 'test', 'source_git_sha': 'abc123',
        'execution_mode': 'real', 'provider': 'ollama', 'model': 'qwen2.5-coder:7b',
        'model_calls': 1, 'cloud_api_used': False, 'deterministic_fallback_used': False,
        'match_authority': 'verbatim', 'success_attribution': 'model_patch_success',
        'export_classification': 'model_patch_success_candidate', 'task_scoped': True,
        'verifier_status': 'passed', 'blocker_type': None,
        'public_claim_allowed': False, 'training_eligible': False,
        'final_lane': 'verifier_passed_by_execution', 'final_status': 'INTERNAL_REPAIR_PASS_INTERNAL_ONLY',
    }
    base.update(overrides)
    return base


# ─── Valid receipt tests ─────────────────────────────────────────────────────

def test_valid_direct_patch_receipt():
    """Valid direct patch receipt passes all checks."""
    violations = check_attribution_rules(_make_receipt())
    gov = check_governance_rules(_make_receipt())
    assert len(violations) == 0
    assert len(gov) == 0


def test_valid_canonical_recovery_receipt():
    """Valid canonical recovery receipt passes all checks."""
    receipt = _make_receipt(
        match_authority='canonical_recovery',
        success_attribution='canonical_recovery_success',
        export_classification='canonical_recovery_success',
        final_lane='canonical_recovery_success',
    )
    violations = check_attribution_rules(receipt)
    assert len(violations) == 0


def test_valid_env_blocked_receipt():
    """Valid env-blocked receipt passes all checks."""
    receipt = _make_receipt(
        match_authority=None, success_attribution=None,
        export_classification='human_review_required',
        final_lane='env_blocked_but_review_verified',
        model_calls=0, blocker_type='DEPENDENCY_SETUP_MISSING',
    )
    violations = check_attribution_rules(receipt)
    gov = check_governance_rules(receipt)
    assert len(violations) == 0
    assert len(gov) == 0


# ─── Attribution violation tests ─────────────────────────────────────────────

def test_success_with_null_authority():
    """Success with match_authority=None should fail."""
    receipt = _make_receipt(match_authority=None, final_status='INTERNAL_REPAIR_PASS_INTERNAL_ONLY')
    violations = check_attribution_rules(receipt)
    assert 'success_with_null_authority' in violations


def test_fuzzy_candidate_only_success():
    """FUZZY_CANDIDATE_ONLY success should fail."""
    receipt = _make_receipt(match_authority='fuzzy_candidate_only')
    violations = check_attribution_rules(receipt)
    assert 'fuzzy_candidate_only_success' in violations


def test_canonical_recovery_collapsed():
    """Canonical recovery collapsed into model success should fail."""
    receipt = _make_receipt(
        match_authority='canonical_recovery',
        export_classification='model_patch_success_candidate',
    )
    violations = check_attribution_rules(receipt)
    assert 'canonical_recovery_collapsed_into_model_success' in violations


def test_model_calls_zero_with_success():
    """model_calls=0 with model success should fail."""
    receipt = _make_receipt(model_calls=0, export_classification='model_patch_success_candidate')
    violations = check_attribution_rules(receipt)
    assert 'model_calls_zero_with_model_success_claimed' in violations


# ─── Governance violation tests ──────────────────────────────────────────────

def test_public_claim_allowed():
    """public_claim_allowed=true should fail."""
    violations = check_governance_rules(_make_receipt(public_claim_allowed=True))
    assert 'public_claim_allowed_true' in violations


def test_training_eligible():
    """training_eligible=true should fail."""
    violations = check_governance_rules(_make_receipt(training_eligible=True))
    assert 'training_eligible_true' in violations


def test_cloud_api_used():
    """cloud_api_used=true should fail."""
    violations = check_governance_rules(_make_receipt(cloud_api_used=True))
    assert 'cloud_api_used_true' in violations


# ─── Verifier violation tests ────────────────────────────────────────────────

def test_task_scoped_false_on_pass():
    """task_scoped=false with verifier pass should fail."""
    violations = check_verifier_rules(_make_receipt(task_scoped=False, verifier_status='passed'))
    assert 'task_scoped_false_on_verifier_pass' in violations


# ─── Model policy tests ──────────────────────────────────────────────────────

def test_3b_treated_as_validated():
    """3B model treated as validated should fail."""
    violations = check_model_policy(_make_receipt(model='qwen2.5:3b', final_status='VALIDATED_PASS'))
    assert '3b_treated_as_validated' in violations


# ─── Lane classification tests ───────────────────────────────────────────────

def test_env_blocked_classified_as_model_success():
    """Env-blocked lane classified as model success should fail."""
    violations = check_lane_classification(_make_receipt(
        final_lane='env_blocked_but_review_verified',
        export_classification='model_patch_success_candidate',
    ))
    assert 'env_blocked_classified_as_model_success' in violations


# ─── Schema drift test ───────────────────────────────────────────────────────

def test_missing_required_field():
    """Missing required field should be detected."""
    receipt = _make_receipt()
    del receipt['match_authority']
    missing = check_receipt_schema(receipt)
    assert 'match_authority' in missing


# ─── Artifact presence test ──────────────────────────────────────────────────

def test_missing_artifact():
    """Missing artifact should be detected."""
    with __import__('tempfile').TemporaryDirectory() as tmp:
        missing = check_artifact_presence(Path(tmp))
        assert 'real_replay_result.json' in missing
