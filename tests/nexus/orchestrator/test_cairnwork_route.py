"""Council F: forwarding one task type from nexus_worker_candidate to Cairnwork.

``cairnwork-route`` is replaced by a fake command that records every call and
answers from a table, so these tests need no Cairnwork install, no model and no
network. The contract it imitates: James3014/cairnwork docs/GATEWAY_ROUTE.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import cairnwork_route as cr


class _CaptureService(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.submitted: list[Any] = []
        self.state_dir = state_dir

    def submit_task(self, request):  # type: ignore[override]
        self.submitted.append(request)
        return {"status": "PENDING_HUMAN_APPROVAL", "task_id": request["task_id"]}

    def get_task_snapshot(self, task_id):  # type: ignore[override]
        known = {r["task_id"] for r in self.submitted}
        return {"task_id": task_id, "status": "RUNNING"} if task_id in known else None

    def cancel_task(self, task_id):  # type: ignore[override]
        return {"task_id": task_id, "service": "self_hosted"}


def _ready_preflight(**_: Any) -> dict[str, Any]:
    return {
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "provider": "agy",
        "requested_model": "gemini-3.8-flash-medium",
        "resolved_model": "gemini-3.8-flash-medium",
        "model_reachable": True,
        "requested_model_verified": True,
        "authenticated": True,
        "authentication_evidence": "successful_exact_model_probe",
        "probe_evidence_hash": "e" * 64,
        "binary_path": "/usr/bin/true",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "c" * 64,
        "probe_expires_at": "2099-01-01T00:00:00+00:00",
    }


def _fake_route(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A cairnwork-route stand-in: answers from answers.json, logs to calls.jsonl."""
    answers, calls = tmp_path / "answers.json", tmp_path / "calls.jsonl"
    answers.write_text("{}", encoding="utf-8")
    script = tmp_path / "cairnwork-route"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "args = sys.argv[3:]\n"
        "stdin = sys.stdin.read()\n"
        f"open({str(calls)!r}, 'a').write(json.dumps({{'args': args, 'stdin': stdin}}) + '\\n')\n"
        f"table = json.load(open({str(answers)!r}))\n"
        "code, out = table.get(args[0], [1, {'error': 'NO_ANSWER'}])\n"
        "print(json.dumps(out))\n"
        "sys.exit(code)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, answers, calls


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    import nexus.orchestrator.self_hosted_task_service as service_module
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    card_root = tmp_path / "canonical-test-repo"
    card_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=card_root, check=True)
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    original_guard = gateway_module.pre_action_guard
    monkeypatch.setattr(
        gateway_module,
        "pre_action_guard",
        lambda action, **kwargs: original_guard(action, canonical_root=card_root, **kwargs),
    )
    script, answers, calls = _fake_route(tmp_path)
    monkeypatch.setattr(cr, "ROUTE_BIN_AT_START", str(script))
    monkeypatch.setattr(cr, "ROUTE_STATE_AT_START", str(tmp_path / "cairnwork-state"))
    state = tmp_path / "gateway-state"
    state.mkdir()
    service = _CaptureService(state)
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight())
    return {
        "card_root": card_root,
        "service": service,
        "gateway": gateway,
        "state": state,
        "answers": answers,
        "calls": calls,
        "monkeypatch": monkeypatch,
    }


def _mode(ctx, mode: str) -> None:
    ctx["monkeypatch"].setattr(cr, "ROUTE_MODE_AT_START", mode)


def _answer(ctx, **table: Any) -> None:
    ctx["answers"].write_text(json.dumps(table), encoding="utf-8")


def _calls(ctx) -> list[dict[str, Any]]:
    path = ctx["calls"]
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _arguments(ctx, task_id: str, **extra: Any) -> dict[str, Any]:
    relative = f"tasks/test/{task_id}.md"
    card = ctx["card_root"] / relative
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    return {
        "task_id": task_id,
        "what": "fix add()",
        "why": "it is off by one",
        "allowed_files": ["src/calc.py"],
        "verifier_commands": ["python3 -m pytest -q tests/test_calc.py"],
        "owner_confirmation": True,
        "task_card_path": relative,
        "task_card_hash": hashlib.sha256(card.read_bytes()).hexdigest(),
        **extra,
    }


def _tool(ctx, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = ctx["gateway"].handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _shadow_lines(ctx, count: int, limit: float = 10.0) -> list[dict[str, Any]]:
    """Shadow checks run in the background: wait for `count` lines."""
    path = ctx["state"] / "cairnwork_shadow.jsonl"
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        lines = path.read_text().splitlines() if path.exists() else []
        if len(lines) >= count:
            return [json.loads(line) for line in lines]
        time.sleep(0.05)
    raise AssertionError(f"expected {count} shadow lines")


def _state_files(ctx) -> list[str]:
    return sorted(str(p.relative_to(ctx["state"])) for p in ctx["state"].rglob("*"))


SUBMITTED = [0, {"task_id": "task-cw1", "status": "BOUND", "duplicate": False}]
STATUS = [
    0,
    {
        "task_id": "task-cw1",
        "status": "DISPATCHED",
        "core_verified": False,
        "candidate_commit": "",
        "phase": "WORKER_STARTED",
    },
]


def test_off_is_the_default_and_unknown_values_mean_off(monkeypatch):
    assert cr.route_mode() in ("off", "shadow", "route")
    monkeypatch.setattr(cr, "ROUTE_MODE_AT_START", "rout")
    assert cr.route_mode() == "off"


def test_off_changes_nothing_and_never_calls_cairnwork(ctx):
    _mode(ctx, "off")
    normal = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "off-1"))
    asked = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "off-2", worker="cairnwork"))
    assert normal["isError"] is False and normal["structuredContent"]["task_id"] == "off-1"
    assert asked["structuredContent"]["error"] == "WORKFORCE_ADMISSION_WORKER_MISMATCH"
    assert _calls(ctx) == [] and _state_files(ctx) == []


def test_shadow_only_logs_and_the_response_is_the_same_as_off(ctx):
    _mode(ctx, "off")
    off = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "same-1"))["structuredContent"]
    ctx["service"].submitted.clear()
    _mode(ctx, "shadow")
    _answer(ctx, check=[0, {"would_accept": False}])
    shadow = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "same-1"))["structuredContent"]
    assert shadow == off
    log = _shadow_lines(ctx, 1)
    assert [c["args"] for c in _calls(ctx)] == [["check"]]
    sent = json.loads(_calls(ctx)[0]["stdin"])
    assert sent["idempotency_key"] == "same-1" and sent["base_commit"] == "a" * 40
    assert sent["verifiers"] == [
        ["pytest-0", ["python3", "-m", "pytest", "-q", "tests/test_calc.py"]]
    ]
    assert log[0]["answer"] == {"would_accept": False}


def test_shadow_survives_a_broken_cairnwork_and_skips_other_shapes(ctx):
    _mode(ctx, "shadow")
    ctx["monkeypatch"].setattr(cr, "ROUTE_BIN_AT_START", "/nonexistent/cairnwork-route")
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "broken-1"))
    assert result["isError"] is False and len(ctx["service"].submitted) == 1
    other = _arguments(ctx, "shape-1", verifier_commands=["git diff --check"])
    assert _tool(ctx, "nexus_worker_candidate", other)["isError"] is False
    assert [line["task_id"] for line in _shadow_lines(ctx, 1)] == ["broken-1"]
    time.sleep(0.3)
    assert len(_shadow_lines(ctx, 1)) == 1  # the other shape was never offered


def test_route_submits_to_cairnwork_and_never_to_self_hosted(ctx):
    _mode(ctx, "route")
    _answer(ctx, submit=SUBMITTED, status=STATUS)
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-1", worker="cairnwork"))
    out = result["structuredContent"]
    assert out["owner"] == "cairnwork" and out["cairnwork_task_id"] == "task-cw1"
    assert ctx["service"].submitted == []
    assert (ctx["state"] / "cairnwork_jobs" / "cw-1.json").is_file()
    status = _tool(ctx, "nexus_task_status", {"task_id": "cw-1"})["structuredContent"]
    assert status["status"] == "DISPATCHED" and status["terminal"] is False
    assert _calls(ctx)[-1]["args"] == ["status", "--key", "cw-1"]


def test_route_without_the_explicit_worker_stays_on_self_hosted(ctx):
    _mode(ctx, "route")
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "plain-1"))
    assert result["isError"] is False and len(ctx["service"].submitted) == 1
    assert _calls(ctx) == []


def test_not_accepting_removes_the_record_and_nothing_is_rerouted(ctx):
    _mode(ctx, "route")
    _answer(ctx, submit=[2, {"error": "NOT_ACCEPTING", "detail": "drained"}])
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-2", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_NOT_ACCEPTING"
    assert not (ctx["state"] / "cairnwork_jobs" / "cw-2.json").exists()
    assert ctx["service"].submitted == []


def test_an_unknown_answer_keeps_ownership_with_cairnwork(ctx):
    _mode(ctx, "route")
    _answer(
        ctx,
        submit=[1, {"error": "INTERNAL", "detail": "boom"}],
        status=[1, {"error": "INTERNAL", "detail": "boom"}],
    )
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-3", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_INTERNAL"
    assert ctx["service"].submitted == []
    status = _tool(ctx, "nexus_task_status", {"task_id": "cw-3"})["structuredContent"]
    assert status["status"] == "UNKNOWN_REQUIRES_RECONCILE"
    again = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-3"))  # not via SelfHosted
    assert again["structuredContent"]["error"] == "CAIRNWORK_OWNS_TASK_ID"
    assert ctx["service"].submitted == []


def test_forwarded_tasks_stay_visible_after_rollback_to_off(ctx):
    _mode(ctx, "route")
    _answer(
        ctx,
        submit=SUBMITTED,
        status=STATUS,
        cancel=[2, {"error": "NOT_CANCELLABLE", "detail": "x"}],
    )
    _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-4", worker="cairnwork"))
    _mode(ctx, "off")
    status = _tool(ctx, "nexus_task_status", {"task_id": "cw-4"})["structuredContent"]
    assert status["owner"] == "cairnwork" and status["status"] == "DISPATCHED"
    cancel = _tool(ctx, "nexus_task_cancel", {"task_id": "cw-4"})["structuredContent"]
    assert cancel["cancelled"] is False and cancel["error"] == "NOT_CANCELLABLE"
    assert _calls(ctx)[-1]["args"] == ["cancel", "--task-id=task-cw1"]
    other = _tool(ctx, "nexus_task_cancel", {"task_id": "not-forwarded"})["structuredContent"]
    assert other == {"task_id": "not-forwarded", "service": "self_hosted"}


def test_wait_returns_when_cairnwork_finishes(ctx):
    _mode(ctx, "route")
    _answer(
        ctx,
        submit=SUBMITTED,
        status=[
            0,
            {
                "task_id": "task-cw1",
                "status": "COMPLETED",
                "core_verified": True,
                "candidate_commit": "c" * 40,
            },
        ],
    )
    _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-5", worker="cairnwork"))
    waited = _tool(ctx, "nexus_task_wait", {"task_id": "cw-5", "timeout_seconds": 5})
    out = waited["structuredContent"]
    assert out["terminal"] is True and out["core_verified"] is True


def test_route_refuses_a_task_shape_that_is_not_a_small_fix(ctx):
    _mode(ctx, "route")
    args = _arguments(ctx, "cw-6", worker="cairnwork", verifier_commands=["git diff --check"])
    result = _tool(ctx, "nexus_worker_candidate", args)
    assert result["structuredContent"]["error"] == "CAIRNWORK_TASK_SHAPE_UNSUPPORTED"
    assert _calls(ctx) == [] and ctx["service"].submitted == []


def test_a_task_id_self_hosted_already_owns_is_not_forwarded(ctx):
    _mode(ctx, "off")
    _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "mine-1"))
    _mode(ctx, "route")
    _answer(ctx, submit=SUBMITTED)
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "mine-1", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_TASK_ID_OWNED_BY_NEXUS"
    assert _calls(ctx) == []


def test_small_fix_shape():
    pytest_cmd = ["python3 -m pytest -q tests/test_x.py"]
    assert cr.small_fix_shape({}, pytest_cmd)
    assert not cr.small_fix_shape({"authority_change_candidate_confirmation": True}, pytest_cmd)
    assert not cr.small_fix_shape({"fail_to_pass_required": True}, pytest_cmd)
    assert not cr.small_fix_shape({"provider": "agy"}, pytest_cmd)
    assert not cr.small_fix_shape({}, ["python3 -m pytest -q"])
    assert not cr.small_fix_shape({}, ["python -m pytest tests/test_x.py"])
    assert not cr.small_fix_shape({}, ["python3 -m pytest 'tests/x.py"])


def test_mode_is_read_once_at_start():
    source = Path(cr.__file__).read_text(encoding="utf-8")
    assert source.count("os.environ") == 3  # the three *_AT_START constants only
    assert os.environ.get("NEXUS_CAIRNWORK_ROUTE") is None or cr.ROUTE_MODE_AT_START


def test_a_slow_cairnwork_does_not_delay_the_shadow_response(ctx):
    _mode(ctx, "shadow")
    slow = ctx["answers"].parent / "slow-route"
    slow.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(5)\nprint('{{}}')\n")
    slow.chmod(0o755)
    ctx["monkeypatch"].setattr(cr, "ROUTE_BIN_AT_START", str(slow))
    started = time.monotonic()
    assert _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "slow-1"))["isError"] is False
    assert time.monotonic() - started < 3


@pytest.mark.parametrize("mode", ["shadow", "route"])
def test_a_malformed_task_card_never_reaches_cairnwork(ctx, mode):
    _mode(ctx, mode)
    _answer(ctx, submit=SUBMITTED, check=[0, {"would_accept": True}])
    args = _arguments(ctx, f"bad-card-{mode}", worker="cairnwork")
    card = ctx["card_root"] / args["task_card_path"]
    card.write_text(card.read_text() + "```nexus-expected-evidence\n{\n", encoding="utf-8")
    args["task_card_hash"] = hashlib.sha256(card.read_bytes()).hexdigest()
    result = _tool(ctx, "nexus_worker_candidate", args)
    assert result["structuredContent"]["error"].startswith("TASK_CARD_BINDING_INVALID")
    time.sleep(0.3)
    assert _calls(ctx) == [] and not (ctx["state"] / "cairnwork_jobs").exists()


def test_a_card_that_names_expected_evidence_is_not_a_small_fix(ctx):
    import nexus.orchestrator.unified_mcp_gateway_parts.worker_candidate as wc

    ctx["monkeypatch"].setattr(wc, "parse_task_card_expected_evidence", lambda text: {"x": 1})
    _mode(ctx, "route")
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "ev-1", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_TASK_SHAPE_UNSUPPORTED"
    assert _calls(ctx) == []


def test_not_accepting_keeps_a_record_another_call_made(ctx):
    _mode(ctx, "route")
    jobs = ctx["state"] / "cairnwork_jobs"
    jobs.mkdir()
    (jobs / "cw-7.json").write_text("{}", encoding="utf-8")  # a concurrent submit's record
    _answer(ctx, submit=[2, {"error": "NOT_ACCEPTING", "detail": "drained"}])
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-7", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_NOT_ACCEPTING"
    assert (jobs / "cw-7.json").exists()


def test_concurrent_submits_create_one_record(ctx):
    paths = [ctx["state"] / "cairnwork_jobs" / "race.json"] * 8
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda p=p: results.append(cr._create_record(p, "race", "h")))
        for p in paths
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False] * 7 + [True]


def test_without_a_state_dir_route_refuses_and_nothing_is_owned(ctx):
    _mode(ctx, "route")
    ctx["service"].state_dir = None
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "nostate-1", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_NO_STATE_DIR"
    assert ctx["gateway"]._cairnwork_owns("nostate-1") is False


def test_wait_returns_at_once_when_the_status_cannot_be_read(ctx):
    _mode(ctx, "route")
    _answer(ctx, submit=SUBMITTED, status=[1, {"error": "INTERNAL", "detail": "x"}])
    _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-8", worker="cairnwork"))
    started = time.monotonic()
    out = _tool(ctx, "nexus_task_wait", {"task_id": "cw-8", "timeout_seconds": 30})[
        "structuredContent"
    ]
    assert out["status"] == "UNKNOWN_REQUIRES_RECONCILE" and time.monotonic() - started < 5


@pytest.mark.parametrize(
    "arguments, verifiers",
    [
        ({}, ["python3 -m pytest -c evil.ini tests/test_x.py"]),
        ({}, ["python3 -m pytest -p evil tests/test_x.py"]),
        ({}, ["python3 -m pytest tests/../x.py"]),
        ({}, []),
        ({"zz_new_field": 1}, ["python3 -m pytest tests/test_x.py"]),
        ({"authority_change_candidate_confirmation": False}, ["python3 -m pytest -q"]),
    ],
)
def test_small_fix_shape_is_an_allowlist(arguments, verifiers):
    assert not cr.small_fix_shape(arguments, verifiers)
    assert cr.small_fix_shape(
        {"fail_to_pass_required": False}, ["python3 -m pytest -x tests/a/test_x.py::t"]
    )


def test_the_mode_is_fixed_when_the_gateway_process_starts():
    code = (
        "import os\n"
        "from nexus.orchestrator.unified_mcp_gateway_parts import cairnwork_route as cr\n"
        "os.environ['NEXUS_CAIRNWORK_ROUTE'] = 'route'\n"
        "print(cr.route_mode())\n"
    )
    env = {**os.environ, "NEXUS_CAIRNWORK_ROUTE": "shadow"}
    done = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "shadow"


def test_other_refusals_keep_the_record_and_never_fall_back(ctx):
    _mode(ctx, "route")
    _answer(ctx, submit=[2, {"error": "DuplicateLogicalTask", "detail": "card active"}])
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-9", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_DuplicateLogicalTask"
    assert (ctx["state"] / "cairnwork_jobs" / "cw-9.json").exists()
    assert ctx["service"].submitted == []


def test_unconfigured_route_refuses_before_creating_any_record(ctx):
    _mode(ctx, "route")
    ctx["monkeypatch"].setattr(cr, "ROUTE_BIN_AT_START", "")
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-10", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_UNCONFIGURED"
    assert not (ctx["state"] / "cairnwork_jobs" / "cw-10.json").exists()


def test_self_hosted_rechecks_ownership_right_before_submit(ctx):
    _mode(ctx, "off")
    gateway = ctx["gateway"]
    real = gateway._cairnwork_owns
    calls = {"n": 0}

    def owned_late(task_id):  # a concurrent route call binds while planning runs
        calls["n"] += 1
        return calls["n"] > 1 or real(task_id)

    ctx["monkeypatch"].setattr(gateway, "_cairnwork_owns", owned_late)
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "late-1"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_OWNS_TASK_ID"
    assert ctx["service"].submitted == []


def test_record_is_taken_back_if_self_hosted_took_the_id_meanwhile(ctx):
    _mode(ctx, "route")
    _answer(ctx, submit=SUBMITTED)
    service = ctx["service"]
    real = service.get_task_snapshot
    seen = {"n": 0}

    def snapshot(task_id):
        seen["n"] += 1
        return {"task_id": task_id} if seen["n"] > 1 else real(task_id)

    ctx["monkeypatch"].setattr(service, "get_task_snapshot", snapshot)
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "cw-11", worker="cairnwork"))
    assert result["structuredContent"]["error"] == "CAIRNWORK_TASK_ID_OWNED_BY_NEXUS"
    assert not (ctx["state"] / "cairnwork_jobs" / "cw-11.json").exists() and _calls(ctx) == []
