"""State-store core of ``SelfHostedTaskService``.

Big-file split S6b (Issue #2570). ``_StateStoreMixin`` holds the members every task
state read and write goes through, moved out of
``nexus/orchestrator/self_hosted_task_service.py``: the paths (``_state_path``,
``_archive_root``, ``_archive_state_path``, ``_archive_state_candidates``,
``_lock_path``), the invalid-state receipts and payload validation
(``_invalid_state_status``, ``_state_error_receipt``, ``_validate_state_payload``), the
loads (``_load_state_path``, ``_latest_archived_state``, ``_read_state``,
``_read_state_snapshot``), the state lock (``_state_lock``) and the writes
(``_write_state_locked``, ``_normalize_state_write``, ``_write_state``, ``_create_state``,
``_reactivate_archived_state``, ``_mutate_state``), plus
``_require_integrated_replacement``. Their source lines are verbatim, except that every
facade-module name they load (``DURABLE_SELF_HOSTED_STATUSES``, ``ExecutionStateStore``
and ``_jsonable``) is resolved at call time through ``_service_module()``, so patches on
the facade keep taking effect; the status set and the runtime store class stay imported
by the facade.

This is not read-only code: ``_state_lock`` takes the exclusive ``flock`` on
``<state>/.state.lock`` and the write members replace state files atomically through the
runtime ``ExecutionStateStore`` (``nexus_runtime.execution_state``). Lock-free are the
paths, the receipts and validation, ``_load_state_path``, ``_latest_archived_state`` and
``_read_state_snapshot``. The constructor (``__init__``, which binds
``_normalize_state_write`` and ``_state_error_receipt`` into the runtime store) and
``canonical_state_dir`` stay in the facade class; the task-action envelope is reached
through ``cls`` / ``self`` (``_ActionEnvelopeMixin``).
"""

from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping, Optional, Sequence

if TYPE_CHECKING:
    from nexus.orchestrator.runtime_state_bridge import RuntimeStateBridge


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _StateStoreMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService
        state_dir: Path
        _runtime_state_bridge: RuntimeStateBridge

        @classmethod
        def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]: ...

        @classmethod
        def _with_task_action(cls, state: dict[str, Any]) -> dict[str, Any]: ...

    # fmt: off
    def _state_path(self, task_id: str) -> Path:
        return self._runtime_state_bridge.store.state_path(task_id)

    def _archive_root(self) -> Path:
        return self.state_dir.parent / "nexus-state-archive"

    def _archive_state_path(self, task_id: str) -> Path:
        return self._archive_root() / f"{task_id}.json"

    def _archive_state_candidates(self, task_id: str) -> list[Path]:
        return self._runtime_state_bridge.store.archive_candidates(task_id)

    def _require_integrated_replacement(self, task_id: str, superseded_by: str) -> None:
        replacement = self._read_state(superseded_by)
        if (
            replacement is None
            or superseded_by == task_id
            or replacement.get("task_id") != superseded_by
            or replacement.get("status") != "INTEGRATED"
            or replacement.get("promotion_status") != "INTEGRATED"
            or not str(replacement.get("integration_result_sha") or "").strip()
        ):
            raise RuntimeError(
                "superseded_by must name an existing INTEGRATED self-hosted task "
                "with promotion_status=INTEGRATED and integration_result_sha"
            )

    @classmethod
    def _invalid_state_status(
        cls,
        task_id: str,
        *,
        code: str,
        detail: str,
        source_path: Path,
        approval_requirements_reasons: Sequence[str] = (),
    ) -> dict[str, Any]:
        blocker: dict[str, Any] = {
            "code": code,
            "detail": detail,
            "source_path": str(source_path),
        }
        if approval_requirements_reasons:
            blocker["approval_requirements_reasons"] = sorted(set(approval_requirements_reasons))
        return cls._with_task_action(
            {
                "schema": "nexus.self_hosted_task_status.v1",
                "task_id": task_id,
                "status": "BLOCKED_INVALID_STATE",
                "found": True,
                "state_valid": False,
                "retry_authorized": False,
                "blocker": blocker,
            }
        )

    @classmethod
    def _state_error_receipt(cls, task_id: str, path: Path, error: BaseException) -> dict[str, Any]:
        if isinstance(error, json.JSONDecodeError):
            return cls._invalid_state_status(
                task_id,
                code="STATE_JSON_INVALID",
                detail=f"state JSON is invalid at line {error.lineno} column {error.colno}",
                source_path=path,
            )
        if isinstance(error, ValueError) and str(error) == "state JSON must decode to an object":
            return cls._invalid_state_status(
                task_id, code="STATE_NOT_OBJECT", detail=str(error), source_path=path
            )
        return cls._invalid_state_status(
            task_id,
            code="STATE_READ_FAILED",
            detail=f"state file could not be read: {type(error).__name__}",
            source_path=path,
        )

    @classmethod
    def _validate_state_payload(
        cls, task_id: str, payload: Mapping[str, Any], source_path: Path
    ) -> dict[str, Any]:
        """Validate an already decoded durable state payload for the runtime store."""
        if not isinstance(payload, Mapping):
            return cls._state_error_receipt(
                task_id, source_path, ValueError("state JSON must decode to an object")
            )
        state = dict(payload)
        if not isinstance(state.get("task_id"), str) or state.get("task_id") != task_id:
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail="state task_id is missing or does not match its filename",
                source_path=source_path,
            )
        status = state.get("status")
        if (
            not isinstance(status, str)
            or not status.strip()
            or status not in _service_module().DURABLE_SELF_HOSTED_STATUSES
        ):
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail=f"state status is invalid or unknown: {status!r}"
                if isinstance(status, str) and status.strip()
                else "state status must be a non-empty string",
                source_path=source_path,
            )
        for field in ("attempts", "executions"):
            value = state.get(field)
            if field in state and (
                not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value)
            ):
                return cls._invalid_state_status(
                    task_id,
                    code="STATE_FIELD_INVALID",
                    detail=f"state {field} must be a list of objects",
                    source_path=source_path,
                )
        object_fields = (
            "action",
            "attempt_resolution",
            "contract",
            "lease",
            "promotion_packet",
            "request",
            "verified_receipt",
        )
        invalid = [
            field
            for field in object_fields
            if field in state and state[field] is not None and not isinstance(state[field], Mapping)
        ]
        if invalid:
            field = invalid[0]
            reasons = [
                f"malformed_source:{name}:expected_mapping"
                for name in invalid
                if name in {"promotion_packet", "verified_receipt"}
            ]
            return cls._invalid_state_status(
                task_id,
                code="STATE_FIELD_INVALID",
                detail=f"state {field} must be an object",
                source_path=source_path,
                approval_requirements_reasons=reasons,
            )
        return cls._with_task_action(state)

    @classmethod
    def _load_state_path(cls, path: Path, task_id: str) -> Optional[dict[str, Any]]:
        return _service_module().ExecutionStateStore(
            path.parent,
            validator=cls._validate_state_payload,
            error_receipt=cls._state_error_receipt,
            validate_writes=False,
        ).load_path(path, task_id)

    def _latest_archived_state(
        self, task_id: str
    ) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
        return self._runtime_state_bridge.store.latest_archive(task_id)

    def _lock_path(self) -> Path:
        return self.state_dir / ".state.lock"

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        with self._runtime_state_bridge.store.lock():
            yield

    def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        return self._runtime_state_bridge.write(task_id, state, already_locked=True)  # pyright: ignore[reportReturnType]

    def _normalize_state_write(self, task_id: str, state: Mapping[str, Any]) -> Mapping[str, Any]:
        normalized = _service_module()._jsonable(state)
        normalized["task_action"] = self._task_action_envelope(normalized)
        return normalized

    def _write_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            return self._write_state_locked(task_id, state)

    def _create_state(self, task_id: str, state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._state_lock():
            destination = self._state_path(task_id)
            if destination.exists():
                existing = self._load_state_path(destination, task_id)
                if existing is not None:
                    return existing, False
            _, archived = self._latest_archived_state(task_id)
            if archived is not None:
                return archived, False
            return self._write_state_locked(task_id, state), True

    def _read_state(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._state_path(task_id)
        if not path.exists():
            _, archived = self._latest_archived_state(task_id)
            return archived
        with self._state_lock():
            if not path.exists():
                return None
            return self._load_state_path(path, task_id)

    def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        """Read a durable snapshot without creating or acquiring the state lock.

        Read-only status and workspace inventory surfaces must not mutate the
        lifecycle store. State writes use atomic ``replace`` semantics, so a
        direct read observes either the previous complete JSON or the next
        complete JSON; a concurrent disappearance is treated as absent.
        """
        return self._runtime_state_bridge.read(task_id)  # pyright: ignore[reportReturnType]

    def _reactivate_archived_state(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock():
            path = self._state_path(task_id)
            if path.exists():
                return self._with_task_action(json.loads(path.read_text(encoding="utf-8")))
            if not self._archive_state_candidates(task_id):
                raise RuntimeError("archived task receipt disappeared before retry")
            return self._write_state_locked(task_id, state)

    def _mutate_state(
        self, task_id: str, mutator: Callable[[dict[str, Any]], None]
    ) -> Optional[dict[str, Any]]:
        with self._state_lock():
            return self._runtime_state_bridge.mutate(task_id, mutator, already_locked=True)  # pyright: ignore[reportReturnType]
    # fmt: on
