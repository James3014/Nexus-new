"""Exactly one buildable Swarm deploy path: nexus_swarm/ (issue #1763 item 7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "nexus_swarm"
ARCHIVED = ROOT / "nexus-swarm-v22-prod"


def _copy_sources(dockerfile: Path) -> list[str]:
    sources: list[str] = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*COPY\s+(?!--from)(?:--\S+\s+)*(.+)\s+\S+\s*$", line)
        if match:
            sources.extend(match.group(1).split())
    return sources


@pytest.mark.parametrize("name", ["manager", "node"])
def test_live_dockerfile_copies_only_existing_paths(name: str) -> None:
    sources = _copy_sources(LIVE / name / "Dockerfile")
    assert sources
    for source in sources:
        if source == ".":
            continue
        assert (LIVE / source).exists(), f"{name}/Dockerfile COPYs missing {source}"


def test_live_module_has_go_mod_sum_and_api() -> None:
    for rel in ("go.mod", "go.sum", "api/proto/swarm.proto"):
        assert (LIVE / rel).is_file(), rel


def test_removed_proto_field_not_used_in_live_manager() -> None:
    for path in (LIVE / "manager").glob("*.go"):
        assert "PreferredRegion" not in path.read_text(encoding="utf-8").replace(
            "PreferredRegion removed", ""
        ), path.name


def test_legacy_demo_excluded_from_go_build_all() -> None:
    main = (LIVE / "cmd" / "swarm-manager" / "main.go").read_text(encoding="utf-8")
    assert main.startswith("//go:build legacy_v18_demo")


def test_v22_prod_fork_is_marked_archived_and_has_no_go_module() -> None:
    assert not (ARCHIVED / "go.mod").exists()
    readme = (ARCHIVED / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# ARCHIVED")
    assert "nexus_swarm/" in readme
