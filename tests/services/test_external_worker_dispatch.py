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
    from nexus.services.grok_account_pool import set_grok_account_pool_manager

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
