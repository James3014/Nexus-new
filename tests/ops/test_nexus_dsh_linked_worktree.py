"""Issue #1607: DSH outer bash inside a linked Git worktree.

DSH ``workspace-write`` grants writes only under the session cwd plus the host
temp areas. A linked worktree keeps its index/lock under the parent repository's
common Git dir, so exact-worktree Git metadata operations are physically denied.
The supported contract is an explicit standalone clone (real ``.git`` directory
inside the workspace) under a non-temp root; linked worktrees, temp-root layouts
and ambiguous Git identity fail closed before DSH is spawned.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_linked_worktree_test", str(SCRIPT)).load_module()
REPO = "James3014/Nexus-new"
ORIGIN = "https://github.com/James3014/Nexus-new.git"
LINKED = "DSH_LINKED_WORKTREE_GIT_METADATA_OUTSIDE_WORKSPACE"
UNDER_TEMP = "DSH_WORKSPACE_UNDER_DSH_TEMP_GRANT"
GIT_IDENTITY_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)

needs_seatbelt = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("sandbox-exec") is None,
    reason="physical DSH Seatbelt confinement witness requires macOS sandbox-exec",
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in GIT_IDENTITY_ENV:
        env.pop(key, None)
    return env


def _layout(base: Path, *, sibling_root: Path | None = None) -> dict[str, Path | str]:
    """Parent checkout + two linked worktrees, mirroring the #1599 witness."""
    main = base / "Nexus-new"
    main.mkdir()
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["remote", "add", "origin", ORIGIN],
    ):
        _git(main, *cmd)
    (main / "mod.py").write_text("value = 1\n", encoding="utf-8")
    (main / "secret.py").write_text("parent = 1\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", "base")
    base_rev = _git(main, "rev-parse", "HEAD").stdout.strip()
    active = base / "wt-active"
    sibling = (sibling_root or base) / "wt-sibling"
    _git(main, "worktree", "add", "-q", "--detach", str(active), base_rev)
    _git(main, "worktree", "add", "-q", "--detach", str(sibling), base_rev)
    return {"main": main, "active": active, "sibling": sibling, "base": base_rev}


def _workspace_write_profile(workspace: Path) -> str:
    # DSH 0.2.0-rc.2 ``seatbeltProfileArgs`` for workspace-write: the workspace
    # plus the host temp grants (``writableRoots``), canonicalized.
    roots = [workspace.resolve(), *guard.dsh_temp_write_roots()]
    grants = " ".join(f'(subpath "{root}")' for root in dict.fromkeys(roots))
    return (
        "(version 1) (allow default) (deny file-write*) "
        '(allow file-write* (literal "/dev/null")) '
        f"(allow file-write* {grants})"
    )


def _sandboxed(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sandbox-exec", "-p", _workspace_write_profile(workspace), *argv],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
        env=_clean_env(),
    )


def _prepare(source: Path, target: Path, base: str, *, repository: str = REPO):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "prepare-standalone",
            "--repository",
            repository,
            "--source-repo-root",
            str(source),
            "--base-revision",
            base,
            "--target",
            str(target),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=_clean_env(),
    )


def _last_json(proc: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _blocked_code(proc: subprocess.CompletedProcess[str]) -> str:
    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    return _last_json(proc)["reason_code"]


def _phase_fixture(tmp_path: Path) -> dict[str, Path]:
    doctor = tmp_path / "doctor"
    payload = {
        "schema": guard.DOCTOR_SCHEMA,
        "claim_ceiling": guard.DOCTOR_CLAIM_CEILING,
        "resume_disposition": "SAFE",
        "next_gate": {"code": "CONTINUE_BOUNDED_ISSUE_WORK"},
        "source": {"status": "OBSERVED", "head": "a" * 40, "github_main": "b" * 40},
        "task": {
            "status": "OBSERVED",
            "state": "open",
            "issue_number": 1607,
            "updated_at": "2026-10-10T00:00:00Z",
            "url": "https://example.invalid/1607",
        },
    }
    doctor.write_text(
        f"#!/usr/bin/env python3\nimport json\nprint(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )
    doctor.chmod(0o755)
    dsh = tmp_path / "dsh"
    dsh.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\n"
        "Path(os.environ['FAKE_DSH_MARKER']).write_text(json.dumps(sys.argv[1:]))\n"
        "print(json.dumps({'type': 'session', 'sessionId': 'session-1607', "
        "'cwd': os.getcwd()}))\n",
        encoding="utf-8",
    )
    dsh.chmod(0o755)
    contract = tmp_path / "contract.md"
    contract.write_text("CONTRACT allowed: mod.py\n", encoding="utf-8")
    home = tmp_path / "dsh-home"
    home.mkdir()
    return {
        "doctor": doctor,
        "dsh": dsh,
        "contract": contract,
        "home": home,
        "state": tmp_path / "state",
        "marker": tmp_path / "dsh-spawned.json",
    }


def _start_phase(ctx: dict[str, Path], repo_root: Path, env: dict[str, str] | None = None):
    full = _clean_env()
    full["FAKE_DSH_MARKER"] = str(ctx["marker"])
    full.update(env or {})
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start-phase",
            "--repository",
            REPO,
            "--issue",
            "1607",
            "--phase",
            "green",
            "--repo-root",
            str(repo_root),
            "--dsh-home",
            str(ctx["home"]),
            "--phase-contract",
            str(ctx["contract"]),
            "--state-root",
            str(ctx["state"]),
            "--doctor-bin",
            str(ctx["doctor"]),
            "--dsh-bin",
            str(ctx["dsh"]),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=full,
    )


def test_dsh_temp_write_roots_cover_tmp_and_node_tmpdir(tmp_path: Path) -> None:
    roots = guard.dsh_temp_write_roots({"TMPDIR": str(tmp_path) + "/"})
    assert Path("/tmp").resolve() in roots
    assert tmp_path.resolve() in roots
    assert Path(tempfile.gettempdir()).resolve() in roots


@needs_seatbelt
def test_linked_worktree_git_restore_is_physically_denied_under_workspace_write(
    dsh_non_temp_path: Path,
) -> None:
    lay = _layout(dsh_non_temp_path)
    active = Path(lay["active"])
    (active / "mod.py").write_text("value = 2\n", encoding="utf-8")

    restore = _sandboxed(active, "git", "checkout", "--", "mod.py")

    assert restore.returncode != 0
    assert "index.lock" in restore.stderr
    assert "Operation not permitted" in restore.stderr
    assert (active / "mod.py").read_text(encoding="utf-8") == "value = 2\n"


def test_start_phase_blocks_linked_worktree_before_spawning_dsh(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    ctx = _phase_fixture(tmp_path)

    proc = _start_phase(ctx, Path(lay["active"]))

    assert _blocked_code(proc) == LINKED
    assert not ctx["marker"].exists()
    receipt = _last_json(proc)
    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["provider_invocation_allowed"] is False
    assert "prepare-standalone" in receipt["detail"]

    temp_family = tmp_path / "temp-family"
    temp_family.mkdir()
    temp_lay = _layout(temp_family)
    assert _blocked_code(_start_phase(ctx, Path(temp_lay["active"]))) == LINKED
    assert not ctx["marker"].exists()


def test_resume_blocks_linked_worktree_before_spawning_dsh(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    ctx = _phase_fixture(tmp_path)
    log = tmp_path / "phase.log"
    log.write_text(
        json.dumps({"type": "session", "sessionId": "session-1607", "cwd": str(lay["active"])})
        + "\n",
        encoding="utf-8",
    )
    binding = guard.build_binding_from_log(
        log_path=log,
        repository=REPO,
        issue_number=1607,
        repo_root=Path(lay["active"]),
        dsh_home=ctx["home"],
        phase="green",
    )
    state = ctx["state"]
    guard.store_binding(state, binding)
    env = _clean_env()
    env["FAKE_DSH_MARKER"] = str(ctx["marker"])

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "resume",
            "--session-id",
            "session-1607",
            "--state-root",
            str(state),
            "--doctor-bin",
            str(ctx["doctor"]),
            "--dsh-bin",
            str(ctx["dsh"]),
            "--task",
            "git checkout -- mod.py",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert _blocked_code(proc) == LINKED
    assert not ctx["marker"].exists()
    assert _last_json(proc)["provider_invocation_allowed"] is False


@needs_seatbelt
def test_standalone_clone_allows_exact_git_metadata_ops_and_denies_parent_and_siblings(
    dsh_non_temp_path: Path,
) -> None:
    lay = _layout(dsh_non_temp_path)
    main, active, sibling = Path(lay["main"]), Path(lay["active"]), Path(lay["sibling"])
    base = str(lay["base"])
    clone = dsh_non_temp_path / "standalone"
    source_status = _git(active, "status", "--porcelain").stdout
    main_refs = _git(main, "for-each-ref").stdout

    proc = _prepare(active, clone, base)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    receipt = _last_json(proc)
    assert receipt["schema"] == guard.STANDALONE_CLONE_SCHEMA
    assert receipt["repository"] == REPO
    assert receipt["base_revision"] == base
    assert receipt["origin_url"] == ORIGIN
    assert receipt["copy_back"] == "NONE"
    assert receipt["publication_authority"] == "NONE"
    assert receipt["git_metadata_contract"]["ok"] is True
    assert str(sibling.resolve()) in receipt["source_family_paths"]
    assert (clone / ".git").is_dir()
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == base
    assert _git(clone, "status", "--porcelain").stdout == ""

    # Allowed Git metadata operations inside the standalone workspace, under the
    # real DSH grant set (workspace + host temp areas).
    (clone / "mod.py").write_text("value = 2\n", encoding="utf-8")
    restore = _sandboxed(clone, "git", "checkout", "--", "mod.py")
    assert restore.returncode == 0, restore.stderr
    assert (clone / "mod.py").read_text(encoding="utf-8") == "value = 1\n"
    (clone / "mod.py").write_text("value = 3\n", encoding="utf-8")
    stage = _sandboxed(clone, "git", "add", "mod.py")
    assert stage.returncode == 0, stage.stderr
    commit = _sandboxed(
        clone, "git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "c"
    )
    assert commit.returncode == 0, commit.stderr

    # Negative controls: parent checkout, common Git dir and sibling worktree.
    for victim in (
        main / "secret.py",
        sibling / "mod.py",
        active / "mod.py",
        main / ".git" / "description",
        main / ".git" / "refs" / "heads" / "main",
        main / ".git" / "worktrees" / active.name / "index.lock",
    ):
        before = victim.read_bytes() if victim.exists() else None
        denied = _sandboxed(clone, "/bin/sh", "-c", f'printf x >> "{victim}"')
        assert denied.returncode != 0, victim
        assert "Operation not permitted" in denied.stderr
        assert (victim.read_bytes() if victim.exists() else None) == before

    # No automatic copy-back/publication: source worktree and parent refs untouched.
    assert _git(active, "status", "--porcelain").stdout == source_status
    assert _git(active, "rev-parse", "HEAD").stdout.strip() == base
    assert _git(main, "for-each-ref").stdout == main_refs


def test_start_phase_allows_dsh_non_temp_path_standalone_clone_and_records_git_contract(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    clone = dsh_non_temp_path / "standalone"
    assert _prepare(Path(lay["active"]), clone, str(lay["base"])).returncode == 0
    ctx = _phase_fixture(tmp_path)

    proc = _start_phase(ctx, clone)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ctx["marker"].exists()
    summary = _last_json(proc)
    preflight = json.loads(Path(summary["preflight_receipt_path"]).read_text(encoding="utf-8"))
    assert preflight["decision"] == "ALLOW_RESUME"
    contract = preflight["git_metadata_contract"]
    assert contract["ok"] is True
    assert contract["git_dir"] == str(clone.resolve() / ".git")


def test_standalone_clone_under_temp_grant_is_rejected_before_spawn(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    temp_clone = tmp_path / "temp-clone"
    _git(tmp_path, "clone", "-q", "--no-local", str(lay["main"]), str(temp_clone))
    ctx = _phase_fixture(tmp_path)

    assert guard.git_metadata_contract(temp_clone, env=_clean_env())["reason_code"] == UNDER_TEMP
    assert _blocked_code(_start_phase(ctx, temp_clone)) == UNDER_TEMP
    assert not ctx["marker"].exists()


def test_prepare_standalone_rejects_temp_targets_and_temp_exposed_sources(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    active, base = Path(lay["active"]), str(lay["base"])
    target = tmp_path / "clone"

    assert _blocked_code(_prepare(active, target, base)) == "STANDALONE_TARGET_UNDER_DSH_TEMP_GRANT"
    assert not target.exists()

    exposed = dsh_non_temp_path / "exposed"
    exposed.mkdir()
    sib_lay = _layout(exposed, sibling_root=tmp_path)
    blocked = _prepare(Path(sib_lay["active"]), dsh_non_temp_path / "c1", str(sib_lay["base"]))
    assert _blocked_code(blocked) == "STANDALONE_SOURCE_EXPOSED_UNDER_DSH_TEMP_GRANT"
    assert str(Path(sib_lay["sibling"]).resolve()) in _last_json(blocked)["detail"]
    assert not (dsh_non_temp_path / "c1").exists()

    temp_wt = tmp_path / "wt-temp"
    _git(Path(lay["main"]), "worktree", "add", "-q", "--detach", str(temp_wt), base)
    blocked = _prepare(active, dsh_non_temp_path / "c2", base)
    assert _blocked_code(blocked) == "STANDALONE_SOURCE_EXPOSED_UNDER_DSH_TEMP_GRANT"
    assert _blocked_code(_prepare(temp_wt, dsh_non_temp_path / "c3", base)) == (
        "STANDALONE_SOURCE_EXPOSED_UNDER_DSH_TEMP_GRANT"
    )
    assert not (dsh_non_temp_path / "c2").exists() and not (dsh_non_temp_path / "c3").exists()


def test_git_identity_environment_override_fails_closed(
    tmp_path: Path, dsh_non_temp_path: Path
) -> None:
    lay = _layout(dsh_non_temp_path)
    clone = dsh_non_temp_path / "standalone"
    assert _prepare(Path(lay["active"]), clone, str(lay["base"])).returncode == 0
    ctx = _phase_fixture(tmp_path)
    wrong = str(Path(lay["main"]) / ".git")

    proc = _start_phase(ctx, clone, env={"GIT_DIR": wrong})

    assert _blocked_code(proc) == "DSH_GIT_IDENTITY_AMBIGUOUS"
    assert not ctx["marker"].exists()
    for key in ("GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        result = guard.git_metadata_contract(clone, env={key: wrong})
        assert result["ok"] is False
        assert result["reason_code"] == "DSH_GIT_IDENTITY_AMBIGUOUS"


def test_ambiguous_or_shared_git_identity_fails_closed(dsh_non_temp_path: Path) -> None:
    lay = _layout(dsh_non_temp_path)
    env = _clean_env()
    plain = dsh_non_temp_path / "not-a-repo"
    plain.mkdir()
    sub = Path(lay["main"]) / "pkg"
    sub.mkdir()
    shared = dsh_non_temp_path / "shared"
    _git(dsh_non_temp_path, "clone", "-q", "--shared", str(lay["main"]), str(shared))
    real = dsh_non_temp_path / "real-git"
    _git(dsh_non_temp_path, "clone", "-q", "--no-local", str(lay["main"]), str(real))
    symlinked = dsh_non_temp_path / "symlinked"
    symlinked.mkdir()
    shutil.copy(Path(lay["main"]) / "mod.py", symlinked / "mod.py")
    (symlinked / ".git").symlink_to(real / ".git")

    cases = {
        plain: "DSH_GIT_IDENTITY_UNRESOLVED",
        sub: "DSH_GIT_IDENTITY_AMBIGUOUS",
        symlinked: "DSH_GIT_IDENTITY_AMBIGUOUS",
        Path(lay["sibling"]): LINKED,
        shared: "DSH_GIT_OBJECT_STORE_SHARED",
    }
    for repo_root, code in cases.items():
        result = guard.git_metadata_contract(repo_root, env=env)
        assert result["ok"] is False, repo_root
        assert result["reason_code"] == code, (repo_root, result)
    assert guard.git_metadata_contract(real, env=env)["ok"] is True


def test_prepare_standalone_rejects_wrong_identity_and_unsafe_targets(
    dsh_non_temp_path: Path,
) -> None:
    lay = _layout(dsh_non_temp_path)
    active, main, base = Path(lay["active"]), Path(lay["main"]), str(lay["base"])

    wrong_repo = _prepare(active, dsh_non_temp_path / "x1", base, repository="James3014/other")
    assert _blocked_code(wrong_repo) == "STANDALONE_REPOSITORY_MISMATCH"
    assert (
        _blocked_code(_prepare(active, dsh_non_temp_path / "x2", base[:12]))
        == "STANDALONE_BASE_INVALID"
    )
    assert _blocked_code(_prepare(active, dsh_non_temp_path / "x3", "f" * 40)) == (
        "STANDALONE_BASE_UNAVAILABLE"
    )
    assert _blocked_code(_prepare(active, active / "nested", base)) == "STANDALONE_TARGET_UNSAFE"
    assert _blocked_code(_prepare(active, main / ".git" / "x", base)) == (
        "STANDALONE_TARGET_UNSAFE"
    )
    assert _blocked_code(_prepare(active, dsh_non_temp_path, base)) == "STANDALONE_TARGET_UNSAFE"
    for leftover in ("x1", "x2", "x3"):
        assert not (dsh_non_temp_path / leftover).exists()

    clone = dsh_non_temp_path / "standalone"
    first = _prepare(active, clone, base)
    assert first.returncode == 0, first.stderr
    again = _prepare(active, clone, base)
    assert again.returncode == 0, again.stderr
    assert _last_json(again)["reused"] is True

    (clone / "mod.py").write_text("dirty\n", encoding="utf-8")
    assert _blocked_code(_prepare(active, clone, base)) == "STANDALONE_TARGET_DIRTY"
    assert (clone / "mod.py").read_text(encoding="utf-8") == "dirty\n"

    other = dsh_non_temp_path / "other-origin"
    _git(dsh_non_temp_path, "clone", "-q", "--no-local", str(main), str(other))
    _git(other, "remote", "set-url", "origin", "https://github.com/James3014/other.git")
    mismatch = "STANDALONE_TARGET_IDENTITY_MISMATCH"
    assert _blocked_code(_prepare(active, other, base)) == mismatch
    assert _blocked_code(_prepare(active, Path(lay["sibling"]), base)) == mismatch
    _git(
        main,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@e",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "n",
    )
    newer = _git(main, "rev-parse", "HEAD").stdout.strip()
    (clone / "mod.py").write_text("value = 1\n", encoding="utf-8")
    assert _blocked_code(_prepare(active, clone, newer)) == mismatch
