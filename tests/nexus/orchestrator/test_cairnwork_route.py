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
    assert [c["args"] for c in _calls(ctx)] == [["check"]]
    sent = json.loads(_calls(ctx)[0]["stdin"])
    assert sent["idempotency_key"] == "same-1" and sent["base_commit"] == "a" * 40
    assert sent["verifiers"] == [
        ["pytest-0", ["python3", "-m", "pytest", "-q", "tests/test_calc.py"]]
    ]
    log = (ctx["state"] / "cairnwork_shadow.jsonl").read_text().splitlines()
    assert json.loads(log[0])["answer"] == {"would_accept": False}


def test_shadow_survives_a_broken_cairnwork_and_skips_other_shapes(ctx):
    _mode(ctx, "shadow")
    ctx["monkeypatch"].setattr(cr, "ROUTE_BIN_AT_START", "/nonexistent/cairnwork-route")
    result = _tool(ctx, "nexus_worker_candidate", _arguments(ctx, "broken-1"))
    assert result["isError"] is False and len(ctx["service"].submitted) == 1
    other = _arguments(ctx, "shape-1", verifier_commands=["git diff --check"])
    assert _tool(ctx, "nexus_worker_candidate", other)["isError"] is False
    log = (ctx["state"] / "cairnwork_shadow.jsonl").read_text().splitlines()
    assert [json.loads(line)["task_id"] for line in log] == ["broken-1"]


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
    assert _calls(ctx)[-1]["args"] == ["cancel", "--task-id", "task-cw1"]
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
