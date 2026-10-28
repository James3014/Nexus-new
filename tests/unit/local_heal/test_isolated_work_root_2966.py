"""#2966: the live Gateway runs from ``~/Library/Application Support/...``, a subtree the
model-output sandbox refuses as a read root, so default local_heal work dirs must land elsewhere.

On a host without an OS barrier (Linux CI, NEXUS_DISABLE_OS_SANDBOX=1) the run test proves only
that nothing runs; the path tests prove the relocation everywhere. No test skips."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus.engine.model_output_sandbox import denied_subtrees
from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services.local_heal import armor_artifact_storage
from nexus.services.local_heal.armor_artifact_storage import (
    ENV_ARMOR_ALLOW_EPHEMERAL,
    SANDBOX_REACHABLE_WORKSPACES_REL,
    make_isolated_workspace,
    resolve_isolated_work_root,
)
from nexus.services.local_heal.micro_verifier import MicroVerifier

# tmp_path is OS temp; production roots are not, and the durability check stays covered elsewhere.
_ENV = {ENV_ARMOR_ALLOW_EPHEMERAL: "1"}


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _deployment(home: Path) -> Path:
    # Same shape as the live Gateway's code root.
    root = home / "Library/Application Support/Nexus/gateway-direct/deployments/a1-0000"
    root.mkdir(parents=True)
    return root


def test_default_work_root_leaves_a_denied_subtree(home):
    root = resolve_isolated_work_root(workspace_root=_deployment(home), env=_ENV)
    assert root == (home / SANDBOX_REACHABLE_WORKSPACES_REL).resolve()
    assert root.is_dir()
    assert not any(root.is_relative_to(subtree) for subtree in denied_subtrees())


def test_relocated_work_root_must_still_be_durable(home, monkeypatch):
    # Only the fallback counts as ephemeral here, so the refusal is the relocation's own check.
    monkeypatch.setattr(
        armor_artifact_storage,
        "is_ephemeral_path",
        lambda path: str(SANDBOX_REACHABLE_WORKSPACES_REL) in str(path),
    )
    with pytest.raises(ValueError, match="isolated work root must be durable"):
        resolve_isolated_work_root(workspace_root=_deployment(home), env={})


def test_default_work_root_is_unchanged_outside_denied_subtrees(home):
    code_root = home / "workspace" / "Nexus-new"
    code_root.mkdir(parents=True)
    root = resolve_isolated_work_root(workspace_root=code_root, env=_ENV)
    assert root == (code_root / ".nexus/artifacts/local_armor/workspaces").resolve()


def test_explicit_work_dir_is_never_moved(home):
    explicit = _deployment(home) / "chosen"
    assert resolve_isolated_work_root(explicit, env=_ENV) == explicit.resolve()


def test_micro_verifier_runs_in_a_default_workspace_of_a_gateway_layout(home):
    repo = make_isolated_workspace(workspace_root=_deployment(home), env=_ENV, prefix="world-c-")
    (repo / "good.py").write_text("VALUE = 1\n")
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=repo,
        patched_files=["good.py"],
        verifier_env_metadata={"interpreter": sys.executable},
    )
    if not os_sandbox_available():
        assert "verifier_unavailable" in res.classifications
        return
    assert "sandbox_read_root_inside_forbidden" not in res.details
    assert res.import_ok is True
