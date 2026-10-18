"""Task-build members of ``SelfHostedTaskService``.

Big-file split S8b (Issue #2582). ``_TaskBuildMixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``build_contract``: a submit / retry request -> ``ArchitectTaskContract`` (workforce
  dispatch binding, provider order and budget, expected evidence, owner-inline
  authority-change confirmation, target roots, ``git rev-parse HEAD`` for a missing
  Controller revision, collaboration realm, fail-to-pass);
* ``_terminal_retry_revision_refresh_allowed``: may a terminal retry refresh its
  predecessor's Controller / Target revisions (``git merge-base --is-ancestor``);
* ``_contract_from_state``, ``_prompt``, ``_set_child_pgid``, ``_lease_from_state``,
  ``_capture_resumed_candidate``, ``_receipt_from_state`` and ``_escalation_policy``.

Their source lines are verbatim, except that every facade-module name they load at run
time (the contract model types, ``subprocess``, ``uuid4``, the target-root and
dispatch-binding helpers, the retry predecessor proofs, the status / provider / budget
constants and ``_utc_now``) is resolved at call time through ``_service_module()``, so
patches on the facade keep taking effect.

``_set_child_pgid`` writes the task state through ``_mutate_state`` (state lock, then the
runtime store's atomic replace); ``build_contract`` and the revision refresh run read-only
git in the Controller repository.  Members are reached through ``self``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

if TYPE_CHECKING:
    from nexus.contracts.collaboration_realm import CollaborationExecutionRealm
    from nexus.executors.worker_contract import WorkerExecutionReceipt
    from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
    from nexus.orchestrator.task_contract import ArchitectTaskContract
    from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy
    from nexus.orchestrator.worktree_manager import TargetWorktreeLease


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _TaskBuildMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService's _StateStoreMixin base

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

    # fmt: off
    def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract:
        if "prompt" in request:
            raise ValueError("prompt is not accepted; submit WHAT and WHY")
        dispatch_binding = _service_module().validate_workforce_dispatch_binding(request)
        if dispatch_binding is not None:
            requested_provider = str(request.get("worker", "auto")).strip().lower()
            if requested_provider not in {"", "auto", dispatch_binding["provider"]}:
                raise RuntimeError("WORKFORCE_ADMISSION_PROVIDER_MISMATCH")
            caller_provider = str(request.get("provider") or "").strip().lower()
            if caller_provider and caller_provider != dispatch_binding["provider"].lower():
                raise RuntimeError("WORKFORCE_ADMISSION_PROVIDER_MISMATCH")
            caller_worker_id = str(request.get("worker_id") or "").strip()
            if caller_worker_id and caller_worker_id != dispatch_binding["worker_id"]:
                raise RuntimeError("WORKFORCE_ADMISSION_WORKER_MISMATCH")
            requested_model = str(request.get("model") or "").strip()
            if requested_model and requested_model != dispatch_binding["model"]:
                raise RuntimeError("WORKFORCE_ADMISSION_MODEL_MISMATCH")
            request = dict(request)
            request.update({
                "worker": dispatch_binding["provider"],
                "provider": dispatch_binding["provider"],
                "model": dispatch_binding["model"],
                "worker_id": dispatch_binding["worker_id"],
                "worker_order": [dispatch_binding["provider"]],
            })
        worker = str(request.get("worker", "codex")).strip().lower()
        requested_worker = worker
        if worker not in _service_module().SUPPORTED_WORKER_PROVIDERS:
            if worker != "auto":
                raise ValueError(
                    "worker must be one of: auto, " + ", ".join(_service_module().SUPPORTED_WORKER_PROVIDERS)
                )
        provider_order = request.get("worker_order")
        if provider_order is None:
            provider_order = (
                list(_service_module().SUPPORTED_WORKER_PROVIDERS)
                if requested_worker == "auto"
                else [worker]
            )
        provider_order = [str(provider).strip().lower() for provider in provider_order]
        if worker == "auto" and not provider_order:
            raise ValueError("worker_order must be non-empty for auto selection")
        if worker == "auto" and (set(provider_order) - set(_service_module().SUPPORTED_WORKER_PROVIDERS) or len(set(provider_order)) != len(provider_order)):
            raise ValueError("worker_order contains an unknown or duplicate provider")
        if worker == "auto":
            worker = provider_order[0]
        fallback_worker = request.get("fallback_worker", request.get("fallback_provider"))
        if fallback_worker is not None:
            fallback_worker = str(fallback_worker).strip().lower()
            if fallback_worker not in _service_module().SUPPORTED_WORKER_PROVIDERS:
                raise ValueError(
                    "fallback_worker must be one of: " + ", ".join(_service_module().SUPPORTED_WORKER_PROVIDERS)
                )
            if fallback_worker == worker:
                raise ValueError("fallback_worker must differ from worker")
            if fallback_worker not in provider_order:
                provider_order.append(fallback_worker)
        what = str(request.get("what", "")).strip()
        why = str(request.get("why", "")).strip()
        if not what or not why:
            raise ValueError("what and why are required")
        task_id = str(request.get("task_id") or f"mcp-{_service_module().uuid4().hex[:12]}")
        decisions = request.get("architecture_decisions") or [
            {
                "decision_id": "target-boundary",
                "selected_option": "Target-only mutation",
                "rationale": "Preserve Controller immutability during worker execution",
                "rejected_alternatives": ["Controller mutation"],
            }
        ]
        decision_models = [
            item if isinstance(item, _service_module().ArchitectureDecision) else _service_module().ArchitectureDecision(**item)
            for item in decisions
        ]
        verifier_commands = [str(item) for item in request.get("verifier_commands", [])]
        protected_contracts = [str(item) for item in request.get("protected_contracts", [])]
        raw_expected_evidence = request.get("expected_evidence")
        expected_evidence = None
        if raw_expected_evidence is not None:
            # Projection point (§55-57): adopt the producer declaration
            # verbatim into the contract. Validation (incl. §21-22 coupling)
            # runs in the contract model; transport/service MUST NOT author it.
            from nexus.orchestrator.task_contract import ExpectedEvidenceUniverse

            if isinstance(raw_expected_evidence, Mapping):
                expected_evidence = ExpectedEvidenceUniverse.model_validate(raw_expected_evidence)
            else:
                expected_evidence = ExpectedEvidenceUniverse.model_validate(
                    raw_expected_evidence.model_dump(mode="json")
                    if hasattr(raw_expected_evidence, "model_dump")
                    else dict(raw_expected_evidence)
                )
        if (
            request.get("worker_candidate_ingress")
            and str(request.get("contract_kind") or "") == _service_module().ContractKind.OWNER_INLINE.value
        ):
            authority_confirmation = request.get("authority_change_candidate_confirmation", False)
            if not isinstance(authority_confirmation, bool):
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_INVALID")
            marker_present = "repository-authority-change.v1" in protected_contracts
            if marker_present != authority_confirmation:
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_MARKER_MISMATCH")
            inline = request.get("owner_inline_contract")
            if not isinstance(inline, Mapping) or inline.get("authority_change_candidate_confirmation", False) is not authority_confirmation:
                raise RuntimeError("AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH")
        authorized_deletions = [str(item) for item in request.get("authorized_deletions", [])]
        base_worktree_root, target_repo_root = _service_module().resolve_canonical_target_roots(
            task_id=task_id,
            campaign_id=request.get("campaign_id"),
            requested_target_worktree_root=request.get("target_worktree_root"),
            requested_target_repo_root=request.get("target_repo_root"),
        )
        controller_repo_root = request.get("controller_repo_root")
        if not controller_repo_root:
            controller_repo_root = str(Path.cwd().resolve())
        else:
            controller_repo_root = str(Path(controller_repo_root).expanduser().resolve())

        controller_revision = request.get("controller_revision")
        if not controller_revision:
            res = _service_module().subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_repo_root, capture_output=True, text=True)
            controller_revision = res.stdout.strip() if res.returncode == 0 else "HEAD"
        else:
            controller_revision = str(controller_revision)

        target_base_revision = request.get("target_base_revision")
        if not target_base_revision:
            target_base_revision = controller_revision
        else:
            target_base_revision = str(target_base_revision)

        raw_collaboration_realm = request.get("collaboration_realm")
        collaboration_realm: Optional[CollaborationExecutionRealm] = None
        if raw_collaboration_realm is not None:
            if not isinstance(raw_collaboration_realm, Mapping):
                raise ValueError("COLLABORATION_REALM_INVALID")
            try:
                collaboration_realm = _service_module().CollaborationExecutionRealm.model_validate(raw_collaboration_realm)
            except Exception as exc:
                raise ValueError("COLLABORATION_REALM_INVALID") from exc

        fail_to_pass_required = request.get("fail_to_pass_required", False)
        if not isinstance(fail_to_pass_required, bool):
            raise ValueError("FAIL_TO_PASS_REQUIRED_INVALID")
        required_evidence = ["candidate_state_hash", "controller_unchanged", "verified_candidate_receipt"]
        if fail_to_pass_required:
            # Bound into the contract hash through required_evidence (#2274).
            required_evidence.append(_service_module().FAIL_TO_PASS_EVIDENCE_TOKEN)

        return _service_module().ArchitectTaskContract(
            task_id=task_id,
            objective=what,
            goal=_service_module().DevelopmentGoal(what=what, why=why),
            architecture_decisions=decision_models,
            acceptance_profile=_service_module().AcceptanceProfile(
                verifier_commands=verifier_commands,
                protected_contracts=protected_contracts,
                authorized_deletions=authorized_deletions,
                required_evidence=required_evidence,
            ),
            human_approval_policy=_service_module().HumanApprovalPolicy(
                approver_roles=list(request.get("approver_roles", ["James"])),
            ),
            controller_revision=controller_revision,
            target_base_revision=target_base_revision,
            controller_repo_root=controller_repo_root,
            target_repo_root=str(target_repo_root),
            target_worktree_root=str(base_worktree_root),
            allowed_files=list(request["allowed_files"]),
            forbidden_files=list(request.get("forbidden_files", [])),
            authorized_deletions=authorized_deletions,
            verifier_commands=verifier_commands,
            protected_contracts=protected_contracts,
            preferred_provider=worker,
            fallback_provider=fallback_worker or (provider_order[1] if len(provider_order) > 1 else None),
            provider_order=provider_order,
            maximum_provider_calls=len(provider_order) if requested_worker == "auto" else (2 if fallback_worker else 1),
            maximum_replans=0,
            maximum_attempts_per_task=int(request.get("maximum_attempts_per_task", _service_module().DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK) or _service_module().DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK),
            maximum_wall_time_seconds=float(request.get("maximum_wall_time_seconds", 0) or 0),
            maximum_changed_files=int(request.get("maximum_changed_files", 0) or 0),
            maximum_deleted_files=int(request.get("maximum_deleted_files", 0) or 0),
            mutation_mode=_service_module().MutationMode.WORKING_TREE_ONLY,
            human_approval_required=True,
            collaboration_realm=collaboration_realm,
            expected_evidence=expected_evidence,
        )

    @staticmethod
    def _terminal_retry_revision_refresh_allowed(
        existing: Mapping[str, Any],
        request: Mapping[str, Any],
        contract: ArchitectTaskContract,
    ) -> bool:
        previous_raw_request = existing.get("request")
        action_bound_refresh = isinstance(previous_raw_request, Mapping) and (
            "action" in previous_raw_request or "bound_action_request" in previous_raw_request
        )
        if action_bound_refresh and not (
            _service_module()._terminal_retry_pre_provider_state_allowed(existing)
            or _service_module()._terminal_retry_verifier_static_failure_allowed(existing)
        ):
            return False
        previous_request = dict(previous_raw_request or {})
        if not isinstance(existing.get("request"), Mapping):
            return False
        if _service_module()._terminal_retry_semantic_payload(previous_request) != _service_module()._terminal_retry_semantic_payload(request):
            return False

        previous_contract = existing.get("contract") or {}
        previous_controller = str(previous_contract.get("controller_revision") or "")
        previous_target = str(previous_contract.get("target_base_revision") or "")
        revisions = (
            (previous_controller, contract.controller_revision),
            (previous_target, contract.target_base_revision),
        )
        if not all(old and new for old, new in revisions):
            return False
        if all(old == new for old, new in revisions):
            return False

        controller_root = Path(contract.controller_repo_root).expanduser().resolve()
        return all(
            _service_module().subprocess.run(
                ["git", "merge-base", "--is-ancestor", old, new],
                cwd=controller_root,
                capture_output=True,
                text=True,
            ).returncode == 0
            for old, new in revisions
        )

    def _contract_from_state(self, state: Mapping[str, Any]) -> ArchitectTaskContract:
        request = state.get("request")
        if isinstance(request, Mapping):
            return self.build_contract(request)
        contract = state.get("contract")
        if not isinstance(contract, Mapping):
            raise RuntimeError("task state is missing its contract")
        return _service_module().ArchitectTaskContract.model_validate(contract)

    @staticmethod
    def _prompt(contract: ArchitectTaskContract) -> str:
        allowed = ", ".join(contract.allowed_files)
        verifiers = "\n".join(f"- {command}" for command in contract.verifier_commands)
        return (
            f"WHAT: {contract.goal.what}\n"
            f"WHY: {contract.goal.why}\n"
            f"Allowed files: {allowed}\n"
            "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
            "outside the allowed scope. Run every verifier command below after making the change; if any "
            "verifier fails, diagnose and repair within the allowed files before returning.\n"
            f"Required verifier commands:\n{verifiers}\n"
            "Return a concise summary only after all required verifiers pass."
        )

    def _set_child_pgid(self, task_id: str, attempt_id: str, pgid: Optional[int]) -> None:
        def mutate(state: dict[str, Any]) -> None:
            if state.get("attempt_id") == attempt_id and state.get("status") not in _service_module().TERMINAL_STATUSES:
                state["worker_child_pgid"] = pgid
                state["updated_at"] = _service_module()._utc_now()

        self._mutate_state(task_id, mutate)

    def _lease_from_state(self, state: Mapping[str, Any]) -> TargetWorktreeLease:
        raw = state.get("lease")
        if not isinstance(raw, Mapping):
            raise RuntimeError("durable lease evidence is missing")
        return _service_module().TargetWorktreeLease(**dict(raw))

    def _capture_resumed_candidate(
        self,
        contract: ArchitectTaskContract,
        controller: SelfHostedDevelopmentController,
        lease: TargetWorktreeLease,
        state: Mapping[str, Any],
    ):
        candidate = controller.collect_candidate(contract, lease)
        stored = state.get("candidate") or {}
        if stored.get("candidate_state_hash") and stored["candidate_state_hash"] != candidate.candidate_state_hash:
            raise RuntimeError("candidate state changed during recovery")
        return candidate

    @staticmethod
    def _receipt_from_state(value: Any) -> Optional[WorkerExecutionReceipt]:
        if isinstance(value, _service_module().WorkerExecutionReceipt):
            return value
        if not isinstance(value, Mapping) or "outcome" not in value:
            return None
        try:
            payload = dict(value)
            payload["argv"] = tuple(payload.get("argv", ()))
            return _service_module().WorkerExecutionReceipt(**payload)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _escalation_policy(contract: ArchitectTaskContract) -> Optional[WorkerEscalationPolicy]:
        if not contract.preferred_provider or not contract.fallback_provider:
            return None
        return _service_module().WorkerEscalationPolicy(
            cheap_provider=contract.preferred_provider,
            strong_provider=contract.fallback_provider,
            provider_order=tuple(contract.provider_order or (contract.preferred_provider, contract.fallback_provider)),
        )
    # fmt: on
