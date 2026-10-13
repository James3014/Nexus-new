"""Bind flow-level capability receipts to the UnifiedRuntime that actually executed them.

The research flow builds its row-level capability receipts from its own capability plan
plus usage-trace flags.  The online candidate, however, is produced by
``run_mainchain(with_nexus_armor=True)`` (via ``LLMCandidateGenerator``), whose
UnifiedRuntime runs its own selected capabilities and records each one as a stage
(``INVOKED`` / ``SKIPPED`` / ``SELECTED_NOT_EXECUTED``).  Before this projection the
UnifiedRuntime receipts were dropped at the flow report boundary, so a capability that
really ran (pregate, plan_quality_gate, acceptance_check, jit_validation, ...) was reported
as ``selected_without_invocation`` and a capability that was skipped carried no reason.

``project_unified_capability_stages`` keeps a bounded, claim-safe view of those stages;
``overlay_unified_capability_receipts`` applies it to the flow receipts.  The overlay never
invents an invocation: a receipt only becomes ``invoked`` when the runtime stage itself says
``invoked`` with evidence refs, and it carries that stage's ``claim_boundary``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

UNIFIED_RUNTIME_SELECTION_SOURCE = "unified_runtime"
UNIFIED_RUNTIME_NOT_SELECTED = "NOT_SELECTED"
PROJECTION_SCHEMA = "nexus_unified_capability_projection_v1"
_MAX_REFS = 6
_STATUS_RANK = {"INVOKED": 3, "SKIPPED": 2, "SELECTED_NOT_EXECUTED": 1}


def _stage_rows(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    caps = receipt.get("capabilities")
    if not isinstance(caps, list):
        return []
    return [
        item for item in caps if isinstance(item, Mapping) and str(item.get("name") or "").strip()
    ]


def _compact_stage(stage: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    boundary = (
        stage.get("claim_boundary") if isinstance(stage.get("claim_boundary"), Mapping) else {}
    )
    refs = [str(ref) for ref in (stage.get("evidence_refs") or []) if str(ref).strip()]
    invoked = bool(stage.get("invoked")) and str(stage.get("status") or "") == "INVOKED"
    return {
        "name": str(stage.get("name")),
        "status": str(stage.get("status") or ""),
        "invoked": invoked,
        "skip_reason": str(stage.get("skip_reason") or stage.get("reason") or ""),
        "gate_passed": bool(stage.get("gate_passed")) if invoked else False,
        "evidence_refs": refs[:_MAX_REFS],
        "simulated": bool(stage.get("simulated", True)),
        "claim_boundary": {
            "simulated": bool(boundary.get("simulated", True)),
            "claim_eligible": bool(boundary.get("claim_eligible", False)),
            "evidence_complete": bool(boundary.get("evidence_complete", False)),
        }
        if boundary
        else {},
        "trigger_source": str(stage.get("trigger_source") or ""),
        "runtime_task_id": task_id,
    }


def project_unified_capability_stages(receipts: Iterable[Any] | None) -> list[dict[str, Any]]:
    """Merge the capability stages of every UnifiedRuntime attempt into one row per name.

    An attempt that invoked the capability wins over one that skipped it; ties keep the
    latest attempt.  Non-mapping receipts are ignored.
    """

    merged: dict[str, dict[str, Any]] = {}
    for receipt in receipts or ():
        if not isinstance(receipt, Mapping):
            continue
        task_id = str(receipt.get("task_id") or "")
        for stage in _stage_rows(receipt):
            row = _compact_stage(stage, task_id=task_id)
            prev = merged.get(row["name"])
            if prev is None or _STATUS_RANK.get(row["status"], 0) >= _STATUS_RANK.get(
                prev["status"], 0
            ):
                row["attempts"] = int(prev.get("attempts", 0)) + 1 if prev else 1
                merged[row["name"]] = row
            else:
                prev["attempts"] = int(prev.get("attempts", 0)) + 1
    return [merged[name] for name in sorted(merged)]


def unified_receipts_from_meta(meta: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """UnifiedRuntime receipt(s) carried by a candidate-generator metadata mapping."""

    if not isinstance(meta, Mapping):
        return []
    receipt = meta.get("unified_runtime_receipt")
    return [receipt] if isinstance(receipt, Mapping) and receipt else []


def overlay_unified_capability_receipts(
    receipts: list[dict[str, Any]],
    stages: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Apply executed-runtime truth to flow receipts that were never marked invoked.

    * runtime stage invoked with evidence -> receipt invoked, refs/claim_boundary from the stage;
    * runtime stage skipped / not executed -> receipt keeps invoked=False and names the runtime
      reason (``unified_runtime:<STATUS>:<reason>``) instead of a bare
      ``selected_without_invocation``.
    * no runtime stage -> ``unified_runtime:NOT_SELECTED`` (the executing planner did not
      select it).
    Receipts that are already invoked are returned unchanged.
    """

    by_name = {
        str(stage.get("name")): stage for stage in stages or () if isinstance(stage, Mapping)
    }
    if not by_name:
        return receipts
    out: list[dict[str, Any]] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            out.append(receipt)
            continue
        stage = by_name.get(str(receipt.get("name") or ""))
        if bool(receipt.get("invoked")) or not bool(receipt.get("selected", True)):
            out.append(receipt)
            continue
        if stage is None:
            # Selected by the flow plan, but the executing runtime's planner never selected
            # it: say so instead of a bare "selected_without_invocation".
            updated = dict(receipt)
            updated["unified_runtime_status"] = UNIFIED_RUNTIME_NOT_SELECTED
            updated["failure_reason"] = f"unified_runtime:{UNIFIED_RUNTIME_NOT_SELECTED}"
            out.append(updated)
            continue
        updated = dict(receipt)
        updated["unified_runtime_status"] = str(stage.get("status") or "")
        refs = [str(ref) for ref in (stage.get("evidence_refs") or []) if str(ref).strip()]
        if bool(stage.get("invoked")) and refs:
            gate_passed = bool(stage.get("gate_passed"))
            updated.update({
                "invoked": True,
                "evidence_present": True,
                "evidence_refs": refs,
                "gate_passed": gate_passed,
                "outcome_contributed": False,
                "selection_source": UNIFIED_RUNTIME_SELECTION_SOURCE,
                "failure_reason": "" if gate_passed else "evidence_without_gate_pass",
            })
            if isinstance(stage.get("claim_boundary"), Mapping) and stage.get("claim_boundary"):
                updated["claim_boundary"] = dict(stage["claim_boundary"])
            if stage.get("trigger_source"):
                updated["trigger_source"] = str(stage["trigger_source"])
        else:
            reason = str(stage.get("skip_reason") or "")
            updated["failure_reason"] = f"unified_runtime:{stage.get('status') or 'UNKNOWN'}" + (
                f":{reason}" if reason else ""
            )
        out.append(updated)
    return out
