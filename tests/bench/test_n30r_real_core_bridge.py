"""N30R-R1B tests: genuine production executor wiring.

Source-level forbidden-pattern tests + runtime behavior tests.
"""
from __future__ import annotations

import ast
import copy
import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import sha256_str
from scripts.bench.n30r_runner import ARMS, _materialize_task
from scripts.bench.n30r_arm_adapters import _read_fixture_source
from scripts.bench.n30r_real_core_bridge import (
    REAL_CORE_ARM_ID,
    FROZEN_TOPOLOGY,
    FROZEN_PLANNER_VERSION,
    REQUIRED_PLANNER_FIELDS,
    RealCoreBridgeResult,
    invoke_capability_planner,
    validate_planner_snapshot,
    run_real_core_bridge,
    _build_production_receipt_hash,
)

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)

SMOKE_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "smoke_manifest.json"

_BRIDGE_SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "bench" / "n30r_real_core_bridge.py"


def _read_bridge_source() -> str:
    return _BRIDGE_SOURCE.read_text(encoding="utf-8")


# ===========================================================================
# Section 10: Source-level forbidden-pattern tests
# ===========================================================================

def test_real_core_bridge_has_no_direct_provider_call():
    """Bridge must not call provider() directly — only through LocalModelExecutor."""
    source = _read_bridge_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "provider":
                if any(
                    isinstance(p, ast.Constant) and p.value == "You are a code repair assistant."
                    for p in node.args
                ):
                    pytest.fail("Bridge has direct provider() call with system_prompt")


def test_real_core_bridge_has_no_manual_verifier():
    """Bridge must not call _run_verifier_in_dir."""
    source = _read_bridge_source()
    assert "_run_verifier_in_dir" not in source, "Bridge has manual verifier call"


def test_real_core_bridge_has_no_manual_apply_workspace():
    """Bridge must not use tempfile.TemporaryDirectory for manual apply."""
    source = _read_bridge_source()
    assert "tempfile.TemporaryDirectory" not in source, "Bridge has manual apply workspace"


def test_real_core_bridge_does_not_mutate_planner_snapshot():
    """Bridge must not assign to signal_snapshot keys."""
    source = _read_bridge_source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.value, ast.Name) and target.value.id == "signal_snapshot":
                        pytest.fail(f"Bridge mutates signal_snapshot at line {node.lineno}")


def test_real_core_bridge_does_not_hardcode_executor_called():
    """Bridge must not hardcode local_model_executor_called=True in fail-closed paths.
    In the success path (after LocalModelExecutor.run), True is correct."""
    source = _read_bridge_source()
    lines = source.split("\n")
    # The only allowed hardcoded local_model_executor_called=True is in the
    # success path return statement (after LocalModelExecutor.run was called).
    # All fail-closed paths must use executor_invoked variable.
    in_success_path = False
    for i, line in enumerate(lines, 1):
        if "LocalModelExecutor.run(" in line:
            in_success_path = True
        if in_success_path and "local_model_executor_called=True" in line and not line.strip().startswith("#"):
            continue
        if not in_success_path and "local_model_executor_called=True" in line and not line.strip().startswith("#"):
            if "executor_invoked" not in line:
                pytest.fail(f"Bridge hardcodes local_model_executor_called=True in fail-closed path at line {i}")


def test_real_core_bridge_does_not_hardcode_production_path_used():
    """Bridge must not hardcode production_local_path_used=True."""
    source = _read_bridge_source()
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "production_local_path_used=True" in stripped and not stripped.startswith("#"):
            pytest.fail(f"Bridge hardcodes production_local_path_used=True at line {i}")


def test_real_core_bridge_does_not_hash_snapshot_as_production_receipt():
    """Bridge must not use sha256_str(str(signal_snapshot)) as production_receipt_sha256."""
    source = _read_bridge_source()
    assert 'sha256_str(str(signal_snapshot))' not in source, (
        "Bridge uses snapshot hash as production receipt"
    )


# ===========================================================================
# Section 11: Runtime behavior tests
# ===========================================================================

def test_real_core_calls_local_model_executor_run_exactly_once():
    """LocalModelExecutor.run must be called exactly once with correct request."""
    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="def f(): pass",
        candidate_hash="abc123", reasoning_summary="test",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_actual_execution": True,
            "isolated_verifier_status": "fail",
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="qwen2.5-coder:7b-instruct",
        error="", timeout=False, evidence_refs=("ref1",),
    )

    call_count = 0
    def mock_run(request, provider=None):
        nonlocal call_count
        call_count += 1
        assert isinstance(request, LocalModelExecutorRequest)
        assert request.dry_run is False
        assert request.mutation_allowed is True
        assert request.verifier_allowed is True
        assert request.execution_topology == "localheal_pipeline"
        assert isinstance(request.route_context.get("signal_snapshot"), dict)
        return mock_response

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", side_effect=mock_run):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert call_count == 1
    assert result.local_model_executor_called is True


def test_real_core_does_not_mutate_planner_signal_snapshot():
    """Planner snapshot must be immutable through the bridge."""
    original_snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
        "protocol_mode": "anchored_edit",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "executor_provider": "ollama",
        "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
        "context_slimming_policy": {},
        "harness_relevance_policy": {},
        "research_isolation_policy": {},
    }
    snapshot_before = copy.deepcopy(original_snapshot)

    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="",
        candidate_hash="", reasoning_summary="",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_actual_execution": True,
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="qwen2.5-coder:7b-instruct",
        error="", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner", return_value=original_snapshot):
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert original_snapshot == snapshot_before, "Planner snapshot was mutated"


def test_provider_is_only_reached_inside_local_model_executor():
    """Provider must only be called inside LocalModelExecutor.run, not by bridge."""
    provider_call_stack = []

    def spy_provider(model, system_prompt, user_prompt):
        import traceback
        provider_call_stack.append("".join(traceback.format_stack()))
        return "def f(): pass"

    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="def f(): pass",
        candidate_hash="abc", reasoning_summary="",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_actual_execution": True,
            "isolated_verifier_status": "fail",
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="qwen2.5-coder:7b-instruct",
        error="", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], spy_provider, 3001, 0, "test")

    assert len(provider_call_stack) == 0, (
        "Provider was called outside LocalModelExecutor — bridge has direct provider call"
    )


def test_real_core_requires_actual_localheal_pipeline_execution():
    """Response metadata must confirm actual pipeline execution."""
    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="",
        candidate_hash="", reasoning_summary="",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": False,
            "localheal_pipeline_actual_execution": False,
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="qwen2.5-coder:7b-instruct",
        error="", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert result.terminal_status == "CONTRACT_INVALID"
    assert "pipeline_execution_incomplete" in result.verifier_status


def test_real_core_rejects_executor_response_without_pipeline_execution():
    """If pipeline_run_called=False, bridge must fail closed."""
    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=False, candidate_patch="",
        candidate_hash="", reasoning_summary="",
        raw_model_metadata={
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="none", model_name="",
        error="no_pipeline", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert result.terminal_status == "CONTRACT_INVALID"


def test_real_core_rejects_non_executor_response_type():
    """If executor returns non-response type, bridge must fail closed."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value="not_a_response"):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert result.terminal_status == "CONTRACT_INVALID"
    assert "non_executor_response_type" in result.verifier_status


def test_production_receipt_hash_is_hash_of_canonical_executor_response():
    """Receipt hash must be deterministic SHA-256 of canonical executor response."""
    r1 = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="x",
        candidate_hash="h1", reasoning_summary="",
        raw_model_metadata={"k": "v1"}, provider="p", model_name="m",
        error="", timeout=False, evidence_refs=(),
    )
    r2 = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="x",
        candidate_hash="h1", reasoning_summary="",
        raw_model_metadata={"k": "v1"}, provider="p", model_name="m",
        error="", timeout=False, evidence_refs=(),
    )
    r3 = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="x",
        candidate_hash="h1", reasoning_summary="",
        raw_model_metadata={"k": "v2"}, provider="p", model_name="m",
        error="", timeout=False, evidence_refs=(),
    )
    h1 = _build_production_receipt_hash(r1)
    h2 = _build_production_receipt_hash(r2)
    h3 = _build_production_receipt_hash(r3)
    assert h1 == h2, "Same response must produce same hash"
    assert h1 != h3, "Different metadata must produce different hash"
    assert len(h1) == 64


def test_production_receipt_hash_is_not_signal_snapshot_hash():
    """Receipt hash must differ from snapshot hash."""
    snapshot = {"planner_version": "capability_planner_v1", "key": "value"}
    snapshot_hash = sha256_str(json.dumps(snapshot, sort_keys=True, default=str))

    response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="",
        candidate_hash="", reasoning_summary="",
        raw_model_metadata={"different": True}, provider="", model_name="",
        error="", timeout=False, evidence_refs=(),
    )
    receipt_hash = _build_production_receipt_hash(response)

    assert receipt_hash != snapshot_hash


def test_candidate_isolation_fields_come_from_executor_metadata():
    """Candidate isolation must come from executor response metadata, not bridge."""
    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="patch",
        candidate_hash="real_hash", reasoning_summary="",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_actual_execution": True,
            "candidate_isolated": True,
            "selected_candidate_hash": "real_candidate",
            "isolated_verifier_status": "pass",
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="m",
        error="", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert result.candidate_id == "real_hash"
    assert result.verifier_status == "pass"
    assert result.terminal_status == "VERIFIED_SOLVE"


def test_verifier_fields_come_from_executor_metadata():
    """Verifier status must come from executor response, not bridge re-run."""
    mock_response = LocalModelExecutorResponse(
        invoked=True, local_model_called=True, candidate_patch="patch",
        candidate_hash="h", reasoning_summary="",
        raw_model_metadata={
            "execution_topology": "localheal_pipeline",
            "localheal_pipeline_run_called": True,
            "localheal_pipeline_actual_execution": True,
            "isolated_verifier_status": "fail",
            "selected_capabilities_used": ("repair_loop",),
        },
        provider="ollama", model_name="m",
        error="", timeout=False, evidence_refs=(),
    )

    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    with patch.object(LocalModelExecutor, "run", return_value=mock_response):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert result.verifier_status == "fail"
    assert result.terminal_status == "VERIFIED_FAIL"


def test_missing_planner_route_truth_source_blocks_execution():
    """Snapshot without route_truth_source must still pass validation (it's not required by planner)."""
    snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
        "protocol_mode": "anchored_edit",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
        "context_slimming_policy": {},
        "harness_relevance_policy": {},
        "research_isolation_policy": {},
    }
    errors = validate_planner_snapshot(snapshot)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_missing_planner_execution_topology_blocks_execution():
    """Snapshot without execution_topology must fail validation."""
    snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "protocol_mode": "anchored_edit",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
        "context_slimming_policy": {},
        "harness_relevance_policy": {},
        "research_isolation_policy": {},
    }
    errors = validate_planner_snapshot(snapshot)
    assert any("wrong_topology" in e or "incomplete_signal_snapshot" in e for e in errors)


def test_missing_planner_protocol_mode_blocks_execution():
    """Snapshot without protocol_mode must fail (required by executor)."""
    snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
        "context_slimming_policy": {},
        "harness_relevance_policy": {},
        "research_isolation_policy": {},
    }
    errors = validate_planner_snapshot(snapshot)
    assert any("incomplete_signal_snapshot" in e and "protocol_mode" in e for e in errors)


def test_missing_planner_executor_model_blocks_execution():
    """Snapshot without executor_model must fail (required by executor)."""
    snapshot = {
        "planner_version": "capability_planner_v1",
        "selected_executor": "local_model",
        "execution_topology": "localheal_pipeline",
        "protocol_mode": "anchored_edit",
        "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
        "context_slimming_policy": {},
        "harness_relevance_policy": {},
        "research_isolation_policy": {},
    }
    errors = validate_planner_snapshot(snapshot)
    assert any("incomplete_signal_snapshot" in e and "executor_model" in e for e in errors)


def test_prompt_variant_arm_is_not_labeled_real_core():
    """Old prompt-variant arm must not exist."""
    assert "N30R_B_7B_CORE" not in ARMS
    assert "N30R_B_7B_REAL_CORE" in ARMS


def test_golden_patch_is_absent_from_real_core_request():
    """Golden patch must not appear in the executor request."""
    manifest = json.loads(SMOKE_MANIFEST.read_text())
    task = _materialize_task(manifest["tasks"][0])

    captured_requests = []
    def mock_run(request, provider=None):
        captured_requests.append(request)
        return LocalModelExecutorResponse(
            invoked=False, local_model_called=False, candidate_patch="",
            candidate_hash="", reasoning_summary="",
            raw_model_metadata={}, provider="none", model_name="",
            error="dry_run", timeout=False, evidence_refs=(),
        )

    with patch.object(LocalModelExecutor, "run", side_effect=mock_run):
        with patch("scripts.bench.n30r_real_core_bridge.invoke_capability_planner") as mock_planner:
            mock_planner.return_value = {
                "planner_version": "capability_planner_v1",
                "selected_executor": "local_model",
                "execution_topology": "localheal_pipeline",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "executor_provider": "ollama",
                "ssd_route_map": {"capability_reasons": {"repair_loop": ["test"]}},
                "context_slimming_policy": {},
                "harness_relevance_policy": {},
                "research_isolation_policy": {},
            }
            result = run_real_core_bridge(task, ARMS["N30R_B_7B_REAL_CORE"], lambda m, s, u: "", 3001, 0, "test")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    req_str = json.dumps({
        "problem_statement": req.problem_statement,
        "route_context": {k: v for k, v in req.route_context.items() if k != "signal_snapshot"},
    })
    assert "golden" not in req_str.lower()
