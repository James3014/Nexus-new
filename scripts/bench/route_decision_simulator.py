from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from nexus.engine.learning_policy_loader import audit_route_cost_policy, route_cost_controls_for_task


@dataclass(frozen=True)
class RouteDecisionSimulation:
    task_id: str
    route_features: dict[str, Any]
    expected_capabilities: list[str]
    controls: dict[str, Any]
    hidden_verifier_required: bool
    supervised_bare_first_allowed: bool
    supervised_bare_first_block_reason: str
    runtime_classification: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": "nexus_route_decision_simulation.v1",
            "task_id": self.task_id,
            "route_features": dict(self.route_features),
            "expected_capabilities": list(self.expected_capabilities),
            "controls": dict(self.controls),
            "hidden_verifier_required": self.hidden_verifier_required,
            "supervised_bare_first_allowed": self.supervised_bare_first_allowed,
            "supervised_bare_first_block_reason": self.supervised_bare_first_block_reason,
            "runtime_classification": self.runtime_classification,
        }


def simulate_route_decision(
    project_root: Path,
    *,
    task_id: str,
    route_features: dict[str, Any],
    expected_capabilities: list[str] | tuple[str, ...] | None = None,
    budget: dict[str, Any] | None = None,
    hidden_verifier_required: bool = True,
) -> dict[str, Any]:
    """Replay route-cost policy decisions without running a model.

    This intentionally mirrors the supervised-bare admission gate in
    ``capability_ab_runner`` so policy changes can be preflighted before an
    expensive Flash/Pro run.
    """

    expected = _expected_capability_list(expected_capabilities)
    controls = route_cost_controls_for_task(
        project_root,
        task_id,
        budget=budget,
        route_features=route_features,
        expected_capabilities=expected,
    )
    allowed, reason = _supervised_bare_admission(controls, route_features, hidden_verifier_required)
    runtime_classification = (
        "nexus_supervised_bare_first_candidate"
        if allowed
        else "nexus_hardened_or_standard_candidate"
    )
    return RouteDecisionSimulation(
        task_id=str(task_id),
        route_features=dict(route_features),
        expected_capabilities=expected,
        controls=controls,
        hidden_verifier_required=hidden_verifier_required,
        supervised_bare_first_allowed=allowed,
        supervised_bare_first_block_reason=reason,
        runtime_classification=runtime_classification,
    ).to_jsonable()


def build_route_cost_preflight_gate(
    project_root: Path,
    *,
    tasks: list[dict[str, Any]],
    budget: dict[str, Any] | None = None,
    hidden_verifier_required: bool = True,
) -> dict[str, Any]:
    simulations = [
        simulate_route_decision(
            project_root,
            task_id=str(task.get("task_id") or task.get("id") or ""),
            route_features=dict(task.get("route_features") or task),
            expected_capabilities=_expected_capability_list(task.get("expected_capabilities")),
            budget=budget,
            hidden_verifier_required=hidden_verifier_required,
        )
        for task in tasks
    ]
    policy_audit = audit_route_cost_policy(project_root, budget)
    failures: list[dict[str, Any]] = []
    if not bool(policy_audit.get("passed", False)):
        failures.extend(policy_audit.get("failures", []) or [])
    for item in simulations:
        if (
            item.get("controls", {}).get("supervised_bare_first") is True
            and not hidden_verifier_required
        ):
            failures.append(
                {
                    "reason": "supervised_bare_first_requires_hidden_verifier",
                    "task_id": item.get("task_id"),
                }
            )
        if _is_broad_medium_supervised(item):
            failures.append(
                {
                    "reason": "broad_medium_supervised_bare_first",
                    "task_id": item.get("task_id"),
                    "policy_source": item.get("controls", {}).get("policy_source", ""),
                }
            )
    return {
        "schema_version": "nexus_route_cost_preflight_gate.v1",
        "passed": not failures,
        "policy_audit": policy_audit,
        "tasks_checked": len(simulations),
        "simulations": simulations,
        "failures": failures,
    }


def build_launch_readiness_gate(evidence_bundle_paths: list[Path]) -> dict[str, Any]:
    """Summarize whether current benchmark evidence is public-claim ready."""

    bundles: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for path in evidence_bundle_paths:
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append({"reason": "evidence_bundle_unreadable", "path": str(path), "detail": str(exc)})
            continue
        model_lock = bundle.get("model_lock", {})
        model_lock = model_lock if isinstance(model_lock, dict) else {}
        gate = bundle.get("public_claim_gate", {})
        gate = gate if isinstance(gate, dict) else {}
        checks = gate.get("checks", {})
        checks = checks if isinstance(checks, dict) else {}
        verdict = str(gate.get("verdict") or "")
        row_counts = bundle.get("row_counts", {})
        row_counts = row_counts if isinstance(row_counts, dict) else {}
        record = {
            "path": str(path),
            "model": str(model_lock.get("with_model_name") or model_lock.get("env_model_name") or ""),
            "same_model": bool(model_lock.get("same_model", False)),
            "public_claim_gate": verdict,
            "with_verified_rate": checks.get("with_semantic_verified_rate"),
            "without_verified_rate": checks.get("without_semantic_verified_rate"),
            "trust_mismatch_free": bool(checks.get("trust_mismatch_free", False)),
            "wall_cost_ratio": checks.get("wall_cost_ratio_with_over_without"),
            "median_paired_wall_cost_ratio": checks.get("median_paired_wall_cost_ratio_with_over_without"),
            "token_cost_ratio": checks.get("token_cost_ratio_with_over_without"),
            "row_count": bundle.get("row_count"),
            "row_counts": row_counts,
        }
        bundles.append(record)
        if verdict != "PASS":
            failures.append({"reason": "public_claim_gate_not_pass", "path": str(path), "verdict": verdict})
        if not record["same_model"]:
            failures.append({"reason": "same_model_required", "path": str(path)})
        if not record["trust_mismatch_free"]:
            failures.append({"reason": "trust_mismatch_not_free", "path": str(path)})
        if float(record.get("with_verified_rate") or 0.0) < 1.0:
            failures.append({"reason": "with_nexus_not_fully_verified", "path": str(path)})
        if float(record.get("with_verified_rate") or 0.0) <= float(record.get("without_verified_rate") or 0.0):
            failures.append({"reason": "no_verified_lift", "path": str(path)})
        wall_ratio = float(record.get("wall_cost_ratio") or 0.0)
        if wall_ratio > 1.8:
            warnings.append(
                {
                    "reason": "wall_cost_ratio_above_launch_target",
                    "path": str(path),
                    "wall_cost_ratio": wall_ratio,
                    "target": 1.8,
                }
            )
        token_ratio = float(record.get("token_cost_ratio") or 0.0)
        if token_ratio > 1.5:
            failures.append(
                {
                    "reason": "token_cost_ratio_above_public_gate",
                    "path": str(path),
                    "token_cost_ratio": token_ratio,
                    "target": 1.5,
                }
            )
    return {
        "schema_version": "nexus_launch_readiness_gate.v1",
        "passed": not failures,
        "bundles_checked": len(bundles),
        "bundles": bundles,
        "warnings": warnings,
        "failures": failures,
    }


def _supervised_bare_admission(
    controls: dict[str, Any],
    route_features: dict[str, Any],
    hidden_verifier_required: bool,
) -> tuple[bool, str]:
    if controls.get("supervised_bare_first") is not True:
        return False, "supervised_bare_first_not_selected"
    if not hidden_verifier_required:
        return False, "hidden_verifier_required"
    risk = str(route_features.get("local_reflex_risk_level") or "").strip().lower()
    sufficiency = str(route_features.get("local_reflex_bare_sufficiency") or "").strip().lower()
    if risk == "low" and sufficiency == "high":
        return True, ""
    if (
        risk == "medium"
        and sufficiency == "medium"
        and controls.get("allow_medium_risk_supervised_bare_first") is True
    ):
        return True, ""
    if controls.get("allow_high_risk_supervised_bare_first") is True:
        return True, ""
    return False, "local_reflex_risk_not_admitted"


def _expected_capability_list(value: Any) -> list[str]:
    if value in (None, "", False):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _is_broad_medium_supervised(simulation: dict[str, Any]) -> bool:
    controls = simulation.get("controls", {})
    controls = controls if isinstance(controls, dict) else {}
    features = simulation.get("route_features", {})
    features = features if isinstance(features, dict) else {}
    if controls.get("allow_medium_risk_supervised_bare_first") is not True:
        return False
    if str(features.get("fixture_kind") or "").strip():
        return False
    if str(features.get("local_reflex_risk_level") or "").strip().lower() == "low":
        return False
    return True
