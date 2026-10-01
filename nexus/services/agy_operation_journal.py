"""Agy compatibility facade over the provider-neutral direct-operation journal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.services.direct_operation_journal import (
    DirectOperationJournal,
    DirectOperationJournalError,
)
from nexus.services.direct_operation_journal import (
    new_attempt_id as new_attempt_id,
)
from nexus.services.direct_operation_journal import (
    new_operation_id as _new_operation_id,
)
from nexus.services.direct_operation_journal import (
    public_operation_view as public_operation_view,
)
from nexus.services.direct_operation_journal import (
    utc_now as utc_now,
)

SCHEMA = "nexus.agy_operation.v1"
_OPERATION_PREFIX = "agyop_"
AgyOperationJournalError = DirectOperationJournalError


def new_operation_id() -> str:
    return _new_operation_id(_OPERATION_PREFIX)


class AgyOperationJournal(DirectOperationJournal):
    """Preserve the existing Agy journal contract while sharing the core."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            schema=SCHEMA,
            operation_prefix=_OPERATION_PREFIX,
        )

    def create(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        cwd: str,
        provider: str,
        model: str | None,
        effort: str | None,
        prompt_sha256: str,
        runtime_revision: str | None,
    ) -> dict[str, Any]:
        return super().create(
            operation_id=operation_id,
            attempt_id=attempt_id,
            cwd=cwd,
            provider=provider,
            model=model,
            effort=effort,
            prompt_sha256=prompt_sha256,
            runtime_revision=runtime_revision,
        )
