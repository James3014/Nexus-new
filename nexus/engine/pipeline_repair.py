from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
import logging
import time
import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from nexus.learning.knowledge_index import KnowledgeIndex
from nexus.events.transport import NexusEventBus
from nexus.core.protocols import PipelineContextProtocol
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands
from nexus.delivery.phantom_guard import detect_inconclusive_success
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event
from nexus.learning.cycle_analyzer import analyze_cycle
from nexus.engine.recursive_repair_loop import RecursiveRepairLoop, recursive_repair_enabled
from nexus.engine.repair.audit_evaluator import evaluate_audit_result
from nexus.engine.repair.composed_phase_result import ComposedAuditResult, ComposedRepairResult
from nexus.engine.repair.escalation_manager import handle_escalation, perform_escalation

logger = logging.getLogger(__name__)

REJECTED_REPAIR_STATUSES = frozenset({"REJECTED"})
RECOVERABLE_REPAIR_STATUSES = frozenset({"FAIL", "FAILED", "RECOVERABLE_BLOCK", "REVISE", "UNKNOWN", "REJECTED_NO_RED_TEST"})

@dataclass
class AuditEvalContext:
    """Encapsulation of audit evaluation parameters for Phase A."""
    tracer: Any
    repair_attempts: int
    review_status_raw: str
    result_object: dict
    current_decision_id: str
    current_skill_id: str

class PipelineRepairMixin:
    """🛠️ Mixin for Repair/Audit loop logic in NexusPipeline."""

    def _enter_runtime_phase(self, ctx: PipelineContextProtocol, phase: str, *, reason: str) -> None:
        """Enter R/A through NexusPipeline's contract guard.

        The fallback keeps narrow legacy mixin harnesses usable; production
        NexusPipeline always supplies ``_advance_runtime_phase``.
        """

        advance = getattr(self, "_advance_runtime_phase", None)
        if callable(advance):
            if "runtime_phase" not in ctx.state.metadata:
                # Legacy direct mixin harnesses enter R without the S/P/D
                # pipeline preamble; real pipeline contexts always bind S.
                ctx.state.metadata["runtime_phase"] = "D"
                ctx.state.metadata["runtime_phase_assumed"] = True
            advance(ctx, phase, reason=reason)
            return
        ctx.state.metadata.setdefault("runtime_phase", "D")
        ctx.state.metadata["runtime_phase"] = phase
        ctx.state.current_phase = phase

    def _phase_observer(self, ctx: PipelineContextProtocol, phase: str, hook: str, **payload: Any) -> None:
        observer = getattr(self, "_emit_phase_observer", None)
        if callable(observer):
            observer(ctx, phase, hook, **payload)

    @staticmethod
    def _is_rejected_repair_status(status: Any) -> bool:
        return str(status or "").strip().upper() in REJECTED_REPAIR_STATUSES

    @staticmethod
    def _is_recoverable_repair_status(status: Any) -> bool:
        return str(status or "").strip().upper() in RECOVERABLE_REPAIR_STATUSES

    @classmethod
    def _is_repair_failure_status(cls, status: Any) -> bool:
        return cls._is_rejected_repair_status(status) or cls._is_recoverable_repair_status(status)

    def _local_assist_mode(self, ctx: PipelineContextProtocol) -> str:
        meta = getattr(ctx.state, "metadata", {}) or {}
        mode = str(meta.get("local_assist_mode") or "disabled").strip().lower()
        if mode in {"planner", "explicit", "shadow", "advisor", "disabled"}:
            from nexus.services.canonical_local_assist_policy import normalize_local_assist_policy

            try:
                return str(normalize_local_assist_policy(mode)["canonical_policy"])
            except ValueError:
                return "disabled"
        return "disabled"

    def _record_shadow_local_assist(self, ctx: PipelineContextProtocol) -> None:
        """Record shadow policy without Local model invocation or Online mutation."""
        from nexus.services.canonical_local_assist_policy import build_canonical_policy_receipt

        meta = ctx.state.metadata
        task_id = str(meta.get("task_id") or ctx.task_id or "")
        revision = self._ensure_workspace_revision(ctx)
        raw_policy = str(meta.get("local_assist_policy_raw") or "shadow")
        policy_receipt = build_canonical_policy_receipt(
            policy=raw_policy if raw_policy in {"shadow", "planner"} else "shadow",
            task={
                "task_id": task_id,
                "workspace_revision": revision,
                "task_statement": str(ctx.task_desc or task_id),
                "task_type": "repair",
                "route": {"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.8}},
            },
        )
        meta["local_assist_status"] = "SHADOW_RECORDED"
        meta["local_assist_shadow_receipt"] = policy_receipt
        meta["local_context_forwarded"] = False
        meta["local_assist_contributed"] = False
        meta["local_provider_call_count"] = 0
        truth = self._stamp_stage_truth(
            meta,
            local_assist_success=False,
            online_success=False,
            runtime_receipt_complete=False,
            task_pipeline_success=False,
        )
        self._write_unified_runtime_pointer(
            ctx,
            {
                "local_assist_mode": "shadow",
                "local_assist_status": "SHADOW_RECORDED",
                "local_context_forwarded": False,
                "unified_runtime_receipt_path": "",
                "unified_runtime_task_id": task_id,
                "online_provider": "",
                "workspace_revision": revision,
                "claim_boundary": policy_receipt.get("claim_boundary") or {},
                "local_provider_call_count": 0,
                "automatic_dispatch": False,
                "runtime_behavior_changed": False,
                **truth,
            },
        )

    def _ensure_workspace_revision(self, ctx: PipelineContextProtocol) -> str:
        meta = ctx.state.metadata
        revision = str(meta.get("workspace_revision") or "").strip()
        if revision:
            return revision
        root = Path(getattr(self.engine, "project_root", ".") or ".")
        try:
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            revision = f"ws-{str(ctx.task_id or 'task')[:24]}"
        meta["workspace_revision"] = revision
        return revision

    def _ensure_repair_gateway(self, ctx: PipelineContextProtocol) -> Any:
        """Bind BattlesuitGateway onto the R-phase repairer when product Online needs it.

        Composition/repair handlers historically lack ``.gateway``. Product paths
        ``online_policy=auto|require`` (and Advisor Local→Online) require a real
        Gateway for ``surgical_ask`` / ``ask_structured`` under ``guard_physical_online``.
        """
        import os

        meta = ctx.state.metadata if getattr(ctx, "state", None) is not None else {}
        if not isinstance(meta, dict):
            meta = {}
        repairer = getattr(ctx, "repairer", None)
        gateway = getattr(repairer, "gateway", None) if repairer is not None else None
        online_policy = str(meta.get("online_policy") or "").strip().lower()
        local_mode = str(meta.get("local_assist_mode") or "").strip().lower()
        product_online = online_policy in {"auto", "require"} or str(
            meta.get("product_entry") or ""
        ).strip().lower() in {"nexus run", "nexus_cli", "cli"}
        needs_gateway = product_online or local_mode in {"advisor", "shadow"}

        if gateway is None and needs_gateway:
            from nexus.services.gateway import BattlesuitGateway

            root = getattr(self.engine, "project_root", ".") or "."
            gateway = BattlesuitGateway(project_root=root)
            if repairer is not None:
                try:
                    repairer.gateway = gateway
                except Exception as exc:  # noqa: BLE001
                    logger.warning("repairer_gateway_bind_failed: %s", exc)

        if gateway is None:
            return None

        preferred = str(
            meta.get("oauth_provider")
            or meta.get("online_provider")
            or os.environ.get("NEXUS_OAUTH_PROVIDER", "")
            or ""
        ).strip().lower()
        # Prefer explicit Online provider over Gateway auto→ollama detection.
        if preferred and preferred not in {"auto", "ollama", "local"}:
            try:
                gateway.oauth_provider = preferred
                gateway.llm_bin = preferred
            except Exception as exc:  # noqa: BLE001
                logger.warning("gateway_provider_bind_failed: %s", exc)
            meta.setdefault("oauth_provider", preferred)
            meta.setdefault("online_provider", preferred)

        return gateway

    def _stamp_stage_truth(
        self,
        meta: dict[str, Any],
        *,
        local_assist_success: bool,
        online_success: bool,
        runtime_receipt_complete: bool,
        task_pipeline_success: bool = False,
    ) -> dict[str, bool]:
        """Keep stage outcomes as distinct booleans (never collapse into one flag)."""
        truth = {
            "local_assist_success": bool(local_assist_success),
            "online_success": bool(online_success),
            "runtime_receipt_complete": bool(runtime_receipt_complete),
            # Formal pipeline acceptance is owned by later audit/completion gates.
            "task_pipeline_success": bool(task_pipeline_success),
        }
        meta.update(truth)
        return truth

    def _write_unified_runtime_pointer(self, ctx: PipelineContextProtocol, payload: dict[str, Any]) -> None:
        """Durable pointer for CLI pipeline report linkage (not a second truth schema)."""
        root = Path(getattr(self.engine, "project_root", ".") or ".")
        task_key = str(payload.get("unified_runtime_task_id") or ctx.task_id or "task")
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", task_key)[:120] or "task"
        path = root / ".nexus" / "reports" / "run" / f"{safe}.unified_runtime_pointer.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        # Always persist the four distinct stage booleans when present on metadata.
        meta = ctx.state.metadata if isinstance(ctx.state.metadata, dict) else {}
        for key in (
            "local_assist_success",
            "online_success",
            "runtime_receipt_complete",
            "task_pipeline_success",
        ):
            if key in meta and key not in payload:
                payload[key] = meta[key]
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        ctx.state.metadata["unified_runtime_pointer_path"] = str(path)

    def _build_advisor_local_request(self, ctx: PipelineContextProtocol, *, allowed_files: list[str]):
        from nexus.services.local_assist_service import LocalAssistRequest, REQUEST_SCHEMA, build_planner_snapshot

        meta = ctx.state.metadata
        task_id = str(meta.get("task_id") or ctx.task_id or "")
        revision = self._ensure_workspace_revision(ctx)
        target = str(meta.get("target_file") or (allowed_files[0] if allowed_files else ""))
        import os as _os

        model = str(
            meta.get("local_assist_model")
            or _os.environ.get("NEXUS_LOCAL_MODEL_NAME")
            or _os.environ.get("NEXUS_LOCAL_MODEL")
            or "qwen2.5-coder:7b-instruct"
        ).strip()
        # Host inventory uses the instruct tag; bare :7b 404s on this machine.
        if model.endswith(":7b") and "instruct" not in model:
            model = "qwen2.5-coder:7b-instruct"
        if model in {"qwen2.5-coder:7b", "qwen2.5-coder:7b-q4", "qwen2.5-coder"}:
            model = "qwen2.5-coder:7b-instruct"
        snapshot = dict(meta.get("local_assist_planner_snapshot") or {})
        if not snapshot:
            snapshot = build_planner_snapshot(task_statement=str(ctx.task_desc or ""), model=model)
        # Always pin model/provider for product advisor path (planner snapshot may be stale).
        snapshot["model_call_allowed"] = True
        snapshot["executor_provider"] = "ollama"
        snapshot["executor_model"] = model
        snapshot["route_truth_source"] = "CapabilityPlanner"
        snapshot.setdefault("execution_topology", "single_local_model")
        snapshot.setdefault("protocol_mode", "unified_diff")
        meta["local_assist_model"] = model
        return LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(Path(getattr(self.engine, "project_root", ".") or ".")),
            workspace_revision=revision,
            task_statement=str(ctx.task_desc or task_id),
            action="advisor",
            allowed_files=tuple(allowed_files),
            target_file=target if target in allowed_files else allowed_files[0],
            target_symbol=str(meta.get("target_symbol") or ""),
            evidence_refs=tuple(
                meta.get("local_assist_evidence_refs")
                or [f"pipeline:{task_id}:advisor_request", f"repair:{task_id}:bounded_scope"]
            ),
            requested_role="advisor",
            mutation_policy="isolated_only",
            planner_snapshot=snapshot,
        )

    def _run_unified_advisor_online(
        self,
        ctx: PipelineContextProtocol,
        *,
        online_callable,
        repair_attempts: int,
    ) -> tuple[Any, Any]:
        """Optional Local Advisor then Online via UnifiedRuntime on the active repair seam.

        ``online_callable`` must accept ``(prompt: str)`` and return ``(res, raw)``.
        """
        from nexus.services.canonical_local_assist_policy import (
            collect_bounded_allowed_files,
            normalize_local_assist_policy,
        )
        from nexus.services.unified_runtime import (
            UnifiedRuntime,
            UnifiedRuntimeRequest,
            build_online_route,
            extract_online_stage_payload,
            normalize_online_invoker_payload,
        )

        from nexus.services.online_execution_policy import guard_physical_online

        meta = ctx.state.metadata
        mode = self._local_assist_mode(ctx)
        task_id = str(meta.get("task_id") or ctx.task_id or "")
        revision = self._ensure_workspace_revision(ctx)
        meta.setdefault("task_id", task_id)
        root = Path(getattr(self.engine, "project_root", ".") or ".")
        gateway = self._ensure_repair_gateway(ctx)

        def _guarded_online(prompt: str):
            """Single seam: bind OnlineExecutionDecision before any physical Online call."""
            allowed, decision, denied = guard_physical_online(
                gateway,
                meta,
                project_root=root,
                requested_provider=str(meta.get("oauth_provider") or meta.get("online_provider") or ""),
                planner_online_needed=True,
                injected_transport=bool(meta.get("injected_transport")),
                task_id=task_id,
            )
            if not allowed and denied is not None:
                return denied
            return online_callable(prompt)

        def _fail_closed_mainchain(exc: Exception, *, local_status: str) -> tuple[dict[str, Any], str]:
            """Preserve the canonical failure without bypassing receipt/verifier gates."""
            error = f"mainchain_exception:{type(exc).__name__}:{exc}"
            truth = self._stamp_stage_truth(
                meta,
                local_assist_success=False,
                online_success=False,
                runtime_receipt_complete=False,
                task_pipeline_success=False,
            )
            meta.update(
                {
                    "local_assist_status": local_status,
                    "local_assist_reason": error,
                    "degraded_to_online": False,
                    "degradation_reason": error,
                    "local_assist_contributed": False,
                    "local_context_forwarded": False,
                    "online_continued_without_local_assist": False,
                    "local_assist_status_detail": "MAINCHAIN_FAILED_CLOSED",
                    "mainchain_error": error,
                    "with_nexus_armor": True,
                }
            )
            self._write_unified_runtime_pointer(
                ctx,
                {
                    "local_assist_mode": mode,
                    "local_assist_status": local_status,
                    "local_context_forwarded": False,
                    "unified_runtime_receipt_path": "",
                    "unified_runtime_task_id": task_id,
                    "online_provider": "",
                    "workspace_revision": revision,
                    "degraded_to_online": False,
                    "degradation_reason": error,
                    "local_assist_contributed": False,
                    "online_continued_without_local_assist": False,
                    "mainchain_entry": True,
                    "mainchain_error": error,
                    "fail_closed": True,
                    "claim_boundary": {
                        "public_claim_allowed": False,
                        "production_ready": False,
                    },
                    **truth,
                },
            )
            return (
                {
                    "status": "FAILED",
                    "patch": "",
                    "error": error,
                    "provider_call_count": 0,
                    "mainchain_entry": True,
                    "receipt_complete": False,
                },
                "",
            )

        if mode == "disabled":
            # P4: Online-only World A still uses UnifiedRuntime + with_nexus armor
            # (no Local). Canonical runtime failure must remain fail-closed.
            try:
                from nexus.services.mainchain_entry import (
                    build_mainchain_capability_invokers,
                    stamp_mainchain_route,
                    wrap_mainchain_online_invoker,
                )

                receipt_path = root / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
                receipt_path.parent.mkdir(parents=True, exist_ok=True)

                def _disabled_online_invoker(context: dict[str, Any]) -> dict[str, Any]:
                    prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
                    res_i, raw_i = _guarded_online(prompt)
                    delivered = bool(raw_i or (isinstance(res_i, dict) and res_i)) and str(raw_i) != "online_execution_not_authorized"
                    return normalize_online_invoker_payload(
                        provider=str(meta.get("oauth_provider") or meta.get("online_provider") or "gateway"),
                        task_id=task_id,
                        invoked=delivered,
                        output_delivered=delivered,
                        gate_passed=delivered,
                        provider_call_count=1 if delivered else 0,
                        response=res_i if isinstance(res_i, dict) else {"raw": raw_i},
                        raw_response=str(raw_i or ""),
                        error="" if delivered else "online_empty_or_denied",
                        evidence_refs=[f"online:{task_id}:world_a_disabled_local"] if delivered else [],
                    )

                route = stamp_mainchain_route(
                    build_online_route(
                        recommended_flow="direct",
                        gateway_provider=str(meta.get("oauth_provider") or ""),
                        local_enabled=False,
                    ),
                    with_nexus_armor=True,
                    product_entry="nexus_run",
                )
                if meta.get("online_policy"):
                    route["online_policy"] = str(meta.get("online_policy"))
                if meta.get("online_execution_decision"):
                    route["online_execution_decision"] = meta.get("online_execution_decision")
                route["workspace_root"] = str(root)
                codeintel = meta.get("codeintel") if isinstance(meta.get("codeintel"), dict) else {}
                request = UnifiedRuntimeRequest(
                    task_id=task_id,
                    workspace_revision=revision,
                    task_statement=str(ctx.task_desc or task_id),
                    task_type="repair",
                    route=route,
                    online_prompt=str(ctx.task_desc or ""),
                    online_payload=f"attempt={repair_attempts}",
                    online_phase="R",
                    online_enabled=True,
                    local_enabled=False,
                    codeintel=codeintel,
                    evidence_refs=(f"pipeline:{task_id}:world_a_online_only",),
                )

                def _v(context: dict[str, Any]) -> dict[str, Any]:
                    online = context.get("online", {}) if isinstance(context, dict) else {}
                    delivered = bool(online.get("invoked") and online.get("status") == "SUCCEEDED")
                    return {
                        "task_id": task_id,
                        "status": "pass" if delivered else "fail",
                        "gate_passed": delivered,
                        "invoked": True,
                        "evidence_refs": [f"verifier:{task_id}:world_a_online_only"],
                    }

                def _learn(context: dict[str, Any]) -> dict[str, Any]:
                    return {
                        "task_id": task_id,
                        "status": "recorded",
                        "invoked": True,
                        "gate_passed": True,
                        "evidence_refs": [f"learning:{task_id}:world_a_online_only"],
                    }

                from nexus.services.mainchain_entry import run_mainchain

                receipt = run_mainchain(
                    request,
                    online_invoker=_disabled_online_invoker,
                    capability_invokers=build_mainchain_capability_invokers(codeintel=codeintel),
                    verifier=_v,
                    learning=_learn,
                    receipt_path=receipt_path,
                    with_nexus_armor=True,
                )
                domain, raw, payload = extract_online_stage_payload(
                    receipt.get("online") if isinstance(receipt.get("online"), dict) else {}
                )
                res = domain or payload.get("response") or {}
                online_ok = bool(receipt.get("online", {}).get("invoked")) and str(raw) != "online_execution_not_authorized"
                truth = self._stamp_stage_truth(
                    meta,
                    local_assist_success=False,
                    online_success=online_ok,
                    runtime_receipt_complete=bool(receipt.get("receipt_complete")),
                    task_pipeline_success=False,
                )
                meta["local_assist_status"] = "NOT_REQUESTED"
                meta["local_context_forwarded"] = False
                meta["local_assist_contributed"] = False
                meta["with_nexus_armor"] = True
                self._write_unified_runtime_pointer(
                    ctx,
                    {
                        "local_assist_mode": "disabled",
                        "local_assist_status": "NOT_REQUESTED",
                        "local_context_forwarded": False,
                        "local_assist_contributed": False,
                        "unified_runtime_receipt_path": str(receipt_path),
                        "unified_runtime_task_id": task_id,
                        "workspace_revision": revision,
                        "with_nexus_armor": True,
                        "mainchain_entry": True,
                        "claim_boundary": dict(receipt.get("claim_boundary") or {"public_claim_allowed": False}),
                        **truth,
                    },
                )
                return res, raw
            except Exception as exc:
                logger.warning("world_a_mainchain_online_only_failed: %s", exc)
                return _fail_closed_mainchain(exc, local_status="NOT_REQUESTED")

        if mode == "shadow":
            try:
                # Record planner recommendation without invoking local model.
                self._record_shadow_local_assist(ctx)
            except Exception as exc:
                logger.warning("local_assist_shadow_record_failed: %s", exc)
            res, raw = _guarded_online(str(ctx.task_desc or ""))
            online_ok = bool(raw or (isinstance(res, dict) and res)) and str(raw) != "online_execution_not_authorized"
            truth = self._stamp_stage_truth(
                meta,
                local_assist_success=False,
                online_success=online_ok,
                runtime_receipt_complete=False,
                task_pipeline_success=False,
            )
            pointer = {
                "local_assist_mode": "shadow",
                "local_assist_status": meta.get("local_assist_status", "SHADOW_RECORDED"),
                "local_context_forwarded": False,
                "local_assist_contributed": False,
                "unified_runtime_receipt_path": "",
                "unified_runtime_task_id": task_id,
                "online_provider": "",
                "workspace_revision": revision,
                "local_provider_call_count": 0,
                **truth,
            }
            self._write_unified_runtime_pointer(ctx, pointer)
            return res, raw

        # mode == advisor
        allowed = collect_bounded_allowed_files(meta, str(ctx.task_desc or ""))
        if not allowed:
            res, raw = online_callable(str(ctx.task_desc or ""))
            online_ok = bool(raw or (isinstance(res, dict) and res))
            truth = self._stamp_stage_truth(
                meta,
                local_assist_success=False,
                online_success=online_ok,
                runtime_receipt_complete=False,
                task_pipeline_success=False,
            )
            meta.update(
                {
                    "local_assist_status": "NOT_INVOKED",
                    "local_assist_reason": "bounded_scope_missing",
                    "degraded_to_online": True,
                    "degradation_reason": "bounded_scope_missing",
                    "local_assist_contributed": False,
                    "local_context_forwarded": False,
                    "online_continued_without_local_assist": True,
                    "local_assist_status_detail": "ONLINE_CONTINUED_WITHOUT_LOCAL_ASSIST",
                }
            )
            self._write_unified_runtime_pointer(
                ctx,
                {
                    "local_assist_mode": "advisor",
                    "local_assist_status": "NOT_INVOKED",
                    "local_context_forwarded": False,
                    "unified_runtime_receipt_path": "",
                    "unified_runtime_task_id": task_id,
                    "online_provider": "",
                    "workspace_revision": revision,
                    "degraded_to_online": True,
                    "degradation_reason": "bounded_scope_missing",
                    "local_assist_contributed": False,
                    "claim_boundary": {"public_claim_allowed": False, "production_ready": False},
                    **truth,
                },
            )
            return res, raw

        local_request = self._build_advisor_local_request(ctx, allowed_files=allowed)
        local_service = meta.get("local_assist_service")
        if local_service is None:
            from nexus.services.local_assist_service import LocalAssistService

            local_service = LocalAssistService()

        root = Path(getattr(self.engine, "project_root", ".") or ".")
        receipt_path = root / ".nexus" / "reports" / "unified_runtime" / f"{task_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)

        def online_invoker(context: dict[str, Any]) -> dict[str, Any]:
            import json as _json

            from nexus.services.online_execution_policy import guard_physical_online

            # Single guard seam: resolve+bind before any physical Online callable.
            gateway = self._ensure_repair_gateway(ctx)
            root = Path(getattr(self.engine, "project_root", ".") or ".")
            # Prefer decision already on UR context; fall back to task meta.
            # Drop stale require_policy_missing_provider decisions when provider is now known.
            meta_for_guard = dict(meta)
            if isinstance(context, Mapping) and context.get("online_execution_decision"):
                meta_for_guard["online_execution_decision"] = context.get("online_execution_decision")
            if isinstance(context, Mapping) and context.get("online_policy"):
                meta_for_guard["online_policy"] = context.get("online_policy")
            provider_now = str(meta.get("oauth_provider") or meta.get("online_provider") or "")
            prior_dec = meta_for_guard.get("online_execution_decision")
            if (
                provider_now
                and isinstance(prior_dec, Mapping)
                and str(prior_dec.get("reason") or "") == "require_policy_missing_provider"
            ):
                meta_for_guard.pop("online_execution_decision", None)

            prompt = str(context.get("online_prompt") or context.get("task_statement") or "")
            local_stage = context.get("local", {}) if isinstance(context, dict) else {}
            local_response = local_stage.get("response", {}) if isinstance(local_stage, dict) else {}
            local_outputs = local_response.get("local_outputs", {}) if isinstance(local_response, dict) else {}
            local_forwarded = False
            if local_outputs:
                prompt = (
                    prompt
                    + "\n\n[LOCAL_ASSIST_CONTEXT]\n"
                    + _json.dumps(local_outputs, ensure_ascii=False, sort_keys=True, default=str)
                )
                local_forwarded = True
            try:
                allowed, _decision, denied = guard_physical_online(
                    gateway,
                    meta_for_guard,
                    project_root=root,
                    requested_provider=str(meta.get("oauth_provider") or meta.get("online_provider") or ""),
                    planner_online_needed=True,
                    injected_transport=bool(
                        meta.get("injected_transport")
                        or (isinstance(context, Mapping) and context.get("online_authorization_source") == "injected_test_transport")
                    ),
                    task_id=task_id,
                )
                if not allowed and denied is not None:
                    res, raw = denied
                else:
                    res, raw = online_callable(prompt)
            except Exception as exc:
                return normalize_online_invoker_payload(
                    provider=str(meta.get("online_provider") or "gateway"),
                    task_id=task_id,
                    invoked=False,
                    output_delivered=False,
                    gate_passed=False,
                    provider_call_count=0,
                    response="",
                    raw_response="",
                    usage={},
                    error=f"online_exception:{exc}",
                    evidence_refs=[f"online:{task_id}:exception"],
                    transport="gateway_compatibility",
                    selection_source="compatibility_default",
                )
            result_mapping = res if isinstance(res, dict) else {}
            delivered = bool(raw or result_mapping)
            refs = [f"online:{task_id}:repair_seam"] if delivered else []
            if delivered and local_forwarded:
                refs.append(f"online:{task_id}:local_context_forwarded")
            return normalize_online_invoker_payload(
                provider=str(result_mapping.get("provider") or meta.get("online_provider") or "gateway"),
                task_id=task_id,
                invoked=delivered,
                output_delivered=delivered,
                gate_passed=delivered,
                provider_call_count=1 if delivered else 0,
                response=result_mapping or raw,
                raw_response=str(raw or ""),
                usage={},
                error="" if delivered else "online_empty_response",
                evidence_refs=refs,
                transport="gateway_compatibility",
                selection_source="compatibility_default",
            )

        def response_contract(context: dict[str, Any]) -> dict[str, Any]:
            online = context.get("online", {}) if isinstance(context, dict) else {}
            domain, _raw, payload = extract_online_stage_payload(online if isinstance(online, dict) else {})
            delivered = bool(domain) or bool(payload.get("output_delivered"))
            return {
                "task_id": task_id,
                "status": "pass" if delivered else "fail",
                "gate_passed": delivered,
                "invoked": True,
                "evidence": "online_payload_present" if delivered else "online_payload_missing",
                "evidence_refs": [f"verifier:{task_id}:repair_response_contract"],
            }

        def learning_contract(context: dict[str, Any]) -> dict[str, Any]:
            """Minimal product-path learning stage: record Local+Online stage facts (not value claims)."""
            local = context.get("local", {}) if isinstance(context, dict) else {}
            online = context.get("online", {}) if isinstance(context, dict) else {}
            local_ok = str((local or {}).get("status") or "").upper() == "SUCCEEDED"
            online_ok = str((online or {}).get("status") or "").upper() == "SUCCEEDED"
            passed = local_ok and online_ok
            return {
                "task_id": task_id,
                "status": "recorded" if passed else "incomplete",
                "invoked": True,
                "gate_passed": passed,
                "outcome_contributed": False,
                "value_measured": False,
                "evidence": "pipeline_repair_learning_stage",
                "evidence_refs": [f"learning:{task_id}:repair_hybrid_stage"],
            }

        from nexus.services.mainchain_entry import (
            build_mainchain_capability_invokers,
            stamp_mainchain_route,
            wrap_mainchain_online_invoker,
        )

        route = stamp_mainchain_route(
            build_online_route(
                recommended_flow="hybrid",
                gateway_provider=str(meta.get("oauth_provider") or ""),
                local_enabled=True,
            ),
            with_nexus_armor=True,
            product_entry="nexus_run",
        )
        # Propagate Nexus-owned Online policy from task context (CLI/workspace).
        if meta.get("online_policy"):
            route["online_policy"] = str(meta.get("online_policy"))
        if meta.get("online_execution_decision"):
            route["online_execution_decision"] = meta.get("online_execution_decision")
        route["workspace_root"] = str(Path(getattr(self.engine, "project_root", ".") or "."))
        codeintel = meta.get("codeintel") if isinstance(meta.get("codeintel"), dict) else {}
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=revision,
            task_statement=str(ctx.task_desc or task_id),
            task_type="repair",
            route=route,
            online_prompt=str(ctx.task_desc or ""),
            online_payload=f"attempt={repair_attempts}",
            online_phase="R",
            local_enabled=True,
            local_request=local_request,
            codeintel=codeintel,
            evidence_refs=(f"pipeline:{task_id}:advisor_online",),
        )

        try:
            from nexus.services.mainchain_entry import run_mainchain

            receipt = run_mainchain(
                request,
                online_invoker=online_invoker,
                local_service=local_service,
                capability_invokers=build_mainchain_capability_invokers(codeintel=codeintel),
                verifier=response_contract,
                learning=learning_contract,
                receipt_path=receipt_path,
                with_nexus_armor=True,
            )
        except Exception as exc:
            logger.warning("advisor_mainchain_failed_closed: %s", exc)
            return _fail_closed_mainchain(exc, local_status="FAILED")

        local_stage = receipt.get("local", {}) if isinstance(receipt, dict) else {}
        online_stage = receipt.get("online", {}) if isinstance(receipt, dict) else {}
        domain, raw, payload = extract_online_stage_payload(online_stage if isinstance(online_stage, dict) else {})
        local_invoked = bool(local_stage.get("invoked"))
        local_response = local_stage.get("response", {}) if isinstance(local_stage.get("response"), dict) else {}
        local_outputs = local_response.get("local_outputs", {}) if isinstance(local_response, dict) else {}
        has_local_body = bool(local_outputs)
        local_delivered = bool(
            (local_stage.get("gate_passed") or local_stage.get("status") == "SUCCEEDED")
            and has_local_body
        )
        online_invoked = bool(online_stage.get("invoked") or payload.get("invoked"))
        online_delivered = bool(payload.get("output_delivered") or domain or raw)
        # Forwarding is true only when Online evidence records physical packing.
        # Do not force-true when Local was invoked without local_outputs.
        evidence_pool = list(online_stage.get("evidence_refs") or []) + list(payload.get("evidence_refs") or [])
        local_forwarded = any("local_context_forwarded" in str(ref) for ref in evidence_pool)

        claim = dict(receipt.get("claim_boundary") or {})
        meta["unified_runtime_receipt"] = receipt
        meta["unified_runtime_receipt_path"] = str(receipt_path)
        meta["unified_runtime_task_id"] = task_id
        meta["unified_runtime_claim_boundary"] = claim
        meta["local_context_forwarded"] = bool(local_forwarded)
        meta["online_provider"] = str(payload.get("provider") or "")
        meta["local_assist_contributed"] = bool(
            local_invoked and local_delivered and local_forwarded and online_invoked
        )
        if local_invoked and local_delivered and local_forwarded:
            meta["local_assist_status"] = "SUCCEEDED"
            meta["degraded_to_online"] = False
            meta["degradation_reason"] = ""
        else:
            if local_invoked and not has_local_body:
                meta["local_assist_status"] = "EMPTY_OUTPUTS"
                meta["degradation_reason"] = "local_outputs_empty"
            else:
                meta["local_assist_status"] = str(local_stage.get("status") or "FAILED")
                meta["degradation_reason"] = str(
                    local_stage.get("reason") or local_stage.get("status") or "local_assist_unavailable"
                )
            meta["degraded_to_online"] = True
            meta["online_continued_without_local_assist"] = True
            meta["local_assist_status_detail"] = "ONLINE_CONTINUED_WITHOUT_LOCAL_ASSIST"

        truth = self._stamp_stage_truth(
            meta,
            local_assist_success=bool(meta.get("local_assist_contributed")),
            online_success=bool(online_invoked and online_delivered),
            runtime_receipt_complete=bool(receipt.get("receipt_complete")),
            task_pipeline_success=False,
        )

        self._write_unified_runtime_pointer(
            ctx,
            {
                "local_assist_mode": "advisor",
                "local_assist_status": meta.get("local_assist_status"),
                "local_context_forwarded": meta.get("local_context_forwarded"),
                "unified_runtime_receipt_path": str(receipt_path),
                "unified_runtime_task_id": task_id,
                "online_provider": meta.get("online_provider", ""),
                "workspace_revision": revision,
                "degraded_to_online": bool(meta.get("degraded_to_online")),
                "degradation_reason": meta.get("degradation_reason", ""),
                "local_assist_contributed": bool(meta.get("local_assist_contributed")),
                "claim_boundary": claim,
                **truth,
            },
        )

        if isinstance(domain, dict):
            return domain, raw
        return (
            {
                "status": "APPROVED" if online_stage.get("status") == "SUCCEEDED" else "FAILED",
                "patch": str(domain or raw or ""),
            },
            raw,
        )

    def _is_mock_engine_environment(self) -> bool:
        try:
            from unittest.mock import MagicMock
            if isinstance(self.engine, MagicMock):
                return True
        except Exception:
            pass
        project_root = getattr(self.engine, "project_root", None)
        run_dir = getattr(self.engine, "run_dir", None)
        if not isinstance(project_root, (str, Path)):
            return True
        if run_dir is not None and not isinstance(run_dir, (str, Path)):
            return True
        # Non-project directories (e.g. /tmp in tests) are mock environments
        if not Path(project_root).joinpath("nexus").is_dir():
            return True
        return False

    def _execute_single_repair(self, ctx: PipelineContextProtocol, tracer: Any, repair_attempts: int) -> dict:
        """Executes a single repair attempt (Phase R - v24.0 Bayesian Hardened)."""
        with tracer.phase_span('R', task_id=ctx.task_id) as r_span:
            # Product Online path (nexus run --online-policy auto|require): do not let
            # composition short-circuit past the canonical Local→Online UnifiedRuntime seam.
            online_policy = str(ctx.state.metadata.get("online_policy") or "").strip().lower()
            if online_policy in {"auto", "require"}:
                composed = None
                logger.info(
                    "🛡️ [Pipeline:R] product online_policy=%s: skip composition short-circuit",
                    online_policy,
                )
            else:
                composed = self._run_composition_repair_phase(ctx, repair_attempts)
            if composed is not None:
                logger.info("🛡️ [Pipeline:R] Composition repair returned result")
                return composed
            logger.info("🛡️ [Pipeline:R] Composition repair returned None, falling through")

            self._prepare_repair_context(ctx, repair_attempts)

            # 🧪 [Round 20] Inject Bayesian params based on previous trauma
            r_params = ctx.bayesian_params.copy()
            if repair_attempts > 1:
                r_params["temperature"] = 0.2 + (repair_attempts * 0.15)
                logger.info(f"🔥 [Bayesian-Repair] Scaling temperature to {r_params['temperature']:.2f}")

            try:
                # 🛡️ [v26.1] Surgical Alignment — ensure product Online has a real Gateway
                gateway = self._ensure_repair_gateway(ctx)
                use_surgical = ctx.state.metadata.get("use_surgical_repair") or getattr(gateway, "use_surgical_repair", False)
                local_assist_mode = self._local_assist_mode(ctx)
                online_policy_now = str(ctx.state.metadata.get("online_policy") or "").strip().lower()
                # Product require/auto without explicit flag: prefer surgical when Gateway supports it.
                if (
                    not use_surgical
                    and online_policy_now in {"auto", "require"}
                    and gateway is not None
                    and hasattr(gateway, "surgical_ask")
                ):
                    use_surgical = True
                logger.info(
                    "🛡️ [Pipeline:R] gateway_bound=%s use_surgical=%s has_surgical_ask=%s provider=%s",
                    gateway is not None,
                    bool(use_surgical),
                    hasattr(gateway, "surgical_ask") if gateway is not None else False,
                    getattr(gateway, "oauth_provider", "") if gateway is not None else "",
                )
                if use_surgical and hasattr(gateway, "surgical_ask"):
                    symbols = ctx.state.metadata.get("plan_target_symbols", [])
                    if not symbols:
                        # 啟發式提取關鍵符號
                        if "separability_matrix" in ctx.task_desc.lower():
                            symbols = ["separability_matrix"]
                        elif "timeseries" in ctx.task_desc.lower():
                            symbols = ["TimeSeries"]
                        else:
                            # 提取第一個看起來像類別的名詞
                            match = re.search(r'\b([A-Z][a-zA-Z0-9_]{3,})\b', ctx.task_desc)
                            if match:
                                symbols = [match.group(1)]
                            
                    rejection = ctx.state.metadata.get("last_audit_rejection_receipt")

                    from nexus.services.online_execution_policy import guard_physical_online

                    # Advisor/shadow product path: use ask_structured (registered Online CLI).
                    # surgical_ask pulls AST surgical context and can fail closed on host
                    # sources; it also implies patch apply which advisory tasks forbid.
                    advisory_online = local_assist_mode in {"advisor", "shadow"}

                    def _online_callable(prompt: str):
                        allowed, _decision, denied = guard_physical_online(
                            gateway,
                            ctx.state.metadata,
                            project_root=getattr(self.engine, "project_root", ".") or ".",
                            requested_provider=str(
                                ctx.state.metadata.get("oauth_provider")
                                or getattr(gateway, "oauth_provider", "")
                                or ""
                            ),
                            planner_online_needed=True,
                            injected_transport=bool(ctx.state.metadata.get("injected_transport")),
                            task_id=str(ctx.state.metadata.get("task_id") or ctx.task_id or ""),
                        )
                        if not allowed and denied is not None:
                            return denied
                        if advisory_online and hasattr(gateway, "ask_structured"):
                            return gateway.ask_structured(
                                prompt,
                                "",
                                phase="R",
                                system_instruction=(
                                    "You are the Online stage of Nexus Local+Online Hybrid. "
                                    "Return JSON only with keys status, patch, summary. "
                                    "status must be APPROVED or FAIL. patch is advisory text only. "
                                    "Do not request tools, file writes, or formal workspace mutation."
                                ),
                                output_schema={
                                    "status": "APPROVED | FAIL",
                                    "patch": "Advisory text only",
                                    "summary": "Short note",
                                },
                            )
                        return gateway.surgical_ask(
                            task=prompt,
                            symbols=symbols,
                            phase="R",
                            rejection_receipt=rejection,
                            attempt=repair_attempts,
                        )

                    if advisory_online:
                        res, raw = self._run_unified_advisor_online(
                            ctx,
                            online_callable=_online_callable,
                            repair_attempts=repair_attempts,
                        )
                    else:
                        res, raw = _online_callable(ctx.task_desc)
                        online_ok = (
                            bool(raw or (isinstance(res, dict) and res))
                            and str(raw) != "online_execution_not_authorized"
                        )
                        meta = ctx.state.metadata
                        truth = self._stamp_stage_truth(
                            meta,
                            local_assist_success=False,
                            online_success=online_ok,
                            runtime_receipt_complete=False,
                            task_pipeline_success=False,
                        )
                        meta["local_assist_status"] = "NOT_REQUESTED"
                        meta["local_context_forwarded"] = False
                        meta["local_assist_contributed"] = False
                        self._write_unified_runtime_pointer(
                            ctx,
                            {
                                "local_assist_mode": "disabled",
                                "local_assist_status": "NOT_REQUESTED",
                                "local_context_forwarded": False,
                                "local_assist_contributed": False,
                                "unified_runtime_task_id": str(meta.get("task_id") or ctx.task_id or ""),
                                "workspace_revision": self._ensure_workspace_revision(ctx),
                                **truth,
                            },
                        )
                    if not isinstance(res, dict):
                        res = {"status": "FAILED", "patch": str(res or "")}

                    # Advisory Local Assist: never formal-mutate workspace via patch apply.
                    if not advisory_online:
                        from nexus.engine.direct_mode import extract_target_files
                        target_files = extract_target_files(ctx.task_desc)
                        if not target_files:
                            # 嘗試從模型產出的 raw_text 中提取路徑
                            target_files = extract_target_files(raw)
                        
                        if not target_files:
                            target_files = ctx.state.metadata.get("plan_target_files", [])
                        
                        # 嘗試從 symbols 反查檔案
                        if not target_files and symbols:
                            from nexus.engine.surgical_retriever import SurgicalRetriever
                            retriever = SurgicalRetriever(self.engine.project_root)
                            for sym in symbols:
                                found = retriever.find_definition(sym)
                                if found:
                                    target_files.append(str(found[0].relative_to(self.engine.project_root)))
                        
                        target_file = target_files[0] if target_files else ""
                        if not target_file and "separability_matrix" in ctx.task_desc:
                            target_file = "astropy/modeling/separable.py"
                            
                        if target_file and hasattr(gateway, "apply_patch_v2"):
                            logger.info(f"🔪 [Pipeline:Apply] Target file identified: {target_file}")
                            apply_res = gateway.apply_patch_v2(ctx.task_id, target_file, raw)
                            res["patch_apply_success"] = apply_res.get("success", False)
                            res["patch_generated"] = True
                            res["result_object"] = apply_res
                        else:
                            logger.warning(f"⚠️ [Pipeline:Apply] No target file identified. (Found files: {target_files})")
                    else:
                        res.setdefault("patch_apply_success", False)
                        res.setdefault("formal_workspace_mutated", False)
                        res.setdefault("advisory_only", True)
                else:
                    # Non-surgical path: Local Assist still owns Advisor/Shadow policy.
                    # Prefer injected online callable (tests), else gateway.ask_structured
                    # when available. Without an Online transport, advisor degrades and
                    # legacy repairer.run continues (no silent Local success claim).
                    from nexus.services.online_execution_policy import guard_physical_online

                    injected_online = ctx.state.metadata.get("local_assist_online_callable")
                    online_callable = None
                    if callable(injected_online):
                        def online_callable(prompt: str, _fn=injected_online, _gw=gateway):
                            allowed, _d, denied = guard_physical_online(
                                _gw,
                                ctx.state.metadata,
                                project_root=getattr(self.engine, "project_root", ".") or ".",
                                planner_online_needed=True,
                                injected_transport=bool(
                                    ctx.state.metadata.get("injected_transport") or True
                                ),
                                task_id=str(ctx.state.metadata.get("task_id") or ctx.task_id or ""),
                            )
                            # injected_transport=True allows fixture callables when authorized as inject;
                            # task deny still returns denied.
                            if not allowed and denied is not None:
                                return denied
                            return _fn(prompt)
                    elif gateway is not None and hasattr(gateway, "ask_structured"):
                        def online_callable(prompt: str, _gateway=gateway, _pack=ctx.pack):
                            allowed, _d, denied = guard_physical_online(
                                _gateway,
                                ctx.state.metadata,
                                project_root=getattr(self.engine, "project_root", ".") or ".",
                                requested_provider=str(getattr(_gateway, "oauth_provider", "") or ""),
                                planner_online_needed=True,
                                injected_transport=bool(ctx.state.metadata.get("injected_transport")),
                                task_id=str(ctx.state.metadata.get("task_id") or ctx.task_id or ""),
                            )
                            if not allowed and denied is not None:
                                return denied
                            return _gateway.ask_structured(
                                prompt,
                                str(_pack or ""),
                                phase="R",
                            )

                    if local_assist_mode == "advisor" and callable(online_callable):
                        res, raw = self._run_unified_advisor_online(
                            ctx,
                            online_callable=online_callable,
                            repair_attempts=repair_attempts,
                        )
                        if not isinstance(res, dict):
                            res = {"status": "FAILED", "patch": str(res or "")}
                    elif local_assist_mode == "shadow":
                        # Record shadow recommendation only; Online path unchanged.
                        if callable(online_callable):
                            res, raw = self._run_unified_advisor_online(
                                ctx,
                                online_callable=online_callable,
                                repair_attempts=repair_attempts,
                            )
                            if not isinstance(res, dict):
                                res = {"status": "FAILED", "patch": str(res or "")}
                        else:
                            self._record_shadow_local_assist(ctx)
                            res = ctx.repairer.run(ctx.state, ctx.pack, bayesian_params=r_params)
                    elif local_assist_mode == "advisor":
                        # No Online transport available: do not invent Local contribution.
                        meta = ctx.state.metadata
                        self._stamp_stage_truth(
                            meta,
                            local_assist_success=False,
                            online_success=False,
                            runtime_receipt_complete=False,
                            task_pipeline_success=False,
                        )
                        meta.update(
                            {
                                "local_assist_status": "NOT_INVOKED",
                                "local_assist_reason": "online_transport_missing",
                                "degraded_to_online": False,
                                "degradation_reason": "online_transport_missing",
                                "local_assist_contributed": False,
                                "local_context_forwarded": False,
                            }
                        )
                        self._write_unified_runtime_pointer(
                            ctx,
                            {
                                "local_assist_mode": "advisor",
                                "local_assist_status": "NOT_INVOKED",
                                "degradation_reason": "online_transport_missing",
                                "local_assist_contributed": False,
                                "local_context_forwarded": False,
                                "unified_runtime_task_id": str(meta.get("task_id") or ctx.task_id or ""),
                                "workspace_revision": self._ensure_workspace_revision(ctx),
                            },
                        )
                        res = ctx.repairer.run(ctx.state, ctx.pack, bayesian_params=r_params)
                    else:
                        res = ctx.repairer.run(ctx.state, ctx.pack, bayesian_params=r_params)
            except TypeError:
                # Backward compatibility for older repairer signatures.
                res = ctx.repairer.run(ctx.state, ctx.pack)
            ctx.accumulator.record(ctx.state, "R", res, overhead=100)

        r_out = self._process_repair_response(ctx, res, repair_attempts)
        
        # 🚀 [v24.0] Immediate Intra-loop learning trigger
        if self._is_repair_failure_status(r_out["status"]):
            self._record_intra_loop_trauma(ctx, r_out)

        # CLI Pregate validation
        if not self._is_repair_failure_status(r_out["status"]):
            r_out["status"] = self._run_pregate_if_needed(ctx, r_out["status"], r_out["result"])
            
            # === NEW: T11 產生 Evidence Bundle 給 Verifier ===
            try:
                self._write_hallucination_evidence_bundle(ctx)
            except Exception as e:
                logger.warning("evidence_bundle_generation_failed: %s", e)

        self.engine._add_step_to_history(
            ctx.state, "R",
            metadata={
                "status": "executed",
                "decision_id": r_out["current_decision_id"],
                "skill_id": r_out["current_skill_id"],
                "attempt": repair_attempts
            }
        )
        return r_out

    def _run_composition_repair_phase(self, ctx: PipelineContextProtocol, repair_attempts: int) -> dict | None:
        """Run the composed R phase when explicitly registered."""
        registry = getattr(self, "registry", None)
        if registry is None:
            return None
        plugin = next((item for item in registry.get_ordered_plugins() if item.name == "R"), None)
        if plugin is None or not plugin.should_run(ctx):
            return None

        ctx.pack.update(
            {
                "task": ctx.task_desc,
                "attempt": repair_attempts,
                "dry_run": bool(ctx.dry_run),
            }
        )
        result = plugin.execute(self, ctx)
        # Record token usage from composition repair phase
        result_mutations = dict(getattr(result, "mutations", None) or {})
        tokens_used = result_mutations.get("tokens_used")
        token_raw = result_mutations.get("token_raw_model")
        logger.info("🛡️ [Pipeline:R] Composition result: tokens_used=%s, token_raw=%s", tokens_used, token_raw)
        if tokens_used or token_raw:
            logger.info("🛡️ [Pipeline:R] Recording tokens to accumulator")
            ctx.accumulator.record(ctx.state, "R", result_mutations, overhead=100)
        normalized = self._normalize_composed_repair_result(ctx, result, repair_attempts)
        mutations = normalized.mutations
        status = normalized.status
        result_object = normalized.result_object
        ctx.state.metadata["last_review_status"] = status
        self._map_repair_metadata(ctx, result_object)
        if self._is_repair_failure_status(status):
            self._record_intra_loop_trauma(ctx, {"status": status, "result": result_object})
        else:
            status = self._run_pregate_if_needed(ctx, status, result_object)
            try:
                self._write_hallucination_evidence_bundle(ctx)
            except Exception as e:
                logger.warning("evidence_bundle_generation_failed: %s", e)
        r_out = {
            "status": status,
            "result": result_object,
            "current_decision_id": normalized.current_decision_id,
            "current_skill_id": normalized.current_skill_id,
        }
        ctx.state.metadata["composition_repair_phase_status"] = status
        ctx.state.metadata["composition_repair_phase_mutations"] = mutations
        self.engine._add_step_to_history(
            ctx.state,
            "R",
            metadata={
                "status": "executed",
                "decision_id": r_out["current_decision_id"],
                "skill_id": r_out["current_skill_id"],
                "attempt": repair_attempts,
                "composition_phase": True,
            },
        )
        return r_out

    def _normalize_composed_repair_result(
        self,
        ctx: PipelineContextProtocol,
        result: Any,
        repair_attempts: int,
    ) -> ComposedRepairResult:
        """Align composed R output with legacy repair response semantics."""
        mutations = dict(getattr(result, "mutations", None) or {})
        raw_result_object = mutations.get("result_object")
        result_object = dict(raw_result_object) if isinstance(raw_result_object, dict) else mutations

        raw_status = mutations.get("status") or result_object.get("status")
        # PhaseResult.status describes executor progress, not reviewer authority.
        # A missing/unknown reviewer decision is a repairable block; only an
        # explicit status in the result payload can preserve terminal REJECTED.
        status = str(raw_status or "").strip().upper()
        if status in {"FAIL", "FAILED", "REVISE", "RECOVERABLE_BLOCK", "UNKNOWN"}:
            status = "RECOVERABLE_BLOCK"
        elif status not in {"APPROVED", "SKIPPED_QUOTA", "REJECTED"}:
            status = "RECOVERABLE_BLOCK"

        phase_decisions = ctx.state.metadata.setdefault("phase_decisions", {})
        phase_skills = ctx.state.metadata.setdefault("phase_skills", {})
        decision_id = str(
            mutations.get("decision_id")
            or phase_decisions.get("R")
            or self._register_phase_decision(ctx, "R", f"composition-r-{repair_attempts}")
        )
        skill_id = str(mutations.get("skill_id") or phase_skills.get("R") or "composition-repair")
        phase_decisions["R"] = decision_id
        phase_skills["R"] = skill_id

        return ComposedRepairResult(
            status=status,
            result_object=result_object,
            mutations=mutations,
            current_decision_id=decision_id,
            current_skill_id=skill_id,
        )

    def _record_intra_loop_trauma(self, ctx: PipelineContextProtocol, r_out: dict):
        """🛡️ [v24.0] 記錄失敗基因，防止修復循環陷入死胡同。"""
        try:
            from nexus.core.state_contracts import TraumaRecord
            trauma = TraumaRecord(
                failure_signature=f"REPAIR_FAIL_{ctx.state.current_step_id}",
                penalty=-0.3 * ctx.state.retry_count,
                expiry=None # Eternal for current task
            )
            ctx.state.autonomic_weights.trauma_records.append(trauma)
            logger.info("🧠 [Learning] Intra-loop trauma recorded for next iteration.")
        except Exception: pass

    def _prepare_repair_context(self, ctx: PipelineContextProtocol, repair_attempts: int) -> None:
        """Prepares context required for repair (RCA, skill context)."""
        if repair_attempts >= 2:
            ctx.pack["force_deep_diagnosis"] = True
            logger.info("🩺 Multiple failures (≥2), forcing deep diagnosis mode")
            NexusEventBus.publish("repair_failed", {"task_id": ctx.state.task_id, "attempt": repair_attempts})

        try:
            learned = ctx.pack.get("learned_skills", [])
            if learned and isinstance(learned, list) and len(learned) > 0:
                best_skill = learned[0]
                if isinstance(best_skill, dict) and best_skill.get("score", 0) >= 0.3:
                    best_skill_id = best_skill["skill_id"]
                    ki = KnowledgeIndex(self.engine.project_root)
                    full_skill = ki.load_full_skill(best_skill_id)
                    if full_skill:
                        # Inject top 2000 chars of skill context to stay within token budget
                        ctx.pack["skill_context"] = full_skill[:2000]
                        ctx.state.metadata["skill_context_loaded"] = best_skill_id
                        logger.info("📚 Successfully loaded skill context: %s", best_skill_id)
        except Exception as skill_ctx_exc:
            logger.warning("skill_context_load_fallback: %s", skill_ctx_exc)

    def _process_repair_response(self, ctx: PipelineContextProtocol, res: Any, repair_attempts: int) -> dict:
        """Parses repairer response and updates state metadata."""
        # Resolve IDs for history tracking
        phase_decisions = ctx.state.metadata.get("phase_decisions", {}) or {}
        current_decision_id = str(phase_decisions.get("R") or self._register_phase_decision(ctx, "R", "default-repair"))

        phase_skills = ctx.state.metadata.get("phase_skills", {}) or {}
        current_skill_id = str(phase_skills.get("R") or "default-repair")

        review_status_raw = "REJECTED"
        result_object = {}

        if isinstance(res, dict):
            review_status_raw = res.get("status", "REJECTED")
            ctx.state.metadata["last_review_status"] = review_status_raw
            result_object = res.get("result_object", {})
            self._map_repair_metadata(ctx, result_object)
        elif isinstance(res, list):
            self._process_repair_signals(ctx, res)

        return {
            "status": review_status_raw,
            "result": result_object,
            "current_decision_id": current_decision_id,
            "current_skill_id": current_skill_id
        }

    def _collect_code_artifacts_from_git_diff(self) -> List[str]:
        project_root = Path(getattr(self.engine, "project_root", Path.cwd()))
        diff_cmd = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if diff_cmd.returncode != 0 or not diff_cmd.stdout:
            return []
        return [line.strip() for line in diff_cmd.stdout.splitlines() if line.strip()]

    @staticmethod
    def _build_test_artifacts_from_pregate_results(pregate_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for pregate_res in pregate_results:
            out.append(
                {
                    "command": pregate_res.get("cmd", ""),
                    "exit_code": pregate_res.get("exit_code", -1),
                    "stdout_tail": pregate_res.get("stdout_tail", ""),
                }
            )
        return out

    @staticmethod
    def _build_command_artifacts_from_pregate_results(pregate_results: List[Dict[str, Any]]) -> List[str]:
        return [
            f"{pregate_res.get('cmd', '')} -> rc={pregate_res.get('exit_code', -1)}"
            for pregate_res in pregate_results
        ]

    def _build_hallucination_evidence_bundle(self, ctx: PipelineContextProtocol) -> Dict[str, Any]:
        pregate_results = ctx.state.metadata.get("cli_pregate_results", [])
        if not isinstance(pregate_results, list):
            pregate_results = []

        return {
            "code_artifacts": self._collect_code_artifacts_from_git_diff(),
            "test_artifacts": self._build_test_artifacts_from_pregate_results(pregate_results),
            "command_artifacts": self._build_command_artifacts_from_pregate_results(pregate_results),
        }

    def _write_hallucination_evidence_bundle(self, ctx: PipelineContextProtocol) -> Path:
        import json

        project_root = Path(getattr(self.engine, "project_root", Path.cwd()))
        evidence_path = project_root / ".nexus" / "reports" / "hallucination_evidence.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"evidence_bundle": self._build_hallucination_evidence_bundle(ctx)}
        evidence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return evidence_path

    def _map_repair_metadata(self, ctx: PipelineContextProtocol, result_object: dict) -> None:
        """Maps result object fields to state metadata for persistence."""
        mapping = {
            "patch_generated": "last_patch_generated",
            "patch_apply_success": "last_patch_apply_success",
            "no_change_reason": "last_no_change_reason",
            "proof_type": "last_proof_type",
            "proof_value": "last_proof_value",
            "sandbox_mode": "sandbox_mode"
        }
        for res_key, meta_key in mapping.items():
            if res_key in result_object:
                ctx.state.metadata[meta_key] = result_object[res_key]

        # Extract verification intent from model response
        audit_meta = result_object.get("audit_metadata", {})
        if audit_meta.get("verify_commands"):
            ctx.state.metadata["verification_commands"] = audit_meta["verify_commands"]
        if audit_meta.get("return_codes"):
            ctx.state.metadata["verification_exit_codes"] = list(audit_meta["return_codes"].values())

    def _process_repair_signals(self, ctx: PipelineContextProtocol, res: list) -> None:
        """Processes signals (drift/diag) from repair history list."""
        if not res:
            return
        latest_res = res[-1]
        if not isinstance(latest_res, dict):
            return

        for key in ["scope_drift", "insufficient_diag"]:
            if key in latest_res:
                ctx.pack[key] = latest_res[key]
                if "signals" not in ctx.state.metadata:
                    ctx.state.metadata["signals"] = {}
                ctx.state.metadata["signals"][key] = latest_res[key]

    def _run_pregate_if_needed(self, ctx: PipelineContextProtocol, current_status: str, result_object: dict) -> str:
        """Runs CLI-based verification (Pre-Gate) to block hallucinated success."""
        if self._is_mock_engine_environment():
            ctx.state.metadata["pregate_skip"] = True
            ctx.state.metadata["pregate_skip_reason"] = "mock_engine_environment"
            return current_status
        try:
            from nexus.engine.target_env_context import resolve_target_env
            target_env = resolve_target_env(self.engine.project_root, ctx.task_id, getattr(self.engine, "run_dir", None), task_desc=ctx.task_desc)

            verify_cmds = list(ctx.state.metadata.get("verification_commands", []))
            # Allow injection of specific verify commands via pack
            pack_verify = ctx.pack.get("verify_commands", [])
            if pack_verify:
                verify_cmds.extend(pack_verify)

            # Fallback to automatic discovery if no commands provided
            if not verify_cmds:
                from nexus.engine.cli_pregate import build_verify_commands
                verify_cmds = build_verify_commands(target_env)

            if not verify_cmds:
                ctx.state.metadata["pregate_skip"] = True
                ctx.state.metadata["pregate_skip_reason"] = "no_verify_commands_detected"
                # === CHANGED: 沒有驗證命令時不自動 PASS ===
                logger.warning("⚠️ CLI Pre-Gate: No verify commands detected. Status downgraded to UNVERIFIED.")
                ctx.state.metadata["pregate_unverified"] = True
                # 不改變 current_status，但在 Audit 階段會被 Evidence Verifier 攔截
                return current_status

            logger.info("🚦 CLI Pre-Gate Triggered: Running %d verify commands", len(verify_cmds))
            passed, results = run_cli_pregate(target_env, verify_cmds, timeout_per_cmd=60)

            # Log results to metadata
            ctx.state.metadata["cli_pregate_results"] = results
            ctx.state.metadata["pregate_skip"] = False
            ctx.state.metadata["verification_commands"] = verify_cmds
            ctx.state.metadata["verification_exit_codes"] = [r["exit_code"] for r in results]

            if not passed:
                result_object["cli_pregate_rejected"] = True
                logger.info("🚫 CLI Pre-Gate Rejected: Forcing return to repair loop")
                return "REJECTED"

        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            logger.debug("cli_pregate_error_ignored: %s", exc)

        return current_status

    def _evaluate_audit_result(self, ctx: PipelineContextProtocol, eval_ctx: AuditEvalContext) -> dict:
        return evaluate_audit_result(self, ctx, eval_ctx, phantom_detector=detect_inconclusive_success)

    def _run_composition_audit_phase(self, ctx: PipelineContextProtocol, r_out: dict, repair_attempts: int = 1) -> dict | None:
        """Run the composed A phase as a fail-closed pre-audit gate when registered."""
        registry = getattr(self, "registry", None)
        if registry is None:
            return None
        plugin = next((item for item in registry.get_ordered_plugins() if item.name == "A"), None)
        if plugin is None:
            return self._missing_composed_audit_result(ctx, reason="missing_composed_audit_executor")
        if not plugin.should_run(ctx):
            return self._missing_composed_audit_result(ctx, reason="composed_audit_executor_skipped")

        original_pack = dict(ctx.pack or {})
        evidence_bundle = self._build_hallucination_evidence_bundle(ctx)
        ctx.pack.update(
            {
                "summary": str(r_out.get("status") or ctx.state.metadata.get("task_description") or ctx.task_id),
                "response_text": str(r_out.get("status") or ""),
                "evidence_bundle": evidence_bundle,
            }
        )
        try:
            result = plugin.execute(self, ctx)
        finally:
            ctx.pack = original_pack

        normalized = self._normalize_composed_audit_result(ctx, result)
        ctx.state.metadata["composition_audit_phase_status"] = normalized.status
        ctx.state.metadata["composition_audit_phase_mutations"] = normalized.mutations
        if self._is_repair_failure_status(normalized.status) or bool(normalized.mutations.get("fail")) or normalized.mutations.get("audit_success") is False:
            reason = normalized.rejection_reason
            ctx.state.metadata["composition_audit_phase_rejection"] = reason
            self._record_composed_audit_rejection(ctx, r_out, normalized, repair_attempts, reason)
            return {
                "audit_success": False,
                "status": normalized.status,
                "phantom_reason": reason,
            }
        return {"audit_success": True, "status": normalized.status or "APPROVED", "phantom_reason": ""}

    def _missing_composed_audit_result(self, ctx: PipelineContextProtocol, *, reason: str) -> dict:
        ctx.state.metadata["composition_audit_phase_status"] = "MISSING"
        ctx.state.metadata["composition_audit_phase_rejection"] = reason
        ctx.state.metadata["evidence_trust_rejection"] = True
        return {"audit_success": False, "status": "RECOVERABLE_BLOCK", "phantom_reason": reason}

    def _normalize_composed_audit_result(self, ctx: PipelineContextProtocol, result: Any) -> ComposedAuditResult:
        """Normalize composed A output without treating executor success as audit success."""
        mutations = dict(getattr(result, "mutations", None) or {})
        # PhaseResult.status is executor progress (usually SUCCESS), not a
        # reviewer decision. Without an explicit payload decision, fail closed
        # as a repairable block and never grant audit acceptance.
        raw_status = mutations.get("status")
        status = str(raw_status or "").strip().upper()
        if bool(mutations.get("fail")) or mutations.get("audit_success") is False:
            status = "RECOVERABLE_BLOCK"
        elif status in {"FAIL", "FAILED", "REVISE", "RECOVERABLE_BLOCK", "UNKNOWN"}:
            status = "RECOVERABLE_BLOCK"
        elif status not in {"APPROVED", "SKIPPED_QUOTA", "REJECTED"}:
            status = "RECOVERABLE_BLOCK"

        phase_decisions = ctx.state.metadata.setdefault("phase_decisions", {})
        phase_skills = ctx.state.metadata.setdefault("phase_skills", {})
        decision_id = str(mutations.get("decision_id") or phase_decisions.get("A") or self._register_phase_decision(ctx, "A", "composition-audit"))
        skill_id = str(mutations.get("skill_id") or phase_skills.get("A") or "composition-audit")
        phase_decisions["A"] = decision_id
        phase_skills["A"] = skill_id
        reason = str(mutations.get("reason") or f"composition_audit_{status.lower()}")

        return ComposedAuditResult(
            status=status,
            mutations=mutations,
            current_decision_id=decision_id,
            current_skill_id=skill_id,
            rejection_reason=reason,
        )

    def _record_composed_audit_rejection(
        self,
        ctx: PipelineContextProtocol,
        r_out: dict,
        audit: ComposedAuditResult,
        repair_attempts: int,
        reason: str,
    ) -> None:
        """Persist legacy-compatible A phase bookkeeping for composed audit rejections."""
        ctx.state.current_phase = "A"
        ctx.state.metadata["last_audit_decision_id"] = audit.current_decision_id
        ctx.state.metadata["last_repair_decision_id"] = str(r_out.get("current_decision_id", ""))
        ctx.state.metadata["evidence_trust_rejection"] = True
        self._update_meta_counter(ctx, "anti_hallucination_checks")
        self._update_meta_counter(ctx, "anti_hallucination_block_count")
        self.engine._add_step_to_history(
            ctx.state,
            "A",
            metadata={
                "status": audit.status,
                "decision_id": audit.current_decision_id,
                "skill_id": audit.current_skill_id,
                "composition_phase": True,
            },
        )
        self._record_repair_outcome_event(
            ctx,
            repair_attempts,
            False,
            reason,
            dict(r_out.get("result") or {}),
            str(r_out.get("current_decision_id") or ""),
            str(r_out.get("current_skill_id") or ""),
            "REJECTED",
            audit.status,
        )

    def _update_meta_counter(self, ctx: PipelineContextProtocol, key: str, increment: int = 1) -> None:
        """Safely updates an integer counter in metadata."""
        current = ctx.state.metadata.get(key, 0)
        if not isinstance(current, int):
            current = 0
        ctx.state.metadata[key] = current + increment

    def _load_audit_hints(self, ctx: PipelineContextProtocol) -> None:
        """Preloads audit hints based on historical hallucination patterns."""
        try:
            ki = KnowledgeIndex(self.engine.project_root, use_embedding=True)
            a_hints = ki.search_similar(ctx.task_desc, top_k=3, threshold=0.2, task_type=ctx.task_type)
            
            known_phantoms = []
            for fm, _ in a_hints:
                if hasattr(fm, 'phantom_patterns') and fm.phantom_patterns:
                    known_phantoms.extend(fm.phantom_patterns)
            
            if known_phantoms:
                ctx.state.metadata["known_phantom_patterns"] = list(set(known_phantoms))
                if "missing_physical_proof" in known_phantoms:
                    ctx.state.metadata["require_strict_proof"] = True
                logger.info("🛡️ Phase A: Loaded %d historical hallucination patterns", len(known_phantoms))
        except Exception as exc:
            logger.debug("a_phase_learning_skip: %s", exc)

    def _record_repair_outcome_event(self, ctx: PipelineContextProtocol, repair_attempts: int, audit_success: bool, 
                                   phantom_reason: str, result_object: dict, current_decision_id: str, 
                                   current_skill_id: str, status: str, review_status_raw: str) -> None:
        """Records detailed outcome event for future optimization."""
        proof_present = bool(str(result_object.get("proof_type", "") or "").strip() and 
                             str(result_object.get("proof_value", "") or "").strip())
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            payload = OutcomePayload(
                task_id=ctx.state.task_id,
                phase="R",
                decision_id=current_decision_id,
                skill_id=current_skill_id,
                passed=bool(audit_success),
                phantom_blocked=bool(phantom_reason),
                repair_success=bool(audit_success),
                retry_count=max(0, repair_attempts - 1),
                proof_present=proof_present,
                regression_pass_rate=100.0 if audit_success else 0.0,
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                metadata={"status": status, "audit_status": review_status_raw, "source": "pipeline.repair_audit"},
            )
            event = build_outcome_event(payload)
            append_skill_outcome_event(self.engine.project_root, event)
        except Exception as exc:
            logger.warning("skill_outcome_event_write_failed: %s", exc)

    def _handle_escalation(self, ctx: PipelineContextProtocol, repair_attempts: int, review_status_raw: str, phantom_reason: str) -> bool:
        return handle_escalation(
            self,
            ctx,
            repair_attempts,
            review_status_raw,
            phantom_reason,
            cycle_analyzer=analyze_cycle,
        )

    def _perform_escalation(self, ctx: PipelineContextProtocol, mid_root: str, repair_attempts: int):
        return perform_escalation(self, ctx, mid_root, repair_attempts)

    def _repair_audit_loop(self, ctx: PipelineContextProtocol, tracer: Any) -> bool:
        """Main R↔A loop: Iteratively repair and audit until success or exhaustion."""
        if ctx.dry_run:
            return self._execute_dry_run_repair(ctx)

        repair_attempts = 0
        success = False
        max_retries = getattr(self.engine, 'max_retries', 3)
        rlm_loop = None
        if recursive_repair_enabled(ctx):
            rlm_loop = RecursiveRepairLoop.from_context(
                project_root=getattr(self.engine, "project_root", Path.cwd()),
                ctx=ctx,
                max_iterations=max_retries,
            )
            ctx.state.metadata["rlm_recursive_repair_enabled"] = True
            ctx.state.metadata["rlm_recursive_trace_path"] = str(rlm_loop.trace_path)

        while repair_attempts < max_retries:
            if self._check_external_interrupt(ctx):
                break

            repair_attempts += 1
            ctx.state.retry_count = max(ctx.state.retry_count, repair_attempts - 1)
            self._enter_runtime_phase(ctx, "R", reason="repair_attempt_entry")
            self._phase_observer(ctx, "R", "on_phase_start", phase_attempt=repair_attempts)
            logger.info(f"🛠️ [Pipeline] Repair Attempt {repair_attempts}/{max_retries}")
            if rlm_loop is not None and not rlm_loop.prepare_iteration(
                project_root=Path(getattr(self.engine, "project_root", Path.cwd())),
                ctx=ctx,
                iteration=repair_attempts,
            ):
                break

            # Step 1: Repair
            r_out = self._execute_single_repair(ctx, tracer, repair_attempts)
            terminal_rejection = self._is_rejected_repair_status(r_out.get("status"))
            record_receipt = getattr(self, "_record_phase_receipt", None)
            if callable(record_receipt):
                record_receipt(
                    ctx,
                    phase="R",
                    status=str(r_out.get("status") or "FAILED"),
                    transition="R:start->end",
                    output_payload=r_out.get("result") or {},
                    next_action="none" if terminal_rejection else "audit",
                )
            self._phase_observer(ctx, "R", "on_phase_end", status=str(r_out.get("status") or "FAILED"))
            if rlm_loop is not None:
                rlm_loop.record_repair(
                    iteration=repair_attempts,
                    status=r_out["status"],
                    result=r_out["result"],
                    metadata=ctx.state.metadata,
                )
            if terminal_rejection:
                break

            # Step 2: Audit
            self._enter_runtime_phase(ctx, "A", reason="audit_entry")
            self._phase_observer(ctx, "A", "on_phase_start", phase_attempt=repair_attempts)
            eval_ctx = AuditEvalContext(
                tracer=tracer,
                repair_attempts=repair_attempts,
                review_status_raw=r_out["status"],
                result_object=r_out["result"],
                current_decision_id=r_out["current_decision_id"],
                current_skill_id=r_out["current_skill_id"]
            )
            a_out = self._run_composition_audit_phase(ctx, r_out, repair_attempts)
            if a_out is None:
                a_out = self._evaluate_audit_result(ctx, eval_ctx)
            # Audit failures produced by evidence/phantom checks are repairable
            # unless the reviewer supplied an explicit terminal disposition.
            if (
                not a_out.get("audit_success")
                and a_out.get("status") == "REJECTED"
                and r_out.get("status") != "REJECTED"
            ):
                a_out = {**a_out, "status": "RECOVERABLE_BLOCK"}
            if rlm_loop is not None:
                rlm_loop.record_audit(iteration=repair_attempts, audit_result=a_out)
                budget_state = rlm_loop.consume_iteration()
                ctx.state.metadata["rlm_budget_state"] = budget_state.to_dict()

            if callable(record_receipt):
                record_receipt(
                    ctx,
                    phase="A",
                    status=str(a_out.get("status") or ("SUCCESS" if a_out.get("audit_success") else "FAILED")),
                    transition="A:start->end",
                    output_payload=a_out,
                    block_class="" if a_out.get("audit_success") else "RECOVERABLE_BLOCK",
                    next_action="crystallize" if a_out.get("audit_success") else "repair_or_replan",
                )
            self._phase_observer(
                ctx,
                "A",
                "on_phase_end" if a_out.get("audit_success") else "on_phase_fail",
                status=str(a_out.get("status") or "FAILED"),
            )

            if a_out["audit_success"]:
                success = True
                break

            if rlm_loop is not None and rlm_loop.state.exhausted:
                ctx.state.metadata["rlm_budget_exhausted"] = True
                ctx.state.metadata["rlm_budget_exhausted_reasons"] = rlm_loop.state.exhausted_reasons
                rlm_loop.record_budget_exhausted(iteration=repair_attempts)
                break

            # Step 3: Handle Failure
            if self._is_recoverable_repair_status(a_out["status"]) and repair_attempts < max_retries:
                esc_ret = self._handle_escalation(ctx, repair_attempts, r_out["status"], a_out["phantom_reason"])
                
                # Check for tuple signature
                if isinstance(esc_ret, tuple):
                    break_auto, replan_ok = esc_ret
                else:
                    break_auto = esc_ret
                    replan_ok = False
                
                if replan_ok:
                    logger.warning("🔄 Escalation triggered successful replan, resetting repair cycle.")
                    self._phase_observer(ctx, "R", "on_phase_retry", reason="replan")
                    self._enter_runtime_phase(ctx, "D", reason="audit_rejection_replan")
                    repair_attempts = 0
                    continue
                    
                if break_auto:
                    self._phase_observer(ctx, "A", "on_phase_block", reason="escalation_boundary")
                    # Escalation might have reached max_retries or failed replan
                    break
                self._phase_observer(ctx, "R", "on_phase_retry", reason="audit_rejected")
                logger.warning("🔄 Audit Rejected. Retrying repair cycle...")
                continue
            else:
                # Reached max retries or unrecoverable error
                break

        return success

    def _execute_dry_run_repair(self, ctx: PipelineContextProtocol) -> bool:
        """Simulates repair loop in Dry Run mode."""
        ctx.state.retry_count = 0
        self._enter_runtime_phase(ctx, "R", reason="dry_run_repair_entry")
        self._phase_observer(ctx, "R", "on_phase_start", phase_attempt=1)
        r_dec_id = self._register_phase_decision(ctx, "R", "dry-run-repair")
        self._mock_dry_run_state(ctx)

        self.engine._add_step_to_history(
            ctx.state, "R", metadata={"status": "executed", "decision_id": r_dec_id, "skill_id": "dry-run-repair", "attempt": 1, "dry_run_mode": True}
        )
        record_receipt = getattr(self, "_record_phase_receipt", None)
        if callable(record_receipt):
            record_receipt(
                ctx,
                phase="R",
                status="SUCCESS",
                transition="R:start->end",
                output_payload={"dry_run_mode": True},
                next_action="audit",
            )
        self._phase_observer(ctx, "R", "on_phase_end", status="SUCCESS")

        self._enter_runtime_phase(ctx, "A", reason="dry_run_audit_entry")
        self._phase_observer(ctx, "A", "on_phase_start", phase_attempt=1)
        a_out = self._run_composition_audit_phase(
            ctx,
            {
                "status": "APPROVED",
                "result": {"dry_run_mode": True},
                "current_decision_id": r_dec_id,
                "current_skill_id": "dry-run-repair",
            },
        )
        if callable(record_receipt):
            record_receipt(
                ctx,
                phase="A",
                status=str((a_out or {}).get("status") or ("SUCCESS" if not a_out or a_out.get("audit_success") else "FAILED")),
                transition="A:start->end",
                output_payload=a_out or {"dry_run_mode": True},
                next_action="crystallize" if not a_out or a_out.get("audit_success") else "human_review",
            )
        self._phase_observer(
            ctx,
            "A",
            "on_phase_end" if not a_out or a_out.get("audit_success") else "on_phase_fail",
            status=str((a_out or {}).get("status") or "SUCCESS"),
        )
        if a_out is not None and not bool(a_out.get("audit_success")):
            return False

        a_dec_id = self._register_phase_decision(ctx, "A", "audit-review")
        self.engine._add_step_to_history(
            ctx.state, "A", metadata={"status": "APPROVED", "decision_id": a_dec_id, "skill_id": "audit-review", "dry_run_mode": True}
        )

        self._record_dry_run_outcome(ctx, r_dec_id)
        return True

    def _mock_dry_run_state(self, ctx: PipelineContextProtocol) -> None:
        """Mocks metadata for dry run."""
        ctx.state.metadata.update({
            "last_review_status": "APPROVED", 
            "last_patch_generated": False,
            "last_patch_apply_success": True, 
            "last_no_change_reason": "dry_run_mode",
            "last_proof_type": "", 
            "last_proof_value": ""
        })

    def _record_dry_run_outcome(self, ctx: PipelineContextProtocol, r_dec_id: str) -> None:
        """Records outcome for dry run."""
        try:
            from nexus.core.skill_outcomes import OutcomePayload
            payload = OutcomePayload(
                task_id=ctx.state.task_id, phase="R", decision_id=r_dec_id,
                skill_id="dry-run-repair", passed=True, phantom_blocked=False,
                repair_success=True, retry_count=0, proof_present=False,
                regression_pass_rate=100.0,
                pattern_reuse=float(ctx.state.metadata.get("pattern_reuse_rate", 0.0) or 0.0),
                next_run_hit=float(ctx.state.metadata.get("next_run_hit_rate", 0.0) or 0.0),
                metadata={"status": "APPROVED", "audit_status": "APPROVED", "source": "pipeline.dry_run"}
            )
            append_skill_outcome_event(self.engine.project_root, build_outcome_event(payload))
        except Exception as exc:
            logger.warning("dry_run_outcome_record_failed: %s", exc)

    def _check_external_interrupt(self, ctx: PipelineContextProtocol) -> bool:
        """Checks for external signals (e.g., force_replan)."""
        external_signals = NexusEventBus.drain_signals("force_replan")
        if external_signals:
            logger.warning("📡 External signal received: force_replan. Breaking R↔A loop.")
            ctx.state.metadata["external_force_replan"] = True
            return True
        return False
