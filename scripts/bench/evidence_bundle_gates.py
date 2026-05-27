from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from scripts.bench.public_gate_bundle import (
    build_public_gate_checks,
    derive_cost_efficiency_decision,
)
from scripts.bench.public_lane_contract import (
    build_expected_capability_evidence_contract,
    build_public_claim_gates,
    build_route_policy_evidence_contract,
    build_skill_mount_evidence_contract,
    derive_public_gate_failures,
)


@dataclass(frozen=True)
class EvidenceBundleGateOutputs:
    delivery_gate_failures: list[str]
    cost_gate_failures: list[str]
    route_policy_evidence_contract: dict[str, Any]
    expected_capability_evidence_contract: dict[str, Any]
    skill_mount_evidence_contract: dict[str, Any]
    delivery_gate_passed: bool
    cost_claim_passed: bool
    cost_efficiency_status: str
    cost_efficiency_failures: list[str]
    public_gate_checks: dict[str, Any]
    public_claim_gates: dict[str, dict[str, Any]]


def build_evidence_bundle_gate_outputs(
    context: Mapping[str, Any],
    config: Mapping[str, Any],
) -> EvidenceBundleGateOutputs:
    gate_failures = derive_public_gate_failures(context, config)
    delivery_gate_failures = list(gate_failures["delivery_gate_failures"])
    cost_gate_failures = list(gate_failures["cost_gate_failures"])

    if float(context.get("session_worker_contamination_rate", 0.0) or 0.0) > 0.0:
        delivery_gate_failures.append("session_worker_contamination_detected")

    outbound_prompt_ledger_summary = context["outbound_prompt_ledger_summary"]
    if bool(context.get("outbound_prompt_ledger_invalid", False)):
        cost_gate_failures.extend(str(item) for item in outbound_prompt_ledger_summary.get("failures", []) or [])

    rows = list(context["rows"])
    route_policy_evidence_contract = build_route_policy_evidence_contract(rows)
    if route_policy_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"route_policy_evidence:{failure}"
            for failure in route_policy_evidence_contract.get("failures", [])
        )

    expected_capability_evidence_contract = build_expected_capability_evidence_contract(rows)
    if expected_capability_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"expected_capability_evidence:{failure}"
            for failure in expected_capability_evidence_contract.get("failures", [])
        )

    skill_mount_evidence_contract = build_skill_mount_evidence_contract(rows)
    if skill_mount_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"skill_mount_evidence:{failure}"
            for failure in skill_mount_evidence_contract.get("failures", [])
        )

    delivery_gate_passed = not delivery_gate_failures
    cost_claim_passed = delivery_gate_passed and not cost_gate_failures
    exclusion_candidate = False
    exclusion_reason_code = ""
    exclusion_provenance = ""
    for row in rows:
        for receipt in row.get("capability_receipts", []) or []:
            if isinstance(receipt, dict):
                tel = receipt.get("telemetries", {}) or {}
                if tel.get("cost_accounting_exclusion_candidate"):
                    exclusion_candidate = True
                    exclusion_reason_code = "network_timeout_exceeded"
                    exclusion_provenance = tel.get("telemetry_provenance", "")

    cost_efficiency_decision = derive_cost_efficiency_decision(
        delivery_gate_passed=delivery_gate_passed,
        delivery_gate_failures=delivery_gate_failures,
        cost_gate_failures=cost_gate_failures,
        wall_cost_ratio_with_over_without=float(context["wall_cost_ratio_with_over_without"]),
        token_cost_ratio_with_over_without=float(context["token_cost_ratio_with_over_without"]),
        model_call_ratio_with_over_without=float(context["model_call_ratio_with_over_without"]),
        retry_cost_share_wall=float(context["retry_cost_share_wall"]),
        retry_cost_share_tokens=float(context["retry_cost_share_tokens"]),
        wall_ledger_invalid=bool(context["wall_ledger_invalid"]),
        warning_ledger_invalid=bool(context["warning_ledger_invalid"]),
        valid_comparison_ready=bool(context["valid_comparison_ready"]),
        exclusion_candidate=exclusion_candidate,
        exclusion_reason_code=exclusion_reason_code,
        exclusion_provenance=exclusion_provenance,
    )
    cost_efficiency_failures = list(cost_efficiency_decision.failures)
    cost_efficiency_status = cost_efficiency_decision.status
    if (
        cost_efficiency_failures
        and delivery_gate_passed
        and not cost_gate_failures
        and not bool(context["wall_ledger_invalid"])
        and not bool(context["warning_ledger_invalid"])
        and bool(context["valid_comparison_ready"])
        and float(context["wall_cost_ratio_with_over_without"]) <= 1.05
        and float(context["token_cost_ratio_with_over_without"]) <= 1.05
        and float(context["model_call_ratio_with_over_without"]) <= 1.0
        and float(context["retry_cost_share_wall"]) == 0.0
        and float(context["retry_cost_share_tokens"]) == 0.0
    ):
        cost_efficiency_status = "NEUTRAL"

    local_context = {
        **context,
        "config": config,
        "delivery_gate_failures": delivery_gate_failures,
        "cost_gate_failures": cost_gate_failures,
        "route_policy_evidence_contract": route_policy_evidence_contract,
        "expected_capability_evidence_contract": expected_capability_evidence_contract,
        "skill_mount_evidence_contract": skill_mount_evidence_contract,
        "delivery_gate_passed": delivery_gate_passed,
        "cost_claim_passed": cost_claim_passed,
        "cost_efficiency_status": cost_efficiency_status,
        "cost_efficiency_failures": cost_efficiency_failures,
    }
    public_gate_checks = build_public_gate_checks(local_context)
    public_claim_gates = build_public_claim_gates(
        delivery_gate_passed=delivery_gate_passed,
        cost_claim_passed=cost_claim_passed,
        cost_efficiency_status=cost_efficiency_status,
        delivery_gate_failures=delivery_gate_failures,
        cost_gate_failures=cost_gate_failures,
        cost_efficiency_failures=cost_efficiency_failures,
        public_gate_checks=public_gate_checks,
    )
    return EvidenceBundleGateOutputs(
        delivery_gate_failures=delivery_gate_failures,
        cost_gate_failures=cost_gate_failures,
        route_policy_evidence_contract=route_policy_evidence_contract,
        expected_capability_evidence_contract=expected_capability_evidence_contract,
        skill_mount_evidence_contract=skill_mount_evidence_contract,
        delivery_gate_passed=delivery_gate_passed,
        cost_claim_passed=cost_claim_passed,
        cost_efficiency_status=cost_efficiency_status,
        cost_efficiency_failures=cost_efficiency_failures,
        public_gate_checks=public_gate_checks,
        public_claim_gates=public_claim_gates,
    )
