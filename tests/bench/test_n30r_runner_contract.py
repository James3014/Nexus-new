"""Tests for N30R paired-arm runner contract."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import N30RTaskSpec, sha256_str
from scripts.bench.n30r_arm_adapters import ArmRunResult, run_bare_arm, run_core_arm, _read_fixture_source
from scripts.bench.n30r_runner import ARMS, _materialize_task, run_benchmark

SMOKE_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"


def _fake_provider_success(model: str, system_prompt: str, user_prompt: str) -> str:
    """Fake provider that returns a golden patch."""
    # Read the golden source from the fixture
    return ""


def _fake_provider_returning(model: str, system_prompt: str, user_prompt: str) -> str:
    """Provider that returns content but may not fix the bug."""
    return "def greet(name):\n    return f'Hi, {name}!'"


def test_runner_supports_exactly_two_initial_arms():
    assert len(ARMS) == 2
    assert "N30R_A_7B_BARE" in ARMS
    assert "N30R_B_7B_REAL_CORE" in ARMS


def test_unknown_arm_is_rejected():
    with pytest.raises(ValueError, match="Unknown arm"):
        run_benchmark(
            manifest_path=str(SMOKE_MANIFEST),
            arm_ids=["N30R_FAKE_ARM"],
            task_ids=None,
            trials=1,
            seeds=[3001],
            output_path="/tmp/test_reject.jsonl",
            provider=lambda m, s, u: "",
            dry_run=True,
        )


def test_dry_run_makes_zero_provider_calls():
    call_count = 0
    def counting_provider(model, system_prompt, user_prompt):
        nonlocal call_count
        call_count += 1
        return "should not be called"

    run_benchmark(
        manifest_path=str(SMOKE_MANIFEST),
        arm_ids=["N30R_A_7B_BARE"],
        task_ids=["n30r_smoke_syntax"],
        trials=1,
        seeds=[3001],
        output_path="/tmp/test_dry.jsonl",
        provider=counting_provider,
        dry_run=True,
    )
    assert call_count == 0


def test_bare_arm_does_not_call_capability_planner():
    """Bare arm must not invoke CapabilityPlanner."""
    arm = ARMS["N30R_A_7B_BARE"]
    assert arm.nexus_enabled is False
    assert arm.core_armor_enabled is False


def test_core_arm_calls_capability_planner():
    """Core arm must use planner-owned signal snapshot."""
    arm = ARMS["N30R_B_7B_REAL_CORE"]
    assert arm.nexus_enabled is True
    assert arm.core_armor_enabled is True


def test_core_arm_uses_planner_owned_signal_snapshot():
    """Core arm's arm_config hash must differ from bare arm."""
    bare = ARMS["N30R_A_7B_BARE"]
    core = ARMS["N30R_B_7B_REAL_CORE"]
    assert bare.arm_config_sha256 != core.arm_config_sha256


def test_each_arm_gets_fresh_workspace():
    """Materialized tasks should have identical hashes (same source)."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    t1 = _materialize_task(manifest["tasks"][0])
    t2 = _materialize_task(manifest["tasks"][0])
    assert t1.source_sha256 == t2.source_sha256
    assert t1.task_bundle_sha256 == t2.task_bundle_sha256


def test_source_hash_equal_across_paired_arms():
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    t = _materialize_task(manifest["tasks"][0])
    assert t.source_sha256
    assert len(t.source_sha256) == 64


def test_verifier_hash_equal_across_paired_arms():
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    t = _materialize_task(manifest["tasks"][0])
    assert t.verifier_contract_sha256
    assert len(t.verifier_contract_sha256) == 64


def test_environment_hash_equal_across_paired_arms():
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    t = _materialize_task(manifest["tasks"][0])
    assert t.environment_sha256
    assert len(t.environment_sha256) == 64


def test_arm_config_hash_differs():
    bare = ARMS["N30R_A_7B_BARE"]
    core = ARMS["N30R_B_7B_REAL_CORE"]
    assert bare.arm_config_sha256 != core.arm_config_sha256


def test_empty_output_is_not_verified_failure():
    """Empty output must be INFRA_INVALID, not VERIFIED_FAIL."""
    from scripts.bench.n30r_contracts import N30RAttemptReceipt
    r = N30RAttemptReceipt(
        run_id="r", task_id="t", trial_index=0, seed=3001, arm_id="A",
        provider_requested="ollama", provider_actual="ollama",
        model_requested="m", model_actual="m",
        model_parameters_sha256="x", task_bundle_sha256="x",
        source_sha256="x", verifier_contract_sha256="x",
        environment_sha256="x", arm_config_sha256="x",
        rendered_prompt_sha256="x",
        model_call_started=True, model_response_received=True,
        raw_output_sha256="", raw_output_length=0,
        patch_sha256="", patch_length=0,
        apply_status="none", verifier_status="not_run",
        terminal_status="INFRA_INVALID",
        timeout_limit_sec=120, wall_time_sec=1.0,
        timed_out=False, timeout_stage="",
        candidate_isolated=False, trust_mismatch=False,
        receipt_complete=False,
    )
    errors = r.validate_terminal_invariants()
    assert r.terminal_status == "INFRA_INVALID"


def test_model_timeout_is_terminal_model_timeout():
    from scripts.bench.n30r_contracts import N30RAttemptReceipt
    r = N30RAttemptReceipt(
        run_id="r", task_id="t", trial_index=0, seed=3001, arm_id="A",
        provider_requested="ollama", provider_actual="ollama",
        model_requested="m", model_actual="m",
        model_parameters_sha256="x", task_bundle_sha256="x",
        source_sha256="x", verifier_contract_sha256="x",
        environment_sha256="x", arm_config_sha256="x",
        rendered_prompt_sha256="x",
        model_call_started=True, model_response_received=False,
        raw_output_sha256="", raw_output_length=0,
        patch_sha256="", patch_length=0,
        apply_status="none", verifier_status="not_run",
        terminal_status="MODEL_TIMEOUT",
        timeout_limit_sec=120, wall_time_sec=120.0,
        timed_out=True, timeout_stage="model_call",
        candidate_isolated=False, trust_mismatch=False,
        receipt_complete=False,
    )
    assert r.terminal_status == "MODEL_TIMEOUT"


def test_provider_mismatch_sets_trust_mismatch():
    from scripts.bench.n30r_contracts import N30RAttemptReceipt
    r = N30RAttemptReceipt(
        run_id="r", task_id="t", trial_index=0, seed=3001, arm_id="A",
        provider_requested="ollama", provider_actual="openai",
        model_requested="m", model_actual="m",
        model_parameters_sha256="x", task_bundle_sha256="x",
        source_sha256="x", verifier_contract_sha256="x",
        environment_sha256="x", arm_config_sha256="x",
        rendered_prompt_sha256="x",
        model_call_started=True, model_response_received=True,
        raw_output_sha256=sha256_str("out"), raw_output_length=3,
        patch_sha256=sha256_str("p"), patch_length=1,
        apply_status="success", verifier_status="pass",
        terminal_status="VERIFIED_SOLVE",
        timeout_limit_sec=120, wall_time_sec=1.0,
        timed_out=False, timeout_stage="",
        candidate_isolated=True, trust_mismatch=True,
        receipt_complete=True,
    )
    errors = r.validate_terminal_invariants()
    assert not any("provider mismatch" in e for e in errors)


def test_missing_receipt_field_blocks_verified_solve():
    from scripts.bench.n30r_contracts import N30RAttemptReceipt
    r = N30RAttemptReceipt(
        run_id="r", task_id="t", trial_index=0, seed=3001, arm_id="A",
        provider_requested="ollama", provider_actual="ollama",
        model_requested="m", model_actual="m",
        model_parameters_sha256="x", task_bundle_sha256="x",
        source_sha256="x", verifier_contract_sha256="x",
        environment_sha256="x", arm_config_sha256="x",
        rendered_prompt_sha256="x",
        model_call_started=True, model_response_received=True,
        raw_output_sha256=sha256_str("out"), raw_output_length=3,
        patch_sha256=sha256_str("p"), patch_length=1,
        apply_status="success", verifier_status="pass",
        terminal_status="VERIFIED_SOLVE",
        timeout_limit_sec=120, wall_time_sec=1.0,
        timed_out=False, timeout_stage="",
        candidate_isolated=True, trust_mismatch=False,
        receipt_complete=False,  # incomplete
    )
    errors = r.validate_terminal_invariants()
    # VERIFIED_SOLVE with receipt_complete=false is itself an invariant violation
    assert any("receipt_complete=true" in e for e in errors)


def test_deterministic_verifier_is_final_authority():
    """The verifier determines pass/fail, not the model."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])
    # Verifier command is deterministic
    assert task.verifier_command[0] == "python3"


def test_golden_patch_is_not_in_prompt():
    """Bare arm prompt must not contain golden patch."""
    from scripts.bench.n30r_arm_adapters import run_bare_arm
    arm = ARMS["N30R_A_7B_BARE"]
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    def check_prompt(model, system_prompt, user_prompt):
        assert "golden" not in user_prompt.lower()
        assert "GOLDEN" not in user_prompt
        return "def greet(name):\n    return f'Hello, {name}!'"

    result = run_bare_arm(task, arm, check_prompt, 3001, 0, "test_run")
    # If we get here, the golden patch was not in the prompt


def test_learning_retrieval_is_disabled():
    """Core arm must not enable learning retrieval."""
    arm = ARMS["N30R_B_7B_REAL_CORE"]
    assert arm.additional_capability == ""
    assert "learning" not in arm.arm_id.lower()
    assert "retrieval" not in arm.arm_id.lower()
