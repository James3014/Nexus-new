from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RegistryStatusResult:
    registry_health: str
    skills_count: int
    models_configured: int
    policies_count: int
    last_refresh: str


@dataclass(frozen=True)
class SkillListRow:
    skill_id: str
    name: str
    origin_type: str


@dataclass(frozen=True)
class SkillSyncResult:
    added: int
    updated: int


class RegistryStatusManifest(Protocol):
    health: dict[str, Any]
    skills_count: int
    models_configured: int
    policies_count: int
    last_refresh: str


class RegistryClient(Protocol):
    registry: Any

    def get_status(self) -> RegistryStatusManifest:
        ...


class ExternalSkillLoaderLike(Protocol):
    def sync_all(self) -> tuple[int, int]:
        ...


RegistryFactory = Callable[[Path], RegistryClient]
SkillLoaderFactory = Callable[[Path], ExternalSkillLoaderLike]


def _default_registry_factory(repo_root: Path) -> RegistryClient:
    from nexus.core.unified_registry import UnifiedRegistry

    return UnifiedRegistry(repo_root)


def _default_skill_loader_factory(repo_root: Path) -> ExternalSkillLoaderLike:
    from nexus.learning.external_skill_loader import ExternalSkillLoader

    return ExternalSkillLoader(repo_root)


def get_registry_status(
    repo_root: str | Path,
    *,
    registry_factory: RegistryFactory | None = None,
) -> RegistryStatusResult:
    root = Path(repo_root)
    factory = registry_factory or _default_registry_factory
    manifest = factory(root).get_status()
    health = manifest.health or {}
    return RegistryStatusResult(
        registry_health=str(health.get("registry", "UNKNOWN")),
        skills_count=int(manifest.skills_count),
        models_configured=int(manifest.models_configured),
        policies_count=int(manifest.policies_count),
        last_refresh=str(manifest.last_refresh),
    )


def render_registry_status(result: RegistryStatusResult) -> list[str]:
    return [
        "📊 [Nexus Registry Status]",
        f"  SQLite Registry: {result.registry_health}",
        f"  Skill Count    : {result.skills_count}",
        f"  Models (Armor) : {result.models_configured}",
        f"  Policies Count : {result.policies_count}",
        f"  Last Refresh   : {result.last_refresh}",
    ]


def get_skills_list(
    repo_root: str | Path,
    *,
    registry_factory: RegistryFactory | None = None,
) -> list[SkillListRow]:
    root = Path(repo_root)
    factory = registry_factory or _default_registry_factory
    skills = factory(root).registry.list_all()
    return [
        SkillListRow(
            skill_id=str(skill.get("id", "")),
            name=str(skill.get("name", "")),
            origin_type=str(skill.get("origin_type", "internal")),
        )
        for skill in skills
    ]


def render_skills_list(skills: list[SkillListRow]) -> list[str]:
    lines = [
        f"{'ID':<20} | {'Name':<30} | {'Type':<10}",
        "-" * 65,
    ]
    for skill in skills:
        lines.append(f"{skill.skill_id:<20} | {skill.name:<30} | {skill.origin_type:<10}")
    return lines


def sync_external_skills(
    repo_root: str | Path,
    *,
    loader_factory: SkillLoaderFactory | None = None,
) -> SkillSyncResult:
    root = Path(repo_root)
    loader = (loader_factory or _default_skill_loader_factory)(root)
    added, updated = loader.sync_all()
    return SkillSyncResult(added=int(added), updated=int(updated))


def render_skill_sync_complete(result: SkillSyncResult) -> str:
    return f"✅ Sync Complete: {result.added} added, {result.updated} updated."
