from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.exception_translation import NexusCliActionError
from scripts.engine.commands.registry_actions import (
    RegistryStatusResult,
    SkillListRow,
    SkillSyncResult,
    get_registry_status,
    get_skills_list,
    render_registry_status,
    render_skill_sync_complete,
    render_skills_list,
    sync_external_skills,
)


@dataclass
class FakeManifest:
    health: dict[str, str]
    skills_count: int
    models_configured: int
    policies_count: int
    last_refresh: str


class FakeRegistry:
    def __init__(self, manifest: FakeManifest) -> None:
        self._manifest = manifest
        self.registry = FakeSkillRegistry([])

    def get_status(self) -> FakeManifest:
        return self._manifest


class FakeSkillRegistry:
    def __init__(self, skills: list[dict]) -> None:
        self._skills = skills

    def list_all(self) -> list[dict]:
        return self._skills


class FakeUnifiedRegistry:
    def __init__(self, skills: list[dict]) -> None:
        self.registry = FakeSkillRegistry(skills)


class FakeSkillLoader:
    def __init__(self, result: tuple[int, int]) -> None:
        self._result = result

    def sync_all(self) -> tuple[int, int]:
        return self._result


def test_get_registry_status_maps_manifest_without_click(tmp_path: Path):
    calls: list[Path] = []
    manifest = FakeManifest(
        health={"registry": "OK"},
        skills_count=7,
        models_configured=3,
        policies_count=2,
        last_refresh="2026-05-22T12:00:00Z",
    )

    def registry_factory(root: Path) -> FakeRegistry:
        calls.append(root)
        return FakeRegistry(manifest)

    result = get_registry_status(tmp_path, registry_factory=registry_factory)

    assert calls == [tmp_path]
    assert result == RegistryStatusResult(
        registry_health="OK",
        skills_count=7,
        models_configured=3,
        policies_count=2,
        last_refresh="2026-05-22T12:00:00Z",
    )


def test_render_registry_status_preserves_cli_output_schema():
    lines = render_registry_status(
        RegistryStatusResult(
            registry_health="OK",
            skills_count=7,
            models_configured=3,
            policies_count=2,
            last_refresh="2026-05-22T12:00:00Z",
        )
    )

    assert lines == [
        "📊 [Nexus Registry Status]",
        "  SQLite Registry: OK",
        "  Skill Count    : 7",
        "  Models (Armor) : 3",
        "  Policies Count : 2",
        "  Last Refresh   : 2026-05-22T12:00:00Z",
    ]


def test_registry_status_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_get_registry_status(root: Path) -> RegistryStatusResult:
        assert root == tmp_path
        return RegistryStatusResult(
            registry_health="OK",
            skills_count=7,
            models_configured=3,
            policies_count=2,
            last_refresh="2026-05-22T12:00:00Z",
        )

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_registry_status", fake_get_registry_status)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "registry", "status"])

    assert result.exit_code == 0
    assert "SQLite Registry: OK" in result.output
    assert "Skill Count    : 7" in result.output
    assert "Last Refresh   : 2026-05-22T12:00:00Z" in result.output


def test_registry_status_cli_translates_action_errors(monkeypatch, tmp_path: Path):
    def fake_get_registry_status(root: Path) -> RegistryStatusResult:
        raise NexusCliActionError("registry status unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_registry_status", fake_get_registry_status)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "registry", "status"])

    assert result.exit_code == 6
    assert "Error: registry status unavailable" in result.output


def test_get_skills_list_maps_registry_rows_without_click(tmp_path: Path):
    calls: list[Path] = []

    def registry_factory(root: Path) -> FakeUnifiedRegistry:
        calls.append(root)
        return FakeUnifiedRegistry(
            [
                {"id": "s1", "name": "Alpha", "origin_type": "external"},
                {"id": "s2", "name": "Beta"},
            ]
        )

    rows = get_skills_list(tmp_path, registry_factory=registry_factory)

    assert calls == [tmp_path]
    assert rows == [
        SkillListRow(skill_id="s1", name="Alpha", origin_type="external"),
        SkillListRow(skill_id="s2", name="Beta", origin_type="internal"),
    ]


def test_render_skills_list_preserves_cli_table_schema():
    lines = render_skills_list(
        [
            SkillListRow(skill_id="s1", name="Alpha", origin_type="external"),
            SkillListRow(skill_id="s2", name="Beta", origin_type="internal"),
        ]
    )

    assert lines == [
        "ID                   | Name                           | Type      ",
        "-----------------------------------------------------------------",
        "s1                   | Alpha                          | external  ",
        "s2                   | Beta                           | internal  ",
    ]


def test_skills_list_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_get_skills_list(root: Path) -> list[SkillListRow]:
        assert root == tmp_path
        return [SkillListRow(skill_id="s1", name="Alpha", origin_type="external")]

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_skills_list", fake_get_skills_list)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "skills", "list"])

    assert result.exit_code == 0
    assert "ID" in result.output
    assert "s1" in result.output
    assert "Alpha" in result.output


def test_skills_list_cli_translates_action_errors(monkeypatch, tmp_path: Path):
    def fake_get_skills_list(root: Path) -> list[SkillListRow]:
        raise NexusCliActionError("skills list unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "get_skills_list", fake_get_skills_list)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "skills", "list"])

    assert result.exit_code == 6
    assert "Error: skills list unavailable" in result.output


def test_sync_external_skills_maps_loader_result_without_click(tmp_path: Path):
    calls: list[Path] = []

    def loader_factory(root: Path) -> FakeSkillLoader:
        calls.append(root)
        return FakeSkillLoader(("2", "3"))

    result = sync_external_skills(tmp_path, loader_factory=loader_factory)

    assert calls == [tmp_path]
    assert result == SkillSyncResult(added=2, updated=3)


def test_render_skill_sync_complete_preserves_cli_output_schema():
    assert render_skill_sync_complete(SkillSyncResult(added=2, updated=3)) == (
        "✅ Sync Complete: 2 added, 3 updated."
    )


def test_skills_sync_cli_uses_action_result(monkeypatch, tmp_path: Path):
    def fake_sync_external_skills(root: Path) -> SkillSyncResult:
        assert root == tmp_path
        return SkillSyncResult(added=2, updated=3)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "sync_external_skills", fake_sync_external_skills)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "skills", "sync"])

    assert result.exit_code == 0
    assert "Sync Complete: 2 added, 3 updated." in result.output


def test_skills_sync_cli_translates_action_errors(monkeypatch, tmp_path: Path):
    def fake_sync_external_skills(root: Path) -> SkillSyncResult:
        raise NexusCliActionError("skills sync unavailable", exit_code=6)

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "sync_external_skills", fake_sync_external_skills)

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "skills", "sync"])

    assert result.exit_code == 6
    assert "Error: skills sync unavailable" in result.output
