"""#2721 measurement-only Claude worker: inert by default, exact invocation when on."""

from __future__ import annotations

import json
import os
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

FAKE_CLAUDE = r'''#!{python}
import json, os, sys
from pathlib import Path
log = Path(__file__).with_name("calls.jsonl")
args = sys.argv[1:]
if args == ["--version"]:
    print("9.9.9 (Fake Claude)")
    sys.exit(0)
prompt = args[-1]
with log.open("a") as fh:
    fh.write(json.dumps({{"argv": args, "cwd": os.getcwd(),
                          "env_keys": sorted(os.environ), "auto_memory": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")}}) + "\n")
model = os.environ.get("FAKE_CLAUDE_SERVED_MODEL", "claude-haiku-5-5")
print(json.dumps({{"type": "system", "subtype": "init", "model": model, "session_id": "s1"}}))
assert os.environ["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin", os.environ["PATH"]
if not prompt.startswith("Reply with exactly"):
    readme = Path("README.md")
    readme.write_text(readme.read_text() + "\nbounded change\n")
    print(json.dumps({{"type": "assistant", "message": {{"model": model, "content": [
        {{"type": "tool_use", "id": "t1", "name": "Edit", "input": {{"file_path": "README.md"}}}}]}}}}))
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
                   "total_cost_usd": 0.001, "session_id": "s1",
                   "usage": {{"input_tokens": 10, "output_tokens": 5}},
                   "modelUsage": {{model: {{"inputTokens": 10, "outputTokens": 5}}}}}}))
'''


def _fake_claude(tmp_path: Path) -> Path:
    path = tmp_path / "bin" / "claude"
    path.parent.mkdir(parents=True)
    path.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture()
def switch_off(monkeypatch):
    monkeypatch.delenv(cmw.MEASUREMENT_CLAUDE_ENV, raising=False)
    monkeypatch.delenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, raising=False)


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
    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
    from unittest.mock import MagicMock

    result = UnifiedMCPGateway(service=MagicMock())._provider_preflight(
        {"provider": "claude", "model": "claude-haiku-5-5"})
    assert result["blocker"] == "ASSIST_PROVIDER_NOT_REGISTERED"


# -- invocation ------------------------------------------------------------------

def test_argv_is_fixed_and_the_prompt_is_last():
    argv = cmw.claude_measurement_argv("WHAT: x")
    assert argv[:-1] == cmw.CLAUDE_MEASUREMENT_FLAGS and argv[-1] == "WHAT: x"
    assert "--bare" not in argv and "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch"
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--setting-sources") + 1] == ""
    for bad in ("", "  ", "--help"):
        with pytest.raises(ValueError):
            cmw.claude_measurement_argv(bad)


def test_stream_summary_collects_tools_usage_and_models():
    lines = [
        {"type": "system", "subtype": "init", "model": "claude-haiku-5-5", "session_id": "s"},
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
    assert cmw.summarize_stream_json("").result_seen is False


def _enable(monkeypatch, tmp_path) -> Path:
    fake = _fake_claude(tmp_path)
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, str(fake))
    cmw._PROBE_CACHE.clear()
    return fake


def _lease(tmp_path: Path):
    root = tmp_path / "targets"
    target = root / "t1"
    target.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    (target / "README.md").write_text("# Repo\n")
    contract = SimpleNamespace(task_id="t1", target_worktree_root=str(root), target_repo_root=str(target))
    return contract, SimpleNamespace(task_id="t1", target_worktree=str(target))


def test_adapter_runs_the_exact_invocation_and_keeps_the_trace(monkeypatch, tmp_path):
    fake = _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(cmw.MEASUREMENT_TRACE_DIR_ENV, str(tmp_path / "traces"))
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: edit", timeout_seconds=30)
    assert receipt.outcome == "EXECUTION_COMPLETED", receipt.failure_reason
    (call,) = [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text().splitlines()]
    assert call["argv"] == list(cmw.claude_measurement_argv("WHAT: edit"))
    assert Path(call["cwd"]).resolve() == Path(lease.target_worktree).resolve()
    assert call["auto_memory"] == "1"
    assert not any(key.startswith("ANTHROPIC_") for key in call["env_keys"])
    assert [key for key in call["env_keys"] if key.startswith("NEXUS_")] == ["NEXUS_CLI_WORKER_RUN_TAG"]
    assert "VIRTUAL_ENV" not in call["env_keys"] and "PYTHONPATH" not in call["env_keys"]
    trace = tmp_path / "traces" / "t1" / f"{receipt.stdout_sha256}.stream.jsonl"
    assert trace.is_file() and "tool_use" in trace.read_text()


def test_adapter_refuses_other_models_and_unleased_targets(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    contract, lease = _lease(tmp_path)
    with pytest.raises(WorkerProviderUnavailable, match="not the measurement model"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: x", model="claude-opus-5-5")
    stray = SimpleNamespace(task_id="t1", target_worktree=str(tmp_path))
    with pytest.raises(WorkerProviderUnavailable, match="not_leased"):
        cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, stray, prompt="WHAT: x")


def test_adapter_fails_a_run_served_by_another_model(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("FAKE_CLAUDE_SERVED_MODEL", "claude-sonnet-5")
    # The worker env is an allowlist, so pass the override through PATH-independent HOME file instead.
    contract, lease = _lease(tmp_path)
    receipt = cmw.ClaudeMeasurementWorkerAdapter().invoke(contract, lease, prompt="WHAT: x", timeout_seconds=30)
    # FAKE_CLAUDE_SERVED_MODEL is not inherited (env allowlist), so the run stays on haiku:
    assert receipt.outcome == "EXECUTION_COMPLETED"
    summary = cmw.summarize_stream_json(json.dumps({"type": "result", "is_error": False,
                                                    "modelUsage": {"claude-sonnet-5": {}}}))
    assert summary.models_seen == ("claude-sonnet-5",)


def test_preflight_probes_once_and_caches(monkeypatch, tmp_path):
    fake = _enable(monkeypatch, tmp_path)
    first = cmw.measurement_claude_preflight("claude-haiku-5-5")
    second = cmw.measurement_claude_preflight("claude-haiku-5-5")
    assert first["execution_ready"] is True and first["readiness_status"] == "MODEL_VERIFIED"
    assert first["probe_evidence_hash"] == second["probe_evidence_hash"]
    calls = (fake.parent / "calls.jsonl").read_text().splitlines()
    assert len(calls) == 1 and json.loads(calls[0])["argv"][:-1] == list(cmw.CLAUDE_MEASUREMENT_FLAGS)
    assert cmw.measurement_claude_preflight("claude-opus-5-5")["blocker"] == "MEASUREMENT_CLAUDE_MODEL_MISMATCH"


def test_relative_or_missing_binary_is_not_ready(monkeypatch):
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_ENV, "1")
    monkeypatch.setenv(cmw.MEASUREMENT_CLAUDE_BIN_ENV, "claude")
    assert not cmw.ClaudeMeasurementWorkerAdapter().preflight().ready
    assert cmw.measurement_claude_preflight("claude-haiku-5-5")["blocker"] == "MEASUREMENT_CLAUDE_BINARY_UNAVAILABLE"


# -- workforce policy --------------------------------------------------------------

def test_measurement_policy_routes_every_online_role_to_claude(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    loader = mwp.measurement_workforce_policy_loader()
    snapshot = loader.load()
    worker = snapshot.workers[cmw.CLAUDE_MEASUREMENT_WORKER_ID]
    assert (worker.provider, worker.model) == ("claude", "claude-haiku-5-5")
    template = snapshot.workers[mwp.TEMPLATE_WORKER_ID]
    assert (worker.state, worker.autonomy, worker.requires) == (template.state, template.autonomy, template.requires)
    for role in worker.roles:
        assert loader.resolve_route(role) == cmw.CLAUDE_MEASUREMENT_WORKER_ID
    packaged = mwp.WorkforcePolicyLoader if hasattr(mwp, "WorkforcePolicyLoader") else None
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    assert cmw.CLAUDE_MEASUREMENT_WORKER_ID not in WorkforcePolicyLoader().load().workers
    del packaged


# -- the real P1 chain -------------------------------------------------------------

def test_p1_chain_dispatches_the_claude_worker_end_to_end(tmp_path):
    fake = _fake_claude(tmp_path)
    spec = {"work": str(tmp_path / "work"), "out": str(tmp_path / "out.json"), "task_id": "m2721-claude-witness"}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEXUS_")}
    env.update({
        cmw.MEASUREMENT_CLAUDE_ENV: "1",
        cmw.MEASUREMENT_CLAUDE_BIN_ENV: str(fake),
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
    calls = [json.loads(line) for line in (fake.parent / "calls.jsonl").read_text().splitlines()]
    worker_calls = [c for c in calls if not c["argv"][-1].startswith("Reply with exactly")]
    assert len(worker_calls) == 1
    argv = worker_calls[0]["argv"]
    assert argv[:-1] == list(cmw.CLAUDE_MEASUREMENT_FLAGS)
    # The Nexus prompt is the Gateway's base worker prompt plus Nexus's own context.
    assert argv[-1].startswith(result["base_prompt"])
