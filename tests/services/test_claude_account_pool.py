from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from nexus.services.claude_account_pool import (
    ClaudeAccountIdentityError,
    ClaudeAccountPoolError,
    ClaudeAccountPoolExhaustedError,
    ClaudeAccountPoolManager,
    build_claude_profile_env,
    classify_claude_failure,
    identity_fingerprint,
)
from nexus.services.external_account_pool import AccountFailureKind
from nexus.services.external_worker_runtime import (
    AccountBinding,
    ClaudeAccountAdapter,
    ClaudeExecutionAdapter,
    ExternalWorkerRuntimeError,
    WorkerRequest,
    get_account_adapter,
    get_execution_adapter,
)

ROOT = Path(__file__).resolve().parents[2]
HOST = "test-host-1"
SECRETS = {
    "ANTHROPIC_API_KEY": "sk-ant-SECRET-1",
    "ANTHROPIC_AUTH_TOKEN": "tok-SECRET-2",
    "ANTHROPIC_BASE_URL": "https://secret-base.invalid",
    "CLAUDE_CODE_OAUTH_TOKEN": "oauth-SECRET-3",
    "GH_TOKEN": "ghp_SECRET4",
    "GITHUB_TOKEN": "ghs_SECRET5",
    "OPENAI_API_KEY": "sk-SECRET6",
}


def _fp(name: str) -> str:
    return identity_fingerprint(f"acct-{name}", "org-1")


class FakeObserver:
    """Maps config dir -> observed fingerprint; missing key means unobservable."""

    def __init__(self) -> None:
        self.table: dict[str, str | None] = {}
        self.calls: list[Path] = []

    def __call__(self, config_dir: Path) -> str | None:
        self.calls.append(config_dir)
        return self.table.get(str(config_dir))


def _pool(tmp_path: Path, names: list[str], observer: FakeObserver | None = None):
    observer = observer or FakeObserver()
    root = tmp_path / "pool"
    manager = ClaudeAccountPoolManager(root, host_identity=HOST, identity_observer=observer)
    for name in names:
        home = tmp_path / f"cfg-{name}"
        home.mkdir(mode=0o700)
        manager.register_local_profile(
            alias=name, config_dir=home, approved_identity_fingerprint=_fp(name)
        )
        observer.table[str(home.resolve())] = _fp(name)
    return manager, observer, root


def _request(tmp_path: Path, *, mode: str = "plan", auto: bool = False) -> WorkerRequest:
    return WorkerRequest(
        provider="claude",
        model="sonnet",
        prompt="do the thing",
        cwd=str(tmp_path),
        mode=mode,
        auto_approve=auto,
        timeout_seconds=60,
    )


def _fake_claude(tmp_path: Path) -> Path:
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\necho '2.1.296 (Claude Code)'\n", encoding="utf-8")
    fake.chmod(0o755)
    return fake


# -- registry -------------------------------------------------------------
def test_registry_resolves_claude_adapters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_ACCOUNT_POOL_DIR", str(tmp_path / "p"))
    from nexus.services import claude_account_pool as mod

    mod.set_claude_account_pool_manager(None)
    try:
        assert isinstance(get_execution_adapter("claude"), ClaudeExecutionAdapter)
        assert isinstance(get_account_adapter("claude"), ClaudeAccountAdapter)
    finally:
        mod.set_claude_account_pool_manager(None)


def test_dispatch_prefix_registered() -> None:
    dispatch = SourceFileLoader(
        "nexus_dispatch_claude_test", str(ROOT / "scripts/ops/nexus-external-worker-dispatch")
    ).load_module()
    assert dispatch._PROVIDER_PREFIXES["claude"] == "claudeop_"
    assert dispatch._provider_from_operation_id("claudeop_" + "a" * 32) == "claude"


# -- leases ---------------------------------------------------------------
def test_two_profiles_distinct_dirs_and_leases_third_exhausted(tmp_path: Path) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    one = manager.acquire("claudeop_" + "1" * 32)
    two = manager.acquire("claudeop_" + "2" * 32)
    assert one.lease_id != two.lease_id
    assert one.execution_env["CLAUDE_CONFIG_DIR"] != two.execution_env["CLAUDE_CONFIG_DIR"]
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "3" * 32)
    manager.release(one)
    three = manager.acquire("claudeop_" + "3" * 32)
    assert three.execution_env["CLAUDE_CONFIG_DIR"] == one.execution_env["CLAUDE_CONFIG_DIR"]


def test_least_recently_used_is_selected_first(tmp_path: Path) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    first = manager.acquire("claudeop_" + "1" * 32)
    manager.release(first)
    second = manager.acquire("claudeop_" + "2" * 32)
    assert second.execution_env["CLAUDE_CONFIG_DIR"] != first.execution_env["CLAUDE_CONFIG_DIR"]


def test_second_manager_instance_cannot_take_held_account(tmp_path: Path) -> None:
    manager, observer, root = _pool(tmp_path, ["a"])
    held = manager.acquire("claudeop_" + "1" * 32)
    other = ClaudeAccountPoolManager(root, host_identity=HOST, identity_observer=observer)
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        other.acquire("claudeop_" + "2" * 32)
    manager.release(held)
    assert other.acquire("claudeop_" + "2" * 32).lease_id != held.lease_id


def test_cross_process_exclusivity_and_dead_pid_pruning(tmp_path: Path) -> None:
    manager, _, root = _pool(tmp_path, ["a"])
    code = (
        "import sys;from pathlib import Path;"
        "from nexus.services.claude_account_pool import ClaudeAccountPoolManager as M;"
        "m=M(Path(sys.argv[1]),host_identity=sys.argv[2],identity_observer=lambda d: sys.argv[3]);"
        "l=m.acquire('claudeop_'+'9'*32);print(l.lease_id,flush=True);"
        "sys.stdin.readline()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(root), HOST, _fp("a")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip().startswith("claudelease_")
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            manager.acquire("claudeop_" + "1" * 32)
    finally:
        assert proc.stdin is not None
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(timeout=20)
    # holder pid is dead and lease was never released: pruned, account usable again
    assert manager.acquire("claudeop_" + "1" * 32).lease_id


# -- identity -------------------------------------------------------------
@pytest.mark.parametrize("observed", ["mismatch", None])
def test_identity_mismatch_or_missing_fails_closed(tmp_path: Path, observed) -> None:
    manager, observer, root = _pool(tmp_path, ["a"])
    cfg = str((tmp_path / "cfg-a").resolve())
    observer.table[cfg] = _fp("someone-else") if observed == "mismatch" else None
    with pytest.raises(ClaudeAccountIdentityError) as info:
        manager.acquire("claudeop_" + "1" * 32)
    assert info.value.failure_kind is AccountFailureKind.AUTH_OR_SESSION_INVALID
    state = json.loads((root / "state.json").read_text())
    assert state["leases"] == {}
    # account is cooled down, so it is not retried; default profile is never offered
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "2" * 32)
    assert all(Path(c) != Path.home() / ".claude" for c in observer.calls)


def test_default_profile_dir_cannot_be_registered(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    home = tmp_path / ".claude"
    home.mkdir(mode=0o700)
    manager = ClaudeAccountPoolManager(tmp_path / "pool", host_identity=HOST)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(ClaudeAccountPoolError, match="DEFAULT_PROFILE"):
        manager.register_local_profile(
            alias="x", config_dir=home, approved_identity_fingerprint=_fp("x")
        )


def test_registration_rejects_open_perms_bad_fingerprint_and_duplicates(tmp_path: Path) -> None:
    manager = ClaudeAccountPoolManager(tmp_path / "pool", host_identity=HOST)
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o755)
    loose.chmod(0o755)
    with pytest.raises(ClaudeAccountPoolError, match="PERMISSIONS_TOO_OPEN"):
        manager.register_local_profile(
            alias="a", config_dir=loose, approved_identity_fingerprint=_fp("a")
        )
    ok = tmp_path / "ok"
    ok.mkdir(mode=0o700)
    with pytest.raises(ClaudeAccountPoolError, match="FINGERPRINT_INVALID"):
        manager.register_local_profile(
            alias="a", config_dir=ok, approved_identity_fingerprint="alice@example.com"
        )
    manager.register_local_profile(alias="a", config_dir=ok, approved_identity_fingerprint=_fp("a"))
    ok2 = tmp_path / "ok2"
    ok2.mkdir(mode=0o700)
    with pytest.raises(ClaudeAccountPoolError, match="IDENTITY_ALREADY_REGISTERED"):
        manager.register_local_profile(
            alias="b", config_dir=ok2, approved_identity_fingerprint=_fp("a")
        )


# -- host binding ---------------------------------------------------------
def test_unbound_or_mismatched_host_refuses(tmp_path: Path) -> None:
    manager, observer, root = _pool(tmp_path, ["a"])
    foreign = ClaudeAccountPoolManager(root, host_identity="other-host", identity_observer=observer)
    with pytest.raises(ClaudeAccountPoolError, match="HOST_MISMATCH"):
        foreign.acquire("claudeop_" + "1" * 32)
    state = json.loads((root / "state.json").read_text())
    state.pop("host_binding")
    (root / "state.json").write_text(json.dumps(state))
    with pytest.raises(ClaudeAccountPoolError, match="HOST_UNBOUND"):
        manager.acquire("claudeop_" + "1" * 32)
    with pytest.raises(ClaudeAccountPoolError, match="CONFIRMATION_REQUIRED"):
        manager.bind_host()
    manager.bind_host(confirm_existing_pool=True)
    assert manager.acquire("claudeop_" + "1" * 32).lease_id


# -- env / secrets --------------------------------------------------------
def test_env_strips_sensitive_keys_and_state_has_no_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    manager, _, root = _pool(tmp_path, ["a"])
    lease = manager.acquire("claudeop_" + "1" * 32)
    env = dict(lease.execution_env)
    assert not (set(SECRETS) & set(env))
    assert env["CLAUDE_CONFIG_DIR"] == str((tmp_path / "cfg-a").resolve())
    blob = json.dumps(env) + repr(lease) + (root / "state.json").read_text()
    assert not any(v in blob for v in SECRETS.values())
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(_fake_claude(tmp_path)))
    binding = AccountBinding(provider="claude", execution_env=env)
    command = ClaudeExecutionAdapter().compile(_request(tmp_path), binding=binding)
    assert not (set(SECRETS) & set(command.env))
    assert not any(v in json.dumps(dict(command.env)) + repr(binding) for v in SECRETS.values())
    assert not any(v in " ".join(command.argv) for v in SECRETS.values())


def test_build_env_requires_existing_absolute_dir(tmp_path: Path) -> None:
    with pytest.raises(ClaudeAccountPoolError):
        build_claude_profile_env(tmp_path / "missing")
    with pytest.raises(ClaudeAccountPoolError):
        build_claude_profile_env("relative")


def _adapter(manager: ClaudeAccountPoolManager) -> ClaudeAccountAdapter:
    adapter = ClaudeAccountAdapter()
    adapter.manager = manager
    return adapter


# -- compile --------------------------------------------------------------
def test_compile_plan_vs_act_and_requires_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(_fake_claude(tmp_path)))
    binding = AccountBinding(
        provider="claude", execution_env={"CLAUDE_CONFIG_DIR": str(tmp_path), "PATH": "/bin"}
    )
    adapter = ClaudeExecutionAdapter()
    plan = adapter.compile(_request(tmp_path), binding=binding)
    assert plan.argv[1:3] == ("-p", "--output-format")
    assert "stream-json" in plan.argv and "--verbose" in plan.argv
    assert "--no-session-persistence" in plan.argv
    assert plan.argv[plan.argv.index("--permission-mode") + 1] == "plan"
    assert plan.argv[plan.argv.index("--model") + 1] == "sonnet"
    assert plan.argv[-1] == "do the thing"
    assert plan.env["CLAUDE_CONFIG_DIR"] == str(tmp_path)
    assert plan.cli_version == "2.1.296 (Claude Code)"
    act = adapter.compile(_request(tmp_path, mode="act", auto=True), binding=binding)
    assert act.argv[act.argv.index("--permission-mode") + 1] == "acceptEdits"
    with pytest.raises(ExternalWorkerRuntimeError, match="CLAUDE_PROFILE_BINDING_REQUIRED"):
        adapter.compile(_request(tmp_path), binding=AccountBinding(provider="claude"))
    with pytest.raises(ExternalWorkerRuntimeError, match="BINDING_PROVIDER_MISMATCH"):
        adapter.compile(_request(tmp_path), binding=AccountBinding(provider="grok"))


# -- interpret ------------------------------------------------------------
def _lines(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


_SYSTEM = {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5", "session_id": "s-1"}
_TOOL = {
    "type": "assistant",
    "message": {
        "model": "claude-sonnet-5-5",
        "content": [{"type": "tool_use", "id": "t1"}, {"type": "text", "text": "x"}],
    },
}
_OK = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "session_id": "s-1",
    "total_cost_usd": 0.0123,
    "result": "done",
}


def test_interpret_success_attests_model_session_cost_tools(tmp_path: Path) -> None:
    out = ClaudeExecutionAdapter().interpret(
        _request(tmp_path),
        exit_code=0,
        stdout_text=_lines(_SYSTEM, _TOOL, _TOOL, _OK),
        stderr_text="",
    )
    assert out.status == "COMPLETED" and out.failure_kind is None
    assert out.observed_model == "claude-sonnet-5-5"
    assert out.provider_session_id == "s-1"
    assert out.total_cost == pytest.approx(0.0123)
    assert out.tool_event_count == 2
    assert out.retry_permitted is False


def test_rate_limit_event_alone_is_not_failure(tmp_path: Path) -> None:
    rate = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}
    out = ClaudeExecutionAdapter().interpret(
        _request(tmp_path), exit_code=0, stdout_text=_lines(_SYSTEM, rate, _OK), stderr_text=""
    )
    assert out.status == "COMPLETED"
    only_rate = ClaudeExecutionAdapter().interpret(
        _request(tmp_path), exit_code=0, stdout_text=_lines(_SYSTEM, rate), stderr_text=""
    )
    assert only_rate.status == "OUTCOME_UNKNOWN"
    assert only_rate.failure_kind != AccountFailureKind.QUOTA_EXHAUSTED.value


def test_interpret_quota_and_auth_errors(tmp_path: Path) -> None:
    adapter = ClaudeExecutionAdapter()
    quota = adapter.interpret(
        _request(tmp_path),
        exit_code=1,
        stdout_text=_lines(
            _SYSTEM,
            {
                "type": "result",
                "subtype": "error",
                "is_error": True,
                "result": "Claude usage limit reached",
            },
        ),
        stderr_text="",
    )
    assert quota.status == "FAILED"
    assert quota.failure_kind == AccountFailureKind.QUOTA_EXHAUSTED.value
    assert quota.retry_permitted is False  # never rotate around a per-person limit
    auth = adapter.interpret(
        _request(tmp_path),
        exit_code=1,
        stdout_text=_lines({
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "Invalid API key - Please run /login",
        }),
        stderr_text="",
    )
    assert auth.failure_kind == AccountFailureKind.AUTH_OR_SESSION_INVALID.value
    assert auth.retry_permitted is True
    post_effect = adapter.interpret(
        _request(tmp_path),
        exit_code=1,
        stdout_text=_lines(
            _TOOL,
            {"type": "result", "subtype": "error", "is_error": True, "result": "401 unauthorized"},
        ),
        stderr_text="",
    )
    assert post_effect.retry_permitted is False


@pytest.mark.parametrize("stdout", ["", "garbage\n"])
def test_timeout_or_no_result_is_unknown_without_retry(tmp_path: Path, stdout: str) -> None:
    out = ClaudeExecutionAdapter().interpret(
        _request(tmp_path),
        exit_code=124,
        stdout_text=_lines(_SYSTEM, _TOOL) + stdout,
        stderr_text="timeout",
    )
    assert out.status == "OUTCOME_UNKNOWN"
    assert out.retry_permitted is False
    assert out.details["unknown_outcome"] is True
    assert classify_claude_failure("x", timed_out=True) is AccountFailureKind.TIMEOUT


# -- rotation / unknown outcome ------------------------------------------
def test_auth_failure_rotates_to_other_verified_account(tmp_path: Path) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    adapter = _adapter(manager)
    first = adapter.acquire("claudeop_" + "1" * 32)
    second = adapter.report_failure(first, AccountFailureKind.AUTH_OR_SESSION_INVALID)
    assert second is not None
    assert second.execution_env["CLAUDE_CONFIG_DIR"] != first.execution_env["CLAUDE_CONFIG_DIR"]
    adapter.release(second)


def test_rotation_to_account_with_bad_identity_fails_closed(tmp_path: Path) -> None:
    manager, observer, _ = _pool(tmp_path, ["a", "b"])
    adapter = _adapter(manager)
    first = adapter.acquire("claudeop_" + "1" * 32)
    other = "b" if "cfg-a" in first.execution_env["CLAUDE_CONFIG_DIR"] else "a"
    observer.table[str((tmp_path / f"cfg-{other}").resolve())] = _fp("intruder")
    with pytest.raises(ClaudeAccountIdentityError):
        adapter.report_failure(first, AccountFailureKind.AUTH_OR_SESSION_INVALID)


@pytest.mark.parametrize("kind", [AccountFailureKind.TIMEOUT, AccountFailureKind.UNKNOWN])
def test_timeout_unknown_never_rotates_and_lease_kept_for_release(
    tmp_path: Path, kind: AccountFailureKind
) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    assert adapter.report_failure(binding, kind) is None
    adapter.release(binding)  # still owned: known release succeeds


def test_unknown_outcome_blocks_reuse_until_reconcile(tmp_path: Path) -> None:
    manager, _, root = _pool(tmp_path, ["a"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    lease = adapter._leases[binding.lease_id_hash]
    adapter.hold_unknown_outcome(binding)
    adapter.release(binding)  # dispatch releases afterwards; must NOT free it
    state = json.loads((root / "state.json").read_text())
    (lease_id,) = state["leases"]
    assert state["leases"][lease_id]["unknown_outcome"] is True
    assert manager.report_failure(lease, AccountFailureKind.AUTH_OR_SESSION_INVALID) is None
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "2" * 32)
    # survives pid death of the holder (pruning ignores it)
    state["leases"][lease_id]["pid"] = 2**22 + 12345
    (root / "state.json").write_text(json.dumps(state))
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "2" * 32)
    assert manager.unknown_outcome_leases() == (lease_id,)
    manager.reconcile_release(lease_id)
    assert manager.acquire("claudeop_" + "2" * 32).lease_id != lease_id
    with pytest.raises(ClaudeAccountPoolError, match="NOT_UNKNOWN_OUTCOME"):
        manager.reconcile_release("claudelease_nope")


def test_exhausted_after_rotation_request(tmp_path: Path) -> None:
    manager, _, _ = _pool(tmp_path, ["a"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        adapter.report_failure(binding, AccountFailureKind.AUTH_OR_SESSION_INVALID)


@pytest.mark.parametrize(
    "kind", [AccountFailureKind.QUOTA_EXHAUSTED, AccountFailureKind.RATE_LIMITED]
)
def test_quota_and_rate_limit_never_rotate(tmp_path: Path, kind: AccountFailureKind) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    assert adapter.report_failure(binding, kind) is None
    adapter.release(binding)


# -- hooks / settings isolation ------------------------------------------
def test_compile_disables_project_settings_hooks_and_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(_fake_claude(tmp_path)))
    hostile = tmp_path / "repo" / ".claude"
    hostile.mkdir(parents=True)
    (hostile / "settings.json").write_text('{"hooks": {"x": []}}', encoding="utf-8")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    binding = AccountBinding(provider="claude", execution_env={"CLAUDE_CONFIG_DIR": str(cfg)})
    request = _request(tmp_path / "repo")
    command = ClaudeExecutionAdapter().compile(request, binding=binding)
    argv = list(command.argv)
    assert argv[argv.index("--setting-sources") + 1] == "user"
    assert json.loads(argv[argv.index("--settings") + 1]) == {"disableAllHooks": True}
    assert "--strict-mcp-config" in argv and "--mcp-config" not in argv
    assert argv.index("--strict-mcp-config") < argv.index("--")
    assert str(hostile) not in " ".join(argv) + json.dumps(dict(command.env))


def test_compile_refuses_default_profile_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(_fake_claude(tmp_path)))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    default = tmp_path / ".claude"
    (default / "sub").mkdir(parents=True)
    for target in (default, default / "sub"):
        binding = AccountBinding(
            provider="claude", execution_env={"CLAUDE_CONFIG_DIR": str(target)}
        )
        with pytest.raises(ExternalWorkerRuntimeError, match="DEFAULT_PROFILE_NOT_ALLOWED"):
            ClaudeExecutionAdapter().compile(_request(tmp_path), binding=binding)


# -- version probe env ----------------------------------------------------
def test_version_probe_runs_with_sanitized_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump = tmp_path / "env.dump"
    fake = tmp_path / "claude"
    fake.write_text(f"#!/bin/sh\nenv > {dump}\necho '2.1.296'\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(fake))
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    manager, _, _ = _pool(tmp_path, ["a"])
    lease = manager.acquire("claudeop_" + "1" * 32)
    binding = AccountBinding(provider="claude", execution_env=lease.execution_env)
    command = ClaudeExecutionAdapter().compile(_request(tmp_path), binding=binding)
    assert command.cli_version == "2.1.296"
    text = dump.read_text()
    assert not any(k in text for k in SECRETS) and not any(v in text for v in SECRETS.values())
    assert f"CLAUDE_CONFIG_DIR={lease.execution_env['CLAUDE_CONFIG_DIR']}" in text


# -- default observer attestation ----------------------------------------
def _observer_cli(tmp_path: Path, payload: dict) -> Path:
    fake = tmp_path / "claude-auth"
    fake.write_text("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(payload) + "\nEOF\n", encoding="utf-8")
    fake.chmod(0o755)
    return fake


@pytest.mark.parametrize(
    "mutate,ok",
    [
        ({}, True),
        ({"authMethod": "OAuth Token"}, True),
        ({"loggedIn": False}, False),
        ({"loggedIn": "true"}, False),
        ({"configDirectory": None}, False),
        ({"configDirectory": "/somewhere/else"}, False),
        ({"authMethod": "api_key"}, False),
        ({"authMethod": None}, False),
    ],
)
def test_default_observer_requires_full_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate: dict, ok: bool
) -> None:
    from nexus.services.claude_account_pool import default_identity_observer

    cfg = tmp_path / "cfg"
    cfg.mkdir(mode=0o700)
    payload = {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "configDirectory": str(cfg),
        "accountUuid": "acct-1",
        "organizationUuid": "org-1",
    }
    payload.update(mutate)
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(_observer_cli(tmp_path, payload)))
    observed = default_identity_observer(cfg)
    assert observed == (identity_fingerprint("acct-1", "org-1") if ok else None)


def test_register_refuses_dir_inside_default_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    inner = tmp_path / ".claude" / "profiles" / "x"
    inner.mkdir(parents=True, mode=0o700)
    manager = ClaudeAccountPoolManager(tmp_path / "pool", host_identity=HOST)
    with pytest.raises(ClaudeAccountPoolError, match="DEFAULT_PROFILE"):
        manager.register_local_profile(
            alias="x", config_dir=inner, approved_identity_fingerprint=_fp("x")
        )


# -- provider liveness ----------------------------------------------------
def test_dead_dispatcher_with_live_provider_keeps_lease_as_unknown(tmp_path: Path) -> None:
    manager, _, root = _pool(tmp_path, ["a"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    sleeper = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        adapter.attach_provider(binding, sleeper.pid)
        state = json.loads((root / "state.json").read_text())
        (lease_id,) = state["leases"]
        assert state["leases"][lease_id]["provider_pid"] == sleeper.pid
        assert state["leases"][lease_id]["provider_pgid"] == sleeper.pid
        state["leases"][lease_id]["pid"] = 2**22 + 12345  # dispatcher dead
        (root / "state.json").write_text(json.dumps(state))
        with pytest.raises(ClaudeAccountPoolExhaustedError):
            manager.acquire("claudeop_" + "2" * 32)
        state = json.loads((root / "state.json").read_text())
        assert state["leases"][lease_id]["unknown_outcome"] is True
    finally:
        sleeper.kill()
        sleeper.wait()
    # provider now dead too, but the lease was marked unknown: still blocked until reconcile
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "2" * 32)
    manager.reconcile_release(lease_id)
    assert manager.acquire("claudeop_" + "2" * 32).lease_id


def test_dead_dispatcher_and_dead_provider_is_reclaimed(tmp_path: Path) -> None:
    manager, _, root = _pool(tmp_path, ["a"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    done = subprocess.Popen(["true"], start_new_session=True)
    done.wait()
    adapter.attach_provider(binding, done.pid)
    state = json.loads((root / "state.json").read_text())
    (lease_id,) = state["leases"]
    state["leases"][lease_id]["pid"] = 2**22 + 12345
    (root / "state.json").write_text(json.dumps(state))
    assert manager.acquire("claudeop_" + "2" * 32).lease_id != lease_id


def test_env_is_strict_allowlist_even_for_unlisted_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services import claude_account_pool as mod

    unlisted = {
        "HF_TOKEN": "hf-SECRET",
        "NPM_TOKEN": "npm-SECRET",
        "SSH_AUTH_SOCK": "/tmp/ssh-SECRET",
        "GH_ENTERPRISE_TOKEN": "ghe-SECRET",
    }
    for key, value in {**SECRETS, **unlisted}.items():
        monkeypatch.setenv(key, value)
    dump = tmp_path / "env.dump"
    fake = tmp_path / "claude"
    fake.write_text(f"#!/bin/sh\nenv > {dump}\necho 2.1.296\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("NEXUS_CLAUDE_BIN", str(fake))
    manager, _, _ = _pool(tmp_path, ["a"])
    lease = manager.acquire("claudeop_" + "1" * 32)
    allowed = set(mod._NEUTRAL_ENV_KEYS) | {"CLAUDE_CONFIG_DIR"}
    assert set(lease.execution_env) <= allowed
    binding = AccountBinding(provider="claude", execution_env=lease.execution_env)
    command = ClaudeExecutionAdapter().compile(_request(tmp_path), binding=binding)
    assert set(command.env) <= allowed
    probed = {line.split("=", 1)[0] for line in dump.read_text().splitlines() if "=" in line}
    assert not (probed & (set(SECRETS) | set(unlisted)))
    assert not any(v in dump.read_text() for v in {**SECRETS, **unlisted}.values())


def test_default_profile_detected_by_inode_incl_symlink_and_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services.claude_account_pool import is_default_profile_path

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / ".claude" / "x").mkdir(parents=True)
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / ".claude")
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert is_default_profile_path(tmp_path)
    assert is_default_profile_path(tmp_path / ".claude")
    assert is_default_profile_path(tmp_path / ".claude" / "x")
    assert is_default_profile_path(link)
    assert not is_default_profile_path(other)


def test_quota_failure_cools_down_account_for_new_tasks(tmp_path: Path) -> None:
    manager, _, _ = _pool(tmp_path, ["a", "b"])
    adapter = _adapter(manager)
    binding = adapter.acquire("claudeop_" + "1" * 32)
    used = binding.execution_env["CLAUDE_CONFIG_DIR"]
    assert adapter.report_failure(binding, AccountFailureKind.QUOTA_EXHAUSTED) is None
    adapter.release(binding)
    nxt = manager.acquire("claudeop_" + "2" * 32)
    assert nxt.execution_env["CLAUDE_CONFIG_DIR"] != used
    with pytest.raises(ClaudeAccountPoolExhaustedError):
        manager.acquire("claudeop_" + "3" * 32)  # first account cooling, second held
    reasons = {a.alias: a.last_failure_reason for a in manager.local_accounts()}
    assert "QUOTA_EXHAUSTED" in reasons.values()


def test_operator_reconcile_flags_list_and_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nexus.services.claude_account_pool import set_claude_account_pool_manager

    manager, _, root = _pool(tmp_path, ["a"])
    lease = manager.acquire("claudeop_" + "1" * 32)
    manager.mark_unknown_outcome(lease)
    state = json.loads((root / "state.json").read_text())
    state["host_binding"]["host_id_hash"] = ClaudeAccountPoolManager(root).host_id_hash
    (root / "state.json").write_text(json.dumps(state))
    monkeypatch.setenv("NEXUS_CLAUDE_ACCOUNT_POOL_DIR", str(root))
    set_claude_account_pool_manager(None)
    dispatch = SourceFileLoader(
        "nexus_dispatch_claude_flags", str(ROOT / "scripts/ops/nexus-external-worker-dispatch")
    ).load_module()
    try:
        assert dispatch.main(["--claude-list-unknown"]) == 0
        assert json.loads(capsys.readouterr().out)["unknown_outcome_leases"] == [lease.lease_id]
        assert dispatch.main(["--claude-reconcile-release", lease.lease_id]) == 0
        assert json.loads(capsys.readouterr().out)["unknown_outcome_leases"] == []
    finally:
        set_claude_account_pool_manager(None)
