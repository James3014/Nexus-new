from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.claim_evidence_read_model import validate_claim_evidence_read_model
from nexus.contracts.optimization_report import ProviderTokenCleanliness


SF_REPLACEMENT_CLEANLINESS_GATE_SCHEMA = "nexus_sf_replacement_cleanliness_gate.v1"
SF_REPLACEMENT_APPLY_PLAN_SCHEMA = "nexus_sf_replacement_apply_plan.v1"


@dataclass(frozen=True)
class SFReplacementDecision:
    capability: str
    current_skill: str
    challenger_skill: str
    decision: str
    reason: str
    token_delta: int | None
    wall_delta_sec: float | None
    blockers: tuple[str, ...] = ()
    schema: str = SF_REPLACEMENT_CLEANLINESS_GATE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "capability": self.capability,
            "current_skill": self.current_skill,
            "challenger_skill": self.challenger_skill,
            "decision": self.decision,
            "reason": self.reason,
            "token_delta": self.token_delta,
            "wall_delta_sec": self.wall_delta_sec,
            "blockers": list(self.blockers),
            "runtime_update_allowed": self.decision == "REPLACE" and not self.blockers,
            "public_benchmark_allowed": False,
        }


def build_sf_replacement_cleanliness_gate(
    row: Mapping[str, Any],
    *,
    require_same_provider_cleanliness_window: bool = True,
) -> dict[str, Any]:
    capability = str(row.get("capability") or row.get("capability_id") or "")
    current_skill = str(row.get("current_skill") or row.get("current_best") or "")
    challenger_skill = str(row.get("challenger_skill") or row.get("challenger") or "")
    token_delta = _int_or_none(row.get("token_delta"))
    wall_delta = _float_or_none(row.get("wall_delta_sec"))
    blockers = _replacement_blockers(row, require_same_provider_cleanliness_window=require_same_provider_cleanliness_window)

    if blockers:
        decision = "HOLD"
        reason = _primary_blocker_reason(blockers)
    elif token_delta is not None and wall_delta is not None and token_delta < 0 and wall_delta < 0:
        decision = "REPLACE"
        reason = "challenger_receipt_clean_and_better_on_token_and_wall"
    else:
        decision = "NO_REPLACEMENT"
        reason = "challenger_not_better_on_both_token_and_wall"

    return SFReplacementDecision(
        capability=capability,
        current_skill=current_skill,
        challenger_skill=challenger_skill,
        decision=decision,
        reason=reason,
        token_delta=token_delta,
        wall_delta_sec=wall_delta,
        blockers=tuple(blockers),
    ).to_dict()


def build_sf_replacement_cleanliness_manifest(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    decisions = [build_sf_replacement_cleanliness_gate(row) for row in rows]
    return {
        "schema": "nexus_sf_replacement_cleanliness_manifest.v1",
        "status": "PASS" if not any(item["blockers"] for item in decisions) else "RETURN",
        "summary": {
            "decision_count": len(decisions),
            "replace_count": sum(1 for item in decisions if item["decision"] == "REPLACE"),
            "hold_count": sum(1 for item in decisions if item["decision"] == "HOLD"),
            "no_replacement_count": sum(1 for item in decisions if item["decision"] == "NO_REPLACEMENT"),
            "runtime_update_allowed": bool(decisions) and all(
                item["decision"] in {"REPLACE", "NO_REPLACEMENT"} for item in decisions
            ),
            "public_benchmark_allowed": False,
        },
        "decisions": decisions,
        "claim_boundary": [
            "Replacement cleanliness is an internal SF apply-review gate.",
            "It can approve replacement candidates for runtime review but cannot unlock public benchmark claims.",
        ],
    }


def build_sf_replacement_apply_plan(
    cleanliness_manifest: Mapping[str, Any],
    *,
    allow_runtime_apply: bool = False,
) -> dict[str, Any]:
    decisions = list(cleanliness_manifest.get("decisions", []) or [])
    items = [_apply_item(item, allow_runtime_apply=allow_runtime_apply) for item in decisions if isinstance(item, Mapping)]
    blockers = sorted(
        {
            blocker
            for item in items
            for blocker in item["blockers"]
        }
    )
    if str(cleanliness_manifest.get("status") or "RETURN") != "PASS":
        blockers.append("cleanliness_manifest_not_pass")
    return {
        "schema": SF_REPLACEMENT_APPLY_PLAN_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "allow_runtime_apply": bool(allow_runtime_apply),
        "apply_allowed": bool(allow_runtime_apply) and not blockers,
        "replacement_count": sum(1 for item in items if item["action"] == "APPLY_REPLACEMENT"),
        "hold_count": sum(1 for item in items if item["action"] == "HOLD"),
        "no_replacement_count": sum(1 for item in items if item["action"] == "KEEP_CURRENT"),
        "items": items,
        "blockers": sorted(set(blockers)),
        "runtime_update_allowed": bool(allow_runtime_apply) and not blockers,
        "public_benchmark_allowed": False,
        "claim_boundary": [
            "SF apply plans are runtime-apply review artifacts only.",
            "They do not unlock public benchmark claims or bypass post-apply smoke.",
        ],
    }


def _replacement_blockers(
    row: Mapping[str, Any],
    *,
    require_same_provider_cleanliness_window: bool,
) -> list[str]:
    blockers: list[str] = []
    if str(row.get("status") or "PASS") not in {"PASS", "SUCCESS"}:
        blockers.append("comparison_row_not_pass")
    if not bool(row.get("current_runtime_receipt_chain_ok", True)):
        blockers.append("current_runtime_receipt_incomplete")
    if not bool(row.get("challenger_runtime_receipt_chain_ok", row.get("runtime_receipt_chain_ok", False))):
        blockers.append("challenger_runtime_receipt_incomplete")
    if not bool(row.get("challenger_effective", True)):
        blockers.append("challenger_not_effective")
    blockers.extend(_read_model_blockers(row.get("read_model")))
    if require_same_provider_cleanliness_window and not bool(row.get("same_provider_cleanliness_window", True)):
        blockers.append("blocked_by_cleanliness_window")
    current_clean = _provider_cleanliness(row.get("current_provider_token_cleanliness", ProviderTokenCleanliness.MEASURED.value))
    challenger_clean = _provider_cleanliness(
        row.get("challenger_provider_token_cleanliness", row.get("provider_token_cleanliness", ProviderTokenCleanliness.MEASURED.value))
    )
    if current_clean in {ProviderTokenCleanliness.MISSING, ProviderTokenCleanliness.ESTIMATED}:
        blockers.append("blocked_by_missing_cost_truth:current")
    if challenger_clean in {ProviderTokenCleanliness.MISSING, ProviderTokenCleanliness.ESTIMATED}:
        blockers.append("blocked_by_missing_cost_truth:challenger")
    if _int_or_none(row.get("token_delta")) is None:
        blockers.append("missing_token_delta")
    if _float_or_none(row.get("wall_delta_sec")) is None:
        blockers.append("missing_wall_delta_sec")
    return sorted(set(blockers))


def _apply_item(decision: Mapping[str, Any], *, allow_runtime_apply: bool) -> dict[str, Any]:
    blockers = [str(item) for item in decision.get("blockers", []) or []]
    action = "HOLD"
    if blockers:
        action = "HOLD"
    elif decision.get("decision") == "REPLACE":
        action = "APPLY_REPLACEMENT" if allow_runtime_apply else "REVIEW_REPLACEMENT"
        if not allow_runtime_apply:
            blockers.append("runtime_apply_not_authorized")
    elif decision.get("decision") == "NO_REPLACEMENT":
        action = "KEEP_CURRENT"
    else:
        blockers.append("decision_not_apply_ready")
    return {
        "capability": str(decision.get("capability") or ""),
        "current_skill": str(decision.get("current_skill") or ""),
        "challenger_skill": str(decision.get("challenger_skill") or ""),
        "decision": str(decision.get("decision") or ""),
        "action": action,
        "blockers": sorted(set(blockers)),
    }


def _read_model_blockers(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return ["read_model_invalid"]
    blockers = [f"read_model:{item}" for item in validate_claim_evidence_read_model(raw)]
    if str(raw.get("status") or "RETURN") != "PASS":
        blockers.append("read_model_not_pass")
    if bool(raw.get("runtime_update_allowed", False)):
        blockers.append("read_model_runtime_update_attempt")
    if bool(raw.get("public_benchmark_allowed", False)):
        blockers.append("read_model_public_benchmark_attempt")
    return blockers


def _primary_blocker_reason(blockers: list[str]) -> str:
    for prefix in (
        "blocked_by_cleanliness_window",
        "blocked_by_missing_cost_truth",
        "challenger_runtime_receipt_incomplete",
        "current_runtime_receipt_incomplete",
        "challenger_not_effective",
    ):
        for blocker in blockers:
            if blocker.startswith(prefix):
                return prefix
    return blockers[0] if blockers else ""


def _provider_cleanliness(value: ProviderTokenCleanliness | str | Any) -> ProviderTokenCleanliness:
    if isinstance(value, ProviderTokenCleanliness):
        return value
    return ProviderTokenCleanliness(str(value))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
