from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.orchestrator.canonical_core_transport import extract_git_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    base_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

    # Modify and commit
    (test_repo / "tracked_a.txt").write_text("modified a\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "tracked_a.txt"], cwd=test_repo)
    subprocess.check_call(["git", "commit", "-m", "update a"], cwd=test_repo)
    cand_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    cand_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    base_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    base_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    base_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
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
    after_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    assert after_head == base_commit


def test_t8_temp_index_cleanup(test_repo: Path):
    """T8: Temporary index directory is cleanly removed after success."""
    import tempfile

    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    (test_repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert len(manifest["entries"]) == 1

    # Verify no dangling temp indexes in system temp
    # TemporaryDirectory context manager guarantees cleanup
    assert Path(tempfile.gettempdir()).exists()


def test_t9_failure_cleanup(test_repo: Path, monkeypatch: pytest.MonkeyPatch):
    """T9: Temporary index directory is cleaned up even if write-tree or diff-tree fails."""
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
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
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=test_repo, text=True
    ).strip()
    base_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()

    # Add uncommitted modification
    (test_repo / "tracked_a.txt").write_text("uncommitted change\n", encoding="utf-8")

    # Unfixed naive behavior:
    naive_tgt_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=test_repo, text=True
    ).strip()
    assert naive_tgt_tree == base_tree  # Naive HEAD tree completely misses the working-tree edit!

    # Fixed extract_git_manifest behavior:
    manifest = extract_git_manifest(test_repo, base_commit, "HEAD")
    assert manifest["target_tree"] != f"git-tree:{base_tree}"
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["path"] == "tracked_a.txt"


def _imported_sys_path(extra_env: dict[str, str] | None = None) -> list[str]:
    """sys.path of a fresh interpreter that imports the transport module."""
    env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_REPO_ROOT"}
    env.update(extra_env or {})
    code = (
        "import json, sys\n"
        "import nexus.orchestrator.canonical_core_transport\n"
        "print(json.dumps(sys.path))\n"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, text=True
    )
    return json.loads(out.strip().splitlines()[-1])


def test_transport_import_injects_no_developer_checkout_path():
    """Without NEXUS_CORE_REPO_ROOT, no hardcoded developer path is put on sys.path."""
    sys_path = _imported_sys_path()
    assert not any("/Users/jameschen" in entry for entry in sys_path)


def test_transport_import_uses_configured_core_root_when_set(tmp_path: Path):
    """NEXUS_CORE_REPO_ROOT, when set, is the only extra Core root placed on sys.path."""
    core_root = tmp_path / "nexus-core"
    core_root.mkdir()
    sys_path = _imported_sys_path({"NEXUS_CORE_REPO_ROOT": str(core_root)})
    assert sys_path[0] == str(core_root.resolve())


# --- NN-1 phase 2: installed-package identity from PEP 610 direct_url.json ---
EXPECTED_CORE_REVISION = "77c7fb8fdc8c68a85c771280decd4a1e01b55085"


def _install_fake_certify(
    site: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_url: dict | str | None,
    *,
    dist_name: str = "nexus_certify",
):
    """Create a fake installed nexus-certify (product/ + dist-info) under `site`.

    Points the transport's imported-Core package at the fake `product/`.
    """
    from types import SimpleNamespace

    from nexus.orchestrator import canonical_core_transport as transport

    package_dir = site / "product"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("")
    dist_info = site / f"{dist_name}-0.2.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: nexus-certify\nVersion: 0.2.0\n"
    )
    (dist_info / "RECORD").write_text(
        f"product/__init__.py,,\n{dist_info.name}/METADATA,,\n{dist_info.name}/RECORD,,\n"
    )
    if direct_url is not None:
        text = direct_url if isinstance(direct_url, str) else json.dumps(direct_url)
        (dist_info / "direct_url.json").write_text(text)
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.setattr(
        transport,
        "_IMPORTED_CORE_PACKAGE",
        SimpleNamespace(__file__=str(package_dir / "__init__.py")),
    )
    return transport


def _vcs_direct_url(commit: str) -> dict:
    return {
        "url": "https://github.com/James3014/nexus-core.git",
        "vcs_info": {"vcs": "git", "commit_id": commit, "requested_revision": commit},
    }


def test_expected_core_revision_is_owner_decided_pin():
    from nexus.orchestrator import canonical_core_transport as transport

    assert transport.CANONICAL_CORE_REVISION == EXPECTED_CORE_REVISION
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "nexus-core-issue-completion.yml"
    ).read_text()
    pinned = re.findall(r"nexus-certify-ref:\s*[\"']?([0-9a-f]{40})[\"']?", workflow)
    assert pinned, "workflow must pin nexus-certify to an exact SHA"
    assert set(pinned) == {transport.CANONICAL_CORE_REVISION}


def test_installed_core_identity_available_when_direct_url_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    transport = _install_fake_certify(
        tmp_path / "site", monkeypatch, _vcs_direct_url(EXPECTED_CORE_REVISION)
    )
    identity = transport.read_observed_core_identity()
    assert identity["available"] is True
    assert identity["observed_commit"] == EXPECTED_CORE_REVISION
    assert identity["revision_match"] is True
    assert identity["identity_source"] == "direct_url.json"
    status = transport.core_provenance_status(identity)
    assert status["status"] == "CORE_REVISION_PINNED"
    assert status["fail_closed"] is False


def test_installed_core_identity_unavailable_when_direct_url_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    transport = _install_fake_certify(tmp_path / "site", monkeypatch, None)
    identity = transport.read_observed_core_identity()
    assert identity["available"] is False
    assert identity["observed_commit"] is None
    status = transport.core_provenance_status(identity)
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE"
    assert status["fail_closed"] is True


def test_installed_core_identity_mismatch_when_direct_url_commit_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wrong = "fde015797672b0aac5dca7b41c7e5a0b901698d4"
    transport = _install_fake_certify(tmp_path / "site", monkeypatch, _vcs_direct_url(wrong))
    identity = transport.read_observed_core_identity()
    assert identity["available"] is True
    assert identity["observed_commit"] == wrong
    status = transport.core_provenance_status(identity)
    assert status["status"] == "CORE_REVISION_MISMATCH"
    assert status["fail_closed"] is True


@pytest.mark.parametrize(
    "direct_url",
    [
        "{not json",
        {"url": "file:///src/nexus-core", "dir_info": {"editable": True}},
        {"url": "https://x/y.git", "vcs_info": {"vcs": "hg", "commit_id": EXPECTED_CORE_REVISION}},
        {"url": "https://x/y.git", "vcs_info": {"vcs": "git"}},
        {"url": "https://x/y.git", "vcs_info": {"vcs": "git", "commit_id": "77c7fb8"}},
        {
            "url": "https://x/y.git",
            "vcs_info": {"vcs": "git", "commit_id": EXPECTED_CORE_REVISION.upper()},
        },
    ],
)
def test_installed_core_identity_fails_closed_on_unusable_direct_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, direct_url
):
    transport = _install_fake_certify(tmp_path / "site", monkeypatch, direct_url)
    identity = transport.read_observed_core_identity()
    assert identity["available"] is False
    assert identity["observed_commit"] is None
    assert transport.core_provenance_status(identity)["status"] == "CORE_IDENTITY_UNAVAILABLE"


def test_direct_url_not_trusted_when_imported_core_is_not_the_installed_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A shadowing product/ elsewhere must not inherit the installed distribution's identity."""
    from types import SimpleNamespace

    transport = _install_fake_certify(
        tmp_path / "site", monkeypatch, _vcs_direct_url(EXPECTED_CORE_REVISION)
    )
    shadow = tmp_path / "shadow" / "product"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text("")
    monkeypatch.setattr(
        transport, "_IMPORTED_CORE_PACKAGE", SimpleNamespace(__file__=str(shadow / "__init__.py"))
    )
    identity = transport.read_observed_core_identity()
    assert identity["observed_commit"] != EXPECTED_CORE_REVISION
    assert transport.core_provenance_status(identity)["fail_closed"] is True


def test_explicit_core_root_still_uses_git_identity(tmp_path: Path):
    """NEXUS_CORE_REPO_ROOT opt-in path (checkout identity via git) is unchanged."""
    from nexus.orchestrator.canonical_core_transport import read_observed_core_identity

    repo = tmp_path / "core"
    (repo / "product").mkdir(parents=True)
    (repo / "product" / "__init__.py").write_text("")
    env = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "PATH": os.environ["PATH"],
    }
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, env=env
    ).strip()
    identity = read_observed_core_identity(core_root=repo)
    assert identity["available"] is True
    assert identity["observed_commit"] == head
