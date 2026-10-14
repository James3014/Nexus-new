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

Reporting truth (wiring plan PR-1):

* the flow receipt's ``receipt_base.claim_boundary`` was built for the not-invoked flow view
  (``simulated=true, receipt_present=false``).  When the overlay applies a runtime invocation it
  re-projects ``receipt_base`` from the runtime boundary, but only to ``simulated=false`` when the
  runtime attests ``simulated=false`` *and* the executor outcome does not declare a simulation
  (``SIMULATED_BY_DESIGN_EXECUTORS`` such as ``jit_validation`` always stay simulated);
* planner nodes with no executable body (control-plane references such as ``direct_mode`` and
  the ``research_route`` routing node) get an explicit ``NOT_EXECUTABLE:<class>`` receipt instead
  of ``selected_not_invoked`` / ``simulated``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from nexus.core.capability_executor_registry import SIMULATED_BY_DESIGN_EXECUTORS
from nexus.services.capability_registry import (
    NOT_EXECUTABLE_CAPABILITY_REASONS,
    NOT_EXECUTABLE_PREFIX,
)

UNIFIED_RUNTIME_SELECTION_SOURCE = "unified_runtime"
UNIFIED_RUNTIME_NOT_SELECTED = "NOT_SELECTED"
PROJECTION_SCHEMA = "nexus_unified_capability_projection_v1"
_MAX_REFS = 6
_STATUS_RANK = {"INVOKED": 3, "SKIPPED": 2, "SELECTED_NOT_EXECUTED": 1}
# Routing nodes: the planner satisfies the route itself; the body (a research lookup) runs only
# on a task signal.  Unless the runtime attests a real (simulated=false) invocation, the receipt
# says the node is not an executable capability.
NOT_EXECUTABLE_ROUTING_NODE = f"{NOT_EXECUTABLE_PREFIX}:control_plane_routing_node"
NOT_EXECUTABLE_ROUTING_NODES: dict[str, str] = {"research_route": NOT_EXECUTABLE_ROUTING_NODE}
_MAX_OUTCOME_DEPTH = 5


def not_executable_reason(name: str) -> str:
    """``NOT_EXECUTABLE:<class>`` for a planner node with no executable body, else ""."""

    key = str(name or "")
    return NOT_EXECUTABLE_CAPABILITY_REASONS.get(key) or NOT_EXECUTABLE_ROUTING_NODES.get(key, "")


def _declares_simulated(value: Any, depth: int = 0) -> bool:
    """True when an executor outcome (or a nested response/claim_boundary) says simulated."""

    if depth > _MAX_OUTCOME_DEPTH or not isinstance(value, Mapping):
        return False
    if value.get("simulated") is True or str(value.get("claim") or "").upper() == "SIMULATED":
        return True
    return any(
        _declares_simulated(value.get(key), depth + 1)
        for key in ("response", "outcome", "claim_boundary")
    )


def _outcome_simulated(receipt: Mapping[str, Any], name: str) -> bool:
    results = receipt.get("capability_results")
    if not isinstance(results, Mapping):
        return False
    return _declares_simulated(results.get(name))


def _evidence_index(receipt: Mapping[str, Any], name: str) -> set[str]:
    """Evidence ids the runtime receipt itself holds a record for (bundle entry or stage)."""

    index: set[str] = set()
    bundle = receipt.get("capability_evidence_bundle")
    entries = bundle.get("entries") if isinstance(bundle, Mapping) else None
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, Mapping) and entry.get("physical_callable"):
            index.update(str(ref) for ref in (entry.get("evidence_ids") or []) if str(ref).strip())
    results = receipt.get("capability_results")
    record = results.get(name) if isinstance(results, Mapping) else None
    if (
        isinstance(record, Mapping)
        and record.get("physical_callable")
        and isinstance(record.get("response"), Mapping)
        and record["response"]
    ):
        for key in ("evidence_refs", "evidence_ids"):
            index.update(str(ref) for ref in (record.get(key) or []) if str(ref).strip())
    return index


def _stage_rows(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    caps = receipt.get("capabilities")
    if not isinstance(caps, list):
        return []
    return [
        item for item in caps if isinstance(item, Mapping) and str(item.get("name") or "").strip()
    ]


def _compact_stage(
    stage: Mapping[str, Any],
    *,
    task_id: str,
    outcome_simulated: bool = False,
    evidence_index: set[str] | None = None,
) -> dict[str, Any]:
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
            **(
                {"receipt_present": bool(boundary.get("receipt_present"))}
                if "receipt_present" in boundary
                else {}
            ),
        }
        if boundary
        else {},
        "trigger_source": str(stage.get("trigger_source") or ""),
        "runtime_task_id": task_id,
        # Every ref must name an evidence record the runtime receipt holds (tighten-only).
        "refs_resolved": bool(refs) and all(ref in (evidence_index or set()) for ref in refs),
        "outcome_simulated": bool(
            outcome_simulated
            or any(_declares_simulated(stage.get(key)) for key in ("response", "outcome"))
        ),
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
            name = str(stage.get("name"))
            row = _compact_stage(
                stage,
                task_id=task_id,
                outcome_simulated=_outcome_simulated(receipt, name),
                evidence_index=_evidence_index(receipt, name),
            )
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


def runtime_attests_real(
    receipt: Mapping[str, Any], stage: Mapping[str, Any] | None = None
) -> bool:
    """True only when every runtime signal agrees the execution was real (tighten-only).

    All of these must hold, otherwise the receipt stays simulated:

    * the name is not in ``SIMULATED_BY_DESIGN_EXECUTORS``;
    * the stage's own ``simulated`` flag is exactly ``False`` (and the receipt's, if present);
    * the stage ``claim_boundary.simulated`` is exactly ``False`` and
      ``claim_boundary.receipt_present`` is exactly ``True`` (missing is not real);
    * the stage carries non-empty evidence refs and every ref resolves to an evidence record
      in the runtime receipt (``refs_resolved``: a bundle entry's ``evidence_ids`` or the
      capability's own stage record); a dangling or made-up ref is not real.

    ``claim_eligible`` is deliberately not required: it is false whenever the gate did not
    pass, which says nothing about whether the capability ran; the re-projected boundary
    keeps ``claim_eligible`` from the runtime, so no claim is made.
    * no executor outcome declares a simulation (``outcome_simulated``).
    """

    name = str(receipt.get("name") or "")
    if name in SIMULATED_BY_DESIGN_EXECUTORS:
        return False
    source = stage if isinstance(stage, Mapping) else receipt
    if source.get("simulated") is not False:
        return False
    if "simulated" in receipt and receipt.get("simulated") is not False:
        return False
    boundary = source.get("claim_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("simulated") is not False:
        return False
    if boundary.get("receipt_present") is not True:
        return False
    refs = [str(ref) for ref in (source.get("evidence_refs") or []) if str(ref).strip()]
    if not refs or source.get("refs_resolved") is not True:
        return False
    if bool(receipt.get("outcome_simulated")) or bool(source.get("outcome_simulated")):
        return False
    return True


def reproject_receipt_base_claim_boundary(
    receipt: dict[str, Any], stage: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Make ``receipt_base.claim_boundary`` agree with the runtime boundary (tighten-only).

    Applies to receipts the overlay marked invoked from a UnifiedRuntime stage.  When the
    runtime attests a real execution (``runtime_attests_real``) the stale flow-view
    ``receipt_base`` (``simulated=true, receipt_present=false``) is re-projected from the
    runtime boundary.  Otherwise both the top-level and the ``receipt_base`` boundary are set
    to ``simulated=true, claim_eligible=false`` so no reader can see a real claim.
    """

    if not bool(receipt.get("invoked")):
        return receipt
    updated = dict(receipt)
    refs = [str(ref) for ref in (updated.get("evidence_refs") or []) if str(ref).strip()]
    raw_rb = updated.get("receipt_base")
    old_rb: dict[str, Any] = dict(raw_rb) if isinstance(raw_rb, Mapping) else {}
    raw_cb = old_rb.get("claim_boundary")
    old_cb: dict[str, Any] = dict(raw_cb) if isinstance(raw_cb, Mapping) else {}
    top = updated.get("claim_boundary")
    top_cb: dict[str, Any] = dict(top) if isinstance(top, Mapping) else {}
    real = runtime_attests_real(updated, stage) and bool(refs)
    if not real:
        updated["claim_boundary"] = {
            **top_cb,
            "simulated": True,
            "claim_eligible": False,
            "evidence_complete": False,
        }
        if str(updated.get("name") or "") in SIMULATED_BY_DESIGN_EXECUTORS:
            updated["simulated_reason"] = "executor_simulated_by_design"
        elif bool(updated.get("outcome_simulated")) or (
            isinstance(stage, Mapping) and bool(stage.get("outcome_simulated"))
        ):
            updated["simulated_reason"] = "executor_outcome_simulated"
        if old_rb:
            updated["receipt_base"] = {
                **old_rb,
                "claim_boundary": {
                    **old_cb,
                    "simulated": True,
                    "claim_eligible": False,
                    "public_claim_allowed": False,
                    "evidence_complete": False,
                },
            }
        return updated
    if not old_rb:
        return updated
    try:
        from nexus_runtime.planning.evidence.claim_boundary import evaluate_claim_boundary
        from nexus_runtime.planning.evidence.receipt_base import project_child_receipt_base

        boundary = evaluate_claim_boundary(
            simulated=False,
            claim_eligible=bool(top_cb.get("claim_eligible", False)),
            receipt_present=True,
            model_calls=int(old_cb.get("model_calls") or 0),
        ).to_dict()
        name = str(updated.get("name") or "capability")
        gate_passed = bool(updated.get("gate_passed"))
        contributed = bool(updated.get("outcome_contributed"))
        chain = old_rb.get("consumption_chain")
        consumer = "engine"
        if isinstance(chain, list) and chain and isinstance(chain[0], Mapping):
            consumer = str(chain[0].get("consumer") or "engine")
        updated["receipt_base"] = project_child_receipt_base(
            source_world=str(old_rb.get("source_world") or "B"),
            source_component=str(old_rb.get("source_component") or "capability_receipt_engine"),
            task_id=str(old_rb.get("task_id") or ""),
            stage_payload={
                "name": name,
                "selected": True,
                "invoked": True,
                "gate_passed": gate_passed,
                "outcome_contributed": contributed,
                "executor_id": str(updated.get("executor_id") or ""),
                "selection_source": UNIFIED_RUNTIME_SELECTION_SOURCE,
            },
            stage_name=name,
            evidence_refs=refs,
            consumer=consumer,
            selected=True,
            injected=True,
            used=contributed,
            evidence_present=True,
            gate_passed=gate_passed,
            outcome_contributed=contributed,
            claim_boundary=boundary,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed, record why
        updated["receipt_base_reprojection_error"] = str(exc)[:200]
        updated["claim_boundary"] = {**top_cb, "simulated": True, "claim_eligible": False}
        updated["receipt_base"] = {
            **old_rb,
            "claim_boundary": {**old_cb, "simulated": True, "claim_eligible": False},
        }
    return updated


def not_executable_receipt(
    receipt: Mapping[str, Any], reason: str, *, runtime_reason: str = ""
) -> dict[str, Any]:
    """Explicit ``NOT_EXECUTABLE:<class>`` receipt: nothing ran, nothing is claimed."""

    updated = dict(receipt)
    updated.update({
        "invoked": False,
        "evidence_present": False,
        "evidence_refs": [],
        "gate_passed": False,
        "outcome_contributed": False,
        "execution_state": NOT_EXECUTABLE_PREFIX,
        "not_executable": True,
        "not_executable_reason": reason,
        "failure_reason": reason,
    })
    if runtime_reason:
        updated["unified_runtime_reason"] = runtime_reason
    if isinstance(updated.get("claim_boundary"), Mapping):
        updated["claim_boundary"] = {
            **dict(updated["claim_boundary"]),
            "simulated": True,
            "claim_eligible": False,
            "evidence_complete": False,
        }
    return updated


def _runtime_reason(stage: Mapping[str, Any] | None) -> str:
    if stage is None:
        return f"unified_runtime:{UNIFIED_RUNTIME_NOT_SELECTED}"
    reason = str(stage.get("skip_reason") or "")
    return f"unified_runtime:{stage.get('status') or 'UNKNOWN'}" + (f":{reason}" if reason else "")


def overlay_unified_capability_receipts(
    receipts: list[dict[str, Any]],
    stages: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Apply executed-runtime truth to flow receipts that were never marked invoked.

    * runtime stage invoked with evidence -> receipt invoked, refs/claim_boundary from the stage,
      ``receipt_base.claim_boundary`` re-projected tighten-only
      (``reproject_receipt_base_claim_boundary``);
    * runtime stage skipped / not executed -> receipt keeps invoked=False and names the runtime
      reason (``unified_runtime:<STATUS>:<reason>``) instead of a bare
      ``selected_without_invocation``.
    * no runtime stage -> ``unified_runtime:NOT_SELECTED`` (the executing planner did not
      select it).
    * planner node with no executable body (``not_executable_reason``) and no runtime-attested
      real invocation -> explicit ``NOT_EXECUTABLE:<class>`` receipt.
    Receipts that are already invoked keep their verdict; they only gain the runtime stage's
    status and gate result as ``unified_runtime_status`` / ``unified_runtime_gate_passed``.
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
        name = str(receipt.get("name") or "")
        stage = by_name.get(name)
        if not bool(receipt.get("selected", True)):
            out.append(receipt)
            continue
        if bool(receipt.get("invoked")):
            if stage is not None and bool(stage.get("invoked")):
                annotated = dict(receipt)
                annotated["unified_runtime_status"] = str(stage.get("status") or "")
                annotated["unified_runtime_gate_passed"] = bool(stage.get("gate_passed"))
                out.append(annotated)
            else:
                out.append(receipt)
            continue
        refs = (
            [str(ref) for ref in (stage.get("evidence_refs") or []) if str(ref).strip()]
            if stage is not None
            else []
        )
        runtime_invoked = stage is not None and bool(stage.get("invoked")) and bool(refs)
        ne_reason = not_executable_reason(name)
        if ne_reason and not (runtime_invoked and runtime_attests_real(receipt, stage)):
            updated = not_executable_receipt(
                receipt, ne_reason, runtime_reason=_runtime_reason(stage)
            )
            updated["unified_runtime_status"] = (
                str(stage.get("status") or "")
                if stage is not None
                else UNIFIED_RUNTIME_NOT_SELECTED
            )
            out.append(updated)
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
        if runtime_invoked:
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
            if bool(stage.get("outcome_simulated")):
                updated["outcome_simulated"] = True
            updated = reproject_receipt_base_claim_boundary(updated, stage)
        else:
            updated["failure_reason"] = _runtime_reason(stage)
        out.append(updated)
    return out
