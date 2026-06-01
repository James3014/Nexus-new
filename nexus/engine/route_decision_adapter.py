from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RouteRationaleCode(str, Enum):
    RESEARCH_ISOLATION_REQUIRED = "research_isolation_required"
    RECEIPT_LITE_ALLOWED = "receipt_lite_allowed"
    PREMODEL_RESCUE_ALLOWED = "premodel_rescue_allowed"
    MODEL_PATCH_REQUIRED = "model_patch_required"
    HIGH_RISK_GOVERNANCE_LOCKED = "high_risk_governance_locked"
    DELIVERY_GATE_OVERRIDE = "delivery_gate_override"
    EVIDENCE_INTEGRITY_REQUIRED = "evidence_integrity_required"
    COST_AWARE_LOCAL_FALLBACK = "cost_aware_local_fallback"


@dataclass(frozen=True)
class RouteDecisionRationale:
    """機器可讀的路由決策動機 (Machine-readable Rationale)"""
    primary_code: RouteRationaleCode
    supporting_codes: tuple[RouteRationaleCode, ...] = ()
    reason_text: str = ""
    evidence_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_code": self.primary_code.value,
            "supporting_codes": [c.value for c in self.supporting_codes],
            "reason_text": self.reason_text,
            "evidence_hints": list(self.evidence_hints),
        }


@dataclass(frozen=True)
class RouteDecisionReceipt:
    """Phase 6 路由決策收據，確保決策動機可審計"""
    schema_version: str = "route_decision_receipt.v1"
    task_id: str = ""
    selected_route: str = ""
    rationale: RouteDecisionRationale | None = None
    gate_passed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "selected_route": self.selected_route,
            "rationale": self.rationale.to_dict() if self.rationale else None,
            "gate_passed": self.gate_passed,
            "metadata": self.metadata,
        }
