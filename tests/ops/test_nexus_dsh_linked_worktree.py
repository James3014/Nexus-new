"""Issue #1607: DSH outer bash inside a linked Git worktree.

DSH ``workspace-write`` grants writes only under the session cwd (plus host temp
areas). A linked worktree keeps its index/lock under the parent repository's
common Git dir, so exact-worktree Git metadata operations are physically denied.
The supported contract is an explicit standalone clone (real ``.git`` directory
inside the workspace); linked worktrees and ambiguous Git identity fail closed
before DSH is spawned.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_linked_worktree_test", str(SCRIPT)).load_module()
REPO = "James3014/Nexus-new"
ORIGIN = "https://github.com/James3014/Nexus-new.git"

needs_seatbelt = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("sandbox-exec") is None,
    reason="physical DSH Seatbelt confinement witness requires macOS sandbox-exec",
)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check)


GIT_IDENTITY_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
)


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in GIT_IDENTITY_ENV:
        env.pop(key, None)
    return env


def _layout(tmp_path: Path) -> dict[str, Path | str]:
    """Parent checkout + two linked worktrees, mirroring the #1599 witness."""
    main = tmp_path / "Nexus-new"
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
    base = _git(main, "rev-parse", "HEAD").stdout.strip()
    active = tmp_path / "wt-active"
    sibling = tmp_path / "wt-sibling"
    _git(main, "worktree", "add", "-q", "--detach", str(active), base)
    _git(main, "worktree", "add", "-q", "--detach", str(sibling), base)
    return {"main": main, "active": active, "sibling": sibling, "base": base}


def _workspace_write_profile(workspace: Path) -> str:
    # Same SBPL shape as DSH 0.2.0-rc.2 ``seatbeltProfileArgs`` for workspace-write.
    # The host temp grants are omitted because pytest's tmp_path lives under the
    # temp area; in the live #1599 witness the common Git dir was outside it.
    root = str(workspace.resolve())
    return (
        "(version 1) (allow default) (deny file-write*) "
        '(allow file-write* (literal "/dev/null")) '
        f'(allow file-write* (subpath "{root}"))'
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


def _prepare(source: Path, target: Path, base: str, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "prepare-standalone",
            "--repository",
            REPO,
            "--source-repo-root",
            str(source),
            "--base-revision",
            base,
            "--target",
            str(target),
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=_clean_env(),
    )


def _last_json(proc: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(proc.stdout.strip().splitlines()[-1])


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


@needs_seatbelt
def test_linked_worktree_git_restore_is_physically_denied_under_workspace_write(
    tmp_path: Path,
) -> None:
    lay = _layout(tmp_path)
    active = Path(lay["active"])
    (active / "mod.py").write_text("value = 2\n", encoding="utf-8")

    restore = _sandboxed(active, "git", "checkout", "--", "mod.py")

    assert restore.returncode != 0
    assert "index.lock" in restore.stderr
    assert "Operation not permitted" in restore.stderr
    assert (active / "mod.py").read_text(encoding="utf-8") == "value = 2\n"


def test_start_phase_blocks_linked_worktree_before_spawning_dsh(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
    ctx = _phase_fixture(tmp_path)

    proc = _start_phase(ctx, Path(lay["active"]))

    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    assert not ctx["marker"].exists()
    receipt = _last_json(proc)
    assert receipt["decision"] == "BLOCK_RESUME"
    assert receipt["reason_code"] == "DSH_LINKED_WORKTREE_GIT_METADATA_OUTSIDE_WORKSPACE"
    assert receipt["provider_invocation_allowed"] is False
    assert "prepare-standalone" in receipt["detail"]


def test_resume_blocks_linked_worktree_before_spawning_dsh(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
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

    assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
    assert not ctx["marker"].exists()
    receipt = _last_json(proc)
    assert receipt["reason_code"] == "DSH_LINKED_WORKTREE_GIT_METADATA_OUTSIDE_WORKSPACE"
    assert receipt["provider_invocation_allowed"] is False


@needs_seatbelt
def test_standalone_clone_allows_exact_git_metadata_ops_and_denies_parent_and_siblings(
    tmp_path: Path,
) -> None:
    lay = _layout(tmp_path)
    main, active, sibling = Path(lay["main"]), Path(lay["active"]), Path(lay["sibling"])
    base = str(lay["base"])
    clone = tmp_path / "standalone"
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
    assert (clone / ".git").is_dir()
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == base
    assert _git(clone, "status", "--porcelain").stdout == ""

    # Allowed Git metadata operations inside the standalone workspace.
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
        main / ".git" / "description",
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


def test_start_phase_allows_standalone_clone_and_records_git_contract(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
    clone = tmp_path / "standalone"
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


def test_git_identity_environment_override_fails_closed(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
    clone = tmp_path / "standalone"
    assert _prepare(Path(lay["active"]), clone, str(lay["base"])).returncode == 0
    ctx = _phase_fixture(tmp_path)
    wrong = str(Path(lay["main"]) / ".git")

    proc = _start_phase(ctx, clone, env={"GIT_DIR": wrong})

    assert proc.returncode == guard.EXIT_BLOCKED
    assert not ctx["marker"].exists()
    assert _last_json(proc)["reason_code"] == "DSH_GIT_IDENTITY_AMBIGUOUS"
    for key in ("GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        result = guard.git_metadata_contract(clone, env={key: wrong})
        assert result["ok"] is False
        assert result["reason_code"] == "DSH_GIT_IDENTITY_AMBIGUOUS"


def test_ambiguous_or_shared_git_identity_fails_closed(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
    env = _clean_env()
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    sub = Path(lay["main"]) / "pkg"
    sub.mkdir()
    shared = tmp_path / "shared"
    _git(tmp_path, "clone", "-q", "--shared", str(lay["main"]), str(shared))
    real = tmp_path / "real-git"
    _git(tmp_path, "clone", "-q", "--no-local", str(lay["main"]), str(real))
    symlinked = tmp_path / "symlinked"
    symlinked.mkdir()
    shutil.copy(Path(lay["main"]) / "mod.py", symlinked / "mod.py")
    (symlinked / ".git").symlink_to(real / ".git")

    cases = {
        plain: "DSH_GIT_IDENTITY_UNRESOLVED",
        sub: "DSH_GIT_IDENTITY_AMBIGUOUS",
        symlinked: "DSH_GIT_IDENTITY_AMBIGUOUS",
        Path(lay["sibling"]): "DSH_LINKED_WORKTREE_GIT_METADATA_OUTSIDE_WORKSPACE",
        shared: "DSH_GIT_OBJECT_STORE_SHARED",
    }
    for repo_root, code in cases.items():
        result = guard.git_metadata_contract(repo_root, env=env)
        assert result["ok"] is False, repo_root
        assert result["reason_code"] == code, (repo_root, result)
    assert guard.git_metadata_contract(Path(lay["main"]), env=env)["ok"] is True


def test_prepare_standalone_rejects_wrong_identity_and_unsafe_targets(tmp_path: Path) -> None:
    lay = _layout(tmp_path)
    active, main, base = Path(lay["active"]), Path(lay["main"]), str(lay["base"])

    def code(proc: subprocess.CompletedProcess[str]) -> str:
        assert proc.returncode == guard.EXIT_BLOCKED, proc.stdout + proc.stderr
        return _last_json(proc)["reason_code"]

    wrong_repo = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "prepare-standalone",
            "--repository",
            "James3014/other",
            "--source-repo-root",
            str(active),
            "--base-revision",
            base,
            "--target",
            str(tmp_path / "x1"),
        ],
        text=True,
        capture_output=True,
        check=False,
        env=_clean_env(),
    )
    assert code(wrong_repo) == "STANDALONE_REPOSITORY_MISMATCH"
    assert code(_prepare(active, tmp_path / "x2", base[:12])) == "STANDALONE_BASE_INVALID"
    assert code(_prepare(active, tmp_path / "x3", "f" * 40)) == "STANDALONE_BASE_UNAVAILABLE"
    assert code(_prepare(active, active / "nested", base)) == "STANDALONE_TARGET_UNSAFE"
    assert code(_prepare(active, main / ".git" / "x", base)) == "STANDALONE_TARGET_UNSAFE"
    assert code(_prepare(active, tmp_path, base)) == "STANDALONE_TARGET_UNSAFE"
    for leftover in ("x1", "x2", "x3"):
        assert not (tmp_path / leftover).exists()

    clone = tmp_path / "standalone"
    first = _prepare(active, clone, base)
    assert first.returncode == 0, first.stderr
    again = _prepare(active, clone, base)
    assert again.returncode == 0, again.stderr
    assert _last_json(again)["reused"] is True

    (clone / "mod.py").write_text("dirty\n", encoding="utf-8")
    assert code(_prepare(active, clone, base)) == "STANDALONE_TARGET_DIRTY"
    assert (clone / "mod.py").read_text(encoding="utf-8") == "dirty\n"

    other = tmp_path / "other-origin"
    _git(tmp_path, "clone", "-q", "--no-local", str(main), str(other))
    _git(other, "remote", "set-url", "origin", "https://github.com/James3014/other.git")
    assert code(_prepare(active, other, base)) == "STANDALONE_TARGET_IDENTITY_MISMATCH"
    assert (
        code(_prepare(active, Path(lay["sibling"]), base)) == "STANDALONE_TARGET_IDENTITY_MISMATCH"
    )
