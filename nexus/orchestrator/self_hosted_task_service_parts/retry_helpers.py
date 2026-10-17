"""Module-level retry helpers of SHTS.

Big-file split S5 (Issue #2566). The module-level helpers moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* retry transport identity: ``_retry_request`` (fresh attempt-scoped identity minted by
  the runtime's ``mint_retry_identity``), ``_retry_semantic_payload`` and
  ``_terminal_retry_semantic_payload``;
* terminal-retry state proofs: ``_terminal_retry_inherited_worktree_time_allowed``,
  ``_terminal_retry_pre_provider_state_allowed``, ``_terminal_retry_released_lease_proof``
  and ``_terminal_retry_verifier_static_failure_allowed``;
* ``_validate_retry_predecessor``.

The facade re-exports each of them (``from ... import X as X``), so
``self_hosted_task_service.X is retry_helpers.X``. Their source lines are verbatim,
except that every facade-module name they load (``mint_retry_identity``, ``uuid4``,
``LifecycleActionEnvelope``, ``LifecycleActionType``, ``canonical_request_hash``,
``WorktreeManager``, ``RETRYABLE_TASK_STATUSES``, ``_validated_action_request`` and
``validate_workforce_dispatch_binding`` (from ``dispatch_binding``), and the moved
helpers ``_retry_semantic_payload``, ``_terminal_retry_semantic_payload``,
``_terminal_retry_inherited_worktree_time_allowed`` and
``_terminal_retry_released_lease_proof`` when one helper calls another) is resolved at
call time through ``_service_module()``, so patches on the facade keep taking effect.
The stdlib names they use (``json``, ``os``, ``datetime``, ``Path``) are imported here and
are the same objects the facade binds.

None of them takes a lock or writes state. The terminal-retry proofs only read: the
filesystem (``is_dir`` / ``lexists`` / the ownership tombstones) and git, through the
worktree manager they already used before the move (``rev-parse`` / ``merge-base`` /
``released_lease_proof``).
"""

from __future__ import annotations

import importlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a helper runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


# fmt: off
def _retry_request(state: Mapping[str, Any]) -> dict[str, Any]:
    """Create fresh attempt-scoped transport identity for one semantic task."""
    raw_request = state.get("request")
    if not isinstance(raw_request, Mapping):
        raise ValueError("RETRY_REQUEST_MISSING")
    request = json.loads(json.dumps(dict(raw_request)))
    identity = _service_module().mint_retry_identity(state, request, token=_service_module().uuid4().hex)
    task_id = identity.task_id
    attempt_id = identity.attempt_id
    action_id = identity.action_id
    idempotency_key = identity.idempotency_key

    raw_action = request.get("action")
    if isinstance(raw_action, Mapping):
        raw_bound = request.get("bound_action_request")
        if not isinstance(raw_bound, Mapping):
            raise ValueError("RETRY_BOUND_ACTION_REQUEST_MISSING")
        envelope = _service_module().LifecycleActionEnvelope.model_validate(raw_action)
        bound = json.loads(json.dumps(dict(raw_bound)))
        bound.update(
            task_id=task_id,
            attempt_id=attempt_id,
            action_id=action_id,
            idempotency_key=idempotency_key,
            action_type=_service_module().LifecycleActionType.TASK_RETRY.value,
        )
        action_payload = envelope.model_dump(mode="json")
        action_payload.update(
            task_id=task_id,
            attempt_id=attempt_id,
            action_id=action_id,
            idempotency_key=idempotency_key,
            action_type=_service_module().LifecycleActionType.TASK_RETRY.value,
            request_hash=_service_module().canonical_request_hash(bound),
        )
        retry_action = _service_module().LifecycleActionEnvelope.model_validate(action_payload).model_dump(mode="json")
        return {
            **bound,
            "action": retry_action,
            "bound_action_request": bound,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "action_id": action_id,
            "idempotency_key": idempotency_key,
            "action_request_hash": retry_action["request_hash"],
        }

    request.update(
        task_id=task_id,
        attempt_id=attempt_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
    )
    request.pop("action_request_hash", None)
    request["action_request_hash"] = _service_module().canonical_request_hash(request)
    return request


def _retry_semantic_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only attempt-scoped transport identity from a durable request."""
    raw_bound = request.get("bound_action_request")
    source = raw_bound if isinstance(raw_bound, Mapping) else request
    payload = json.loads(json.dumps(dict(source)))
    for field in (
        "attempt_id",
        "action_id",
        "idempotency_key",
        "action_request_hash",
        "action_type",
    ):
        payload.pop(field, None)
    return payload


def _terminal_retry_semantic_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return the validated task semantics shared by a terminal fast-forward.

    Action-bound retries legitimately receive fresh transport identity and a
    fresh expected head.  Validate the complete envelope first, then remove
    only those transport and revision fields; planner, worker, card, paths,
    and authority fields remain part of the comparison.
    """
    effective, _ = _service_module()._validated_action_request(request)
    if "workforce_demands" in effective or "workforce_admission" in effective:
        _service_module().validate_workforce_dispatch_binding(effective, require_binding=True)
    payload = _service_module()._retry_semantic_payload(effective)
    payload.pop("controller_revision", None)
    payload.pop("target_base_revision", None)
    dispatch_envelope = payload.get("canonical_dispatch_envelope")
    if isinstance(dispatch_envelope, Mapping):
        # The envelope is validated as part of the bound request.  Its
        # attempt_id is the sole transport-derived field that changes on a
        # legitimate retry; preserve every Planner/admission field.
        dispatch_envelope = dict(dispatch_envelope)
        dispatch_envelope.pop("attempt_id", None)
        payload["canonical_dispatch_envelope"] = dispatch_envelope
    return payload


def _terminal_retry_inherited_worktree_time_allowed(state: Mapping[str, Any]) -> bool:
    """Accept only worktree time inherited from a completed prior attempt."""
    telemetry = state.get("telemetry")
    if not isinstance(telemetry, Mapping) or type(telemetry.get("worktree_time_ms")) is not int:
        return False
    if telemetry["worktree_time_ms"] == 0:
        return True
    if telemetry["worktree_time_ms"] < 0:
        return False
    if state.get("error") != "existing task branch candidate lacks durable protection":
        return False

    attempts = state.get("attempts")
    history = state.get("status_history")
    current_id = str(state.get("attempt_id") or "")
    if (
        not current_id
        or not isinstance(attempts, list)
        or len(attempts) < 2
        or not isinstance(history, list)
        or not all(isinstance(item, Mapping) for item in history)
    ):
        return False
    current = attempts[-1]
    previous = attempts[-2]
    if (
        not isinstance(current, Mapping)
        or not isinstance(previous, Mapping)
        or str(current.get("attempt_id") or "") != current_id
        or str(previous.get("attempt_id") or "") == current_id
        or current.get("last_status") != "FINAL_BLOCK"
        or not current.get("started_at")
        or not current.get("finished_at")
        or not previous.get("started_at")
        or not previous.get("finished_at")
    ):
        return False
    try:
        history_times = [datetime.fromisoformat(str(item["at"])) for item in history]
        current_started = datetime.fromisoformat(str(current["started_at"]))
        current_finished = datetime.fromisoformat(str(current["finished_at"]))
        previous_finished = datetime.fromisoformat(str(previous["finished_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    try:
        if any(later < earlier for earlier, later in zip(history_times, history_times[1:])):
            return False
        current_start_indexes = [
            index for index, item in enumerate(history)
            if item.get("status") == "ATTEMPT_INCREMENTED"
            and str(item.get("at")) == str(current["started_at"])
        ]
    except TypeError:
        return False
    if len(current_start_indexes) != 1:
        return False
    current_start_index = current_start_indexes[0]
    try:
        current_segment = history[current_start_index:]
        if [item.get("status") for item in current_segment] != ["ATTEMPT_INCREMENTED", "FINAL_BLOCK"]:
            return False
        prior_segment = history[:current_start_index]
        previous_window = [
            item for item in prior_segment
            if datetime.fromisoformat(str(item["at"])) >= datetime.fromisoformat(str(previous["started_at"]))
            and datetime.fromisoformat(str(item["at"])) <= previous_finished
        ]
        if [item.get("status") for item in previous_window] != [
            "SUBMITTED", "TARGET_LEASED", "WORKER_RUNNING", "FINAL_BLOCK",
        ]:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    try:
        current_finished_at = history[current_start_index + 1].get("at")
        if (
            current_finished_at != current["finished_at"]
            or current_finished < current_started
            or previous_finished > current_started
        ):
            return False
    except (IndexError, TypeError):
        return False

    contract = state.get("contract")
    target_worktree = str(state.get("target_worktree") or "").strip()
    if not isinstance(contract, Mapping) or not target_worktree:
        return False
    controller_root = Path(str(contract.get("controller_repo_root") or "")).expanduser()
    target_root = Path(str(contract.get("target_worktree_root") or "")).expanduser()
    target_path = Path(target_worktree).expanduser()
    if (
        not controller_root.is_dir()
        or not target_root.is_dir()
        or os.path.lexists(target_path)
        or target_path.resolve() == target_root.resolve()
        or target_root.resolve() not in target_path.resolve().parents
        or str(contract.get("target_repo_root") or "") != target_worktree
    ):
        return False
    if (
        state.get("lease") is not None
        or state.get("executions") not in (None, [])
        or any(
            state.get(field) is not None
            for field in (
                "execution", "execution_outcome", "candidate", "candidate_commit_sha",
                "candidate_ref", "candidate_state_hash", "verified_receipt",
                "verified_receipt_hash", "provider_receipt", "worker_receipt",
            )
        )
        or state.get("promotion_packet") not in (None, {})
    ):
        return False
    try:
        manager = _service_module().WorktreeManager(
            root_dir=target_root,
            create_root=False,
        )
        ownership_path = manager._ownership_record_path(controller_root, str(state.get("task_id") or ""))
        if os.path.lexists(ownership_path) or manager._worktree_entry(controller_root, target_path):
            return False
        if manager._active_target_worktrees(controller_root, target_path):
            return False
        branch_ref = f"refs/heads/nexus/task/{state.get('task_id')}"
        target_base = str(contract.get("target_base_revision") or "")
        if not target_base:
            return False
        branch_head = manager._run_git(["rev-parse", "--verify", branch_ref], cwd=controller_root)
        if not branch_head:
            return False
        try:
            manager._run_git(
                ["merge-base", "--is-ancestor", branch_head, target_base],
                cwd=controller_root,
            )
        except RuntimeError:
            return False
    except (OSError, RuntimeError, ValueError, TypeError):
        return False
    return True


def _terminal_retry_pre_provider_state_allowed(state: Mapping[str, Any]) -> bool:
    """Permit revision refresh only for a known, effect-free terminal state."""
    if state.get("status") != "FINAL_BLOCK":
        return False
    if str(state.get("cleanup_decision") or "") not in {
        "REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED",
    }:
        return False
    if state.get("target_created_at") is not None:
        return False
    if state.get("active_provider") not in (None, ""):
        return False
    if state.get("worker_preflight") is not None or state.get("worker_child_pgid") is not None:
        return False
    if state.get("worker_started_at") is None or state.get("worker_finished_at") is None:
        return False
    if state.get("execution") is not None or state.get("execution_outcome") is not None:
        return False
    if any(
        state.get(field) is not None
        for field in (
            "candidate", "candidate_commit_sha", "candidate_ref",
            "candidate_state_hash", "verified_receipt", "verified_receipt_hash",
        )
    ):
        return False
    packet = state.get("promotion_packet")
    if packet is not None and (
        not isinstance(packet, Mapping)
        or any(
            packet.get(field) is not None
            for field in (
                "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash",
                "verified_receipt_hash", "approval_binding",
            )
        )
    ):
        return False
    if state.get("candidate_status") not in (None, ""):
        return False
    if state.get("promotion_status") != "NOT_CREATED":
        return False
    if state.get("merge_performed") not in (None, False) or state.get("push_performed") not in (None, False):
        return False
    telemetry = state.get("telemetry")
    if not isinstance(telemetry, Mapping):
        return False
    if any(
        type(telemetry.get(field)) is not int or telemetry[field] != 0
        for field in ("provider_calls", "provider_attempts", "provider_time_ms", "verifier_time_ms")
    ):
        return False
    return _service_module()._terminal_retry_inherited_worktree_time_allowed(state)


def _terminal_retry_released_lease_proof(state: Mapping[str, Any]) -> bool:
    lease = state.get("lease")
    contract = state.get("contract")
    if not isinstance(lease, Mapping) or not isinstance(contract, Mapping):
        return False
    controller_root = Path(str(contract.get("controller_repo_root") or "")).expanduser()
    target_worktree = Path(str(lease.get("target_worktree") or "")).expanduser()
    if not controller_root.is_dir() or not target_worktree:
        return False
    try:
        controller_root = controller_root.resolve(strict=True)
        manager = _service_module().WorktreeManager(create_root=False)
        return manager.released_lease_proof(
            controller_root,
            task_id=str(state.get("task_id") or ""),
            attempt_id=str(state.get("attempt_id") or "") or None,
            lease_id=str(lease.get("lease_id") or ""),
            target_worktree=target_worktree,
            task_state=state,
        )
    except (OSError, RuntimeError, ValueError, TypeError):
        return False


def _terminal_retry_verifier_static_failure_allowed(state: Mapping[str, Any]) -> bool:
    """Allow the one known verifier pre-provider failure after formal cleanup."""
    if (
        state.get("status") != "FINAL_BLOCK"
        or state.get("error") != "invalid verifier contract: invalid verifier argument"
        or state.get("cleanup_decision") != "REMOVED"
        or state.get("cleanup_performed") is not True
        or not state.get("cleanup_performed_at")
        or state.get("cleanup_blocker") not in (None, "")
        or state.get("cleanup_eligible") is not True
        or not _service_module()._terminal_retry_released_lease_proof(state)
    ):
        return False
    lease = state.get("lease")
    if (
        not isinstance(lease, Mapping)
        or not lease.get("lease_id")
        or lease.get("task_id") != state.get("task_id")
        or state.get("target_created_at") is None
        or not state.get("active_provider")
        or not isinstance(state.get("worker_preflight"), Mapping)
        or state.get("worker_started_at") is None
        or state.get("worker_finished_at") is None
        or state.get("worker_child_pgid") is not None
        or state.get("execution") is not None
        or state.get("execution_outcome") is not None
        or state.get("executions") not in (None, [])
        or state.get("promotion_status") != "NOT_CREATED"
        or state.get("candidate_status") not in (None, "")
        or state.get("merge_performed") not in (None, False)
        or state.get("push_performed") not in (None, False)
    ):
        return False
    if any(state.get(field) is not None for field in (
        "candidate", "candidate_commit_sha", "candidate_ref", "candidate_state_hash",
        "verified_receipt", "verified_receipt_hash", "promotion_packet",
        "provider_receipt", "worker_receipt",
    )):
        return False
    telemetry = state.get("telemetry")
    return isinstance(telemetry, Mapping) and all(
        type(telemetry.get(field)) is int and telemetry[field] == 0
        for field in ("provider_calls", "provider_attempts", "provider_time_ms", "verifier_time_ms")
    )


def _validate_retry_predecessor(
    request: Mapping[str, Any],
    predecessor: Optional[Mapping[str, Any]],
) -> None:
    """Fail closed unless TASK_RETRY is a fresh attempt of one terminal task."""
    if predecessor is None:
        raise ValueError("RETRY_REQUIRES_EXISTING_TASK")

    status = str(predecessor.get("status") or "")
    cleanup_decision = str(predecessor.get("cleanup_decision") or "")
    if status not in _service_module().RETRYABLE_TASK_STATUSES:
        raise ValueError("RETRY_REQUIRES_TERMINAL_TASK")
    if cleanup_decision not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
        raise ValueError("RETRY_TARGET_DISPOSITION_REQUIRED")

    attempts = predecessor.get("attempts") or ()
    used_attempt_ids = {
        str(item.get("attempt_id") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_action_ids = {
        str(item.get("action_id") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_idempotency_keys = {
        str(item.get("idempotency_key") or "")
        for item in attempts
        if isinstance(item, Mapping)
    }
    used_attempt_ids.add(str(predecessor.get("attempt_id") or ""))
    used_action_ids.add(str(predecessor.get("action_id") or ""))
    used_idempotency_keys.add(str(predecessor.get("idempotency_key") or ""))
    if str(request.get("attempt_id") or "") in used_attempt_ids:
        raise ValueError("RETRY_ATTEMPT_ID_REUSED")
    if str(request.get("action_id") or "") in used_action_ids:
        raise ValueError("RETRY_ACTION_ID_REUSED")
    if str(request.get("idempotency_key") or "") in used_idempotency_keys:
        raise ValueError("RETRY_IDEMPOTENCY_KEY_REUSED")

    previous_request = predecessor.get("request")
    if not isinstance(previous_request, Mapping):
        raise ValueError("RETRY_PREDECESSOR_REQUEST_MISSING")
    if _service_module().canonical_request_hash(_service_module()._terminal_retry_semantic_payload(request)) != _service_module().canonical_request_hash(
        _service_module()._terminal_retry_semantic_payload(previous_request)
    ):
        raise ValueError("RETRY_SEMANTIC_TASK_MISMATCH")
# fmt: on
