from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


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

    def sync(self, payload: dict[str, Any]) -> bool:
        if not _sync_enabled():
            return False
        from nexus.services.memory_repository import MemoryRepository

        db_path = os.environ.get("NEXUS_MEMORY_DB_PATH")
        repo = MemoryRepository(
            Path(db_path) if db_path else self.project_root / ".nexus" / "memory" / "memory_index.lancedb"
        )
        repo.semantic_dedup_ingest("findings_cards", payload)
        return True


def _sync_enabled() -> bool:
    return os.environ.get("NEXUS_FINDINGS_LANCEDB_SYNC", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
