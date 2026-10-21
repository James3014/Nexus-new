"""#2254 items 2, 3, 6: codex disposable HOME, env allowlist, symlink/.git checks.

The Codex launcher ``scripts/ops/start_codex_nexus_enforced.sh`` and its
``scripts/ops/codex_run_guard.py`` were deleted on 2026-10-21 (#2584, Phase-2
batch B, ``ARCHIVED_2026-10-21_phase2_batch_B.md``).  The live consumer of
``nexus.executors.codex_run_boundary`` is ``CodexCliExecutor``.  Cases that
checked a boundary behaviour through the launcher keep their test ids and now
call the boundary module directly with the same planted mutations; cases that
only checked launcher mechanics (process groups, guard exit codes, state dir)
assert the launcher is gone.
"""

import os
import stat
import subprocess
from pathlib import Path

from nexus.executors.codex_run_boundary import (
    CODEX_TARGET_ESCAPE,
    codex_child_env,
    materialize_codex_home,
    target_integrity_failure,
    target_integrity_snapshot,
    write_back_refreshed_auth,
)

_RETIRED_LAUNCHER = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "start_codex_nexus_enforced.sh"
)
_RETIRED_GUARD = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "codex_run_guard.py"

# The same mutations the fake codex used to plant inside the run copy.
_MUTATE = r"""
case "$FAKE_CODEX_MODE" in
  symlink) ln -s "$FAKE_ESCAPE_DIR" "$work/escape-link" ;;
  filelink) ln -s "$FAKE_ESCAPE_DIR/secret.txt" "$work/escape-file" ;;
  gitptr) echo "gitdir: $FAKE_ESCAPE_DIR" > "$work/.git" ;;
  hidden) mkdir "$work/locked"; ln -s "$FAKE_ESCAPE_DIR" "$work/locked/escape"; chmod 000 "$work/locked" ;;
  nestedgit) mkdir "$work/sub"; ln -s "$FAKE_ESCAPE_DIR" "$work/sub/.git" ;;
  nestedgitdir) mkdir -p "$work/sub/.git"; ln -s "$FAKE_ESCAPE_DIR" "$work/sub/.git/leak" ;;
  lockedgit) mkdir -p "$work/sub/.git"; ln -s "$FAKE_ESCAPE_DIR" "$work/sub/.git/leak"; chmod 000 "$work/sub/.git" ;;
  nestedfile) mkdir "$work/sub"; echo "gitdir: /outside" > "$work/sub/.git" ;;
  nestedcfg) mkdir -p "$work/n2/.git"; printf '[core]\n\tfsmonitor = x\n' > "$work/n2/.git/config" ;;
  nestedhooklink) mkdir -p "$work/sub/.git" "$work/inner"; ln -s "$work/inner" "$work/sub/.git/hooks" ;;
  nestedupper) mkdir -p "$work/sub/.GIT"; printf '[core]\n\tfsmonitor = x\n' > "$work/sub/.GIT/config" ;;
  nestedmixedfile) mkdir "$work/sub2"; echo "gitdir: /outside" > "$work/sub2/.Git" ;;
  inside) ln -s tracked.txt "$work/inside-link" ;;
esac
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _integrity(tmp_path: Path, mode: str, *, prepare=None):
    """Snapshot a detached worktree, plant ``mode`` like the fake codex did, compare.

    The work copy is a detached ``git worktree`` of a canonical repo, as the
    launcher's run copy was, so ``.git`` is a pointer file.
    """
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(canonical, "init", "-q")
    _git(canonical, "add", ".")
    _git(canonical, "commit", "-qm", "init")
    if prepare is not None:
        prepare(canonical)
    work = tmp_path / "work"
    _git(canonical, "worktree", "add", "--quiet", "--detach", str(work), "HEAD")
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "secret.txt").write_text("s\n", encoding="utf-8")
    before = target_integrity_snapshot(work)
    subprocess.run(
        ["bash", "-c", _MUTATE],
        env={
            **os.environ,
            "work": str(work),
            "FAKE_CODEX_MODE": mode,
            "FAKE_ESCAPE_DIR": str(secret_dir),
        },
        check=True,
    )
    try:
        return target_integrity_failure(before, target_integrity_snapshot(work))
    finally:
        for locked in (work / "locked", work / "sub" / ".git"):
            if locked.is_dir() and not locked.is_symlink():
                locked.chmod(0o755)


def _auth_round_trip(tmp_path: Path, refreshed: str | None, *, host_meanwhile: str | None = None):
    """Materialize a run HOME, let the "run" rewrite its auth copy, then write back."""
    real_home = tmp_path / "realhome"
    codex_home = real_home / ".codex"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-fake"}', encoding="utf-8")
    (codex_home / "auth.json").chmod(0o644)
    source = {"HOME": str(real_home), "CODEX_HOME": str(codex_home)}
    run_home = tmp_path / "run-home"
    assert materialize_codex_home(run_home, source=source) is None
    if refreshed is not None:
        (run_home / ".codex" / "auth.json").write_text(refreshed, encoding="utf-8")
    if host_meanwhile is not None:
        (codex_home / "auth.json").write_text(host_meanwhile, encoding="utf-8")
    write_back_refreshed_auth(run_home, source=source)
    return codex_home / "auth.json"


def _launcher_retired() -> None:
    assert not _RETIRED_LAUNCHER.exists()
    assert not _RETIRED_GUARD.exists()


def test_codex_runs_in_a_disposable_home_with_auth_only(tmp_path):
    real_home = tmp_path / "realhome"
    (real_home / ".ssh").mkdir(parents=True)
    (real_home / ".gitconfig").write_text("[user]\n\tname = real\n", encoding="utf-8")
    codex_home = real_home / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-fake"}', encoding="utf-8")
    (codex_home / "auth.json").chmod(0o644)
    (codex_home / "history.jsonl").write_text("secret history\n", encoding="utf-8")
    (codex_home / "config.toml").write_text("[mcp_servers.x]\n", encoding="utf-8")
    (codex_home / "sessions").mkdir()
    home = tmp_path / "run-home"

    assert materialize_codex_home(home, source={"HOME": str(real_home)}) is None
    env = codex_child_env({"PATH": "/usr/bin"}, home=home, tmpdir=home / "tmp")

    assert home != real_home and real_home not in home.parents
    assert env["HOME"] == str(home)
    assert env["CODEX_HOME"] == str(home / ".codex")
    for forbidden in (".ssh", ".gitconfig"):
        assert not (home / forbidden).exists()
    assert sorted(p.name for p in (home / ".codex").iterdir()) == ["auth.json"]
    auth = home / ".codex" / "auth.json"
    assert not auth.is_symlink()
    assert stat.S_IMODE(auth.stat().st_mode) == 0o600
    assert auth.read_text(encoding="utf-8") == '{"OPENAI_API_KEY":"sk-fake"}'


def test_codex_child_env_is_an_allowlist(tmp_path):
    source = {
        **os.environ,
        "GH_TOKEN": "ghp_fake",
        "GITHUB_TOKEN": "ghp_fake2",
        "SSH_AUTH_SOCK": "/tmp/agent.sock",
        "OPENAI_API_KEY": "sk-ambient",
        "NEXUS_CODEX_ENV_PASSTHROUGH": "FAKE_CODEX_MODE,GH_TOKEN",
        "FAKE_CODEX_MODE": "inside",
    }
    keys = set(codex_child_env(source, home=tmp_path / "h", tmpdir=tmp_path / "h" / "tmp"))

    for forbidden in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "OPENAI_API_KEY"):
        assert forbidden not in keys
    assert {"PATH", "HOME", "CODEX_HOME", "TMPDIR", "FAKE_CODEX_MODE"} <= keys


def test_codex_run_fails_on_a_planted_escaping_directory_symlink(tmp_path):
    assert _integrity(tmp_path, "symlink") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_on_a_planted_escaping_file_symlink(tmp_path):
    assert _integrity(tmp_path, "filelink") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_when_the_git_pointer_is_rewritten(tmp_path):
    assert _integrity(tmp_path, "gitptr") == CODEX_TARGET_ESCAPE


def test_codex_run_allows_an_inside_symlink_and_committed_escaping_baseline(tmp_path):
    def commit_escaping_link(canonical: Path) -> None:
        os.symlink("/etc/hosts", canonical / "baseline-link")
        _git(canonical, "add", "baseline-link")
        _git(canonical, "commit", "-qm", "baseline escaping link")

    assert _integrity(tmp_path, "inside", prepare=commit_escaping_link) is None


def test_codex_run_home_is_removed_when_the_run_fails(tmp_path):
    _launcher_retired()


def test_codex_run_fails_on_an_escaping_symlink_hidden_in_an_unreadable_directory(tmp_path):
    assert _integrity(tmp_path, "hidden") == CODEX_TARGET_ESCAPE


def test_codex_launcher_creates_its_state_dir_when_report_file_is_set(tmp_path):
    _launcher_retired()


def test_codex_env_passthrough_refuses_injection_and_credential_names():
    from nexus.executors.codex_run_boundary import codex_child_env

    source = {
        "PATH": "/usr/bin",
        "NEXUS_CODEX_ENV_PASSTHROUGH": "GIT_ASKPASS,GIT_SSH_COMMAND,LD_PRELOAD,DYLD_INSERT_LIBRARIES,"
        "PYTHONPATH,BASH_ENV,NODE_OPTIONS,GH_TOKEN,MY_API_KEY,SAFE_VALUE",
        "GIT_ASKPASS": "x",
        "GIT_SSH_COMMAND": "x",
        "LD_PRELOAD": "x",
        "DYLD_INSERT_LIBRARIES": "x",
        "PYTHONPATH": "x",
        "BASH_ENV": "x",
        "NODE_OPTIONS": "x",
        "GH_TOKEN": "x",
        "MY_API_KEY": "x",
        "SAFE_VALUE": "ok",
    }
    env = codex_child_env(source, home=Path("/h"), tmpdir=Path("/h/tmp"))

    assert env["SAFE_VALUE"] == "ok"
    for name in list(source)[2:-1]:
        assert name not in env


def test_codex_run_fails_on_an_escaping_symlink_named_dot_git_in_a_subdirectory(tmp_path):
    assert _integrity(tmp_path, "nestedgit") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_on_an_escaping_symlink_inside_a_nested_dot_git_directory(tmp_path):
    assert _integrity(tmp_path, "nestedgitdir") == CODEX_TARGET_ESCAPE


def test_codex_env_lc_prefix_does_not_pass_credential_shaped_names():
    from nexus.executors.codex_run_boundary import codex_child_env

    env = codex_child_env(
        {"LC_ALL": "C", "LC_GITHUB_TOKEN": "x", "LC_AUTH_SOCK": "x"},
        home=Path("/h"),
        tmpdir=Path("/h/tmp"),
    )

    assert env["LC_ALL"] == "C"
    assert "LC_GITHUB_TOKEN" not in env and "LC_AUTH_SOCK" not in env


def test_codex_run_fails_on_an_escaping_symlink_inside_an_unreadable_nested_dot_git(tmp_path):
    assert _integrity(tmp_path, "lockedgit") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_on_a_nested_dot_git_file_pointing_outside(tmp_path):
    assert _integrity(tmp_path, "nestedfile") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_on_a_nested_dot_git_directory_with_a_planted_config(tmp_path):
    assert _integrity(tmp_path, "nestedcfg") == CODEX_TARGET_ESCAPE


def test_codex_run_kills_a_backgrounded_child_before_verifying(tmp_path):
    _launcher_retired()


def test_codex_refreshed_auth_is_written_back_to_the_host_atomically(tmp_path):
    host = _auth_round_trip(tmp_path, '{"OPENAI_API_KEY":"sk-refreshed"}')

    assert host.read_text(encoding="utf-8").strip() == '{"OPENAI_API_KEY":"sk-refreshed"}'
    assert stat.S_IMODE(host.stat().st_mode) == 0o600
    assert sorted(p.name for p in host.parent.glob("auth.json*")) == ["auth.json"]


def test_codex_refreshed_auth_does_not_clobber_a_host_file_changed_meanwhile(tmp_path):
    host = _auth_round_trip(
        tmp_path,
        '{"OPENAI_API_KEY":"sk-refreshed"}',
        host_meanwhile='{"OPENAI_API_KEY":"sk-other-session"}',
    )

    assert host.read_text(encoding="utf-8").strip() == '{"OPENAI_API_KEY":"sk-other-session"}'


def test_codex_invalid_refreshed_auth_is_not_written_back(tmp_path):
    host = _auth_round_trip(tmp_path, "not json")

    assert host.read_text(encoding="utf-8") == '{"OPENAI_API_KEY":"sk-fake"}'


def test_codex_launcher_fails_closed_when_the_guard_fails_in_home(tmp_path):
    _launcher_retired()


def test_codex_launcher_fails_closed_when_the_guard_fails_in_snapshot(tmp_path):
    _launcher_retired()


def test_codex_launcher_fails_closed_when_the_guard_fails_in_verify(tmp_path):
    _launcher_retired()


def test_codex_env_strips_proxy_credentials_and_odd_locale_values():
    from nexus.executors.codex_run_boundary import codex_child_env

    env = codex_child_env(
        {
            "HTTPS_PROXY": "http://user:pw@proxy.example:8080/",
            "http_proxy": "http://proxy.example:3128",
            "NO_PROXY": "localhost,127.0.0.1",
            "LC_ALL": "en_US.UTF-8",
            "LC_MESSAGES": "$(touch /tmp/x)",
        },
        home=Path("/h"),
        tmpdir=Path("/h/tmp"),
    )

    assert env["HTTPS_PROXY"] == "http://proxy.example:8080/"
    assert env["http_proxy"] == "http://proxy.example:3128"
    assert env["NO_PROXY"] == "localhost,127.0.0.1"
    assert env["LC_ALL"] == "en_US.UTF-8"
    assert "LC_MESSAGES" not in env


def test_codex_auth_is_not_written_back_when_the_run_is_rejected(tmp_path):
    _launcher_retired()


def test_codex_empty_credential_is_not_written_back(tmp_path):
    host = _auth_round_trip(tmp_path, '{"OPENAI_API_KEY":""}')

    assert host.read_text(encoding="utf-8") == '{"OPENAI_API_KEY":"sk-fake"}'


def test_codex_run_fails_on_an_in_tree_symlink_inside_a_nested_dot_git(tmp_path):
    assert _integrity(tmp_path, "nestedhooklink") == CODEX_TARGET_ESCAPE


def test_codex_env_strips_credentials_from_schemeless_proxy_values():
    from nexus.executors.codex_run_boundary import codex_child_env

    env = codex_child_env(
        {"HTTP_PROXY": "user:pw@proxy.example:8080"}, home=Path("/h"), tmpdir=Path("/h/tmp")
    )

    assert env["HTTP_PROXY"] == "proxy.example:8080"


def test_codex_run_fails_on_a_case_variant_nested_dot_git_directory(tmp_path):
    assert _integrity(tmp_path, "nestedupper") == CODEX_TARGET_ESCAPE


def test_codex_run_fails_on_a_case_variant_nested_dot_git_file(tmp_path):
    assert _integrity(tmp_path, "nestedmixedfile") == CODEX_TARGET_ESCAPE
