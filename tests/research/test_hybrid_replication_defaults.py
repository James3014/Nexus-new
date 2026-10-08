from pathlib import Path

from nexus.research.hybrid_replication_live import (
    DEFAULT_REPO_ROOTS,
    resolve_default_repo_roots,
    resolve_live_binding,
    resolve_workspace_root,
)

HOME = Path("/home/tester")
EXPECTED_KEYS = [
    "James3014/Nexus-new",
    "James3014/devspace",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine",
    "James3014/nexus-runtime",
    "James3014/nexus-opencli-reviewer",
]


def test_workspace_root_env_override_wins() -> None:
    assert resolve_workspace_root({"NEXUS_WORKSPACE_ROOT": "/x/ws"}, HOME) == Path("/x/ws")


def test_workspace_root_defaults_from_home() -> None:
    assert resolve_workspace_root({}, HOME) == HOME / "Workspace"


def test_live_binding_env_override_wins() -> None:
    env = {"NEXUS_HYBRID_LIVE_BINDING": "/x/LB.json"}
    assert resolve_live_binding(env, HOME) == Path("/x/LB.json")


def test_live_binding_defaults_from_home() -> None:
    assert resolve_live_binding({}, HOME) == (
        HOME / "nexus-hybrid-deployment-replication-20260930" / "live" / "LIVE_BINDING.json"
    )


def test_repo_roots_keys_and_order_unchanged() -> None:
    roots = resolve_default_repo_roots({}, HOME)
    assert list(roots) == EXPECTED_KEYS
    assert roots["James3014/devspace"] == str(HOME / "Workspace" / "devspace")
    assert list(DEFAULT_REPO_ROOTS) == EXPECTED_KEYS


def test_repo_roots_follow_env_override() -> None:
    roots = resolve_default_repo_roots({"NEXUS_WORKSPACE_ROOT": "/x/ws"}, HOME)
    assert roots["James3014/Nexus-new"] == "/x/ws/Nexus-new"
