"""Online A/B 20261013b finding 3: the online registered-CLI route ignored the gateway timeout.

``ask_unified`` built the registered CLI invoker with ``route.get("timeout_sec", 120.0)``, so
the with_nexus agy call was cut at 120 s while the bench (and ``ask_structured``) configured
``NEXUS_GATEWAY_TIMEOUT_SEC=300``. 120 s must only be the last-resort default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nexus_runtime.kernel.request import UnifiedRuntimeRequest

from nexus.services.gateway import BattlesuitGateway


def _timeouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route_extra: dict[str, Any]
) -> dict[str, float]:
    seen: dict[str, float] = {}
    captured: dict[str, Any] = {}

    def _fake_build(provider, *, command=None, model_name=None, timeout_sec=120.0, **_kw):
        seen[str(provider)] = float(timeout_sec)
        return lambda _context: {"invoked": False, "provider_call_count": 0}

    def _capture(_request, *, online_invoker, **_kw):
        captured["invoker"] = online_invoker
        return {}

    monkeypatch.setattr(
        "nexus.services.unified_runtime.build_registered_online_invoker", _fake_build
    )
    monkeypatch.setattr("nexus.services.mainchain_entry.run_mainchain", _capture)
    base = dict(
        task_id="timeout-1",
        workspace_revision="rev-1",
        task_statement="timeout",
        task_type="repair",
        online_enabled=True,
    )
    gw = BattlesuitGateway(project_root=tmp_path)
    # Explicit registered edge: the invoker is built at ask time.
    gw.ask_unified(
        UnifiedRuntimeRequest(
            **base,
            route={
                "recommended_flow": "direct",
                "provider": "codex",
                "online_command": "/bin/true",
                **route_extra,
            },
        )
    )
    registered = seen.pop("codex")
    # Workforce-deferred edge: the admitted provider's invoker is built at call time.
    gw.ask_unified(
        UnifiedRuntimeRequest(
            **base,
            route={
                "recommended_flow": "direct",
                "online_command": "/bin/true",
                "workforce_bindings": {"online": {"worker_id": "agy_flash_38"}},
                **route_extra,
            },
        )
    )
    captured["invoker"]({
        "task_id": "timeout-1",
        "online_prompt": "hi",
        "gateway_invocation_authority": {
            "gate_passed": True,
            "resolved_provider": "agy",
            "resolved_model": "gemini-3.8-flash-medium",
        },
    })
    return {"registered_edge": registered, "workforce_edge": seen["agy"]}


def test_online_route_honors_configured_gateway_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "300")
    assert _timeouts(tmp_path, monkeypatch, {}) == {
        "registered_edge": 300.0,
        "workforce_edge": 300.0,
    }


def test_online_route_timeout_defaults_to_120_only_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_GATEWAY_TIMEOUT_SEC", raising=False)
    assert _timeouts(tmp_path, monkeypatch, {}) == {
        "registered_edge": 120.0,
        "workforce_edge": 120.0,
    }


def test_explicit_route_timeout_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_GATEWAY_TIMEOUT_SEC", "300")
    assert _timeouts(tmp_path, monkeypatch, {"timeout_sec": 42}) == {
        "registered_edge": 42.0,
        "workforce_edge": 42.0,
    }
