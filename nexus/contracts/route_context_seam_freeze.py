from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


ROUTE_CONTEXT_SEAM_FREEZE_SCHEMA = "nexus.route_context_seam_freeze.v1"


@dataclass(frozen=True)
class RouteContextSeamFreeze:
    route_manifest_ref: str
    context_receipt_ref: str
    runtime_dispatch_changed: bool
    preserved_l0_l1: bool
    claim_read_model_status: str
    allowed_next_work: tuple[str, ...] = ()
    schema: str = ROUTE_CONTEXT_SEAM_FREEZE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "route_manifest_ref": self.route_manifest_ref,
            "context_receipt_ref": self.context_receipt_ref,
            "runtime_dispatch_changed": self.runtime_dispatch_changed,
            "preserved_l0_l1": self.preserved_l0_l1,
            "claim_read_model_status": self.claim_read_model_status,
            "allowed_next_work": list(self.allowed_next_work),
            "claim_boundary": [
                "This freeze contract protects route/context seams before refactor work.",
                "It does not approve runtime policy changes or public benchmark claims.",
            ],
        }
        payload["blockers"] = validate_route_context_seam_freeze(payload)
        payload["status"] = "PASS" if not payload["blockers"] else "RETURN"
        return payload


def build_route_context_seam_freeze(
    *,
    route_manifest_ref: str,
    context_receipt_ref: str,
    runtime_dispatch_changed: bool,
    preserved_l0_l1: bool,
    claim_read_model_status: str,
    allowed_next_work: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    return RouteContextSeamFreeze(
        route_manifest_ref=route_manifest_ref,
        context_receipt_ref=context_receipt_ref,
        runtime_dispatch_changed=runtime_dispatch_changed,
        preserved_l0_l1=preserved_l0_l1,
        claim_read_model_status=claim_read_model_status,
        allowed_next_work=tuple(str(item) for item in allowed_next_work if str(item).strip()),
    ).to_dict()


def validate_route_context_seam_freeze(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not str(payload.get("route_manifest_ref") or "").strip():
        blockers.append("missing_route_manifest_ref")
    if not str(payload.get("context_receipt_ref") or "").strip():
        blockers.append("missing_context_receipt_ref")
    if bool(payload.get("runtime_dispatch_changed", False)):
        blockers.append("runtime_dispatch_changed")
    if not bool(payload.get("preserved_l0_l1", False)):
        blockers.append("context_l0_l1_not_preserved")
    if str(payload.get("claim_read_model_status") or "").upper() != "PASS":
        blockers.append("claim_read_model_not_pass")
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("freeze_contract_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("freeze_contract_must_not_unlock_public_benchmark")
    return sorted(set(blockers))
