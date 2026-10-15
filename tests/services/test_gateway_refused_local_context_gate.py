"""Gateway compatibility Online invoker must not forward refused Local output (#2245).

When Workforce admission refuses the Local assist stage, nexus-runtime marks it
FAILED / gate_passed False but keeps the model response.  The Gateway
``gateway_online_invoker`` must forward ``local_outputs`` into the online prompt
only when the stage passed its gate with a success status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nexus_runtime.kernel.request import UnifiedRuntimeRequest

from nexus.services.gateway import BattlesuitGateway

LOCAL_ADVICE = "refused-local-advice-sentinel"


def _gateway_invoker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[str]]:
    """Return the Gateway compatibility Online invoker plus the captured prompts."""
    prompts: list[str] = []

    def _fake_ask(prompt: str, payload: str = "", **_kw: Any) -> tuple[dict[str, Any], str]:
        prompts.append(prompt)
        return {"answer": "online-ok"}, "online-ok"

    captured: dict[str, Any] = {}

    def _capture(request: Any, *, online_invoker: Any, **_kw: Any) -> dict[str, Any]:
        captured["invoker"] = online_invoker
        return {}

    monkeypatch.delenv("NEXUS_OAUTH_PROVIDER", raising=False)
    monkeypatch.setattr("nexus.services.mainchain_entry.run_mainchain", _capture)
    gw = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(gw, "ask_structured", _fake_ask)
    gw.ask_unified(
        UnifiedRuntimeRequest(
            task_id="t2245",
            workspace_revision="rev-1",
            task_statement="repair",
            task_type="repair",
            online_enabled=True,
            route={"recommended_flow": "direct"},
        )
    )
    return captured["invoker"], prompts


def _context(local_stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "t2245",
        "online_prompt": "fix the bug",
        "local": local_stage,
    }


def _local_stage(*, status: str, gate_passed: bool) -> dict[str, Any]:
    return {
        "status": status,
        "gate_passed": gate_passed,
        "invoked": True,
        "reason": "" if gate_passed else "local_action_not_executor_bound",
        "response": {"local_outputs": {"concise_summary": LOCAL_ADVICE}},
    }


def test_refused_local_stage_output_is_not_forwarded_to_online_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoker, prompts = _gateway_invoker(tmp_path, monkeypatch)
    result = invoker(_context(_local_stage(status="FAILED", gate_passed=False)))
    assert len(prompts) == 1
    assert "[LOCAL_ASSIST_CONTEXT]" not in prompts[0]
    assert LOCAL_ADVICE not in prompts[0]
    refs = [str(r) for r in result.get("evidence_refs", [])]
    assert not any("local_context_forwarded" in r for r in refs)
    assert "gateway:t2245:local_context_withheld:FAILED" in refs


def test_succeeded_gate_passed_local_stage_output_is_still_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoker, prompts = _gateway_invoker(tmp_path, monkeypatch)
    result = invoker(_context(_local_stage(status="SUCCEEDED", gate_passed=True)))
    assert len(prompts) == 1
    assert "[LOCAL_ASSIST_CONTEXT]" in prompts[0]
    assert LOCAL_ADVICE in prompts[0]
    refs = [str(r) for r in result.get("evidence_refs", [])]
    assert "gateway:t2245:local_context_forwarded" in refs
    assert not any("local_context_withheld" in r for r in refs)


def test_gate_passed_local_stage_with_failed_status_is_not_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoker, prompts = _gateway_invoker(tmp_path, monkeypatch)
    result = invoker(_context(_local_stage(status="FAILED", gate_passed=True)))
    assert len(prompts) == 1
    assert "[LOCAL_ASSIST_CONTEXT]" not in prompts[0]
    assert LOCAL_ADVICE not in prompts[0]
    refs = [str(r) for r in result.get("evidence_refs", [])]
    assert not any("local_context_forwarded" in r for r in refs)
    assert "gateway:t2245:local_context_withheld:FAILED" in refs
