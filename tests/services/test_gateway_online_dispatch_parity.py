"""Gateway Online dispatch parity (nexus-runtime #190 pair, Nexus-new #2056).

Every Gateway path that can reach a physical registered-CLI invoker must take its
authority from the single runtime-resolved ``OnlineExecutionDecision``
(``context["online_execution_decision_resolved"]``).  With the decision absent, with
``physical_invocation_allowed=False`` (incl. the injected_test_transport fixture
decision) or with a forged mapping, no path may start the provider process.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from nexus_runtime.kernel.request import UnifiedRuntimeRequest
from nexus_runtime.support.services.online_execution_policy import (
    RESOLVED_DECISION_CONTEXT_KEY,
    resolve_online_execution_decision,
)

from nexus.services.gateway import BattlesuitGateway

MODEL = "gpt-5.6-luna"


def _fake_cli(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "starts.log"
    script = tmp_path / "fake-codex"
    script.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\necho edge-output\n')
    script.chmod(0o755)
    return script, log


def _decisions() -> dict[str, Any]:
    physical = resolve_online_execution_decision(
        task_online_policy="auto", requested_provider="codex", environ={}
    )
    assert physical.physical_invocation_allowed is True
    fixture = resolve_online_execution_decision(
        task_online_policy="auto", injected_transport=True, requested_provider="codex"
    )
    assert fixture.physical_invocation_allowed is False
    return {
        "absent": None,
        "physical_false": replace(physical, physical_invocation_allowed=False),
        "injected_fixture": fixture,
        "forged_mapping": {
            "online_execution_authorized": True,
            "physical_invocation_allowed": True,
            "online_authorization_source": "workspace_policy",
        },
        "physical_true": physical,
    }


def _route_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: Path):
    """Capture the Online invoker the Gateway hands to the mainchain, per dispatch path."""
    captured: dict[str, Any] = {}

    def _capture(request, *, online_invoker, **_kw):
        captured["invoker"] = online_invoker
        return {}

    monkeypatch.setattr("nexus.services.mainchain_entry.run_mainchain", _capture)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(script))
    base = dict(
        task_id="parity-1",
        workspace_revision="rev-1",
        task_statement="parity",
        task_type="repair",
        online_enabled=True,
    )
    paths: dict[str, Any] = {}
    # 1) Workforce-deferred edge (admitted provider resolved at call time).
    gw = BattlesuitGateway(project_root=tmp_path)
    gw.ask_unified(
        UnifiedRuntimeRequest(
            **base,
            route={
                "recommended_flow": "direct",
                "online_command": str(script),
                "workforce_bindings": {"online": {"worker_id": "codex_luna"}},
            },
        )
    )
    paths["workforce_edge"] = captured.pop("invoker")
    # 2) Explicit registered edge (route provider).
    gw.ask_unified(
        UnifiedRuntimeRequest(
            **base,
            route={
                "recommended_flow": "direct",
                "provider": "codex",
                "online_command": str(script),
            },
        )
    )
    paths["registered_edge"] = captured.pop("invoker")
    # 3) Gateway configured for codex (no route provider, no Workforce binding).
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "codex")
    gw_codex = BattlesuitGateway(project_root=tmp_path)
    gw_codex.ask_unified(
        UnifiedRuntimeRequest(
            **base, route={"recommended_flow": "direct", "online_command": str(script)}
        )
    )
    paths["codex_configured_edge"] = captured.pop("invoker")
    return paths


def _context(decision: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "task_id": "parity-1",
        "online_prompt": "hi",
        "online_model_name": MODEL,
        "gateway_invocation_authority": {
            "gate_passed": True,
            "resolved_provider": "codex",
            "resolved_model": MODEL,
        },
    }
    if isinstance(decision, dict):
        ctx["online_execution_decision"] = decision
    elif decision is not None:
        ctx[RESOLVED_DECISION_CONTEXT_KEY] = decision
    return ctx


# "injected_fixture" joins this list with the runtime pin that contains nexus-runtime #190
# (68e86ed); on 6782e38 the registered CLI still starts under a fixture decision.
FAIL_CLOSED_CASES = ["absent", "physical_false", "forged_mapping"]


@pytest.mark.parametrize("case", FAIL_CLOSED_CASES)
def test_every_gateway_dispatch_path_fails_closed_without_physical_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    script, log = _fake_cli(tmp_path)
    paths = _route_paths(tmp_path, monkeypatch, script)
    assert set(paths) == {"workforce_edge", "registered_edge", "codex_configured_edge"}
    decision = _decisions()[case]
    for name, invoker in paths.items():
        result = invoker(_context(decision))
        assert result.get("provider_call_count", 0) == 0, (name, result)
        assert result.get("invoked") is not True, (name, result)
    # 4) Print-mode registered CLI (ask_structured compatibility lane).
    gw = BattlesuitGateway(project_root=tmp_path)
    gw._online_execution_decision = decision
    out, _raw = gw._ask_via_registered_print_cli(
        content="hi",
        sys_msg="",
        provider="codex",
        model_name=MODEL,
        timeout_sec=10,
        gateway_telemetry={},
    )
    assert out["status"] == "FAILED" and out["provider_call_count"] == 0
    assert not log.exists(), f"{case}: a provider process was started"


def test_dispatch_paths_start_the_process_only_under_a_physical_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script, log = _fake_cli(tmp_path)
    paths = _route_paths(tmp_path, monkeypatch, script)
    result = paths["registered_edge"](_context(_decisions()["physical_true"]))
    assert result["invoked"] is True and result["provider_call_count"] == 1
    assert log.exists()
