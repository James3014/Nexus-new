"""Boundary between caller ownership checks and runtime state I/O.

The caller supplies pure payload validation and operation authorization.  The
runtime store owns JSON decoding, archive selection, locking, and atomic
replacement; no caller callback is allowed to perform I/O inside a mutation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from nexus_runtime.execution_state import ExecutionStateStore


class RuntimeStateBridge:
    def __init__(
        self,
        state_dir: Path,
        *,
        validator: Callable[[str, Mapping[str, Any], Path], Mapping[str, Any] | None],
        before_write: Callable[[str, Mapping[str, Any]], Mapping[str, Any] | None]
        | None = None,
    ) -> None:
        self.store = ExecutionStateStore(
            Path(state_dir),
            validator=validator,
            before_write=before_write,
            validate_writes=False,
        )

    def read(self, task_id: str) -> Mapping[str, Any] | None:
        return self.store.read_snapshot(task_id)

    def write(
        self,
        task_id: str,
        state: Mapping[str, Any],
        *,
        authorize: Callable[[], None] | None = None,
    ) -> Mapping[str, Any]:
        if authorize is not None:
            authorize()
        return self.store.write(task_id, state)

    def mutate(
        self,
        task_id: str,
        mutator: Callable[[dict[str, Any]], None],
        *,
        authorize: Callable[[], None] | None = None,
    ) -> Mapping[str, Any] | None:
        def guarded(value: dict[str, Any]) -> None:
            if authorize is not None:
                authorize()
            mutator(value)

        return self.store.mutate(task_id, guarded)
