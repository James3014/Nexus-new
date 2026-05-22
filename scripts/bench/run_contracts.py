from __future__ import annotations

import json
from typing import Any

from nexus.engine.capability_aliases import normalize_capability_names


def receipt_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    if str(row.get("mode") or "") != "with_nexus":
        return {"status": "NOT_APPLICABLE", "missing": [], "reason": "non_nexus_arm"}
    coverage = row.get("expected_capability_receipt_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    missing = [str(item) for item in coverage.get("missing", []) or [] if str(item).strip()]
    return {
        "status": "DATA_CONTRACT_VIOLATION" if missing else "PASS",
        "missing": missing,
        "reason": "missing_expected_capability_receipts" if missing else "",
    }


def token_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    model_calls = int(row.get("model_calls", 0) or 0)
    total_tokens = int(row.get("total_tokens", 0) or 0)
    status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
    measured = total_tokens > 0 and status in {"ok", "measured"}
    if model_calls > 0 and not measured:
        return {
            "status": "DATA_CONTRACT_VIOLATION",
            "reason": "model_call_without_measured_provider_tokens",
            "source": str(row.get("gateway_token_source") or "missing"),
        }
    if model_calls <= 0:
        return {
            "status": "NOT_APPLICABLE",
            "reason": "no_model_call",
            "source": str(row.get("gateway_token_source") or "none"),
        }
    return {
        "status": "PASS",
        "reason": "",
        "source": str(row.get("gateway_token_source") or "provider"),
    }


def apply_data_contract_audit(row: dict[str, Any]) -> None:
    receipt_contract = receipt_data_contract(row)
    token_contract = token_data_contract(row)
    violations = [
        str(item["reason"])
        for item in (receipt_contract, token_contract)
        if str(item.get("status") or "") == "DATA_CONTRACT_VIOLATION" and str(item.get("reason") or "")
    ]
    row["receipt_data_contract_status"] = receipt_contract["status"]
    row["receipt_data_contract_missing"] = receipt_contract["missing"]
    row["receipt_data_contract_reason"] = receipt_contract["reason"]
    row["token_data_contract_status"] = token_contract["status"]
    row["token_data_contract_reason"] = token_contract["reason"]
    row["token_source_of_truth"] = token_contract["source"]
    row["data_contract_violation"] = bool(violations)
    row["data_contract_violation_reasons"] = violations


def rubric_section(
    *,
    status: str,
    score: float,
    hard_fail_reasons: list[str],
    required_artifacts: list[str],
    telemetry_completeness: dict[str, Any] | None = None,
    stage_credit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "score": round(float(score), 4),
        "hard_fail_reasons": hard_fail_reasons,
        "required_artifacts": required_artifacts,
        "telemetry_completeness": telemetry_completeness or {},
        "stage_credit": stage_credit or {},
    }


def build_rubric_contract(row: dict[str, Any]) -> dict[str, Any]:
    mode = str(row.get("mode") or "")
    expected = normalize_capability_names(row.get("expected_capabilities", []) or []) if mode == "with_nexus" else []
    receipt_missing = [str(item) for item in row.get("receipt_data_contract_missing", []) or [] if str(item).strip()]
    token_status = str(row.get("token_data_contract_status") or "")
    receipt_status = str(row.get("receipt_data_contract_status") or "")
    semantic_completed = bool(row.get("semantic_completed", False))
    run_eligible = bool(row.get("run_eligible", True))
    trust_mismatch = bool(row.get("report_trust_mismatch", False))
    model_calls = int(row.get("model_calls", 0) or 0)
    total_tokens = int(row.get("total_tokens", row.get("model_total_tokens", 0)) or 0)
    token_measured = bool(row.get("provider_token_measured", False)) or str(
        row.get("token_capture_status") or row.get("model_token_capture_status") or ""
    ).strip().lower() in {"measured", "ok"}

    plan_failures: list[str] = []
    if mode == "with_nexus" and not bool(row.get("model_uses_nexus", False)):
        plan_failures.append("nexus_route_not_observed")
    plan_status = "PASS" if not plan_failures else "RETURN"

    evidence_failures: list[str] = []
    if receipt_status == "DATA_CONTRACT_VIOLATION":
        evidence_failures.append("missing_required_capability_receipts")
    evidence_status = "PASS" if not evidence_failures else "RETURN"

    delivery_failures: list[str] = []
    if not semantic_completed:
        delivery_failures.append("semantic_not_verified")
    if trust_mismatch:
        delivery_failures.append("trust_mismatch")
    if not run_eligible:
        delivery_failures.append(str(row.get("infra_invalid_reason") or "run_not_eligible"))
    delivery_status = "PASS" if not delivery_failures else "RETURN"

    cost_failures: list[str] = []
    if token_status == "DATA_CONTRACT_VIOLATION":
        cost_failures.append("token_telemetry_incomplete")
    cost_status = "PASS" if not cost_failures else "RETURN"
    token_completeness = {
        "model_calls": model_calls,
        "total_tokens": total_tokens,
        "provider_token_measured": token_measured,
        "token_source_of_truth": str(row.get("token_source_of_truth") or ""),
    }

    stage_wall = {
        "executor_init_sec": float(row.get("gateway_invocation_build_sec", 0.0) or 0.0),
        "provider_wait_sec": float(row.get("gateway_provider_wait_sec", 0.0) or 0.0),
        "verifier_sec": float(row.get("hidden_verifier_wall_sec", 0.0) or 0.0),
        "receipt_write_sec": float(row.get("receipt_write_sec", 0.0) or 0.0),
    }
    hard_fail_reasons = sorted(set(plan_failures + evidence_failures + delivery_failures + cost_failures))
    overall_status = "PASS" if not hard_fail_reasons else "RETURN"
    return {
        "schema": "nexus_rubric_contract_v1",
        "overall_status": overall_status,
        "hard_fail_reasons": hard_fail_reasons,
        "plan_rubric": rubric_section(
            status=plan_status,
            score=1.0 if plan_status == "PASS" else 0.0,
            hard_fail_reasons=plan_failures,
            required_artifacts=["route_decision"] if mode == "with_nexus" else [],
            stage_credit={"route_decision_present": bool(row.get("route_decision_schema_version"))},
        ),
        "evidence_rubric": rubric_section(
            status=evidence_status,
            score=1.0 if evidence_status == "PASS" else 0.0,
            hard_fail_reasons=evidence_failures,
            required_artifacts=expected,
            telemetry_completeness={
                "receipt_data_contract_status": receipt_status,
                "missing": receipt_missing,
            },
        ),
        "delivery_rubric": rubric_section(
            status=delivery_status,
            score=1.0 if delivery_status == "PASS" else 0.0,
            hard_fail_reasons=delivery_failures,
            required_artifacts=["hidden_verifier", "delivery_gate"],
            stage_credit={
                "semantic_completed": semantic_completed,
                "run_eligible": run_eligible,
                "trust_mismatch": trust_mismatch,
            },
        ),
        "cost_rubric": rubric_section(
            status=cost_status,
            score=1.0 if cost_status == "PASS" else 0.0,
            hard_fail_reasons=cost_failures,
            required_artifacts=["provider_token_telemetry"] if model_calls > 0 else [],
            telemetry_completeness=token_completeness,
            stage_credit=stage_wall,
        ),
    }


def apply_rubric_contract(row: dict[str, Any]) -> None:
    rubric = build_rubric_contract(row)
    row["rubric_contract"] = rubric
    row["rubric_contract_json"] = json.dumps(rubric, ensure_ascii=False, sort_keys=True)
    row["rubric_contract_status"] = rubric["overall_status"]
    row["rubric_contract_hard_fail_reasons"] = rubric["hard_fail_reasons"]
    row["evidence_rubric_status"] = rubric["evidence_rubric"]["status"]
    row["delivery_rubric_status"] = rubric["delivery_rubric"]["status"]
    row["cost_rubric_status"] = rubric["cost_rubric"]["status"]


def apply_contracts_to_row(row: dict[str, Any]) -> None:
    apply_data_contract_audit(row)
    apply_rubric_contract(row)
