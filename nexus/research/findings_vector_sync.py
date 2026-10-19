from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from nexus.services.lancedb_roots import MEMORY_INDEX, resolve_lancedb_root
from nexus.services.memory_repository_lifecycle import ScopedMemoryRepositoryRegistry

# Shared across syncs so the registry's repository cache (keyed by root/db/table) is actually reused.
_SHARED_REGISTRY = ScopedMemoryRepositoryRegistry()


def reset_shared_registry() -> None:
    _SHARED_REGISTRY.reset()


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

        resolved_db_path = resolve_lancedb_root(MEMORY_INDEX, self.project_root)
        registry = self.registry or _SHARED_REGISTRY
        repo = registry.repository_for(
            project_root=self.project_root,
            db_path=resolved_db_path,
            table_name="findings_cards",
        )
        if not payload.get("content") and payload.get("body"):
            payload = dict(payload)
            payload["content"] = payload["body"]
        if repo.semantic_dedup_ingest("findings_cards", payload) == "SKIPPED_READ_ONLY":
            return False  # #2721: nothing was synced
        return True


def _sync_enabled() -> bool:
    return os.environ.get("NEXUS_FINDINGS_LANCEDB_SYNC", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
