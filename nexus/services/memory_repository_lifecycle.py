from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from nexus.services.memory_repository import MemoryRepository

RepositoryFactory = Callable[[Path], MemoryRepository]


@dataclass
class ScopedMemoryRepositoryRegistry:
    """Explicit lifecycle cache for LanceDB-backed memory repositories."""

    factory: RepositoryFactory = MemoryRepository
    _cache: dict[tuple[str, str, str], MemoryRepository] = field(default_factory=dict)

    def repository_for(self, *, project_root: Path, db_path: Path, table_name: str) -> MemoryRepository:
        key = (
            str(Path(project_root).resolve()),
            str(Path(db_path).resolve()),
            str(table_name),
        )
        if key not in self._cache:
            self._cache[key] = self.factory(Path(db_path))
        return self._cache[key]

    def reset(self) -> None:
        self._cache.clear()

    def cache_size(self) -> int:
        return len(self._cache)
