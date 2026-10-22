from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-external-worker-dispatch"
os.environ["NEXUS_EXTERNAL_WORKER_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_external_worker_dispatch_test", str(DISPATCH_PATH)).load_module()


def _fake_cline(path: Path, *, sleep_seconds: float = 0.0, exit_code: int = 0) -> None:
    body = f"""#!/bin/sh
sleep {sleep_seconds}
cat <<'EOF'
{{"type":"run_start","providerId":"cline","modelId":"cline-free/mimo-v2.6-flash","taskId":"task-fixture"}}
{{"type":"run_result","finishReason":"completed","text":"ok","model":{{"provider":"cline","id":"cline-free/mimo-v2.6-flash"}},"usage":{{"totalCost":0}},"taskId":"task-fixture"}}
EOF
exit {exit_code}
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.mark.parametrize(("mode", "sweep_ready"), [("act", True), ("plan", True), ("act", False)])
def test_codex_operation_has_run_boundary_and_sweeps_setsid_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, sweep_ready: bool
) -> None:
    fake = tmp_path / "codex"
    marker = tmp_path / "escaped-child"
    observed = tmp_path / "codex-env"
    child_pid = tmp_path / "child-pid"
    child_ready = tmp_path / "child-ready"
    child_code = (
        "import os,time; os.setsid(); "
        f"open({str(child_ready)!r}, 'w').close(); "
        f"time.sleep(1.5); open({str(marker)!r}, 'w').write('escaped')"
    )
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli test')\n"
        "    sys.exit(0)\n"
        f"Path({str(observed)!r}).write_text(json.dumps({{'HOME': os.environ.get('HOME'), 'CODEX_HOME': os.environ.get('CODEX_HOME'), 'LEAK': os.environ.get('NEXUS_PRIVATE_TOKEN'), 'argv': sys.argv}}))\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"Path({str(child_pid)!r}).write_text(str(child.pid))\n"
        f"while not Path({str(child_ready)!r}).exists(): time.sleep(0.01)\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'thread-1'}))\n"
        "print(json.dumps({'type': 'turn.started'}))\n"
        "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'OK'}}))\n"
        "print(json.dumps({'type': 'turn.completed'}))\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(fake))
    monkeypatch.setenv("HOME", str(tmp_path / "host-home"))
    work = tmp_path / "wt"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    monkeypatch.setenv("NEXUS_PRIVATE_TOKEN", "must-not-reach-child")
    # The test sandbox denies ps/lsof; exercise the dispatch-to-sweep facade
    # with a real detached child and a deterministic process probe.
    monkeypatch.setattr(
        dispatch._cli_worker, "sweep_baseline", lambda: object() if sweep_ready else None
    )
    monkeypatch.setattr(dispatch._cli_worker, "track_run", lambda tag, pid: (tag, pid))

    def sweep_detached_child(tag, tracker, baseline, roots):
        assert tag == tracker[0]
        assert str(work) in roots
        pid = int(child_pid.read_text(encoding="utf-8"))
        os.kill(pid, signal.SIGKILL)
        return True

    monkeypatch.setattr(dispatch._cli_worker, "sweep_run", sweep_detached_child)

    root = tmp_path / "ops"
    journal = dispatch._journal("codex", root)
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(work),
        provider="codex",
        model="gpt-5.6-luna",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
        initial_fields={"mode": mode, "auto_approve": False, "require_free": False},
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "Reply exactly OK")
    code = dispatch._run_operation(
        operation_id=operation_id,
        provider="codex",
        model="gpt-5.6-luna",
        prompt_file=str(prompt_path),
        cwd=str(work),
        mode=mode,
        auto_approve=False,
        timeout_seconds=5,
        require_free=False,
        thinking="medium",
        operation_root=root,
    )
    if not sweep_ready:
        assert code == 1
        assert journal.read(operation_id)["failure_kind"] == "CODEX_DESCENDANT_SWEEP_UNAVAILABLE"
        assert not observed.exists()
        return
    assert code == 0, journal.read(operation_id).get("failure_kind")
    assert journal.read(operation_id)["status"] == "COMPLETED"
    command = journal.read(operation_id)
    assert command["mode"] == mode
    env = json.loads(observed.read_text(encoding="utf-8"))
    assert env["HOME"] != str(tmp_path / "host-home")
    assert env["CODEX_HOME"] == str(Path(env["HOME"]) / ".codex")
    assert env["LEAK"] is None
    assert env["argv"][env["argv"].index("--sandbox") + 1] == (
        "workspace-write" if mode == "act" else "read-only"
    )
    time.sleep(1.7)
    assert not marker.exists()


def _codex_op(tmp_path: Path, cwd: Path, root_name: str = "ops"):
    root = tmp_path / root_name
    journal = dispatch._journal("codex", root)
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(cwd),
        provider="codex",
        model="gpt-5.6-luna",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
        initial_fields={"mode": "act", "auto_approve": False, "require_free": False},
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "x")
    kwargs = dict(
        operation_id=operation_id,
        provider="codex",
        model="gpt-5.6-luna",
        prompt_file=str(prompt_path),
        cwd=str(cwd),
        mode="act",
        auto_approve=False,
        timeout_seconds=5,
        require_free=False,
        thinking="medium",
        operation_root=root,
    )
    return journal, operation_id, kwargs


@pytest.mark.parametrize(
    ("inner_code", "clean", "expect_write_back"),
    [(0, True, True), (1, True, False), (0, False, False)],
)
def test_codex_refreshed_auth_written_back_only_on_clean_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    inner_code: int,
    clean: bool,
    expect_write_back: bool,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "host-home"))
    work = tmp_path / "wt"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    _journal, _op, kwargs = _codex_op(tmp_path, work)
    calls: list[Path] = []
    monkeypatch.setattr(dispatch._codex_boundary, "materialize_codex_home", lambda home: None)
    monkeypatch.setattr(
        dispatch._codex_boundary, "write_back_refreshed_auth", lambda home: calls.append(home)
    )
    monkeypatch.setattr(dispatch, "_run_operation_inner", lambda **_kw: inner_code)
    monkeypatch.setattr(dispatch, "_codex_run_clean", lambda *_a: clean)
    assert dispatch._run_operation(**kwargs) == inner_code
    assert bool(calls) is expect_write_back


def test_codex_cwd_home_and_main_clone_refused_linked_worktree_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "host-home"
    (home / "workspace").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    git = lambda *a, cwd: subprocess.run(  # noqa: E731
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    main = home / "workspace" / "repo"
    main.mkdir()
    git("init", "-q", cwd=main)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=main)
    linked = home / "workspace" / "wt-linked"
    git("worktree", "add", "-q", str(linked), cwd=main)
    scratch = tmp_path / "scratch-clone"
    scratch.mkdir()
    git("init", "-q", cwd=scratch)
    plain = tmp_path / "plain"
    plain.mkdir()
    refused = "CODEX_CWD_NOT_DISPOSABLE_WORKTREE"
    assert dispatch._codex_cwd_refusal(str(home)) == refused
    assert dispatch._codex_cwd_refusal(str(tmp_path)) == refused
    assert dispatch._codex_cwd_refusal(str(plain)) == refused
    assert dispatch._codex_cwd_refusal(str(main)) == refused
    assert dispatch._codex_cwd_refusal(str(linked)) is None
    assert dispatch._codex_cwd_refusal(str(scratch)) is None

    journal, op, kwargs = _codex_op(tmp_path, main, "ops2")
    monkeypatch.setattr(
        dispatch, "_run_operation_inner", lambda **_kw: pytest.fail("provider must not start")
    )
    assert dispatch._run_operation(**kwargs) == 1
    assert journal.read(op)["failure_kind"] == refused


def test_codex_cwd_case_variant_paths_are_judged_by_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "host-home"
    (home / "workspace").mkdir(parents=True)
    if not (home / "Workspace").exists():
        # Case-sensitive filesystem (Linux CI): emulate the alias spelling with
        # a symlink so the identity checks are exercised on every platform.
        (home / "Workspace").symlink_to(home / "workspace", target_is_directory=True)
    monkeypatch.setenv("HOME", str(home))

    def git(*a: str, cwd: Path) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    main = home / "workspace" / "repo"
    main.mkdir()
    git("init", "-q", cwd=main)
    git("commit", "-q", "--allow-empty", "-m", "i", cwd=main)
    linked = home / "workspace" / "wt-linked"
    git("worktree", "add", "-q", str(linked), cwd=main)
    refused = "CODEX_CWD_NOT_DISPOSABLE_WORKTREE"
    assert dispatch._codex_cwd_refusal(str(home / "Workspace" / "repo")) == refused
    assert dispatch._codex_cwd_refusal(str(home / "Workspace" / "wt-linked")) is None
    assert dispatch._canonical_path(str(home / "Workspace" / "wt-linked")) == str(linked.resolve())

    seen: dict[str, object] = {}
    monkeypatch.setattr(dispatch._codex_boundary, "materialize_codex_home", lambda h: None)
    monkeypatch.setattr(dispatch, "_run_operation_inner", lambda **kw: seen.update(kw) or 0)
    monkeypatch.setattr(dispatch, "_codex_run_clean", lambda *_a: False)
    _journal, _op, kwargs = _codex_op(tmp_path, linked, "ops3")
    kwargs["cwd"] = str(home / "Workspace" / "wt-linked")
    assert dispatch._run_operation(**kwargs) == 0
    assert seen["cwd"] == str(linked.resolve())


def test_background_cline_operation_reaches_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "cline"
    _fake_cline(fake)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(fake))

    root = tmp_path / "ops"
    record = dispatch._spawn_background(
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=10,
        require_free=True,
        thinking="none",
        operation_root=root,
    )
    operation_id = record["operation_id"]

    deadline = time.time() + 5
    journal = dispatch._journal("cline", root)
    while time.time() < deadline:
        current = journal.read(operation_id)
        if current["status"] in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            break
        time.sleep(0.05)

    current = journal.read(operation_id)
    assert current["status"] == "COMPLETED"
    assert current["observed_provider"] == "cline"
    assert current["observed_model"] == "cline-free/mimo-v2.6-flash"
    assert current["total_cost"] == 0.0
    assert current["provider_session_id"] == "task-fixture"
    assert current["reconciliation"]["retry_permitted"] is False
    assert not journal.prompt_path(operation_id).exists()


def test_outer_timeout_is_outcome_unknown_and_never_retry_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "cline"
    _fake_cline(fake, sleep_seconds=5)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(fake))

    root = tmp_path / "ops"
    journal = dispatch._journal("cline", root)
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        effort="none",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
        initial_fields={
            "mode": "plan",
            "auto_approve": False,
            "require_free": True,
        },
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "timeout")

    code = dispatch._run_operation(
        operation_id=operation_id,
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=1,
        require_free=True,
        thinking="none",
        operation_root=root,
        heartbeat_interval=0.1,
        outer_grace_seconds=0.1,
    )
    current = journal.read(operation_id)
    assert code == 124
    assert current["status"] == "OUTCOME_UNKNOWN"
    assert current["failure_kind"] == "WRAPPER_WALL_TIMEOUT_AFTER_PROVIDER_START"
    assert current["reconciliation"]["retry_permitted"] is False


def test_operation_id_infers_provider_for_status(tmp_path: Path) -> None:
    journal = dispatch._journal("cline", tmp_path / "ops")
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        effort="none",
        prompt_sha256="0" * 64,
        runtime_revision=None,
    )
    assert dispatch._provider_from_operation_id(operation_id) == "cline"


def test_runtime_revision_prefers_actual_snapshot_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    release = runtime / "releases" / "bundle-a"
    snapshot = release / "snapshot"
    snapshot.mkdir(parents=True)
    (release / "host-generation.json").write_text(
        '{"source_revision":"' + "b" * 40 + '"}\n',
        encoding="utf-8",
    )
    current = runtime / "current"
    current.symlink_to(release)
    monkeypatch.setattr(dispatch, "SNAPSHOT", current / "snapshot")

    assert dispatch._runtime_revision() == "b" * 40


def _fake_opencode(path: Path) -> None:
    body = """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo 1.18.32
  exit 0
fi
# Regression guard: RDC/generic runner must close stdin. If stdin remains open
# like an interactive pipe, OpenCode waits before dispatch and this test fails.
if read unexpected; then
  echo "unexpected stdin: $unexpected" >&2
  exit 9
fi
cat <<'EOF'
{"type":"step_start","sessionID":"ses_fake","part":{"type":"step-start"}}
{"type":"text","sessionID":"ses_fake","part":{"type":"text","text":"ok"}}
{"type":"step_finish","sessionID":"ses_fake","part":{"type":"step-finish","reason":"stop","cost":0}}
EOF
exit 0
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_background_opencode_receives_stdin_eof_and_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "opencode"
    _fake_opencode(fake)
    monkeypatch.setenv("NEXUS_OPENCODE_BIN", str(fake))

    root = tmp_path / "ops"
    record = dispatch._spawn_background(
        provider="opencode",
        model="opencode/mimo-v2.6-flash-free",
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=10,
        require_free=True,
        thinking="none",
        operation_root=root,
    )
    operation_id = record["operation_id"]

    deadline = time.time() + 5
    journal = dispatch._journal("opencode", root)
    while time.time() < deadline:
        current = journal.read(operation_id)
        if current["status"] in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            break
        time.sleep(0.05)

    current = journal.read(operation_id)
    assert current["status"] == "COMPLETED"
    assert current["observed_provider"] == "opencode"
    assert current["observed_model"] == "opencode/mimo-v2.6-flash-free"
    assert current["total_cost"] == 0.0
    assert current["provider_session_id"] == "ses_fake"
    assert current["reconciliation"]["retry_permitted"] is False
    assert not journal.prompt_path(operation_id).exists()


def _fake_grok_with_profile_failover(path: Path) -> None:
    body = """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "grok 1.0.41"
  exit 0
fi
if [ -f "$HOME/fail-auth" ]; then
  echo '{"error":"You are not authenticated."}'
  exit 1
fi
echo '{"model":"grok-4.5","session_id":"grok-session-ok","finish_reason":"stop","text":"OK"}'
exit 0
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_background_grok_rotates_once_with_same_operation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "grok"
    _fake_grok_with_profile_failover(fake)
    monkeypatch.setenv("NEXUS_GROK_BIN", str(fake))

    pool_root = tmp_path / "grok-pool"
    first_home = tmp_path / "profile-a"
    second_home = tmp_path / "profile-b"
    first_home.mkdir()
    second_home.mkdir()
    (first_home / "fail-auth").write_text("1", encoding="utf-8")
    pool_root.mkdir()
    (pool_root / "state.json").write_text(
        __import__("json").dumps({
            "accounts": {
                "a-first": {
                    "home_path": str(first_home),
                    "enabled": True,
                    "cooldown_until": 0.0,
                    "last_failure_reason": "",
                    "last_failure_timestamp": 0.0,
                },
                "b-second": {
                    "home_path": str(second_home),
                    "enabled": True,
                    "cooldown_until": 0.0,
                    "last_failure_reason": "",
                    "last_failure_timestamp": 0.0,
                },
            },
            "active_alias": "a-first",
            "updated_at": 0.0,
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_GROK_ACCOUNT_POOL_ROOT", str(pool_root))
    from nexus.services.grok_account_pool import (
        GrokAccountPoolManager,
        set_grok_account_pool_manager,
    )

    GrokAccountPoolManager(pool_root).bind_host(confirm_existing_pool=True)
    set_grok_account_pool_manager(None)
    root = tmp_path / "ops"
    record = dispatch._spawn_background(
        provider="grok",
        model="grok-4.5",
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=10,
        require_free=False,
        thinking="none",
        operation_root=root,
    )
    operation_id = record["operation_id"]

    deadline = time.time() + 5
    journal = dispatch._journal("grok", root)
    while time.time() < deadline:
        current = journal.read(operation_id)
        if current["status"] in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            break
        time.sleep(0.05)

    current = journal.read(operation_id)
    assert current["operation_id"] == operation_id
    assert current["status"] == "COMPLETED"
    assert current["attempts"] == 2
    assert current["rotations"] == 1
    assert current["observed_provider"] == "grok"
    assert current["observed_model"] == "grok-4.5"
    assert current["provider_session_id"] == "grok-session-ok"
    assert current["reconciliation"]["retry_permitted"] is False
    state = __import__("json").loads((pool_root / "state.json").read_text())
    assert state["accounts"]["a-first"]["last_failure_reason"] == "AUTH_OR_SESSION_INVALID"
    assert state.get("leases", {}) == {}
    set_grok_account_pool_manager(None)


def test_runtime_revision_binds_explicit_snapshot_git_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "snapshot"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Snapshot Test"],
        check=True,
    )
    (repo / "README.md").write_text("snapshot\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "snapshot"], check=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    monkeypatch.setenv("NEXUS_EXTERNAL_WORKER_SNAPSHOT", str(repo))
    monkeypatch.setattr(dispatch, "SNAPSHOT", repo)

    assert dispatch._runtime_revision() == head


def _fake_claude_cli(path: Path, *, terminal: bool) -> None:
    result = (
        """echo '{"type":"result","subtype":"success","is_error":false,"session_id":"cs-1","total_cost_usd":0.01,"result":"ok"}'"""
        if terminal
        else "true"
    )
    path.write_text(
        f"""#!/bin/sh
case "$1" in
  --version) echo "2.1.296 (Claude Code)"; exit 0;;
  auth) echo '{{"loggedIn":true,"authMethod":"claude.ai","configDirectory":"'"$CLAUDE_CONFIG_DIR"'","accountUuid":"acct-1","organizationUuid":"org-1"}}'; exit 0;;
esac
echo '{{"type":"system","subtype":"init","model":"claude-sonnet-5-5","session_id":"cs-1"}}'
{result}
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_claude_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, terminal: bool):
    import json

    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolManager,
        identity_fingerprint,
        set_claude_account_pool_manager,
    )

    fake = tmp_path / "claude"
    _fake_claude_cli(fake, terminal=terminal)
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(fake))
    pool_root = tmp_path / "claude-pool"
    monkeypatch.setenv("NEXUS_CLAUDE_ACCOUNT_POOL_DIR", str(pool_root))
    home = tmp_path / "cfg-a"
    home.mkdir(mode=0o700)
    ClaudeAccountPoolManager(pool_root).register_local_profile(
        alias="claude-a",
        config_dir=home,
        approved_identity_fingerprint=identity_fingerprint("acct-1", "org-1"),
    )
    set_claude_account_pool_manager(None)
    root = tmp_path / "ops"
    record = dispatch._spawn_background(
        provider="claude",
        model="sonnet",
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=10,
        require_free=False,
        thinking="none",
        operation_root=root,
    )
    journal = dispatch._journal("claude", root)
    deadline = time.time() + 10
    while time.time() < deadline:
        current = journal.read(record["operation_id"])
        if current["status"] in {"COMPLETED", "FAILED", "OUTCOME_UNKNOWN"}:
            break
        time.sleep(0.05)
    state = json.loads((pool_root / "state.json").read_text())
    return record["operation_id"], journal.read(record["operation_id"]), state


def test_background_claude_success_attests_and_releases_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_id, current, state = _run_claude_operation(tmp_path, monkeypatch, terminal=True)
    assert operation_id.startswith("claudeop_")
    assert current["status"] == "COMPLETED"
    assert current["observed_provider"] == "claude"
    assert current["observed_model"] == "claude-sonnet-5-5"
    assert current["provider_session_id"] == "cs-1"
    assert state["leases"] == {}


def test_background_claude_no_terminal_result_keeps_lease_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, current, state = _run_claude_operation(tmp_path, monkeypatch, terminal=False)
    assert current["status"] == "OUTCOME_UNKNOWN"
    assert current["reconciliation"]["retry_permitted"] is False
    assert current["rotations"] == 0
    (lease,) = state["leases"].values()
    assert lease["unknown_outcome"] is True


def _claude_inproc_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script_tail: str):
    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolManager,
        identity_fingerprint,
        set_claude_account_pool_manager,
    )

    fake = tmp_path / "claude"
    _fake_claude_cli(fake, terminal=True)
    text = fake.read_text().replace(
        'echo \'{"type":"system"', script_tail + '\necho \'{"type":"system"', 1
    )
    fake.write_text(text)
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(fake))
    pool_root = tmp_path / "claude-pool"
    monkeypatch.setenv("NEXUS_CLAUDE_ACCOUNT_POOL_DIR", str(pool_root))
    home = tmp_path / "cfg-a"
    home.mkdir(mode=0o700)
    ClaudeAccountPoolManager(pool_root).register_local_profile(
        alias="claude-a",
        config_dir=home,
        approved_identity_fingerprint=identity_fingerprint("acct-1", "org-1"),
    )
    set_claude_account_pool_manager(None)
    root = tmp_path / "ops"
    journal = dispatch._journal("claude", root)
    operation_id = journal.new_operation_id()
    import hashlib

    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="claude",
        model="sonnet",
        effort="none",
        prompt_sha256=hashlib.sha256(b"hello").hexdigest(),
        runtime_revision=None,
        initial_fields={"mode": "plan", "auto_approve": False, "require_free": False},
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "hello")
    return journal, operation_id, prompt_path, root, pool_root


def _run_claude_inproc(tmp_path, operation_id, prompt_path, root, timeout=30, grace=1.0):
    return dispatch._run_operation(
        operation_id=operation_id,
        provider="claude",
        model="sonnet",
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=timeout,
        require_free=False,
        thinking="none",
        operation_root=root,
        heartbeat_interval=1.0,
        outer_grace_seconds=grace,
    )


def _pids_of(path: Path) -> int:
    return int(path.read_text())


def test_claude_supervision_failure_kills_provider_and_holds_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services import external_worker_runtime as runtime
    from nexus.services.claude_account_pool import set_claude_account_pool_manager

    pid_file = tmp_path / "provider.pid"
    original_attach = runtime.ClaudeAccountAdapter.attach_provider

    def boom(self, binding, provider_pid):
        pid_file.write_text(str(provider_pid))
        original_attach(self, binding, provider_pid)
        raise RuntimeError("supervision exploded")

    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "attach_provider", boom)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "sleep 30"
    )
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
    finally:
        set_claude_account_pool_manager(None)
    current = journal.read(operation_id)
    assert current["status"] == "OUTCOME_UNKNOWN"
    assert current["failure_kind"].startswith("PROVIDER_SUPERVISION_FAILED_UNKNOWN_OUTCOME")
    with pytest.raises(ProcessLookupError):
        os.killpg(_pids_of(pid_file), 0)
    state = json.loads((pool_root / "state.json").read_text())
    (lease,) = state["leases"].values()
    assert lease["unknown_outcome"] is True


def test_claude_wall_timeout_holds_lease_until_reconcile_and_kills_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services import external_worker_runtime as runtime
    from nexus.services.claude_account_pool import (
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    pid_file = tmp_path / "provider.pid"
    original_attach = runtime.ClaudeAccountAdapter.attach_provider

    def record_pid(self, binding, provider_pid):
        pid_file.write_text(str(provider_pid))
        original_attach(self, binding, provider_pid)

    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "attach_provider", record_pid)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "sleep 60"
    )
    try:
        code = _run_claude_inproc(tmp_path, operation_id, prompt_path, root, timeout=1, grace=0.0)
        assert code == 124
        current = journal.read(operation_id)
        assert current["status"] == "OUTCOME_UNKNOWN"
        with pytest.raises(ProcessLookupError):
            os.killpg(_pids_of(pid_file), 0)
        manager = get_claude_account_pool_manager()
        (lease_id,) = manager.unknown_outcome_leases()
        assert json.loads((pool_root / "state.json").read_text())["leases"][lease_id][
            "unknown_outcome"
        ]
        manager.reconcile_release(lease_id)
        assert json.loads((pool_root / "state.json").read_text())["leases"] == {}
    finally:
        set_claude_account_pool_manager(None)


def test_dispatch_hold_failure_never_releases_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services import external_worker_runtime as runtime
    from nexus.services.claude_account_pool import set_claude_account_pool_manager

    released: list[str] = []

    def failing_hold(self, binding):
        raise RuntimeError("hold failed")

    def tracking_release(self, binding):
        released.append("release")

    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "hold_unknown_outcome", failing_hold)
    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "release", tracking_release)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "sleep 60"
    )
    try:
        code = _run_claude_inproc(tmp_path, operation_id, prompt_path, root, timeout=1, grace=0.0)
    finally:
        set_claude_account_pool_manager(None)
    assert code == 124
    assert released == []
    assert journal.read(operation_id)["status"] == "OUTCOME_UNKNOWN"


def _kill_dispatcher_pid_in_state(pool_root: Path) -> None:
    import json

    done = subprocess.Popen(["true"])
    done.wait()
    state = json.loads((pool_root / "state.json").read_text())
    for record in state["leases"].values():
        record["pid"] = done.pid
    (pool_root / "state.json").write_text(json.dumps(state))


def test_claude_failing_hold_with_dead_processes_still_blocks_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from nexus.services import external_worker_runtime as runtime
    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolExhaustedError,
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    def failing_hold(self, binding):
        raise RuntimeError("hold failed")

    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "hold_unknown_outcome", failing_hold)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "sleep 60"
    )
    try:
        assert (
            _run_claude_inproc(tmp_path, operation_id, prompt_path, root, timeout=1, grace=0.0)
            == 124
        )
        _kill_dispatcher_pid_in_state(pool_root)
        manager = get_claude_account_pool_manager()
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            manager.acquire("claudeop_" + "9" * 32)
        capsys.readouterr()
        assert dispatch.main(["--claude-list-unknown"]) == 0
        listed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert len(listed["unknown_outcome_leases"]) == 1
    finally:
        set_claude_account_pool_manager(None)


def test_claude_interpret_exception_kills_group_and_blocks_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services import external_worker_runtime as runtime
    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolExhaustedError,
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    pid_file = tmp_path / "provider.pid"
    original_attach = runtime.ClaudeAccountAdapter.attach_provider

    def record_pid(self, binding, provider_pid):
        pid_file.write_text(str(provider_pid))
        original_attach(self, binding, provider_pid)

    def broken_interpret(self, request, **kwargs):
        raise ValueError("interpret exploded")

    monkeypatch.setattr(runtime.ClaudeAccountAdapter, "attach_provider", record_pid)
    monkeypatch.setattr(runtime.ClaudeExecutionAdapter, "interpret", broken_interpret)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
        current = journal.read(operation_id)
        assert current["status"] == "OUTCOME_UNKNOWN"
        assert current["failure_kind"].endswith("ValueError")
        with pytest.raises(ProcessLookupError):
            os.killpg(_pids_of(pid_file), 0)
        _kill_dispatcher_pid_in_state(pool_root)
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32)
        (lease,) = json.loads((pool_root / "state.json").read_text())["leases"].values()
        assert lease["unknown_outcome"] is True
    finally:
        set_claude_account_pool_manager(None)


def test_claude_clean_success_releases_and_account_is_reusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services.claude_account_pool import (
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 0
        assert journal.read(operation_id)["status"] == "COMPLETED"
        assert json.loads((pool_root / "state.json").read_text())["leases"] == {}
        assert get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32).lease_id
    finally:
        set_claude_account_pool_manager(None)


def test_claude_quota_terminal_failure_cools_down_account_for_next_acquire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolExhaustedError,
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    fake = tmp_path / "claude"
    fake.write_text(
        fake.read_text().replace(
            '"subtype":"success","is_error":false,"session_id":"cs-1","total_cost_usd":0.01,"result":"ok"',
            '"subtype":"error","is_error":true,"session_id":"cs-1","result":"Claude usage limit reached"',
        )
    )
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) != 0
        current = journal.read(operation_id)
        assert current["status"] == "FAILED"
        assert current["failure_kind"] == "QUOTA_EXHAUSTED"
        assert current["rotations"] == 0
        state = json.loads((pool_root / "state.json").read_text())
        assert state["leases"] == {}
        assert state["accounts"]["claude-a"]["last_failure_reason"] == "QUOTA_EXHAUSTED"
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32)
    finally:
        set_claude_account_pool_manager(None)


def test_claude_popen_failure_is_pre_effect_and_account_reusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nexus.services.claude_account_pool import (
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    real_execute_child = subprocess.Popen._execute_child

    def failing_execute_child(self, args, *rest, **kwargs):
        if "--output-format" in list(args):
            raise OSError("fork failed")
        return real_execute_child(self, args, *rest, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "_execute_child", failing_execute_child)
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
        current = journal.read(operation_id)
        assert current["status"] == "FAILED"
        assert current["failure_kind"] == "PROVIDER_START_FAILED:OSError"
        assert json.loads((pool_root / "state.json").read_text())["leases"] == {}
        manager = get_claude_account_pool_manager()
        assert manager.unknown_outcome_leases() == ()
        assert manager.acquire("claudeop_" + "9" * 32).lease_id
    finally:
        set_claude_account_pool_manager(None)


def _claude_result_text(tmp_path: Path, result: str) -> None:
    fake = tmp_path / "claude"
    fake.write_text(
        fake.read_text().replace(
            '"subtype":"success","is_error":false,"session_id":"cs-1","total_cost_usd":0.01,"result":"ok"',
            '"subtype":"error","is_error":true,"session_id":"cs-1","result":"' + result + '"',
        )
    )


def test_claude_rotation_heartbeat_failure_records_unknown_and_holds_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 1: a journal failure at ACCOUNT_ROTATING must not escape unrecorded."""

    import json

    from nexus.services.claude_account_pool import set_claude_account_pool_manager
    from nexus.services.direct_operation_journal import DirectOperationJournal

    original_heartbeat = DirectOperationJournal.heartbeat

    def failing_rotation_heartbeat(self, operation_id, *, phase=None, **kwargs):
        if phase == "ACCOUNT_ROTATING":
            raise OSError("journal disk full")
        return original_heartbeat(self, operation_id, phase=phase, **kwargs)

    monkeypatch.setattr(DirectOperationJournal, "heartbeat", failing_rotation_heartbeat)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    _claude_result_text(tmp_path, "Not logged in. Please run /login")
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
    finally:
        set_claude_account_pool_manager(None)
    current = journal.read(operation_id)
    assert current["status"] == "OUTCOME_UNKNOWN"
    assert current["failure_kind"].startswith("PROVIDER_SUPERVISION_FAILED_UNKNOWN_OUTCOME")
    assert current["reconciliation"]["retry_permitted"] is False
    (lease,) = json.loads((pool_root / "state.json").read_text())["leases"].values()
    assert lease["unknown_outcome"] is True


def test_claude_starting_heartbeat_failure_is_pre_effect_terminal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 1 (same class): PROVIDER_STARTING heartbeat failure leaves a terminal record."""

    import json

    from nexus.services.claude_account_pool import set_claude_account_pool_manager
    from nexus.services.direct_operation_journal import DirectOperationJournal

    original_heartbeat = DirectOperationJournal.heartbeat

    def failing_start_heartbeat(self, operation_id, *, phase=None, **kwargs):
        if phase == "PROVIDER_STARTING":
            raise OSError("journal disk full")
        return original_heartbeat(self, operation_id, phase=phase, **kwargs)

    monkeypatch.setattr(DirectOperationJournal, "heartbeat", failing_start_heartbeat)
    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
    finally:
        set_claude_account_pool_manager(None)
    current = journal.read(operation_id)
    assert current["status"] == "FAILED"
    assert current["failure_kind"] == "JOURNAL_HEARTBEAT_FAILED:OSError"
    assert current["reconciliation"]["result"] == "NO_PROVIDER_PROCESS_STARTED"
    assert json.loads((pool_root / "state.json").read_text())["leases"] == {}


def _fail_cooldown_writes(monkeypatch: pytest.MonkeyPatch, *, failures: int) -> list[int]:
    from nexus.services.claude_account_pool import ClaudeAccountPoolManager

    original_write = ClaudeAccountPoolManager._write_state
    calls: list[int] = []

    def flaky_write(self, state):
        cooling = any(
            isinstance(a, dict) and a.get("last_failure_reason") == "QUOTA_EXHAUSTED"
            for a in state.get("accounts", {}).values()
        )
        if cooling and len(calls) < failures:
            calls.append(1)
            raise OSError("transient state write failure")
        return original_write(self, state)

    monkeypatch.setattr(ClaudeAccountPoolManager, "_write_state", flaky_write)
    return calls


def test_claude_quota_cooldown_write_failure_keeps_account_ineligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 2: a failed cooldown write must not leave the account immediately eligible."""

    import json

    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolExhaustedError,
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    _claude_result_text(tmp_path, "Claude usage limit reached")
    _fail_cooldown_writes(monkeypatch, failures=10**6)
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) != 0
        current = journal.read(operation_id)
        assert current["status"] == "FAILED"
        assert current["failure_kind"] == "QUOTA_EXHAUSTED"
        _kill_dispatcher_pid_in_state(pool_root)
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32)
        assert len(json.loads((pool_root / "state.json").read_text())["leases"]) == 1
        assert current["reconciliation"]["account_release"] == "LEASE_HELD_COOLDOWN_PERSIST_FAILED"
    finally:
        set_claude_account_pool_manager(None)


def test_claude_quota_cooldown_write_transient_failure_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 2: one transient failure is retried; cooldown persists and lease frees."""

    import json

    from nexus.services.claude_account_pool import (
        ClaudeAccountPoolExhaustedError,
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    _claude_result_text(tmp_path, "Claude usage limit reached")
    calls = _fail_cooldown_writes(monkeypatch, failures=1)
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) != 0
        assert calls == [1]
        current = journal.read(operation_id)
        assert current["status"] == "FAILED"
        state = json.loads((pool_root / "state.json").read_text())
        assert state["leases"] == {}
        assert state["accounts"]["claude-a"]["last_failure_reason"] == "QUOTA_EXHAUSTED"
        assert state["accounts"]["claude-a"]["cooldown_until"] > time.time()
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32)
    finally:
        set_claude_account_pool_manager(None)


class _InterruptedDuringPopen(BaseException):
    """Stands in for e.g. KeyboardInterrupt raised inside Popen.__init__ after fork."""


def test_claude_exception_inside_popen_after_fork_kills_child_and_holds_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 4: Popen raising after the fork must not free the lease of a live child."""

    import json

    from nexus.services.claude_account_pool import set_claude_account_pool_manager

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "sleep 30"
    )
    real_execute_child = subprocess.Popen._execute_child
    forked: list[int] = []

    def interrupted_after_fork(self, args, *rest, **kwargs):
        real_execute_child(self, args, *rest, **kwargs)
        if "--output-format" in list(args):
            forked.append(self.pid)
            raise _InterruptedDuringPopen()

    monkeypatch.setattr(subprocess.Popen, "_execute_child", interrupted_after_fork)
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
    finally:
        set_claude_account_pool_manager(None)
    current = journal.read(operation_id)
    assert current["status"] == "OUTCOME_UNKNOWN"
    assert current["failure_kind"].endswith("_InterruptedDuringPopen")
    (child_pid,) = forked
    with pytest.raises(ProcessLookupError):
        os.killpg(child_pid, 0)
    (lease,) = json.loads((pool_root / "state.json").read_text())["leases"].values()
    assert lease["unknown_outcome"] is True


def test_claude_real_exec_failure_after_fork_is_pre_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 4: a child that failed to exec was reaped by CPython; no hold needed."""

    import json

    from nexus.services.claude_account_pool import (
        get_claude_account_pool_manager,
        set_claude_account_pool_manager,
    )

    journal, operation_id, prompt_path, root, pool_root = _claude_inproc_setup(
        tmp_path, monkeypatch, "true"
    )
    real_execute_child = subprocess.Popen._execute_child

    def missing_binary(self, args, *rest, **kwargs):
        if "--output-format" in list(args):
            args = [str(tmp_path / "missing-claude"), *list(args)[1:]]
        return real_execute_child(self, args, *rest, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "_execute_child", missing_binary)
    try:
        assert _run_claude_inproc(tmp_path, operation_id, prompt_path, root) == 1
        current = journal.read(operation_id)
        assert current["status"] == "FAILED"
        assert current["failure_kind"] == "PROVIDER_START_FAILED:FileNotFoundError"
        assert json.loads((pool_root / "state.json").read_text())["leases"] == {}
        assert get_claude_account_pool_manager().acquire("claudeop_" + "9" * 32).lease_id
    finally:
        set_claude_account_pool_manager(None)


def test_cline_exception_inside_popen_after_fork_is_unknown_not_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2389 item 4 (Codex r2): adapters without launch_pending never record FAILED/release."""

    import hashlib

    from nexus.services import external_worker_runtime as runtime

    fake = tmp_path / "cline"
    _fake_cline(fake)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(fake))
    released: list[str] = []
    original_get = runtime.get_account_adapter

    def tracking_get(provider):
        adapter = original_get(provider)
        original_release = adapter.release

        def tracking_release(binding):
            released.append("release")
            return original_release(binding)

        adapter.release = tracking_release
        return adapter

    monkeypatch.setattr(dispatch, "get_account_adapter", tracking_get)
    real_execute_child = subprocess.Popen._execute_child
    forked: list[int] = []

    def interrupted_after_fork(self, args, *rest, **kwargs):
        real_execute_child(self, args, *rest, **kwargs)
        if "--json" in list(args) and "--provider" in list(args):
            forked.append(self.pid)
            os.kill(self.pid, signal.SIGSTOP)  # keep the forked child alive and unreaped
            raise _InterruptedDuringPopen()

    monkeypatch.setattr(subprocess.Popen, "_execute_child", interrupted_after_fork)
    root = tmp_path / "ops"
    journal = dispatch._journal("cline", root)
    operation_id = journal.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        effort="none",
        prompt_sha256=hashlib.sha256(b"hello").hexdigest(),
        runtime_revision=None,
        initial_fields={"mode": "plan", "auto_approve": False, "require_free": True},
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "hello")
    code = dispatch._run_operation(
        operation_id=operation_id,
        provider="cline",
        model="cline-free/mimo-v2.6-flash",
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=30,
        require_free=True,
        thinking="none",
        operation_root=root,
        heartbeat_interval=1.0,
        outer_grace_seconds=1.0,
    )
    current = journal.read(operation_id)
    assert (code, current["status"], current["failure_kind"]) == (
        1,
        "OUTCOME_UNKNOWN",
        "PROVIDER_SUPERVISION_FAILED_UNKNOWN_OUTCOME:_InterruptedDuringPopen",
    )
    assert released == []
    (child_pid,) = forked
    with pytest.raises(ProcessLookupError):
        os.killpg(child_pid, 0)
