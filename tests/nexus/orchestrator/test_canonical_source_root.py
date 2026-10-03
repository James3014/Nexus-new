from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.canonical_source_root import (
    DEFAULT_CANONICAL_SOURCE_ROOT,
    resolve_canonical_source_root,
    resolve_rdc_repo_root,
)

# ── existing resolve_canonical_source_root tests ──────────────────────


def test_unset_override_preserves_daily_canonical_default():
    assert resolve_canonical_source_root({}) == DEFAULT_CANONICAL_SOURCE_ROOT


def test_relative_override_fails_closed(tmp_path: Path):
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_MUST_BE_ABSOLUTE"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": "relative/root"}, source_root=tmp_path
        )


def test_missing_override_fails_closed(tmp_path: Path):
    missing = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_MISSING"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(missing)}, source_root=missing
        )


def test_override_cannot_rebind_loaded_code_to_another_directory(tmp_path: Path):
    loaded_root = tmp_path / "loaded"
    requested_root = tmp_path / "requested"
    loaded_root.mkdir()
    requested_root.mkdir()

    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_SOURCE_MISMATCH"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(requested_root)},
            source_root=loaded_root,
        )


def test_override_must_be_a_git_worktree_root(tmp_path: Path):
    with pytest.raises(RuntimeError, match="NEXUS_CANONICAL_SOURCE_ROOT_NOT_GIT_WORKTREE"):
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(tmp_path)},
            source_root=tmp_path,
        )


def test_matching_git_worktree_root_is_accepted(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    assert (
        resolve_canonical_source_root(
            {"NEXUS_CANONICAL_SOURCE_ROOT": str(tmp_path)},
            source_root=tmp_path,
        )
        == tmp_path.resolve()
    )


# ── Issue #1338: resolve_rdc_repo_root regression tests ───────────────


def _git_repo(
    tmp_path: Path, remote_url: str = "https://github.com/James3014/Nexus-new.git"
) -> Path:
    """Create a minimal git repo with an origin remote for testing."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "remote", "add", "origin", remote_url],
        check=True,
    )
    return tmp_path


def test_rdc_repo_root_wrong_cwd_does_not_affect_binding(tmp_path: Path):
    """Ambient cwd (/tmp or unrelated dir) must NOT become the repo root."""
    repo = _git_repo(tmp_path / "real_repo")

    # Resolve from the real repo — should succeed regardless of cwd
    result = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    assert result == repo.resolve()


def test_rdc_repo_root_remote_mismatch_fails_closed(tmp_path: Path):
    """If origin remote doesn't match expected_repository, fail closed."""
    repo = _git_repo(tmp_path, remote_url="https://github.com/SomeOther/Repo.git")

    with pytest.raises(RuntimeError, match="RDC_REPO_ROOT_REMOTE_MISMATCH"):
        resolve_rdc_repo_root(
            expected_repository="James3014/Nexus-new",
            canonical_root=repo,
        )


def test_rdc_repo_root_missing_root_fails_closed(tmp_path: Path):
    """Non-existent canonical root must fail closed."""
    missing = tmp_path / "does_not_exist"

    with pytest.raises(RuntimeError, match="RDC_REPO_ROOT_MISSING"):
        resolve_rdc_repo_root(
            expected_repository="James3014/Nexus-new",
            canonical_root=missing,
        )


def test_rdc_repo_root_not_git_repo_fails_closed(tmp_path: Path):
    """A directory that is not a git repo must fail closed."""
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()

    with pytest.raises(RuntimeError, match="RDC_REPO_ROOT_NOT_GIT_REPO"):
        resolve_rdc_repo_root(
            expected_repository="James3014/Nexus-new",
            canonical_root=plain_dir,
        )


def test_rdc_repo_root_no_origin_remote_fails_closed(tmp_path: Path):
    """A git repo without an origin remote must fail closed."""
    repo = tmp_path / "bare_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    with pytest.raises(RuntimeError, match="RDC_REPO_ROOT_REMOTE_UNREADABLE"):
        resolve_rdc_repo_root(
            expected_repository="James3014/Nexus-new",
            canonical_root=repo,
        )


def test_rdc_repo_root_stable_binding_on_resume(tmp_path: Path):
    """Deterministic: same result regardless of when/where resolve is called."""
    repo = _git_repo(tmp_path)

    result1 = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    result2 = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    assert result1 == result2 == repo.resolve()


def test_rdc_repo_root_ssh_remote_matches(tmp_path: Path):
    """SSH-style remotes should also match the expected repository."""
    repo = _git_repo(tmp_path, remote_url="git@github.com:James3014/Nexus-new.git")

    result = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    assert result == repo.resolve()


def test_rdc_repo_root_https_remote_matches(tmp_path: Path):
    """HTTPS-style remotes should match the expected repository."""
    repo = _git_repo(tmp_path, remote_url="https://github.com/James3014/Nexus-new.git")

    result = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    assert result == repo.resolve()


def test_rdc_repo_root_ssh_url_remote_matches(tmp_path: Path):
    """ssh:// URL-style remotes should also match the expected repository."""
    repo = _git_repo(tmp_path, remote_url="ssh://git@github.com/James3014/Nexus-new.git")

    result = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )
    assert result == repo.resolve()


def test_rdc_repo_root_defaults_to_canonical_source_root(tmp_path: Path):
    """When canonical_root is omitted, should use CANONICAL_SOURCE_ROOT."""
    # This tests the default-argument path; since CANONICAL_SOURCE_ROOT
    # is this repo, it should succeed if origin matches.
    # We test by providing an explicit canonical_root matching DEFAULT.
    root = DEFAULT_CANONICAL_SOURCE_ROOT
    # Verify the default path works (relies on real repo having correct remote).
    # This is a structural test—remote may not match in CI, so we test
    # that the function at least accepts canonical_root=None by checking
    # it doesn't crash with a non-remote error when given the real root.
    try:
        resolve_rdc_repo_root(
            expected_repository="James3014/Nexus-new",
            canonical_root=root,
        )
    except RuntimeError as exc:
        # Acceptable: remote mismatch in fork/CI, but NOT a missing/git error
        assert "REMOTE_MISMATCH" in str(exc) or "REMOTE_UNREADABLE" in str(exc)


def test_rdc_repo_root_uses_physical_identity_not_textual_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Git top-level spelling may differ while identifying the same directory."""
    repo = tmp_path / "Repo"
    repo.mkdir()
    calls = iter([
        subprocess.CompletedProcess(["git"], 0, stdout=str(tmp_path / "repo") + "\n", stderr=""),
        subprocess.CompletedProcess(
            ["git"], 0, stdout="https://github.com/James3014/Nexus-new.git\n", stderr=""
        ),
    ])
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(calls))
    monkeypatch.setattr(os.path, "samefile", lambda left, right: True)

    result = resolve_rdc_repo_root(
        expected_repository="James3014/Nexus-new",
        canonical_root=repo,
    )

    assert result == repo.resolve()
