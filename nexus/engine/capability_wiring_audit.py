from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.engine.capability_planner import PENDING_EXECUTOR_CAPABILITIES, default_capability_nodes
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS
from nexus.engine.capability_receipt_policy import RECEIPT_BACKED_CAPABILITIES


HIGH_PRIORITY_CAPABILITIES = frozenset(
    {
        "acceptance_check",
        "artifact_gate",
        "autoreason",
        "belief",
        "benchmark",
        "claim_gate",
        "codeintel",
        "ddtree",
        "delivery_gate",
        "drone",
        "hyper",
        "jit_validation",
        "lancedb",
        "learn_mode",
        "learn_phase_slo",
        "memory",
        "mempalace_gate",
        "msa_router",
        "nightshift",
        "plan_quality_gate",
        "pregate",
        "repair_loop",
        "research",
        "sandbox",
        "semantic_searcher",
        "swarm",
        "swarm_quiet_moment",
        "ultra_review",
    }
)


def unused_reason_for_row(row: dict[str, Any]) -> str:
    """Classify why a selected capability did not prove runtime contribution."""
    if not row.get("selected", False):
        return "not_selected_by_signal"
    if not row.get("adapter_exists", False):
        return "selected_no_adapter"
    if row.get("pending_executor", False):
        return "pending_executor"
    if row.get("maturity") in {"legacy_alias", "deprecated"}:
        return "deprecated_alias"
    if not row.get("invoked", False):
        return "selected_no_runtime_payload"
    if not row.get("evidence_present", False):
        return "invoked_no_evidence"
    if not row.get("gate_passed", False):
        return "evidence_no_gate"
    if not row.get("outcome_contributed", False):
        return "gate_no_outcome"
    return ""


@dataclass(frozen=True)
class WiringAuditResult:
    rows: tuple[dict[str, Any], ...]
    high_priority_registry_only: tuple[str, ...]
    high_priority_missing_receipt_policy: tuple[str, ...]
    pending_executor_without_spec: tuple[str, ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "nexus_capability_wiring_audit_v1",
            "capability_count": len(self.rows),
            "rows": list(self.rows),
            "high_priority_registry_only": list(self.high_priority_registry_only),
            "high_priority_missing_receipt_policy": list(self.high_priority_missing_receipt_policy),
            "pending_executor_without_spec": list(self.pending_executor_without_spec),
            "passed": self.passed,
        }


def _adapter_payload_keys(adapter: Any) -> tuple[str, ...]:
    keys: list[str] = []
    for attr in ("evidence_keys", "used_keys"):
        keys.extend(str(item) for item in getattr(adapter, attr, ()) or ())
    gate_key = getattr(adapter, "gate_key", "")
    if gate_key:
        keys.append(str(gate_key))
    return tuple(dict.fromkeys(keys))


def _wiring_status(*, name: str, maturity: str, adapter_exists: bool, pending_executor: bool) -> str:
    if maturity == "legacy_alias":
        return "deprecated_alias"
    if not adapter_exists:
        return "registry_only"
    if pending_executor:
        return "receipt_backed_pending_executor"
    if maturity in {"experimental", "prototype"}:
        return "receipt_backed_shadow"
    return "runtime_backed"


def _pending_executor_spec(name: str, *, pending_executor: bool) -> dict[str, Any]:
    if not pending_executor:
        return {
            "required": False,
            "status": "not_applicable",
            "runtime_claim_allowed": True,
            "allowed_claim_scope": "runtime_backed",
        }
    return {
        "required": True,
        "status": "present",
        "runtime_claim_allowed": False,
        "allowed_claim_scope": "receipt_or_shadow_only",
        "must_prove_before_runtime_claim": [
            f"{name}_executor_control",
            f"{name}_receipt_adapter",
            f"{name}_public_safe_receipt",
            f"{name}_integration_smoke",
        ],
    }


def build_capability_wiring_audit() -> WiringAuditResult:
    nodes = default_capability_nodes()
    rows: list[dict[str, Any]] = []
    for name, node in sorted(nodes.items()):
        adapter = RECEIPT_ADAPTERS.get(name)
        pending = name in PENDING_EXECUTOR_CAPABILITIES
        status = _wiring_status(
            name=name,
            maturity=node.maturity,
            adapter_exists=bool(adapter),
            pending_executor=pending,
        )
        spec = _pending_executor_spec(name, pending_executor=pending)
        rows.append(
            {
                "name": name,
                "category": node.category,
                "phase_hooks": list(node.phase_hooks),
                "maturity": node.maturity,
                "node_exists": True,
                "adapter_exists": bool(adapter),
                "receipt_policy_backed": name in RECEIPT_BACKED_CAPABILITIES,
                "pending_executor": pending,
                "executor_spec": spec,
                "status": status,
                "runtime_payload_keys": list(_adapter_payload_keys(adapter)) if adapter else [],
                "high_priority": name in HIGH_PRIORITY_CAPABILITIES,
            }
        )

    high_priority_registry_only = tuple(
        row["name"]
        for row in rows
        if row["high_priority"] and row["status"] == "registry_only"
    )
    high_priority_missing_receipt_policy = tuple(
        row["name"]
        for row in rows
        if row["high_priority"] and not row["receipt_policy_backed"]
    )
    pending_executor_without_spec = tuple(
        row["name"]
        for row in rows
        if row["pending_executor"] and row["executor_spec"].get("status") != "present"
    )
    return WiringAuditResult(
        rows=tuple(rows),
        high_priority_registry_only=high_priority_registry_only,
        high_priority_missing_receipt_policy=high_priority_missing_receipt_policy,
        pending_executor_without_spec=pending_executor_without_spec,
        passed=not high_priority_registry_only
        and not high_priority_missing_receipt_policy
        and not pending_executor_without_spec,
    )
