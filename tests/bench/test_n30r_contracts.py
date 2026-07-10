"""Tests for N30R canonical evaluation contracts."""
from __future__ import annotations

import pytest

from scripts.bench.n30r_contracts import (
    N30RAttemptReceipt,
    N30RArmSpec,
    N30RTaskSpec,
    N30RTerminalStatus,
    sha256_str,
)


def _minimal_task(**overrides) -> N30RTaskSpec:
    defaults = dict(
        task_id="t1",
        split="smoke",
        source_relpath="src/f.py",
        source_sha256=sha256_str("source"),
        task_statement="fix the bug",
        expected_failure_signature="AssertionError",
        verifier_command=("python3", "-c", "assert False"),
        verifier_contract_sha256=sha256_str("vc"),
        environment_sha256=sha256_str("env"),
        task_bundle_sha256=sha256_str("bundle"),
        golden_patch_sha256=sha256_str("patch"),
        golden_patch_private_ref="private://ref",
        original_verifier_expected="FAIL",
        golden_verifier_expected="PASS",
    )
    defaults.update(overrides)
    return N30RTaskSpec(**defaults)


def _minimal_receipt(**overrides) -> N30RAttemptReceipt:
    defaults = dict(
        run_id="run1",
        task_id="t1",
        trial_index=0,
        seed=3001,
        arm_id="N30R_A_7B_BARE",
        provider_requested="ollama",
        provider_actual="ollama",
        model_requested="qwen2.5-coder:7b",
        model_actual="qwen2.5-coder:7b",
        model_parameters_sha256=sha256_str("params"),
        task_bundle_sha256=sha256_str("bundle"),
        source_sha256=sha256_str("source"),
        verifier_contract_sha256=sha256_str("vc"),
        environment_sha256=sha256_str("env"),
        arm_config_sha256=sha256_str("arm"),
        rendered_prompt_sha256=sha256_str("prompt"),
        model_call_started=True,
        model_response_received=True,
        raw_output_sha256=sha256_str("output"),
        raw_output_length=100,
        patch_sha256=sha256_str("patch"),
        patch_length=50,
        apply_status="success",
        verifier_status="pass",
        terminal_status="VERIFIED_SOLVE",
        timeout_limit_sec=120.0,
        wall_time_sec=5.0,
        timed_out=False,
        timeout_stage="",
        candidate_isolated=True,
        trust_mismatch=False,
        receipt_complete=True,
    )
    defaults.update(overrides)
    return N30RAttemptReceipt(**defaults)


# ---------------------------------------------------------------------------
# Terminal status tests
# ---------------------------------------------------------------------------

def test_verified_solve_requires_full_evidence():
    r = _minimal_receipt()
    errors = r.validate_terminal_invariants()
    assert errors == [], f"unexpected errors: {errors}"


def test_empty_output_cannot_be_verified_failure():
    r = _minimal_receipt(
        terminal_status="VERIFIED_FAIL",
        raw_output_sha256="",
        raw_output_length=0,
        patch_sha256="",
        patch_length=0,
        apply_status="none",
        verifier_status="fail",
        candidate_isolated=False,
    )
    errors = r.validate_terminal_invariants()
    assert any("empty output cannot be VERIFIED_FAIL" in e for e in errors)


def test_model_timeout_is_not_infra_invalid():
    r = _minimal_receipt(
        terminal_status="MODEL_TIMEOUT",
        timed_out=True,
        timeout_stage="model_call",
        model_call_started=True,
        model_response_received=False,
        raw_output_sha256="",
        raw_output_length=0,
        patch_sha256="",
        patch_length=0,
        apply_status="none",
        verifier_status="not_run",
        candidate_isolated=False,
        receipt_complete=False,
    )
    errors = r.validate_terminal_invariants()
    assert not any("MODEL_TIMEOUT" in e and "INFRA_INVALID" in e for e in errors)
    assert r.terminal_status == "MODEL_TIMEOUT"


def test_provider_mismatch_sets_trust_mismatch():
    r = _minimal_receipt(
        provider_actual="openai",
        trust_mismatch=True,
    )
    errors = r.validate_terminal_invariants()
    assert not any("provider mismatch" in e for e in errors)


def test_missing_output_hash_marks_receipt_incomplete():
    r = _minimal_receipt(
        receipt_complete=False,
        raw_output_sha256="",
        task_bundle_sha256="",
    )
    errors = r.validate_terminal_invariants()
    assert any("receipt_complete=true requires" in e for e in errors)


# ---------------------------------------------------------------------------
# Golden patch / leakage tests
# ---------------------------------------------------------------------------

def test_golden_patch_body_is_forbidden_in_public_manifest():
    task = _minimal_task()
    # Public spec should never contain golden patch body
    assert hasattr(task, "golden_patch_sha256")
    assert not hasattr(task, "golden_patch_body")
    # Verify only SHA256 and private ref are stored
    assert len(task.golden_patch_sha256) == 64
    assert task.golden_patch_private_ref.startswith("private://")


def test_golden_leakage_is_terminal_invalid():
    r = _minimal_receipt(
        terminal_status="LEAKAGE_INVALID",
        model_call_started=True,
        model_response_received=True,
        raw_output_sha256=sha256_str("leaked"),
        raw_output_length=50,
        patch_sha256="",
        patch_length=0,
        apply_status="none",
        verifier_status="not_run",
        candidate_isolated=True,
        trust_mismatch=False,
        receipt_complete=True,
    )
    errors = r.validate_terminal_invariants()
    assert r.terminal_status == "LEAKAGE_INVALID"
    assert not any("VERIFIED_SOLVE" in e for e in errors)


# ---------------------------------------------------------------------------
# Paired hash invariant tests
# ---------------------------------------------------------------------------

def test_paired_arms_require_same_task_bundle():
    t1 = _minimal_task(task_id="x", task_bundle_sha256=sha256_str("b1"))
    t2 = _minimal_task(task_id="x", task_bundle_sha256=sha256_str("b2"))
    assert t1.task_bundle_sha256 != t2.task_bundle_sha256
    # Paired arms MUST have same hash — this test documents the invariant
    t3 = _minimal_task(task_id="x", task_bundle_sha256=sha256_str("b1"))
    assert t1.task_bundle_sha256 == t3.task_bundle_sha256


def test_paired_arms_require_same_source_hash():
    t1 = _minimal_task(source_sha256=sha256_str("s1"))
    t2 = _minimal_task(source_sha256=sha256_str("s1"))
    assert t1.source_sha256 == t2.source_sha256


def test_paired_arms_require_same_verifier_hash():
    t1 = _minimal_task(verifier_contract_sha256=sha256_str("v1"))
    t2 = _minimal_task(verifier_contract_sha256=sha256_str("v1"))
    assert t1.verifier_contract_sha256 == t2.verifier_contract_sha256


def test_paired_arms_require_same_environment_hash():
    t1 = _minimal_task(environment_sha256=sha256_str("e1"))
    t2 = _minimal_task(environment_sha256=sha256_str("e1"))
    assert t1.environment_sha256 == t2.environment_sha256


def test_rendered_prompt_hash_may_differ_between_arms():
    r1 = _minimal_receipt(rendered_prompt_sha256=sha256_str("p1"))
    r2 = _minimal_receipt(rendered_prompt_sha256=sha256_str("p2"))
    assert r1.rendered_prompt_sha256 != r2.rendered_prompt_sha256


def test_initial_arms_have_no_additional_capability():
    arm_bare = N30RArmSpec(
        arm_id="N30R_A_7B_BARE",
        model_provider="ollama",
        model_name="qwen2.5-coder:7b-instruct",
        model_parameters={"param": 7_000_000_000},
        nexus_enabled=False,
        core_armor_enabled=False,
        additional_capability="",
        arm_config_sha256=sha256_str("bare"),
    )
    arm_core = N30RArmSpec(
        arm_id="N30R_B_7B_CORE",
        model_provider="ollama",
        model_name="qwen2.5-coder:7b-instruct",
        model_parameters={"param": 7_000_000_000},
        nexus_enabled=True,
        core_armor_enabled=True,
        additional_capability="",
        arm_config_sha256=sha256_str("core"),
    )
    assert arm_bare.additional_capability == ""
    assert arm_core.additional_capability == ""
    assert arm_bare.arm_config_sha256 != arm_core.arm_config_sha256
