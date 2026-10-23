"""Checkpoint and terminal-Core-record members of ``SelfHostedTaskService``.

Big-file split S8a (Issue #2579). ``_CheckpointMixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``_checkpoint``: every lifecycle status write of a task (status history, telemetry,
  attempt rows, lease / execution / promotion projections, the runtime-development
  mapping) under the state lock, then the attempt transition event, then, for a terminal
  status, the terminal Core record;
* ``TERMINAL_CORE_RECORD_SCHEMA``, ``_TERMINAL_CORE_EXPECTED_HOST_REASONS``,
  ``_build_terminal_core_record`` and ``_record_terminal_core_not_covered``: Core's
  NOT_COVERED record for a declared-universe task that ended without a receipt (#2346);
* ``_touch_owned_state``: the ownership check and timestamp write of one worker
  heartbeat. The heartbeat loop itself lives in nexus-runtime
  (``execution_coordination/coordinator.py``), which reaches this through
  ``runtime_coordination_bridge._State.heartbeat``. The unused in-repo loop
  ``_heartbeat`` was removed in #2584 Phase-2 batch A.

Their source lines are verbatim, except that the facade-module names they load
(``TERMINAL_STATUSES``, ``_jsonable``, ``_parse_time``, ``_utc_now``, ``time``,
``build_runtime_development_mapping``, ``build_core_verdict`` and ``__name__`` for the
logger) are resolved at call time through ``_service_module()``, so patches on the facade
keep taking effect and the warning keeps the facade logger name.

This is not read-only code: it writes the task state through ``_mutate_state`` (state
lock, then the runtime store's atomic replace) and appends attempt transition events
through ``_emit_bound_attempt_transition``; both, and the other members it uses, are
reached through ``self``.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

if TYPE_CHECKING:
    from nexus.orchestrator.ambient_core import AmbientCoreControlPort
    from nexus.orchestrator.task_contract import ArchitectTaskContract


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _CheckpointMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService and its other bases
        ambient_core_port: Optional[AmbientCoreControlPort]

        def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract: ...

        @staticmethod
        def _card_evidence_binding_error(
            contract: Any, request: Mapping[str, Any]
        ) -> Optional[str]: ...

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

        def _emit_bound_attempt_transition(
            self, result: Optional[Mapping[str, Any]], task_id: str
        ) -> None: ...

    # fmt: off
    def _checkpoint(
        self,
        task_id: str,
        status: str,
        values: Optional[Mapping[str, Any]] = None,
        *,
        attempt_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        now = _service_module()._utc_now()

        def mutate(state: dict[str, Any]) -> None:
            if attempt_id is not None and state.get("attempt_id") != attempt_id:
                raise RuntimeError("task attempt ownership changed")
            previous = state.get("status")
            state["status"] = status
            if values:
                updates = _service_module()._jsonable(dict(values))
                updates.pop("submitted_at", None)
                state.update(updates)
            state["updated_at"] = now
            state["heartbeat_at"] = now
            history = list(state.get("status_history", []))
            if previous != status:
                history.append({"status": status, "at": now})
            state["status_history"] = history
            submitted_at = _service_module()._parse_time(state.get("submitted_at"))
            started_at = _service_module()._parse_time(state.get("worker_started_at"))
            if submitted_at is not None:
                wall_time_ms = max(0, int((_service_module().time.time() - submitted_at) * 1000))
                worker_wall_time_ms = max(0, int((_service_module().time.time() - started_at) * 1000)) if started_at is not None else 0
                previous_telemetry = state.get("telemetry") or {}
                executions = state.get("executions") or ([state.get("execution")] if state.get("execution") else [])
                provider_time_ms = sum(int(item.get("wall_time_ms") or 0) for item in executions if isinstance(item, Mapping))
                provider_calls = sum(int(item.get("provider_calls") or 0) for item in executions if isinstance(item, Mapping))
                provider_attempts = sum(
                    int(item.get("provider_attempt_count"))  # pyright: ignore[reportArgumentType]
                    if item.get("provider_attempt_count") is not None
                    else 1
                    for item in executions
                    if isinstance(item, Mapping)
                )
                verified = state.get("verified_receipt") or {}
                verifier_time_ms = sum(int(item.get("wall_time_ms") or 0) for item in verified.get("verifier_evidence") or [] if isinstance(item, Mapping))
                worktree_time_ms = int(previous_telemetry.get("worktree_time_ms") or 0)
                commit_hook_time_ms = int(previous_telemetry.get("commit_hook_time_ms") or 0)
                cleanup_time_ms = int(previous_telemetry.get("cleanup_time_ms") or 0)
                measured_ms = provider_time_ms + verifier_time_ms + worktree_time_ms + commit_hook_time_ms + cleanup_time_ms
                state["telemetry"] = {
                    "wall_time_ms": wall_time_ms,
                    "worker_wall_time_ms": worker_wall_time_ms,
                    "provider_time_ms": provider_time_ms,
                    "provider_calls": provider_calls,
                    "provider_attempts": provider_attempts,
                    "tokens": None,
                    "cost": None,
                    "token_status": "unmeasured",
                    "cost_status": "unmeasured",
                    "savings_claim_allowed": False,
                    "verifier_time_ms": verifier_time_ms,
                    "worktree_time_ms": worktree_time_ms,
                    "commit_hook_time_ms": commit_hook_time_ms,
                    "cleanup_time_ms": cleanup_time_ms,
                    "overhead_ms": max(0, wall_time_ms - measured_ms),
                }
            if status in _service_module().TERMINAL_STATUSES:
                state["worker_finished_at"] = now
                state["worker_child_pgid"] = None
            for attempt in state.get("attempts") or []:
                if attempt.get("attempt_id") == state.get("attempt_id"):
                    attempt["last_status"] = status
                    attempt["updated_at"] = now
                    if status in _service_module().TERMINAL_STATUSES or status == "PENDING_HUMAN_APPROVAL":
                        attempt["finished_at"] = now
            lease = state.get("lease") or {}
            if lease:
                state.update({
                    "controller_worktree": (state.get("contract") or {}).get("controller_repo_root"),
                    "controller_status_sha256": lease.get("controller_status_sha256"),
                    "target_worktree": lease.get("target_worktree"),
                    "target_initial_revision": lease.get("initial_head"),
                    "target_branch": lease.get("target_branch"),
                    "target_created_at": state.get("target_created_at") or now,
                })
            execution = state.get("execution") or {}
            if execution:
                state["execution_outcome"] = execution.get("outcome")
            resolution = state.get("attempt_resolution") or {}
            if resolution:
                state["verification_verdict"] = resolution.get("verdict")
            packet = state.get("promotion_packet") or {}
            if packet:
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                ):
                    state[field] = packet.get(field)
            action_id = str(state.get("action_id") or f"action-{state.get('attempt_id') or task_id}")
            promotion_status = str(state.get("promotion_status") or "NOT_CREATED")
            integrated = state.get("status") == "INTEGRATED" or promotion_status == "INTEGRATED"
            runtime_phase = str(state.get("runtime_phase") or "").strip().upper()
            runtime_terminal_state = str(state.get("runtime_terminal_state") or "").strip().upper()
            state["runtime_development_mapping"] = _service_module().build_runtime_development_mapping(
                task_id=str(state.get("task_id") or task_id),
                attempt_id=str(state.get("attempt_id") or attempt_id or "attempt-unknown"),
                action_id=action_id,
                runtime_phase=runtime_phase,
                runtime_terminal_state=runtime_terminal_state,
                development_status=str(state.get("status") or "UNKNOWN"),
                runtime_success=(
                    runtime_phase == "C" and runtime_terminal_state == "COMPLETE"
                ),
                candidate_status=str(state.get("candidate_status") or promotion_status),
                candidate_accepted=promotion_status in {"APPROVED", "INTEGRATED"},
                integration_status=promotion_status,
                integrated=integrated,
                runtime_receipt_ref=str(state.get("runtime_receipt_ref") or ""),
                development_receipt_ref=str(state.get("verified_receipt_hash") or ""),
            )

        result = self._mutate_state(task_id, mutate)
        self._emit_bound_attempt_transition(result, task_id)
        if status in _service_module().TERMINAL_STATUSES:
            self._record_terminal_core_not_covered(task_id, result)
        return result

    TERMINAL_CORE_RECORD_SCHEMA = "nexus.self_hosted_terminal_core_record.v1"
    _TERMINAL_CORE_EXPECTED_HOST_REASONS = frozenset({
        "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE",
        "CORE_COVERAGE_INCOMPLETE",
    })

    def _build_terminal_core_record(
        self, state: Mapping[str, Any], *, contract: Any = None
    ) -> Optional[dict[str, Any]]:
        """Core's NOT_COVERED record for a declared-universe task with no receipt (#2346).

        Returns None (nothing to record) for a legacy task, a non-terminal
        state, a captured Candidate, or any state that already carries a
        verified receipt: those paths are unchanged. ``terminal_status`` is the
        status at which the attempt ended without a receipt; a later lifecycle
        move of the same attempt (e.g. SUPERSEDED) is the state's own status. Otherwise the record always fails closed: it
        carries no commit permission, and a Core failure is recorded as the
        failure reason, never as coverage.
        """
        status = str(state.get("status") or "")
        if status not in _service_module().TERMINAL_STATUSES or state.get("verified_receipt") is not None:
            return None
        if any(
            state.get(field) not in (None, "", {})
            for field in (
                "candidate",
                "candidate_state_hash",
                "candidate_commit_sha",
                "candidate_ref",
                "promotion_packet",
            )
        ):
            # A captured Candidate is not "candidate missing"; its own
            # verification path owns that Core record.
            return None
        request = state.get("request")
        if not isinstance(request, Mapping):
            return None
        claims_universe = (
            request.get("expected_evidence") is not None
            or request.get("core_envelope_required") is True
        )
        if contract is None and not claims_universe:
            # Legacy (no-universe) task: nothing is built, called or written.
            return None
        attempt_id = str(state.get("attempt_id") or "")
        task_id = str(state.get("task_id") or request.get("task_id") or "")
        build_error: Optional[str] = None
        if contract is None:
            try:
                contract = self.build_contract(request)
            except Exception as exc:
                build_error = f"CORE_TERMINAL_CONTRACT_UNAVAILABLE:{type(exc).__name__}"
        if (
            build_error is None
            and getattr(contract, "expected_evidence", None) is None
            and not claims_universe
        ):
            return None
        record: dict[str, Any] = {
            "schema": self.TERMINAL_CORE_RECORD_SCHEMA,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "terminal_status": status,
            "record_status": "FAILED",
            "failure_reason": build_error,
            "verified": False,
            "candidate_commit_allowed": False,
            "core_verdict": None,
        }
        if build_error is not None:
            return record
        try:
            card_error = self._card_evidence_binding_error(contract, request)
            if card_error is not None:
                raise RuntimeError(card_error)
            port = self.ambient_core_port
            if port is None:
                raise RuntimeError("AMBIENT_CORE_CONTROL_PORT_REQUIRED")
            recorder: Any = getattr(port, "record_terminal_not_covered", None)
            if not callable(recorder):
                raise RuntimeError("AMBIENT_CORE_TERMINAL_RECORD_UNSUPPORTED")
            projection: Any = recorder(
                contract=contract,
                request=request,
                task_id=task_id,
                attempt_id=attempt_id,
                terminal_status=status,
            )
            verdict = _service_module().build_core_verdict(contract=contract, projection=projection)
            if not verdict.get("blocking"):
                # A task that produced nothing can never read as covered.
                raise RuntimeError("CORE_TERMINAL_RECORD_NOT_BLOCKING")
            # RECORDED means exactly Core's NOT_COVERED answer for this
            # universe from the pinned Core; any other host finding (an
            # unpinned Core, an identity or universe mismatch) is a failure.
            host_reasons = list(verdict.get("host_reason_codes") or ())
            unexpected = [
                code
                for code in host_reasons
                if code not in self._TERMINAL_CORE_EXPECTED_HOST_REASONS
            ]
            if unexpected:
                record.update(core_verdict=verdict)
                raise RuntimeError(str(unexpected[0]))
            if (
                verdict.get("core_status") != "UNVERIFIABLE"
                or verdict.get("integrity") != "MISSING"
                or "MISSING" not in (verdict.get("reason_codes") or ())
                or "AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE" not in host_reasons
            ):
                record.update(core_verdict=verdict)
                raise RuntimeError("CORE_TERMINAL_RECORD_NOT_MISSING")
            if isinstance(projection, Mapping) and projection.get("terminal_status"):
                record["terminal_status"] = str(projection["terminal_status"])
            record.update(record_status="RECORDED", core_verdict=verdict)
        except Exception as exc:
            code = str(exc).split(":", 1)[0].strip() or type(exc).__name__
            reason = f"CORE_TERMINAL_RECORD_FAILED:{code}"
            record["failure_reason"] = reason
            if record.get("core_verdict") is None:
                try:
                    record["core_verdict"] = _service_module().build_core_verdict(
                        contract=contract, projection=None, transport_error=reason
                    )
                except Exception:
                    record["core_verdict"] = None
        return record

    def _record_terminal_core_not_covered(self, task_id: str, state: Any) -> None:
        """Persist the #2346 record; never changes the terminal state it describes."""
        try:
            if not isinstance(state, Mapping):
                return
            attempt_id = str(state.get("attempt_id") or "")
            existing = state.get("terminal_core_record")
            if (
                isinstance(existing, Mapping)
                and existing.get("attempt_id") == attempt_id
                and existing.get("record_status") == "RECORDED"
            ):
                # Recorded once per attempt; a FAILED record is tried again
                # at the next terminal write (e.g. after Core is fixed).
                return
            record = self._build_terminal_core_record(state)
            if record is None:
                return
            status = state.get("status")

            def attach(current: dict[str, Any]) -> None:
                # Only onto the same attempt, still terminal and receipt-free.
                current_record = current.get("terminal_core_record")
                already_recorded = (
                    isinstance(current_record, Mapping)
                    and current_record.get("attempt_id") == attempt_id
                    and current_record.get("record_status") == "RECORDED"
                )
                if (
                    current.get("attempt_id") == attempt_id
                    and current.get("status") == status
                    and current.get("verified_receipt") is None
                    and not already_recorded
                ):
                    current["terminal_core_record"] = _service_module()._jsonable(record)

            self._mutate_state(task_id, attach)
        except Exception as exc:
            # Recording is evidence only; the terminal state stands as written.
            logging.getLogger(_service_module().__name__).warning(
                "terminal Core record for %s not persisted: %s", task_id, type(exc).__name__
            )
            return

    @staticmethod
    def _touch_owned_state(state: dict[str, Any], attempt_id: str) -> None:
        if state.get("attempt_id") != attempt_id or state.get("status") in _service_module().TERMINAL_STATUSES:
            raise RuntimeError("task is no longer owned by this attempt")
        now = _service_module()._utc_now()
        state["heartbeat_at"] = now
        state["updated_at"] = now
    # fmt: on
