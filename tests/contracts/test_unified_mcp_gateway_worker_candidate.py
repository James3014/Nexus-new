"""Characterization tests for the gateway's worker-resolution and calibration helpers (Issue #2490).

Big-file split G7b: these tests pin ``_resolve_assisted_worker``,
``_model_calibration_evidence`` and ``_model_calibration_plan`` before the methods move
out of ``UnifiedMCPGateway`` into a mixin. The calibration methods are driven through
their public tools (``nexus_model_calibration_evidence`` / ``nexus_model_calibration_plan``).
``_resolve_assisted_worker`` has no in-tree caller, so it is called on the instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import nexus.services.model_workforce_policy as workforce_policy
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway
from nexus.services.model_capability_lineage import CHANGE_KIND_VALUES, LineageResolutionError


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


@pytest.fixture
def gateway(tmp_path: Path) -> UnifiedMCPGateway:
    return UnifiedMCPGateway(service=_Service(tmp_path / "state"))


def _call(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _ok(gateway, name, arguments):
    result = _call(gateway, name, arguments)
    assert not result.get("isError"), result
    return result["structuredContent"]


def _error(gateway, name, arguments) -> str:
    result = _call(gateway, name, arguments)
    assert result.get("isError") is True, result
    return str(result["structuredContent"]["error"])


# --- _resolve_assisted_worker -------------------------------------------------------


@dataclass
class _Worker:
    worker_id: str
    provider: str
    model: str
    state: str = "ADMITTED"


@dataclass
class _Snapshot:
    workers: dict[str, _Worker] = field(default_factory=dict)


class _Loader:
    def __init__(self, *workers: _Worker) -> None:
        self.snapshot = _Snapshot({worker.worker_id: worker for worker in workers})
        self.loads = 0

    def load(self) -> _Snapshot:
        self.loads += 1
        return self.snapshot


@pytest.mark.parametrize(("env", "provider"), [(None, "agy"), ("Codex ", "codex"), ("  ", "agy")])
def test_auto_worker_uses_the_assist_provider_env(gateway, monkeypatch, env, provider) -> None:
    if env is None:
        monkeypatch.delenv("NEXUS_ASSIST_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("NEXUS_ASSIST_PROVIDER", env)
    gateway._workforce_loader = _Loader()
    for requested in ("auto", "", None, " AUTO "):
        assert gateway._resolve_assisted_worker(requested, " m1 ") == (provider, "m1", None)
    assert gateway._workforce_loader.loads == 0  # auto never consults the workforce policy


def test_named_worker_resolves_provider_model_and_worker_id(gateway) -> None:
    gateway._workforce_loader = _Loader(_Worker("w-gemini", "agy", "gemini-3.8"))
    assert gateway._resolve_assisted_worker("W-Gemini", "") == ("agy", "gemini-3.8", "w-gemini")
    assert gateway._resolve_assisted_worker("w-gemini", "gemini-3.8") == (
        "agy",
        "gemini-3.8",
        "w-gemini",
    )


def test_worker_matched_by_unique_model(gateway) -> None:
    gateway._workforce_loader = _Loader(_Worker("w1", "cline", "glm-5.2"))
    assert gateway._resolve_assisted_worker("glm-5.2", "") == ("cline", "glm-5.2", "w1")


def test_named_worker_rejects_model_identity_mismatch(gateway) -> None:
    gateway._workforce_loader = _Loader(_Worker("w1", "cline", "glm-5.2"))
    with pytest.raises(GatewayInputError, match="^ASSIST_MODEL_IDENTITY_MISMATCH$"):
        gateway._resolve_assisted_worker("w1", "other-model")


@pytest.mark.parametrize("state", sorted(getattr(workforce_policy, "NON_ADMISSIBLE_STATES")))
def test_non_admissible_worker_is_refused(gateway, state) -> None:
    gateway._workforce_loader = _Loader(_Worker("w1", "cline", "glm-5.2", state=state))
    with pytest.raises(GatewayInputError, match="^ASSIST_MODEL_NOT_ADMISSIBLE:w1$"):
        gateway._resolve_assisted_worker("w1", "")


@pytest.mark.parametrize("key", ["cline", "codex", "mimo", "ollama"])
def test_registered_provider_without_policy_worker_passes_through(gateway, key) -> None:
    gateway._workforce_loader = _Loader(_Worker("a", "x", "dup"), _Worker("b", "y", "dup"))
    assert gateway._resolve_assisted_worker(key.upper(), " m ") == (key, "m", None)


@pytest.mark.parametrize("key", ["dup", "unknown-provider"])
def test_unregistered_or_ambiguous_key_is_refused(gateway, key) -> None:
    gateway._workforce_loader = _Loader(_Worker("a", "x", "dup"), _Worker("b", "y", "dup"))
    with pytest.raises(GatewayInputError, match="^ASSIST_PROVIDER_NOT_REGISTERED$"):
        gateway._resolve_assisted_worker(key, "")


# --- _model_calibration_evidence via nexus_model_calibration_evidence --------------


class _Planner:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def evidence_bundle(self, **kwargs: Any) -> dict:
        self.calls.append(("evidence_bundle", kwargs))
        if self.fail:
            raise LineageResolutionError(self.fail)
        return {"bundle": kwargs}

    def build_calibration_plan(self, **kwargs: Any):
        self.calls.append(("build_calibration_plan", kwargs))
        if self.fail:
            raise LineageResolutionError(self.fail)

        class _Plan:
            def to_dict(self) -> dict:
                return {"plan": kwargs}

        return _Plan()


@pytest.mark.parametrize(
    ("arguments", "kwargs"),
    [
        ({"lineage_id": " lin-1 "}, {"lineage_id": "lin-1"}),
        ({"provider": " agy ", "model": " gemini "}, {"provider": "agy", "model": "gemini"}),
    ],
)
def test_calibration_evidence_resolves_by_lineage_or_exact_identity(
    gateway, arguments, kwargs
) -> None:
    gateway._calibration_planner = _Planner()
    assert _ok(gateway, "nexus_model_calibration_evidence", arguments) == {"bundle": kwargs}
    assert gateway._calibration_planner.calls == [("evidence_bundle", kwargs)]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {"lineage_id": "l", "provider": "p"},
            "nexus_model_calibration_evidence accepts lineage_id OR exact provider+model, not both",
        ),
        (
            {"provider": "p"},
            "nexus_model_calibration_evidence requires provider and model together",
        ),
        ({"model": "m"}, "nexus_model_calibration_evidence requires provider and model together"),
        ({}, "nexus_model_calibration_evidence requires lineage_id OR exact provider+model"),
    ],
)
def test_calibration_evidence_input_validation(gateway, arguments, message) -> None:
    gateway._calibration_planner = _Planner()
    assert _error(gateway, "nexus_model_calibration_evidence", arguments) == message
    assert gateway._calibration_planner.calls == []


@pytest.mark.parametrize("arguments", [{"lineage_id": "l"}, {"provider": "p", "model": "m"}])
def test_calibration_evidence_maps_lineage_errors(gateway, arguments) -> None:
    gateway._calibration_planner = _Planner(fail="LINEAGE_UNKNOWN")
    assert _error(gateway, "nexus_model_calibration_evidence", arguments) == "LINEAGE_UNKNOWN"


# --- _model_calibration_plan via nexus_model_calibration_plan ------------------------


def test_calibration_plan_builds_bounded_plan(gateway) -> None:
    gateway._calibration_planner = _Planner()
    result = _ok(
        gateway,
        "nexus_model_calibration_plan",
        {
            "provider": " agy ",
            "model": " gemini ",
            "target_role": "reviewer",
            "change_kind": " Transport_Only ",
            "description": "x" * 600,
        },
    )
    expected = {
        "provider": "agy",
        "model": "gemini",
        "target_role": "reviewer",
        "change_kind": "transport_only",
        "description": "x" * 512,
    }
    assert result == {"plan": expected}
    assert gateway._calibration_planner.calls == [("build_calibration_plan", expected)]


def test_calibration_plan_defaults_change_kind_and_description(gateway) -> None:
    gateway._calibration_planner = _Planner()
    result = _ok(
        gateway, "nexus_model_calibration_plan", {"provider": "p", "model": "m", "target_role": "r"}
    )
    assert result == {
        "plan": {
            "provider": "p",
            "model": "m",
            "target_role": "r",
            "change_kind": None,
            "description": "",
        }
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"provider": "p", "model": "m"}, "target_role is required"),
        (
            {"model": "m", "target_role": "r"},
            "nexus_model_calibration_plan requires provider and model",
        ),
        (
            {"provider": "p", "target_role": "r"},
            "nexus_model_calibration_plan requires provider and model",
        ),
        (
            {"provider": "p", "model": "m", "target_role": "r", "change_kind": "bogus"},
            f"change_kind must be one of {', '.join(CHANGE_KIND_VALUES)}",
        ),
    ],
)
def test_calibration_plan_input_validation(gateway, arguments, message) -> None:
    gateway._calibration_planner = _Planner()
    assert _error(gateway, "nexus_model_calibration_plan", arguments) == message
    assert gateway._calibration_planner.calls == []


def test_calibration_plan_maps_lineage_errors(gateway) -> None:
    gateway._calibration_planner = _Planner(fail="LINEAGE_AMBIGUOUS")
    assert (
        _error(
            gateway,
            "nexus_model_calibration_plan",
            {"provider": "p", "model": "m", "target_role": "r"},
        )
        == "LINEAGE_AMBIGUOUS"
    )
