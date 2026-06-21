from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from nexus.services.memory_repository_lifecycle import ScopedMemoryRepositoryRegistry


class FindingsVectorSync(Protocol):
    """Adapter boundary for optional findings-card vector indexing."""

    def sync(self, payload: dict[str, Any]) -> bool:
        ...


@dataclass(frozen=True)
class NoopFindingsVectorSync:
    def sync(self, payload: dict[str, Any]) -> bool:
        return False


@dataclass(frozen=True)
class MemoryRepositoryFindingsVectorSync:
    project_root: Path
    registry: ScopedMemoryRepositoryRegistry | None = None

    def sync(self, payload: dict[str, Any]) -> bool:
        if not _sync_enabled():
            return False

        db_path = os.environ.get("NEXUS_MEMORY_DB_PATH")
        resolved_db_path = Path(db_path) if db_path else self.project_root / ".nexus" / "memory" / "memory_index.lancedb"
        registry = self.registry or ScopedMemoryRepositoryRegistry()
        repo = registry.repository_for(
            project_root=self.project_root,
            db_path=resolved_db_path,
            table_name="findings_cards",
        )
        if not payload.get("content") and payload.get("body"):
            payload = dict(payload)
            payload["content"] = payload["body"]
        repo.semantic_dedup_ingest("findings_cards", payload)
        return True


def _sync_enabled() -> bool:
    return os.environ.get("NEXUS_FINDINGS_LANCEDB_SYNC", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
