from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus.engine.harness_route_policy import extract_failure_text
from nexus.engine.harness_sensors import (
    build_bdd_acceptance_receipt,
    build_harness_preflight_sensor,
    build_sensor_fusion_decision,
    build_semantic_failure_sensor,
)


def write_runtime_receipt_json(repo_root: Path, *, category: str, receipt_slug: str, payload: dict[str, Any]) -> str:
    rel = Path(".nexus") / "reports" / "capabilities" / category / f"{receipt_slug}.json"
    out = repo_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(rel)


def _business_acceptance_contract(route: dict[str, Any], *, task_desc: str = "") -> dict[str, str]:
    raw = route.get("bdd_acceptance") or route.get("business_acceptance") or {}
    if isinstance(raw, dict):
        contract = {
            "given": str(raw.get("given") or "").strip(),
            "when": str(raw.get("when") or "").strip(),
            "then": str(raw.get("then") or "").strip(),
        }
        if any(contract.values()):
            return contract
    features = route.get("route_features", {}) if isinstance(route.get("route_features", {}), dict) else {}
    raw = features.get("bdd_acceptance") or features.get("business_acceptance") or {}
    if isinstance(raw, dict):
        contract = {
            "given": str(raw.get("given") or "").strip(),
            "when": str(raw.get("when") or "").strip(),
            "then": str(raw.get("then") or "").strip(),
        }
        if any(contract.values()):
            return contract
    text = str(task_desc or "").strip()
    lower = text.lower()
    if "given" in lower and "when" in lower and "then" in lower:
        given_idx = lower.find("given")
        when_idx = lower.find("when", given_idx + 5)
        then_idx = lower.find("then", when_idx + 4)
        if given_idx >= 0 and when_idx > given_idx and then_idx > when_idx:
            return {
                "given": text[given_idx:when_idx].strip(" :.;"),
                "when": text[when_idx:then_idx].strip(" :.;"),
                "then": text[then_idx:].strip(" :.;"),
            }
    return {"given": "", "when": "", "then": ""}


def emit_harness_runtime_receipts(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    receipt_slug: str,
    selected_capabilities: set[str],
    capabilities: dict[str, Any],
    route: dict[str, Any],
    artifact_verified: bool,
) -> None:
    if "harness_preflight_sensor" in selected_capabilities:
        preflight = build_harness_preflight_sensor(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pending_capabilities=[],
            selected_capabilities=sorted(selected_capabilities),
        )
        report_path = write_runtime_receipt_json(
            repo_root,
            category="harness_preflight_sensor",
            receipt_slug=receipt_slug,
            payload=preflight,
        )
        capabilities["harness_preflight_refs"] = [report_path, f"cost_lane:{preflight['cost_lane']}"]
        capabilities["harness_preflight_report_path"] = report_path
        capabilities["capability_wired"] = preflight["capability_wired"]
        capabilities["executor_ready"] = preflight["executor_ready"]
        capabilities["cost_lane"] = preflight["cost_lane"]
        capabilities["harness_preflight_sensor_used"] = True
        capabilities["harness_preflight_sensor_gate_passed"] = bool(preflight["capability_wired"])

    if "semantic_failure_sensor" in selected_capabilities:
        failure_text = extract_failure_text(route=route, task_desc=task_desc) or task_desc
        failure_sensor = build_semantic_failure_sensor(failure_text=failure_text)
        report_path = write_runtime_receipt_json(
            repo_root,
            category="semantic_failure_sensor",
            receipt_slug=receipt_slug,
            payload=failure_sensor,
        )
        capabilities["semantic_failure_refs"] = [report_path, failure_sensor["summary"]]
        capabilities["failure_cause"] = failure_sensor["cause"]
        capabilities["likely_fix"] = failure_sensor["likely_fix"]
        capabilities["recommended_escalation"] = failure_sensor["recommended_escalation"]
        capabilities["semantic_failure_escalation_required"] = failure_sensor["escalation_required"]
        capabilities["retry_policy"] = failure_sensor["retry_policy"]
        sensor_fusion = build_sensor_fusion_decision(
            semantic_failure_sensor=failure_sensor,
            current_route=str(route.get("recommended_flow") or ""),
            phase="R",
        )
        capabilities["sensor_fusion_decision"] = sensor_fusion
        capabilities["sensor_fusion_recommended_capabilities"] = sensor_fusion["recommended_capabilities"]
        capabilities["sensor_fusion_escalation_required"] = sensor_fusion["escalation_required"]
        capabilities["semantic_failure_sensor_used"] = True
        capabilities["semantic_failure_sensor_gate_passed"] = bool(
            failure_sensor["retry_policy"].get("requires_evidence_delta")
            and not failure_sensor["retry_policy"].get("allow_blind_retry")
        )

    if "bdd_acceptance_skill" in selected_capabilities:
        contract = _business_acceptance_contract(route, task_desc=task_desc)
        receipt = build_bdd_acceptance_receipt(
            given=contract["given"],
            when=contract["when"],
            then=contract["then"],
            evidence_refs=[f"artifact:{receipt_slug}:tests_passed"] if artifact_verified else [],
        )
        report_path = write_runtime_receipt_json(
            repo_root,
            category="bdd_acceptance_skill",
            receipt_slug=receipt_slug,
            payload=receipt,
        )
        capabilities["bdd_acceptance_refs"] = [report_path, *receipt["evidence_refs"]]
        capabilities["bdd_acceptance_report_path"] = report_path
        capabilities["business_verified"] = receipt["business_verified"]
        capabilities["bdd_acceptance_skill_used"] = True
        capabilities["bdd_acceptance_skill_gate_passed"] = bool(receipt["business_verified"])
