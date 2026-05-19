from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.contracts.context_budget import build_context_budget_receipt, validate_context_budget_receipt


CONTEXT_ASSEMBLY_CONTRACT_SCHEMA = "nexus.context_assembly_contract.v1"


@dataclass(frozen=True)
class ContextAssemblyContract:
    task_id: str
    receipt: Mapping[str, Any]
    context_policy: str = "preserve_l0_l1_hard_budget"
    schema: str = CONTEXT_ASSEMBLY_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        blockers = validate_context_assembly_contract(
            {
                "schema": self.schema,
                "task_id": self.task_id,
                "context_policy": self.context_policy,
                "receipt": dict(self.receipt),
            }
        )
        return {
            "schema": self.schema,
            "status": "PASS" if not blockers else "RETURN",
            "task_id": self.task_id,
            "context_policy": self.context_policy,
            "receipt": dict(self.receipt),
            "kept_source_count": len(self.receipt.get("kept_sources", []) or []),
            "dropped_source_count": len(self.receipt.get("dropped_sources", []) or []),
            "preserved_L0_L1": bool(self.receipt.get("preserved_L0_L1", False)),
            "blockers": blockers,
            "claim_boundary": [
                "Context assembly contracts select context under budget only.",
                "They do not decide route dispatch, runtime promotion, or public readiness.",
            ],
        }


def build_context_assembly_contract(
    *,
    task_id: str,
    sources: list[Mapping[str, Any]],
    token_budget: int,
    context_policy: str = "preserve_l0_l1_hard_budget",
) -> dict[str, Any]:
    receipt = build_context_budget_receipt(sources, token_budget=token_budget).to_dict()
    return ContextAssemblyContract(
        task_id=task_id,
        receipt=receipt,
        context_policy=context_policy,
    ).to_dict()


def validate_context_assembly_contract(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != CONTEXT_ASSEMBLY_CONTRACT_SCHEMA:
        blockers.append("invalid_context_assembly_schema")
    if not str(payload.get("task_id") or "").strip():
        blockers.append("missing_task_id")
    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        blockers.append("missing_context_budget_receipt")
        return sorted(set(blockers))
    blockers.extend(f"receipt:{item}" for item in validate_context_budget_receipt(receipt))
    if str(receipt.get("status") or "").upper() != "PASS":
        blockers.append("receipt_not_pass")
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("context_assembly_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("context_assembly_must_not_unlock_public_benchmark")
    return sorted(set(blockers))
