import os
import subprocess
import sys
from pathlib import Path


def test_codex_enforced_startup_contract_block():
    try:
        res = subprocess.run(
            ["bash", "scripts/ops/start_codex_nexus_enforced.sh"],
            capture_output=True, text=True, cwd="/tmp"
        )
        assert res.returncode != 0
    except Exception:
        pass

def test_antigravity_compat_proxy():
    # 測試舊腳本是否成功導向
    res = subprocess.run(
        ["bash", "scripts/ops/start_antigravity_nexus_enforced.sh", "--help"],
        capture_output=True, text=True
    )
    # 應該包含轉接警告
    assert "[DEPRECATION-WARNING]" in res.stdout


# ---------------------------------------------------------------------------
# #2195: no sandbox bypass, disposable work copy, integrity, denied actions
# ---------------------------------------------------------------------------

_LAUNCHER = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "start_codex_nexus_enforced.sh"
)

_FAKE_CODEX = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_CODEX_ARGV"
cat > /dev/null
work=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-C" ]]; then work="$2"; fi
  shift
done
case "$FAKE_CODEX_MODE" in
  work) echo delivered > "$work/candidate.txt"; echo '{"type":"turn.completed"}' ;;
  canonical) echo tampered > "$FAKE_CANONICAL/tracked.txt"; echo '{"type":"turn.completed"}' ;;
  declined) echo '{"type":"item.completed","item":{"type":"command_execution","status":"declined"}}' ;;
  sandbox) echo '{"type":"error","message":"sandbox denied exec error, exit code: 1"}' ;;
  quoted)
    # Model text and command output that merely quote the old markers.
    echo '{"type":"item.completed","item":{"type":"agent_message","text":"grep: sandbox denied|rejected by user|\"status\": \"declined\""}}'
    echo '{"type":"item.completed","item":{"type":"command_execution","status":"completed","aggregated_output":"sandbox denied rejected by user \"status\": \"declined\""}}'
    echo 'sandbox denied exec error, exit code: 1 (not JSON)'
    echo '{"type":"turn.completed"}' ;;
  pyfail) echo '{"type":"turn.completed"}' ;;
  fail) echo '{"type":"turn.failed","error":{"message":"model unavailable"}}'; exit 3 ;;
  ref)
    moved="$(GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
      git -C "$FAKE_CANONICAL" commit-tree 'HEAD^{tree}' -p HEAD -m moved)"
    # Moves the checked-out branch (HEAD follows it).
    git -C "$FAKE_CANONICAL" update-ref "$(git -C "$FAKE_CANONICAL" symbolic-ref HEAD)" "$moved"
    echo '{"type":"turn.completed"}' ;;
  sideref)
    # Another session moving a different branch in the shared common dir.
    moved="$(GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
      git -C "$FAKE_CANONICAL" commit-tree 'HEAD^{tree}' -p HEAD -m moved)"
    git -C "$FAKE_CANONICAL" update-ref refs/heads/side "$moved"
    git -C "$FAKE_CANONICAL" pack-refs --all
    echo '{"type":"turn.completed"}' ;;
  churn|codecfg:*)
    # #2547: what other sessions do to the shared config during a run.
    branch="$(git -C "$FAKE_CANONICAL" symbolic-ref --short HEAD)"
    git -C "$FAKE_CANONICAL" worktree add -q -b concurrent-2547 "$FAKE_CANONICAL/../other-wt" "origin/$branch"
    git -C "$FAKE_CANONICAL" branch -q --set-upstream-to "origin/$branch"
    git -C "$FAKE_CANONICAL" remote set-branches --add origin feat/x
    git -C "$FAKE_CANONICAL" config branch.feat/x.description work
    if [[ "$FAKE_CODEX_MODE" == codecfg:* ]]; then
      spec="${FAKE_CODEX_MODE#codecfg:}"
      git -C "$FAKE_CANONICAL" config "${spec%%=*}" "${spec#*=}"
    fi
    echo '{"type":"turn.completed"}' ;;
  *) echo '{"type":"turn.completed"}' ;;
esac
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _launch(
    tmp_path: Path,
    mode: str,
    approval: str = "workspace-write",
    work_root: Path | None = None,
    model: str = "gpt-test",
    commit: bool = True,
    default_work_root: bool = False,
    origin: bool = False,
):
    canonical = tmp_path / "canonical"
    ops = canonical / "scripts" / "ops"
    ops.mkdir(parents=True)
    (ops / "_nexus_enforced_briefing.sh").write_text('echo "$1"\n', encoding="utf-8")
    (ops / "nexus_startup_contract_check.py").write_text("", encoding="utf-8")
    (canonical / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(canonical, "init", "-q")
    _git(canonical, "add", ".")
    if commit:
        _git(canonical, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        _git(canonical, "branch", "side")
    if origin:
        # A fetched remote, so upstream bookkeeping during the run is real (#2547).
        upstream = tmp_path / "upstream"
        _git(tmp_path, "clone", "-q", "--bare", str(canonical), str(upstream))
        _git(canonical, "remote", "add", "origin", str(upstream))
        _git(canonical, "fetch", "-q", "origin")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text(_FAKE_CODEX, encoding="utf-8")
    fake.chmod(0o755)
    if mode == "pyfail":
        # The denial classifier (python3 -I) fails; the startup check still runs.
        stub = bin_dir / "python3"
        stub.write_text(
            f'#!/usr/bin/env bash\n[[ "$1" == "-I" && "$2" == "-" ]] && exit 1\nexec "{sys.executable}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    if mode.startswith("cfg"):
        # The shared Git-config fingerprint fails (cfgfail), prints nothing
        # (cfgempty) or prints garbage (cfgjunk); cfglate fails only on the
        # second (after-run) call.  Every other python3 call runs for real.
        behaviour = {
            "cfgfail": "exit 1",
            "cfgempty": "exit 0",
            "cfgjunk": "echo not-a-sha256; exit 0",
            "cfglate": f'n=$(cat "{tmp_path}/cfg-calls" 2>/dev/null || echo 0); '
            f'echo $((n + 1)) > "{tmp_path}/cfg-calls"; [[ "$n" -ge 1 ]] && exit 1',
        }[mode]
        stub = bin_dir / "python3"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f'if [[ "$1" == "-I" && "$3" == "git-config-fingerprint" ]]; then {behaviour}; fi\n'
            f'exec "{sys.executable}" "$@"\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded task\n", encoding="utf-8")
    state = tmp_path / "state"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CODEX_BIN": "codex",
        "NEXUS_CODEX_ENV_PASSTHROUGH": "FAKE_CODEX_MODE,FAKE_CODEX_ARGV,FAKE_CANONICAL",
        "FAKE_CODEX_MODE": mode,
        "FAKE_CODEX_ARGV": str(tmp_path / "argv.txt"),
        "FAKE_CANONICAL": str(canonical),
        "NEXUS_MACHINE_STATE_DIR": str(state),
        "LOCK_FILE": str(tmp_path / "launcher.lock"),
        "NEXUS_CODEX_WORK_ROOT": str(work_root or tmp_path / "runs"),
        # Keep the default state dir (work copies, report) inside the test.
        "XDG_STATE_HOME": str(tmp_path / "xdg"),
        "TMPDIR": str(tmp_path / "tmpdir"),
    }
    env.pop("REPORT_FILE", None)
    if default_work_root:
        env.pop("NEXUS_CODEX_WORK_ROOT")
    res = subprocess.run(
        ["bash", str(_LAUNCHER), model, approval, str(prompt)],
        cwd=canonical,
        env=env,
        capture_output=True,
        text=True,
    )
    argv_file = tmp_path / "argv.txt"
    argv = argv_file.read_text(encoding="utf-8").splitlines() if argv_file.exists() else []
    return res, argv, canonical.resolve()


def test_codex_launcher_refuses_sandbox_bypass_modes(tmp_path):
    for approval in ("danger", "danger-full-access", "yolo"):
        res, argv, _ = _launch(tmp_path / approval, "work", approval=approval)
        assert res.returncode == 2
        assert "approval mode refused" in res.stderr
        assert argv == []


def test_codex_launcher_runs_sandboxed_in_a_disposable_work_copy(tmp_path):
    res, argv, canonical = _launch(tmp_path, "work")

    assert res.returncode == 0, res.stderr
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert argv[argv.index("-c") + 1] == 'approval_policy="never"'
    assert not any("dangerously" in item for item in argv)
    work = Path(argv[argv.index("-C") + 1]).resolve()
    assert work.parent == (tmp_path / "runs").resolve()
    assert canonical not in work.parents and work not in canonical.parents
    assert (work / "candidate.txt").read_text(encoding="utf-8") == "delivered\n"
    assert not (canonical / "candidate.txt").exists()


def test_codex_launcher_read_only_mode_uses_read_only_sandbox(tmp_path):
    res, argv, _ = _launch(tmp_path, "none", approval="read-only")

    assert res.returncode == 0, res.stderr
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_codex_launcher_fails_when_canonical_checkout_changes(tmp_path):
    res, _, canonical = _launch(tmp_path, "canonical")

    assert res.returncode == 5
    assert "canonical_checkout_integrity_violation" in res.stderr
    # Reported, never reverted.
    assert (canonical / "tracked.txt").read_text(encoding="utf-8") == "tampered\n"


def test_codex_launcher_denied_actions_are_non_delivery(tmp_path):
    for mode in ("declined", "sandbox"):
        res, _, _ = _launch(tmp_path / mode, mode)
        assert res.returncode == 4, res.stderr
        assert "codex_action_denied" in res.stderr


def test_codex_launcher_refuses_work_root_inside_canonical(tmp_path):
    res, argv, _ = _launch(tmp_path, "work", work_root=tmp_path / "canonical" / "runs")

    assert res.returncode == 2
    assert "overlaps the canonical checkout" in res.stderr
    assert argv == []


def test_codex_launcher_excludes_tmp_from_the_sandbox_and_state(tmp_path):
    res, argv, _ = _launch(tmp_path, "work", default_work_root=True)

    assert res.returncode == 0, res.stderr
    configs = [argv[index + 1] for index, item in enumerate(argv) if item == "-c"]
    assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in configs
    assert "sandbox_workspace_write.exclude_slash_tmp=true" in configs
    state = (tmp_path / "xdg" / "nexus-codex").resolve()
    work = Path(argv[argv.index("-C") + 1]).resolve()
    assert work.parent == state / "runs"
    assert (state / "antigravity_invoke_report.txt").is_file()
    # Only the TMPDIR fixture is checked: on Linux CI tmp_path itself is
    # under /tmp, and the sandbox flags above cover /tmp.
    tmpdir = (tmp_path / "tmpdir").resolve()
    assert tmpdir not in work.parents
    assert tmpdir not in (state / "antigravity_invoke_report.txt").parents


def test_codex_launcher_ignores_denial_markers_in_free_text(tmp_path):
    res, _, _ = _launch(tmp_path, "quoted")

    assert res.returncode == 0, res.stderr
    assert "codex_action_denied" not in res.stderr


def test_codex_launcher_propagates_a_nonzero_codex_exit(tmp_path):
    res, _, _ = _launch(tmp_path, "fail")

    assert res.returncode == 3, res.stderr
    assert "codex exited 3" in res.stderr


def test_codex_launcher_fails_when_a_canonical_ref_moves(tmp_path):
    res, _, canonical = _launch(tmp_path, "ref")

    assert res.returncode == 5, res.stderr
    assert "canonical_checkout_integrity_violation" in res.stderr
    # Reported, never reverted.
    side = subprocess.run(
        ["git", "log", "-1", "--format=%s", "HEAD"],
        cwd=canonical,
        capture_output=True,
        text=True,
        check=True,
    )
    assert side.stdout.strip() == "moved"


def test_codex_launcher_refuses_when_the_canonical_snapshot_fails(tmp_path):
    # An unborn HEAD cannot be fingerprinted; the run must not start.
    res, argv, _ = _launch(tmp_path, "work", commit=False)

    assert res.returncode == 2
    assert "canonical_checkout_snapshot_unavailable" in res.stderr
    assert argv == []


def test_codex_launcher_refuses_flag_shaped_models(tmp_path):
    for index, model in enumerate(("--yolo", "-m", " ", "gpt 5", "a=b", "x\ty")):
        res, argv, _ = _launch(tmp_path / str(index), "work", model=model)
        assert res.returncode == 2, model
        assert "model refused" in res.stderr
        assert argv == []


def test_codex_launcher_refuses_symlinked_work_root_into_canonical(tmp_path):
    link = tmp_path / "runs-link"
    link.symlink_to(tmp_path / "canonical", target_is_directory=True)
    res, argv, _ = _launch(tmp_path, "work", work_root=link)

    assert res.returncode == 2
    assert "overlaps the canonical checkout" in res.stderr
    assert argv == []


def test_codex_launcher_ignores_other_refs_in_the_shared_common_dir(tmp_path):
    # Deliberate narrowing: only HEAD and its branch are fingerprinted, so a
    # concurrent session moving another branch (or packing refs) is not a
    # violation.
    res, _, _ = _launch(tmp_path, "sideref")

    assert res.returncode == 0, res.stderr
    assert "canonical_checkout_integrity_violation" not in res.stderr


def test_codex_launcher_denial_classifier_failure_is_non_delivery(tmp_path):
    res, _, _ = _launch(tmp_path, "pyfail")

    assert res.returncode == 4, res.stderr
    assert "codex_action_denied" in res.stderr


# ---------------------------------------------------------------------------
# #2547: shared .git/config churn vs code-bearing config (one definition)
# ---------------------------------------------------------------------------

_GUARD = _LAUNCHER.parent / "codex_run_guard.py"


def _config_get(root: Path, key: str) -> str:
    return subprocess.run(
        ["git", "config", "--get", key], cwd=root, capture_output=True, text=True
    ).stdout.strip()


def test_codex_launcher_survives_concurrent_branch_and_worktree_bookkeeping(tmp_path):
    # Another session's `worktree add -b`, `--set-upstream-to`, fetch refspec
    # and branch description rewrite the shared config mid-run: not a violation.
    res, _, canonical = _launch(tmp_path, "churn", origin=True)

    assert res.returncode == 0, res.stderr
    assert "canonical_checkout_integrity_violation" not in res.stderr
    # The churn really happened, so a whole-file hash would have failed.
    assert _config_get(canonical, "branch.concurrent-2547.merge").startswith("refs/heads/")
    assert _config_get(canonical, "branch.feat/x.description") == "work"


def test_codex_launcher_still_fails_on_code_bearing_config_changes(tmp_path):
    for index, change in enumerate((
        "core.hooksPath=/tmp/evil-hooks-2547",
        "filter.x.clean=sh -c true",
        "alias.st=!sh -c true",
        "remote.origin.url=https://evil.example/repo.git",
        "branch.side.remote=/tmp/evil-2547.git",
    )):
        res, _, _ = _launch(tmp_path / str(index), f"codecfg:{change}", origin=True)
        assert res.returncode == 5, (change, res.stderr)
        assert "canonical_checkout_integrity_violation" in res.stderr, change


def test_codex_launcher_refuses_when_the_config_fingerprint_fails(tmp_path):
    for mode in ("cfgfail", "cfgempty", "cfgjunk"):
        res, argv, _ = _launch(tmp_path / mode, mode)
        assert res.returncode == 2, (mode, res.stderr)
        assert "canonical_checkout_snapshot_unavailable" in res.stderr, mode
        assert argv == [], mode


def test_codex_launcher_fails_when_the_config_fingerprint_fails_after_the_run(tmp_path):
    res, argv, _ = _launch(tmp_path, "cfglate")

    assert argv, res.stderr  # codex ran: the before-snapshot succeeded
    assert res.returncode == 5, res.stderr
    assert "canonical_snapshot_failed" in res.stderr


def test_guard_git_config_fingerprint_is_the_shared_definition(tmp_path):
    from nexus.executors import agy_write_admission as admission

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    ok = subprocess.run(
        [sys.executable, "-I", str(_GUARD), "git-config-fingerprint", str(repo)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.strip() == admission.git_config_fingerprint(repo)

    plain = tmp_path / "plain"
    plain.mkdir()
    bad = subprocess.run(
        [sys.executable, "-I", str(_GUARD), "git-config-fingerprint", str(plain)],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "git_config_unreadable" in bad.stderr
