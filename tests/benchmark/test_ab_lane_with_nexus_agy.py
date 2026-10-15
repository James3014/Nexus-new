"""With-Nexus arm of the A/B lane reaches agy through the unified runtime (issue #1844).

The sprint candidate generator used to send no ``workforce_bindings``, so the runtime refused
the call with ``workforce_bindings must be an object mapping`` before any provider call. The lane
now declares the exact agy identity; Workforce Admission still decides, and a fake agy executable
proves the row reaches the provider.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from nexus.research.sprint_service import (
    BENCH_WORKFORCE_BINDINGS_ENV,
    LLMCandidateGenerator,
)
from scripts.bench.agy_provider import (
    AGY_DEFAULT_MODEL,
    AGY_LANE_CONTROLS,
    agy_workforce_bindings,
    configure_agy_lane_env,
)

REPLY = json.dumps({
    "status": "APPROVED",
    "operation": "replace",
    "target_snippet": "return text",
    "replacement": "return text.strip()",
})

# Mirrors the real print-mode contract the runtime enforces since runtime #205: glog-format
# identity lines go into the ``--log-file`` path (the served-model witness; without them the
# runtime returns ``model_identity_unobserved``) and the JSON envelope goes to stdout.
FAKE_AGY = """#!{python}
import json, sys
argv = sys.argv[1:]
open({log!r}, "a").write(json.dumps(argv) + "\\n")
model = argv[argv.index("--model") + 1] if "--model" in argv else ""
if "--log-file" in argv:
    with open(argv[argv.index("--log-file") + 1], "a") as glog:
        glog.write("I1014 10:36:21.492269       1 model_resolver.go:93] Resolving model " + model + "\\n")
        glog.write(
            "I1014 10:36:21.492301       1 model_config_manager.go:328] "
            'Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"\\n'
        )
print(json.dumps({{"conversation_id": "c1", "status": "SUCCESS", "response": {reply!r},
                  "duration_seconds": 0.1, "num_turns": 1,
                  "usage": {{"input_tokens": 900, "output_tokens": 100, "total_tokens": 1000}}}}))
"""


def _lane_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, bindings: bool) -> Path:
    log = tmp_path / "argv.log"
    exe = tmp_path / "bin" / "agy"
    exe.parent.mkdir()
    exe.write_text(
        FAKE_AGY.format(python=sys.executable, log=str(log), reply=REPLY), encoding="utf-8"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    env: dict[str, str] = {}
    configure_agy_lane_env(env)
    for key, value in env.items():
        if key == BENCH_WORKFORCE_BINDINGS_ENV and not bindings:
            continue
        monkeypatch.setenv(key, value)
    if not bindings:
        monkeypatch.delenv(BENCH_WORKFORCE_BINDINGS_ENV, raising=False)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    # Test-owned workspace policy (the lane's online authorization is not part of this change).
    policy = tmp_path / ".nexus" / "online_execution_policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({"default_online_policy": "auto"}), encoding="utf-8")
    return log


def _ask(tmp_path: Path) -> dict:
    generator = LLMCandidateGenerator(tmp_path, safe_mode=True, target_file="demo.py")
    generator._workspace_revision = lambda: "revision-agy-001"
    _out, _raw, receipt = generator._ask_unified_candidate(
        prompt="fix normalize",
        payload="Return one small edit.",
        task="fix normalize",
        seed=1,
        attempt=1,
        model=AGY_DEFAULT_MODEL,
    )
    return receipt


def test_agy_lane_env_declares_exact_identity_binding_mapping():
    env: dict[str, str] = {}
    configure_agy_lane_env(env)
    assert env["NEXUS_OAUTH_PROVIDER"] == "agy"
    bindings = json.loads(env[BENCH_WORKFORCE_BINDINGS_ENV])
    assert bindings == agy_workforce_bindings(AGY_DEFAULT_MODEL)
    assert bindings["online"]["provider"] == "agy"
    assert bindings["online"]["model"] == AGY_DEFAULT_MODEL
    assert bindings["online"]["controls"] == list(AGY_LANE_CONTROLS)
    assert "worker_id" not in bindings["online"]


def test_with_nexus_row_reaches_agy_and_resolves_agy_flash_38(monkeypatch, tmp_path: Path):
    log = _lane_env(monkeypatch, tmp_path, bindings=True)
    receipt = _ask(tmp_path)

    admission = receipt["workforce_admission"]
    assert admission["overall_decision"] == "ALLOW"
    assert admission["records"][0]["decision"]["resolved_worker_id"] == "agy_flash_38"
    online = receipt["online"]
    authority = online["context_trace"]["gateway_invocation_authority"]
    assert authority["resolved_worker_id"] == "agy_flash_38"
    assert authority["resolved_provider"] == "agy"
    assert authority["resolved_model"] == AGY_DEFAULT_MODEL
    assert online["status"] == "SUCCEEDED"
    assert online["response"]["provider_call_count"] >= 1
    argv = json.loads(log.read_text().splitlines()[0])
    assert argv[argv.index("--model") + 1] == AGY_DEFAULT_MODEL


def test_without_bindings_the_runtime_still_refuses_before_any_provider_call(
    monkeypatch, tmp_path: Path
):
    log = _lane_env(monkeypatch, tmp_path, bindings=False)
    receipt = _ask(tmp_path)

    admission = receipt["workforce_admission"]
    assert admission["overall_decision"] == "BLOCK"
    assert "workforce_bindings must be an object mapping" in " ".join(admission["overall_reasons"])
    assert receipt["online"]["invoked"] is False
    assert not log.exists()
