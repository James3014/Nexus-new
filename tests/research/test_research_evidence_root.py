from __future__ import annotations

from pathlib import Path

from nexus.research.clm_system_one.candidate_evidence_collector import (
    _collection_root,
)
from nexus.research.clm_system_one.research_evidence_root import (
    CANONICAL_STATE_RELATIVE_ROOT,
    DEFAULT_RELATIVE_ROOT,
    resolve_research_evidence_root,
)
from nexus.research.clm_system_one.trajectory_continuity import (
    resolve_research_evidence_root as trajectory_resolve_research_evidence_root,
)


def test_explicit_evidence_root_override_wins(tmp_path: Path, monkeypatch) -> None:
    override = tmp_path / "explicit-evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(override))
    monkeypatch.setenv(
        "NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR",
        str(tmp_path / "canonical-state"),
    )

    assert resolve_research_evidence_root(tmp_path / "repo") == override.resolve()


def test_distinct_worktrees_share_configured_canonical_state_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_root = tmp_path / "canonical-state"
    monkeypatch.delenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", raising=False)
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(state_root))

    first = resolve_research_evidence_root(tmp_path / "worktree-a")
    second = resolve_research_evidence_root(tmp_path / "worktree-b")

    expected = (state_root / CANONICAL_STATE_RELATIVE_ROOT).resolve()
    assert first == expected
    assert second == expected
    assert _collection_root(tmp_path / "worktree-a") == expected
    assert trajectory_resolve_research_evidence_root(tmp_path / "worktree-b") == expected


def test_repo_local_root_remains_standalone_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    repo_root = tmp_path / "standalone-repo"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", raising=False)
    monkeypatch.delenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", raising=False)

    assert (
        resolve_research_evidence_root(repo_root)
        == (repo_root.resolve() / DEFAULT_RELATIVE_ROOT).resolve()
    )
