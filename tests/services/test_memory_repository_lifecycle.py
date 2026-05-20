from pathlib import Path

from nexus.services.memory_repository_lifecycle import ScopedMemoryRepositoryRegistry


class FakeRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path


def test_scoped_memory_repository_registry_reuses_same_scope(tmp_path):
    created: list[Path] = []

    def factory(path: Path):
        created.append(path)
        return FakeRepository(path)

    registry = ScopedMemoryRepositoryRegistry(factory=factory)

    first = registry.repository_for(project_root=tmp_path, db_path=tmp_path / "memory.lancedb", table_name="findings")
    second = registry.repository_for(project_root=tmp_path, db_path=tmp_path / "memory.lancedb", table_name="findings")

    assert first is second
    assert len(created) == 1
    assert registry.cache_size() == 1


def test_scoped_memory_repository_registry_separates_project_roots_and_tables(tmp_path):
    registry = ScopedMemoryRepositoryRegistry(factory=FakeRepository)

    first = registry.repository_for(project_root=tmp_path / "a", db_path=tmp_path / "memory.lancedb", table_name="findings")
    second = registry.repository_for(project_root=tmp_path / "b", db_path=tmp_path / "memory.lancedb", table_name="findings")
    third = registry.repository_for(project_root=tmp_path / "a", db_path=tmp_path / "memory.lancedb", table_name="policy")

    assert first is not second
    assert first is not third
    assert registry.cache_size() == 3
    registry.reset()
    assert registry.cache_size() == 0
