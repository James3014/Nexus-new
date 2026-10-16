"""Task Card allowed_files may never list authority-bearing paths (#1750).

Since #2271 an agent can create and commit Task Cards without an Owner step in
BOOTSTRAP + SEPARATE. A hash-bound card must therefore never be able to
"authorize" workflows, governance files or dependency pins.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import nexus.orchestrator.standing_grant_store as sg_store
from nexus.orchestrator import bootstrap_agent_authority as baa
from nexus.orchestrator.task_card_scope import protected_path_reason
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from tests.nexus.orchestrator.test_bootstrap_agent_authority import (  # noqa: F401
    _bind,
    _call,
    _create_args,
    _isolated,
    _make_pair,
    _real_mode,
    _records,
)

PROTECTED = [
    ".github/workflows/x.yml",
    ".github/CODEOWNERS",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/governance/current_operating_mode.yaml",
    ".nexus-core/config.toml",
    "pyproject.toml",
    "uv.lock",
]


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_paths_have_a_reason(path):
    assert protected_path_reason(path)


@pytest.mark.parametrize(
    "path",
    [
        "./AGENTS.md",
        ".GITHUB/workflows/x.yml",
        "Docs/Governance/x.yaml",
        "./uv.lock",
        "Pyproject.toml",
    ],
)
def test_normalization_and_case_insensitivity(path):
    assert protected_path_reason(path)


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "nexus/orchestrator/x.py",
        "tests/x.py",
        "docs/runbooks/x.md",
        "subdir/AGENTS.md",
        "scripts/ops/x.py",
        "tasks/x/00-card.md",
    ],
)
def test_ordinary_paths_are_not_protected(path):
    assert protected_path_reason(path) is None


@pytest.mark.parametrize("path", ["nexus/*.py", "tests/x?.py", "tests/[a].py"])
def test_glob_entries_are_refused(path):
    assert protected_path_reason(path)


def _args(path: str) -> dict[str, Any]:
    return {**_create_args(), "allowed_files": ["README.md", path]}


@pytest.mark.parametrize("path", PROTECTED)
def test_bootstrap_agent_create_refuses_protected_path_before_any_write(
    tmp_path, monkeypatch, path
):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _args(path))
    assert result["isError"] is True
    assert "TASK_CARD_CREATE_PROTECTED_PATH:" in result["structuredContent"]["error"]
    assert path in result["structuredContent"]["error"]
    assert not (controller / "tasks").exists()
    assert _records(tmp_path) == []
    assert not (tmp_path / "authority" / baa.RECORD_FILENAME).exists()


@pytest.mark.parametrize("path", PROTECTED)
def test_grant_path_create_refuses_protected_path_before_authority(tmp_path, monkeypatch, path):
    loaded, controller, _ = _make_pair(tmp_path, None)  # no mode file: grant path
    _bind(monkeypatch, loaded, controller, separate=False)
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", _args(path))
    assert result["isError"] is True
    error = result["structuredContent"]["error"]
    assert "TASK_CARD_CREATE_PROTECTED_PATH:" in error
    assert "OWNER_AUTHORITY_REQUIRED" not in error
    assert not (loaded / "tasks").exists()
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()


def test_bootstrap_authority_refuses_protected_effect_directly(tmp_path):
    from nexus.contracts.autonomy_goal import AutonomyActionClass

    with pytest.raises(baa.BootstrapAgentAuthorityError, match="PROTECTED_PATH"):
        baa.authorize_bootstrap_agent_effect(
            repository=MagicMock(),
            action=AutonomyActionClass.TASK_CARD_CREATE,
            effect={"allowed_files": ["AGENTS.md"]},
            key=None,
            context={},
            record_directory=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_ordinary_path_still_creates(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, _real_mode())
    _bind(monkeypatch, loaded, controller, separate=True)
    args = {**_create_args(), "allowed_files": ["README.md", "nexus/orchestrator/x.py"]}
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", args)
    assert result["isError"] is False, result["structuredContent"]


@pytest.mark.parametrize(
    "path",
    [
        ".github",
        ".github/",
        "docs/governance",
        ".nexus-core",
        "docs//governance/x.yaml",
        "docs/./governance/x.yaml",
        ".//AGENTS.md",
        ".github//workflows/x.yml",
    ],
)
def test_bare_directories_and_non_canonical_spellings_are_protected(path):
    assert protected_path_reason(path)


def test_create_refuses_protected_path_reached_through_symlink(tmp_path, monkeypatch):
    loaded, controller, _ = _make_pair(tmp_path, None)  # grant path: canonical root = loaded
    _bind(monkeypatch, loaded, controller, separate=False)
    (loaded / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (loaded / "ghlink").symlink_to(".github")
    args = {**_create_args(), "allowed_files": ["README.md", "ghlink/workflows/x.yml"]}
    result = _call(UnifiedMCPGateway(service=MagicMock()), "nexus_task_card_create", args)
    assert result["isError"] is True
    error = result["structuredContent"]["error"]
    assert "TASK_CARD_CREATE_PROTECTED_PATH:AUTHORITY_DIRECTORY:ghlink/workflows/x.yml" in error
    assert not (loaded / "tasks").exists()
    assert not sg_store.DEFAULT_RECEIPT_PATH.exists()
