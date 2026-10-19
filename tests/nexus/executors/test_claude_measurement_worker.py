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
needs_sandbox = pytest.mark.skipif(not SANDBOX, reason="macOS sandbox-exec required")

FAKE_CLAUDE = r'''#!/usr/bin/python3
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
model = os.environ.get("FAKE_MODEL", "claude-haiku-5-5")
init = {"type": "system", "subtype": "init", "model": model, "session_id": "s1",
        "tools": ["Bash", "Edit", "Read", "Write"], "mcp_servers": [], "permissionMode": "acceptEdits",
        "claude_code_version": "9.9.9",
        "fake_observed": {"argv": args, "cwd": os.getcwd(), "env": dict(os.environ), "probes": probes}}
print(json.dumps(init))
if not prompt.startswith("Reply with exactly"):
    readme = Path("README.md")
    readme.write_text(readme.read_text() + "\nbounded change\n")
    print(json.dumps({"type": "assistant", "message": {"model": model, "content": [
        {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "README.md"}}]}}))
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "ratelimit":
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "terminal_reason": "api_error", "api_error_status": 429,
                      "result": "API Error: 429 rate_limit_error", "session_id": "s1"}))
    sys.exit(1)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
                  "total_cost_usd": 0.001, "session_id": "s1",
                  "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7,
                            "cache_creation_input_tokens": 3},
                  "modelUsage": {model: {"inputTokens": 10, "outputTokens": 5}}}))
'''


def _fake_claude(tmp_path: Path, *, secret: Path | None = None, outside: Path | None = None,
                 venv_file: Path | None = None) -> Path:
    path = tmp_path / "bin" / "claude"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (FAKE_CLAUDE.replace("__SECRET__", str(secret or ""))
            .replace("__OUTSIDE__", str(outside or tmp_path / "outside.txt"))
            .replace("__VENV_FILE__", str(venv_file or "")))
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return Path(os.path.realpath(path))


@pytest.fixture()
def switch_off(monkeypatch):
    for key in (cmw.MEASUREMENT_CLAUDE_ENV, cmw.MEASUREMENT_CLAUDE_BIN_ENV, cmw.MEASUREMENT_CLAUDE_TOKEN_FILE_ENV):
        monkeypatch.delenv(key, raising=False)


def _enable(monkeypatch, tmp_path, **fake) -> Path:
    exe = _fake_claude(tmp_path, **fake)
    token = tmp_path / "token"
    token.write_text("fake-oauth-token-123\n")
    token.chmod(0o600)
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, str(exe))
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_TOKEN_FILE_ENV, str(token))
    monkeypatch.setenv(cmw.MEASUREMENT_TRACE_DIR_ENV, str(tmp_path / "traces"))
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
        (controller.parent / "venv" / "bin" / "python").write_text("venv-python\n")
    contract = SimpleNamespace(task_id="t1", target_worktree_root=str(root), target_repo_root=str(target),
                               controller_repo_root=str(controller))
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
    assert preflight["blocker"] == "MEASUREMENT_CLAUDE_WORKER_DISABLED" and not preflight["execution_ready"]
    assert not cmw.ClaudeMeasurementWorkerAdapter().preflight().ready


def test_registry_rejects_a_claude_adapter_while_switched_off(switch_off):
    adapters = dict(WorkerRegistry.default()._adapters)
    adapters["claude"] = cmw.ClaudeMeasurementWorkerAdapter()
    with pytest.raises(ValueError, match="unknown worker providers"):
        WorkerRegistry(adapters)


def test_gateway_preflight_for_claude_is_unregistered_while_switched_off(switch_off):
    from unittest.mock import MagicMock

    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

    result = UnifiedMCPGateway(service=MagicMock())._provider_preflight(
        {"provider": "claude", "model": "claude-haiku-5-5"})
    assert result["blocker"] == "ASSIST_PROVIDER_NOT_REGISTERED"


# -- invocation ------------------------------------------------------------------

def test_argv_is_fixed_and_the_prompt_is_last():
    argv = cmw.claude_measurement_argv("WHAT: x")
    assert argv[:-1] == cmw.CLAUDE_MEASUREMENT_FLAGS and argv[-1] == "WHAT: x"
    assert "--bare" not in argv and "--dangerously-skip-permissions" not in argv
    assert "--fallback-model" not in argv
    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch,Task,Agent"
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}' and "--strict-mcp-config" in argv
    for bad in ("", "  ", "--help"):
        with pytest.raises(ValueError):
            cmw.claude_measurement_argv(bad)


def test_executable_must_be_absolute_and_not_a_symlink(tmp_path):
    real = _fake_claude(tmp_path)
    link = tmp_path / "claude-link"
    link.symlink_to(real)
    assert cmw.measurement_claude_executable({cmw.MEASUREMENT_CLAUDE_BIN_ENV: str(real)}) == str(real)
    for raw in ("claude", str(link), str(tmp_path / "missing")):
        assert cmw.measurement_claude_executable({cmw.MEASUREMENT_CLAUDE_BIN_ENV: raw}) is None


def test_token_file_must_be_private(tmp_path):
    token = tmp_path / "tok"
    token.write_text("abc\n")
    token.chmod(0o644)
    assert cmw.measurement_claude_token({cmw.MEASUREMENT_CLAUDE_TOKEN_FILE_ENV: str(token)}) is None
    token.chmod(0o600)
    assert cmw.measurement_claude_token({cmw.MEASUREMENT_CLAUDE_TOKEN_FILE_ENV: str(token)}) == "abc"
    assert cmw.measurement_claude_token({cmw.CLAUDE_OAUTH_TOKEN_ENV: "envtok"}) == "envtok"


def test_stream_summary_collects_tools_usage_models_and_init():
    lines = [
        {"type": "system", "subtype": "init", "model": "claude-haiku-5-5", "session_id": "s",
         "tools": ["Read"], "mcp_servers": [], "secret_field": "x"},
        {"type": "assistant", "message": {"model": "claude-haiku-5-5", "content": [
            {"type": "text", "text": "hi"}, {"type": "tool_use", "id": "a", "name": "Read", "input": {"p": 1}}]}},
        "not json",
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "total_cost_usd": 0.01,
         "usage": {"input_tokens": 7}, "modelUsage": {"claude-haiku-5-5": {}, "claude-other": {}}},
    ]
    text = "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
    summary = cmw.summarize_stream_json(text)
    assert summary.result_seen and summary.is_error is False and summary.num_turns == 3
    assert [call["name"] for call in summary.tool_calls] == ["Read"]
    assert summary.models_seen == ("claude-haiku-5-5", "claude-other")
    assert summary.init == {"tools": ["Read"], "mcp_servers": [], "model": "claude-haiku-5-5"}
    assert cmw.summarize_stream_json("").result_seen is False


@pytest.mark.parametrize(("result", "stderr", "expected"), [
    ({"is_error": True, "terminal_reason": "api_error", "api_error_status": 429, "result": "rate_limit_error"}, "", "rate_limited"),
    ({"is_error": True, "terminal_reason": "api_error", "api_error_status": 529, "result": "Overloaded"}, "", "overloaded"),
    ({"is_error": False, "terminal_reason": "api_error", "result": "Not logged in · Please run /login"}, "", "auth"),
    ({"is_error": True, "subtype": "error_max_turns", "result": "stopped"}, "", None),
    ({"is_error": False, "subtype": "success", "result": "done"}, "", None),
])
def test_infra_classification(result, stderr, expected):
    summary = cmw.summarize_stream_json(json.dumps({"type": "result", **result}))
    assert cmw.classify_claude_infra(summary, stderr) == expected


def test_seatbelt_profile_shape(tmp_path):
    profile = cmw.build_claude_seatbelt_profile(target=tmp_path / "t", run_root=tmp_path / "r",
                                                readable=(tmp_path / "v",), proxy_port=4567)
    assert "(deny network-outbound)" in profile
    assert '(allow network-outbound (remote ip "localhost:4567"))' in profile
    assert "(deny file-read-data" in profile and '(subpath "/Users")' in profile
    assert f'(deny file-write* (literal "{os.path.realpath(tmp_path / "t")}/.git")' in profile


def test_proxy_tunnels_only_the_api_host():
    with cmw.HostAllowlistProxy(allowed_hosts=("api.anthropic.com",)) as proxy:
        for line in (b"CONNECT github.com:443 HTTP/1.1\r\n\r\n", b"GET http://pypi.org/ HTTP/1.1\r\n\r\n",
                     b"CONNECT api.anthropic.com:80 HTTP/1.1\r\n\r\n"):
            sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=5)
            sock.sendall(line)
            assert sock.recv(64).startswith(b"HTTP/1.1 403")
            sock.close()
    assert [a["allowed"] for a in proxy.attempts] == [False, False, False]
    assert [a["host"] for a in proxy.attempts][0] == "github.com"


@needs_sandbox
def test_adapter_runs_the_exact_isolated_sandboxed_invocation(monkeypatch, tmp_path):
    secret = tmp_path / "answers" / "gold.patch"
    secret.parent.mkdir()
    secret.write_text("the gold fix")
    _enable(monkeypatch, tmp_path, secret=secret, outside=tmp_path / "answers" / "planted.txt")
    contract, lease = _lease(tmp_path, venv=True)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: edit", timeout_seconds=60)
    assert receipt.outcome == "EXECUTION_COMPLETED", (receipt.failure_reason, receipt.stderr_tail)
    seen = _observed(tmp_path, receipt)
    assert seen["argv"] == list(cmw.claude_measurement_argv("WHAT: edit"))
    assert Path(seen["cwd"]).resolve() == Path(lease.target_worktree).resolve()
    env = seen["env"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "fake-oauth-token-123"
    assert env["HOME"] != os.environ.get("HOME") and env["CLAUDE_CONFIG_DIR"].startswith(env["HOME"])
    assert env["DISABLE_AUTOUPDATER"] == "1" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    venv = os.path.realpath(tmp_path / "ctl" / "venv")
    assert env["PATH"] == f"{venv}/bin:" + cmw.CLAUDE_MEASUREMENT_SYSTEM_PATH and env["VIRTUAL_ENV"] == venv
    assert not any(key.startswith(("ANTHROPIC_", "GITHUB_", "GH_TOKEN")) for key in env)
    probes = seen["probes"]
    assert probes["read_secret"].startswith("DENIED"), probes
    assert probes["write_outside"].startswith("DENIED") and probes["write_git"].startswith("DENIED"), probes
    assert probes["direct_net"].startswith("DENIED"), probes
    assert probes["proxy_github"].startswith("HTTP/1.1 403"), probes
    assert not (tmp_path / "answers" / "planted.txt").exists()
    sidecar = json.loads((tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.run.json").read_text())
    assert sidecar["proxy_attempts"] == [{"host": "github.com", "port": 443, "allowed": False}]
    assert sidecar["init"]["mcp_servers"] == [] and sidecar["seatbelt_sha256"] == receipt.provider_permission_profile_sha256
    assert "fake-oauth-token-123" not in json.dumps(sidecar)


@needs_sandbox
def test_adapter_marks_provider_rate_limits_as_infra(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(cmw, "CLAUDE_MEASUREMENT_ENV", {**cmw.CLAUDE_MEASUREMENT_ENV, "FAKE_MODE": "ratelimit"})
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: x", timeout_seconds=60)
    assert receipt.outcome == "FAILED" and receipt.failure_reason == "claude_infra:rate_limited"


@needs_sandbox
def test_adapter_fails_a_run_served_by_another_model(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(cmw, "CLAUDE_MEASUREMENT_ENV", {**cmw.CLAUDE_MEASUREMENT_ENV, "FAKE_MODEL": "claude-sonnet-5"})
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: x", timeout_seconds=60)
    assert receipt.outcome == "FAILED" and "model substitution observed" in receipt.failure_reason


def test_adapter_refuses_other_models_and_unleased_targets(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    contract, lease = _lease(tmp_path)
    with pytest.raises(WorkerProviderUnavailable, match="not the measurement model"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: x", model="claude-opus-5-5")
    stray = SimpleNamespace(task_id="t1", target_worktree=str(tmp_path))
    with pytest.raises(WorkerProviderUnavailable, match="not_leased"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, stray, prompt="WHAT: x")


@needs_sandbox
def test_preflight_probes_once_and_caches(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    first = cmw.measurement_claude_preflight("claude-haiku-5-5")
    second = cmw.measurement_claude_preflight("claude-haiku-5-5")
    assert first["execution_ready"] is True and first["readiness_status"] == "MODEL_VERIFIED", first
    assert first["probe_evidence_hash"] == second["probe_evidence_hash"]
    assert cmw.measurement_claude_preflight("claude-opus-5-5")["blocker"] == "MEASUREMENT_CLAUDE_MODEL_MISMATCH"
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_VERSION_ENV, "2.1.303")
    assert cmw.measurement_claude_preflight("claude-haiku-5-5")["blocker"] == "MEASUREMENT_CLAUDE_VERSION_MISMATCH"


def test_relative_binary_is_not_ready(monkeypatch):
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, "claude")
    assert not cmw.ClaudeMeasurementWorkerAdapter().preflight().ready
    assert cmw.measurement_claude_preflight("claude-haiku-5-5")["blocker"] == "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE"


# -- workforce policy --------------------------------------------------------------

def test_measurement_policy_routes_every_online_role_to_claude(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    loader = mwp.measurement_workforce_policy_loader()
    snapshot = loader.load()
    worker = snapshot.workers[cmw.CLAUDE_MEASUREMENT_WORKER_ID]
    assert (worker.provider, worker.model) == ("claude", "claude-haiku-5-5")
    template = snapshot.workers[mwp.TEMPLATE_WORKER_ID]
    assert (worker.state, worker.autonomy, worker.requires) == (template.state, template.autonomy, template.requires)
    for role in worker.roles:
        assert loader.resolve_route(role) == cmw.CLAUDE_MEASUREMENT_WORKER_ID
    assert cmw.CLAUDE_MEASUREMENT_WORKER_ID not in WorkforcePolicyLoader().load().workers


# -- the real P1 chain -------------------------------------------------------------

@needs_sandbox
def test_p1_chain_dispatches_the_claude_worker_end_to_end(tmp_path):
    fake = _fake_claude(tmp_path)
    token = tmp_path / "token"
    token.write_text("fake-oauth-token-123\n")
    token.chmod(0o600)
    spec = {"work": str(tmp_path / "work"), "out": str(tmp_path / "out.json"), "task_id": "m2721-claude-witness"}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEXUS_")}
    env.update({
        cmw.MEASUREMENT_CLAUDE_ENV: "1",
        cmw.MEASUREMENT_CLAUDE_BIN_ENV: str(fake),
        cmw.MEASUREMENT_CLAUDE_TOKEN_FILE_ENV: str(token),
        cmw.MEASUREMENT_TRACE_DIR_ENV: str(tmp_path / "traces"),
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), env.get("PYTHONPATH", "")]),
    })
    subprocess.run([sys.executable, str(DRIVER), str(spec_path)], cwd=REPO_ROOT, env=env, check=True, timeout=600)
    result = json.loads((tmp_path / "out.json").read_text())
    assert "driver_error" not in result, result.get("trace")
    assert result["gateway_is_error"] is False, result.get("gateway_error")
    assert (result["request_provider"], result["request_model"]) == ("claude", "claude-haiku-5-5")
    assert result["request_worker_id"] == cmw.CLAUDE_MEASUREMENT_WORKER_ID
    assert result["selected_provider"] == "claude", result
    assert result["execution_providers"] == ["claude"]
    assert result["receipt_verified"] is True, result["receipt_failure_reasons"]
    assert "+bounded change" in (result.get("candidate_diff") or ""), json.dumps(result, indent=1)[:4000]
    traces = sorted((tmp_path / "traces" / spec["task_id"]).glob("*.stream.jsonl"))
    assert len(traces) == 1
    seen = json.loads(traces[0].read_text().splitlines()[0])["fake_observed"]
    assert seen["argv"][:-1] == list(cmw.CLAUDE_MEASUREMENT_FLAGS)
    # The Nexus prompt is the Gateway's base worker prompt plus Nexus's own context.
    assert seen["argv"][-1].startswith(result["base_prompt"])
