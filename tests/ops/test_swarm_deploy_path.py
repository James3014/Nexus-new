"""Swarm deploy path retired (Owner decision 2026-10-16, #2334; was #1763 item 7).

nexus_swarm/ and nexus-swarm-v22-prod/ were physically deleted. The test ids below
are kept on purpose (the exact-base impact gate reads a vanished id as lost
coverage); each one now asserts the retired state of what it used to check.
Full coverage of the retirement lives in tests/ops/test_retired_go_swarm_removed.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "nexus_swarm"
ARCHIVED = ROOT / "nexus-swarm-v22-prod"


@pytest.mark.parametrize("name", ["manager", "node"])
def test_live_dockerfile_copies_only_existing_paths(name: str) -> None:
    assert not (LIVE / name / "Dockerfile").exists(), f"{name}/Dockerfile was retired"


def test_live_module_has_go_mod_sum_and_api() -> None:
    for rel in ("go.mod", "go.sum", "api/proto/swarm.proto"):
        assert not (LIVE / rel).exists(), rel


def test_removed_proto_field_not_used_in_live_manager() -> None:
    assert list((LIVE / "manager").glob("*.go")) == []


def test_legacy_demo_excluded_from_go_build_all() -> None:
    assert not (LIVE / "cmd" / "swarm-manager" / "main.go").exists()


def test_v22_prod_fork_is_marked_archived_and_has_no_go_module() -> None:
    assert not (ARCHIVED / "go.mod").exists()
    assert not (ARCHIVED / "README.md").exists()
