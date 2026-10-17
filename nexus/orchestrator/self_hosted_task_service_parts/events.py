"""Attempt-event and continuity cluster of ``SelfHostedTaskService``.

Big-file split S3 (Issue #2552). ``_EventsMixin`` holds the attempt-transition event
emission and the continuity rehydration moved out of
``nexus/orchestrator/self_hosted_task_service.py``: ``_record_event_append_failure``,
``_emit_bound_attempt_transition``, ``_emit_attempt_transition``,
``read_canonical_attempt_events``, ``read_canonical_attempt_continuity``,
``rehydrate_task_continuation``, ``rehydrate_project_entry``,
``rehydrate_task_continuation_snapshot``, ``_request_hash``, ``_record_direct_failure``
and ``record_canonical_action_failure``. Their source lines are verbatim, except that
every facade-module name they load (``NexusEventBus``, ``build_attempt_transition_event``,
``events_from_attempt_records``, ``project``, ``build_rehydration_projection``,
``canonical_request_hash``, ``_utc_now``, ``_validated_action_request``,
``_validate_project_entry_authority_binding``,
``_reject_unbound_project_entry_authority_hints``, ``SelfHostedTaskService``) is resolved
at call time through ``_service_module()``, so patches on the facade keep taking effect.

Not all of it is read-only: ``_record_event_append_failure`` and ``_record_direct_failure``
write state through ``_mutate_state`` (under the state lock), and the emitters append to
the canonical EventBus log (binding it for production first when the service is not
ephemeral). The rehydration and ``read_canonical_*`` paths take no lock and write
nothing. The state lock and state store stay in the facade class and are reached
through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from pathlib import Path


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _EventsMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService
        ephemeral: bool

        @staticmethod
        def canonical_state_dir() -> Path: ...

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

        def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]: ...

        @classmethod
        def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]: ...

    # fmt: off
    def _record_event_append_failure(self, task_id: str, error: Exception) -> None:
        """Persist the state/event reconciliation debt without emitting another event."""
        now = _service_module()._utc_now()

        def mutate(state: dict[str, Any]) -> None:
            state["event_reconciliation_required"] = True
            state["event_append_failure"] = {
                "status": "BLOCKED",
                "error_type": type(error).__name__,
                "error_sha256": hashlib.sha256(str(error).encode("utf-8")).hexdigest(),
                "at": now,
            }
            state["updated_at"] = now

        self._mutate_state(task_id, mutate)

    def _emit_bound_attempt_transition(
        self, result: Optional[Mapping[str, Any]], task_id: str
    ) -> None:
        try:
            if not self.ephemeral:
                _service_module().NexusEventBus.ensure_configured(self.canonical_state_dir(), production=True)
            self._emit_attempt_transition(result, task_id)
        except Exception as exc:
            self._record_event_append_failure(task_id, exc)
            raise

    @staticmethod
    def _emit_attempt_transition(result: Optional[Mapping[str, Any]], task_id: str) -> None:
        if not result or not result.get("attempt_id"):
            return
        sequence = _service_module().NexusEventBus.next_attempt_sequence(
            str(result.get("task_id") or task_id), str(result.get("attempt_id"))
        )
        candidate_refs = tuple(str(value) for value in (
            result.get("candidate_commit_sha"),
            (result.get("promotion_packet") or {}).get("candidate_tree_sha"),
        ) if value)
        evidence_refs = tuple(str(value) for value in (
            result.get("verified_receipt_hash"),
            (result.get("verified_receipt") or {}).get("receipt_ref"),
        ) if value)
        # Persistence/sequence failures are deterministic event blocks.  They
        # must remain visible to the caller; silently dropping them creates a
        # false lifecycle receipt while leaving the lifecycle authority intact.
        request = result.get("request") if isinstance(result.get("request"), Mapping) else {}
        status = str(result.get("status"))
        rejected_states = frozenset({"ATTEMPT_REJECTED", "REJECTED"})
        explicit_type = result.get("continuity_event_type") or request.get("continuity_event_type")  # pyright: ignore[reportOptionalMemberAccess]
        if explicit_type is not None:
            if not isinstance(explicit_type, str) or not explicit_type.strip():
                raise ValueError("continuity_event_type must be a non-empty string")
            if status in rejected_states and explicit_type != "ATTEMPT_REJECTED":
                raise ValueError("rejected state requires ATTEMPT_REJECTED continuity type")
            continuity_event_type = explicit_type
        else:
            continuity_event_type = (
                "ATTEMPT_REJECTED" if status in rejected_states else "OBSERVATION_RECORDED"
            )

        def continuity_list(name: str, alias: str = "") -> tuple[str, ...]:
            value = result.get(name)
            if value is None and alias:
                value = result.get(alias)
            if value is None:
                value = request.get(name)  # pyright: ignore[reportOptionalMemberAccess]
            if value is None and alias:
                value = request.get(alias)  # pyright: ignore[reportOptionalMemberAccess]
            if value is None:
                return ()
            if isinstance(value, str):
                return (value,)
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{name} must be a list/tuple of non-empty strings")
            if any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"{name} must contain non-empty strings")
            return tuple(value)

        contract = result.get("contract") if isinstance(result.get("contract"), Mapping) else {}

        def identity_value(
            explicit: str,
            durable: str,
            structured: tuple[str, ...],
            request_fields: tuple[str, ...],
        ) -> str:
            for value in (
                result.get(explicit),
                result.get(durable),
                *(contract.get(field) for field in structured),  # pyright: ignore[reportOptionalMemberAccess]
                *(request.get(field) for field in request_fields),  # pyright: ignore[reportOptionalMemberAccess]
            ):
                if value is not None and str(value).strip():
                    return str(value)
            return "unknown"

        action = str(result.get("action") or request.get("action") or "")  # pyright: ignore[reportOptionalMemberAccess]
        observation = str(result.get("observation") or request.get("observation") or "")  # pyright: ignore[reportOptionalMemberAccess]
        _service_module().NexusEventBus.emit_attempt_transition(
            _service_module().build_attempt_transition_event(
                task_id=str(result.get("task_id") or task_id),
                attempt_id=str(result.get("attempt_id")),
                sequence=sequence,
                state=status,
                reason=str(result.get("error") or result.get("reason") or ""),
                action=action,
                observation=observation,
                continuity_event_type=continuity_event_type,
                strategy_delta=str(
                    result.get("strategy_delta") or request.get("strategy_delta") or ""  # pyright: ignore[reportOptionalMemberAccess]
                ),
                do_not_repeat=continuity_list("do_not_repeat", "rejected_strategies"),
                unresolved_risks=continuity_list("unresolved_risks"),
                unknowns=continuity_list("unknowns"),
                next_action=str(result.get("next_action") or request.get("next_action") or ""),  # pyright: ignore[reportOptionalMemberAccess]
                claim_ceiling=str(
                    result.get("claim_ceiling") or request.get("claim_ceiling") or ""  # pyright: ignore[reportOptionalMemberAccess]
                ),
                candidate_refs=candidate_refs,
                evidence_refs=evidence_refs,
                source_revision=identity_value(
                    "source_revision",
                    "controller_revision",
                    ("source_revision", "controller_revision", "current_source_revision"),
                    ("source_revision", "controller_revision"),
                ),
                contract_revision=identity_value(
                    "contract_revision",
                    "contract_hash",
                    (
                        "contract_revision",
                        "contract_hash",
                        "current_contract_revision",
                        "current_contract_hash",
                    ),
                    ("contract_revision", "contract_hash"),
                ),
            )
        )

    @staticmethod
    def read_canonical_attempt_events(
        task_id: str, attempt_id: str, *, project_root: Optional[Path] = None
    ) -> list[dict[str, Any]]:
        """Read attempt events from the canonical EventBus log, without mutation."""
        # Read the validated canonical store directly.  The EventBus observer
        # facade intentionally serves best-effort dashboards and swallows
        # integrity failures; continuity recovery must preserve those errors.
        if project_root is not None:
            _service_module().NexusEventBus.configure(project_root, create=False, production=True)
        if _service_module().NexusEventBus._log_store.event_log_path != _service_module().NexusEventBus._event_log_path:
            _service_module().NexusEventBus._log_store.event_log_path = _service_module().NexusEventBus._event_log_path
        records = _service_module().NexusEventBus._log_store.read_recent(event_type="attempt_transition", limit=10_000)
        selected = []
        for record in records:
            payload = record.get("payload") if isinstance(record, Mapping) else None
            if not isinstance(payload, Mapping):
                raise ValueError("attempt transition payload is missing")
            if payload.get("task_id") == task_id and payload.get("attempt_id") == attempt_id:
                selected.append(dict(record))
        if not selected:
            raise ValueError("attempt continuity stream is empty")
        return selected

    @staticmethod
    def read_canonical_attempt_continuity(task_id: str, attempt_id: str) -> list[Any]:
        """Consume the canonical JSONL attempt log as validated continuity events."""
        return _service_module().events_from_attempt_records(
            _service_module().SelfHostedTaskService.read_canonical_attempt_events(task_id, attempt_id),
            task_id=task_id,
            attempt_id=attempt_id,
        )

    def rehydrate_task_continuation(
        self,
        task_id: str,
        attempt_id: Optional[str] = None,
        *,
        _project_entry: bool = False,
        _state: Mapping[str, Any] | None = None,
        _project_entry_repository: str | None = None,
        _project_entry_issue: int | None = None,
    ) -> dict[str, Any]:
        """Deterministic, model-independent, read-only rehydration projection.

        Rebuilds task continuation projection purely from physical durable state
        and canonical attempt continuity records. Never mutates task state.
        """
        state = _state if _state is not None else self._read_state_snapshot(task_id)
        if state is None:
            raise KeyError(f"unknown task: {task_id}")
        if not isinstance(state, Mapping):
            raise ValueError("REHYDRATION_MALFORMED_STATE: task state must be a mapping")
        persisted_request = state.get("request")
        if state.get("state_valid") is False or str(state.get("status") or "").startswith("BLOCKED_INVALID_"):
            blocker = state.get("blocker") if isinstance(state.get("blocker"), Mapping) else {}
            detail = blocker.get("detail") or "state is invalid"  # pyright: ignore[reportOptionalMemberAccess]
            raise ValueError(f"REHYDRATION_MALFORMED_STATE: {detail}")
        for key in ("candidate", "promotion_packet", "verified_receipt", "contract"):
            val = state.get(key)
            if val is not None and not isinstance(val, Mapping):
                raise ValueError(f"REHYDRATION_MALFORMED_STATE: {key} must be a mapping")
        work_claim = state.get("work_claim")
        if work_claim is not None:
            if not isinstance(work_claim, Mapping):
                raise ValueError("REHYDRATION_WORK_CLAIM_MISMATCH: work_claim must be a mapping")
            if not isinstance(work_claim.get("identity"), Mapping):
                raise ValueError("REHYDRATION_WORK_CLAIM_MISMATCH: work_claim identity must be a mapping")

        target_attempt_id = attempt_id or state.get("attempt_id")
        if not target_attempt_id:
            raise ValueError("REHYDRATION_ATTEMPT_ID_REQUIRED")
        if not self.ephemeral:
            events = _service_module().events_from_attempt_records(
                self.read_canonical_attempt_events(
                    task_id, str(target_attempt_id), project_root=self.canonical_state_dir()
                ),
                task_id=task_id,
                attempt_id=str(target_attempt_id),
            )
        else:
            events = self.read_canonical_attempt_continuity(task_id, str(target_attempt_id))
        snapshot = _service_module().project(events)
        task_action = self._task_action_envelope(state)
        projection = _service_module().build_rehydration_projection(
            task_state=state,
            continuity_snapshot=snapshot,
            task_action_envelope=task_action,
            requested_attempt_id=attempt_id,
        )
        result = projection.to_dict()
        if not _project_entry:
            return result
        try:
            if not isinstance(persisted_request, Mapping):
                _service_module()._reject_unbound_project_entry_authority_hints(state)
                return {"continuation": result, "authority_binding": None}
            _service_module()._reject_unbound_project_entry_authority_hints(persisted_request)
            persisted_hash = str(state.get("action_request_hash") or "")
            binding = _service_module()._validate_project_entry_authority_binding(
                persisted_request,
                repository=_project_entry_repository or str(persisted_request.get("repository") or ""),
                issue_number=_project_entry_issue or int(persisted_request.get("issue") or persisted_request.get("issue_number") or 0),
            )
            if binding is not None and not persisted_hash:
                raise ValueError("PROJECT_ENTRY_REQUEST_HASH_MISSING")
            if persisted_hash:
                if "action" in persisted_request or "bound_action_request" in persisted_request:
                    effective_request, envelope = _service_module()._validated_action_request(persisted_request)
                    if not isinstance(envelope, Mapping) or persisted_hash != str(envelope.get("request_hash") or ""):
                        raise ValueError("PROJECT_ENTRY_REQUEST_HASH_MISMATCH")
                    effective_binding = _service_module()._validate_project_entry_authority_binding(effective_request)
                    if effective_binding != binding:
                        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH")
                    binding = effective_binding
                else:
                    hash_input = dict(persisted_request)
                    hash_input.pop("action_request_hash", None)
                    if persisted_hash != _service_module().canonical_request_hash(hash_input):
                        raise ValueError("PROJECT_ENTRY_REQUEST_HASH_MISMATCH")
            if binding is not None:
                for field in ("authority_goal_id", "autonomy_goal_id"):
                    if state.get(field) is not None and state[field] != binding["goal_id"]:
                        raise ValueError("PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH")
                if state.get("authority_coordination_scope_id") is not None and state["authority_coordination_scope_id"] != binding["coordination_scope_id"]:
                    raise ValueError("PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH")
                raw_submission = state.get("autonomy_submission_binding")
                if isinstance(raw_submission, Mapping) and raw_submission.get("goal_id") is not None and raw_submission["goal_id"] != binding["goal_id"]:
                    raise ValueError("PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH")
            else:
                _service_module()._reject_unbound_project_entry_authority_hints(state)
            return {"continuation": result, "authority_binding": binding}
        except (TypeError, ValueError) as exc:
            raise ValueError(f"PROJECT_ENTRY_AUTHORITY_BINDING_INVALID: {exc}") from exc

    def rehydrate_project_entry(self, task_id: str, attempt_id: Optional[str], *, repository: str, issue_number: int) -> dict[str, Any]:
        state = self._read_state_snapshot(task_id)
        if not isinstance(state, Mapping):
            raise KeyError(f"unknown task: {task_id}")
        request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        request_present = bool(request.get("repository") or request.get("issue") or request.get("issue_number"))  # pyright: ignore[reportOptionalMemberAccess]
        if ((request_present and (request.get("repository") != repository or  # pyright: ignore[reportOptionalMemberAccess]
                ("issue" in request and str(request.get("issue")) != str(issue_number)) or  # pyright: ignore[reportOperatorIssue, reportOptionalMemberAccess]
                ("issue_number" in request and str(request.get("issue_number")) != str(issue_number)))) or  # pyright: ignore[reportOperatorIssue, reportOptionalMemberAccess]
                (state.get("repository") and state.get("repository") != repository) or
                (state.get("issue") and str(state.get("issue")) != str(issue_number))):
            raise ValueError("PROJECT_ENTRY_AUTHORITY_SELECTOR_MISMATCH")
        # The helper performs the continuity read and authority validation from
        # one state snapshot; this entry point exists for the gateway contract.
        return self.rehydrate_task_continuation(task_id, attempt_id, _project_entry=True, _state=state, _project_entry_repository=repository, _project_entry_issue=issue_number)

    @classmethod
    def rehydrate_task_continuation_snapshot(
        cls,
        task_state: Mapping[str, Any],
        attempt_continuity_events: Iterable[Any],
        *,
        attempt_id: Optional[str] = None,
    ) -> dict[str, Any]:
        snapshot = _service_module().project(attempt_continuity_events)
        task_action = cls._task_action_envelope(task_state)
        return _service_module().build_rehydration_projection(
            task_state=task_state,
            continuity_snapshot=snapshot,
            task_action_envelope=task_action,
            requested_attempt_id=attempt_id,
        ).to_dict()

    @staticmethod
    def _request_hash(request: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _record_direct_failure(self, task_id: str, blocker: str, error: str = "") -> Optional[dict[str, Any]]:
        """Persist an uncertain Direct/Assisted outcome without allocating a Target."""
        now = _service_module()._utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if state.get("status") == "DIRECT_COMPLETED":
                return
            action = dict(state.get("canonical_action") or {})
            reconciliation = dict(action.get("reconciliation") or {})
            reconciliation.update({
                "status": "REQUIRED",
                "blocker": blocker,
                "error": error,
                "at": now,
            })
            action["reconciliation"] = reconciliation
            state["canonical_action"] = action
            state["status"] = "DIRECT_RECONCILE_REQUIRED"
            state["error"] = error or blocker
            state["reconciliation_required"] = True
            state["updated_at"] = now
            state.setdefault("status_history", []).append({"status": state["status"], "at": now})

        result = self._mutate_state(task_id, mutate)
        self._emit_bound_attempt_transition(result, task_id)
        return result

    def record_canonical_action_failure(self, task_id: str, blocker: str, error: str = "") -> Optional[dict[str, Any]]:
        """Public observer-safe hook for an Assisted provider/apply failure."""
        return self._record_direct_failure(task_id, blocker, error)
    # fmt: on
