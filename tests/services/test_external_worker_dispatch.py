from __future__ import annotations

import os
import stat
import subprocess
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
