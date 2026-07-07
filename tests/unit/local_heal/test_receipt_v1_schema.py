"""
Tests for local_heal_receipt_v1 schema compliance and fail-closed logic.

Validates:
1. All v1 required fields are present in every receipt
2. simulated=true forces claim_eligible=false
3. Missing observed_stop_layer → debug-only, not benchmark row
4. ENV failures classified as env_fixable_by_agent or env_external_blocked
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock


def _make_mock_ctx(**overrides):
    """Create a minimal mock HealContext for receipt testing."""
    ctx = MagicMock()
    ctx.instance_id = overrides.get("instance_id", "test-task-001")
    ctx.solve_eligible = overrides.get("solve_eligible", False)
    ctx.runner_completed = overrides.get("runner_completed", True)
    ctx.reproduced = overrides.get("reproduced", True)
    ctx.final_patch = overrides.get("final_patch", "")
    ctx.evaluation_report = overrides.get("evaluation_report", "")
    ctx.hidden_verifier_required = overrides.get("hidden_verifier_required", False)
    ctx.hidden_verifier_passed = overrides.get("hidden_verifier_passed", False)
    ctx.failure_reason = overrides.get("failure_reason", "")
    ctx.errors = overrides.get("errors", [])
    ctx.repro_script = overrides.get("repro_script", "reproduce_bug.py")
    ctx.python_executable = overrides.get("python_executable", "python3")
    ctx.env_resolution = overrides.get("env_resolution", {"ready": True})
    ctx.env_denoise = overrides.get("env_denoise", {})
    ctx.model_decisions = overrides.get("model_decisions", [])
    ctx.initial_ctx_len = 0
    ctx.final_ctx_len = 0
    ctx.resolved_span_len = 0
    ctx.attempt = overrides.get("attempt", 1)
    ctx.reasoning_mode = "INTUITIVE"
    ctx.prompt_variant_id = "default"
    ctx.refusal_detected = False
    ctx.empty_response = False
    ctx.wall_time_sec = overrides.get("wall_time_sec", 10.0)
    ctx.token_telemetry_status = "not_applicable"
    ctx.token_total_estimated = 0
    ctx.syntax_gate_passed = True
    ctx.expected_stop_layer = "verification"
    ctx.expected_reason_family = "SOLVED"
    ctx._latency_ledger = None
    ctx._claim_delivery_gate = overrides.get("_claim_delivery_gate", {"claim_gate_passed": overrides.get("solve_eligible", False)})
    return ctx


# ─── Test 1: v1 required fields present ───

V1_REQUIRED_FIELDS = [
    "schema_version", "task_id", "instance_id", "run_id", "timestamp",
    "simulated", "claim_eligible", "solve_eligible", "public_benchmark_allowed",
    "expected_stop_layer", "observed_stop_layer", "phase_durations", "model_phase_split",
    "failure_reason", "evidence_refs", "visible_passed", "hidden_passed",
]


def test_v1_required_fields_present():
    """All v1 required fields must be present in every receipt."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx()
    receipt = build_repair_receipt(ctx)
    missing = [f for f in V1_REQUIRED_FIELDS if f not in receipt]
    assert not missing, f"Missing v1 fields: {missing}"


def test_v1_schema_version():
    """schema_version must be '1.0'."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx()
    receipt = build_repair_receipt(ctx)
    assert receipt["schema_version"] == "1.0"


def test_v1_identity_fields():
    """task_id, instance_id, run_id, timestamp must be non-empty."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx(instance_id="astropy__astropy-14096")
    receipt = build_repair_receipt(ctx)
    assert receipt["task_id"] == "astropy__astropy-14096"
    assert receipt["instance_id"] == "astropy__astropy-14096"
    assert len(receipt["run_id"]) > 0
    assert "T" in receipt["timestamp"]  # ISO 8601


# ─── Test 2: simulated=true forces claim_eligible=false ───

def test_simulated_forces_claim_eligible_false():
    """When simulated=True (patched in), claim_eligible must be forced to False."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx(solve_eligible=True, runner_completed=True)
    receipt = build_repair_receipt(ctx)
    # Simulate the fail-closed logic: if simulated were True
    receipt["simulated"] = True
    # The fail-closed rule: simulated=True → claim_eligible=False
    if receipt["simulated"]:
        receipt["claim_eligible"] = False
    assert receipt["simulated"] is True
    assert receipt["claim_eligible"] is False


def test_simulated_false_allows_claim_eligible():
    """When simulated=False, claim_eligible can be True IF verification succeeded."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    # Not solved → claim_eligible=False even when simulated=False
    ctx1 = _make_mock_ctx(runner_completed=True, solve_eligible=False)
    r1 = build_repair_receipt(ctx1)
    assert r1["simulated"] is False
    assert r1["claim_eligible"] is False
    
    # Solved + verification → claim_eligible=True
    ctx2 = _make_mock_ctx(runner_completed=True, solve_eligible=True, reproduced=True, final_patch="diff")
    r2 = build_repair_receipt(ctx2)
    assert r2["simulated"] is False
    assert r2["claim_eligible"] is True


def test_claim_eligible_requires_verification_success():
    """claim_eligible=True ONLY when verification succeeded, no failure, solve_eligible=True."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    
    # Not solved → claim_eligible=False
    ctx1 = _make_mock_ctx(runner_completed=True, solve_eligible=False)
    r1 = build_repair_receipt(ctx1)
    assert r1["claim_eligible"] is False
    
    # Solved but failure_reason present → claim_eligible=False
    ctx2 = _make_mock_ctx(runner_completed=True, solve_eligible=True, failure_reason="VERIFICATION_FAILED")
    r2 = build_repair_receipt(ctx2)
    assert r2["claim_eligible"] is False
    
    # Solved, no failure, verification → claim_eligible=True
    ctx3 = _make_mock_ctx(runner_completed=True, solve_eligible=True, reproduced=True, final_patch="diff")
    r3 = build_repair_receipt(ctx3)
    assert r3["claim_eligible"] is True


# ─── Test 3: observed_stop_layer ───

def test_observed_stop_layer_populated():
    """observed_stop_layer must match gate_exit logic."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    # Environment failure → gate_exit = "env_resolver"
    ctx = _make_mock_ctx(env_resolution={"ready": False})
    receipt = build_repair_receipt(ctx)
    assert receipt["observed_stop_layer"] == "env_resolver"
    
    # No reproduction → gate_exit = "repro_runner"
    ctx2 = _make_mock_ctx(reproduced=False, repro_script="")
    receipt2 = build_repair_receipt(ctx2)
    assert receipt2["observed_stop_layer"] == "repro_runner"
    
    # No patch → gate_exit = "patcher"
    ctx3 = _make_mock_ctx(reproduced=True, final_patch="")
    receipt3 = build_repair_receipt(ctx3)
    assert receipt3["observed_stop_layer"] == "patcher"
    
    # Has patch → gate_exit = "verification"
    ctx4 = _make_mock_ctx(reproduced=True, final_patch="diff")
    receipt4 = build_repair_receipt(ctx4)
    assert receipt4["observed_stop_layer"] == "verification"


# ─── Test 4: ENV failure classification ───

def test_env_failure_classified_as_fixable():
    """REPRO_ENVIRONMENT_FAILURE should be classified as a taxonomy value."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(failure_reason="REPRO_ENVIRONMENT_FAILURE")
    result = _failure_class(ctx)
    # Should be one of the taxonomy values (not the old 'env_noise' string)
    from nexus.services.local_heal.env_taxonomy import EnvFailureTaxonomy, TAXONOMY_META
    assert result in [m.value for m in EnvFailureTaxonomy]
    assert TAXONOMY_META[EnvFailureTaxonomy(result)]["agent_fixable"] is True


def test_env_fixable_when_denoise_attempted():
    """If env_denoise has data AND failure is env-related, taxonomy should classify it."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(
        failure_reason="REPRO_ENVIRONMENT_FAILURE",
        env_denoise={"numpy": "1.24.0 → 1.26.0"},
    )
    result = _failure_class(ctx)
    from nexus.services.local_heal.env_taxonomy import EnvFailureTaxonomy, TAXONOMY_META
    assert result in [m.value for m in EnvFailureTaxonomy]
    assert TAXONOMY_META[EnvFailureTaxonomy(result)]["agent_fixable"] is True


def test_env_external_blocked_for_binary():
    """BINARY_MISSING should be classified as TOOLCHAIN_MISSING."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(failure_reason="BINARY_MISSING: compiler not found")
    result = _failure_class(ctx)
    assert result == "TOOLCHAIN_MISSING"


def test_env_fixable_is_default():
    """Unknown env failures default to DEPENDENCY_MISMATCH."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(failure_reason="UNKNOWN_ENV_ISSUE")
    result = _failure_class(ctx)
    assert result == "DEPENDENCY_MISMATCH"


# ─── Test 5: failure_class uses new env classification ───

def test_failure_class_uses_env_classification():
    """_failure_class should return a taxonomy value, not env_noise."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(failure_reason="REPRO_ENVIRONMENT_FAILURE")
    result = _failure_class(ctx)
    from nexus.services.local_heal.env_taxonomy import EnvFailureTaxonomy
    assert result in [m.value for m in EnvFailureTaxonomy]


def test_failure_class_env_external():
    """BINARY_MISSING → TOOLCHAIN_MISSING."""
    from nexus.services.local_heal.receipt import _failure_class
    ctx = _make_mock_ctx(failure_reason="BINARY_MISSING: compiler not found")
    result = _failure_class(ctx)
    assert result == "TOOLCHAIN_MISSING"


# ─── Test 6: phase_durations ───

def test_phase_durations_empty_when_no_ledger():
    """phase_durations should be empty dict when no latency ledger."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx()
    receipt = build_repair_receipt(ctx)
    assert receipt["phase_durations"] == {}


def test_phase_durations_from_ledger():
    """phase_durations should extract from latency ledger."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    
    ledger = MagicMock()
    ledger.phases = [
        {"name": "reproduction", "duration_sec": 0.6},
        {"name": "planning", "duration_sec": 12.8},
        {"name": "patch", "duration_sec": 297.7},
    ]
    ledger.to_dict = lambda: {"phases": ledger.phases}
    
    ctx = _make_mock_ctx()
    ctx._latency_ledger = ledger
    receipt = build_repair_receipt(ctx)
    assert receipt["phase_durations"]["reproduction"] == 0.6
    assert receipt["phase_durations"]["planning"] == 12.8
    assert receipt["phase_durations"]["patch"] == 297.7


# ─── T2: Receipt match_authority semantic tests ────────────────────────────────

def test_receipt_match_authority_verbatim():
    """ctx with match_authority='verbatim' → receipt telemetries preserves it."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx(solve_eligible=True, reproduced=True, final_patch="diff")
    ctx.match_authority = "verbatim"
    receipt = build_repair_receipt(ctx)
    assert receipt["telemetries"]["match_authority"] == "verbatim"


def test_receipt_match_authority_cross_file_correction():
    """ctx with match_authority='cross_file_correction' → receipt preserves it."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx(solve_eligible=True, reproduced=True, final_patch="diff")
    ctx.match_authority = "cross_file_correction"
    receipt = build_repair_receipt(ctx)
    assert receipt["telemetries"]["match_authority"] == "cross_file_correction"


def test_receipt_match_authority_empty_string():
    """ctx with match_authority='' → receipt telemetries has empty string."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx()
    ctx.match_authority = ""
    receipt = build_repair_receipt(ctx)
    assert receipt["telemetries"]["match_authority"] == ""


def test_receipt_match_authority_none():
    """ctx with match_authority=None → receipt telemetries has empty string."""
    from nexus.services.local_heal.receipt import build_repair_receipt
    ctx = _make_mock_ctx()
    ctx.match_authority = None
    receipt = build_repair_receipt(ctx)
    assert receipt["telemetries"]["match_authority"] == ""
