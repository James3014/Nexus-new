"""Regression: trusted-anchor ephemeral repositories are removed deterministically.

The default-branch verifier intermittently crashed in ``TemporaryDirectory``
cleanup with ``OSError: [Errno 39] Directory not empty: 'commit-graphs'`` because
Git work triggered by the bundle fetch (commit-graph write, detached auto-gc or
maintenance) was still writing into the temporary repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

import scripts.ops.trusted_deletion_anchor as trusted_anchor

HOSTILE_GIT_CONFIG = """\
[gc]
\tauto = 1
\tautoDetach = true
\tautoPackLimit = 1
\twriteCommitGraph = true
[maintenance]
\tauto = true
[fetch]
\twriteCommitGraph = true
"""


@pytest.fixture
def hostile_git_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every global default eagerly schedule background Git work."""

    global_config = tmp_path / "hostile.gitconfig"
    global_config.write_text(HOSTILE_GIT_CONFIG, encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "trusted-anchor-test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "trusted-anchor-test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _source_repo(root: Path) -> tuple[Path, str, str]:
    source = root / "source"
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    (source / "tests").mkdir()
    (source / "tests/test_example.py").write_text("def test_x():\n    assert True\n")
    (source / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (source / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(source, "add", ".")
    _run_git(source, "commit", "-qm", "base")
    base_sha = _run_git(source, "rev-parse", "HEAD")
    (source / "tests/test_example.py").write_text("def test_x():\n    assert 1 + 1 == 2\n")
    _run_git(source, "commit", "-qam", "head")
    head_sha = _run_git(source, "rev-parse", "HEAD")
    return source, base_sha, head_sha


def test_ephemeral_bare_repo_disables_background_git_work(
    tmp_path: Path, hostile_git_environment: None
) -> None:
    repo = tmp_path / "repo.git"
    trusted_anchor._init_ephemeral_bare_repo(repo)
    for key, value in trusted_anchor.EPHEMERAL_GIT_CONFIG:
        assert _run_git(repo, "config", "--local", "--get", key) == value
        # Repository-local values must win over the hostile global defaults.
        assert _run_git(repo, "config", "--get", key) == value


def test_bundle_fetch_leaves_ephemeral_repo_quiescent_across_repeated_runs(
    tmp_path: Path, hostile_git_environment: None
) -> None:
    source, base_sha, head_sha = _source_repo(tmp_path)
    bundle = tmp_path / "git-objects.bundle"
    trusted_anchor._create_git_bundle(source, bundle, base_sha, head_sha, base_sha)
    for attempt in range(5):
        directory = Path(tempfile.mkdtemp(prefix="trusted-anchor-verify-", dir=tmp_path))
        repo = directory / "repo.git"
        trusted_anchor._init_ephemeral_bare_repo(repo)
        for ref in (trusted_anchor.BASE_REF, trusted_anchor.HEAD_REF):
            trusted_anchor._git(repo, "fetch", str(bundle), f"{ref}:{ref}")
        info = repo / "objects/info"
        assert not (info / "commit-graphs").exists(), attempt
        assert not (info / "commit-graph").exists(), attempt
        assert not (repo / "gc.pid").exists(), attempt
        # Strict removal (no ignore_errors) must succeed immediately.
        shutil.rmtree(directory)
        assert not directory.exists()


class _CleanupFailingTemporaryDirectory:
    """Stand-in reproducing the observed ``__exit__`` failure deterministically.

    Mirrors the stdlib contract: the cleanup error surfaces only when
    ``ignore_cleanup_errors`` is not requested.
    """

    def __init__(self, *, prefix: str, ignore_cleanup_errors: bool = False) -> None:
        self.name = tempfile.mkdtemp(prefix=prefix)
        self.ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *exc_info: object) -> None:
        shutil.rmtree(self.name, ignore_errors=True)
        if not self.ignore_cleanup_errors:
            raise OSError(39, "Directory not empty", "commit-graphs")


def _verifier_bundle(root: Path) -> tuple[Path, argparse.Namespace]:
    source, base_sha, head_sha = _source_repo(root)
    bundle_dir = root / "bundle"
    bundle_dir.mkdir()
    trusted_anchor._create_git_bundle(
        source, bundle_dir / "git-objects.bundle", base_sha, head_sha, base_sha
    )
    identity = {
        "event_name": "pull_request_target",
        "repository": "James3014/Nexus-new",
        "default_branch": "main",
        "workflow_ref": (
            "James3014/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main"
        ),
        "workflow_sha": base_sha,
        "run_id": 1765,
        "pull_request_number": 1765,
    }
    manifest_bytes = json.dumps(
        {"workflow_identity": identity, "base_sha": base_sha, "head_sha": head_sha}
    ).encode()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    anchor_bytes = json.dumps(
        {
            "manifest_sha256": manifest_sha256,
            "workflow_identity": identity,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
    ).encode()
    (bundle_dir / "manifest.json").write_bytes(manifest_bytes)
    (bundle_dir / "external-anchor.json").write_bytes(anchor_bytes)
    (bundle_dir / "raw-evidence.json").write_text("{}")
    # Deliberately wrong: the verifier must reject inside the temp-repo block.
    (bundle_dir / "raw-diff.bin").write_bytes(b"tampered")
    args = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        verify_evidence=str(bundle_dir / "raw-evidence.json"),
        expected_event_name=identity["event_name"],
        expected_repository=identity["repository"],
        expected_default_branch=identity["default_branch"],
        expected_workflow_ref=identity["workflow_ref"],
        expected_workflow_sha=base_sha,
        expected_run_id=identity["run_id"],
        expected_pull_request_number=identity["pull_request_number"],
        expected_manifest_sha256=manifest_sha256,
        expected_external_anchor_sha256=hashlib.sha256(anchor_bytes).hexdigest(),
        expected_base_sha=base_sha,
        expected_head_sha=head_sha,
    )
    return bundle_dir, args


def test_verifier_cleanup_error_does_not_mask_verification_failure(
    tmp_path: Path, hostile_git_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, args = _verifier_bundle(tmp_path)
    monkeypatch.setattr(
        trusted_anchor.tempfile, "TemporaryDirectory", _CleanupFailingTemporaryDirectory
    )
    with pytest.raises(SystemExit) as excinfo:
        trusted_anchor._verifier(args)
    assert excinfo.value.code == 1


def test_verifier_rejects_tampered_diff_with_real_cleanup_across_repeated_runs(
    tmp_path: Path, hostile_git_environment: None
) -> None:
    _, args = _verifier_bundle(tmp_path)
    before = set(os.listdir(tempfile.gettempdir()))
    for _ in range(5):
        with pytest.raises(SystemExit) as excinfo:
            trusted_anchor._verifier(args)
        assert excinfo.value.code == 1
    leaked = {
        name
        for name in set(os.listdir(tempfile.gettempdir())) - before
        if name.startswith("trusted-anchor-verify-")
    }
    assert not leaked
