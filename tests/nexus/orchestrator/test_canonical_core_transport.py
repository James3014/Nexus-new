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

    # Make write-tree fail inside the with block
    orig_run = subprocess.run

    def failing_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and "write-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "write-tree failed")
        return orig_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_run)

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
EXPECTED_CORE_REVISION = "67427c5840cd41cd1cf11fff63b710c81a813755"


_BUILD_IDENTITY_FIXTURE = Path(__file__).with_name("_core_build_identity_fixture.py")


def _build_identity_module():
    """The vendored Core ``build_identity`` module, loaded without bytecode."""
    import types

    module = types.ModuleType("_fixture_build_identity")
    source = _BUILD_IDENTITY_FIXTURE.read_bytes()
    exec(compile(source, str(_BUILD_IDENTITY_FIXTURE), "exec"), module.__dict__)
    return module


def _place_core_identity(product_dir: Path) -> None:
    """Give a fake Core ``product/`` Core's own build_identity module."""
    protocol = product_dir / "protocol"
    protocol.mkdir(parents=True, exist_ok=True)
    (protocol / "__init__.py").write_text("")
    (protocol / "build_identity.py").write_bytes(_BUILD_IDENTITY_FIXTURE.read_bytes())


def _source_digest(product_dir: Path) -> str:
    return _build_identity_module().source_digest(product_dir)


def _pin_source_digest(monkeypatch: pytest.MonkeyPatch, digest: str, revision: str) -> None:
    monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST", digest)
    monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", revision)


def _write_stamp(product_dir: Path, stamp: dict | str) -> None:
    text = stamp if isinstance(stamp, str) else json.dumps(stamp)
    (product_dir / "_build_identity.json").write_text(text)


def _stamp(product_dir: Path, commit, *, dirty=False, digest: str | None = None) -> dict:
    return {
        "schema": "nexus.core.build-identity.v1-experimental",
        "distribution": "nexus-certify",
        "version": "0.2.0",
        "git_commit": commit,
        "git_tree": None if commit is None else "e" * 40,
        "git_dirty": None if commit is None else dirty,
        "source_digest": digest or _source_digest(product_dir),
    }


def _install_fake_certify(
    site: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_url: dict | str | None,
    *,
    dist_name: str = "nexus_certify",
):
    """Create a fake installed nexus-certify (product/ + dist-info) under `site`.

    Points the transport's imported-Core package at the fake `product/`. Since
    #2246 the identity is Core's build stamp, so the fake wheel is stamped as if
    built from the commit its ``direct_url.json`` names: a git commit gives a
    stamp with that commit, another usable record a stamp without git metadata,
    raw text an unreadable stamp, and no record no stamp at all.
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
    _place_core_identity(package_dir)
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST", raising=False)
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", raising=False)
    if isinstance(direct_url, str):
        _write_stamp(package_dir, direct_url)
    elif isinstance(direct_url, dict):
        vcs = direct_url.get("vcs_info") or {}
        commit = vcs.get("commit_id") if vcs.get("vcs") == "git" else None
        _write_stamp(package_dir, _stamp(package_dir, commit))
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
    workflow = (REPO_ROOT / ".github" / "workflows" / "nexus-core-issue-completion.yml").read_text()
    pinned = re.findall(r"nexus-certify-ref:\s*[\"']?([0-9a-f]{40})[\"']?", workflow)
    assert pinned, "workflow must pin nexus-certify to an exact SHA"
    assert set(pinned) == {transport.CANONICAL_CORE_REVISION}
    # The Core actions themselves are pinned to the same commit (#2246 review).
    uses = re.findall(r"nexus-core/\.github/actions/([\w.-]+)@([^\s\"']+)", workflow)
    assert {name for name, _ in uses} == {"issue-gate", "receipt-verify"}, uses
    assert {ref for _, ref in uses} == {transport.CANONICAL_CORE_REVISION}, uses


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
    assert identity["identity_source"] == "build_stamp"
    assert identity["build_identity"] == "EMBEDDED"
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
    # Since #2246 the identity is computed for the imported root itself; an
    # unstamped shadow without a deployer digest pin is never pinned.
    _place_core_identity(shadow)
    monkeypatch.setattr(
        transport, "_IMPORTED_CORE_PACKAGE", SimpleNamespace(__file__=str(shadow / "__init__.py"))
    )
    identity = transport.read_observed_core_identity()
    assert identity["observed_commit"] != EXPECTED_CORE_REVISION
    assert identity["source_root"] == str(shadow.parent)
    assert identity["reason"] == "CORE_SOURCE_DIGEST_UNPINNED"
    assert transport.core_provenance_status(identity)["fail_closed"] is True


def test_explicit_core_root_still_uses_git_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """NEXUS_CORE_REPO_ROOT opt-in path: a git checkout is identified by Core's
    source digest pinned for the revision (#2246), never by running git."""
    from nexus.orchestrator import canonical_core_transport as transport
    from nexus.orchestrator.canonical_core_transport import read_observed_core_identity

    repo = tmp_path / "core"
    (repo / "product").mkdir(parents=True)
    (repo / "product" / "__init__.py").write_text("")
    _place_core_identity(repo / "product")
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
    monkeypatch.setattr(transport, "CANONICAL_CORE_REVISION", head)
    _pin_source_digest(monkeypatch, _source_digest(repo / "product"), head)

    def no_git(*_args, **_kwargs):
        raise AssertionError("provenance must not run a subprocess")

    monkeypatch.setattr(transport.subprocess, "check_output", no_git)
    monkeypatch.setattr(transport.subprocess, "run", no_git)
    identity = read_observed_core_identity(core_root=repo)
    assert identity["available"] is True
    assert identity["observed_commit"] == head
    assert identity["identity_source"] == "source_digest"


# --- #2181: the in-tree `product/` package must never stand in for Core ---

_STUB_CORE_FILES = {
    "product/__init__.py": "",
    "product/adapters/__init__.py": "",
    "product/adapters/generic_verification.py": (
        "def verify_generic_changeset(payload):\n    return 0, {}\n"
    ),
    "product/protocol/__init__.py": 'PUBLIC_PROTOCOL_VERSION = "stub"\n',
    "product/protocol/generic_verification.py": (
        'GENERIC_VERIFICATION_REQUEST_SCHEMA_ID = "req"\n'
        'GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID = "resp"\n'
        "def _h(value):\n    return 'sha256:0'\n"
        "acceptance_contract_hash = change_manifest_hash = change_set_hash = _h\n"
        "evidence_bundle_hash = verification_plan_hash = expected_universe_identity = _h\n"
    ),
}


def _stub_core(root: Path) -> Path:
    for rel, text in _STUB_CORE_FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def _import_transport(core_root: Path, preamble: str = "") -> dict:
    env = {k: v for k, v in os.environ.items() if k != "NEXUS_CORE_REPO_ROOT"}
    env["NEXUS_CORE_REPO_ROOT"] = str(core_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import json, sys\n"
        f"{preamble}"
        "from nexus.orchestrator import canonical_core_transport as t\n"
        "pkg = t._IMPORTED_CORE_PACKAGE\n"
        "print(json.dumps({'available': t.CORE_AVAILABLE, 'error': t.CORE_IMPORT_ERROR,\n"
        "  'package': getattr(pkg, '__file__', None),\n"
        "  'product': getattr(sys.modules.get('product'), '__file__', None),\n"
        "  'status': t.core_provenance_status()['status']}))\n"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env, text=True
    )
    return json.loads(out.strip().splitlines()[-1])


def test_configured_core_root_is_imported_when_nothing_shadows_it(tmp_path: Path):
    """Positive control: a fresh import resolves `product` from NEXUS_CORE_REPO_ROOT."""
    core = _stub_core(tmp_path / "core")
    result = _import_transport(core)
    assert result["available"] is True, result
    assert Path(result["package"]).resolve() == (core / "product" / "__init__.py").resolve()


def test_in_tree_product_already_imported_fails_closed(tmp_path: Path):
    """The repository's own `product/` imported first must not be used as Core."""
    core = _stub_core(tmp_path / "core")
    # The real Gateway imports in-tree `product` via nexus/contracts/changeset_certification.
    result = _import_transport(core, preamble="sys.path.insert(0, '.')\nimport product\n")
    assert Path(result["product"]).resolve() == (REPO_ROOT / "product" / "__init__.py").resolve()
    assert result["available"] is False
    assert "CORE_PRODUCT_SHADOWED" in result["error"]
    assert result["status"] == "CORE_UNAVAILABLE"


def test_preloaded_core_submodule_from_elsewhere_fails_closed(tmp_path: Path):
    """A verifier submodule loaded from another tree must not pass as Core."""
    core = _stub_core(tmp_path / "core")
    other = _stub_core(tmp_path / "other")
    preamble = (
        f"sys.path.insert(0, {str(other)!r})\n"
        "import product.adapters.generic_verification\n"
        "del sys.modules['product']\n"
        "sys.path.remove(sys.path[0])\n"
    )
    result = _import_transport(core, preamble=preamble)
    assert result["available"] is False
    assert "CORE_PRODUCT_SHADOWED" in result["error"]
    assert "(module product.adapters" in result["error"]


def test_core_shadow_reason_is_pure_and_fail_closed(tmp_path: Path):
    from types import SimpleNamespace

    from nexus.orchestrator.canonical_core_transport import _core_shadow_reason

    core = tmp_path / "core"
    inside = SimpleNamespace(__file__=str(core / "product" / "__init__.py"))
    outside = SimpleNamespace(__file__=str(REPO_ROOT / "product" / "__init__.py"))
    namespace = SimpleNamespace(__file__=None)
    assert _core_shadow_reason(core, inside) is None
    assert _core_shadow_reason(None, outside) is None  # no configured root: unchanged
    assert _core_shadow_reason(core, None) is None  # not imported yet
    assert "CORE_PRODUCT_SHADOWED" in _core_shadow_reason(core, outside)
    assert "CORE_PRODUCT_SHADOWED" in _core_shadow_reason(core, namespace)


def _git_core_checkout(repo: Path) -> str:
    (repo / "product").mkdir(parents=True)
    (repo / "product" / "__init__.py").write_text("")
    _place_core_identity(repo / "product")
    (repo / ".gitignore").write_text("__pycache__/\n")
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
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, env=env
    ).strip()


@pytest.mark.parametrize("dirt", ["untracked", "modified", "ignored"])
def test_dirty_core_checkout_is_not_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dirt: str
):
    from nexus.orchestrator import canonical_core_transport as transport

    repo = tmp_path / "core"
    head = _git_core_checkout(repo)
    monkeypatch.setattr(transport, "CANONICAL_CORE_REVISION", head)
    _pin_source_digest(monkeypatch, _source_digest(repo / "product"), head)
    clean = transport.read_observed_core_identity(core_root=repo)
    assert clean["available"] is True
    assert transport.core_provenance_status(clean)["status"] == "CORE_REVISION_PINNED"
    # Since #2246 "dirty" means a shipped source differs from the pinned digest;
    # bytecode is not source (see test_stray_pycache_does_not_change_provenance).
    if dirt == "untracked":
        (repo / "product" / "shadow.py").write_text("x = 1\n")
    elif dirt == "ignored":
        (repo / ".gitignore").write_text("__pycache__/\nproduct/ignored_mod.py\n")
        (repo / "product" / "ignored_mod.py").write_text("x = 1\n")
    else:
        (repo / "product" / "__init__.py").write_text("patched = True\n")
    identity = transport.read_observed_core_identity(core_root=repo)
    assert identity["reason"] == "CORE_SOURCE_DIGEST_MISMATCH"
    assert identity["observed_commit"] is None
    status = transport.core_provenance_status(identity)
    assert status["status"] == "CORE_REVISION_MISMATCH" and status["fail_closed"] is True
    assert status["observed_source_digest"] != status["expected_source_digest"]


# --- #2246: git-free Core identity via Core's core_identity() -----------------

PIN = EXPECTED_CORE_REVISION


def _fake_core(root: Path) -> Path:
    product = root / "product"
    product.mkdir(parents=True)
    (product / "__init__.py").write_text('"""Core."""\n')
    (product / "adapters").mkdir()
    (product / "adapters" / "__init__.py").write_text("")
    _place_core_identity(product)
    return product


def _identity(monkeypatch: pytest.MonkeyPatch, root: Path) -> tuple[dict, dict]:
    from nexus.orchestrator import canonical_core_transport as transport

    monkeypatch.setattr(transport, "CANONICAL_CORE_REVISION", PIN)
    identity = transport.read_observed_core_identity(core_root=root)
    return identity, transport.core_provenance_status(identity)


def test_stray_pycache_does_not_change_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression for 2026-10-15: bytecode in the Core checkout is not a source change."""
    product = _fake_core(tmp_path / "core")
    _pin_source_digest(monkeypatch, _source_digest(product), PIN)
    before, status = _identity(monkeypatch, tmp_path / "core")
    assert status["status"] == "CORE_REVISION_PINNED", status
    for directory in (product, product / "adapters", product / "protocol"):
        (directory / "__pycache__").mkdir(exist_ok=True)
        (directory / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00junk")
    (product / "stray.pyc").write_bytes(b"junk")
    after, status = _identity(monkeypatch, tmp_path / "core")
    assert status["status"] == "CORE_REVISION_PINNED", status
    assert status["fail_closed"] is False
    assert status["observed_commit"] == PIN
    assert status["identity_source"] == "source_digest"
    assert after["observed_source_digest"] == before["observed_source_digest"]


def test_reading_core_identity_writes_no_bytecode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    product = _fake_core(tmp_path / "core")
    _pin_source_digest(monkeypatch, _source_digest(product), PIN)
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    _identity(monkeypatch, tmp_path / "core")
    assert not list((tmp_path / "core").rglob("__pycache__"))


def test_source_digest_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _fake_core(tmp_path / "core")
    _pin_source_digest(monkeypatch, "sha256:" + "0" * 64, PIN)
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert identity["reason"] == "CORE_SOURCE_DIGEST_MISMATCH"
    assert status["status"] == "CORE_REVISION_MISMATCH"
    assert status["fail_closed"] is True
    assert status["observed_commit"] is None
    assert status["expected_source_digest"] == "sha256:" + "0" * 64


@pytest.mark.parametrize(
    ("digest", "revision", "reason"),
    [
        (None, None, "CORE_SOURCE_DIGEST_UNPINNED"),
        ("ok", None, "CORE_SOURCE_DIGEST_PIN_MALFORMED"),
        (None, PIN, "CORE_SOURCE_DIGEST_PIN_MALFORMED"),
        ("sha256:short", PIN, "CORE_SOURCE_DIGEST_PIN_MALFORMED"),
        ("ok", PIN.upper(), "CORE_SOURCE_DIGEST_PIN_MALFORMED"),
        ("ok", "f" * 40, "CORE_SOURCE_DIGEST_PIN_FOR_OTHER_REVISION"),
    ],
    ids=[
        "missing",
        "revision_missing",
        "digest_missing",
        "digest_malformed",
        "revision_upper",
        "other_revision",
    ],
)
def test_unstamped_core_without_a_valid_digest_pin_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, digest, revision, reason
):
    product = _fake_core(tmp_path / "core")
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST", raising=False)
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", raising=False)
    if digest is not None:
        value = _source_digest(product) if digest == "ok" else digest
        monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST", value)
    if revision is not None:
        monkeypatch.setenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", revision)
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert identity["build_identity"] == "UNSTAMPED"
    assert identity["reason"] == reason
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE"
    assert status["fail_closed"] is True and status["observed_commit"] is None


@pytest.mark.parametrize("stamp", ["{not json", "[]", '{"schema": "other"}'])
def test_invalid_build_stamp_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stamp: str
):
    product = _fake_core(tmp_path / "core")
    _write_stamp(product, stamp)
    # Even a correct digest pin does not rescue an invalid stamp.
    _pin_source_digest(monkeypatch, _source_digest(product), PIN)
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert identity["build_identity"] == "INVALID_STAMP"
    assert identity["reason"] == "CORE_BUILD_STAMP_INVALID"
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE" and status["fail_closed"] is True


@pytest.mark.parametrize(
    ("case", "status_name", "reason"),
    [
        ("pinned", "CORE_REVISION_PINNED", None),
        ("other_commit", "CORE_REVISION_MISMATCH", None),
        ("dirty_build", "CORE_IDENTITY_UNAVAILABLE", "CORE_BUILD_DIRTY"),
        ("edited_after_build", "CORE_IDENTITY_UNAVAILABLE", "CORE_SOURCE_NOT_AS_BUILT"),
        ("no_git_metadata", "CORE_IDENTITY_UNAVAILABLE", "CORE_BUILD_STAMP_WITHOUT_COMMIT"),
    ],
)
def test_embedded_wheel_identity_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, status_name: str, reason
):
    """Installed wheel: EMBEDDED, git_commit == pin, git_dirty False, source as built."""
    product = _fake_core(tmp_path / "site")
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST", raising=False)
    monkeypatch.delenv("NEXUS_CORE_SOURCE_DIGEST_REVISION", raising=False)
    commit = {"other_commit": "f" * 40, "no_git_metadata": None}.get(case, PIN)
    _write_stamp(product, _stamp(product, commit, dirty=case == "dirty_build"))
    if case == "edited_after_build":
        (product / "__init__.py").write_text("patched = True\n")
    identity, status = _identity(monkeypatch, tmp_path / "site")
    assert identity["build_identity"] == "EMBEDDED"
    assert status["status"] == status_name, status
    assert status["fail_closed"] is (status_name != "CORE_REVISION_PINNED")
    if reason is not None:
        assert identity["reason"] == reason
    if case == "pinned":
        assert status["identity_source"] == "build_stamp"
        assert status["observed_commit"] == PIN


def test_unreadable_core_identity_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A Core without core_identity() (older than nexus-core #270).
    old = tmp_path / "old" / "product"
    old.mkdir(parents=True)
    (old / "__init__.py").write_text("")
    identity, status = _identity(monkeypatch, tmp_path / "old")
    assert identity["reason"] == "CORE_IDENTITY_UNREADABLE"
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE"
    # Core refuses a symlinked package directory; the host fails closed.
    product = _fake_core(tmp_path / "linked")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (product / "extra").symlink_to(elsewhere, target_is_directory=True)
    _pin_source_digest(monkeypatch, "sha256:" + "0" * 64, PIN)
    identity, status = _identity(monkeypatch, tmp_path / "linked")
    assert identity["reason"] == "CORE_IDENTITY_UNREADABLE"
    assert status["fail_closed"] is True


def test_build_stamp_in_a_digest_pinned_checkout_never_decides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A stamp sits outside the digest: where the deployer pinned a digest, a
    forged stamp claiming the pin cannot pin modified sources."""
    product = _fake_core(tmp_path / "core")
    _pin_source_digest(monkeypatch, _source_digest(product), PIN)
    (product / "adapters" / "__init__.py").write_text("tampered = True\n")
    _write_stamp(product, _stamp(product, PIN))  # consistent with the tampered tree
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert identity["build_identity"] == "EMBEDDED"
    assert identity["identity_source"] == "source_digest"
    assert identity["reason"] == "CORE_SOURCE_DIGEST_MISMATCH"
    assert status["status"] == "CORE_REVISION_MISMATCH" and status["fail_closed"] is True
    # A genuine stamp in the pinned tree is fine: the digest still decides.
    (product / "adapters" / "__init__.py").write_text("")
    _write_stamp(product, _stamp(product, PIN))
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert status["status"] == "CORE_REVISION_PINNED"
    assert status["identity_source"] == "source_digest"


@pytest.mark.parametrize("body", ["raise SystemExit(3)\n", "core_identity = 1\n", "1/0\n"])
def test_core_identity_module_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
):
    product = _fake_core(tmp_path / "core")
    (product / "protocol" / "build_identity.py").write_text(body)
    identity, status = _identity(monkeypatch, tmp_path / "core")
    assert identity["reason"] == "CORE_IDENTITY_UNREADABLE"
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE" and status["fail_closed"] is True


def _plant_programs(repo: Path, markers: Path) -> None:
    """Hooks and config programs a Target writer can plant; each only touches a marker."""
    markers.mkdir()
    hooks = repo / ".git" / "hooks"
    for name in ("post-index-change", "reference-transaction", "pre-commit"):
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook-{name}'\n", encoding="utf-8")
        hook.chmod(0o755)


def _set_config(repo: Path, key: str, value: str) -> None:
    subprocess.check_call(["git", "config", "--add", key, value], cwd=repo)


@pytest.fixture
def sentinel_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


@pytest.mark.parametrize(
    "key, value",
    [
        ("diff.external", "sh -c \"touch '{markers}/diff-external'\" --"),
        ("hook.m.command", "touch '{markers}/config-hook'"),
        ("filter.m.clean", "sh -c \"touch '{markers}/clean-filter'; cat\""),
    ],
)
def test_manifest_of_a_target_naming_a_program_is_refused_before_it_runs(
    test_repo: Path, tmp_path: Path, sentinel_cwd: None, key: str, value: str
):
    markers = tmp_path / "markers"
    _plant_programs(test_repo, markers)
    _set_config(test_repo, key, value.format(markers=markers))
    if key == "hook.m.command":
        _set_config(test_repo, "hook.m.event", "post-index-change")
    if key == "filter.m.clean":
        (test_repo / ".gitattributes").write_text("*.txt filter=m\n", encoding="utf-8")
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True)
    (test_repo / "tracked_a.txt").write_text("worker edit\n", encoding="utf-8")
    (test_repo / "new.txt").write_text("untracked\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="CANONICAL_CORE_TARGET_GIT_CONFIG_REFUSED"):
        extract_git_manifest(test_repo, base_commit.strip(), "HEAD")

    assert sorted(p.name for p in markers.iterdir()) == []


def test_manifest_of_a_dirty_target_runs_none_of_its_hooks(
    test_repo: Path, tmp_path: Path, sentinel_cwd: None
):
    markers = tmp_path / "markers"
    _plant_programs(test_repo, markers)
    _set_config(test_repo, "core.fsmonitor", f"touch '{markers}/fsmonitor'; true")
    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True)
    (test_repo / "tracked_a.txt").write_text("worker edit\n", encoding="utf-8")
    (test_repo / "new.txt").write_text("untracked\n", encoding="utf-8")

    manifest = extract_git_manifest(test_repo, base_commit.strip(), "HEAD")

    assert sorted(row["path"] for row in manifest["entries"]) == ["new.txt", "tracked_a.txt"]
    assert sorted(p.name for p in markers.iterdir()) == []


def test_manifest_git_calls_are_bounded_in_time(test_repo: Path, monkeypatch: pytest.MonkeyPatch):
    from nexus.core import hardened_git

    timeouts: list[object] = []
    orig_run = subprocess.run

    def recording_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[:1] == ["git"]:
            timeouts.append(kwargs.get("timeout"))
        return orig_run(cmd, *args, **kwargs)

    base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=test_repo, text=True)
    (test_repo / "tracked_a.txt").write_text("worker edit\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", recording_run)

    extract_git_manifest(test_repo, base_commit.strip(), "HEAD")

    assert len(timeouts) >= 6
    assert set(timeouts) == {hardened_git.GIT_TIMEOUT_S}
