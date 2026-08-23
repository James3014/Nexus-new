from __future__ import annotations

import json
from typing import Any, Final, Mapping, Sequence

PROTOCOL_COMMENT_ID: Final[int] = 5372838455
PROTOCOL_SCHEMA: Final[str] = "nexus.eia_roi_wave2_protocol.v1"
OBSERVATION_SCHEMA: Final[str] = "nexus.eia_roi_observation.v1"
QUALIFICATION_SCHEMA: Final[str] = "nexus.eia_roi_wave2_qualification.v1"
FIXED_WORKER_MODEL: Final[str] = "opencode-go/deepseek-v4-flash"
FIXED_WORKER_PROVIDER: Final[str] = "opencode"
NON_SCORING: Final[str] = "NON_SCORING"
FORMAL_SCORING: Final[str] = "FORMAL"
WAVE2_QUALIFIED: Final[str] = "WAVE2_HARNESS_QUALIFIED"
WAVE2_REVISE: Final[str] = "WAVE2_HARNESS_REVISE"


class Wave2QualificationError(ValueError):
    """Raised when a Wave 2 benchmark invariant is not physically supported."""


_FIXTURES: Final[dict[str, dict[str, Any]]] = {
    "F01": {
        "family": "localized repair",
        "base_sha": "c90cb159476c5824d4c1fc4e341652f60036ddf5",
        "allowed_paths": (
            "scripts/ops/pr_impact_gate.py",
            "tests/ops/test_pr_impact_gate.py",
        ),
        "verifier_command": "python3 -m pytest -q tests/ops/test_pr_impact_gate.py",
    },
    "F02": {
        "family": "localized repair",
        "base_sha": "667a4adf702b77e7ab45d61be292b484a3e46a12",
        "allowed_paths": (
            "nexus/contracts/unified_runtime_receipt.py",
            "tests/contracts/test_unified_runtime_receipt.py",
        ),
        "verifier_command": "python3 -m pytest -q tests/contracts/test_unified_runtime_receipt.py",
    },
    "F03": {
        "family": "bounded multi-file",
        "base_sha": "e67e2267171bf07ebb422ac42bf7b7c6d77a0920",
        "allowed_paths": (
            "nexus/events/contracts.py",
            "nexus/core/task_continuity.py",
            "nexus/orchestrator/self_hosted_task_service.py",
            "tests/core/test_event_bus.py",
            "tests/core/test_task_continuity.py",
            "tests/nexus/orchestrator/test_self_hosted_task_service.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/core/test_event_bus.py "
            "tests/core/test_task_continuity.py "
            "tests/nexus/orchestrator/test_self_hosted_task_service.py"
        ),
    },
    "F04": {
        "family": "bounded multi-file",
        "base_sha": "d974944d54f53ebaf673deb36dfd0aa366fc1704",
        "allowed_paths": (
            "nexus/services/external_intelligence_automation.py",
            "scripts/ops/external_intelligence_service.py",
            "tests/services/test_external_intelligence_automation.py",
            "tests/services/test_external_intelligence_service.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/services/test_external_intelligence_automation.py "
            "tests/services/test_external_intelligence_service.py"
        ),
    },
    "F05": {
        "family": "failing-test / diagnosis",
        "base_sha": "b9705e70720b4cceb61c26588898724ac4b8cfb8",
        "allowed_paths": (
            "scripts/ops/external_intelligence_service.py",
            "tests/services/test_external_intelligence_service.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/services/test_external_intelligence_service.py"
        ),
    },
    "F06": {
        "family": "failing-test / diagnosis",
        "base_sha": "d5f5d42da9319b7d2efc912525a28fd998cb97c6",
        "allowed_paths": (
            "scripts/ops/pr_impact_gate.py",
            "tests/ops/test_pr_impact_gate.py",
        ),
        "verifier_command": "python3 -m pytest -q tests/ops/test_pr_impact_gate.py",
    },
    "F07": {
        "family": "caller/interface dependency",
        "base_sha": "ef581b3282fde164dd525847af2860cd81208134",
        "allowed_paths": (
            "scripts/engine/nexus_cli.py",
            "scripts/ops/external_intelligence_service.py",
            "tests/ops/test_nexus_cli.py",
            "tests/services/test_external_intelligence_service.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/ops/test_nexus_cli.py "
            "tests/services/test_external_intelligence_service.py"
        ),
    },
    "F08": {
        "family": "caller/interface dependency",
        "base_sha": "bf847187bca61becf9d30ca6dab563a014c7a87e",
        "allowed_paths": (
            "nexus/contracts/completion_path_telemetry.py",
            "tests/contracts/test_completion_path_telemetry.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/contracts/test_completion_path_telemetry.py"
        ),
    },
    "F09": {
        "family": "irrelevant-context distractor",
        "base_sha": "839f8bb923d7ae6ce9b45be9c48591990c3e0ffd",
        "allowed_paths": (
            "scripts/ops/repo_doctor.py",
            "tests/ops/test_repo_doctor.py",
        ),
        "verifier_command": "python3 -m pytest -q tests/ops/test_repo_doctor.py",
    },
    "F10": {
        "family": "irrelevant-context distractor",
        "base_sha": "754036799b1ddbea60f3cbc3750afca7f0ebfc42",
        "allowed_paths": (
            "tests/ops/test_ci_gate_closeout_contract.py",
            "tests/ops/test_delivery_gate_contract.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/ops/test_ci_gate_closeout_contract.py "
            "tests/ops/test_delivery_gate_contract.py"
        ),
    },
    "F11": {
        "family": "known failure guard",
        "base_sha": "f9899121c6b691fd7a66a391a2055a2c78bd387b",
        "allowed_paths": (
            "nexus/services/external_intelligence_fanout.py",
            "tests/services/test_external_intelligence_fanout.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/services/test_external_intelligence_fanout.py"
        ),
    },
    "F12": {
        "family": "UNKNOWN/probe-required",
        "base_sha": "34052b5fe77af6d782f24c0d88f411470912ad45",
        "allowed_paths": (
            "nexus/contracts/github_orchestration.py",
            "nexus/orchestrator/github_orchestration.py",
            "scripts/ops/pr_impact_gate.py",
            "tests/contracts/test_github_orchestration.py",
            "tests/nexus/orchestrator/test_github_orchestration.py",
            "tests/ops/test_pr_impact_gate.py",
        ),
        "verifier_command": (
            "python3 -m pytest -q tests/contracts/test_github_orchestration.py "
            "tests/nexus/orchestrator/test_github_orchestration.py "
            "tests/nexus/orchestrator/test_repository_contract_gate.py "
            "tests/ops/test_pr_impact_gate.py"
        ),
    },
}

_STAGE1_A1_FIRST: Final[frozenset[str]] = frozenset({"F01", "F02", "F03", "F07", "F08", "F09"})

PAIR_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "planner_ref",
    "admission_ref",
    "worker_id",
    "profile",
    "provider",
    "model",
)

QUALIFICATION_WITNESSES: Final[tuple[str, ...]] = (
    "exact_base_materialization",
    "frozen_verifier_readback",
    "oracle_ledger_negative_control",
    "pair_identity_mismatch_rejection",
    "observation_roundtrip_not_observed",
    "result_quarantine_rejection",
)

TOKEN_COMPONENTS: Final[tuple[str, ...]] = ("compiler", "worker", "coordinator")
TOKEN_STATUSES: Final[frozenset[str]] = frozenset({"MEASURED", "NOT_OBSERVED"})

REQUIRED_OBSERVATION_FIELDS: Final[frozenset[str]] = frozenset({
    "schema",
    "protocol_comment_id",
    "scoring_mode",
    "fixture_id",
    "family",
    "base_sha",
    "base_tree",
    "arm",
    "order_index",
    "attempt_id",
    "planner_ref",
    "admission_ref",
    "worker_id",
    "profile",
    "provider",
    "model",
    "execution_realm",
    "transport",
    "compiler_artifact",
    "started_at",
    "ended_at",
    "first_pass_verifier_pass",
    "repair_count",
    "final_disposition",
    "candidate_head",
    "candidate_tree",
    "candidate_diff_sha256",
    "scope_violation_count",
    "unauthorized_path_attempt_count",
    "identity_substitution_violation",
    "false_green_or_evidence_insufficiency",
    "diagnosis_status",
    "diagnosis_probe",
    "evidence_refs",
    "coordinator_high_reasoning_invocation_count",
    "coordinator_high_reasoning_turn_count",
    "compiler_tokens",
    "compiler_token_status",
    "worker_tokens",
    "worker_token_status",
    "coordinator_tokens",
    "coordinator_token_status",
    "observable_total_tokens",
    "input_bytes",
    "output_bytes",
    "context_bytes",
    "verifier_command",
    "verifier_artifact_ref",
    "diff_check_pass",
    "allowed_path_audit_pass",
    "deletion_audit_pass",
})


def execution_fixture_manifest() -> dict[str, Any]:
    fixtures = []
    for fixture_id in sorted(_FIXTURES):
        spec = _FIXTURES[fixture_id]
        fixtures.append({
            "fixture_id": fixture_id,
            "family": spec["family"],
            "base_sha": spec["base_sha"],
            "allowed_paths": list(spec["allowed_paths"]),
            "verifier_command": spec["verifier_command"],
        })
    return {
        "schema": PROTOCOL_SCHEMA,
        "protocol_comment_id": PROTOCOL_COMMENT_ID,
        "scoring_mode": NON_SCORING,
        "fixtures": fixtures,
    }


def mandatory_schedule() -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for fixture_id in sorted(_FIXTURES):
        stage1_arms = ("A1", "A3") if fixture_id in _STAGE1_A1_FIRST else ("A3", "A1")
        for order_index, arm in enumerate(stage1_arms, start=1):
            schedule.append({
                "stage": 1,
                "fixture_id": fixture_id,
                "arm": arm,
                "order_index": order_index,
            })

        fixture_number = int(fixture_id[1:])
        stage2_arms = ("B1", "B2") if fixture_number % 2 else ("B2", "B1")
        for order_index, arm in enumerate(stage2_arms, start=1):
            schedule.append({
                "stage": 2,
                "fixture_id": fixture_id,
                "arm": arm,
                "order_index": order_index,
            })
    return schedule


def fixture_spec(fixture_id: str) -> dict[str, Any]:
    try:
        spec = _FIXTURES[fixture_id]
    except KeyError as exc:
        raise Wave2QualificationError(f"UNKNOWN_FIXTURE:{fixture_id}") from exc
    return {
        "fixture_id": fixture_id,
        "family": spec["family"],
        "base_sha": spec["base_sha"],
        "allowed_paths": tuple(spec["allowed_paths"]),
        "verifier_command": spec["verifier_command"],
    }


def validate_materialization(
    *,
    fixture_id: str,
    actual_head: str,
    actual_tree: str,
    allowed_paths: Sequence[str],
    verifier_command: str,
) -> dict[str, str]:
    spec = fixture_spec(fixture_id)
    if actual_head != spec["base_sha"]:
        raise Wave2QualificationError("FIXTURE_BASE_SHA_MISMATCH")
    if len(actual_tree) != 40 or any(ch not in "0123456789abcdef" for ch in actual_tree.lower()):
        raise Wave2QualificationError("INVALID_FIXTURE_TREE")
    if tuple(allowed_paths) != spec["allowed_paths"]:
        raise Wave2QualificationError("FIXTURE_ALLOWED_PATHS_MISMATCH")
    if verifier_command != spec["verifier_command"]:
        raise Wave2QualificationError("FIXTURE_VERIFIER_MISMATCH")
    return {"base_sha": actual_head, "base_tree": actual_tree.lower()}


def assert_stage1_pair_identity(a1: Mapping[str, Any], a3: Mapping[str, Any]) -> None:
    if a1.get("arm") != "A1" or a3.get("arm") != "A3":
        raise Wave2QualificationError("INVALID_STAGE1_PAIR_ARMS")
    for field in ("fixture_id", "base_sha", *PAIR_IDENTITY_FIELDS):
        if a1.get(field) != a3.get(field):
            raise Wave2QualificationError(f"STAGE1_PAIR_IDENTITY_MISMATCH:{field}")
    for field in PAIR_IDENTITY_FIELDS:
        if not str(a1.get(field) or "").strip():
            raise Wave2QualificationError(f"STAGE1_PAIR_IDENTITY_MISSING:{field}")


def validate_stage2_identity(row: Mapping[str, Any]) -> None:
    arm = str(row.get("arm") or "")
    if arm == "B1":
        if row.get("provider") != FIXED_WORKER_PROVIDER or row.get("model") != FIXED_WORKER_MODEL:
            raise Wave2QualificationError("FIXED_WORKER_IDENTITY_MISMATCH")
        if row.get("admission_state") != "ALLOW":
            raise Wave2QualificationError("FIXED_WORKER_NOT_ADMITTED")
        if row.get("provider_preflight") != "AVAILABLE":
            raise Wave2QualificationError("FIXED_WORKER_UNAVAILABLE")
        return
    if arm == "B2":
        if not str(row.get("planner_ref") or "").strip():
            raise Wave2QualificationError("AUTHORITATIVE_SELECTION_MISSING_PLANNER_REF")
        if not str(row.get("admission_ref") or "").strip():
            raise Wave2QualificationError("AUTHORITATIVE_SELECTION_MISSING_ADMISSION_REF")
        if row.get("admission_state") != "ALLOW":
            raise Wave2QualificationError("AUTHORITATIVE_SELECTION_NOT_ADMITTED")
        return
    raise Wave2QualificationError("INVALID_STAGE2_ARM")


def assert_oracle_quarantine(
    outbound_payloads: Sequence[str],
    *,
    forbidden_tokens: Sequence[str],
) -> None:
    normalized_tokens = tuple(token for token in forbidden_tokens if str(token).strip())
    if not normalized_tokens:
        raise Wave2QualificationError("ORACLE_TOKEN_SET_REQUIRED")
    for payload in outbound_payloads:
        text = str(payload)
        for token in normalized_tokens:
            if token in text:
                raise Wave2QualificationError("HIDDEN_ORACLE_LEAK")


def validate_token_provenance(row: Mapping[str, Any]) -> None:
    measured_total = 0
    for component in TOKEN_COMPONENTS:
        status = str(row.get(f"{component}_token_status") or "")
        if status not in TOKEN_STATUSES:
            raise Wave2QualificationError(f"INVALID_TOKEN_STATUS:{component}")
        value = row.get(f"{component}_tokens")
        if status == "NOT_OBSERVED":
            if value is not None:
                raise Wave2QualificationError(f"UNOBSERVED_TOKEN_VALUE_PRESENT:{component}")
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise Wave2QualificationError(f"INVALID_MEASURED_TOKEN_VALUE:{component}")
        measured_total += value

    observable_total = row.get("observable_total_tokens")
    if not isinstance(observable_total, int) or isinstance(observable_total, bool):
        raise Wave2QualificationError("INVALID_OBSERVABLE_TOTAL_TOKENS")
    if observable_total != measured_total:
        raise Wave2QualificationError("OBSERVABLE_TOTAL_TOKEN_MISMATCH")


def validate_observation(row: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_OBSERVATION_FIELDS - set(row))
    if missing:
        raise Wave2QualificationError(f"OBSERVATION_FIELDS_MISSING:{','.join(missing)}")
    if row.get("schema") != OBSERVATION_SCHEMA:
        raise Wave2QualificationError("INVALID_OBSERVATION_SCHEMA")
    if row.get("protocol_comment_id") != PROTOCOL_COMMENT_ID:
        raise Wave2QualificationError("PROTOCOL_BINDING_MISMATCH")
    if row.get("scoring_mode") != NON_SCORING:
        raise Wave2QualificationError("WAVE2_OBSERVATION_MUST_BE_NON_SCORING")

    spec = fixture_spec(str(row.get("fixture_id") or ""))
    if row.get("family") != spec["family"] or row.get("base_sha") != spec["base_sha"]:
        raise Wave2QualificationError("OBSERVATION_FIXTURE_BINDING_MISMATCH")
    if row.get("verifier_command") != spec["verifier_command"]:
        raise Wave2QualificationError("OBSERVATION_VERIFIER_BINDING_MISMATCH")
    repair_count = row.get("repair_count")
    if (
        not isinstance(repair_count, int)
        or isinstance(repair_count, bool)
        or repair_count not in {0, 1}
    ):
        raise Wave2QualificationError("REPAIR_BUDGET_EXCEEDED")
    validate_token_provenance(row)


def serialize_observation(row: Mapping[str, Any]) -> str:
    validate_observation(row)
    return json.dumps(dict(row), sort_keys=True, separators=(",", ":"))


def deserialize_observation(payload: str) -> dict[str, Any]:
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise Wave2QualificationError("INVALID_OBSERVATION_PAYLOAD")
    validate_observation(decoded)
    return decoded


def assert_scoring_allowed(*, qualification_state: str, scoring_mode: str) -> None:
    if scoring_mode == NON_SCORING:
        return
    if scoring_mode != FORMAL_SCORING:
        raise Wave2QualificationError("INVALID_SCORING_MODE")
    if qualification_state != WAVE2_QUALIFIED:
        raise Wave2QualificationError("FORMAL_SCORING_BEFORE_WAVE2_QUALIFICATION")


def build_qualification_receipt(witnesses: Mapping[str, object]) -> dict[str, Any]:
    unexpected = sorted(set(witnesses) - set(QUALIFICATION_WITNESSES))
    if unexpected:
        raise Wave2QualificationError(f"UNKNOWN_QUALIFICATION_WITNESS:{','.join(unexpected)}")

    evidence_refs: dict[str, str] = {}
    for name in QUALIFICATION_WITNESSES:
        raw_ref = witnesses.get(name)
        evidence_refs[name] = raw_ref.strip() if isinstance(raw_ref, str) else ""

    missing = [name for name, evidence_ref in evidence_refs.items() if not evidence_ref]
    state = WAVE2_QUALIFIED if not missing else WAVE2_REVISE
    return {
        "schema": QUALIFICATION_SCHEMA,
        "protocol_comment_id": PROTOCOL_COMMENT_ID,
        "gate_passed": not missing,
        "state": state,
        "missing_witnesses": missing,
        "evidence_refs": evidence_refs,
        "formal_scoring_authorized": not missing,
    }
