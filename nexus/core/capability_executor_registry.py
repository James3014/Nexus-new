from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.contracts.fail_closed import Decision, decide
from nexus.core.belief_contracts import CapabilityExecutionPlan, CapabilityReceipt
from nexus.core.layer_ports import registered_ports, resolve_port

logger = logging.getLogger(__name__)

CapabilityExecutor = Callable[[CapabilityExecutionPlan, str], CapabilityReceipt]


# Import/construct alone is never real execution (P4).
_SHALLOW_SUCCESS_KEYS = frozenset(
    {
        "class_instantiated",
        "function_found",
        "symbol_resolved",
        "resolve_service",
        "resolve_module",
        "resolve_providers",
    }
)


_SHALLOW_ACTIONS = frozenset(
    {
        "resolve_service",
        "resolve_module",
        "resolve_providers",
        "construct",
        "resolve",
        # Probe/fixture/gate-preflight alone is not production execution (P1).
        "should_run",
        "health_check",
        "bind",
        "cleanup",
        "hash_fallback",
        "import_success",
        "probe",
        "fixture",
        "deterministic_confidence_probe",
    }
)


def _is_shallow_outcome(outcome: Mapping[str, Any] | None) -> bool:
    """True when outcome only proves import/construct/probe, not a physical action."""
    if not isinstance(outcome, Mapping) or not outcome:
        return False
    if outcome.get("error") and not outcome.get("action"):
        return False
    action = str(outcome.get("action") or "")
    if action in _SHALLOW_ACTIONS:
        return True
    # Empty cleanup is not production execution
    if action == "cleanup" and not outcome.get("result"):
        return True
    if action:
        return False
    return any(bool(outcome.get(k)) for k in _SHALLOW_SUCCESS_KEYS)


# Explicit success / failure semantic_status values (structured field, not string scan).
_SEMANTIC_SUCCESS_STATUSES = frozenset(
    {
        "VERIFIED",
        "ACCEPTED",
        "COMPLETE",
        "COMPLETED",
        "PASSED",
        "PASS",
        "SUCCEEDED",
        "SUCCESS",
        "OK",
    }
)
_SEMANTIC_FAIL_STATUSES = frozenset(
    {
        "UNVERIFIED",
        "BLOCKED",
        "FAILED",
        "ERROR",
        "FAIL",
        "REJECTED",
        "INCOMPLETE",
    }
)

# Executors whose body is a self-declared mock on every path (the mask in
# jit_tool_injector.py is a keyword mock; the blocked path never masks anything).
# Their receipts stay simulated even when a runtime boundary says otherwise.
SIMULATED_BY_DESIGN_EXECUTORS = frozenset({"jit_validation"})


def _structured_fail_in_value(value: Any, *, depth: int = 0, max_depth: int = 4) -> bool:
    """Bounded recursive inspection of Mapping/list for structured fail fields.

    Does **not** free-text scan strings or parse arbitrary ``result`` prose.
    """
    if depth > max_depth:
        return False
    if isinstance(value, Mapping):
        err = value.get("error")
        if err not in (None, "", [], {}):
            return True
        semantic = str(value.get("semantic_status") or "").strip().upper()
        if semantic in _SEMANTIC_FAIL_STATUSES:
            return True
        if semantic and semantic not in _SEMANTIC_SUCCESS_STATUSES and "semantic_status" in value:
            # Present but not an explicit success status.
            return True
        if value.get("passed") is False:
            return True
        if value.get("ok") is False:
            return True
        for v in value.values():
            if _structured_fail_in_value(v, depth=depth + 1, max_depth=max_depth):
                return True
        return False
    if isinstance(value, (list, tuple)):
        for item in list(value)[:32]:
            if _structured_fail_in_value(item, depth=depth + 1, max_depth=max_depth):
                return True
        return False
    return False


def apply_semantic_success_guard(
    *,
    invoked: bool,
    gate_passed: bool,
    outcome: Mapping[str, Any] | None,
) -> tuple[bool, bool, dict[str, Any]]:
    """Fail closed when structured outcome fields contradict success.

    Bounded recursive inspection of Mapping/list for:
    - non-empty ``error``
    - ``semantic_status`` in UNVERIFIED/BLOCKED/FAILED/ERROR
    - ``passed is False`` / ``ok is False``
    Free-text / arbitrary ``result`` string parsing is not used.
    """
    out: dict[str, Any] = dict(outcome or {})
    if not invoked:
        return False, False, out

    if _structured_fail_in_value(out):
        return invoked, False, out

    return invoked, bool(gate_passed), out


def _honest_structural_telemetries(
    wall_time_ms: int | None,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build telemetries without inventing measured wall/tokens (RC-3).

    - wall_time_ms is None → telemetry_source=unavailable, claimable=false
    - wall_time_ms provided (real elapsed) → measured with that value (may be 0)
    Never default wall to 1 or mark measured without a real wall sample.
    """
    if wall_time_ms is None:
        tel: dict[str, Any] = {
            "telemetry_source": "unavailable",
            "wall_time_ms": None,
            "token_usage": None,
            "provider_costs": None,
            "overhead_ms": None,
            "model_calls": 0,
            "claimable": False,
            "missing_evidence_reason": "telemetry_unavailable",
        }
    else:
        try:
            wall = int(wall_time_ms)
        except (TypeError, ValueError):
            wall = None
        if wall is None or wall < 0:
            tel = {
                "telemetry_source": "unavailable",
                "wall_time_ms": None,
                "token_usage": None,
                "provider_costs": None,
                "overhead_ms": None,
                "model_calls": 0,
                "claimable": False,
                "missing_evidence_reason": "telemetry_unavailable",
            }
        else:
            # Structural capability: model_calls=0 is allowed; wall is real elapsed.
            tel = {
                "telemetry_source": "measured",
                "wall_time_ms": wall,
                "overhead_ms": wall,
                "token_usage": 0,
                "provider_costs": 0.0,
                "model_calls": 0,
                "claimable": False,
            }
    if extra:
        tel.update(extra)
    # Fail-closed: cannot claim measured without a concrete wall sample
    if tel.get("telemetry_source") == "measured" and tel.get("wall_time_ms") is None:
        tel["telemetry_source"] = "unavailable"
        tel["claimable"] = False
        tel["missing_evidence_reason"] = "telemetry_unavailable"
    return tel


# #1869: registry receipts whose gate_passed is a constant/default True. ``_make_receipt`` callers
# must pass gate_passed explicitly (tests/core/test_registry_gate_passed_inventory.py scans this).
# NON-CLAIM: "the physical call ran without a structured failure" (execution health). It feeds
# router terminal_outcome / learning telemetry only and is NOT claim evidence; claim gates
# (claim_gate/artifact_gate) are sealed by router (is_claimable) and artifact_gate below is bound to
# the verifier-artifact/source-hash helper.
NON_CLAIM_EXECUTION_HEALTH_RECEIPTS: frozenset[str] = frozenset(
    {
        "codeintel",
        "lancedb",
        "belief",
        "memory",
        "semantic_searcher",
        "semantic_failure_sensor",
        "prompt_compression",
    }
)
BOUND_CLAIM_GATE_RECEIPTS: frozenset[str] = frozenset({"artifact_gate"})


def _make_receipt(
    cap_name: str,
    plan: CapabilityExecutionPlan,
    *,
    invoked: bool = True,
    gate_passed: bool = True,
    outcome: dict[str, Any] | None = None,
    wall_time_ms: int | None = None,
    skill_receipts: list | None = None,
    **extra_telemetry: Any,
) -> CapabilityReceipt:
    out: dict[str, Any] = dict(outcome or {})
    # Fail closed: import/construct ≠ executed (never claim real success).
    if invoked and _is_shallow_outcome(out):
        invoked = False
        gate_passed = False
        out = {
            **out,
            "error": "import_construct_not_execution",
            "detail": "physical method call required; import/construct alone is insufficient",
        }
    # Structured semantic-success guard (error / semantic_status / passed / ok).
    invoked, gate_passed, out = apply_semantic_success_guard(
        invoked=invoked,
        gate_passed=gate_passed,
        outcome=out,
    )
    if not out:
        stamp = (
            COUNTED_FIXED_TIMESTAMP
            if _counted_learn_lane()
            else datetime.now(timezone.utc).isoformat()
        )
        out = {"phase_executed": "", "timestamp": stamp}
    evidence_id = f"ev_cap_{cap_name}_{os.urandom(4).hex()}"
    return CapabilityReceipt(
        capability_name=cap_name,
        selected=True,
        invoked=invoked,
        evidence_id=evidence_id,
        gate_passed=gate_passed,
        outcome=out,
        skill_receipts=skill_receipts or [],
        telemetries=_honest_structural_telemetries(wall_time_ms, extra=dict(extra_telemetry or {})),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _try_import_class(module_path: str, class_name: str) -> type | None:
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name, None)
    except Exception as exc:
        logger.debug("executor_registry: cannot import %s.%s: %s", module_path, class_name, exc)
        return None


def _provider_auth_allowed(*, require_external: bool = False, require_local_model: bool = False) -> bool:
    """Fail-closed provider/model authorization gate (no Gemini/API-key substitution)."""
    if require_external and os.environ.get("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "").strip() != "1":
        return False
    if require_local_model and os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "").strip() != "1":
        return False
    return True


def _structured_outcome(
    *,
    action: str,
    semantic_status: str,
    evidence_refs: list[str] | None = None,
    result: Any = None,
    error: str | None = None,
    control_plane: bool = False,
    legacy_alias_of: str | None = None,
    contamination_signal: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Bounded structured mapping for executor outcomes (not str(result) theater).

    ``contamination_signal`` (P-CONTAM-01, record-only) is emitted only when given,
    so receipts without a signal keep their shape.
    """
    out: dict[str, Any] = {
        "action": action,
        "semantic_status": semantic_status,
        "evidence_refs": list(evidence_refs or []),
    }
    if error is not None:
        out["error"] = str(error)[:300]
    if result is not None:
        if isinstance(result, Mapping):
            # Keep a compact nested mapping (no free-form dump).
            compact: dict[str, Any] = {}
            for k, v in list(result.items())[:24]:
                if isinstance(v, (str, int, float, bool)) or v is None:
                    compact[str(k)] = v if not isinstance(v, str) else v[:200]
                elif isinstance(v, (list, tuple)):
                    compact[str(k)] = list(v)[:8]
                elif isinstance(v, Mapping):
                    compact[str(k)] = {
                        str(sk): (sv if not isinstance(sv, str) else sv[:120])
                        for sk, sv in list(v.items())[:8]
                    }
                else:
                    compact[str(k)] = type(v).__name__
            out["result"] = compact
        else:
            out["result_type"] = type(result).__name__
            out["result_repr"] = str(result)[:200]
    if control_plane:
        out["control_plane_reference"] = True
        out["not_production_executor_f"] = True
    if legacy_alias_of:
        out["legacy_alias_of"] = legacy_alias_of
        out["not_independent_executor"] = True
    out.update(extra)
    if contamination_signal is not None:
        out["contamination_signal"] = dict(contamination_signal)
    return out


def _auth_blocked_receipt(
    cap_name: str,
    plan: CapabilityExecutionPlan,
    *,
    wall_time_ms: int,
    reason: str = "BLOCKED_EXTERNAL_AUTH",
) -> CapabilityReceipt:
    return _make_receipt(
        cap_name,
        plan,
        invoked=True,
        gate_passed=False,
        wall_time_ms=wall_time_ms,
        outcome=_structured_outcome(
            action="auth_gate",
            semantic_status="BLOCKED",
            error=reason,
            evidence_refs=[f"ev_auth_block_{cap_name}"],
            auth_required=True,
        ),
    )


def _archived_receipt(
    cap_name: str, plan: CapabilityExecutionPlan, task_desc: str = ""
) -> CapabilityReceipt:
    """Receipt-visible fail-closed result for a capability archived 2026-10-12 or 2026-10-13."""
    from nexus.services.capability_registry import ARCHIVED_CAPABILITY_REASONS

    reason = ARCHIVED_CAPABILITY_REASONS[cap_name]
    return _make_receipt(
        cap_name,
        plan,
        invoked=False,
        gate_passed=False,
        wall_time_ms=0,
        outcome=_structured_outcome(
            action="archived",
            semantic_status="BLOCKED",
            error=reason,
            evidence_refs=[f"ev_archived_{cap_name}_{plan.task_id}"],
            skip_reason=reason,
            archived=True,
            task_hint=str(task_desc or "")[:80],
        ),
    )


def _resolve_run_root(plan: CapabilityExecutionPlan) -> tuple[Path, Path, str]:
    constraints = plan.constraints or {}
    project_root = Path(str(constraints.get("project_root", ".")))
    run_id = str(constraints.get("run_id") or plan.task_id)
    raw = constraints.get("run_root") or constraints.get("runtime_root")
    if raw:
        run_root = Path(str(raw))
    else:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", run_id)[:120]
        run_root = project_root / ".nexus" / "runtime" / safe_id
    return project_root, run_root, run_id


def _resolve_learn_store(plan: CapabilityExecutionPlan) -> tuple[Path, Path, str]:
    """Project-level learn store: the directory the ``learn:*`` CLI reads.

    ``LearnModeService(<project>)`` keeps claims and the phase ledger under
    ``<project>/.nexus``.  The project is the runtime-supplied ``workspace_root`` (else
    ``project_root``, else the cwd).  An explicit ``run_root`` / ``runtime_root`` constraint
    still isolates the run (tests); without one the executor must not invent a fresh,
    empty per-task directory, because the report would then never see the project data.
    """
    constraints = plan.constraints or {}
    raw_root = str(
        constraints.get("workspace_root") or constraints.get("project_root") or ""
    ).strip()
    project_root = Path(raw_root).expanduser().resolve() if raw_root else Path.cwd().resolve()
    run_id = str(constraints.get("run_id") or plan.task_id)
    raw_run = constraints.get("run_root") or constraints.get("runtime_root")
    run_root = Path(str(raw_run)) if raw_run else project_root
    return project_root, run_root, run_id


def _assert_outputs_in_run_root(output_paths: list[Path], run_root: Path) -> None:
    rr = run_root.resolve()
    for p in output_paths:
        if not str(p.resolve()).startswith(str(rr)):
            raise RuntimeError(f"output path {p} resolves outside run_root {rr}")


# ─── S-phase ──────────────────────────────────────────────────────────────────

def _exec_mempalace(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.services.mem_palace", "MemPalace")
    if cls is None:
        return _make_receipt("mempalace", plan, invoked=False, gate_passed=False,
                             outcome={"error": "MemPalace class not importable"})
    try:
        constraints = dict(plan.constraints or {})
        root = str(constraints.get("workspace_root") or "").strip()
        tenant_id = str(constraints.get("mempalace_tenant_id") or "").strip()
        artifact_type = str(
            constraints.get("mempalace_artifact_type") or "capability_evidence"
        ).strip()
        artifact = constraints.get("mempalace_artifact")
        artifact_map = dict(artifact) if isinstance(artifact, Mapping) else {}
        artifact_id = str(artifact_map.get("artifact_id") or "").strip()
        query = str(constraints.get("mempalace_query") or artifact_id).strip()
        if not root or not tenant_id or not artifact_id or not query:
            return _make_receipt(
                "mempalace",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="ingest+retrieve+verify",
                    semantic_status="BLOCKED",
                    error="MEMPALACE_ARTIFACT_CONTEXT_REQUIRED",
                    evidence_refs=[f"ev_mempalace_blocked_{plan.task_id}"],
                    ingest_performed=False,
                    retrieve_performed=False,
                    verification_passed=False,
                ),
            )
        inst = cls(project_root=root)
        stored = inst.ingest_to_shards(
            tenant_id=tenant_id,
            artifact_type=artifact_type,
            data=artifact_map,
        )
        retrieved = inst.retrieve_from_shards(
            tenant_id=tenant_id,
            query=query,
            artifact_type=artifact_type,
            limit=5,
        )
        verified = inst.verify(retrieved)
        roundtrip_match = any(
            str((item.get("core") or {}).get("artifact_id") or "") == artifact_id
            for item in verified
            if isinstance(item, Mapping)
        )
        ok = bool(stored) and bool(retrieved) and roundtrip_match
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "mempalace",
            plan,
            gate_passed=ok,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="ingest+retrieve+verify",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_mempalace_roundtrip_{plan.task_id}"],
                result={
                    "artifact_id": artifact_id,
                    "stored_aaak_id": str((stored or {}).get("aaak_id") or ""),
                    "retrieved_count": len(retrieved),
                },
                ingest_performed=bool(stored),
                retrieve_performed=True,
                verification_passed=roundtrip_match,
                retrieved_count=len(retrieved),
                physical_callable=(
                    "nexus.services.mem_palace.MemPalace."
                    "ingest_to_shards+retrieve_from_shards+verify"
                ),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt("mempalace", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
                             outcome={"error": str(exc)})


def _exec_nightshift_runner_service(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not (
        _provider_auth_allowed(require_local_model=True)
        or _provider_auth_allowed(require_external=True)
    ):
        return _auth_blocked_receipt(
            "nightshift_runner_service",
            plan,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            reason="BLOCKED_EXTERNAL_AUTH:nightshift_model",
        )
    try:
        AutoResearchNightShift, compute_time_budget = (
            resolve_port("nightshift.AutoResearchNightShift"),
            resolve_port("nightshift.compute_time_budget"),
        )

        constraints = dict(plan.constraints or {})
        root = Path(
            str(constraints.get("workspace_root") or Path(__file__).resolve().parents[2])
        ).expanduser().resolve()
        target_file = str(constraints.get("nightshift_target_file") or "README.md")
        budget = int(compute_time_budget(requested_sec=60, buffer_ratio=0.1))
        inst = AutoResearchNightShift(
            task=str(task_desc or plan.task_id),
            max_rounds=1,
            budget_min=1,
            target_file=target_file,
            project_root=root,
        )
        if not hasattr(inst, "run") or not callable(inst.run):
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "nightshift_runner_service",
                plan,
                invoked=False,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome=_structured_outcome(
                    action="compute_time_budget",
                    semantic_status="FAILED",
                    error="AutoResearchNightShift.run missing",
                ),
            )
        result = inst.run()
        elapsed = int((time.monotonic() - start) * 1000)
        result_map = dict(result) if isinstance(result, Mapping) else {}
        best_score = float(result_map.get("best_score") or inst.best_score or 0.0)
        rounds_attempted = len(inst.trace_log)
        report_path = root / ".nexus" / "reports" / f"nightshift_{inst.task.replace('/', '_')}.json"
        success = bool(
            result_map.get("status") == "COMPLETED"
            and best_score > 0
            and rounds_attempted > 0
            and report_path.is_file()
            and isinstance(inst.last_learning_closure, Mapping)
            and isinstance(inst.last_unified_runtime_receipt, Mapping)
        )
        return _make_receipt(
            "nightshift_runner_service",
            plan,
            wall_time_ms=elapsed,
            gate_passed=success,
            outcome=_structured_outcome(
                action="run",
                semantic_status="VERIFIED" if success else "BLOCKED",
                evidence_refs=[f"file:{report_path}"] if report_path.is_file() else [],
                result={
                    "budget_sec": budget,
                    "terminal_status": str(result_map.get("status") or ""),
                    "best_score": best_score,
                    "rounds_attempted": rounds_attempted,
                    "report_path": str(report_path),
                    "learning_closure_present": bool(inst.last_learning_closure),
                    "runtime_receipt_present": bool(inst.last_unified_runtime_receipt),
                },
                physical_callable=(
                    "nexus.app.nightshift_runner_service.AutoResearchNightShift.run"
                ),
                terminal_success=success,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "nightshift_runner_service",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="compute_time_budget",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_autonomic_router(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-13 legacy-engine: the legacy AutonomicRouter suggestion (consumed by
    nothing, enabled by no policy rule) is retired; fail closed."""
    return _archived_receipt("autonomic_router", plan, task_desc)


# ─── X-phase ──────────────────────────────────────────────────────────────────

def _exec_codeintel(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    skeleton_cls = _try_import_class("nexus.services.codeintel.skeleton_provider", "PythonCodeSkeletonProvider")
    if skeleton_cls is None:
        return _make_receipt("codeintel", plan, invoked=False, gate_passed=False,
                             outcome={"error": "PythonCodeSkeletonProvider not importable"})
    try:
        from pathlib import Path
        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or ".")).resolve()
        target_symbol = str(constraints.get("target_symbol") or "").strip()
        if not target_symbol:
            return _make_receipt(
                "codeintel",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="lookup_implementation",
                    semantic_status="BLOCKED",
                    error="TARGET_SYMBOL_REQUIRED",
                    evidence_refs=[f"ev_codeintel_blocked_{plan.task_id}"],
                    lookup_symbol="",
                    lookup_performed=False,
                    physical_callable=(
                        "nexus.services.codeintel.skeleton_provider."
                        "PythonCodeSkeletonProvider.lookup_implementation"
                    ),
                ),
            )
        search_paths = constraints.get("search_paths") or ()
        target_file = str(constraints.get("target_file") or "").strip()
        if not search_paths and target_file:
            search_paths = (target_file,)
        if isinstance(search_paths, str):
            search_paths = (search_paths,)
        inst = skeleton_cls(root=str(root), search_paths=tuple(search_paths))
        lookup = inst.lookup_implementation(target_symbol)
        matches = list(getattr(lookup, "matches", ()) or ())
        result = {
            "provider": type(inst).__name__,
            "root": str(root),
            "lookup_symbol": target_symbol,
            "found": bool(getattr(lookup, "found", False)),
            "reason": str(getattr(lookup, "reason", "") or ""),
            "match_count": len(matches),
            "files": [str(getattr(item, "file_path", "")) for item in matches[:8]],
        }
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "codeintel",
            plan,
            gate_passed=True,  # non-claim execution health (#1869)
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="lookup_implementation",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_codeintel_lookup_{plan.task_id}"],
                result=result,
                lookup_symbol=target_symbol,
                lookup_performed=True,
                found=bool(getattr(lookup, "found", False)),
                match_count=len(matches),
                physical_callable=(
                    "nexus.services.codeintel.skeleton_provider."
                    "PythonCodeSkeletonProvider.lookup_implementation"
                ),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt("codeintel", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
                             outcome={"error": str(exc)[:300]})


def _exec_lancedb(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        import pandas as pd

        from nexus.services.lancedb_roots import KNOWLEDGE, resolve_lancedb_root
        from nexus.services.memory_repository import MemoryRepository

        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or ".")).resolve()
        query = str(constraints.get("search_query") or task_desc or "").strip()
        table = str(constraints.get("search_table") or "policy").strip()
        limit = max(1, min(20, int(constraints.get("search_limit") or 5)))
        repository = MemoryRepository(resolve_lancedb_root(KNOWLEDGE, root, honor_env=False))
        frame = repository.search_fts(
            table,
            query,
            limit=limit,
            fallback_columns=["condition", "action"],
        )
        # search_fts may return a DataFrame, a Series or a fallback; only a DataFrame
        # supports ``to_dict(orient="records")``.
        records: list[Any] = (
            frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else []
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "lancedb",
            plan,
            gate_passed=True,  # non-claim execution health (#1869)
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="query",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_lancedb_query_{plan.task_id}"],
                result={"records": records[:limit], "table": table},
                query=query[:200],
                table=table,
                query_performed=True,
                hit_count=len(records),
                physical_callable="nexus.services.memory_repository.MemoryRepository.search_fts",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt("lancedb", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
                             outcome={"error": str(exc)[:300]})


def _research_contamination_signal(
    plan: CapabilityExecutionPlan, result: Mapping[str, Any], research_task: str, log_root: Path
) -> dict[str, Any]:
    """P-CONTAM-01 record-only signal for accepted research output (#2199/#2216).

    The check never changes the receipt status.  The signal goes into the receipt outcome
    and is appended to <workspace>/.nexus/research/contamination_signals.jsonl.
    """
    try:
        from nexus.research.contamination_enforcement import (
            append_contamination_signal,
            check_research_output,
            signal_from_verdict,
        )

        signal = signal_from_verdict(check_research_output(result, echo_texts=(research_task,)))
        append_contamination_signal(
            log_root,
            signal,
            route="capability_executor_registry._exec_research",
            task_id=plan.task_id,
        )
        return signal
    except Exception as exc:  # the record-only signal must never break research
        logger.warning("research contamination signal error: %s", str(exc)[:200])
        return {
            "policy_id": "P-CONTAM-01",
            "mode": "record_only",
            "detected": None,
            "reason": "RESEARCH_CONTAMINATION_GUARD_ERROR",
            "terms": [],
        }


def _exec_research(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_port("research.ResearchPhaseHandler")
    if cls is None:
        return _make_receipt(
            "research",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="run",
                semantic_status="FAILED",
                error=_port_error("research.ResearchPhaseHandler"),
            ),
        )
    try:
        from nexus.core.state_contracts import NexusState

        try:
            research_root = _scoped_workspace(plan.constraints, Path(".").resolve())
        except _ScopeError as scope:
            return _scope_blocked_receipt("research", plan, str(scope), start)
        # Per-task run dir: the handler caches researchpack.json there, so a shared
        # directory would return one task's pack for every other task.
        research_dir = research_root / ".nexus" / "research" / _safe_run_id(plan.task_id)
        research_dir.mkdir(parents=True, exist_ok=True)
        inst = cls(project_root=research_root, run_dir=research_dir)
        # The handler's default LanceDB cache lives under ~/.openclaw; keep cache writes in the
        # per-task run dir (researchpack.json) instead.
        inst._get_lancedb = lambda: None  # type: ignore[method-assign]
        # Outbound calls (chub CLI / felo) only with the operator switch; authorization is
        # env-only, never a request constraint.  The providers are blocked at the egress
        # methods, so a stubbed provider (tests) still runs hermetically.
        research_authorized = _provider_auth_allowed(require_external=True)
        if not research_authorized:
            blocked_pack = {
                "findings": [],
                "source": "BLOCKED_EXTERNAL_AUTH",
                "status": "FAIL",
                "tokens_used": 0,
                "error": "BLOCKED_EXTERNAL_AUTH",
            }
            inst._run_chub = lambda query: dict(blocked_pack)  # type: ignore[method-assign]
            inst._run_felo = lambda query: dict(blocked_pack)  # type: ignore[method-assign]
        state = NexusState(task_id=plan.task_id, metadata={})
        # Real physical run path — not should_run probe alone.
        # ResearchPhaseHandler.run reads context["task"]; "task_statement" is kept
        # for callers that still key on the old name.
        # The task is an opaque payload.  The handler would scan it for URLs and route them to
        # the UCC reach router, so URL extraction is removed from this executor entirely (no
        # parsing of request text for endpoints); providers use their own configured endpoint.
        inst._extract_urls = lambda text: []  # type: ignore[method-assign]
        research_task = str(task_desc or "").strip()
        result = inst.run(
            state,
            {
                "task": research_task,
                "task_statement": research_task,
                "dry_run": True,
                "bounded": True,
            },
        )
        elapsed = int((time.monotonic() - start) * 1000)
        if (
            not research_authorized
            and isinstance(result, Mapping)
            and "BLOCKED_EXTERNAL_AUTH" in str(result.get("error") or "")
        ):
            return _make_receipt(
                "research",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome=_structured_outcome(
                    action="auth_gate",
                    semantic_status="BLOCKED",
                    error="BLOCKED_EXTERNAL_AUTH",
                    evidence_refs=["ev_auth_block_research"],
                    auth_required=True,
                    provider_call_count=0,
                ),
            )
        ok = (
            isinstance(result, Mapping)
            and not result.get("error")
            and result.get("status") != "FAIL"
            and bool(research_task)
            and list(result.get("findings") or []) != ["Empty research task."]
        )
        # P-CONTAM-01 (#2199/#2216): record-only signal on accepted research output.
        signal = (
            _research_contamination_signal(plan, result, research_task, research_root)
            if ok and isinstance(result, Mapping)
            else None
        )
        return _make_receipt(
            "research",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="run",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_research_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable="nexus.engine.phases.research.ResearchPhaseHandler.run",
                contamination_signal=signal,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "research",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run",
                semantic_status="FAILED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_research_err_{plan.task_id}"],
            ),
        )


def _exec_learn_scheduler_service(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_port("learn_scheduler.LearnSchedulerService")
    if cls is None:
        return _make_receipt("learn_scheduler_service", plan, invoked=False, gate_passed=False,
                             outcome={"error": _port_error("learn_scheduler.LearnSchedulerService")})
    try:
        from pathlib import Path
        constraints = dict(plan.constraints or {})
        # The checkout only provides the CLI script; the policy is evaluated on the
        # request's workspace learn store (workspace_root), not on the checkout's data.
        repo_root = Path(__file__).resolve().parents[2]
        report_root = Path(
            str(constraints.get("workspace_root") or repo_root)
        ).expanduser().resolve()
        inst = cls(repo_root=repo_root, report_root=report_root, project_root=report_root)
        if not hasattr(inst, "run_scheduler"):
            raise RuntimeError("run_scheduler missing")
        result = int(inst.run_scheduler())
        report_path = report_root / ".nexus/reports/learn/scheduler_last_run.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        readiness = float(report.get("slo_readiness") or 0.0)
        passed = result == 0 and readiness >= 0.5
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "learn_scheduler_service",
            plan,
            wall_time_ms=elapsed,
            gate_passed=passed,
            outcome=_structured_outcome(
                action="run_scheduler",
                semantic_status="SUCCEEDED" if passed else "BLOCKED",
                evidence_refs=[f"file:{report_path}"],
                error=None if passed else f"scheduler_exit_{result}",
                result={
                    "exit_code": result,
                    "slo_readiness": readiness,
                    "policy_command": list(report.get("policy_command") or []),
                    "scheduler_report_path": str(report_path),
                    "alert_dispatched": bool(report.get("alert_dispatched")),
                },
                physical_callable=(
                    "nexus.app.learn_scheduler_service."
                    "LearnSchedulerService.run_scheduler"
                ),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "learn_scheduler_service",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "run_scheduler", "error": str(exc)[:300]},
        )


# ─── D-phase ──────────────────────────────────────────────────────────────────

def _exec_belief(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Production belief: call real BeliefEngine.assess_confidence only.

    Never invent confidence from digests, never call missing ``evaluate``,
    never wrap ``no_evaluate`` / error as SUCCEEDED.
    """
    start = time.monotonic()
    try:
        from nexus.core.belief_engine import BeliefEngine

        inst = BeliefEngine()
        assumption = str(
            (plan.constraints or {}).get("assumption")
            or (plan.constraints or {}).get("statement")
            or task_desc
            or plan.task_id
            or ""
        )
        task_id = str(plan.task_id or "")
        # Prefer assess_confidence; fall back to get_confidence only if present.
        if hasattr(inst, "assess_confidence") and callable(getattr(inst, "assess_confidence")):
            raw = inst.assess_confidence(task_id, assumption)
            _action = "assess_confidence"
        elif hasattr(inst, "get_confidence") and callable(getattr(inst, "get_confidence")):
            raw = inst.get_confidence(task_id, assumption)
            _action = "assess_confidence"  # report canonical action name
        else:
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "belief",
                plan,
                invoked=False,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome={
                    "action": "assess_confidence",
                    "error": "no_supported_belief_api",
                    "task_id": task_id,
                    "assumption": assumption[:200],
                },
            )
        try:
            confidence = float(raw)
        except (TypeError, ValueError):
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "belief",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome={
                    "action": "assess_confidence",
                    "error": "confidence_not_numeric",
                    "raw": str(raw)[:120],
                    "task_id": task_id,
                    "assumption": assumption[:200],
                },
            )
        if confidence != confidence:  # NaN
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "belief",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome={
                    "action": "assess_confidence",
                    "error": "confidence_nan",
                    "task_id": task_id,
                    "assumption": assumption[:200],
                },
            )
        confidence = max(0.0, min(1.0, confidence))
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "belief",
            plan,
            gate_passed=True,  # non-claim execution health (#1869)
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="assess_confidence",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_belief_assessment_{task_id}"],
                result={"confidence": confidence},
                confidence=confidence,
                task_id=task_id,
                assumption=assumption[:200],
                physical_callable="nexus.core.belief_engine.BeliefEngine.assess_confidence",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt("belief", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
                             outcome={"error": str(exc)[:300]})


def _exec_autoreason(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    # These planner nodes are EXTERNAL_AUTH_REQUIRED model boundaries.  Local
    # consumes their shared evidence; a local-call flag must not authorize the
    # producer itself or turn an offline canary green.
    if not _provider_auth_allowed(require_external=True) and not bool(
        (plan.constraints or {}).get("allow_fixture_model_boundary")
    ):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt("autoreason", plan, wall_time_ms=elapsed)
    cls = _try_port("autoreason.AutoreasonService")
    if cls is None:
        return _make_receipt(
            "autoreason",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="run",
                semantic_status="FAILED",
                error=_port_error("autoreason.AutoreasonService"),
            ),
        )
    try:
        candidates = _candidate_pool(plan)
        if not candidates:
            return _no_candidate_pool_receipt("autoreason", plan, start)
        inst = cls()
        result = inst.run(candidates=candidates, task_desc=str(task_desc or plan.task_id))
        elapsed = int((time.monotonic() - start) * 1000)
        ok = isinstance(result, Mapping) and not result.get("error")
        return _make_receipt(
            "autoreason",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="run",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_autoreason_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable="nexus.engine.autoreason_service.AutoreasonService.run",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "autoreason",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run",
                semantic_status="FAILED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_autoreason_err_{plan.task_id}"],
            ),
        )


def _exec_repair_loop(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    elapsed = int((time.monotonic() - start) * 1000)
    return _make_receipt(
        "repair_loop",
        plan,
        invoked=True,
        gate_passed=False,
        wall_time_ms=elapsed,
        outcome=_structured_outcome(
            action="await_local_repair_receipt",
            semantic_status="BLOCKED",
            error="REAL_REPAIR_ATTEMPT_RECEIPT_REQUIRED",
            evidence_refs=[f"ev_repair_loop_blocked_{plan.task_id}"],
            result={
                "task_description_present": bool(str(task_desc or "").strip()),
                "required_effects": [
                    "candidate_hash",
                    "applied_hash_match",
                    "non_empty_verifier_commands",
                    "verifier_passed",
                    "settlement_decision",
                ],
            },
            physical_callable=(
                "nexus.services.local_heal.local_model_executor."
                "LocalModelExecutor.run"
            ),
        ),
    )


def _exec_hyper_sprint(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not (
        _provider_auth_allowed(require_local_model=True)
        or _provider_auth_allowed(require_external=True)
    ):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt(
            "hyper_sprint",
            plan,
            wall_time_ms=elapsed,
            reason="BLOCKED_EXTERNAL_AUTH:local_or_online_model",
        )
    fn = _try_import_class("nexus.research.sprint_service", "run_hyper_sprint")
    if fn is None or not callable(fn):
        return _make_receipt("hyper_sprint", plan, invoked=False, gate_passed=False,
                             outcome={"error": "run_hyper_sprint not importable"})
    try:
        from nexus.research.sprint_service import SprintConfig
        hyper = dict(plan.constraints or {})
        try:
            hyper_root = _scoped_workspace(hyper, Path(".").resolve())
            hyper_target = str(hyper.get("hyper_target_file") or "").strip()
            if not hyper_target:
                hyper_target = _first_task_file(hyper) or "README.md"
            _scoped_path(hyper_root, hyper_target)
            hyper_test = str(hyper.get("hyper_test_file") or "").strip()
            if hyper_test:
                _scoped_path(hyper_root, hyper_test)
        except _ScopeError as scope:
            return _scope_blocked_receipt("hyper_sprint", plan, str(scope), start)
        try:
            hyper_candidates = max(1, int(hyper.get("hyper_candidate_count") or 1))
        except (TypeError, ValueError):
            hyper_candidates = 1
        # LLM candidates are opt-in per request; the default stays deterministic.
        hyper_llm = _truthy(hyper.get("hyper_llm_mode"))
        if hyper_llm and not _provider_auth_allowed(require_local_model=True):
            # A request flag is never authorization: llm_mode needs the local-model switch.
            return _auth_blocked_receipt(
                "hyper_sprint",
                plan,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                reason="BLOCKED_EXTERNAL_AUTH:local_model",
            )
        # "local" = Workforce-admitted ollama worker through the armored local lane (needs a
        # test file as verifier); "online" = the gateway provider (the previous behaviour).
        hyper_channel = str(hyper.get("hyper_llm_channel") or "online").strip().lower()
        if hyper_channel not in {"online", "local"}:
            return _scope_blocked_receipt(
                "hyper_sprint", plan, f"unsupported_hyper_llm_channel:{hyper_channel}", start
            )
        try:
            hyper_min_pool = max(1, int(hyper.get("hyper_min_candidate_pool") or 1))
        except (TypeError, ValueError):
            hyper_min_pool = 1
        cfg = SprintConfig(
            task=str(task_desc or plan.task_id),
            target_file=hyper_target,
            test_file=hyper_test or None,
            candidate_count=hyper_candidates,
            max_rounds=1,
            timeout_sec=10,
            safe_mode=True,
            llm_mode=bool(hyper_llm),
            stage1_max_parallel=1,
            stage1_timeout_sec=30,
            llm_channel=hyper_channel,
            min_candidate_pool=hyper_min_pool,
        )
        result = fn(repo_root=hyper_root, config=cfg)
        elapsed = int((time.monotonic() - start) * 1000)
        sprint_status = str(getattr(result, "status", "") or "").upper()
        sprint_ok = sprint_status in {"SUCCESS", "SUCCEEDED"}
        trace = getattr(result, "learning_trace", None)
        trace = trace if isinstance(trace, Mapping) else {}
        candidates = [
            {
                "seed": getattr(item, "seed", None),
                "source": str(getattr(item, "source", "") or ""),
                "score": float(getattr(item, "score", 0.0) or 0.0),
                "rejection": str(getattr(item, "error", "") or "")[:160],
                "code_sha256": hashlib.sha256(
                    str(getattr(item, "candidate_code", "") or "").encode("utf-8")
                ).hexdigest(),
            }
            for item in list(getattr(result, "candidates", []) or [])
        ]
        model_verified = [
            item
            for item in candidates
            if item["source"].startswith("llm") and item["score"] >= 1.0
        ]
        unified = [
            {
                "task_id": str(item.get("task_id") or ""),
                "terminal_status": str(item.get("terminal_status") or ""),
                "local_status": str((item.get("local") or {}).get("status") or "")
                if isinstance(item.get("local"), Mapping)
                else "",
            }
            for item in list(getattr(result, "unified_runtime_receipts", []) or [])
            if isinstance(item, Mapping)
        ]
        summary_keys = (
            "status",
            "reason",
            "target_file",
            "winner_source",
            "final_score",
            "elapsed_sec",
            "attempt_count",
            "model_calls",
            "model_name",
            "model_patch_generated",
            "fallback_used",
            "error_codes",
            "pytest_cmd",
        )
        return _make_receipt(
            "hyper_sprint",
            plan,
            wall_time_ms=elapsed,
            gate_passed=sprint_ok,
            outcome=_structured_outcome(
                action="run_hyper_sprint",
                semantic_status="SUCCEEDED" if sprint_ok else "FAILED",
                evidence_refs=[f"ev_hyper_sprint_{plan.task_id}"],
                result={key: getattr(result, key, None) for key in summary_keys},
                sprint_status=sprint_status,
                target_file=hyper_target,
                test_file=hyper_test,
                candidate_count=hyper_candidates,
                min_candidate_pool=hyper_min_pool,
                llm_mode=bool(hyper_llm),
                llm_channel=hyper_channel,
                llm_mode_effective=bool(trace.get("llm_mode_effective")),
                learn_slo_guard=dict(trace.get("learn_slo_guard") or {}),
                attempt_count=getattr(result, "attempt_count", None),
                model_calls=int(getattr(result, "model_calls", 0) or 0),
                candidates=candidates,
                model_verified_candidate_count=len(model_verified),
                unified_runtime_receipts=unified,
                physical_callable="nexus.research.sprint_service.run_hyper_sprint",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "hyper_sprint",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "run_hyper_sprint", "error": str(exc)[:300]},
        )


def _exec_swarm_multi_agent(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not (
        _provider_auth_allowed(require_local_model=True)
        or _provider_auth_allowed(require_external=True)
    ):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt(
            "swarm_multi_agent",
            plan,
            wall_time_ms=elapsed,
            reason="BLOCKED_EXTERNAL_AUTH:local_or_online_workers",
        )
    constraints = dict(plan.constraints or {})
    try:
        swarm_root = _scoped_workspace(constraints, Path(".").resolve())
        target = str(constraints.get("swarm_target_file") or "").strip() or _first_task_file(constraints)
        verify_script = str(constraints.get("swarm_verify_script") or "").strip()
        if not target or not verify_script:
            return _make_receipt(
                "swarm_multi_agent",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="run_bounded_swarm",
                    semantic_status="BLOCKED",
                    error="SWARM_TARGET_AND_VERIFY_SCRIPT_REQUIRED",
                    evidence_refs=[f"ev_swarm_blocked_{plan.task_id}"],
                    physical_callable="nexus.engine.swarm_run.run_bounded_swarm",
                ),
            )
        _scoped_path(swarm_root, target)
        _scoped_path(swarm_root, verify_script)
    except _ScopeError as scope:
        return _scope_blocked_receipt("swarm_multi_agent", plan, str(scope), start)
    try:
        workers = max(1, min(4, int(constraints.get("swarm_parallelism") or 2)))
    except (TypeError, ValueError):
        workers = 2
    try:
        run_bounded_swarm = resolve_port("swarm_run.run_bounded_swarm")
        report = run_bounded_swarm(
            workspace_root=swarm_root,
            task_id=str(plan.task_id),
            task=str(task_desc or plan.task_id),
            target_file=target,
            verify_script=verify_script,
            workers=workers,
        )
    except Exception as exc:
        return _make_receipt(
            "swarm_multi_agent",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="run_bounded_swarm",
                semantic_status="FAILED",
                error=f"swarm_run_error:{type(exc).__name__}:{str(exc)[:200]}",
                evidence_refs=[f"ev_swarm_error_{plan.task_id}"],
                physical_callable="nexus.engine.swarm_run.run_bounded_swarm",
            ),
        )
    status = str(report.get("status") or "")
    ok = status == "SUCCEEDED"
    worker_rows = [w for w in report.get("workers") or [] if isinstance(w, Mapping)]
    return _make_receipt(
        "swarm_multi_agent",
        plan,
        invoked=True,
        gate_passed=ok,
        wall_time_ms=int((time.monotonic() - start) * 1000),
        outcome=_structured_outcome(
            action="run_bounded_swarm",
            # BLOCKED when a step refused (lock conflict, integration authority); the workers'
            # worktrees, commits and verifier results are still in the report.
            semantic_status="SUCCEEDED" if ok else ("BLOCKED" if status == "BLOCKED" else "FAILED"),
            error="" if ok else str(report.get("reason") or "SWARM_RUN_INCOMPLETE"),
            evidence_refs=[f"ev_swarm_{plan.task_id}"],
            swarm_report=report,
            worker_count=len(worker_rows),
            workers_executed=sum(1 for w in worker_rows if w.get("worker_status") == "candidate_written"),
            verified_workers=sum(1 for w in worker_rows if w.get("verify_result") == "pass"),
            model_calls=sum(int(w.get("model_calls") or 0) for w in worker_rows),
            physical_callable="nexus.engine.swarm_run.run_bounded_swarm",
        ),
    )


def _exec_drone(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.core.drone_engine", "TacticalDrone")
    if cls is None:
        return _make_receipt(
            "drone",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="repair_response_schema",
                semantic_status="FAILED",
                error="TacticalDrone not importable",
            ),
        )
    try:
        from pathlib import Path

        inst = cls(drone_id=f"drone-{plan.task_id}", project_root=Path("."), max_rounds=1)
        # Real production method — not health_check probe.
        repaired = inst.repair_response_schema(
            {"action": "analyze", "task": str(task_desc or plan.task_id)[:200]}
        )
        normalized = inst.normalize_action(str(task_desc or plan.task_id)[:200])
        elapsed = int((time.monotonic() - start) * 1000)
        ok = isinstance(repaired, Mapping)
        return _make_receipt(
            "drone",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="repair_response_schema",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_drone_{plan.task_id}"],
                result={
                    "repaired_keys": list(repaired.keys())[:12] if isinstance(repaired, Mapping) else [],
                    "normalized_action": str(normalized)[:80],
                },
                physical_callable="nexus.core.drone_engine.TacticalDrone.repair_response_schema",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "drone",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="repair_response_schema",
                semantic_status="FAILED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_drone_err_{plan.task_id}"],
            ),
        )


def _exec_nightshift(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    return _exec_nightshift_runner_service(plan, task_desc)


def _exec_sandbox_confined(plan: CapabilityExecutionPlan, constraints: Mapping[str, Any]) -> CapabilityReceipt:
    """Post-candidate sandbox: the visible test inside ``sandboxed_lane.confinement``.

    Selected when the caller passes ``sandbox_forbidden_paths`` (the post-candidate seam does,
    with the hidden verifier test path). The receipt carries the exit code and the stdout
    sha256; a refused confinement (no OS barrier, forbidden read root, forbidden argv) is
    reported as not executed, never as a pass.
    """
    start = time.monotonic()
    runner = _try_port("sandbox_runner.run_confined_test")
    if runner is None:
        return _make_receipt(
            "sandbox_runner",
            plan,
            invoked=False,
            gate_passed=False,
            outcome={"error": _port_error("sandbox_runner.run_confined_test")},
        )
    raw_command = constraints.get("sandbox_command") or []
    command = [str(part) for part in list(raw_command) if str(part).strip()]
    timeout_sec = max(1, min(120, int(constraints.get("sandbox_timeout_sec") or 30)))
    forbidden = [str(item) for item in list(constraints.get("sandbox_forbidden_paths") or []) if str(item).strip()]
    try:
        result = dict(
            runner(
                str(constraints.get("workspace_root") or ""),
                command=command,
                forbidden_paths=forbidden,
                timeout_sec=timeout_sec,
            )
        )
    except Exception as exc:  # noqa: BLE001 - executor boundary must fail closed
        result = {"executed": False, "error": f"{type(exc).__name__}: {exc}"}
    elapsed = int((time.monotonic() - start) * 1000)
    executed = bool(result.get("executed"))
    if not executed:
        # Refused by the confinement (no OS barrier, forbidden root/argv): nothing ran.
        return _make_receipt(
            "sandbox_runner",
            plan,
            invoked=False,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run_task",
                semantic_status="NOT_EXECUTED_SANDBOX_REFUSED",
                error=str(result.get("error") or "sandbox_not_executed"),
                evidence_refs=[f"ev_sandbox_refused_{plan.task_id}"],
                sandbox_executed=False,
                workspace_isolated=False,
                network_allowed=False,
                confined=True,
                forbidden_paths_count=len(forbidden),
                physical_callable="nexus.engine.confined_test_runner.run_confined_test",
            ),
        )
    ok = bool(result.get("success")) and result.get("exit_code") == 0
    return _make_receipt(
        "sandbox_runner",
        plan,
        gate_passed=ok,
        wall_time_ms=elapsed,
        outcome=_structured_outcome(
            action="run_task",
            semantic_status="SUCCEEDED" if ok else "FAILED",
            evidence_refs=[f"ev_sandbox_run_{plan.task_id}", f"sha256:{result.get('stdout_sha256') or ''}"],
            result={
                "run_id": str(result.get("run_id") or ""),
                "duration_sec": float(result.get("duration_sec") or 0.0),
                "stdout_sha256": str(result.get("stdout_sha256") or ""),
                "timed_out": bool(result.get("timed_out")),
            },
            sandbox_executed=True,
            simulated=False,
            workspace_isolated=str(result.get("workspace_source") or "") == "local_project_copy",
            exit_code=result.get("exit_code"),
            stdout_sha256=str(result.get("stdout_sha256") or ""),
            output_tail=(str(result.get("stdout_tail") or "") + str(result.get("stderr_tail") or ""))[-600:],
            network_allowed=False,
            timed_out=bool(result.get("timed_out")),
            confined=True,
            forbidden_paths_count=len(forbidden),
            command=list(result.get("command") or command)[:12],
            physical_callable="nexus.engine.confined_test_runner.run_confined_test",
        ),
    )


def _exec_sandbox_runner(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if "sandbox_forbidden_paths" in dict(plan.constraints or {}):
        return _exec_sandbox_confined(plan, dict(plan.constraints or {}))
    cls = _try_port("sandbox_runner.SandboxRunner")
    if cls is None:
        return _make_receipt("sandbox_runner", plan, invoked=False, gate_passed=False,
                             outcome={"error": _port_error("sandbox_runner.SandboxRunner")})
    try:
        from pathlib import Path
        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or "")).resolve()
        raw_command = constraints.get("sandbox_command") or []
        command = [str(part) for part in list(raw_command) if str(part).strip()]
        timeout_sec = max(1, min(120, int(constraints.get("sandbox_timeout_sec") or 30)))
        if not str(constraints.get("workspace_root") or "").strip() or not command:
            return _make_receipt(
                "sandbox_runner",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="run_task",
                    semantic_status="BLOCKED",
                    error="SANDBOX_COMMAND_CONTEXT_REQUIRED",
                    evidence_refs=[f"ev_sandbox_blocked_{plan.task_id}"],
                    sandbox_executed=False,
                    workspace_isolated=False,
                    network_allowed=False,
                ),
            )
        inst = cls(project_root=root)
        result = inst.run_task(
            str(task_desc or plan.task_id),
            command=command,
            cwd=".",
            timeout_sec=timeout_sec,
            cleanup=True,
        )
        ok = bool(result.get("success")) and int(result.get("exit_code") or 0) == 0
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "sandbox_runner",
            plan,
            gate_passed=ok,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run_task",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_sandbox_run_{plan.task_id}"],
                result={
                    "run_id": str(result.get("run_id") or ""),
                    "report_path": str(result.get("report_path") or ""),
                    "duration_sec": float(result.get("duration_sec") or 0.0),
                },
                sandbox_executed=True,
                workspace_isolated=(
                    str(result.get("workspace_source") or "") == "local_project_copy"
                ),
                exit_code=result.get("exit_code"),
                network_allowed=bool(result.get("network_allowed", True)),
                timed_out=bool(result.get("timed_out")),
                physical_callable="nexus.engine.sandbox_runner.SandboxRunner.run_task",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "sandbox_runner",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "build_elastic_profile", "error": str(exc)[:300]},
        )


# ─── A-phase ──────────────────────────────────────────────────────────────────

def _exec_artifact_gate(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class(
        "nexus.services.local_heal.local_model_capability_executors",
        "ArtifactGateLocalExecutor",
    )
    if cls is None:
        return _make_receipt("artifact_gate", plan, invoked=False, gate_passed=False,
                             outcome={"error": "ArtifactGateLocalExecutor not importable"})
    try:
        inst = cls()
        # #2361: the executor reads attributes (ctx.evidence_refs), so pass its context type.
        from nexus.services.local_heal.local_model_capability_context import (
            LocalModelCapabilityContext,
        )

        constraints = plan.constraints if isinstance(plan.constraints, Mapping) else {}
        anchor = constraints.get("source_anchor")
        raw_refs = constraints.get("evidence_refs")
        # Non-list evidence_refs are rejected (no str() coercion of arbitrary values).
        refs = tuple(r for r in raw_refs if isinstance(r, str)) if isinstance(raw_refs, list) else ()
        ctx: Any = LocalModelCapabilityContext(
            task_id=plan.task_id,
            source_root="",
            problem_statement=task_desc or "",
            target_file="",
            target_symbol="",
            selected_capabilities=("artifact_gate",),
            execution_topology="",
            evidence_refs=refs,
            source_anchor=dict(anchor) if isinstance(anchor, Mapping) else {},
        )
        result: Any = None
        if hasattr(inst, "execute"):
            try:
                result = inst.execute(ctx)
            except TypeError:
                result = inst.execute(context=ctx)
        else:
            result = {"executor": type(inst).__name__}
        elapsed = int((time.monotonic() - start) * 1000)
        # #1869: artifact_gate is a claim gate. A bare "execute() returned" is not a pass: the
        # executor result must carry a validated verifier artifact/status and a typed source hash.
        from nexus.core.claim_gate_binding import claim_gate_binding_reasons

        if isinstance(result, Mapping):
            binding_payload = dict(result)
        elif hasattr(result, "gate_passed") and hasattr(result, "evidence_present"):
            # CapabilityExecutionResult dataclass: only the executor's own payload may carry
            # verifier evidence (#1869). Nothing is synthesized from plan.constraints, so a result
            # without verifier_status/source_hash in its payload stays unbound (fail-closed).
            payload = getattr(result, "payload", None)
            binding_payload = dict(payload) if isinstance(payload, Mapping) else {}
        else:
            binding_payload = {}
        binding_reasons = claim_gate_binding_reasons(binding_payload)
        outcome: dict[str, Any] = {"action": "execute", "result": str(result)[:200]}
        if binding_reasons:
            outcome["binding_blockers"] = binding_reasons
        return _make_receipt(
            "artifact_gate",
            plan,
            gate_passed=not binding_reasons,
            wall_time_ms=elapsed,
            outcome=outcome,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "artifact_gate",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "execute", "error": str(exc)[:300]},
        )


def _resolve_candidate_hash_match(
    constraints: Mapping[str, Any],
) -> tuple[bool | None, bool]:
    """Return (hash_match_value, present).

    Omitted match is NOT treated as True. Top-level False and route_context False
    both count as present False.
    """
    if "candidate_hash_matches_applied" in constraints:
        return bool(constraints.get("candidate_hash_matches_applied")), True
    route = constraints.get("route_context")
    if isinstance(route, Mapping) and "candidate_hash_matches_applied" in route:
        return bool(route.get("candidate_hash_matches_applied")), True
    return None, False


def _exec_claim_gate(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Registry claim_gate is postflight-owned when full context is incomplete.

    Mainchain production claim/delivery/artifact gates run via strict postflight
    evaluators (online_nexus_context.evaluate_postflight_gate). This registry
    path never invents hashes/patches/approvals and never accepts the validator's
    backward-compatible True default when hash-match is omitted.
    """
    start = time.monotonic()
    fn = _try_import_class("nexus.services.local_heal.claim_delivery_gate", "validate_context_claim_delivery")
    if fn is None:
        return _make_receipt(
            "claim_gate",
            plan,
            invoked=False,
            gate_passed=False,
            outcome={
                "action": "validate_context_claim_delivery",
                "error": "validate_context_claim_delivery not importable",
                "postflight_owned": True,
            },
        )
    constraints = dict(plan.constraints or {})
    # Require real claim context — no synthetic theater.
    required = ("source_hash", "candidate_target_file")
    missing = [k for k in required if not str(constraints.get(k) or "").strip()]
    hash_match, hash_present = _resolve_candidate_hash_match(constraints)
    if not hash_present:
        missing.append("candidate_hash_matches_applied")
    if missing:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "claim_gate",
            plan,
            invoked=False,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={
                "action": "validate_context_claim_delivery",
                "error": "missing_real_claim_context",
                "missing_fields": missing,
                "postflight_owned": True,
                "note": "mainchain production claim_gate is postflight-owned",
            },
        )
    # Explicit False (top-level or route_context) must reach validator as False.
    assert hash_match is not None
    try:
        from types import SimpleNamespace

        route_ctx: dict[str, Any] = {}
        if isinstance(constraints.get("route_context"), Mapping):
            route_ctx = dict(constraints.get("route_context") or {})
        # Force explicit hash-match into route_context so no True fallback applies.
        route_ctx["candidate_hash_matches_applied"] = bool(hash_match)

        op = SimpleNamespace(
            solve_eligible=bool(constraints.get("solve_eligible", False)),
            failure_reason=str(constraints.get("failure_reason") or ""),
            evaluation_report=str(constraints.get("evaluation_report") or ""),
            source_hash=str(constraints.get("source_hash") or ""),
            final_patch=str(constraints.get("final_patch") or ""),
            owner_approved=bool(constraints.get("owner_approved", False)),
            # Prefer selected_candidate_hash_matches_applied field name used by validator.
            selected_candidate_hash_matches_applied=bool(hash_match),
            candidate_hash_matches_applied=bool(hash_match),
            candidate_target_file=str(constraints.get("candidate_target_file") or ""),
            route_context=route_ctx,
        )
        ctx = SimpleNamespace(op=op)
        # Pass explicit kwarg so validator cannot apply omitted→True fallback.
        try:
            result = fn(ctx, candidate_hash_matches_applied=bool(hash_match))
        except TypeError:
            result = fn(ctx)
        elapsed = int((time.monotonic() - start) * 1000)
        claim_passed = None
        delivery_passed = None
        generic_passed = None
        failure_reasons: list[str] = []
        if isinstance(result, Mapping):
            if "claim_gate_passed" in result:
                claim_passed = bool(result.get("claim_gate_passed"))
            if "delivery_gate_passed" in result:
                delivery_passed = bool(result.get("delivery_gate_passed"))
            if "passed" in result:
                generic_passed = bool(result.get("passed"))
            elif "ok" in result:
                generic_passed = bool(result.get("ok"))
            elif "gate_passed" in result:
                generic_passed = bool(result.get("gate_passed"))
            raw_reasons = result.get("failure_reasons")
            if isinstance(raw_reasons, (list, tuple)):
                failure_reasons = [str(x) for x in raw_reasons if str(x).strip()]
        # Explicit False hash match always fails closed regardless of validator quirks.
        if not bool(hash_match):
            gate_ok = False
            if "candidate_hash_mismatch" not in failure_reasons:
                failure_reasons = ["candidate_hash_mismatch", *failure_reasons]
        elif claim_passed is not None:
            gate_ok = bool(claim_passed)
        elif generic_passed is not None:
            gate_ok = bool(generic_passed)
        else:
            gate_ok = False
        outcome_map: dict[str, Any] = {
            "action": "validate_context_claim_delivery",
            "result": str(result)[:200] if result is not None else "",
            "claim_gate_passed": claim_passed if claim_passed is not None else gate_ok,
            "delivery_gate_passed": delivery_passed,
            "candidate_hash_matches_applied": bool(hash_match),
            "passed": gate_ok,
            "task_id": plan.task_id,
            "postflight_owned": True,
        }
        if failure_reasons:
            outcome_map["failure_reasons"] = failure_reasons[:8]
        if not gate_ok:
            outcome_map["ok"] = False
        return _make_receipt(
            "claim_gate",
            plan,
            wall_time_ms=elapsed,
            gate_passed=gate_ok,
            outcome=outcome_map,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "claim_gate",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={
                "action": "validate_context_claim_delivery",
                "error": str(exc)[:300],
                "postflight_owned": True,
            },
        )


def _exec_ultra_review(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Run the three ultra-review lanes on the workspace diff in a sandbox worktree.

    Review mode (not dry-run): security_sentry (diff pattern scan + bandit + ruff S rules on
    added lines), logic_breaker (mirror integrity + py_compile + ruff correctness rules) and
    ghost_regression (pytest re-run of mapped tests).  gate_passed is the service's gate; an
    empty diff or a missing check tool fails closed with the service's blocked_reason.
    """
    start = time.monotonic()
    cls = _try_port("ultra_review.UltraReviewService")
    if cls is None:
        return _make_receipt(
            "ultra_review",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="review",
                semantic_status="FAILED",
                error=_port_error("ultra_review.UltraReviewService"),
            ),
        )
    constraints = dict(plan.constraints or {})
    project_root = Path(str(constraints.get("workspace_root") or ".")).expanduser()
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(plan.task_id))[:120] or "task"
    # Post-candidate seam: explicit mapped tests (the visible test) and excluded test names
    # (the hidden verifier test); only passed when the caller supplies them.
    review_kwargs: dict[str, Any] = {}
    for key, kwarg in (
        ("ultra_review_regression_tests", "regression_tests"),
        ("ultra_review_excluded_tests", "excluded_tests"),
    ):
        if key in constraints:
            review_kwargs[kwarg] = [str(item) for item in list(constraints.get(key) or []) if str(item).strip()]
    try:
        payload = cls(project_root=project_root).run(
            dry_run=False,
            task=str(task_desc or plan.task_id)[:500],
            base_ref="HEAD",
            report_path=f".nexus/reports/ultra_review/{safe_id}_capability_report.json",
            sandbox_root=".nexus/reports/ultra_review/capability_sandboxes",
            **review_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - executor boundary must fail closed
        return _make_receipt(
            "ultra_review",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="review",
                semantic_status="FAILED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_ultra_review_err_{plan.task_id}"],
            ),
        )
    elapsed = int((time.monotonic() - start) * 1000)
    status = str(payload.get("status") or "")
    gate_passed = bool(payload.get("gate_passed")) and status == "PASS"
    semantic = {"PASS": "SUCCEEDED", "FAIL": "FAILED", "BLOCKED": "BLOCKED"}.get(status, "FAILED")
    fleet = [item for item in payload.get("fleet") or [] if isinstance(item, Mapping)]
    lanes = {
        str(item.get("lane")): {
            "status": item.get("status"),
            "executed_checks": list(item.get("executed_checks") or [])[:12],
            "unavailable_checks": [
                str(u.get("check")) for u in item.get("unavailable_checks") or [] if isinstance(u, Mapping)
            ],
        }
        for item in fleet
    }
    findings = [
        {
            "lane": f.get("lane"),
            "rule_id": f.get("rule_id"),
            "state": f.get("state"),
            "severity": f.get("severity"),
            "file": f.get("file"),
            "line": f.get("line"),
            "summary": str(f.get("summary") or "")[:160],
        }
        for f in (payload.get("findings") or [])[:20]
        if isinstance(f, Mapping)
    ]
    diff = payload.get("diff") if isinstance(payload.get("diff"), Mapping) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), Mapping) else {}
    evidence = [f"ev_ultra_review_{plan.task_id}"]
    for ref in (payload.get("report_path"), artifacts.get("diff")):
        if ref:
            evidence.append(str(ref))
    return _make_receipt(
        "ultra_review",
        plan,
        invoked=True,
        gate_passed=gate_passed,
        wall_time_ms=elapsed,
        outcome=_structured_outcome(
            action="review",
            semantic_status=semantic,
            evidence_refs=evidence,
            error=(str(payload.get("blocked_reason") or "") or None) if status == "BLOCKED" else None,
            result={
                "run_id": str(payload.get("run_id") or ""),
                "review_status": status,
                "mode": payload.get("mode"),
                "diff_bytes": int(diff.get("bytes") or 0),
                "changed_files_count": len(diff.get("changed_files") or []),
                "verified_findings": sum(1 for f in findings if f.get("state") == "VERIFIED_FINDING"),
            },
            regression_tests=list(
                (payload.get("ghost_regression") or {}).get("executed_tests") or []
                if isinstance(payload.get("ghost_regression"), Mapping)
                else []
            )[:12],
            excluded_regression_tests=list(payload.get("excluded_regression_tests") or [])[:12],
            lanes=lanes,
            executed_checks=sorted({c for lane in lanes.values() for c in lane["executed_checks"]}),
            findings=findings,
            blocked_reason=str(payload.get("blocked_reason") or ""),
            report_path=str(payload.get("report_path") or ""),
            physical_callable="nexus.engine.ultra_review_service.UltraReviewService.run",
        ),
    )


def _exec_learning_closure(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("learning_closure", plan, task_desc)


def _exec_metabolism_resume(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.services.metabolism_engine", "SessionMetabolism")
    if cls is None:
        return _make_receipt("metabolism_resume", plan, invoked=False, gate_passed=False,
                             outcome={"error": "SessionMetabolism not importable"})
    try:
        constraints = dict(plan.constraints or {})
        token_usage = int(constraints.get("metabolism_token_usage") or 0)
        token_limit = int(constraints.get("metabolism_token_limit") or 128000)
        workspace_root = Path(
            str(constraints.get("workspace_root") or "/tmp/nexus-metabolism")
        ).expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        inst = cls(token_limit=token_limit)
        inst.project_root = workspace_root
        inst.stack_path = workspace_root / ".nexus" / "metabolism" / "task_stack.json"
        should = bool(inst.should_distill(token_usage))
        if not should:
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "metabolism_resume",
                plan,
                wall_time_ms=elapsed,
                gate_passed=False,
                outcome=_structured_outcome(
                    action="threshold_check",
                    semantic_status="SKIPPED",
                    evidence_refs=[f"metabolism:threshold:{plan.task_id}"],
                    error="TOKEN_THRESHOLD_NOT_REACHED",
                    result={
                        "token_usage": token_usage,
                        "token_limit": token_limit,
                        "threshold_crossed": False,
                    },
                    physical_callable=(
                        "nexus.services.metabolism_engine."
                        "SessionMetabolism.should_distill"
                    ),
                ),
            )
        before = inst.load_checkpoint()
        before_hash = hashlib.sha256(
            json.dumps(before, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        inst.save_checkpoint(
            plan.task_id,
            "capability_executor",
            ["resume_after_distill"],
        )
        distill_result = inst.distill_local(
            {
                "goal": str(task_desc or plan.task_id),
                "done": [],
                "errors": [],
                "context_source": "CAPABILITY_PLAN",
            }
        )
        transaction_id = distill_result["tx"]
        checkpoint = inst.load_checkpoint()
        checkpoint_hash = hashlib.sha256(
            json.dumps(checkpoint, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        seed_path = workspace_root / ".nexus" / "metabolism" / "session_seed.json"
        seed_hash = hashlib.sha256(seed_path.read_bytes()).hexdigest()
        passed = bool(
            distill_result["status"] == "LOCAL_ONLY"
            and checkpoint.get("task_id") == plan.task_id
            and seed_path.is_file()
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "metabolism_resume",
            plan,
            wall_time_ms=elapsed,
            gate_passed=passed,
            outcome=_structured_outcome(
                action="distill_and_checkpoint",
                semantic_status="VERIFIED" if passed else "FAILED",
                evidence_refs=[
                    f"file:{inst.stack_path}",
                    f"file:{seed_path}",
                ],
                result={
                    "token_usage": token_usage,
                    "token_limit": token_limit,
                    "threshold_crossed": True,
                    "checkpoint_before_hash": before_hash,
                    "checkpoint_after_hash": checkpoint_hash,
                    "checkpoint_path": str(inst.stack_path),
                    "seed_path": str(seed_path),
                    "seed_hash": seed_hash,
                    "transaction_id": transaction_id,
                    "upload": distill_result["upload"],
                    "distill_status": distill_result["status"],
                    "resume_available": bool(checkpoint),
                    "pending_steps": list(checkpoint.get("pending_steps") or []),
                },
                physical_callable=(
                    "nexus.services.metabolism_engine."
                    "SessionMetabolism.distill"
                ),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "metabolism_resume",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "should_distill", "error": str(exc)[:300]},
        )


# ─── Mainchain residual production/beta (real method calls, not import-only) ──


def _exec_memory(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.core.memory_manager", "ProjectMemoryManager")
    if cls is None:
        return _make_receipt(
            "memory", plan, invoked=False, gate_passed=False,
            outcome={"error": "ProjectMemoryManager not importable"},
        )
    try:
        from pathlib import Path
        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or "")).resolve()
        query = str(constraints.get("memory_query") or task_desc or "").strip()
        if not str(constraints.get("workspace_root") or "").strip() or not query:
            return _make_receipt(
                "memory",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="search",
                    semantic_status="BLOCKED",
                    error="PROJECT_MEMORY_CONTEXT_REQUIRED",
                    evidence_refs=[f"ev_memory_blocked_{plan.task_id}"],
                    query=query,
                    search_performed=False,
                    physical_callable="nexus.core.memory_manager.ProjectMemoryManager.search",
                ),
            )
        inst = cls(root)
        hits = _memory_retrieve(inst, query, limit=5)
        findings_hits = _memory_findings_hits(root, query, limit=5)
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "memory",
            plan,
            gate_passed=True,  # non-claim execution health (#1869)
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="search",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_project_memory_search_{plan.task_id}"],
                result={"hit_count": len(hits), "root": str(root)},
                query=query[:200],
                hit_count=len(hits),
                findings_hit_count=len(findings_hits),
                search_performed=True,
                physical_callable="nexus.core.memory_manager.ProjectMemoryManager.search",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "memory", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
            outcome={"error": str(exc)[:300]},
        )


def _exec_plan_quality_gate(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.core.plan_quality_gate", "PlanQualityGate")
    if cls is None:
        return _make_receipt(
            "plan_quality_gate", plan, invoked=False, gate_passed=False,
            outcome={"error": "PlanQualityGate not importable"},
        )
    try:
        gate = cls()
        constraints = dict(plan.constraints) if isinstance(plan.constraints, Mapping) else {}
        required = (
            "intent_pass",
            "risk_score",
            "target_files",
            "impact_map",
            "acceptance_criteria",
            "deliverables",
            "steps",
            "handoff_readiness",
        )
        missing_inputs = [
            key for key in required if constraints.get(key) in (None, "", [], {})
        ]
        if missing_inputs:
            return _make_receipt(
                "plan_quality_gate",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="evaluate",
                    semantic_status="BLOCKED",
                    error="PLAN_QUALITY_CONTEXT_REQUIRED",
                    evidence_refs=[f"ev_plan_quality_blocked_{plan.task_id}"],
                    missing_inputs=missing_inputs,
                    input_fields_present=False,
                    impact_map_evaluated=False,
                    physical_callable="nexus.core.plan_quality_gate.PlanQualityGate.evaluate",
                ),
            )
        prediction = {
            "task_id": plan.task_id,
            "plan_id": plan.plan_id,
            "summary": task_desc or "",
            "steps": list(constraints["steps"]),
            "acceptance": list(constraints.get("acceptance") or constraints["acceptance_criteria"]),
            "handoff_readiness": float(constraints["handoff_readiness"]),
            "intent_pass": constraints["intent_pass"] is True,
            "risk_score": int(constraints["risk_score"]),
            "target_files": list(constraints["target_files"]),
            "acceptance_criteria": list(constraints["acceptance_criteria"]),
            "deliverables": list(constraints["deliverables"]),
        }
        state_metadata = {
            "task_id": plan.task_id,
            "phase": "P",
            "impact_map": dict(constraints["impact_map"]),
        }
        result = gate.evaluate(prediction, state_metadata)
        elapsed = int((time.monotonic() - start) * 1000)
        ok = bool(getattr(result, "passed", getattr(result, "ok", False)))
        return _make_receipt(
            "plan_quality_gate",
            plan,
            gate_passed=ok,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="evaluate",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_plan_quality_{plan.task_id}"],
                result={
                    "passed": ok,
                    "score": float(getattr(result, "score", 0.0) or 0.0),
                    "missing_fields": list(getattr(result, "missing_fields", []) or [])[:8],
                },
                passed=ok,
                input_fields_present=True,
                impact_map_evaluated=bool(state_metadata["impact_map"]),
                physical_callable="nexus.core.plan_quality_gate.PlanQualityGate.evaluate",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "plan_quality_gate", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
            outcome={"error": str(exc)[:300]},
        )


def _exec_semantic_searcher(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.services.semantic_searcher", "SemanticSearcher")
    if cls is None:
        return _make_receipt(
            "semantic_searcher", plan, invoked=False, gate_passed=False,
            outcome={"error": "SemanticSearcher not importable"},
        )
    try:
        from pathlib import Path

        from nexus.services.lancedb_roots import KNOWLEDGE, resolve_lancedb_root
        from nexus.services.memory_repository import MemoryRepository

        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or ".")).resolve()
        query = str(constraints.get("search_query") or task_desc or "").strip()
        table = str(constraints.get("search_table") or "policy").strip()
        limit = max(1, min(20, int(constraints.get("search_limit") or 5)))
        repository = MemoryRepository(resolve_lancedb_root(KNOWLEDGE, root, honor_env=False))
        inst = cls(repository)
        hits = list(inst.search(query=query, table_name=table, limit=limit) or [])[:limit]
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "semantic_searcher",
            plan,
            gate_passed=True,  # non-claim execution health (#1869)
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="search",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_semantic_search_{plan.task_id}"],
                result={"hits": hits, "table": table},
                query=query[:200],
                table=table,
                search_performed=True,
                hit_count=len(hits),
                physical_callable="nexus.services.semantic_searcher.SemanticSearcher.search",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "semantic_searcher", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
            outcome={"error": str(exc)[:300]},
        )


def _exec_pregate(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from pathlib import Path
        detect_project_language = resolve_port("pregate.detect_project_language")
        run_cli_pregate = resolve_port("pregate.run_cli_pregate")

        constraints = dict(plan.constraints or {})
        root = Path(str(constraints.get("workspace_root") or ".")).resolve()
        lang = detect_project_language(root)
        explicit_commands = constraints.get("verify_commands") or []
        cmds = [str(item) for item in explicit_commands if str(item).strip()]
        if not cmds:
            return _make_receipt(
                "pregate",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="run_cli_pregate",
                    semantic_status="BLOCKED",
                    error="EXPLICIT_VERIFY_COMMANDS_REQUIRED",
                    evidence_refs=[f"ev_pregate_blocked_{plan.task_id}"],
                    command_count=0,
                    all_passed=False,
                    results=[],
                    physical_callable="nexus.engine.cli_pregate.run_cli_pregate",
                ),
            )
        timeout_sec = max(1, min(120, int(constraints.get("verify_timeout_sec") or 30)))
        all_passed, results = run_cli_pregate(
            root,
            cmds,
            timeout_per_cmd=timeout_sec,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "pregate",
            plan,
            gate_passed=bool(all_passed),
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run_cli_pregate",
                semantic_status="SUCCEEDED" if all_passed else "FAILED",
                evidence_refs=[f"ev_pregate_execution_{plan.task_id}"],
                result={
                    "language": sorted(lang),
                    "command_count": len(cmds),
                    "all_passed": bool(all_passed),
                },
                language=sorted(lang),
                command_count=len(cmds),
                all_passed=bool(all_passed),
                results=list(results or [])[:8],
                physical_callable="nexus.engine.cli_pregate.run_cli_pregate",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "pregate", plan, invoked=False, gate_passed=False, wall_time_ms=elapsed,
            outcome={"error": str(exc)[:300]},
        )


def _exec_harness_preflight_sensor(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    """Evaluate feed-forward readiness without consuming the repair verifier."""
    start = time.monotonic()
    constraints = plan.constraints
    if not isinstance(constraints, Mapping):
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=False, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error="MALFORMED_PREFLIGHT_CONSTRAINTS",
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
            ),
        )

    commands = constraints.get("verify_commands")
    if (
        not isinstance(commands, (list, tuple))
        or not commands
        or not all(isinstance(item, str) and item.strip() for item in commands)
    ):
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=True, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error="VERIFY_COMMAND_WIRING_REQUIRED",
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
                verifier_executed=False, command_count=0,
            ),
        )

    route = constraints.get("route") or {}
    if not isinstance(route, Mapping):
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=False, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error="MALFORMED_PREFLIGHT_ROUTE",
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
                verifier_executed=False,
            ),
        )

    pending = constraints.get("pending_capabilities", ())
    selected = constraints.get("selected_capabilities", ())
    if (
        not isinstance(pending, (list, tuple))
        or not all(isinstance(item, str) and item.strip() for item in pending)
    ):
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=False, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error="MALFORMED_PENDING_CAPABILITIES",
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
                verifier_executed=False,
            ),
        )
    if (
        not isinstance(selected, (list, tuple))
        or not all(isinstance(item, str) and item.strip() for item in selected)
    ):
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=False, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error="MALFORMED_SELECTED_CAPABILITIES",
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
                verifier_executed=False,
            ),
        )
    try:
        build_harness_preflight_sensor = resolve_port("harness.build_harness_preflight_sensor")

        task_type = str(constraints.get("task_type") or "repair")
        features = route.get("route_features", {})
        if not isinstance(features, Mapping):
            raise ValueError("MALFORMED_PREFLIGHT_ROUTE_FEATURES")
        text = f"{task_desc} {task_type}".lower()
        risk_score = int(features.get("risk_score") or 0)
        candidate_count = int(features.get("candidate_count") or 1)
        simple_hidden = bool(features.get("simple_hidden_bugfix"))
        governance = bool(
            features.get("has_governance_signal")
            or "governance" in text
            or "policy" in text
        )
        bdd_required = bool(
            route.get("bdd_acceptance")
            or features.get("bdd_acceptance_required")
            or "given-when-then" in text
            or "business acceptance" in text
        )
        expected_lane = (
            "lite"
            if simple_hidden and risk_score < 30 and candidate_count <= 1
            else "hardened"
            if risk_score >= 70 or governance
            else "standard"
        )
        expected_reasons = []
        if pending:
            expected_reasons.append("pending_executor_present")
        if bdd_required and "bdd_acceptance_skill" not in selected:
            expected_reasons.append("bdd_acceptance_required")
        if not expected_reasons:
            expected_reasons.append("preflight_clear")
        expected_wired = not bool(pending)
        expected_escalation = bool(pending) or (
            bdd_required and "bdd_acceptance_skill" not in selected
        )

        sensor = build_harness_preflight_sensor(
            task_desc=task_desc,
            task_type=task_type,
            route=dict(route),
            pending_capabilities=tuple(pending),
            selected_capabilities=tuple(selected),
        )
        if not isinstance(sensor, Mapping) or sensor.get("schema_version") != "nexus_harness_preflight_sensor.v1":
            raise ValueError("INVALID_HARNESS_PREFLIGHT_SENSOR")
        required = ("sensor", "capability_wired", "executor_ready", "escalation_required", "reasons")
        if any(key not in sensor for key in required) or sensor.get("sensor") != "harness_preflight":
            raise ValueError("INCOMPLETE_HARNESS_PREFLIGHT_SENSOR")
        if any(not isinstance(sensor.get(key), bool) for key in ("capability_wired", "executor_ready", "escalation_required", "bdd_acceptance_required")):
            raise ValueError("MALFORMED_HARNESS_PREFLIGHT_SENSOR_TYPES")
        if sensor.get("pending_capabilities") != list(pending) or sensor.get("selected_capabilities") != list(selected):
            raise ValueError("INCONSISTENT_HARNESS_PREFLIGHT_CAPABILITIES")
        if sensor.get("capability_wired") is not expected_wired or sensor.get("executor_ready") is not expected_wired:
            raise ValueError("INCONSISTENT_HARNESS_PREFLIGHT_READINESS")
        if sensor.get("bdd_acceptance_required") is not bdd_required:
            raise ValueError("INCONSISTENT_HARNESS_PREFLIGHT_BDD")
        if sensor.get("escalation_required") is not expected_escalation:
            raise ValueError("INCONSISTENT_HARNESS_PREFLIGHT_ESCALATION")
        if sensor.get("reasons") != expected_reasons or sensor.get("cost_lane") != expected_lane:
            raise ValueError("INCONSISTENT_HARNESS_PREFLIGHT_PROJECTION")
        passed = expected_wired and not expected_escalation
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=True, gate_passed=passed,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor",
                semantic_status="SUCCEEDED" if passed else "BLOCKED",
                evidence_refs=[f"ev_harness_preflight_sensor_{plan.task_id}"],
                result=dict(sensor), verifier_executed=False, candidate_required=True,
                **dict(sensor),
            ),
        )
    except Exception as exc:
        return _make_receipt(
            "harness_preflight_sensor", plan, invoked=False, gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="evaluate_harness_preflight_sensor", semantic_status="BLOCKED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_harness_preflight_blocked_{plan.task_id}"],
                verifier_executed=False,
            ),
        )


def _exec_ddtree(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not _provider_auth_allowed(require_external=True) and not bool(
        (plan.constraints or {}).get("allow_fixture_model_boundary")
    ):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt("ddtree", plan, wall_time_ms=elapsed)
    cls = _try_port("ddtree.DDTreeAdapter")
    if cls is None:
        return _make_receipt(
            "ddtree",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="plan",
                semantic_status="FAILED",
                error=_port_error("ddtree.DDTreeAdapter"),
            ),
        )
    try:
        candidates = _candidate_pool(plan)
        if not candidates:
            return _no_candidate_pool_receipt("ddtree", plan, start)
        inst = cls()
        try:
            max_candidates = max(1, int((plan.constraints or {}).get("ddtree_max_candidates") or 2))
        except (TypeError, ValueError):
            max_candidates = 2
        result = inst.plan(
            candidates,
            enabled=True,
            max_candidates=max_candidates,
            task_desc=str(task_desc or ""),
        )
        elapsed = int((time.monotonic() - start) * 1000)
        ok = result is not None
        return _make_receipt(
            "ddtree",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="plan",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_ddtree_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable="nexus.engine.ddtree_adapter.DDTreeAdapter.plan",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "ddtree",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="plan",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


# Counted A/B lanes (NEXUS_SYMMETRIC_PROMPT): the learn reports reach the with-Nexus prompt
# (consumer payload -> [NEXUS MODEL CONTEXT]).  Read from the shared project learn store they
# depended on earlier runs inside the 300-row phase-SLO window and carried wall-clock
# timestamps and host paths, so back-to-back counted runs differed in prompt text through timing
# alone.  In counted lanes they run on a fresh, empty, per-call store and carry no timestamp or
# path, so the fields are identical across runs (empty store: phase_slo_pass=True, all counts 0).
# Fixed, documented value for wall-clock fields in counted lanes (valid ISO-8601, so the prompt
# audit's iso8601 format still holds).
COUNTED_FIXED_TIMESTAMP = "1970-01-01T00:00:00+00:00"
_NONDETERMINISTIC_REPORT_KEYS = frozenset({"timestamp", "generated_at", "updated_at"})


def _counted_learn_lane() -> bool:
    return os.environ.get("NEXUS_SYMMETRIC_PROMPT", "").strip().lower() in {"1", "true", "yes"}


def _without_wall_clock(value: Any, depth: int = 0) -> Any:
    """Report copy with every timestamp-like key set to ``COUNTED_FIXED_TIMESTAMP``."""

    if depth > 8:
        return value
    if isinstance(value, Mapping):
        return {
            k: (
                COUNTED_FIXED_TIMESTAMP
                if k in _NONDETERMINISTIC_REPORT_KEYS
                else _without_wall_clock(v, depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_without_wall_clock(item, depth + 1) for item in value]
    return value



def _exec_learn_mode(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    cls = _try_import_class("nexus.research.learn_mode", "LearnModeService")
    if cls is None:
        return _make_receipt(
            "learn_mode",
            plan,
            invoked=False,
            gate_passed=False,
            outcome=_structured_outcome(
                action="build_report",
                semantic_status="FAILED",
                error="LearnModeService not importable",
            ),
        )
    try:
        counted = _counted_learn_lane()
        isolated = tempfile.TemporaryDirectory(prefix="nexus-counted-learn-") if counted else None
        try:
            project_root, run_root, run_id = _resolve_learn_store(plan)
            if isolated is not None:
                project_root = run_root = Path(isolated.name)
            inst = cls(project_root=project_root, run_root=run_root)
            if hasattr(inst, "build_report") and callable(inst.build_report):
                result = inst.build_report()
                action = "build_report"
            elif hasattr(inst, "build_phase_slo_report") and callable(
                inst.build_phase_slo_report
            ):
                result = inst.build_phase_slo_report(window=1)
                action = "build_phase_slo_report"
            else:
                raise RuntimeError("LearnModeService has no production report method")
            output_paths = [run_root / ".nexus" / "reports" / "learn"]
            _assert_outputs_in_run_root(output_paths, run_root)
        finally:
            if isolated is not None:
                isolated.cleanup()
        elapsed = int((time.monotonic() - start) * 1000)
        ok = result is not None
        report = result if isinstance(result, Mapping) else {"value": str(result)[:200]}
        # Counted lanes: no host path in the outcome (it reaches the prompt; nexus-runtime #218).
        store_fields: dict[str, Any] = (
            {}
            if counted
            else {
                "resolved_run_root": str(run_root),
                "output_paths": [str(p) for p in output_paths],
            }
        )
        return _make_receipt(
            "learn_mode",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action=action,
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_learn_mode_{plan.task_id}"],
                result=_without_wall_clock(report) if counted else report,
                physical_callable=f"nexus.research.learn_mode.LearnModeService.{action}",
                task_hint=str(task_desc or "")[:80],
                run_id=run_id,
                **store_fields,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "learn_mode",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="build_report",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_learn_phase_slo(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.research.learn_mode import LearnModeService

        counted = _counted_learn_lane()
        isolated = tempfile.TemporaryDirectory(prefix="nexus-counted-learn-") if counted else None
        try:
            project_root, run_root, run_id = _resolve_learn_store(plan)
            if isolated is not None:
                project_root = run_root = Path(isolated.name)
            lm = LearnModeService(project_root=project_root, run_root=run_root)
            # Same window as ``learn:phase-slo`` (default 300); window=1 judged one row at most.
            window = max(1, int((plan.constraints or {}).get("phase_slo_window") or 300))
            result = lm.build_phase_slo_report(window=window)
            output_paths = [run_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"]
            _assert_outputs_in_run_root(output_paths, run_root)
        finally:
            if isolated is not None:
                isolated.cleanup()
        physical = "nexus.research.learn_mode.LearnModeService.build_phase_slo_report"
        elapsed = int((time.monotonic() - start) * 1000)
        ok = result is not None
        report = result if isinstance(result, Mapping) else {"value": str(result)[:200]}
        # Counted lanes: no host path in the outcome (it reaches the prompt; nexus-runtime #218).
        store_fields: dict[str, Any] = (
            {}
            if counted
            else {
                "resolved_run_root": str(run_root),
                "output_paths": [str(p) for p in output_paths],
            }
        )
        return _make_receipt(
            "learn_phase_slo",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="build_phase_slo_report",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_learn_phase_slo_{plan.task_id}"],
                result=_without_wall_clock(report) if counted else report,
                physical_callable=physical,
                run_id=run_id,
                **store_fields,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "learn_phase_slo",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="build_phase_slo_report",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_acceptance_check(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Semantic-success gated acceptance with joint verifier evidence allowlist.

    VERIFIED alone is not enough. PASS requires all of:
      semantic_status in VERIFIED/ACCEPTED/COMPLETE
      verifier_status=pass
      non-empty verifier_artifact
      non-empty source_hash
      non-empty evidence_refs (never invent acceptance:<task_id>)
    UNVERIFIED / missing fields always fail closed.
    """
    start = time.monotonic()
    try:
        mod = resolve_port("completion.enforcer_module")
        decide = getattr(mod, "decide_completion", None)
        constraints = dict(plan.constraints or {})
        semantic_in = str(
            constraints.get("semantic_status")
            or constraints.get("completion_status")
            or "UNVERIFIED"
        ).strip().upper()
        verifier_status = str(constraints.get("verifier_status") or "").strip().lower()
        verifier_artifact = str(constraints.get("verifier_artifact") or "").strip()
        source_hash = str(constraints.get("source_hash") or "").strip()
        raw_refs = constraints.get("evidence_refs")
        if isinstance(raw_refs, (list, tuple)):
            evidence_refs = [str(x).strip() for x in raw_refs if str(x).strip()]
        else:
            evidence_refs = []
        # Never mint acceptance:<task_id> as pass evidence.
        missing_evidence: list[str] = []
        if semantic_in not in _SEMANTIC_SUCCESS_STATUSES:
            missing_evidence.append("semantic_status_not_success")
        if verifier_status not in {"pass", "passed", "success", "ok"}:
            missing_evidence.append("verifier_status_not_pass")
        if not verifier_artifact:
            missing_evidence.append("missing_verifier_artifact")
        if not source_hash:
            missing_evidence.append("missing_source_hash")
        if not evidence_refs:
            missing_evidence.append("missing_evidence_refs")

        if not callable(decide):
            elapsed = int((time.monotonic() - start) * 1000)
            return _make_receipt(
                "acceptance_check",
                plan,
                invoked=False,
                gate_passed=False,
                wall_time_ms=elapsed,
                outcome={
                    "action": "decide_completion",
                    "error": "decide_completion_not_callable",
                },
            )

        payload = {
            "task_id": plan.task_id,
            "statement": task_desc,
            "status": str(constraints.get("status") or "INCOMPLETE"),
            "semantic_status": semantic_in or "UNVERIFIED",
            "evidence_refs": list(evidence_refs),
            "verifier_status": verifier_status,
            "verifier_artifact": verifier_artifact,
            "source_hash": source_hash,
        }
        result = decide(payload)
        elapsed = int((time.monotonic() - start) * 1000)
        semantic = str(getattr(result, "semantic_status", "") or semantic_in or "UNVERIFIED").strip().upper()
        success = (
            semantic in _SEMANTIC_SUCCESS_STATUSES
            and not missing_evidence
        )
        outcome = {
            "action": "decide_completion",
            "result": str(result)[:200],
            "semantic_status": semantic or "UNVERIFIED",
            "verifier_status": verifier_status,
            "verifier_artifact": verifier_artifact[:80] if verifier_artifact else "",
            "source_hash": source_hash[:80] if source_hash else "",
            "evidence_refs": list(evidence_refs)[:8],
            "passed": success,
            "task_id": plan.task_id,
        }
        if missing_evidence:
            outcome["missing_evidence"] = missing_evidence
            outcome["ok"] = False
        if not success:
            outcome["ok"] = False
        return _make_receipt(
            "acceptance_check",
            plan,
            wall_time_ms=elapsed,
            gate_passed=success,
            outcome=outcome,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "acceptance_check",
            plan,
            invoked=False,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "decide_completion", "error": str(exc)[:300]},
        )


def _exec_jit_validation(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.core.jit_tool_injector import JITToolInjector
        constraints = dict(plan.constraints or {})
        all_tools = [
            str(item)
            for item in list(constraints.get("jit_all_tools") or [])
            if str(item).strip()
        ]
        token_usage = max(0, int(constraints.get("jit_token_usage") or 0))
        if not all_tools:
            return _make_receipt(
                "jit_validation",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="apply_mask+check_token_quota",
                    semantic_status="BLOCKED",
                    error="JIT_TOOL_CATALOG_REQUIRED",
                    evidence_refs=[f"ev_jit_blocked_{plan.task_id}"],
                    mask_applied=False,
                    quota_checked=False,
                ),
            )
        selected_tools = JITToolInjector.apply_mask(task_desc, all_tools)
        quota_ok = bool(JITToolInjector.check_token_quota(token_usage))
        ok = quota_ok and bool(selected_tools)
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "jit_validation",
            plan,
            gate_passed=ok,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="apply_mask+check_token_quota",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_jit_mask_{plan.task_id}"],
                result={
                    "selected_tools": list(selected_tools),
                    "available_tool_count": len(all_tools),
                    "token_usage": token_usage,
                    "quota_limit": JITToolInjector.MAX_TOKEN_PER_SHARD,
                },
                mask_applied=True,
                # apply_mask is a self-declared keyword mock (jit_tool_injector.py); only the
                # quota check is real.  Say so on the receipt until a real mask exists.
                simulated=True,
                mask_kind="keyword_mock",
                claim_boundary={
                    "simulated": True,
                    "claim": "SIMULATED",
                    "reason": "jit_mask_is_keyword_mock_until_real_mask",
                    "real_parts": ["check_token_quota"],
                },
                quota_checked=True,
                quota_passed=quota_ok,
                selected_tool_count=len(selected_tools),
                physical_callable=(
                    "nexus.core.jit_tool_injector.JITToolInjector."
                    "apply_mask+check_token_quota"
                ),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "jit_validation",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome={"action": "check_token_quota", "error": str(exc)[:300]},
        )


def _exec_semantic_failure_sensor(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from pathlib import Path

        from nexus.services.bug_fingerprint import find_similar_bugs

        hits = find_similar_bugs(
            Path(".").resolve(),
            traceback=str(task_desc or plan.task_id),
            category="",
            top_k=1,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        hit_list = list(hits or [])
        return _make_receipt(
            "semantic_failure_sensor",
            plan,
            wall_time_ms=elapsed,
            gate_passed=True,  # non-claim execution health (#1869)
            outcome=_structured_outcome(
                action="find_similar_bugs",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_semantic_failure_sensor_{plan.task_id}"],
                result={"hit_count": len(hit_list), "top_hit_type": type(hit_list[0]).__name__ if hit_list else "none"},
                physical_callable="nexus.services.bug_fingerprint.find_similar_bugs",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "semantic_failure_sensor",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="find_similar_bugs",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_bdd_acceptance_skill(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    # Shared acceptance semantics via real acceptance_check engine.
    base = _exec_acceptance_check(plan, task_desc)
    base_out = dict(base.outcome or {})
    err = base_out.get("error") if not base.gate_passed else None
    return _make_receipt(
        "bdd_acceptance_skill",
        plan,
        invoked=base.invoked,
        gate_passed=base.gate_passed,
        wall_time_ms=(base.telemetries or {}).get("wall_time_ms"),
        outcome=_structured_outcome(
            action="acceptance_check",
            semantic_status="SUCCEEDED" if base.gate_passed else "FAILED",
            evidence_refs=[f"ev_bdd_acceptance_{plan.task_id}"]
            + list(base_out.get("evidence_refs") or [])[:4],
            result={
                "delegated": "acceptance_check",
                "acceptance_gate_passed": bool(base.gate_passed),
                **{
                    k: base_out[k]
                    for k in ("semantic_status", "verifier_status", "status")
                    if k in base_out
                },
            },
            physical_callable="nexus.core.capability_executor_registry._exec_acceptance_check",
            error=str(err)[:300] if err else None,
        ),
    )


def _exec_judge_panel(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Rank the plan's real candidate pool with a judge provider.

    Candidates come from ``candidate_pool`` (request ``codeintel.judge_panel_candidates`` /
    ``candidate_pool``); nothing is fabricated.  Providers: ``NEXUS_LLM_JUDGE_PROVIDERS``
    (fake / gemini / codex / ollama).  With ``NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`` and no
    configured provider the Ollama judge (Workforce local worker, M5 tunnel) is used; a local
    authorization alone never admits a remote command provider.
    """
    start = time.monotonic()
    allow_fixture = bool((plan.constraints or {}).get("allow_fixture_model_boundary"))
    external_ok = _provider_auth_allowed(require_external=True)
    local_ok = _provider_auth_allowed(require_local_model=True)
    if not (external_ok or local_ok or allow_fixture):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt("judge_panel", plan, wall_time_ms=elapsed)
    candidates_raw = _candidate_pool(plan)
    if not candidates_raw:
        return _no_candidate_pool_receipt("judge_panel", plan, start)
    try:
        AutoreasonCandidate = resolve_port("autoreason.AutoreasonCandidate")
        DeterministicFakeJudgeProvider = resolve_port("judge.DeterministicFakeJudgeProvider")
        JudgeProviderUnavailable = resolve_port("judge.JudgeProviderUnavailable")
        OllamaJudgeProvider = resolve_port("judge.OllamaJudgeProvider")
        build_judge_providers_from_env = resolve_port("judge.build_judge_providers_from_env")

        candidates = [
            AutoreasonCandidate.from_mapping(dict(item), index)
            for index, item in enumerate(candidates_raw)
        ]
        ids = [c.candidate_id for c in candidates]
        if len(candidates) < 2 or len(set(ids)) != len(ids):
            return _make_receipt(
                "judge_panel",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="rank",
                    semantic_status="BLOCKED",
                    error="JUDGE_REQUIRES_TWO_DISTINCT_CANDIDATES",
                    evidence_refs=[f"ev_judge_panel_blocked_{plan.task_id}"],
                    candidate_count=len(candidates),
                ),
            )
        try:
            providers = list(build_judge_providers_from_env() or [])
            if not external_ok:
                # Local-only authorization: no remote command judges.
                providers = [
                    p
                    for p in providers
                    if isinstance(p, (OllamaJudgeProvider, DeterministicFakeJudgeProvider))
                ]
            if not providers and local_ok:
                providers = [OllamaJudgeProvider.from_policy()]
            if not providers and allow_fixture:
                providers = [DeterministicFakeJudgeProvider()]
        except JudgeProviderUnavailable as exc:
            return _auth_blocked_receipt(
                "judge_panel",
                plan,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                reason=f"BLOCKED_PROVIDER_UNAVAILABLE:{str(exc)[:200]}",
            )
        if not providers:
            elapsed = int((time.monotonic() - start) * 1000)
            return _auth_blocked_receipt(
                "judge_panel",
                plan,
                wall_time_ms=elapsed,
                reason="BLOCKED_EXTERNAL_AUTH:no_judge_provider_configured",
            )
        provider = providers[0]
        try:
            result = provider.rank(task_desc=str(task_desc or plan.task_id), candidates=candidates)
        except JudgeProviderUnavailable as exc:
            return _auth_blocked_receipt(
                "judge_panel",
                plan,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                reason=f"BLOCKED_PROVIDER_UNAVAILABLE:{str(exc)[:200]}",
            )
        elapsed = int((time.monotonic() - start) * 1000)
        ranking = (
            [str(item) for item in result.get("ranking") or []]
            if isinstance(result, Mapping)
            else []
        )
        ok = sorted(ranking) == sorted(ids)
        provider_name = str(getattr(provider, "name", type(provider).__name__))
        return _make_receipt(
            "judge_panel",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            model_calls=1 if provider_name == "ollama" else 0,
            outcome=_structured_outcome(
                action="rank",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                error=None if ok else "JUDGE_RANKING_NOT_A_PERMUTATION_OF_CANDIDATES",
                evidence_refs=[f"ev_judge_panel_{plan.task_id}"]
                + (
                    [f"judge_response_sha256:{result.get('response_sha256')}"]
                    if isinstance(result, Mapping) and result.get("response_sha256")
                    else []
                ),
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                candidate_count=len(candidates),
                candidate_ids=ids,
                ranking=ranking,
                winner=ranking[0] if ranking else "",
                physical_callable=f"{type(provider).__module__}.{type(provider).__name__}.rank",
                provider=provider_name,
                judge_model=str(result.get("model") or "") if isinstance(result, Mapping) else "",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "judge_panel",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="rank",
                semantic_status="FAILED",
                error=str(exc)[:300],
                evidence_refs=[f"ev_judge_panel_err_{plan.task_id}"],
            ),
        )


def _exec_llm_judge_panel(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-13: legacy alias of judge_panel; fail closed with an explicit reason."""
    return _archived_receipt("llm_judge_panel", plan, task_desc)


# ── Phase 3: thin adapters over existing unregistered engines ───────────────


def _exec_architecture_scout(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Distant-scout pivot plan, only when the real plateau detector fires.

    The ASI ledger comes from the plan (``asi_failure_records``, the same channel as
    asi_constraint_extractor); ``runtime_decision.detect_plateau`` is the detector the
    research flow uses.  No ledger / no plateau fails closed with the detector's reason
    instead of passing a SKIPPED plan.
    """
    start = time.monotonic()
    try:
        from nexus.research.architecture_scout import DistantScoutPlanner
        from nexus.research.flow.runtime_decision import detect_plateau

        constraints = dict(plan.constraints or {})
        ledger = [
            dict(row)
            for row in constraints.get("asi_failure_records", []) or []
            if isinstance(row, Mapping)
        ]
        plateau = dict(detect_plateau(ledger))
        detected = bool(plateau.get("detected"))
        evidence = [f"ev_architecture_scout_{plan.task_id}"] + [
            f"asi:{row.get('run_id')}" for row in ledger[-4:] if row.get("run_id")
        ]
        if not detected:
            reason = str(plateau.get("reason") or "plateau_not_detected")
            return _make_receipt(
                "architecture_scout",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="detect_plateau",
                    semantic_status="BLOCKED",
                    error=f"PLATEAU_NOT_DETECTED:{reason}",
                    evidence_refs=evidence,
                    result=plateau,
                    plateau_detected=False,
                    plan_status="NOT_PLANNED",
                    ledger_records=len(ledger),
                    physical_callable="nexus.research.flow.runtime_decision.detect_plateau",
                ),
            )
        result = DistantScoutPlanner().plan(
            task_desc=str(task_desc or plan.task_id),
            plateau=plateau,
            asi_ledger=ledger,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        ok = (
            isinstance(result, Mapping)
            and result.get("status") == "READY"
            and result.get("gate_passed") is True
        )
        return _make_receipt(
            "architecture_scout",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="plan",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=evidence,
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                plateau_detected=True,
                plateau=plateau,
                plan_status=str(result.get("status") if isinstance(result, Mapping) else ""),
                ledger_records=len(ledger),
                physical_callable="nexus.research.architecture_scout.DistantScoutPlanner.plan",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "architecture_scout",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="plan",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_asi_constraint_extractor(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        ASIConstraintExtractor = resolve_port("asi.ASIConstraintExtractor")

        constraints = dict(plan.constraints or {})
        records = [
            dict(row)
            for row in constraints.get("asi_failure_records", []) or []
            if isinstance(row, Mapping)
        ]
        if len(records) < 2:
            return _make_receipt(
                "asi_constraint_extractor",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="extract",
                    semantic_status="BLOCKED",
                    error="TWO_REAL_DISCARD_FAILURES_REQUIRED",
                    evidence_refs=[f"ev_asi_blocked_{plan.task_id}"],
                    records_count=len(records),
                    constraints_count=0,
                    physical_callable="nexus.engine.asi_constraints.ASIConstraintExtractor.extract",
                ),
            )
        result = ASIConstraintExtractor(min_failures=2).extract(
            records,
            task_id=plan.task_id,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        count = int(result.get("constraints_count") or 0) if isinstance(result, Mapping) else 0
        extracted = list(result.get("constraints") or []) if isinstance(result, Mapping) else []
        evidence = [
            str(ref)
            for item in extracted
            if isinstance(item, Mapping)
            for ref in item.get("evidence_refs", []) or []
            if str(ref)
        ]
        ok = count > 0 and bool(evidence)
        return _make_receipt(
            "asi_constraint_extractor",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="extract",
                semantic_status="VERIFIED" if ok else "FAILED",
                evidence_refs=evidence or [f"ev_asi_constraint_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable="nexus.engine.asi_constraints.ASIConstraintExtractor.extract",
                task_hint=str(task_desc or "")[:80],
                records_count=len(records),
                constraints_count=count,
                extracted_evidence_refs=evidence,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "asi_constraint_extractor",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="extract",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_benchmark(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("benchmark", plan, task_desc)


_COMMITTEE_PASS_STATUSES: frozenset[str] = frozenset({"VERIFIED"})


def _exec_committee(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not (
        _provider_auth_allowed(require_local_model=True)
        or _provider_auth_allowed(require_external=True)
    ):
        return _auth_blocked_receipt(
            "committee",
            plan,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            reason="BLOCKED_EXTERNAL_AUTH:committee_candidates",
        )
    try:
        from nexus.committee.controller import CommitteeControllerV263

        constraints = dict(plan.constraints or {})
        raw = [
            dict(row)
            for row in constraints.get("committee_proposals", []) or []
            if isinstance(row, Mapping)
        ]
        # Proposals name their proposer "proposer_id": the canonical context seam rejects any
        # request key containing "model", so a "model" field could never reach this executor
        # through UnifiedRuntime. "model" is still read for direct in-process callers.
        valid = []
        for row in raw:
            proposer = str(row.get("proposer_id") or row.get("model") or "").strip()
            if not (proposer and str(row.get("raw_label") or "").strip() and list(row.get("artifacts") or [])):
                continue
            try:
                attempt = max(1, int(row.get("attempt") or 1))
            except (TypeError, ValueError):
                attempt = 1
            valid.append({**row, "proposer_id": proposer, "attempt": attempt})
        if len(valid) < 2:
            return _make_receipt(
                "committee",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="process_proposals",
                    semantic_status="BLOCKED",
                    error="TWO_INDEPENDENT_CANDIDATES_REQUIRED",
                    evidence_refs=[f"ev_committee_blocked_{plan.task_id}"],
                    candidate_count=len(valid),
                    physical_callable="nexus.committee.controller.CommitteeControllerV263.process_proposals",
                ),
            )
        # argv lists pass through unchanged (the verifier's allowlist matches real argv);
        # only a plain string is left for the verifier to split without a shell.
        verify_commands: list[Any] = []
        for item in constraints.get("committee_verify_commands") or []:
            if isinstance(item, (list, tuple)):
                argv = [str(part) for part in item]
                if argv and all(part.strip() for part in argv):
                    verify_commands.append(argv)
            elif str(item).strip():
                verify_commands.append(str(item))
        execution_verifier = None
        verifiers = None
        if verify_commands:
            from nexus.committee.execution_verifier import PatchExecutionVerifier

            try:
                committee_root = _scoped_workspace(constraints, Path(".").resolve())
            except _ScopeError as scope:
                return _scope_blocked_receipt("committee", plan, str(scope), start)
            try:
                verify_timeout = max(1, min(120, int(constraints.get("committee_verify_timeout_sec") or 30)))
            except (TypeError, ValueError):
                verify_timeout = 30
            execution_verifier = PatchExecutionVerifier(
                workspace_root=committee_root,
                commands=verify_commands,
                task_id=str(plan.task_id),
                timeout_sec=verify_timeout,
            )
            verifiers = [execution_verifier]
        ctrl = CommitteeControllerV263(
            task_id=str(plan.task_id), domains=["mainchain"], verifiers=verifiers
        )
        if not ctrl.enabled:
            return _make_receipt(
                "committee",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="process_proposals",
                    semantic_status="BLOCKED",
                    error="COMMITTEE_FEATURE_DISABLED",
                    evidence_refs=[f"ev_committee_disabled_{plan.task_id}"],
                    candidate_count=len(valid),
                    physical_callable="nexus.committee.controller.CommitteeControllerV263.process_proposals",
                ),
            )
        result = ctrl.process_proposals(valid)
        elapsed = int((time.monotonic() - start) * 1000)
        candidates = list(getattr(result, "candidates", []) or [])
        verdicts = list(getattr(result, "verdicts", []) or [])
        winner_id = str(getattr(result, "winner_id", "") or "")
        failure_bucket = str(getattr(result, "failure_bucket", "") or "")
        # An abstention only counts when verdicts exist: with no verifier nothing was judged.
        explicit_abstain = bool(verdicts) and not winner_id and (
            bool(getattr(result, "abstained", False))
            or failure_bucket.upper() in {"ABSTAIN", "NO_WINNER"}
        )
        winner = next((c for c in candidates if getattr(c, "candidate_id", "") == winner_id), None)
        # Fail closed: the committee passes only when a winner exists and that winner has at
        # least one passing verdict.  No verified candidate (every verifier refused or failed,
        # e.g. ``not_executed:no_os_barrier``, or an all-abstain round) is never a pass.
        verified_ids = {
            str(getattr(v, "candidate_id", "") or "")
            for v in verdicts
            if getattr(v, "passed", False)
        }
        winner_verified = bool(winner_id) and winner_id in verified_ids
        # #2454: the pass decision goes through the shared fail-closed helper; only an
        # exact "VERIFIED" status allows (abstain and unverified both block).
        committee_status = (
            "VERIFIED" if winner_verified else ("ABSTAIN" if explicit_abstain else "NOT_VERIFIED")
        )
        committee_decision = decide(committee_status, success=_COMMITTEE_PASS_STATUSES)
        ok = (
            len(candidates) >= 2
            and bool(verdicts)
            and committee_decision.decision is Decision.ALLOW
        )
        verdict_rows = [
            {
                "verifier": str(getattr(v, "verifier_name", "") or getattr(v, "critic_name", "")),
                "candidate_id": str(getattr(v, "candidate_id", "") or ""),
                "verdict": "pass" if getattr(v, "passed", False) else "fail",
                "score": float(getattr(v, "score", 0.0) or 0.0),
            }
            for v in verdicts
        ]
        return _make_receipt(
            "committee",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="process_proposals",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_committee_{plan.task_id}"],
                error=""
                if ok
                else (
                    "COMMITTEE_NO_VERIFIED_CANDIDATE"
                    if verdicts
                    else "NO_COMMITTEE_VERIFIER_VERDICTS"
                ),
                result={
                    "task_id": getattr(result, "task_id", ""),
                    "winner_id": winner_id,
                    "abstained": bool(getattr(result, "abstained", False)),
                    "failure_bucket": failure_bucket,
                    "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
                    "verifier_gap": float(getattr(result, "verifier_gap", 0.0) or 0.0),
                    "receipt_type": type(result).__name__,
                },
                physical_callable="nexus.committee.controller.CommitteeControllerV263.process_proposals",
                candidate_count=len(candidates),
                verdict_count=len(verdicts),
                verdicts=verdict_rows,
                winner_id=winner_id,
                winner_proposer_id=str(getattr(winner, "source_model", "") or "") if winner else "",
                explicit_abstain=explicit_abstain,
                verifier_mode="patch_execution" if execution_verifier else "registry",
                execution_results=list(execution_verifier.results) if execution_verifier else [],
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "committee",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="process_proposals",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


_FILE_LOCK_DEFAULT_TTL_SEC = 1800.0


def _exec_file_lock(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.orchestrator.file_lock_registry import (
            FileLockRegistry,
            canonical_lock_key,
            register_task_lock_file,
        )

        constraints = dict(plan.constraints or {})
        workspace_root = Path(
            str(constraints.get("workspace_root") or "/tmp")
        ).expanduser().resolve()
        # Canonical keys (workspace-relative inside the workspace): a relative and an absolute
        # spelling of one file can never be locked by two tasks at once.
        target_files = list(dict.fromkeys(
            canonical_lock_key(workspace_root, str(item))
            for item in constraints.get("target_files", []) or []
            if str(item).strip()
        ))
        if not target_files:
            return _make_receipt(
                "file_lock",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="acquire+check_access",
                    semantic_status="BLOCKED",
                    error="REAL_TARGET_FILES_REQUIRED",
                    evidence_refs=[f"ev_file_lock_blocked_{plan.task_id}"],
                    physical_callable="nexus.orchestrator.file_lock_registry.FileLockRegistry.acquire",
                ),
            )
        # One registry per workspace keyed by file path (holder = task id), so a second
        # task locking the same file is refused; a lock older than the TTL is stale.
        lock_file = workspace_root / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
        ttl_sec = float(constraints.get("file_lock_ttl_sec") or _FILE_LOCK_DEFAULT_TTL_SEC)
        reg = FileLockRegistry(lock_file=str(lock_file), ttl_sec=ttl_sec)
        acquired = reg.acquire_detailed(plan.task_id, target_files)
        if not acquired["conflicts"]:
            # Released by the mainchain entry when the task completes (TTL is the backstop).
            register_task_lock_file(plan.task_id, str(lock_file))
        conflicts = list(acquired["conflicts"])
        holders = dict(acquired["holders"])
        if conflicts:
            return _make_receipt(
                "file_lock",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="acquire+check_access",
                    semantic_status="BLOCKED",
                    error="FILE_LOCK_HELD_BY_OTHER_TASK:"
                    + ",".join(f"{path}@{holder}" for path, holder in sorted(holders.items())),
                    evidence_refs=[f"file:{lock_file}"],
                    conflicts=conflicts,
                    holders=holders,
                    access_granted=False,
                    task_files_match=False,
                    lock_file=str(lock_file),
                    physical_callable="nexus.orchestrator.file_lock_registry.FileLockRegistry.acquire_detailed",
                ),
            )
        access_results = {
            target: bool(reg.check_access(plan.task_id, target))
            for target in target_files
        }
        task_files = sorted(
            f for f in reg.get_task_files(plan.task_id) if f in {os.path.normpath(t) for t in target_files}
        )
        expected_files = sorted({os.path.normpath(item) for item in target_files})
        ok = not conflicts and all(access_results.values()) and task_files == expected_files
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "file_lock",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="acquire+check_access",
                semantic_status="VERIFIED" if ok else "FAILED",
                evidence_refs=[f"file:{lock_file}"],
                result={
                    "conflicts": conflicts,
                    "access_results": access_results,
                    "task_files": task_files,
                    "task_hint": str(task_desc or "")[:80],
                },
                conflicts=conflicts,
                stale_taken_over=dict(acquired["stale_taken_over"]),
                lock_ttl_sec=ttl_sec,
                access_granted=all(access_results.values()),
                task_files_match=task_files == expected_files,
                lock_file=str(lock_file),
                physical_callable="nexus.orchestrator.file_lock_registry.FileLockRegistry.acquire+check_access",
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "file_lock",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="check_access",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_forecast_gate(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Production ForecastGateService with real LatentPredictor + GateEvaluator injectors."""
    start = time.monotonic()
    try:
        from pathlib import Path

        from nexus.core.gate_evaluator import GateEvaluator
        from nexus.core.state_contracts import NexusState
        from nexus.core.state_io import StateIO
        ForecastGateService = resolve_port("forecast.ForecastGateService")
        get_self_healing_selector = resolve_port("forecast.get_self_healing_selector")
        from nexus.learning.latent_predictor_v20 import LatentPredictorV20
        from nexus.learning.predictor_toggle import LATENT_PREDICTOR, predictor_enabled

        constraints = dict(plan.constraints or {})
        root = Path(
            str(constraints.get("workspace_root") or "/tmp/nexus-forecast")
        ).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        latent = (
            LatentPredictorV20(workspace_root=root)
            if predictor_enabled(LATENT_PREDICTOR)
            else None
        )
        gate_eval = GateEvaluator()
        state_io = StateIO(str(root), run_dir=str(root / ".nexus" / "forecast" / plan.task_id))
        inst = ForecastGateService(
            latent_forecaster=latent,
            gate_eval=gate_eval,
            ash_selector=get_self_healing_selector(str(root)),
            state_io=state_io,
        )
        state = NexusState(task_id=str(plan.task_id))
        state.metadata["task_description"] = str(task_desc or plan.task_id)[:200]
        if constraints.get("forecast_roi_score") is not None:
            state.metadata["roi_score"] = float(constraints["forecast_roi_score"])
        if constraints.get("forecast_tokens") is not None:
            state.metadata["forecast_tokens"] = int(constraints["forecast_tokens"])
        if constraints.get("forecast_reject_prob") is not None:
            state.metadata["reject_prob"] = float(constraints["forecast_reject_prob"])
        result = inst.evaluate(
            task_id=str(plan.task_id),
            task_desc=str(task_desc or plan.task_id),
            state=state,
            phase="D",
        )
        elapsed = int((time.monotonic() - start) * 1000)
        if not isinstance(result, Mapping) or "proceed" not in result:
            return _make_receipt(
                "forecast_gate",
                plan,
                wall_time_ms=elapsed,
                gate_passed=False,
                outcome=_structured_outcome(
                    action="evaluate",
                    semantic_status="FAILED",
                    error="forecast_gate_missing_proceed_field",
                    evidence_refs=[f"ev_forecast_gate_{plan.task_id}"],
                ),
            )
        proceed = bool(result.get("proceed"))
        state_path = str(state_io.state_file)
        ash_strategy = str(state.metadata.get("ash_selected_strategy") or "")
        persisted = Path(state_path).is_file()
        # A proceed decision is complete without ASH persistence. A rejection is
        # complete only when real ASH selection and state persistence occurred.
        ok = bool(proceed or (ash_strategy and persisted))
        return _make_receipt(
            "forecast_gate",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="evaluate",
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_forecast_gate_{plan.task_id}"],
                result={
                    "proceed": proceed,
                    "reason": str(result.get("reason") or "")[:120],
                    "forecast_keys": list((result.get("forecast") or {}).keys())[:8]
                    if isinstance(result.get("forecast"), Mapping)
                    else [],
                },
                physical_callable=(
                    "nexus.engine.forecast_gate_service.ForecastGateService.evaluate"
                    "+LatentPredictorV20+GateEvaluator+StateIO+SelfHealingSelector"
                ),
                decision_emitted=True,
                ash_strategy=ash_strategy,
                state_persisted=persisted,
                state_path=state_path,
                predictor_influence=list(state.metadata.get("predictor_influence") or []),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "forecast_gate",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="evaluate",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_formal_report(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.research.formal_report_service import FormalReportService

        constraints = dict(plan.constraints or {})
        judge_votes = [
            dict(row)
            for row in constraints.get("formal_judge_votes", []) or []
            if isinstance(row, Mapping)
        ]
        verification = [
            dict(row)
            for row in constraints.get("formal_verification", []) or []
            if isinstance(row, Mapping)
        ]
        route_receipts = [
            dict(row)
            for row in constraints.get("formal_route_receipts", []) or []
            if isinstance(row, Mapping)
        ]
        result = FormalReportService().build(
            title=f"report-{plan.task_id}",
            hypothesis=str(task_desc or plan.task_id)[:200],
            asi_constraints=list(constraints.get("formal_asi_constraints") or []),
            judge_votes=judge_votes,
            verification=verification,
            route_receipts=route_receipts,
            citations=[],
            limitations=["mainchain_structural_bind"],
        )
        elapsed = int((time.monotonic() - start) * 1000)
        ok = bool(
            isinstance(result, Mapping)
            and result.get("status") == "READY"
            and result.get("claim_status") == "PASS"
            and judge_votes
            and any(str(row.get("status") or "").upper() == "PASS" for row in verification)
            and any(
                row.get("evidence_present") is True and row.get("gate_passed") is True
                for row in route_receipts
            )
        )
        return _make_receipt(
            "formal_report",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="build",
                semantic_status="VERIFIED" if ok else "BLOCKED",
                evidence_refs=[f"ev_formal_report_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable="nexus.research.formal_report_service.FormalReportService.build",
                report_status=str(result.get("status") or "") if isinstance(result, Mapping) else "",
                claim_status=str(result.get("claim_status") or "") if isinstance(result, Mapping) else "",
                judge_vote_count=len(judge_votes),
                verification_passed=any(
                    str(row.get("status") or "").upper() == "PASS"
                    for row in verification
                ),
                route_receipt_count=len(route_receipts),
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "formal_report",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="build",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_integration_manager(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-13: retired pre-#957 integration path (use ControlledIntegrationManager)."""
    return _archived_receipt("integration_manager", plan, task_desc)


def _exec_xray(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.services.xray_service import XRayService

        constraints = plan.constraints or {}
        if not constraints.get("project_root") and constraints.get("workspace_root"):
            # Scope the scan to workspace_root, but keep the report out of it: an untracked
            # file in a candidate worktree fails the candidate's allowed-scope check (#2688).
            updated = {**constraints, "project_root": constraints["workspace_root"]}
            if not (constraints.get("run_root") or constraints.get("runtime_root")):
                updated["run_root"] = tempfile.mkdtemp(prefix="nexus-xray-")
            plan = dataclasses.replace(plan, constraints=updated)
        project_root, run_root, run_id = _resolve_run_root(plan)
        report_path = run_root / "xray_report_full.md"
        output_paths = [report_path]
        _assert_outputs_in_run_root(output_paths, run_root)

        inst = XRayService(project_root=str(project_root), report_path=str(report_path))
        # Absolute targets: XRayObserver silently skips paths that do not exist relative to cwd.
        # Targets come from the request (task files); fall back to the repo root.
        try:
            targets = _xray_targets(plan, Path(project_root))
        except _ScopeError as scope:
            return _scope_blocked_receipt("xray", plan, str(scope), start)
        result = inst.run(
            targets=[str(t) for t in targets], recursive=False, docker=False, inject_findings=False
        )
        elapsed = int((time.monotonic() - start) * 1000)
        # run() always returns the report path, so success must come from the scan itself.
        scanned = getattr(inst, "last_report", None)
        ok = bool(
            all(t.exists() for t in targets)
            and report_path.exists()
            and scanned is not None
            and scanned.symbols
        )
        return _make_receipt(
            "xray",
            plan,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="run",
                semantic_status="SUCCEEDED" if ok else "FAILED",
                evidence_refs=[f"ev_xray_{plan.task_id}"],
                result={"report_type": type(result).__name__, "report_preview": str(result)[:200]},
                scan_targets=[str(t) for t in targets][:8],
                physical_callable="nexus.services.xray_service.XRayService.run",
                run_id=run_id,
                resolved_run_root=str(run_root),
                output_paths=[str(p) for p in output_paths],
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "xray",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="run",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_swarm_quiet_moment(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-13: echo stub (nothing paused, saved, or read); fail closed."""
    return _archived_receipt("swarm_quiet_moment", plan, task_desc)


def _exec_registry_sync(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    if not _provider_auth_allowed(require_external=True):
        return _auth_blocked_receipt(
            "registry_sync",
            plan,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            reason="BLOCKED_EXTERNAL_AUTH:registry_peer",
        )
    try:
        from nexus.learning.skill_registry import SkillRegistry
        from nexus.security.secure_sync import SecureRegistrySync
        from nexus.security.tls_provider import TLSProvider

        constraints = dict(plan.constraints or {})
        host = str(constraints.get("registry_peer_host") or "").strip()
        port = int(constraints.get("registry_peer_port") or 0)
        query_tokens = {
            str(token)
            for token in constraints.get("registry_query_tokens", []) or []
            if str(token).strip()
        }
        root = Path(
            str(constraints.get("workspace_root") or "/tmp/nexus-registry-sync")
        ).expanduser().resolve()
        if not host or port <= 0 or not query_tokens:
            return _make_receipt(
                "registry_sync",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="pull_from_peer",
                    semantic_status="BLOCKED",
                    error="REGISTRY_PEER_CONTEXT_REQUIRED",
                    evidence_refs=[f"ev_registry_sync_blocked_{plan.task_id}"],
                    physical_callable="nexus.security.secure_sync.SecureRegistrySync.pull_from_peer",
                ),
            )
        tls = TLSProvider(root / ".nexus" / "certs", node_id=f"sync-{plan.task_id}")
        registry = SkillRegistry(root / ".nexus" / "registry" / "skills.db")
        sync = SecureRegistrySync(tls=tls, registry=registry)
        pulled = sync.pull_from_peer_checked(host, port, query_tokens)
        rows = list(pulled.get("rows") or [])
        elapsed = int((time.monotonic() - start) * 1000)
        ok = bool(pulled.get("ok"))
        error_class = str(pulled.get("error_class") or "")
        return _make_receipt(
            "registry_sync",
            plan,
            invoked=True,
            wall_time_ms=elapsed,
            gate_passed=ok,
            outcome=_structured_outcome(
                action="pull_from_peer",
                # Fail closed: an unreachable / failing peer is BLOCKED, never VERIFIED with 0 rows.
                semantic_status="VERIFIED" if ok else "BLOCKED",
                error=None if ok else f"REGISTRY_PEER_UNAVAILABLE:{error_class}",
                evidence_refs=(
                    [f"registry-peer:{host}:{port}"]
                    if ok
                    else [f"ev_registry_sync_blocked_{plan.task_id}"]
                ),
                result={
                    "peer_host": host,
                    "peer_port": port,
                    "row_count": len(rows),
                    "error_class": error_class,
                    "error_detail": str(pulled.get("error") or "")[:300],
                },
                physical_callable="nexus.security.secure_sync.SecureRegistrySync.pull_from_peer_checked",
                task_hint=str(task_desc or "")[:80],
                peer_contacted=bool(pulled.get("peer_contacted")),
                row_count=len(rows),
                error_class=error_class,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "registry_sync",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="pull_from_peer",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_stress_test(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("stress_test", plan, task_desc)


def _exec_meta_opt(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    start = time.monotonic()
    try:
        from nexus.learning.outcome_memory import (
            EpisodeOutcomeRecord,
            OutcomeMemoryManager,
        )

        constraints = dict(plan.constraints or {})
        workspace_root = Path(
            str(constraints.get("workspace_root") or "/tmp/nexus-meta-opt")
        ).expanduser().resolve()
        episode = constraints.get("meta_opt_episode")
        if not isinstance(episode, Mapping):
            return _make_receipt(
                "meta_opt",
                plan,
                invoked=True,
                gate_passed=False,
                wall_time_ms=int((time.monotonic() - start) * 1000),
                outcome=_structured_outcome(
                    action="save_episode_and_tune",
                    semantic_status="BLOCKED",
                    error="REAL_OUTCOME_EPISODE_REQUIRED",
                    evidence_refs=[f"ev_meta_opt_blocked_{plan.task_id}"],
                    physical_callable="nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync",
                ),
            )
        record = EpisodeOutcomeRecord.from_task(
            task_id=str(episode.get("task_id") or plan.task_id),
            task_type=str(episode.get("task_type") or "codeintel"),
            task_desc=str(episode.get("task_desc") or task_desc or plan.task_id),
            solved=bool(episode.get("solved")),
            wall_duration_sec=float(episode.get("wall_duration_sec") or 0.1),
            total_tokens_used=int(episode.get("total_tokens_used") or 0),
            trust_mismatch=bool(episode.get("trust_mismatch", False)),
            receipts=[
                dict(row)
                for row in episode.get("receipts", []) or []
                if isinstance(row, Mapping)
            ],
            ab_lift_value=float(episode.get("ab_lift_value") or 0.0),
        )
        result = OutcomeMemoryManager.save_episode_and_tune_sync(
            record,
            project_root=workspace_root,
        )
        policy = result.get("policy") if isinstance(result.get("policy"), Mapping) else {}
        policy_path = workspace_root / OutcomeMemoryManager.POLICY_PATH
        storage_path = workspace_root / OutcomeMemoryManager.STORAGE_PATH
        ok = bool(
            result.get("status") == "PASS"
            and policy.get("status") == "PASS"
            and int(policy.get("source_experiences_count") or 0) >= 1
            and policy_path.is_file()
            and storage_path.is_file()
        )
        return _make_receipt(
            "meta_opt",
            plan,
            gate_passed=ok,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="save_episode_and_tune",
                semantic_status="VERIFIED" if ok else "FAILED",
                evidence_refs=[f"file:{storage_path}", f"file:{policy_path}"],
                result={
                    "source_experiences_count": int(policy.get("source_experiences_count") or 0),
                    "eligible_experiences_count": int(policy.get("eligible_experiences_count") or 0),
                    "promoted_capabilities": list(policy.get("promoted_capabilities") or []),
                    "penalized_capabilities": list(policy.get("penalized_capabilities") or []),
                },
                episode_persisted=storage_path.is_file(),
                policy_persisted=policy_path.is_file(),
                autotune_status=str(policy.get("status") or ""),
                physical_callable="nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync",
            ),
        )
    except Exception as exc:
        return _make_receipt(
            "meta_opt",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="save_episode_and_tune",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_prompt_compression(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    """STAGE_OWNED_REAL — compression is owned by runtime context path."""
    start = time.monotonic()
    try:
        # Real shared helper if present; else structured stage-owned receipt.
        try:
            from nexus.services.unified_runtime import compress_prompt_context  # type: ignore

            result = compress_prompt_context(str(task_desc or plan.task_id))  # type: ignore[misc]
            action = "compress_prompt_context"
            physical = "nexus.services.unified_runtime.compress_prompt_context"
        except Exception:
            # Stage-owned control: prove module surface without fake success theater.
            import nexus.services.unified_runtime as ur

            action = "stage_owned_reference"
            result = {
                "module": ur.__name__,
                "has_unified_runtime": hasattr(ur, "UnifiedRuntime"),
                "task_chars": len(str(task_desc or "")),
            }
            physical = "nexus.services.unified_runtime.UnifiedRuntime"
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "prompt_compression",
            plan,
            wall_time_ms=elapsed,
            gate_passed=True,  # non-claim execution health (#1869)
            outcome=_structured_outcome(
                action=action,
                semantic_status="SUCCEEDED",
                evidence_refs=[f"ev_prompt_compression_{plan.task_id}"],
                result=result if isinstance(result, Mapping) else {"value": str(result)[:200]},
                physical_callable=physical,
                stage_owned=True,
            ),
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return _make_receipt(
            "prompt_compression",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=elapsed,
            outcome=_structured_outcome(
                action="stage_owned_reference",
                semantic_status="FAILED",
                error=str(exc)[:300],
            ),
        )


def _exec_federation(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("federation", plan, task_desc)


def _exec_oracle_shadow(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("oracle_shadow", plan, task_desc)


def _exec_ui_validator(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """ARCHIVED 2026-10-12: fail closed with an explicit receipt reason."""
    return _archived_receipt("ui_validator", plan, task_desc)


def _exec_external_doc_scout(
    plan: CapabilityExecutionPlan, task_desc: str
) -> CapabilityReceipt:
    start = time.monotonic()
    if not _provider_auth_allowed(require_external=True):
        elapsed = int((time.monotonic() - start) * 1000)
        return _auth_blocked_receipt(
            "external_doc_scout",
            plan,
            wall_time_ms=elapsed,
            reason="BLOCKED_EXTERNAL_AUTH:doc_connector",
        )
    elapsed = int((time.monotonic() - start) * 1000)
    return _make_receipt(
        "external_doc_scout",
        plan,
        wall_time_ms=elapsed,
        gate_passed=False,
        outcome=_structured_outcome(
            action="scout_docs",
            semantic_status="BLOCKED",
            error="BLOCKED_EXTERNAL_AUTH:no_live_connector",
            evidence_refs=[f"ev_external_doc_scout_{plan.task_id}"],
        ),
    )


def _exec_entropy_guard_v2(plan: CapabilityExecutionPlan, task_desc: str) -> CapabilityReceipt:
    """Shannon-entropy audit of the output under review (not the task text).

    Input: ``entropy_audit_text`` (required) and optional ``entropy_audit_tokens``.  No
    fallback to ``task_desc``: auditing the request instead of the output was the reason the
    old key was archived.  VETOED -> BLOCKED; PASSED -> VERIFIED with the measured entropies.
    """
    start = time.monotonic()
    constraints = dict(plan.constraints or {})
    text = str(constraints.get("entropy_audit_text") or "")
    raw_tokens = constraints.get("entropy_audit_tokens") or []
    tokens = [int(t) for t in raw_tokens if isinstance(t, int) and not isinstance(t, bool)]
    if not text.strip():
        return _make_receipt(
            "entropy_guard_v2",
            plan,
            invoked=True,
            gate_passed=False,
            wall_time_ms=int((time.monotonic() - start) * 1000),
            outcome=_structured_outcome(
                action="audit_payload",
                semantic_status="BLOCKED",
                error="ENTROPY_AUDIT_TEXT_REQUIRED",
                evidence_refs=[f"ev_entropy_guard_v2_blocked_{plan.task_id}"],
            ),
        )
    from nexus.services.entropy_v2 import EntropyGuardV2

    audit = EntropyGuardV2().audit_payload(text, tokens)
    passed = str(audit.get("status")) == "PASSED"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _make_receipt(
        "entropy_guard_v2",
        plan,
        gate_passed=passed,
        wall_time_ms=int((time.monotonic() - start) * 1000),
        outcome=_structured_outcome(
            action="audit_payload",
            semantic_status="VERIFIED" if passed else "BLOCKED",
            error=None if passed else "ENTROPY_VETO",
            evidence_refs=[f"sha256:{digest}"],
            result={
                "text_entropy": round(float(audit.get("text_entropy") or 0.0), 4),
                "token_entropy": round(float(audit.get("token_entropy") or 0.0), 4),
                "max_segment_entropy": round(float(audit.get("max_segment_entropy") or 0.0), 4),
                "high_entropy_segments": int(audit.get("high_entropy_segments") or 0),
                "segment_threshold": float(audit.get("segment_threshold") or 0.0),
                "status": str(audit.get("status")),
                "text_sha256": digest,
                "text_chars": len(text),
            },
            physical_callable="nexus.services.entropy_v2.EntropyGuardV2.audit_payload",
        ),
    )


# Executors written and tested here but deliberately NOT in EXECUTOR_REGISTRY until the
# pinned nexus-runtime defines their planner node (registering a key no node can reach
# recreates the silent second catalogue archived in #1906).  entropy_guard_v2 moved into
# EXECUTOR_REGISTRY with the runtime 68e86ed pin (node: nexus-runtime #198, Nexus-new #1907).
PENDING_PLANNER_NODE_EXECUTORS: dict[str, CapabilityExecutor] = {}


EXECUTOR_REGISTRY: dict[str, CapabilityExecutor] = {
    "entropy_guard_v2": _exec_entropy_guard_v2,  # planner node: nexus-runtime #198 (#1907)
    "mempalace": _exec_mempalace,
    "autonomic_router": _exec_autonomic_router,
    "codeintel": _exec_codeintel,
    "lancedb": _exec_lancedb,
    "research": _exec_research,
    "learn_scheduler_service": _exec_learn_scheduler_service,
    "belief": _exec_belief,
    "autoreason": _exec_autoreason,
    "repair_loop": _exec_repair_loop,
    "hyper_sprint": _exec_hyper_sprint,
    "swarm_multi_agent": _exec_swarm_multi_agent,
    "drone": _exec_drone,
    "nightshift": _exec_nightshift,
    "sandbox_runner": _exec_sandbox_runner,
    "artifact_gate": _exec_artifact_gate,
    "claim_gate": _exec_claim_gate,
    "ultra_review": _exec_ultra_review,
    "learning_closure": _exec_learning_closure,
    "metabolism_resume": _exec_metabolism_resume,
    # Mainchain residual production/beta
    "memory": _exec_memory,
    "plan_quality_gate": _exec_plan_quality_gate,
    "semantic_searcher": _exec_semantic_searcher,
    "pregate": _exec_pregate,
    "harness_preflight_sensor": _exec_harness_preflight_sensor,
    "ddtree": _exec_ddtree,
    "learn_mode": _exec_learn_mode,
    "learn_phase_slo": _exec_learn_phase_slo,
    "acceptance_check": _exec_acceptance_check,
    "jit_validation": _exec_jit_validation,
    "semantic_failure_sensor": _exec_semantic_failure_sensor,
    "bdd_acceptance_skill": _exec_bdd_acceptance_skill,
    "judge_panel": _exec_judge_panel,
    "llm_judge_panel": _exec_llm_judge_panel,
    # Phase 3 binds (existing engines, thin adapters)
    "architecture_scout": _exec_architecture_scout,
    "asi_constraint_extractor": _exec_asi_constraint_extractor,
    "benchmark": _exec_benchmark,
    "benchmark_meta_opt": _exec_meta_opt,
    "committee": _exec_committee,
    "file_lock": _exec_file_lock,
    "file_lock_security_gate": _exec_file_lock,
    "forecast_gate": _exec_forecast_gate,
    "forecast_pregate": _exec_forecast_gate,
    "formal_report": _exec_formal_report,
    "integration_manager": _exec_integration_manager,
    "xray": _exec_xray,
    "swarm_quiet_moment": _exec_swarm_quiet_moment,
    "registry_sync": _exec_registry_sync,
    "registry_skills_sync": _exec_registry_sync,
    "stress_test": _exec_stress_test,
    "meta_opt": _exec_meta_opt,
    "prompt_compression": _exec_prompt_compression,
    "federation": _exec_federation,
    "oracle_shadow": _exec_oracle_shadow,
    "ui_validator": _exec_ui_validator,
    "external_doc_scout": _exec_external_doc_scout,
}


def _try_port(port: str) -> Any:
    """Upper-layer collaborator bound via ``nexus.core.layer_ports``; None when unavailable."""
    try:
        return resolve_port(port)
    except Exception as exc:
        logger.debug("executor_registry: cannot resolve port %s: %s", port, exc)
        return None


def _port_error(port: str) -> str:
    """Receipt error for a ``_try_port`` miss: PORT_UNBOUND or PORT_LOAD_FAILED, with the port name."""
    reason = "PORT_LOAD_FAILED" if port in registered_ports() else "PORT_UNBOUND"
    return f"{reason}:{port}"


def get_executor(cap_name: str) -> CapabilityExecutor | None:
    return EXECUTOR_REGISTRY.get(cap_name)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _safe_run_id(task_id: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(task_id or "")).strip("._")
    return cleaned[:96] or "task"


def _task_files(constraints: Mapping[str, Any], *keys: str) -> list[str]:
    """Task files named by the request, in key order, de-duplicated."""
    out: list[str] = []
    for key in keys:
        raw = constraints.get(key)
        if isinstance(raw, (str, os.PathLike)):
            items = [raw]
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = []
        for item in items:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    return out


def _first_task_file(constraints: Mapping[str, Any]) -> str:
    files = _task_files(constraints, "hyper_target_file", "target_file", "target_files")
    return files[0] if files else ""


class _ScopeError(Exception):
    """Request-supplied path or root escapes the trusted project root."""


def _scoped_workspace(constraints: Mapping[str, Any] | None, project_root: Path) -> Path:
    """Executor root: the runtime-supplied ``workspace_root`` constraint, else the project root.

    The registry only forwards ``workspace_root`` from the runtime context / route, never from
    request ``codeintel``, so a request cannot move an executor; request files are then
    checked against this root by ``_scoped_path``.
    """
    raw = str((constraints or {}).get("workspace_root") or "").strip()
    return Path(raw).resolve() if raw else project_root.resolve()


def _scoped_path(root: Path, raw: str) -> Path:
    """Resolve a request path under ``root``; it must stay inside and exist."""
    resolved = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
        raise _ScopeError("path_outside_workspace")
    return resolved


def _scope_blocked_receipt(
    cap_name: str, plan: CapabilityExecutionPlan, reason: str, start: float
) -> CapabilityReceipt:
    return _make_receipt(
        cap_name,
        plan,
        invoked=True,
        gate_passed=False,
        wall_time_ms=int((time.monotonic() - start) * 1000),
        outcome=_structured_outcome(
            action="scope_gate",
            semantic_status="BLOCKED",
            error=reason,
            evidence_refs=[f"ev_scope_block_{cap_name}_{plan.task_id}"],
        ),
    )


def _xray_targets(plan: CapabilityExecutionPlan, project_root: Path) -> list[Path]:
    """Scan targets from the request, contained in the project root; root as fallback."""
    constraints = dict(plan.constraints or {})
    root = _scoped_workspace(constraints, project_root)
    named = _task_files(constraints, "xray_targets", "target_file", "target_files")[:16]
    if not named and isinstance(constraints.get("xray_targets"), (list, tuple)):
        # The task named its files but none exists yet: do not scan an unrelated default.
        raise _ScopeError("no_existing_task_files")
    if not named:
        legacy = root / "nexus" / "services" / "capability_registry.py"
        return [legacy if legacy.exists() else root]
    return [_scoped_path(root, n) for n in named]


NO_CANDIDATE_POOL = "no_candidate_pool"


def _candidate_pool(plan: CapabilityExecutionPlan) -> list[dict[str, Any]]:
    """Real candidate pool from the plan constraints (fed from request.codeintel)."""
    raw = (plan.constraints or {}).get("candidate_pool")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _no_candidate_pool_receipt(
    cap_name: str, plan: CapabilityExecutionPlan, start: float
) -> CapabilityReceipt:
    """Explicit skip: never fabricate a single placeholder candidate."""
    return _make_receipt(
        cap_name,
        plan,
        invoked=False,
        gate_passed=False,
        wall_time_ms=int((time.monotonic() - start) * 1000),
        outcome=_structured_outcome(
            action="skip",
            semantic_status="SKIPPED",
            skip_reason=NO_CANDIDATE_POOL,
            evidence_refs=[f"ev_{cap_name}_skip_{NO_CANDIDATE_POOL}_{plan.task_id}"],
        ),
    )


def _memory_retrieve(manager: Any, query: str, *, limit: int) -> list[Any]:
    """Project-memory retrieval: whole query first, then per-keyword (local_heal pattern).

    ProjectMemoryManager.search is a SQL LIKE substring, so a whole task statement
    only hits when an insight contains it verbatim. Mirror the local_heal retrieval
    adapter: exact query, and when empty, de-duplicated per-keyword lookups.
    """
    hits = list(manager.search(query) or [])
    if hits:
        return hits[:limit]
    head = query.split("Nexus route oracle contract", 1)[0]
    seen: set[tuple[Any, ...]] = set()
    for token in [t for t in re.split(r"[_\W]+", head.lower()) if len(t) >= 3][:8]:
        if token in _MEMORY_STOPWORDS:
            continue
        for row in manager.search(token) or []:
            key = tuple(row)
            if key in seen:
                continue
            seen.add(key)
            hits.append(row)
            if len(hits) >= limit:
                return hits
    return hits


_MEMORY_STOPWORDS = frozenset(
    {"the", "and", "for", "with", "that", "this", "from", "into", "what", "how", "recall", "find"}
)


def _memory_findings_hits(root: Path, query: str, *, limit: int) -> list[dict[str, Any]]:
    """Episode cards from the local_heal FindingsMemoryStore (read-only; none if never created)."""
    if not (root / ".nexus" / "memory").is_dir():
        return []
    try:
        from nexus.services.local_heal.memory_retrieval_adapter import FindingsMemoryLessonStore

        head = query.split("Nexus route oracle contract", 1)[0]
        return FindingsMemoryLessonStore(project_root=root).query(query_text=head, limit=limit)
    except Exception:
        return []
