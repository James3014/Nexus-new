from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


NON_PUBLIC_SHORTCUT_FLAGS = (
    "force_learn_slo_ready",
    "parallel_arms_smoke_only",
    "nexus_only",
)


def build_public_lane_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    shortcut_flags = {
        "force_learn_slo_ready": bool(config.get("force_learn_slo_ready")),
        "parallel_arms_smoke_only": config.get("parallel_arms") == "smoke-only",
        "nexus_only": bool(config.get("nexus_only")),
    }
    non_public_reasons = [name for name, enabled in shortcut_flags.items() if enabled]
    return {
        "schema": "nexus_public_lane_contract_v1",
        "strict_public_lane": True,
        "non_public_shortcut_flags": shortcut_flags,
        "non_public_eligible": not non_public_reasons,
        "non_public_reasons": non_public_reasons,
        "trust_workspace_policy": str(config.get("trust_workspace_policy") or "unspecified"),
        "claim_boundary": [
            "Public lane evidence cannot use shortcut readiness flags.",
            "Nexus-only and smoke-only runs are diagnostic and cannot support public uplift claims.",
            "CLI workspace trust policy must be recorded separately from verifier trust mismatch.",
        ],
    }


def public_lane_gate_failures(config: Mapping[str, Any]) -> list[str]:
    contract = build_public_lane_contract(config)
    return [f"non_public_shortcut:{reason}" for reason in contract["non_public_reasons"]]


def commercial_model_basis_gate_failures(config: Mapping[str, Any]) -> list[str]:
    """Fail closed when a public commercial claim lacks a commercial-model task basis."""

    if not bool(config.get("commercial_model_basis_required", False)):
        return []

    failures: list[str] = []
    tasks_file = str(config.get("tasks_file") or "").strip()
    payload: dict[str, Any] = {}
    if not tasks_file:
        return ["commercial_model_basis:tasks_file_missing", "commercial_model_basis:not_ready"]

    path = Path(tasks_file)
    if not path.exists() or not path.is_file():
        return ["commercial_model_basis:tasks_file_not_readable", "commercial_model_basis:not_ready"]

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            f"commercial_model_basis:tasks_file_parse_failed:{exc.__class__.__name__}",
            "commercial_model_basis:not_ready",
        ]
    if isinstance(loaded, Mapping):
        payload = dict(loaded)
    else:
        return ["commercial_model_basis:tasks_file_not_mapping", "commercial_model_basis:not_ready"]

    schema = str(payload.get("schema") or "")
    rows = payload.get("rows")
    rows = rows if isinstance(rows, list) else []
    tasks = payload.get("tasks")
    tasks = tasks if isinstance(tasks, list) else []

    if schema.startswith("nexus.skill_fit_"):
        failures.append("commercial_model_basis:skill_fit_matrix_not_public_claim_basis")
    if any(isinstance(row, Mapping) and str(row.get("arm_type") or "") == "skill_ablation" for row in rows):
        failures.append("commercial_model_basis:ablation_rows_not_public_claim_basis")

    benchmark_id = str(payload.get("benchmark_id") or "")
    commercial_ready = bool(
        payload.get("frozen") is True
        and "commercial" in benchmark_id
        and str(payload.get("commercial_lane_source") or "").strip()
        and tasks
        and all(isinstance(task, Mapping) and str(task.get("commercial_lane") or "").strip() for task in tasks)
    )
    if not commercial_ready:
        failures.append("commercial_model_basis:not_commercial_model_basis")
        failures.append("commercial_model_basis:not_ready")

    return sorted(set(failures))


def _gate_verdict(bundle: Mapping[str, Any], name: str) -> str:
    gate = bundle.get(name)
    return str(gate.get("verdict") or gate.get("status") or "") if isinstance(gate, Mapping) else ""


def _gate_failures(bundle: Mapping[str, Any], name: str) -> list[str]:
    gate = bundle.get(name)
    if not isinstance(gate, Mapping):
        return [f"{name}_missing"]
    failures = gate.get("failures")
    if isinstance(failures, list):
        return [str(item) for item in failures]
    return []


def _public_gate_checks(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    gate = bundle.get("public_claim_gate")
    checks = gate.get("checks") if isinstance(gate, Mapping) else {}
    return checks if isinstance(checks, Mapping) else {}


def build_route_policy_evidence_contract(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate route-policy evidence for public with-Nexus rows."""
    with_rows = [row for row in rows if str(row.get("mode") or "") == "with_nexus"]
    failures: list[str] = []
    checked_rows = 0
    cost_capped_rescue_rows = 0
    for row in with_rows:
        if not bool(row.get("run_eligible", True)):
            continue
        checked_rows += 1
        locator = f"{row.get('task_id', 'unknown')}:{row.get('trial_index', 1)}"
        policy = row.get("route_execution_policy")
        if not isinstance(policy, Mapping):
            failures.append(f"{locator}:route_execution_policy_missing")
            continue
        reason_codes = policy.get("reason_codes")
        if not isinstance(reason_codes, list):
            failures.append(f"{locator}:route_execution_policy_reason_codes_missing")
            reason_codes = []
        reason_set = {str(item) for item in reason_codes}
        cost_capped_rescue = "cost_capped_capability_allows_verified_pre_model_rescue" in reason_set
        if cost_capped_rescue:
            cost_capped_rescue_rows += 1
            if str(row.get("capability_activation_contract") or "") != "cost_capped":
                failures.append(f"{locator}:cost_capped_rescue_without_cost_capped_contract")
            if not bool(row.get("hidden_verifier_passed", False)):
                failures.append(f"{locator}:cost_capped_rescue_without_hidden_verifier_pass")
            if str(row.get("local_reflex_risk_level") or "") != "low":
                failures.append(f"{locator}:cost_capped_rescue_without_low_risk")
            if str(row.get("local_reflex_bare_sufficiency") or "") != "high":
                failures.append(f"{locator}:cost_capped_rescue_without_high_bare_sufficiency")
            if str(row.get("nexus_winner_source") or "") != "local_deterministic_pre_model_rescue":
                failures.append(f"{locator}:cost_capped_rescue_without_deterministic_delivery_source")
        elif (
            str(row.get("capability_activation_contract") or "") == "required"
            and "expected_capability_protection" in reason_set
            and bool(policy.get("pre_model_deterministic_rescue_allowed", False))
        ):
            failures.append(f"{locator}:required_protected_capability_pre_model_rescue_allowed")
    return {
        "schema": "nexus_route_policy_evidence_contract_v1",
        "status": "PASS" if not failures else "RETURN",
        "checked_with_nexus_rows": checked_rows,
        "cost_capped_rescue_rows": cost_capped_rescue_rows,
        "failures": sorted(set(failures)),
        "claim_boundary": [
            "Public with-Nexus rows must carry route_execution_policy evidence.",
            "Cost-capped protected rescue is only public-eligible when hidden verifier and local reflex guards are recorded.",
            "Required protected capability lanes must not be weakened by cost-capped rescue semantics.",
        ],
    }


def build_expected_capability_evidence_contract(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate expected capability receipt and invocation coverage for public Nexus rows."""

    failures: list[str] = []
    checked_rows = 0
    for row in rows:
        if str(row.get("mode") or "") != "with_nexus":
            continue
        if not bool(row.get("run_eligible", True)):
            continue
        expected = row.get("expected_capabilities")
        if not expected:
            receipt_coverage = row.get("expected_capability_receipt_coverage")
            if isinstance(receipt_coverage, Mapping):
                expected = receipt_coverage.get("expected")
        if not expected:
            continue
        checked_rows += 1
        locator = f"{row.get('task_id', 'unknown')}:{row.get('trial_index', 1)}"
        receipt_coverage = row.get("expected_capability_receipt_coverage")
        receipt_coverage = receipt_coverage if isinstance(receipt_coverage, Mapping) else {}
        invocation_coverage = row.get("expected_capability_invocation_coverage")
        invocation_coverage = invocation_coverage if isinstance(invocation_coverage, Mapping) else {}
        receipts = {
            str(item.get("name") or item.get("capability") or ""): item
            for item in row.get("capability_receipts", []) or []
            if isinstance(item, Mapping) and str(item.get("name") or item.get("capability") or "").strip()
        }
        receipt_missing = [str(item) for item in receipt_coverage.get("missing", []) or [] if str(item).strip()]
        invocation_missing = [str(item) for item in invocation_coverage.get("missing", []) or [] if str(item).strip()]
        if receipt_missing or not bool(receipt_coverage.get("all_public_safe", False)):
            failures.append(f"{locator}:receipt_missing:{','.join(receipt_missing) or 'unknown'}")
        if invocation_missing or not bool(invocation_coverage.get("all_invoked_with_evidence", False)):
            failures.append(f"{locator}:invocation_missing:{','.join(invocation_missing) or 'unknown'}")
        for capability in expected:
            receipt = receipts.get(str(capability))
            if not isinstance(receipt, Mapping):
                continue
            if str(receipt.get("selection_source") or "") != "deterministic_receipt_lite":
                continue
            quality_failures = _deterministic_receipt_lite_quality_failures(row=row, capability=str(capability), receipt=receipt)
            failures.extend(f"{locator}:{failure}" for failure in quality_failures)

    return {
        "schema": "nexus_expected_capability_evidence_contract_v1",
        "status": "PASS" if not failures else "RETURN",
        "checked_with_nexus_rows": checked_rows,
        "failures": sorted(set(failures)),
        "claim_boundary": [
            "A verified patch is not enough for public Nexus claims when expected capabilities are declared.",
            "Every expected capability must be invoked with evidence and carry a public-safe receipt.",
            "Missing expected capability evidence forces RETURN even if delivery and cost gates pass.",
        ],
    }


def build_skill_mount_evidence_contract(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate skill mount evidence without routing over every discovered skill."""

    failures: list[str] = []
    checked_rows = 0
    checked_mounts = 0
    for row in rows:
        if str(row.get("mode") or "") != "with_nexus":
            continue
        if not bool(row.get("run_eligible", True)):
            continue
        mounts = row.get("skill_mount_contract")
        if mounts is None:
            mounts = row.get("skill_mount_contracts")
        if not mounts:
            continue
        checked_rows += 1
        if isinstance(mounts, Mapping):
            mounts = [mounts]
        if not isinstance(mounts, list):
            locator = f"{row.get('task_id', 'unknown')}:{row.get('trial_index', 1)}"
            failures.append(f"{locator}:skill_mount_contract_not_list")
            continue
        for mount in mounts:
            locator = f"{row.get('task_id', 'unknown')}:{row.get('trial_index', 1)}"
            if not isinstance(mount, Mapping):
                failures.append(f"{locator}:skill_mount_contract_entry_not_mapping")
                continue
            checked_mounts += 1
            skill_id = str(mount.get("skill_id") or "").strip()
            if not skill_id:
                failures.append(f"{locator}:skill_mount_missing_skill_id")
            if not str(mount.get("capability") or mount.get("capability_mount") or "").strip():
                failures.append(f"{locator}:skill_mount_missing_capability")
            reason_codes = mount.get("load_reason_codes")
            if not isinstance(reason_codes, list) or not any(str(item).strip() for item in reason_codes):
                failures.append(f"{locator}:skill_mount_missing_load_reason_codes:{skill_id or 'unknown'}")
            evidence_refs = mount.get("evidence_refs")
            if not isinstance(evidence_refs, list) or not any(str(item).strip() for item in evidence_refs):
                failures.append(f"{locator}:skill_mount_missing_evidence_refs:{skill_id or 'unknown'}")
            if mount.get("outcome_contributed") is not True:
                failures.append(f"{locator}:skill_mount_missing_outcome_contribution:{skill_id or 'unknown'}")
            status = str(mount.get("skill_status") or "").strip()
            if status and status != "nexus_curated_candidate":
                failures.append(f"{locator}:skill_mount_non_runtime_status:{skill_id or 'unknown'}:{status}")

    return {
        "schema": "nexus_skill_mount_evidence_contract_v1",
        "status": "PASS" if not failures else "RETURN",
        "checked_with_nexus_rows": checked_rows,
        "checked_mounts": checked_mounts,
        "failures": sorted(set(failures)),
        "claim_boundary": [
            "Nexus skill evidence is optional per row, but any mounted skill must carry a causal contract.",
            "Candidate, vendor, archive, and worktree-copy skills cannot be used as public runtime mounts.",
            "Skill evidence must show load reason, evidence refs, and outcome contribution before it can support route-cost claims.",
        ],
    }


def _non_empty_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _deterministic_receipt_lite_quality_failures(
    *, row: Mapping[str, Any], capability: str, receipt: Mapping[str, Any]
) -> list[str]:
    failures: list[str] = []
    if not _non_empty_string_list(receipt.get("evidence_refs")):
        failures.append(f"receipt_lite_missing_evidence_refs:{capability}")
    if len(set(_non_empty_string_list(receipt.get("distinct_roles")))) < 2:
        failures.append(f"receipt_lite_missing_distinct_roles:{capability}")
    if not _non_empty_string_list(receipt.get("replay_refs")):
        failures.append(f"receipt_lite_missing_replay_refs:{capability}")
    if not _non_empty_string_list(receipt.get("source_refs")):
        failures.append(f"receipt_lite_missing_source_refs:{capability}")
    if not bool(receipt.get("semantic_evidence_complete", False)) or str(row.get("semantic_status") or "") != "VERIFIED":
        failures.append(f"receipt_lite_semantic_evidence_incomplete:{capability}")
    return failures


def build_external_provider_claim_boundary_contract(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Classify whether the provider boundary can support public external-model claims."""
    config = bundle.get("config")
    config = config if isinstance(config, Mapping) else {}
    model_lock = bundle.get("model_lock")
    model_lock = model_lock if isinstance(model_lock, Mapping) else {}
    with_provider = str(config.get("with_model_provider") or "").strip().lower()
    without_mode = str(config.get("without_mode") or "").strip().lower()
    codex_model = str(model_lock.get("codex_model_name") or model_lock.get("direct_codex_model_name") or "").strip()

    failures: list[str] = []
    if with_provider == "codex" or without_mode == "codex" or codex_model:
        failures.append("codex_provider_prompt_wearing_only_for_external_model_claims")

    return {
        "schema": "nexus_external_provider_claim_boundary_contract_v1",
        "status": "PASS" if not failures else "OBSERVATION_ONLY",
        "public_claim_allowed": not failures,
        "failures": failures,
        "provider": {
            "with_model_provider": with_provider,
            "without_mode": without_mode,
            "codex_model_name": codex_model,
        },
        "claim_boundary": [
            "Codex-provider benchmark evidence is prompt-wearing-only for external public model claims unless a separate public-safe provider boundary is proven.",
            "Observation-only rows may support contamination diagnosis but must not support public parity, public cost, or same-model uplift wording.",
        ],
    }


def build_public_promotion_readiness_contract(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate existing bundle evidence into one fail-closed promotion contract."""
    checks = _public_gate_checks(bundle)
    taskset_contract = bundle.get("taskset_contract")
    taskset_contract = taskset_contract if isinstance(taskset_contract, Mapping) else {}
    contamination = bundle.get("session_worker_contamination")
    contamination = contamination if isinstance(contamination, Mapping) else {}
    outbound = bundle.get("outbound_prompt_ledger_gate")
    outbound = outbound if isinstance(outbound, Mapping) else {}
    x3_gate = bundle.get("x3_promotion_gate")
    x3_gate = x3_gate if isinstance(x3_gate, Mapping) else {}
    valid_comparison_gate = bundle.get("valid_comparison_readiness_gate")
    valid_comparison_gate = valid_comparison_gate if isinstance(valid_comparison_gate, Mapping) else {}
    route_policy_contract = bundle.get("route_policy_evidence_contract")
    route_policy_contract = route_policy_contract if isinstance(route_policy_contract, Mapping) else {}
    expected_capability_contract = bundle.get("expected_capability_evidence_contract")
    expected_capability_contract = expected_capability_contract if isinstance(expected_capability_contract, Mapping) else {}
    provider_boundary_contract = bundle.get("external_provider_claim_boundary_contract")
    provider_boundary_contract = provider_boundary_contract if isinstance(provider_boundary_contract, Mapping) else {}

    requirements = {
        "public_verified_delivery_pass": _gate_verdict(bundle, "public_verified_delivery_claim_gate") == "PASS",
        "public_cost_gate_pass": _gate_verdict(bundle, "public_cost_claim_gate") == "PASS",
        "public_cost_efficiency_non_regressed": _gate_verdict(bundle, "public_cost_efficiency_claim_gate")
        in {"PASS", "NEUTRAL", "IMPROVED"},
        "x3_promotion_pass": str(x3_gate.get("status") or x3_gate.get("verdict") or "") == "PASS",
        "valid_comparison_ready": str(valid_comparison_gate.get("status") or valid_comparison_gate.get("verdict") or "PASS")
        == "PASS",
        "fixed_public_taskset_ready": bool(taskset_contract.get("fixed_public_taskset_ready", False)),
        "session_worker_clean": bool(contamination.get("clean", True))
        and float(contamination.get("contamination_rate", 0.0) or 0.0) == 0.0,
        "outbound_prompt_ledger_clean": str(outbound.get("status") or outbound.get("verdict") or "PASS") == "PASS"
        and int(outbound.get("forbidden_literal_count", 0) or 0) == 0,
        "trust_mismatch_zero": float(checks.get("with_trust_mismatch_rate", 0.0) or 0.0) == 0.0
        and float(checks.get("without_trust_mismatch_rate", 0.0) or 0.0) == 0.0,
        "wall_ledger_conserved": float(checks.get("wall_ledger_with_conserved_rate", 1.0) or 0.0) == 1.0
        and float(checks.get("wall_ledger_without_conserved_rate", 1.0) or 0.0) == 1.0,
        "provider_tokens_measured": float(checks.get("provider_token_measured_rate_with", 1.0) or 0.0) == 1.0
        and float(checks.get("provider_token_measured_rate_without", 1.0) or 0.0) == 1.0,
        "route_policy_evidence_pass": str(route_policy_contract.get("status") or "") == "PASS",
        "expected_capability_evidence_pass": str(expected_capability_contract.get("status") or "PASS") == "PASS",
        "external_provider_public_claim_allowed": bool(provider_boundary_contract.get("public_claim_allowed", True)),
    }
    failures = [name for name, passed in requirements.items() if not passed]
    for gate_name in (
        "public_verified_delivery_claim_gate",
        "public_cost_claim_gate",
        "public_cost_efficiency_claim_gate",
        "x3_promotion_gate",
        "valid_comparison_readiness_gate",
        "route_policy_evidence_contract",
        "expected_capability_evidence_contract",
        "external_provider_claim_boundary_contract",
    ):
        failures.extend(f"{gate_name}:{failure}" for failure in _gate_failures(bundle, gate_name))
    failures = sorted(set(failures))
    return {
        "schema": "nexus_public_promotion_readiness_contract_v1",
        "status": "PASS" if not failures else "RETURN",
        "promotion_allowed": not failures,
        "requirements": requirements,
        "failures": failures,
        "claim_boundary": [
            "This contract only aggregates existing evidence bundle gates.",
            "It must not synthesize live model evidence or override delivery, trust, cost, x3, contamination, or outbound-ledger gates.",
            "Final Flash/Pro/GPT-5.5 claims require one readiness contract per source bundle plus a gap dashboard.",
        ],
    }


def derive_public_gate_failures(context: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, list[str]]:
    c = context
    delivery_gate_failures: list[str] = []
    cost_gate_failures: list[str] = []
    if config.get("parallel_arms") == "smoke-only":
        delivery_gate_failures.append("parallel_smoke")
    if len(c["with_rows"]) == 0 or len(c["without_rows"]) == 0:
        delivery_gate_failures.append("single_arm_run")
    if len(c["with_models"]) != 1 or len(c["without_models"]) != 1 or c["with_models"] != c["without_models"]:
        delivery_gate_failures.append("model_mismatch")
    if not c["same_task_trials"]:
        delivery_gate_failures.append("task_trial_mismatch")
    if not c["hidden_verifier_mode"]:
        delivery_gate_failures.append("hidden_verifier_disabled")
    if not c["eligibility_complete"]:
        delivery_gate_failures.append("run_eligibility_incomplete")
    if c["with_trust_mismatch_rate"] > 0.0:
        delivery_gate_failures.append("with_trust_mismatch_above_zero")
    if c["without_trust_mismatch_rate"] > 0.0:
        delivery_gate_failures.append("without_trust_mismatch_above_zero")
    if c["nexus_valid_rate"] < 1.0:
        delivery_gate_failures.append("nexus_wearing_below_threshold")
    if c["nexus_system_execution_valid_rate"] < 1.0:
        delivery_gate_failures.append("nexus_system_execution_below_threshold")
    if c["nexus_context_delivered_rate"] < 1.0:
        delivery_gate_failures.append("nexus_context_delivered_below_threshold")
    if c["nexus_system_usage_valid_rate"] < 1.0:
        delivery_gate_failures.append("nexus_system_usage_valid_below_threshold")
    if c["claim_verified_rate"] < 1.0:
        delivery_gate_failures.append("claim_verified_below_threshold")
    if c["route_decision_present_rate"] < 1.0:
        delivery_gate_failures.append("route_decision_missing")
    if c["token_measured_rate_with"] < 1.0:
        cost_gate_failures.append("with_token_measured_below_threshold")
    if c["token_measured_rate_without"] < 1.0:
        cost_gate_failures.append("without_token_measured_below_threshold")
    if c["provider_token_measured_rate_with"] < 1.0:
        cost_gate_failures.append("with_provider_token_measured_below_threshold")
    if c["provider_token_measured_rate_without"] < 1.0:
        cost_gate_failures.append("without_provider_token_measured_below_threshold")
    if not c["prompt_purity_gate_passed"]:
        cost_gate_failures.append("prompt_purity_above_threshold")
    if (
        c["verified_equal_without_lift"]
        and c["wall_cost_ratio_with_over_without"] > c["route_cost_regression_wall_ratio_threshold"]
        and c["wall_regression_systemic"]
    ):
        cost_gate_failures.append("route_cost_regression_without_verified_lift")
    if (
        c["verified_equal_without_lift"]
        and c["token_cost_ratio_with_over_without"] > c["route_cost_regression_token_ratio_threshold"]
        and c["token_regression_systemic"]
    ):
        cost_gate_failures.append("token_cost_regression_without_verified_lift")
    if not config.get("tasks_file") or not config.get("tasks_manifest_hash"):
        delivery_gate_failures.append("manifest_missing")
    if not config.get("runner_command"):
        delivery_gate_failures.append("runner_command_missing")
    delivery_gate_failures.extend(public_lane_gate_failures(config))
    return {
        "delivery_gate_failures": delivery_gate_failures,
        "cost_gate_failures": cost_gate_failures,
    }


def build_public_claim_gates(
    *,
    delivery_gate_passed: bool,
    cost_claim_passed: bool,
    cost_efficiency_status: str,
    delivery_gate_failures: list[str],
    cost_gate_failures: list[str],
    cost_efficiency_failures: list[str],
    public_gate_checks: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    delivery_failures = sorted(set(delivery_gate_failures))
    cost_failures = sorted(set(cost_gate_failures if delivery_gate_passed else delivery_gate_failures + cost_gate_failures))
    combined_claim_failures = sorted(set(delivery_gate_failures + cost_gate_failures))
    efficiency_failures = sorted(set(cost_efficiency_failures))
    checks = dict(public_gate_checks)
    return {
        "public_delivery_gate": {
            "verdict": "PASS" if delivery_gate_passed else "FAIL",
            "failures": delivery_failures,
            "checks": checks,
            "claim_scope": "verified_delivery_only",
        },
        "public_verified_delivery_claim_gate": {
            "verdict": "PASS" if delivery_gate_passed else "FAIL",
            "failures": delivery_failures,
            "checks": checks,
            "claim_scope": "verified_delivery_lift_only",
        },
        "public_cost_claim_gate": {
            "verdict": "PASS" if cost_claim_passed else "FAIL",
            "failures": cost_failures,
            "checks": {
                **checks,
                "delivery_gate_passed": delivery_gate_passed,
                "cost_claim_public_safe": cost_claim_passed,
            },
            "claim_scope": "token_and_cost_claims",
        },
        "public_cost_efficiency_claim_gate": {
            "verdict": cost_efficiency_status,
            "failures": efficiency_failures,
            "checks": {
                **checks,
                "delivery_gate_passed": delivery_gate_passed,
                "cost_safety_gate_passed": cost_claim_passed,
                "cost_efficiency_status": cost_efficiency_status,
            },
            "claim_scope": "cost_efficiency_direction_only",
        },
        "public_claim_gate": {
            "verdict": "PASS" if cost_claim_passed else "FAIL",
            "failures": combined_claim_failures,
            "checks": checks,
            "claim_scope": "same_model_plus_nexus_system_delivery_and_cost_gate",
        },
    }
