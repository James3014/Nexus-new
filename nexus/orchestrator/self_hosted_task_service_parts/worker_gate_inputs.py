"""Inputs and honest outcomes for the pre-execution gates on the Gateway worker path (#2734).

On the P1 worker path (``_worker_context_materialization``) the planner selects
``pregate``, ``plan_quality_gate``, ``mempalace_gate`` and ``harness_preflight_sensor``, but
the capability context never carried their inputs, so all four refused with a missing-input
code and every receipt read ``INVOKED_NOT_SUCCESS`` (22/22 live tasks).

This module feeds each gate from the Task Card the worker already holds, only for that
gate's own call (no other executor sees the extra keys), and turns the remaining refusals
into an explicit ``NOT_APPLICABLE`` skip that names the missing inputs.  The gates are
record-only here: the caller declares them receipt-only, so their outcome never reaches the
worker prompt, and nothing in the worker path reads them to decide completion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

WORKER_PATH_GATES: tuple[str, ...] = (
    "pregate",
    "plan_quality_gate",
    "mempalace_gate",
    "harness_preflight_sensor",
)
# Declared receipt-only to the runtime: recorded in the sealed bundle and receipts, never
# rendered into the worker's model context (``mempalace`` is the executor-registry alias).
RECEIPT_ONLY_WORKER_GATES: tuple[str, ...] = (*WORKER_PATH_GATES, "mempalace")

NOT_APPLICABLE = "NOT_APPLICABLE"
MEMPALACE_TENANT = "nexus-worker-path"
MEMPALACE_ARTIFACT_TYPE = "worker_task_contract"
# Not run before the edit on this path: the Task Card verifiers run inside the task
# worktree (e.g. ``uv run`` creates a .venv there) and the post-candidate verifier already
# runs the same commands on the candidate.
PREGATE_NOT_APPLICABLE_REASON = "pre_edit_verifier_run_not_enabled_on_worker_path"
# Executor refusal codes that mean "an input was missing", with the inputs each names when
# the executor does not list them itself.
_MISSING_INPUT_CODES: dict[str, tuple[str, ...]] = {
    "EXPLICIT_VERIFY_COMMANDS_REQUIRED": ("verify_commands",),
    "VERIFY_COMMAND_WIRING_REQUIRED": ("verify_commands",),
    "PLAN_QUALITY_CONTEXT_REQUIRED": (),
    "MEMPALACE_ARTIFACT_CONTEXT_REQUIRED": (),
    # #2721 L-B: NEXUS_STATE_READ_ONLY froze the ledger; nothing to ingest or round-trip.
    "MEMPALACE_STATE_READ_ONLY": (),
}
# Inputs whose absence a gate does not list itself, as named in a NOT_APPLICABLE record.
_REQUIRED_INPUTS: dict[str, tuple[tuple[str, str], ...]] = {
    "mempalace_gate": (
        ("workspace_root", "NEXUS_STATE_ROOT"),
        ("mempalace_tenant_id", "mempalace_tenant_id"),
        ("mempalace_artifact", "mempalace_artifact"),
        ("mempalace_query", "mempalace_query"),
    ),
}

Invoker = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def worker_gate_inputs(
    *,
    planner: Mapping[str, Any],
    task_statement: str,
    allowed_files: Any,
    verifier_commands: Any,
    state_root: Any,
) -> dict[str, tuple[dict[str, Any], dict[str, str]]]:
    """Per gate: ``(context additions, provenance)``, derived only from the Task Card.

    An input that cannot be derived is left out, so its gate refuses and the refusal is
    recorded as ``NOT_APPLICABLE`` naming it (never invented data).
    """
    plan_payload = _mapping(planner.get("plan_payload"))
    planner_context = _mapping(planner.get("context"))
    planner_codeintel = _mapping(planner_context.get("codeintel"))
    files = _str_list(allowed_files)
    commands = _str_list(verifier_commands)
    statement = str(task_statement or "").strip()

    harness: dict[str, Any] = {}
    harness_prov: dict[str, str] = {}
    if commands:
        harness["verify_commands"] = commands
        harness_prov["verify_commands"] = "task_card.verifier_commands"
    harness["route"] = {"route_features": dict(_mapping(planner_context.get("route_features")))}
    harness_prov["route"] = "planner.context.route_features"
    task_type = planner_context.get("task_type")
    if isinstance(task_type, str) and task_type.strip():
        harness["task_type"] = task_type
        harness_prov["task_type"] = "planner.context.task_type"
    for key in ("selected_capabilities", "pending_capabilities"):
        listed = plan_payload.get(key)
        if isinstance(listed, (list, tuple)):
            harness[key] = [str(item) for item in listed]
            harness_prov[key] = f"planner.plan_payload.{key}"

    plan: dict[str, Any] = {}
    plan_prov: dict[str, str] = {}
    checks = {
        "task_statement_present": bool(statement),
        "allowed_files_present": bool(files),
        "verifier_commands_present": bool(commands),
    }
    if files:
        plan["intent_pass"] = bool(statement)
        plan_prov["intent_pass"] = "task_card:task_statement_present+allowed_files_present"
        plan["handoff_readiness"] = round(sum(checks.values()) / len(checks), 4)
        plan_prov["handoff_readiness"] = "task_card:fraction_of_checks(" + ",".join(checks) + ")"
        plan["target_files"] = list(files)
        plan["deliverables"] = list(files)
        plan_prov["target_files"] = "task_card.allowed_files"
        plan_prov["deliverables"] = "task_card.allowed_files"
        plan["steps"] = [f"edit {path}" for path in files] + [
            f"run verifier {cmd}" for cmd in commands
        ]
        plan_prov["steps"] = "task_card.procedure(edit_allowed_files,run_verifiers)"
    if files and commands:
        plan["acceptance_criteria"] = [f"verifier passes: {cmd}" for cmd in commands]
        plan_prov["acceptance_criteria"] = "task_card.verifier_commands"
        plan["impact_map"] = {
            "edges": [{"source": path, "covered_by": cmd} for path in files for cmd in commands]
        }
        plan_prov["impact_map"] = "task_card.allowed_files_x_verifier_commands"
    risk = planner_codeintel.get("risk_score")
    if isinstance(risk, (int, float)) and not isinstance(risk, bool):
        plan["risk_score"] = int(risk)
        plan_prov["risk_score"] = "planner.context.codeintel.risk_score"

    memory: dict[str, Any] = {}
    memory_prov: dict[str, str] = {}
    # Never the task worktree: the store must outlive it and must not land in the candidate.
    # Without a state root the gate gets an empty root (overriding the task worktree the
    # context carries), refuses, and is recorded NOT_APPLICABLE naming NEXUS_STATE_ROOT.
    memory["workspace_root"] = str(state_root) if state_root else ""
    memory_prov["workspace_root"] = "NEXUS_STATE_ROOT"
    if statement and files:
        artifact_id = (
            "worker-contract-"
            + _sha256(json.dumps([statement, files, commands], sort_keys=True))[:24]
        )
        memory["mempalace_tenant_id"] = MEMPALACE_TENANT
        memory["mempalace_artifact_type"] = MEMPALACE_ARTIFACT_TYPE
        memory["mempalace_artifact"] = {
            "artifact_id": artifact_id,
            "task_statement_sha256": _sha256(statement),
            "allowed_files": list(files),
            "verifier_commands_sha256": _sha256(json.dumps(commands)),
        }
        memory["mempalace_query"] = artifact_id
        for key in (
            "mempalace_tenant_id",
            "mempalace_artifact_type",
            "mempalace_artifact",
            "mempalace_query",
        ):
            memory_prov[key] = "task_card.contract_artifact"

    return {
        "harness_preflight_sensor": (harness, harness_prov),
        "plan_quality_gate": (plan, plan_prov),
        "mempalace_gate": (memory, memory_prov),
    }


def _executor_outcome(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(record.get("response")).get("outcome"))


def _not_applicable(
    name: str, task_id: str, reason: str, missing: list[str], detail: Mapping[str, Any]
) -> dict[str, Any]:
    skip_reason = f"{NOT_APPLICABLE}:{reason}"
    if missing:
        skip_reason += ":missing=" + ",".join(missing)
    return {
        "task_id": task_id,
        "invoked": False,
        "skipped": True,
        "skip_reason": skip_reason,
        "reason": skip_reason,
        "applicability": NOT_APPLICABLE,
        "missing_inputs": list(missing),
        "gate_passed": False,
        "outcome_contributed": False,
        "evidence_refs": [f"capability:{name}:{task_id}:not_applicable"],
        "physical_callable": f"worker_gate_inputs.not_applicable:{name}",
        "telemetry": {"token_usage": 0, "model_calls": 0},
        "stub": False,
        "response": {
            "status": "SKIPPED",
            "skip_reason": skip_reason,
            "capability": name,
            "outcome": {
                "semantic_status": NOT_APPLICABLE,
                "missing_inputs": list(missing),
                **dict(detail),
            },
        },
    }


def honest_gate_record(
    name: str,
    record: Mapping[str, Any],
    task_id: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The gate's record, with refusals and evaluated failures stated as what they are.

    * A missing-input refusal (the gate was invoked and returned the code) becomes an
      explicit ``NOT_APPLICABLE`` skip naming the inputs.
    * A gate that evaluated its inputs and failed gets ``blockers`` naming why, so the
      runtime records ``EVALUATED_REJECTED`` instead of an opaque ``INVOKED_NOT_SUCCESS``.
    """
    out = dict(record)
    outcome = _executor_outcome(out)
    error = str(outcome.get("error") or "")
    # Only a gate that actually ran and refused is a missing-input refusal; a crash whose
    # message happens to equal a refusal code (``invoked`` not True) keeps its failure record.
    if (
        out.get("invoked") is True
        and error in _MISSING_INPUT_CODES
        and str(out.get("status") or "") != "SUCCEEDED"
    ):
        missing = _str_list(outcome.get("missing_inputs")) or list(_MISSING_INPUT_CODES[error])
        if not missing and context is not None:
            missing = [
                label
                for key, label in _REQUIRED_INPUTS.get(name, ())
                if context.get(key) in (None, "", [], {})
            ]
        return _not_applicable(name, task_id, error, missing, {"executor_error": error})
    if (
        out.get("invoked") is True
        and str(out.get("status") or "") == "FAILED"
        and not error
        and not out.get("blockers")
    ):
        semantic = str(outcome.get("semantic_status") or "FAILED")
        reasons = _str_list(outcome.get("reasons")) or _str_list(
            _mapping(outcome.get("result")).get("missing_fields")
        )
        out["blockers"] = [f"{name}:{semantic.lower()}"] + [
            f"{name}:{item}" for item in reasons[:8]
        ]
    return out


def wrap_worker_gate_invokers(
    invokers: Mapping[str, Invoker],
    inputs: Mapping[str, tuple[Mapping[str, Any], Mapping[str, str]]],
) -> dict[str, Invoker]:
    """Return ``invokers`` with the four worker-path gates fed and honestly recorded."""
    wrapped: dict[str, Invoker] = dict(invokers)

    def pregate(context: Mapping[str, Any]) -> dict[str, Any]:
        return _not_applicable(
            "pregate",
            str(context.get("task_id") or ""),
            PREGATE_NOT_APPLICABLE_REASON,
            [],
            {"post_candidate_verifier_runs_same_commands": True},
        )

    if "pregate" in invokers:
        wrapped["pregate"] = pregate

    def bind(name: str, base: Invoker) -> Invoker:
        extra, provenance = inputs.get(name, ({}, {}))

        def invoke(context: Mapping[str, Any]) -> dict[str, Any]:
            task_id = str(context.get("task_id") or "")
            merged = {**dict(context), **dict(extra)}
            record = dict(base(merged))
            if provenance:
                record["input_provenance"] = {
                    **_mapping(record.get("input_provenance")),
                    **dict(provenance),
                }
            return honest_gate_record(name, record, task_id, merged)

        return invoke

    for name in ("plan_quality_gate", "mempalace_gate", "harness_preflight_sensor"):
        base = invokers.get(name)
        if callable(base):
            wrapped[name] = bind(name, base)
    return wrapped
