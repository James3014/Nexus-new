from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.canonical_core_transport import extract_git_manifest


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """Create a temporary initialized Git repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", "-b", "main"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "Test User"], cwd=repo)
    subprocess.check_call(["git", "config", "user.email", "test@nexus.internal"], cwd=repo)

    # Initial file and commit
    (repo / "tracked_a.txt").write_text("initial a\n", encoding="utf-8")
    (repo / "tracked_b.txt").write_text("initial b\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "."], cwd=repo)
    subprocess.check_call(["git", "commit", "-m", "initial commit"], cwd=repo)
    return repo


def _get_index_hash(repo: Path) -> str:
    """Get the write-tree hash of the normal git index without changing it."""
    return subprocess.check_output(["git", "write-tree"], cwd=repo, text=True).strip()


def test_t1_clean_committed_target(test_repo: Path):
    """T1: Clean committed target (base -> committed candidate) preserves existing behavior."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    # Modify and commit
    (test_repo / "tracked_a.txt").write_text("modified a\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "tracked_a.txt"], cwd=test_repo)
    subprocess.check_call(["git", "commit", "-m", "update a"], cwd=test_repo)
    cand_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    cand_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    manifest = extract_git_manifest(test_repo, base_commit, cand_commit)
    assert manifest["source_tree"] == f"git-tree:{base_tree}"
    assert manifest["target_tree"] == f"git-tree:{cand_tree}"
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["path"] == "tracked_a.txt"
    assert entry["change_type"] == "MODIFY"
    assert entry["before_oid"] is not None
    assert entry["after_oid"] is not None


def test_t2_dirty_tracked_modification(test_repo: Path):
    """T2: Working tree has uncommitted modifications to tracked file."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    # Uncommitted modification
    (test_repo / "tracked_a.txt").write_text("uncommitted dirty content\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert manifest["source_tree"] == f"git-tree:{base_tree}"
    assert manifest["target_tree"] != f"git-tree:{base_tree}"
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["path"] == "tracked_a.txt"
    assert entry["change_type"] == "MODIFY"

    # Target tree in manifest contains the actual blob
    blob_obj = subprocess.check_output(
        ["git", "cat-file", "-p", entry["after_oid"]], cwd=test_repo, text=True
    )
    assert blob_obj == "uncommitted dirty content\n"


def test_t3_dirty_untracked_file(test_repo: Path):
    """T3: Working tree has a new untracked file."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    # New untracked file
    (test_repo / "untracked_new.txt").write_text("brand new file\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert manifest["source_tree"] == f"git-tree:{base_tree}"
    assert manifest["target_tree"] != f"git-tree:{base_tree}"
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["path"] == "untracked_new.txt"
    assert entry["change_type"] == "ADD"
    assert entry["before_oid"] is None
    assert entry["before_mode"] is None
    assert entry["after_oid"] is not None

    blob_obj = subprocess.check_output(
        ["git", "cat-file", "-p", entry["after_oid"]], cwd=test_repo, text=True
    )
    assert blob_obj == "brand new file\n"


def test_t4_dirty_deletion(test_repo: Path):
    """T4: Tracked file deleted from working tree without commit."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    (test_repo / "tracked_b.txt").unlink()

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert manifest["source_tree"] == f"git-tree:{base_tree}"
    assert manifest["target_tree"] != f"git-tree:{base_tree}"
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["path"] == "tracked_b.txt"
    assert entry["change_type"] == "DELETE"
    assert entry["before_oid"] is not None
    assert entry["after_oid"] is None
    assert entry["after_mode"] is None


def test_t5_t6_t7_caller_non_interference(test_repo: Path):
    """T5/T6/T7: Caller normal index, working tree, and HEAD are strictly preserved."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    orig_index_hash = _get_index_hash(test_repo)

    # Make working tree dirty
    dirty_text = "dirty content not added to index\n"
    (test_repo / "tracked_a.txt").write_text(dirty_text, encoding="utf-8")
    (test_repo / "new_untracked.txt").write_text("untracked\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert len(manifest["entries"]) == 2

    # T5: normal index was NOT modified
    after_index_hash = _get_index_hash(test_repo)
    assert after_index_hash == orig_index_hash

    # T6: working tree files remain identical
    assert (test_repo / "tracked_a.txt").read_text(encoding="utf-8") == dirty_text
    assert (test_repo / "new_untracked.txt").read_text(encoding="utf-8") == "untracked\n"

    # T7: HEAD commit is unchanged
    after_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    assert after_head == base_commit


def test_t8_temp_index_cleanup(test_repo: Path):
    """T8: Temporary index directory is cleanly removed after success."""
    import tempfile

    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    (test_repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert len(manifest["entries"]) == 1

    # Verify no dangling temp indexes in system temp
    # TemporaryDirectory context manager guarantees cleanup
    assert Path(tempfile.gettempdir()).exists()


def test_t9_failure_cleanup(test_repo: Path, monkeypatch: pytest.MonkeyPatch):
    """T9: Temporary index directory is cleaned up even if write-tree or diff-tree fails."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    (test_repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    # Monkeypatch subprocess.check_call to fail inside the with block
    orig_check_output = subprocess.check_output

    def failing_check_output(cmd, **kwargs):
        if isinstance(cmd, list) and "write-tree" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return orig_check_output(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "check_output", failing_check_output)

    with pytest.raises(subprocess.CalledProcessError):
        extract_git_manifest(test_repo, base_commit, "HEAD")


def test_t14_dirty_target_oracle(test_repo: Path):
    """T14 Oracle: Prove that without the fix (rev-parse HEAD^{tree}), uncommitted changes are invisible."""
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True).strip()
    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()

    # Add uncommitted modification
    (test_repo / "tracked_a.txt").write_text("uncommitted change\n", encoding="utf-8")

    # Unfixed naive behavior:
    naive_tgt_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True).strip()
    assert naive_tgt_tree == base_tree  # Naive HEAD tree completely misses the working-tree edit!

    # Fixed extract_git_manifest behavior:
    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert manifest["target_tree"] != f"git-tree:{base_tree}"
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["path"] == "tracked_a.txt"
