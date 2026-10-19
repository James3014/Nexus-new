"""Dispatch / worker-context members of ``SelfHostedTaskService``.

Big-file split S9 (Issue #2604). ``_WorkerDispatchMixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``_select_initial_provider`` and ``_next_ready_provider``: the worker preflight walk over
  the contract's provider order / the escalation policy;
* ``_assert_persisted_workforce_dispatch``: the persisted Workforce dispatch binding versus
  the request and the fresh binding (``WORKFORCE_DISPATCH_*_DRIFT``);
* ``_revalidate_tracked_dispatch_task_card`` and ``_revalidate_provider_boundary``: the
  governed identity re-read immediately before provider-side work;
* ``_replace_failed_target``: escalation replaces a failed Target lease through the
  worktree manager and the controller;
* ``_worker_context_materialization``: the frozen Planner projection and its evidence
  journal (STARTED / COMPLETE) before a WorkerRegistry call;
* ``_run_default_resumable`` and ``_run_default``: the default runner, through
  ``RuntimeCoordinationBridge``.

Their source lines are verbatim, except that every facade-module name they load at run
time (``ContractKind``, ``inspect``, ``_jsonable``, ``_sha256_json``, the dispatch-binding
helpers ``_workforce_dispatch_inputs`` / ``_tracked_dispatch_required``, the task-card
helpers ``validate_task_card_binding`` / ``resolve_lifecycle_identity`` /
``_resolve_task_card_path`` and ``_codeintel_lookup_context``) is resolved at call time
through ``_service_module()``, so patches on the facade keep taking effect.

``_worker_context_materialization`` writes the task state through ``_mutate_state`` (state
lock, then the runtime store's atomic replace) and runs the selected capability invokers
outside the lock; ``_run_default_resumable`` hands the attempt to
``RuntimeCoordinationBridge.execute`` (worker launch and leasing stay there).  Members are
reached through ``self``; ``_launch_worker`` and the process helpers live in
``_FinalizeRuntimeMixin`` (``parts/finalize_runtime.py``, split S11; ``_launch_worker``
still derives the worker source root from the facade's ``__file__``).
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional, Sequence

if TYPE_CHECKING:
    from nexus.executors.worker_contract import WorkerExecutionReceipt
    from nexus.executors.worker_registry import WorkerRegistry
    from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
    from nexus.orchestrator.task_contract import ArchitectTaskContract
    from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy
    from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _WorkerDispatchMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService (and its _StateStoreMixin base)
        ephemeral: bool
        worker_registry: WorkerRegistry

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

    # fmt: off
    def _select_initial_provider(
        self,
        contract: ArchitectTaskContract,
        *,
        before_preflight: Callable[[str], None],
    ) -> tuple[str, Any]:
        providers = list(contract.provider_order or [str(contract.preferred_provider or "codex")])
        failures: list[str] = []
        for provider in providers:
            before_preflight(provider)
            preflight = self.worker_registry.preflight(provider)
            if preflight.ready:
                return provider, preflight
            failures.append(f"{provider}: {preflight.reason}")
        raise RuntimeError("worker preflight failed: " + "; ".join(failures))

    def _next_ready_provider(
        self,
        policy: WorkerEscalationPolicy,
        attempts: Sequence[WorkerExecutionReceipt],
        *,
        before_preflight: Callable[[str], None],
    ) -> Optional[str]:
        attempted = {attempt.provider for attempt in attempts}
        for provider in policy.provider_order or (policy.strong_provider,):
            if provider in attempted:
                continue
            before_preflight(provider)
            if self.worker_registry.preflight(provider).ready:
                return provider
        return None

    @staticmethod
    def _assert_persisted_workforce_dispatch(
        state: Mapping[str, Any],
        request: Mapping[str, Any],
        binding: Optional[Mapping[str, Any]],
        *,
        active_provider: Optional[str] = None,
    ) -> None:
        if binding is None:
            return
        persisted = state.get("workforce_dispatch")
        if not isinstance(persisted, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        original_demands, original_admission = _service_module()._workforce_dispatch_inputs(request)
        if persisted.get("demands") != _service_module()._jsonable(original_demands) or persisted.get("admission") != _service_module()._jsonable(original_admission):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        expected = {
            "selected_worker_id": binding["worker_id"],
            "selected_provider": binding["provider"],
            "selected_model": binding["model"],
            "workforce_policy_hash": binding["policy_hash"],
            "workforce_binding_hash": binding["binding_hash"],
            "workforce_aggregate_binding_hash": binding["aggregate_binding_hash"],
        }
        if any(str(state.get(field) or "") != str(value or "") for field, value in expected.items()):
            raise RuntimeError("WORKFORCE_DISPATCH_STATE_DRIFT")
        expected_envelope = binding.get("canonical_dispatch_envelope")
        persisted_envelope = state.get("canonical_dispatch_envelope")
        if isinstance(expected_envelope, Mapping) or "canonical_dispatch_envelope" in request:
            if not isinstance(expected_envelope, Mapping) or dict(persisted_envelope or {}) != dict(expected_envelope):
                raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_STATE_DRIFT")
            persisted_identity = {
                "task_id": state.get("task_id"),
                "attempt_id": state.get("attempt_id"),
                "task_card_path": state.get("task_card_path"),
                "task_card_hash": state.get("task_card_hash"),
            }
            if any(expected_envelope.get(field) != value for field, value in persisted_identity.items()):
                raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT")
        if active_provider is not None and str(active_provider) != str(binding["provider"]):
            raise RuntimeError("WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT")

    def _revalidate_tracked_dispatch_task_card(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        state: Mapping[str, Any],
        binding: Optional[Mapping[str, Any]],
    ) -> None:
        """Re-read the tracked card immediately before provider-side work."""
        if binding is None:
            if _service_module()._tracked_dispatch_required(request, state):
                raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
            return
        envelope = binding.get("canonical_dispatch_envelope")
        if not isinstance(envelope, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISSING")
        if str(request.get("contract_kind") or "") != _service_module().ContractKind.TRACKED_TASK_CARD.value:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked dispatch card required")

        _service_module().validate_task_card_binding(contract, request, is_ephemeral=self.ephemeral)
        identity = _service_module().resolve_lifecycle_identity(
            contract,
            request,
            is_ephemeral=self.ephemeral,
        )
        requested_path = str(request.get("task_card_path") or "")
        expected = {
            "task_id": contract.task_id,
            "attempt_id": str(request.get("attempt_id") or ""),
            "task_card_path": requested_path,
            "task_card_hash": str(request.get("task_card_hash") or ""),
        }
        if not all(expected.values()):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked identity incomplete")
        if any(str(envelope.get(field) or "") != value for field, value in expected.items()):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: dispatch envelope identity drifted")
        persisted = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "task_card_path": str(state.get("task_card_path") or ""),
            "task_card_hash": str(state.get("task_card_hash") or ""),
        }
        if persisted != expected:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: persisted card identity drifted")
        if str(state.get("contract_kind") or "") != _service_module().ContractKind.TRACKED_TASK_CARD.value:
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: persisted tracked contract missing")
        if (
            identity.get("contract_kind") != _service_module().ContractKind.TRACKED_TASK_CARD.value
            or str(identity.get("task_card_path") or "")
            != str(_service_module()._resolve_task_card_path(requested_path))
            or str(identity.get("task_card_hash") or "") != expected["task_card_hash"]
        ):
            raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked card changed after submit")

    def _revalidate_provider_boundary(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        task_id: str,
        binding: Optional[Mapping[str, Any]],
        *,
        active_provider: Optional[str] = None,
    ) -> None:
        """Re-read all governed identity immediately before provider-side work."""
        state = self._read_state(task_id) or {}
        if state.get("status") == "BLOCKED_INVALID_STATE" or state.get("state_valid") is False:
            # An unreadable persisted state cannot prove the task is untracked.
            raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING: persisted state invalid")
        if binding is None and _service_module()._tracked_dispatch_required(request, state):
            # Tracked (Task Card) dispatch never reaches a model worker without
            # a fresh Workforce Admission binding, on any execution lane.
            # Untracked ISOLATED_TARGET dispatch has no admission path yet
            # (known gap, see WORKFORCE_EXECUTION_OVERLAY.md); DIRECT_CANONICAL
            # is Owner-exempt per AGENTS.md (#1761).
            raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
        self._revalidate_tracked_dispatch_task_card(contract, request, state, binding)
        self._assert_persisted_workforce_dispatch(
            state,
            request,
            binding,
            active_provider=active_provider,
        )

    @staticmethod
    def _replace_failed_target(
        manager: WorktreeManager,
        controller: SelfHostedDevelopmentController,
        contract: ArchitectTaskContract,
        lease: TargetWorktreeLease,
        *,
        task_states: Optional[Mapping[str, dict]] = None,
    ) -> TargetWorktreeLease:
        manager.verify_controller_unchanged(
            contract,
            expected_status_sha256=lease.controller_status_sha256,
        )
        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=lease.target_worktree)
        if target_head != lease.initial_head:
            raise RuntimeError("failed worker changed Target HEAD; escalation is blocked")
        manager.cleanup(contract.task_id, force=True)
        prepare_task = controller.prepare_task
        if "task_states" in _service_module().inspect.signature(prepare_task).parameters:
            return prepare_task(contract, task_states=task_states)
        return prepare_task(contract)

    def _worker_context_materialization(
        self,
        *,
        request: Mapping[str, Any],
        state: Mapping[str, Any],
        task_id: str,
        attempt_id: str,
        fresh_submission: bool,
        contract: ArchitectTaskContract,
        lease: TargetWorktreeLease,
        base_prompt: str,
        actual_provider: str,
        actual_model: str | None,
    ) -> tuple[str, dict[str, Any]] | None:
        """Materialize the frozen Planner projection before a WorkerRegistry call.

        The evidence journal is derived state kept beside the signed request and
        action.  A resumed attempt may consume a completed journal only; it may
        never execute an absent or incomplete journal a second time.
        """
        planner_input = request.get("planner_output")
        envelope = state.get("canonical_dispatch_envelope") or request.get(
            "canonical_dispatch_envelope"
        )
        if not isinstance(planner_input, Mapping) and not isinstance(envelope, Mapping):
            if request.get("worker_candidate_ingress") or state.get("workforce_dispatch"):
                raise RuntimeError("worker_context_binding_missing")
            return None
        if not isinstance(planner_input, Mapping) or not isinstance(envelope, Mapping):
            raise RuntimeError("worker_context_binding_missing")

        from nexus_runtime.task_context import (
            append_model_context_to_prompt,
            build_worker_context_package,
        )

        from nexus.services.mainchain_entry import build_mainchain_capability_invokers
        from nexus.services.unified_runtime import materialize_selected_capability_evidence

        if request.get("task_id") not in (None, "", task_id):
            raise RuntimeError("worker_context_task_substitution")
        if request.get("attempt_id") not in (None, "", attempt_id):
            raise RuntimeError("worker_context_attempt_substitution")
        planner = dict(planner_input)
        planner_context = planner.get("context")
        planner_codeintel = (
            planner_context.get("codeintel")
            if isinstance(planner_context, Mapping)
            and isinstance(planner_context.get("codeintel"), Mapping)
            else None
        )
        request_codeintel = request.get("codeintel")
        codeintel = (
            dict(request_codeintel)
            if isinstance(request_codeintel, Mapping)
            else dict(planner_codeintel)
            if planner_codeintel is not None
            else None
        )
        decision_id = str(envelope.get("planner_decision_hash") or "").strip()
        plan_hash = str(envelope.get("planner_plan_hash") or "").strip()
        workspace_revision = str(
            request.get("workspace_revision")
            or request.get("controller_revision")
            or state.get("controller_revision")
            or ""
        ).strip()
        task_statement = str(request.get("what") or request.get("task_statement") or "")
        preliminary_request = {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "what": task_statement,
            "planner_output": planner,
            "canonical_dispatch_envelope": dict(envelope),
        }
        preliminary_package = build_worker_context_package(preliminary_request)
        if preliminary_package.get("status") != "PASS":
            raise RuntimeError("worker_context_preflight_invalid")
        selected = [str(item) for item in preliminary_package.get("selected_capability_ids", ())]
        envelope_provider = str(envelope.get("provider") or "").strip()
        envelope_model = str(envelope.get("model") or "").strip()
        if envelope_provider != str(actual_provider) or envelope_model != str(actual_model or ""):
            raise RuntimeError("worker_context_provider_model_substitution")
        action_request_hash = str(state.get("action_request_hash") or "").strip()
        controller_revision = str(state.get("controller_revision") or contract.controller_revision).strip()
        target_revision = str(lease.initial_head or contract.target_base_revision).strip()
        revision = controller_revision
        target_worktree = str(Path(lease.target_worktree).resolve())
        record = state.get("worker_model_context_materialization")

        if record is not None:
            if not isinstance(record, Mapping) or record.get("status") != "COMPLETE":
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_incomplete")
            expected = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "action_request_hash": action_request_hash,
                "revision": revision,
                "planner_decision_id": decision_id,
                "planner_plan_hash": plan_hash,
                "selected_capabilities": selected,
                "controller_revision": controller_revision,
                "target_revision": target_revision,
                "target_worktree": target_worktree,
            }
            for key, value in expected.items():
                if record.get(key) != value:
                    raise RuntimeError(f"worker_context_materialization_{key}_mismatch")
            bundle = record.get("bundle")
            if not isinstance(bundle, Mapping):
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_bundle_missing")
            bundle_hash = str(record.get("bundle_hash") or "")
            if not bundle_hash or _service_module()._sha256_json(bundle) != bundle_hash:
                raise RuntimeError("worker_context_bundle_hash_mismatch")
            # Records written before #2688 have no observations; when present they are bound.
            if "capability_observations" in record or "capability_observations_hash" in record:
                observations_hash = str(record.get("capability_observations_hash") or "")
                observations = record.get("capability_observations")
                if not observations_hash or _service_module()._sha256_json(
                    observations
                ) != observations_hash:
                    raise RuntimeError("worker_context_observations_hash_mismatch")
        else:
            if not fresh_submission:
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_missing")
            started_record = {
                "schema": "nexus.worker_model_context_materialization.v1",
                "status": "STARTED",
                "task_id": task_id,
                "attempt_id": attempt_id,
                "action_request_hash": action_request_hash,
                "revision": revision,
                "controller_revision": controller_revision,
                "target_revision": target_revision,
                "target_worktree": target_worktree,
                "planner_decision_id": decision_id,
                "planner_plan_hash": plan_hash,
                "selected_capabilities": selected,
            }

            def claim(current: dict[str, Any]) -> None:
                if current.get("attempt_id") != attempt_id:
                    raise RuntimeError("worker_context_materialization_attempt_changed")
                if current.get("worker_model_context_materialization") is not None:
                    raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_replay")
                current["worker_model_context_materialization"] = _service_module()._jsonable(started_record)

            claimed = self._mutate_state(task_id, claim)
            if not isinstance(claimed, Mapping):
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_claim")
            state = claimed
            if (state.get("worker_model_context_materialization") or {}).get("status") != "STARTED":
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_claim_readback")
            invokers = build_mainchain_capability_invokers(
                codeintel=codeintel,
                include_postflight_gates=True,
            )
            capability_results, bundle = materialize_selected_capability_evidence(
                planner_output=planner,
                selected_capabilities=selected,
                task_id=task_id,
                task_statement=task_statement,
                workspace_revision=workspace_revision,
                plan_hash=plan_hash,
                planner_decision_id=decision_id,
                capability_invokers=invokers,
                capability_context={
                    **{
                        key: request[key]
                        for key in (
                            "task_id",
                            "workspace_revision",
                            "task_statement",
                            "planner",
                            # #1579: optional caller identity hint for RIE knowledge
                            # applicability; validated by the codeintel hook.
                            "rie_knowledge_identity",
                        )
                        if key in request
                    },
                    **_service_module()._codeintel_lookup_context(
                        request.get("codeintel_lookup"), target_worktree
                    ),
                    # #2688: xray scans the task's own files (only xray reads this key);
                    # files the task will create do not exist yet and are left out.
                    **_xray_targets_context(request.get("allowed_files"), target_worktree),
                    "workspace_root": target_worktree,
                    "target_worktree": target_worktree,
                    "target_revision": target_revision,
                    "controller_revision": controller_revision,
                },
                codeintel=codeintel,
            )
            bundle = dict(bundle)
            observations = _capability_observations(capability_results)
            record = {
                "schema": "nexus.worker_model_context_materialization.v1",
                "status": "COMPLETE",
                "task_id": task_id,
                "attempt_id": attempt_id,
                "action_request_hash": action_request_hash,
                "revision": revision,
                "controller_revision": controller_revision,
                "target_revision": target_revision,
                "target_worktree": target_worktree,
                "planner_decision_id": decision_id,
                "planner_plan_hash": plan_hash,
                "selected_capabilities": selected,
                "bundle_hash": _service_module()._sha256_json(bundle),
                "bundle": bundle,
                # #2688: what each executor actually did (trigger, store, outputs). The
                # runtime's bundle entries drop these fields; witnesses need them.
                "capability_observations": observations,
                "capability_observations_hash": _service_module()._sha256_json(observations),
                "producer_revision": revision,
            }

            def persist(current: dict[str, Any]) -> None:
                if current.get("attempt_id") != attempt_id:
                    raise RuntimeError("worker_context_materialization_attempt_changed")
                existing = current.get("worker_model_context_materialization")
                if not isinstance(existing, Mapping) or existing.get("status") != "STARTED":
                    raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_replay")
                if any(existing.get(key) != started_record.get(key) for key in started_record):
                    raise RuntimeError("worker_context_materialization_binding_changed")
                current["worker_model_context_materialization"] = _service_module()._jsonable(record)

            persisted = self._mutate_state(task_id, persist)
            if not isinstance(persisted, Mapping):
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_write")
            state = persisted
            record = state.get("worker_model_context_materialization")
            if not isinstance(record, Mapping) or record.get("status") != "COMPLETE":
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_materialization_readback")
            bundle = record.get("bundle")
            if not isinstance(bundle, Mapping):
                raise RuntimeError("OUTCOME_UNKNOWN:worker_context_bundle_readback")

        planner["capability_evidence_bundle"] = dict(bundle)
        package_request = dict(request)
        package_request["task_id"] = task_id
        package_request["attempt_id"] = attempt_id
        package_request["workspace_revision"] = workspace_revision
        package_request["task_statement"] = task_statement
        package_request["planner_output"] = planner
        package_request["canonical_dispatch_envelope"] = dict(envelope)
        package = build_worker_context_package(package_request)
        prompt = append_model_context_to_prompt(base_prompt, package)
        return prompt, package

    def _run_default_resumable(
        self,
        contract: ArchitectTaskContract,
        request: Mapping[str, Any],
        update: Callable[[str, dict[str, Any]], None],
        *,
        task_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        from nexus.orchestrator.runtime_coordination_bridge import RuntimeCoordinationBridge

        return RuntimeCoordinationBridge(self).execute(  # pyright: ignore[reportReturnType]
            task_id,
            attempt_id,
            contract=contract,
            request=request,
            update=update,
        )

    def _run_default(self, contract, request, update):
        return self._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=str((self._read_state(contract.task_id) or {}).get("attempt_id", "")),
        )
    # fmt: on


def _xray_targets_context(allowed_files: Any, target_worktree: Any) -> dict[str, Any]:
    """``{"xray_targets": [...]}``: the allowed paths that already exist (#2688).

    Always present when the task names allowed files, possibly empty: xray then reports
    that no task file exists yet instead of scanning an unrelated default target.
    """
    if not isinstance(allowed_files, (list, tuple)) or not allowed_files or not target_worktree:
        return {}
    root = Path(str(target_worktree))
    return {"xray_targets": [str(path) for path in allowed_files if (root / str(path)).exists()]}


_OBSERVATION_OUTCOME_KEYS = (
    "semantic_status",
    "output_paths",
    "resolved_run_root",
    "scan_targets",
    "hit_count",
    "findings_hit_count",
    "confidence",
    "state_file",
)
_OBSERVATION_MAX_TEXT = 512
_OBSERVATION_MAX_ITEMS = 16
_OBSERVATION_MAX_CAPABILITIES = 64


def _observation_value(value: Any) -> Any:
    """JSON-safe, bounded scalar or list of short strings; anything else is dropped."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None  # drop NaN and +/-inf
    if isinstance(value, str):
        return value[:_OBSERVATION_MAX_TEXT]
    if isinstance(value, (list, tuple)):
        items = [v[:_OBSERVATION_MAX_TEXT] for v in value if isinstance(v, str)]
        return items[:_OBSERVATION_MAX_ITEMS]
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _capability_observations(results: Any) -> dict[str, Any]:
    """Bounded per-capability facts from the raw executor receipts (#2688).

    Keeps only identifiers, paths and counts, bounded and JSON-safe (never prompt
    content, payloads or any error text), so a witness can tell whether and how a
    capability ran and which store it used.  The record binds them with a hash.
    """
    if not isinstance(results, Mapping):
        return {}
    observations: dict[str, Any] = {}
    for name, stage in results.items():
        if not isinstance(stage, Mapping):
            continue
        receipt = _mapping(stage.get("response"))
        inner = _mapping(receipt.get("response"))
        outcome = _mapping(inner.get("outcome"))
        result = _mapping(outcome.get("result"))
        entry: dict[str, Any] = {
            "status": _observation_value(stage.get("status")),
            "skip_reason": _observation_value(stage.get("skip_reason") or ""),
            "trigger_source": _observation_value(receipt.get("trigger_source") or ""),
        }
        for key in _OBSERVATION_OUTCOME_KEYS:
            if key in outcome:
                value = _observation_value(outcome[key])
                if value is not None:
                    entry[key] = value
        if outcome.get("error"):
            entry["error_present"] = True  # never the message: it can carry task text
        if "root" in result:
            root = _observation_value(result["root"])
            if isinstance(root, str):
                entry["store_root"] = root
        observations[str(name)[:_OBSERVATION_MAX_TEXT]] = entry
        if len(observations) >= _OBSERVATION_MAX_CAPABILITIES:
            break
    return observations
