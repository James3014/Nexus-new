from __future__ import annotations

import datetime
from pathlib import Path
import pytest
import yaml

from nexus.contracts.workforce_admission import (
    AdmissionDecision,
    WorkforceAdmissionRequest,
)
from nexus.services.model_workforce_policy import (
    WorkforcePolicyLoader,
    WorkforcePolicyValidationError,
    compute_policy_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "nexus/config/model_workforce.yaml"


def test_loader_loads_default_policy_successfully() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    snapshot = loader.load()

    assert snapshot.schema == "nexus.model_workforce.v1"
    assert snapshot.status == "current"
    assert snapshot.route_authority == "CapabilityPlanner"
    assert len(snapshot.declared_states) > 0
    assert len(snapshot.workers) == 25
    assert snapshot.policy_hash is not None
    assert len(snapshot.policy_hash) == 64  # SHA-256 hex length


def test_loader_fails_closed_when_policy_file_missing(tmp_path: Path) -> None:
    missing_file = tmp_path / "non_existent_policy.yaml"
    loader = WorkforcePolicyLoader(missing_file)
    with pytest.raises(WorkforcePolicyValidationError, match="Policy file not found"):
        loader.load()


def test_loader_fails_closed_on_invalid_schema(tmp_path: Path) -> None:
    bad_policy = tmp_path / "bad_policy.yaml"
    bad_policy.write_text(
        yaml.dump({
            "schema": "invalid.schema.v9",
            "status": "current",
            "route_authority": "CapabilityPlanner",
            "last_verified": "2026-07-29",
            "states": ["PROVEN_MAINCHAIN"],
            "workers": {"w1": {"provider": "p", "model": "m", "state": "PROVEN_MAINCHAIN", "availability": "AVAILABLE", "roles": ["r"]}},
            "routing": {"blocked_or_disabled_models_must_not_be_selected": True, "experiment_only_models_require_explicit_authorization": True},
            "context_policy": {},
        }),
        encoding="utf-8",
    )
    loader = WorkforcePolicyLoader(bad_policy)
    with pytest.raises(WorkforcePolicyValidationError, match="Invalid schema"):
        loader.load()


def test_loader_fails_closed_when_last_verified_is_in_future(tmp_path: Path) -> None:
    future_date = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    bad_policy = tmp_path / "future_policy.yaml"
    bad_policy.write_text(
        yaml.dump({
            "schema": "nexus.model_workforce.v1",
            "status": "current",
            "route_authority": "CapabilityPlanner",
            "last_verified": future_date,
            "states": ["PROVEN_MAINCHAIN"],
            "workers": {"w1": {"provider": "p", "model": "m", "state": "PROVEN_MAINCHAIN", "availability": "AVAILABLE", "roles": ["r"]}},
            "routing": {"blocked_or_disabled_models_must_not_be_selected": True, "experiment_only_models_require_explicit_authorization": True},
            "context_policy": {},
        }),
        encoding="utf-8",
    )
    loader = WorkforcePolicyLoader(bad_policy)
    with pytest.raises(WorkforcePolicyValidationError, match="in the future"):
        loader.load()


def test_loader_fails_closed_on_duplicate_provider_model_identity(tmp_path: Path) -> None:
    bad_policy = tmp_path / "dup_policy.yaml"
    bad_policy.write_text(
        yaml.dump({
            "schema": "nexus.model_workforce.v1",
            "status": "current",
            "route_authority": "CapabilityPlanner",
            "last_verified": "2026-07-29",
            "states": ["PROVEN_MAINCHAIN"],
            "workers": {
                "w1": {"provider": "p1", "model": "m1", "state": "PROVEN_MAINCHAIN", "availability": "AVAILABLE", "roles": ["r"]},
                "w2": {"provider": "p1", "model": "m1", "state": "PROVEN_MAINCHAIN", "availability": "AVAILABLE", "roles": ["r"]},
            },
            "routing": {"blocked_or_disabled_models_must_not_be_selected": True, "experiment_only_models_require_explicit_authorization": True},
            "context_policy": {},
        }),
        encoding="utf-8",
    )
    loader = WorkforcePolicyLoader(bad_policy)
    with pytest.raises(WorkforcePolicyValidationError, match=r"Duplicate provider\+model identity"):
        loader.load()


def test_deterministic_semantic_hash_calculation() -> None:
    data = {"a": 1, "b": [1, 2, 3]}
    h1 = compute_policy_hash(data)
    h2 = compute_policy_hash(data)
    assert h1 == h2
    assert len(h1) == 64


def test_admission_resolution_by_worker_id_and_provider_model() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    snapshot = loader.load()

    # Resolve by ID
    req1 = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        role="fast_bounded_implementation",
        autonomy="L2",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["task_card", "allowed_files", "mandatory_commands", "independent_verification"],  # type: ignore[arg-type]
    )
    dec1 = loader.admit(req1, snapshot)
    assert dec1.decision == AdmissionDecision.ALLOW
    assert dec1.resolved_worker_id == "agy_flash"

    # Resolve by provider + model
    req2 = WorkforceAdmissionRequest(
        provider="agy",
        model="gemini-3.6-flash-high",
        role="fast_bounded_implementation",
        autonomy="L2",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["task_card", "allowed_files", "mandatory_commands", "independent_verification"],  # type: ignore[arg-type]
    )
    dec2 = loader.admit(req2, snapshot)
    assert dec2.decision == AdmissionDecision.ALLOW
    assert dec2.resolved_worker_id == "agy_flash"


def test_admission_blocks_missing_route_authorization() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    req = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        role="fast_bounded_implementation",
        autonomy="L2",
        context="nexus_bounded",
        route_authorized=False,
        provided_controls=["task_card", "allowed_files", "mandatory_commands", "independent_verification"],  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.BLOCK
    assert any("Route authorization required" in r for r in dec.decision_reasons)


def test_admission_blocks_non_admissible_states_and_unavailability() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)

    # REGISTERED_BLOCKED
    req_gemini = WorkforceAdmissionRequest(
        requested_worker_id="direct_gemini",
        role="fast_bounded_implementation",
        autonomy="L0",
        context="nexus_bounded",
        route_authorized=True,
    )
    dec_gemini = loader.admit(req_gemini)
    assert dec_gemini.decision == AdmissionDecision.BLOCK

    # QUARANTINED
    req_laguna = WorkforceAdmissionRequest(
        requested_worker_id="opencode_laguna",
        role="tool_discipline_experiment",
        autonomy="L0",
        context="nexus_bounded",
        route_authorized=True,
    )
    dec_laguna = loader.admit(req_laguna)
    assert dec_laguna.decision == AdmissionDecision.BLOCK

    # BLOCKED_CLIENT_UPGRADE availability
    req_codex = WorkforceAdmissionRequest(
        requested_worker_id="codex_luna",
        role="main_engineering",
        autonomy="L3_HISTORICAL",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["codex_cli_upgrade", "governed_adapter", "independent_verification", "receipt"],  # type: ignore[arg-type]
    )
    dec_codex = loader.admit(req_codex)
    assert dec_codex.decision == AdmissionDecision.BLOCK


def test_admission_blocks_missing_required_controls() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    req = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        role="fast_bounded_implementation",
        autonomy="L2",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["task_card"],  # missing allowed_files, mandatory_commands, independent_verification  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.BLOCK
    assert "allowed_files" in dec.missing_controls
    assert "independent_verification" in dec.missing_controls


def test_admission_escalates_role_mismatch() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    # agy_flash roles are [fast_bounded_implementation, focused_verification]
    req = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        role="main_engineering",
        autonomy="L2",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["task_card", "allowed_files", "mandatory_commands", "independent_verification"],  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.ESCALATE
    assert any("outside admitted roles" in r for r in dec.decision_reasons)


def test_admission_escalates_autonomy_exceeding_ceiling() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    # agy_flash autonomy is L2, requesting L2+
    req = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        role="fast_bounded_implementation",
        autonomy="L2+",
        context="nexus_bounded",
        route_authorized=True,
        provided_controls=["task_card", "allowed_files", "mandatory_commands", "independent_verification"],  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.ESCALATE
    assert any("exceeds worker autonomy ceiling" in r for r in dec.decision_reasons)


def test_admission_escalates_local_nexus_full_and_regression() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    # local_coder_7b requested with nexus_full context
    req = WorkforceAdmissionRequest(
        requested_worker_id="local_coder_7b",
        role="bounded_code_candidate",
        autonomy="L1",
        context="nexus_full",
        route_authorized=True,
        provided_controls=["small_scope", "parser", "compile", "focused_tests", "reversible_application"],  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.ESCALATE
    assert any("nexus_full" in r for r in dec.decision_reasons)


def test_admission_escalates_physical_mutation_conflicts() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)
    # opencode_mimo_free forbids direct_workspace_mutation
    req = WorkforceAdmissionRequest(
        requested_worker_id="opencode_mimo_free",
        role="bounded_candidate_generation",
        autonomy="L1",
        context="nexus_bounded",
        mutation_requested=True,
        route_authorized=True,
        provided_controls=["isolated_directory", "bounded_context", "json_event_receipt", "parser", "focused_tests", "verifier"],  # type: ignore[arg-type]
    )
    dec = loader.admit(req)
    assert dec.decision == AdmissionDecision.ESCALATE
    assert any("forbids physical mutation" in r for r in dec.decision_reasons)


def test_experiment_only_requires_explicit_authorization() -> None:
    loader = WorkforcePolicyLoader(POLICY_PATH)

    # Without explicit authorization -> BLOCK
    req_no_auth = WorkforceAdmissionRequest(
        requested_worker_id="opencode_big_pickle",
        role="bounded_experiment",
        autonomy="L0",
        context="nexus_bounded",
        explicit_experiment_authorization=False,
        route_authorized=True,
    )
    dec_no_auth = loader.admit(req_no_auth)
    assert dec_no_auth.decision == AdmissionDecision.BLOCK
    assert any("requires explicit experiment authorization" in r for r in dec_no_auth.decision_reasons)

    # With explicit authorization -> ALLOW
    req_auth = WorkforceAdmissionRequest(
        requested_worker_id="opencode_big_pickle",
        role="bounded_experiment",
        autonomy="L0",
        context="nexus_bounded",
        explicit_experiment_authorization=True,
        route_authorized=True,
    )
    dec_auth = loader.admit(req_auth)
    assert dec_auth.decision == AdmissionDecision.ALLOW
