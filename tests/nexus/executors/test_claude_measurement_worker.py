"""#2721 measurement-only Claude worker: inert by default, exact sandboxed run when on.

The provider binary is a fake (``/usr/bin/python3`` script) that reports what
it observed (argv, cwd, env, sandbox probes) inside its stream-json init event;
no model is called and no login is used.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import claude_measurement_worker as cmw
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerProviderUnavailable,
    admitted_worker_providers,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.services import measurement_workforce_policy as mwp

DRIVER = Path(__file__).with_name("_claude_measurement_live_driver.py")
REPO_ROOT = Path(__file__).resolve().parents[3]
SANDBOX = Path("/usr/bin/sandbox-exec").exists() and sys.platform == "darwin"


@pytest.fixture(autouse=True)
def _seatbelt_or_plain(monkeypatch):
    """Run every adapter test on every host: with Seatbelt on macOS, without it
    on Linux CI.  Sandbox-enforcement assertions are checked only where the
    sandbox exists; the invocation, env, trace and P1 assertions run everywhere."""
    if not SANDBOX:
        monkeypatch.setattr(cmw, "_USE_SEATBELT", False)


FAKE_CLAUDE = r"""#!/usr/bin/python3
import json, os, socket, sys
from pathlib import Path
args = sys.argv[1:]
if args == ["--version"]:
    print("9.9.9 (Fake Claude)")
    sys.exit(0)
prompt = args[-1]
probes = {}
for name, path in (("read_secret", "__SECRET__"), ("read_venv", "__VENV_FILE__")):
    try:
        probes[name] = Path(path).read_text()[:20] if path and not path.startswith("__") else "n/a"
    except Exception as exc:
        probes[name] = "DENIED:" + type(exc).__name__
try:
    Path("__OUTSIDE__").write_text("x")
    probes["write_outside"] = "WROTE"
except Exception as exc:
    probes["write_outside"] = "DENIED:" + type(exc).__name__
try:
    Path(".git/planted").write_text("x")
    probes["write_git"] = "WROTE"
except Exception as exc:
    probes["write_git"] = "DENIED:" + type(exc).__name__
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3).close()
    probes["direct_net"] = "CONNECTED"
except Exception as exc:
    probes["direct_net"] = "DENIED:" + type(exc).__name__
try:
    proxy = os.environ["HTTPS_PROXY"].rsplit(":", 1)
    s = socket.create_connection((proxy[0].split("//")[1], int(proxy[1])), timeout=3)
    s.sendall(b"CONNECT github.com:443 HTTP/1.1\r\nHost: github.com:443\r\n\r\n")
    probes["proxy_github"] = s.recv(64).decode().split("\r\n")[0]
    s.close()
except Exception as exc:
    probes["proxy_github"] = "ERROR:" + type(exc).__name__
for name, tool in (("exec_security", "/usr/bin/security"), ("exec_open", "/usr/bin/open")):
    try:
        import subprocess
        subprocess.run([tool, "-h"], capture_output=True, timeout=5)
        probes[name] = "RAN"
    except Exception as exc:
        probes[name] = "DENIED:" + type(exc).__name__
try:
    import shutil, subprocess
    shutil.copy("/bin/echo", "copied-echo")
    subprocess.run(["./copied-echo", "hi"], capture_output=True, timeout=5)
    probes["exec_from_target"] = "RAN"
except Exception as exc:
    probes["exec_from_target"] = "DENIED:" + type(exc).__name__
finally:
    Path("copied-echo").unlink(missing_ok=True)
outside = Path(".outside_pid")
if outside.exists():
    try:
        os.kill(int(outside.read_text()), 0)
        probes["signal_outside"] = "ALLOWED"
    except Exception as exc:
        probes["signal_outside"] = "DENIED:" + type(exc).__name__
try:
    import subprocess as _sp
    git = _sp.run(["/usr/bin/git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=20)
    probes["git_status"] = {"rc": git.returncode, "out": git.stdout}
except Exception as exc:
    probes["git_status"] = {"rc": None, "out": type(exc).__name__}
model = os.environ.get("FAKE_MODEL", "claude-haiku-5-5")
mode = os.environ.get("FAKE_MODE", "ok")
init = {"type": "system", "subtype": "init", "session_id": "s1",
        "tools": ["Bash", "Edit", "Read", "Write"], "mcp_servers": [], "permissionMode": "acceptEdits",
        "claude_code_version": "9.9.9",
        "fake_observed": {"argv": args, "cwd": os.getcwd(), "env": dict(os.environ), "probes": probes}}
if mode != "nomodel":
    init["model"] = model
print(json.dumps(init))
if not prompt.startswith("Reply with exactly"):
    readme = Path("README.md")
    readme.write_text(readme.read_text() + "\nbounded change\n")
    print(json.dumps({"type": "assistant", "message": {**({} if mode == "nomodel" else {"model": model}), "content": [
        {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "README.md"}}]}}))
if mode == "ratelimit":
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "terminal_reason": "api_error", "api_error_status": 429,
                      "result": "API Error: 429 rate_limit_error", "session_id": "s1"}))
    sys.exit(1)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
                  "total_cost_usd": 0.001, "session_id": "s1",
                  "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7,
                            "cache_creation_input_tokens": 3},
                  **({} if mode == "nomodel" else {"modelUsage": {model: {"inputTokens": 10, "outputTokens": 5}}})}))
"""


def _fake_claude(
    tmp_path: Path,
    *,
    secret: Path | None = None,
    outside: Path | None = None,
    venv_file: Path | None = None,
) -> Path:
    path = tmp_path / "bin" / "claude"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        FAKE_CLAUDE
        .replace("__SECRET__", str(secret or ""))
        .replace("__OUTSIDE__", str(outside or tmp_path / "outside.txt"))
        .replace("__VENV_FILE__", str(venv_file or ""))
    )
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return Path(os.path.realpath(path))


# Built at runtime so no key-shaped literal exists in the source (secret audit;
# a formatter may join implicitly concatenated string literals).
_KEY_PREFIX = "-".join(("sk", "ant", ""))
FAKE_KEY = _KEY_PREFIX + "api03-" + "FAKEKEYFORTESTSONLY0123456789abcdef"
FAKE_OTHER_KEY = _KEY_PREFIX + "other-" + "KEYSHAPED123456"


def _key_file(tmp_path: Path) -> Path:
    path = tmp_path / "anthropic.env"
    path.write_text(f"# measurement key\nANTHROPIC_API_KEY={FAKE_KEY}\n")
    path.chmod(0o600)
    return path


@pytest.fixture()
def switch_off(monkeypatch):
    for key in (
        cmw.MEASUREMENT_CLAUDE_ENV,
        cmw.MEASUREMENT_CLAUDE_BIN_ENV,
        cmw.MEASUREMENT_ANTHROPIC_ENV_FILE_ENV,
    ):
        monkeypatch.delenv(key, raising=False)


def _enable(monkeypatch, tmp_path, **fake) -> Path:
    exe = _fake_claude(tmp_path, **fake)
    token = _key_file(tmp_path)
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, str(exe))
    monkeypatch.setenv(cmw.MEASUREMENT_ANTHROPIC_ENV_FILE_ENV, str(token))
    monkeypatch.setenv(cmw.MEASUREMENT_TRACE_DIR_ENV, str(tmp_path / "traces"))
    # tmp_path lives under a denied user-data root; the operator lists it.
    monkeypatch.setenv(cmw.MEASUREMENT_READ_ROOTS_ENV, str(tmp_path))
    # Fresh per-task Controllers live under the measurement root (#2742).
    monkeypatch.setenv(cmw.MEASURE_EXTERNAL_TARGET_ROOT_ENV, str(tmp_path))
    cmw._PROBE_CACHE.clear()
    return exe


def _lease(tmp_path: Path, *, venv: bool = False):
    root = tmp_path / "targets"
    target = root / "t1"
    target.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    (target / "README.md").write_text("# Repo\n")
    controller = tmp_path / "ctl" / "base"
    controller.mkdir(parents=True)
    if venv:
        (controller.parent / "venv" / "bin").mkdir(parents=True)
        (controller.parent / "venv" / "bin" / "python").symlink_to("/usr/bin/python3")
        (controller.parent / "venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    contract = SimpleNamespace(
        task_id="t1",
        target_worktree_root=str(root),
        target_repo_root=str(target),
        controller_repo_root=str(controller),
    )
    return contract, SimpleNamespace(task_id="t1", target_worktree=str(target))


def _observed(tmp_path: Path, receipt) -> dict:
    trace = tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.stream.jsonl"
    first = json.loads(trace.read_text().splitlines()[0])
    return first["fake_observed"]


# -- inert by default ------------------------------------------------------------


def test_switch_requires_the_exact_value_one():
    for value in ("", "0", "true", "yes", " 1", "1 "):
        assert not cmw.measurement_claude_enabled({cmw.MEASUREMENT_CLAUDE_ENV: value})
    assert cmw.measurement_claude_enabled({cmw.MEASUREMENT_CLAUDE_ENV: "1"})


def test_live_surfaces_are_unchanged_with_the_switch_off(switch_off):
    assert admitted_worker_providers() == SUPPORTED_WORKER_PROVIDERS
    assert "claude" not in SUPPORTED_WORKER_PROVIDERS
    assert "claude" not in WorkerRegistry.default()._adapters
    assert mwp.measurement_workforce_policy_loader() is None
    preflight = cmw.measurement_claude_preflight("claude-haiku-5-5")
    assert (
        preflight["blocker"] == "MEASUREMENT_CLAUDE_WORKER_DISABLED"
        and not preflight["execution_ready"]
    )
    assert not cmw.ClaudeMeasurementWorkerAdapter().preflight().ready


def test_registry_rejects_a_claude_adapter_while_switched_off(switch_off):
    adapters = dict(WorkerRegistry.default()._adapters)
    adapters["claude"] = cmw.ClaudeMeasurementWorkerAdapter()
    with pytest.raises(ValueError, match="unknown worker providers"):
        WorkerRegistry(adapters)


def test_gateway_preflight_for_claude_is_unregistered_while_switched_off(switch_off):
    from unittest.mock import MagicMock

    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

    result = UnifiedMCPGateway(service=MagicMock())._provider_preflight({
        "provider": "claude",
        "model": "claude-haiku-5-5",
    })
    assert result["blocker"] == "ASSIST_PROVIDER_NOT_REGISTERED"


# -- invocation ------------------------------------------------------------------


def test_argv_is_fixed_and_the_prompt_is_last():
    argv = cmw.claude_measurement_argv("WHAT: x")
    assert argv[:-1] == cmw.CLAUDE_MEASUREMENT_FLAGS and argv[-1] == "WHAT: x"
    assert "--bare" in argv and "--dangerously-skip-permissions" not in argv
    assert "--fallback-model" not in argv
    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch,Task,Agent,Workflow"
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert (
        argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
        and "--strict-mcp-config" in argv
    )
    for bad in ("", "  ", "--help"):
        with pytest.raises(ValueError):
            cmw.claude_measurement_argv(bad)


def test_executable_must_be_absolute_and_not_a_symlink(tmp_path):
    real = _fake_claude(tmp_path)
    link = tmp_path / "claude-link"
    link.symlink_to(real)
    assert cmw.measurement_claude_executable({cmw.MEASUREMENT_CLAUDE_BIN_ENV: str(real)}) == str(
        real
    )
    for raw in ("claude", str(link), str(tmp_path / "missing")):
        assert cmw.measurement_claude_executable({cmw.MEASUREMENT_CLAUDE_BIN_ENV: raw}) is None


def test_api_key_comes_only_from_a_private_env_file(tmp_path):
    key_file = _key_file(tmp_path)
    env = {cmw.MEASUREMENT_ANTHROPIC_ENV_FILE_ENV: str(key_file)}
    assert cmw.measurement_claude_api_key(env) == FAKE_KEY
    key_file.chmod(0o644)
    assert cmw.measurement_claude_api_key(env) is None
    key_file.chmod(0o600)
    link = tmp_path / "link.env"
    link.symlink_to(key_file)
    assert (
        cmw.measurement_claude_api_key({cmw.MEASUREMENT_ANTHROPIC_ENV_FILE_ENV: str(link)}) is None
    )
    # Never from the process environment.
    assert cmw.measurement_claude_api_key({"ANTHROPIC_API_KEY": FAKE_KEY}) is None


def test_stream_summary_collects_tools_usage_models_and_init():
    lines = [
        {
            "type": "system",
            "subtype": "init",
            "model": "claude-haiku-5-5",
            "session_id": "s",
            "tools": ["Read"],
            "mcp_servers": [],
            "secret_field": "x",
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-haiku-5-5",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "tool_use", "id": "a", "name": "Read", "input": {"p": 1}},
                ],
            },
        },
        "not json",
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 3,
            "total_cost_usd": 0.01,
            "usage": {"input_tokens": 7},
            "modelUsage": {"claude-haiku-5-5": {}, "claude-other": {}},
        },
    ]
    text = "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
    summary = cmw.summarize_stream_json(text)
    assert summary.result_seen and summary.is_error is False and summary.num_turns == 3
    assert [call["name"] for call in summary.tool_calls] == ["Read"]
    assert summary.models_seen == ("claude-haiku-5-5", "claude-other")
    assert summary.init == {"tools": ["Read"], "mcp_servers": [], "model": "claude-haiku-5-5"}
    assert cmw.summarize_stream_json("").result_seen is False


@pytest.mark.parametrize(
    ("result", "stderr", "expected"),
    [
        (
            {
                "is_error": True,
                "terminal_reason": "api_error",
                "api_error_status": 429,
                "result": "rate_limit_error",
            },
            "",
            "rate_limited",
        ),
        (
            {
                "is_error": True,
                "terminal_reason": "api_error",
                "api_error_status": 529,
                "result": "Overloaded",
            },
            "",
            "overloaded",
        ),
        (
            {
                "is_error": False,
                "terminal_reason": "api_error",
                "result": "Not logged in · Please run /login",
            },
            "",
            "auth",
        ),
        ({"is_error": True, "subtype": "error_max_turns", "result": "stopped"}, "", None),
        ({"is_error": False, "subtype": "success", "result": "done"}, "", None),
    ],
)
def test_infra_classification(result, stderr, expected):
    summary = cmw.summarize_stream_json(json.dumps({"type": "result", **result}))
    assert cmw.classify_claude_infra(summary, stderr) == expected


def test_seatbelt_profile_shape(tmp_path):
    profile = cmw.build_claude_seatbelt_profile(
        target=tmp_path / "t", run_root=tmp_path / "r", readable=(tmp_path / "v",), proxy_port=4567
    )
    assert "(deny network-outbound)" in profile
    assert '(allow network-outbound (remote ip "localhost:4567"))' in profile
    assert "(deny file-read-data" in profile and '(subpath "/Users")' in profile
    assert f'(deny file-write* (literal "{os.path.realpath(tmp_path / "t")}/.git")' in profile


def test_proxy_tunnels_only_the_api_host():
    with cmw.HostAllowlistProxy(allowed_hosts=("api.anthropic.com",)) as proxy:
        for line in (
            b"CONNECT github.com:443 HTTP/1.1\r\n\r\n",
            b"GET http://pypi.org/ HTTP/1.1\r\n\r\n",
            b"CONNECT api.anthropic.com:80 HTTP/1.1\r\n\r\n",
        ):
            sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=5)
            sock.sendall(line)
            assert sock.recv(64).startswith(b"HTTP/1.1 403")
            sock.close()
    assert [a["allowed"] for a in proxy.attempts] == [False, False, False]
    assert [a["host"] for a in proxy.attempts][0] == "github.com"


def test_adapter_runs_the_exact_isolated_sandboxed_invocation(monkeypatch, tmp_path):
    secret = tmp_path / "answers" / "gold.patch"
    secret.parent.mkdir()
    secret.write_text("the gold fix")
    _enable(monkeypatch, tmp_path, secret=secret, outside=tmp_path / "answers" / "planted.txt")
    contract, lease = _lease(tmp_path, venv=True)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: edit", timeout_seconds=60
    )
    assert receipt.outcome == "EXECUTION_COMPLETED", (receipt.failure_reason, receipt.stderr_tail)
    seen = _observed(tmp_path, receipt)
    assert seen["argv"] == list(cmw.claude_measurement_argv("WHAT: edit"))
    assert Path(seen["cwd"]).resolve() == Path(lease.target_worktree).resolve()
    env = seen["env"]
    # The CLI received the token, and the kept trace never holds it (Codex r1 #1).
    assert env["ANTHROPIC_API_KEY"] == "<REDACTED>"
    trace_bytes = (
        tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.stream.jsonl"
    ).read_bytes()
    assert FAKE_KEY.encode() not in trace_bytes
    assert FAKE_KEY.encode() not in (receipt.stdout_tail or "").encode()
    assert env["HOME"] != os.environ.get("HOME") and env["CLAUDE_CONFIG_DIR"].startswith(
        env["HOME"]
    )
    assert env["DISABLE_AUTOUPDATER"] == "1" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    venv = os.path.realpath(tmp_path / "ctl" / "venv")
    assert (
        env["PATH"] == f"{venv}/bin:" + cmw.CLAUDE_MEASUREMENT_SYSTEM_PATH
        and env["VIRTUAL_ENV"] == venv
    )
    assert [key for key in env if key.startswith("ANTHROPIC_")] == ["ANTHROPIC_API_KEY"]
    assert not any(key.startswith(("GITHUB_", "GH_TOKEN", "CLAUDE_CODE_OAUTH")) for key in env)
    # Sandbox enforcement is proven by the physical witness below (macOS);
    # the proxy refusal holds everywhere.
    assert seen["probes"]["proxy_github"].startswith("HTTP/1.1 403"), seen["probes"]
    sidecar = json.loads(
        (tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.run.json").read_text()
    )
    assert {"host": "github.com", "port": 443, "allowed": False} in sidecar["proxy_attempts"]
    assert (
        sidecar["init"]["mcp_servers"] == []
        and sidecar["seatbelt_sha256"] == receipt.provider_permission_profile_sha256
    )
    assert FAKE_KEY not in json.dumps(sidecar)


def test_adapter_marks_provider_rate_limits_as_infra(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cmw, "CLAUDE_MEASUREMENT_ENV", {**cmw.CLAUDE_MEASUREMENT_ENV, "FAKE_MODE": "ratelimit"}
    )
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: x", timeout_seconds=60
    )
    assert receipt.outcome == "FAILED" and receipt.failure_reason == "claude_infra:rate_limited"


def test_adapter_fails_a_run_served_by_another_model(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cmw,
        "CLAUDE_MEASUREMENT_ENV",
        {**cmw.CLAUDE_MEASUREMENT_ENV, "FAKE_MODEL": "claude-sonnet-5"},
    )
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: x", timeout_seconds=60
    )
    assert receipt.outcome == "FAILED" and "model substitution observed" in receipt.failure_reason


def test_adapter_refuses_other_models_and_unleased_targets(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    contract, lease = _lease(tmp_path)
    with pytest.raises(WorkerProviderUnavailable, match="not the measurement model"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(
            contract, lease, prompt="WHAT: x", model="claude-opus-5-5"
        )
    stray = SimpleNamespace(task_id="t1", target_worktree=str(tmp_path))
    with pytest.raises(WorkerProviderUnavailable, match="not_leased"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, stray, prompt="WHAT: x")


def test_preflight_probes_once_and_caches(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    first = cmw.measurement_claude_preflight("claude-haiku-5-5")
    second = cmw.measurement_claude_preflight("claude-haiku-5-5")
    assert first["execution_ready"] is True and first["readiness_status"] == "MODEL_VERIFIED", first
    assert first["probe_evidence_hash"] == second["probe_evidence_hash"]
    assert (
        cmw.measurement_claude_preflight("claude-opus-5-5")["blocker"]
        == "MEASUREMENT_CLAUDE_MODEL_MISMATCH"
    )
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_VERSION_ENV, "2.1.303")
    assert (
        cmw.measurement_claude_preflight("claude-haiku-5-5")["blocker"]
        == "MEASUREMENT_CLAUDE_VERSION_MISMATCH"
    )


def test_relative_binary_is_not_ready(monkeypatch):
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, "claude")
    assert not cmw.ClaudeMeasurementWorkerAdapter().preflight().ready
    assert (
        cmw.measurement_claude_preflight("claude-haiku-5-5")["blocker"]
        == "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE"
    )


# -- workforce policy --------------------------------------------------------------


def test_measurement_policy_moves_only_the_template_routes(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    packaged = WorkforcePolicyLoader()
    loader = mwp.measurement_workforce_policy_loader()
    assert loader is not None
    snapshot = loader.load()
    worker = snapshot.workers[cmw.CLAUDE_MEASUREMENT_WORKER_ID]
    assert (worker.provider, worker.model) == ("claude", "claude-haiku-5-5")
    template = snapshot.workers[mwp.TEMPLATE_WORKER_ID]
    assert (worker.state, worker.autonomy, worker.requires, worker.roles) == (
        template.state,
        template.autonomy,
        template.requires,
        template.roles,
    )
    online = packaged.load().routing["online"]
    moved = [role for role, target in online.items() if target == mwp.TEMPLATE_WORKER_ID]
    kept = [
        role
        for role, target in online.items()
        if isinstance(target, str)
        and target != mwp.TEMPLATE_WORKER_ID
        and role in ("main_engineering", "independent_review")
    ]
    assert "fast_bounded_implementation" in moved and kept
    for role in moved:
        assert loader.resolve_route(role) == cmw.CLAUDE_MEASUREMENT_WORKER_ID
    for role in kept:  # authority routes are untouched (Codex r1 #7)
        assert loader.resolve_route(role) == packaged.resolve_route(role)
    assert cmw.CLAUDE_MEASUREMENT_WORKER_ID not in packaged.load().workers
    mwp.assert_measurement_dispatch("claude", "claude-haiku-5-5")
    with pytest.raises(ValueError, match="measurement_dispatch_not_claude"):
        mwp.assert_measurement_dispatch("codex", "gpt-5.6-luna")


def test_dispatch_assertion_is_inert_with_the_switch_off(switch_off):
    mwp.assert_measurement_dispatch("codex", "gpt-5.6-luna")


# -- the real P1 chain -------------------------------------------------------------


def test_p1_chain_dispatches_the_claude_worker_end_to_end(tmp_path):
    fake = _fake_claude(tmp_path)
    token = _key_file(tmp_path)
    spec = {
        "work": str(tmp_path / "work"),
        "out": str(tmp_path / "out.json"),
        "task_id": "m2721-claude-witness",
        "use_seatbelt": SANDBOX,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEXUS_")}
    env.update({
        cmw.MEASUREMENT_CLAUDE_ENV: "1",
        cmw.MEASUREMENT_CLAUDE_BIN_ENV: str(fake),
        cmw.MEASUREMENT_ANTHROPIC_ENV_FILE_ENV: str(token),
        cmw.MEASUREMENT_TRACE_DIR_ENV: str(tmp_path / "traces"),
        cmw.MEASUREMENT_READ_ROOTS_ENV: str(tmp_path),
        cmw.MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(tmp_path),
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), env.get("PYTHONPATH", "")]),
    })
    subprocess.run(
        [sys.executable, str(DRIVER), str(spec_path)],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        timeout=600,
    )
    result = json.loads((tmp_path / "out.json").read_text())
    assert "driver_error" not in result, result.get("trace")
    # The subprocess honoured the host's sandbox mode (Linux CI has no Seatbelt).
    assert result["use_seatbelt"] is SANDBOX
    assert result["gateway_is_error"] is False, result.get("gateway_error")
    assert (result["request_provider"], result["request_model"]) == ("claude", "claude-haiku-5-5")
    assert result["request_worker_id"] == cmw.CLAUDE_MEASUREMENT_WORKER_ID
    assert result["selected_provider"] == "claude", result
    assert result["execution_providers"] == ["claude"]
    assert result["receipt_verified"] is True, result["receipt_failure_reasons"]
    assert "+bounded change" in (result.get("candidate_diff") or ""), json.dumps(result, indent=1)[
        :4000
    ]
    traces = sorted((tmp_path / "traces" / spec["task_id"]).glob("*.stream.jsonl"))
    assert len(traces) == 1
    seen = json.loads(traces[0].read_text().splitlines()[0])["fake_observed"]
    assert seen["argv"][:-1] == list(cmw.CLAUDE_MEASUREMENT_FLAGS)
    # The Nexus prompt is the Gateway's base worker prompt plus Nexus's own context.
    assert seen["argv"][-1].startswith(result["base_prompt"])


# -- Codex r1 / review fixes --------------------------------------------------------


def test_a_success_without_model_evidence_fails(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cmw, "CLAUDE_MEASUREMENT_ENV", {**cmw.CLAUDE_MEASUREMENT_ENV, "FAKE_MODE": "nomodel"}
    )
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: x", timeout_seconds=60
    )
    assert receipt.outcome == "FAILED" and "no evidence" in receipt.failure_reason


def test_direct_calls_without_a_leased_contract_are_refused(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _contract, lease = _lease(tmp_path)
    bare_contract = SimpleNamespace(task_id="t1")  # no target_worktree_root / target_repo_root
    with pytest.raises(WorkerProviderUnavailable, match="not_leased"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(bare_contract, lease, prompt="WHAT: x")


def test_read_roots_never_cover_home_or_user_data(tmp_path, monkeypatch):
    """Hermetic on every OS: the denied user-data roots and HOME are fixtures."""
    base = Path(os.path.realpath(tmp_path))
    users, scratch = base / "Users", base / "private" / "tmp"
    home = users / "me"
    for path in (home / "Downloads", scratch / "job" / "venv", base / "usr" / "lib"):
        path.mkdir(parents=True)
    monkeypatch.setattr(cmw, "_READ_DENIED_ROOTS", (str(users), str(scratch)))
    monkeypatch.setenv("HOME", str(home))
    operator_root = scratch / "job"
    for unsafe in (Path("/"), users, scratch, base / "private", home, home.parent):
        assert not cmw.is_safe_read_root(unsafe, (operator_root,)), unsafe
    # Inside a denied tree only the operator-listed roots are allowed (Codex r2 #3).
    assert not cmw.is_safe_read_root(home / "Downloads")
    assert not cmw.is_safe_read_root(operator_root)
    assert cmw.is_safe_read_root(operator_root / "venv", (operator_root,))
    # A path outside every denied root is already readable, so re-allowing it widens nothing.
    assert cmw.is_safe_read_root(base / "usr" / "lib")
    venv = operator_root / "ctl" / "venv"
    venv.parent.mkdir(parents=True)
    venv.symlink_to(home)  # a venv link pointing at HOME is ignored, never re-allowed
    contract = SimpleNamespace(controller_repo_root=str(operator_root / "ctl" / "base"))
    assert cmw.task_venv_for(contract) is None
    # An operator root that is itself broad is dropped.
    roots = cmw.configured_read_roots({
        cmw.MEASUREMENT_READ_ROOTS_ENV: f"{users}:{home}:/:{operator_root}"
    })
    assert roots == (operator_root,)


def test_infra_needs_an_api_error_signal():
    reply = cmw.summarize_stream_json(
        json.dumps({
            "type": "result",
            "is_error": True,
            "subtype": "error_max_turns",
            "result": "Fixed the login quota bug; please run /login after deploying.",
        })
    )
    assert cmw.classify_claude_infra(reply, "") is None
    assert cmw.classify_claude_infra(reply, "Error: 401 authentication failed") == "auth"


def _client_hello(host: str) -> bytes:
    import ssl

    context = ssl.create_default_context()
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    tls = context.wrap_bio(incoming, outgoing, server_hostname=host)
    with pytest.raises(ssl.SSLWantReadError):
        tls.do_handshake()
    return outgoing.read()


def test_sni_parser_reads_real_client_hellos():
    assert cmw.tls_client_hello_sni(_client_hello("api.anthropic.com")) == "api.anthropic.com"
    assert cmw.tls_client_hello_sni(b"GET / HTTP/1.1\r\n\r\n") is None
    assert cmw.tls_client_hello_sni(b"\x16\x03\x01\x00") is None


def test_proxy_refuses_a_tunnel_whose_sni_names_another_host():
    with cmw.HostAllowlistProxy(allowed_hosts=("api.anthropic.com",)) as proxy:
        sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=5)
        sock.sendall(b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n")
        assert sock.recv(64).startswith(b"HTTP/1.1 200")
        sock.sendall(_client_hello("evil.example.com"))
        sock.settimeout(5)
        assert sock.recv(64) == b""  # closed without dialing upstream
        sock.close()
    assert proxy.attempts == [
        {"host": "api.anthropic.com", "port": 443, "allowed": False, "sni": "evil.example.com"}
    ]


def test_proxy_caps_concurrent_connections():
    import time

    with cmw.HostAllowlistProxy(max_connections=1) as proxy:
        first = socket.create_connection(("127.0.0.1", proxy.port), timeout=5)
        time.sleep(0.3)
        second = socket.create_connection(("127.0.0.1", proxy.port), timeout=5)
        second.settimeout(5)
        assert second.recv(64) == b""
        first.close()
        second.close()
    assert {"host": "<over-connection-limit>", "port": 0, "allowed": False} in proxy.attempts


def test_preflight_runs_version_inside_the_sandbox(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    calls = []
    original = cmw.run_claude_once

    def spy(*args, **kwargs):
        calls.append(kwargs.get("argv"))
        return original(*args, **kwargs)

    monkeypatch.setattr(cmw, "run_claude_once", spy)
    assert cmw.measurement_claude_preflight("claude-haiku-5-5")["execution_ready"] is True
    assert calls[0] == ("--version",) and calls[1] is None


# -- physical Seatbelt witnesses (macOS only; not collected elsewhere, never skipped) --

PHYSICAL_WITNESSES = (
    "test_seatbelt_denies_reads_writes_network_and_helper_tools",
    "test_seatbelt_denies_signals_to_processes_outside_the_sandbox",
    "test_git_status_works_alike_in_a_standalone_repo_and_a_p1_worktree",
)


def physical_seatbelt_witness(func, *, available: bool = SANDBOX):
    """Expose a physical witness as a test node only where Seatbelt can run (#1607 pattern)."""
    return func if available else None


def test_witness_nodes_are_declared_and_darwin_ci_must_collect_them():
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Name) and d.id == "physical_seatbelt_witness"
            for d in node.decorator_list
        )
    }
    assert declared == set(PHYSICAL_WITNESSES)
    for name in PHYSICAL_WITNESSES:
        assert (globals().get(name) is not None) is SANDBOX
    if os.environ.get("CI") and sys.platform == "darwin":
        assert SANDBOX, "macOS CI host has no sandbox-exec"


@physical_seatbelt_witness
def test_seatbelt_denies_reads_writes_network_and_helper_tools(monkeypatch, tmp_path):
    secret = tmp_path / "answers" / "gold.patch"
    secret.parent.mkdir()
    secret.write_text("the gold fix")
    _enable(monkeypatch, tmp_path, secret=secret, outside=tmp_path / "answers" / "planted.txt")
    contract, lease = _lease(tmp_path, venv=True)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: edit", timeout_seconds=60
    )
    probes = _observed(tmp_path, receipt)["probes"]
    assert probes["read_secret"].startswith("DENIED"), probes
    assert probes["write_outside"].startswith("DENIED") and probes["write_git"].startswith(
        "DENIED"
    ), probes
    assert probes["direct_net"].startswith("DENIED"), probes
    assert probes["proxy_github"].startswith("HTTP/1.1 403"), probes
    assert probes["exec_security"].startswith("DENIED") and probes["exec_open"].startswith(
        "DENIED"
    ), probes
    assert probes["exec_from_target"].startswith("DENIED"), probes
    assert not (tmp_path / "answers" / "planted.txt").exists()


def test_init_only_model_is_not_evidence_of_service():
    stream = "\n".join(
        json.dumps(e)
        for e in (
            {"type": "system", "subtype": "init", "model": "claude-haiku-5-5"},
            {"type": "result", "subtype": "success", "is_error": False},
        )
    )
    summary = cmw.summarize_stream_json(stream)
    assert summary.models_seen == ("claude-haiku-5-5",) and summary.served_models == ()


def test_sni_is_read_across_fragmented_records():
    hello = _client_hello("api.anthropic.com")
    body = hello[5:]
    cut = len(body) // 3
    fragmented = b"".join(
        b"\x16" + hello[1:3] + len(part).to_bytes(2, "big") + part
        for part in (body[:cut], body[cut:])
    )
    assert cmw.tls_client_hello_sni(fragmented) == "api.anthropic.com"
    assert cmw.tls_client_hello_sni(fragmented[: len(fragmented) - 3]) is None  # incomplete


def test_key_redaction_covers_pieces_and_key_shapes():
    data = f"a {FAKE_KEY} b {FAKE_KEY[:20]} c {FAKE_KEY[20:]} d {FAKE_OTHER_KEY}".encode()
    out = cmw.redact_secrets(data, (FAKE_KEY,))
    for piece in (FAKE_KEY, FAKE_KEY[:20], FAKE_KEY[20:40]):
        assert piece.encode() not in out
    assert (b"sk" + b"-ant-") not in out


@physical_seatbelt_witness
def test_seatbelt_denies_signals_to_processes_outside_the_sandbox(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    contract, lease = _lease(tmp_path)
    outside = subprocess.Popen(["/bin/sleep", "60"])
    try:
        (Path(lease.target_worktree) / ".outside_pid").write_text(str(outside.pid))
        receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
            contract, lease, prompt="WHAT: x", timeout_seconds=60
        )
        probes = _observed(tmp_path, receipt)["probes"]
        assert probes["signal_outside"].startswith("DENIED"), probes
        assert outside.poll() is None  # still running
    finally:
        outside.kill()
        outside.wait()


def _linked_worktree_lease(tmp_path: Path):
    """A P1-shaped lease: a ``git worktree`` of a Controller outside the targets root."""
    controller = tmp_path / "ctl" / "base"
    controller.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=controller, check=True)
    (controller / "README.md").write_text("# Repo\n")
    subprocess.run(["git", "add", "-A"], cwd=controller, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-qm", "base"],
        cwd=controller,
        check=True,
    )
    root = tmp_path / "targets"
    root.mkdir()
    target = root / "t1"
    subprocess.run(
        ["git", "worktree", "add", "-q", "--detach", str(target)], cwd=controller, check=True
    )
    contract = SimpleNamespace(
        task_id="t1",
        target_worktree_root=str(root),
        target_repo_root=str(target),
        controller_repo_root=str(controller),
    )
    return contract, SimpleNamespace(task_id="t1", target_worktree=str(target))


@physical_seatbelt_witness
def test_git_status_works_alike_in_a_standalone_repo_and_a_p1_worktree(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    results = {}
    for name, make in (
        ("standalone", lambda base: _lease(base)),
        ("worktree", _linked_worktree_lease),
    ):
        base = tmp_path / name
        base.mkdir()
        monkeypatch.setenv(cmw.MEASUREMENT_TRACE_DIR_ENV, str(base / "traces"))
        contract, lease = make(base)
        subprocess.run(["git", "add", "-A"], cwd=lease.target_worktree, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@invalid",
                "commit",
                "-qm",
                "c",
                "--allow-empty",
            ],
            cwd=lease.target_worktree,
            check=True,
        )
        receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
            contract, lease, prompt="WHAT: x", timeout_seconds=60
        )
        trace = base / "traces" / "t1" / f"{receipt.stdout_sha256}.stream.jsonl"
        results[name] = json.loads(trace.read_text().splitlines()[0])["fake_observed"]["probes"][
            "git_status"
        ]
    assert results["standalone"]["rc"] == 0, results
    assert results["worktree"] == results["standalone"], results


def test_worktree_git_dirs_follow_the_gitdir_file(tmp_path):
    contract, lease = _linked_worktree_lease(tmp_path)
    target = Path(lease.target_worktree)
    dirs = cmw.worktree_git_dirs(target, contract.controller_repo_root)
    common = Path(os.path.realpath(Path(contract.controller_repo_root) / ".git"))
    assert common in dirs and any(common in d.parents for d in dirs)
    assert cmw.worktree_git_dirs(target) == []  # no Controller named: nothing admitted
    _standalone, lease2 = _lease(tmp_path / "s")
    assert cmw.worktree_git_dirs(Path(lease2.target_worktree), contract.controller_repo_root) == []


def test_a_repointed_gitdir_is_never_admitted(tmp_path):
    contract, lease = _linked_worktree_lease(tmp_path)
    private = tmp_path / "private-dir"
    private.mkdir()
    (private / "commondir").write_text(str(tmp_path))
    (Path(lease.target_worktree) / ".git").write_text(f"gitdir: {private}\n")
    assert cmw.worktree_git_dirs(Path(lease.target_worktree), contract.controller_repo_root) == []


def test_cli_timeout_is_the_cap_minus_the_snapshot_reserve():
    assert cmw.measurement_cli_timeout(900, {}) == 870
    assert cmw.measurement_cli_timeout(None, {cmw.MEASUREMENT_CLAUDE_TIMEOUT_ENV: "600"}) == 570
    assert cmw.measurement_cli_timeout(300, {cmw.MEASUREMENT_CLAUDE_TIMEOUT_ENV: "600"}) == 270


def test_cli_dir_must_hold_only_executables(tmp_path):
    exe = _fake_claude(tmp_path)
    assert cmw.cli_install_dir_ok(exe.parent)
    (exe.parent / "gateway.token").write_text("secret")
    assert not cmw.cli_install_dir_ok(exe.parent)


def test_trace_is_never_written_into_the_worktree(tmp_path):
    target = tmp_path / "targets" / "t1"
    target.mkdir(parents=True)
    inside = {cmw.MEASUREMENT_TRACE_DIR_ENV: str(target / "traces")}
    assert cmw.write_measurement_trace("t1", b"x", "a" * 64, {}, inside, target=target) is None
    # A trace root whose <root>/<task_id> IS the worktree (Codex r3).
    ancestor = {cmw.MEASUREMENT_TRACE_DIR_ENV: str(tmp_path / "targets")}
    assert cmw.write_measurement_trace("t1", b"x", "a" * 64, {}, ancestor, target=target) is None
    assert not list(target.iterdir())
    elsewhere = {cmw.MEASUREMENT_TRACE_DIR_ENV: str(tmp_path / "tr")}
    assert cmw.write_measurement_trace("t1", b"x", "a" * 64, {}, elsewhere, target=target)


@pytest.mark.parametrize("bad", ['a"b', "a\\b", "a\nb"])
def test_sbpl_paths_reject_profile_metacharacters(bad):
    with pytest.raises(ValueError):
        cmw._sbpl(bad)


def test_sidecar_records_key_label_and_id_never_the_key(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(cmw.MEASUREMENT_KEY_LABEL_ENV, "measure-key-1")
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(
        contract, lease, prompt="WHAT: x", timeout_seconds=60
    )
    side = json.loads(
        (tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.run.json").read_text()
    )
    assert side["key_label"] == "measure-key-1"
    assert side["api_key_sha256_12"] == cmw.api_key_id(FAKE_KEY) and FAKE_KEY not in json.dumps(
        side
    )
    assert side["cli_timeout_seconds"] == 30.0


def test_a_worktree_of_a_controller_outside_the_measurement_root_fails_the_run(
    monkeypatch, tmp_path
):
    """Review H2': a shared Controller (e.g. the Gateway's Nexus-new checkout) could
    expose a later fix through ``git log --all``; such a run never starts."""
    _enable(monkeypatch, tmp_path)
    outside = tmp_path / "shared"
    outside.mkdir()
    contract, lease = _linked_worktree_lease(outside)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=contract.controller_repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(["git", "branch", "future", head], cwd=contract.controller_repo_root, check=True)
    monkeypatch.setenv(cmw.MEASURE_EXTERNAL_TARGET_ROOT_ENV, str(tmp_path / "measurement-root"))
    with pytest.raises(WorkerProviderUnavailable, match="worktree_gitdir_outside_measurement_root"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(
            contract, lease, prompt="WHAT: x", timeout_seconds=60
        )
    monkeypatch.delenv(cmw.MEASURE_EXTERNAL_TARGET_ROOT_ENV)
    with pytest.raises(WorkerProviderUnavailable, match="worktree_gitdir_outside_measurement_root"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(
            contract, lease, prompt="WHAT: x", timeout_seconds=60
        )
    assert not (tmp_path / "traces").exists()  # no CLI process was started


def test_a_standalone_target_needs_no_measurement_root(tmp_path):
    _contract, lease = _lease(tmp_path)
    cmw.require_gitdir_in_measurement_root(Path(lease.target_worktree), {})
