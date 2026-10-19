"""Operator outcome receipts of ``SelfHostedTaskService``.

Big-file split S7 (Issue #2575). ``_OperatorOutcomeMixin`` holds
``record_operator_outcome``, moved out of ``nexus/orchestrator/self_hosted_task_service.py``:
it appends one privacy-bounded operator outcome receipt
(``nexus.contracts.operator_outcome_receipt``) to an existing task state, after checking
the receipt against the task (identity, freshness, action id, source revision, runtime
receipt hash) once before and again under the state lock, together with the persisted
history (tamper and supersession checks) and idempotency.  It never changes the task's
lifecycle status or authority.  Its source lines are verbatim, except that the facade-module
name it loads (``validate_operator_outcome_receipt``) is resolved at call time through
``_service_module()``, so patches on the facade keep taking effect.

This is not read-only code: it reads the state through ``_read_state`` (state lock) and
appends through ``_mutate_state`` (state lock, then the runtime store's atomic replace);
both are reached through ``self`` (``_StateStoreMixin``).  ``_bound_custom_runner_values``,
which sat next to it, stays in the facade class; ``_promotion_authority_error`` lives in
``_FinalizeRuntimeMixin`` (``parts/finalize_runtime.py``, split S11).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from nexus.contracts.operator_outcome_receipt import OperatorOutcomeReceipt


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _OperatorOutcomeMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService (_StateStoreMixin)

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def _mutate_state(
            self, task_id: str, mutator: Callable[[dict[str, Any]], None]
        ) -> Optional[dict[str, Any]]: ...

    # fmt: off
    def record_operator_outcome(
        self,
        task_id: str,
        receipt: OperatorOutcomeReceipt | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist one privacy-bounded outcome in the existing task state.

        Idempotent replays return the original receipt.  A key reused with a
        different payload, a cross-attempt supersession, or a cycle fails
        closed; this method never changes task authority or lifecycle status.
        """
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task: {task_id}")
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        expected_action_id = str(state.get("action_id") or "").strip() or None
        expected_source_revision = str(
            state.get("controller_revision") or contract.get("controller_revision") or ""  # pyright: ignore[reportOptionalMemberAccess]
        ).strip() or None
        expected_runtime_receipt_hash = str(
            state.get("runtime_receipt_hash") or ""
        ).strip() or None
        normalized = _service_module().validate_operator_outcome_receipt(
            receipt,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            lifecycle_revision=str(state.get("lifecycle_revision") or ""),
        )
        if normalized.action_id is not None and normalized.action_id != expected_action_id:
            raise ValueError("OPERATOR_OUTCOME_ACTION_ID_MISMATCH")
        if normalized.source_revision is not None and (
            expected_source_revision is None
            or normalized.source_revision != expected_source_revision
        ):
            raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH")
        if normalized.runtime_receipt_hash is not None and (
            expected_runtime_receipt_hash is None
            or normalized.runtime_receipt_hash != expected_runtime_receipt_hash
        ):
            raise ValueError("OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH")

        def mutate(current: dict[str, Any]) -> None:
            current_contract = (
                current.get("contract")
                if isinstance(current.get("contract"), Mapping)
                else {}
            )
            current_action_id = str(current.get("action_id") or "").strip() or None
            current_source_revision = str(
                current.get("controller_revision")
                or current_contract.get("controller_revision")  # pyright: ignore[reportOptionalMemberAccess]
                or ""
            ).strip() or None
            current_runtime_receipt_hash = str(
                current.get("runtime_receipt_hash") or ""
            ).strip() or None
            _service_module().validate_operator_outcome_receipt(
                normalized,
                task_id=task_id,
                attempt_id=str(current.get("attempt_id") or ""),
                lifecycle_revision=str(current.get("lifecycle_revision") or ""),
            )
            if normalized.action_id is not None and normalized.action_id != current_action_id:
                raise ValueError("OPERATOR_OUTCOME_ACTION_ID_MISMATCH")
            if normalized.source_revision is not None and (
                current_source_revision is None
                or normalized.source_revision != current_source_revision
            ):
                raise ValueError("OPERATOR_OUTCOME_SOURCE_REVISION_MISMATCH")
            if normalized.runtime_receipt_hash is not None and (
                current_runtime_receipt_hash is None
                or normalized.runtime_receipt_hash != current_runtime_receipt_hash
            ):
                raise ValueError("OPERATOR_OUTCOME_RUNTIME_RECEIPT_HASH_MISMATCH")
            raw_existing = current.get("operator_outcome_receipts", [])
            if type(raw_existing) is not list or any(
                not isinstance(item, Mapping) for item in raw_existing
            ):
                raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
            existing = list(raw_existing)
            singular = current.get("operator_outcome_receipt")
            if (existing and singular is None) or (
                singular is not None
                and (
                    not isinstance(singular, Mapping)
                    or not existing
                    or dict(singular) != dict(existing[-1])
                )
            ):
                raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
            parsed = {}
            for item in existing:
                try:
                    prior = _service_module().validate_operator_outcome_receipt(
                        item,
                        task_id=task_id,
                        check_freshness=False,
                    )
                except ValueError as exc:
                    raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED") from exc
                if prior.receipt_id in parsed:
                    raise ValueError("OPERATOR_OUTCOME_PERSISTED_RECEIPT_TAMPERED")
                parsed[prior.receipt_id] = prior
            for prior in parsed.values():
                parent_hash = prior.supersedes_receipt_id
                if parent_hash is not None:
                    parent = parsed.get(parent_hash)
                    if parent is None:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING")
                    if parent.task_id != task_id or parent.attempt_id != prior.attempt_id:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ATTEMPT_MISMATCH")
                    if prior.observed_at <= parent.observed_at:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_ORDER_INVALID")
            for start in parsed.values():
                seen = set()
                cursor = start
                while cursor.supersedes_receipt_id is not None:
                    parent_hash = cursor.supersedes_receipt_id
                    if parent_hash in seen or parent_hash == start.receipt_id:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_CYCLE")
                    seen.add(parent_hash)
                    cursor = parsed.get(parent_hash)
                    if cursor is None:
                        raise ValueError("OPERATOR_OUTCOME_PERSISTED_SUPERSESSION_TARGET_MISSING")
            for item in existing:
                if item.get("idempotency_key") != normalized.idempotency_key:
                    continue
                if item.get("receipt_id") != normalized.receipt_id:
                    raise ValueError("OPERATOR_OUTCOME_IDEMPOTENCY_CONFLICT")
                return
            hashes = {str(item.get("receipt_id")) for item in existing}
            if normalized.supersedes_receipt_id is not None:
                if normalized.supersedes_receipt_id not in hashes:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_TARGET_MISSING")
                if normalized.supersedes_receipt_id == normalized.receipt_id:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_CYCLE")
                target = next(
                    item
                    for item in existing
                    if item.get("receipt_id") == normalized.supersedes_receipt_id
                )
                if target.get("task_id") != task_id or target.get("attempt_id") != normalized.attempt_id:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_ATTEMPT_MISMATCH")
                if normalized.observed_at <= parsed[normalized.supersedes_receipt_id].observed_at:
                    raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_ORDER_INVALID")
                seen = set()
                cursor = target
                while cursor.get("supersedes_receipt_id"):
                    parent = str(cursor["supersedes_receipt_id"])
                    if parent in seen or parent == normalized.receipt_id:
                        raise ValueError("OPERATOR_OUTCOME_SUPERSESSION_CYCLE")
                    seen.add(parent)
                    cursor = next(
                        (item for item in existing if item.get("receipt_id") == parent),
                        {},
                    )
            existing.append(normalized.model_dump(mode="json"))
            current["operator_outcome_receipts"] = existing
            current["operator_outcome_receipt"] = existing[-1]

        result = self._mutate_state(task_id, mutate)
        return dict(result.get("operator_outcome_receipt") or normalized.model_dump(mode="json"))  # pyright: ignore[reportOptionalMemberAccess]
    # fmt: on
