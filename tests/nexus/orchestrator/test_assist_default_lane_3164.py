"""#3164: the implicit assist / model-probe default lane is refused before launch.

The default lane (cline, glm-5.2) failed every launch once its authorisation expired.
A submit that names neither provider nor model is refused with its own blocker before
the version preflight, the job record, the workspace and the provider process, unless
``NEXUS_ASSIST_DEFAULT_LANE_ENABLED`` is exactly ``"1"``.  A caller that names a
provider or a model keeps the behaviour it had before.

Every process start and signal is replaced by a stub that fails the test, so no
provider binary is ever run.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
from nexus.orchestrator.unified_mcp_gateway_parts import assist_jobs

SWITCH = "NEXUS_ASSIST_DEFAULT_LANE_ENABLED"
ASSIST_BLOCKER = "ASSIST_DEFAULT_LANE_UNAVAILABLE: "
PROBE_BLOCKER = "MODEL_PROBE_DEFAULT_LANE_UNAVAILABLE: "


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


class _VersionReached(OSError):
    """Raised by the stubbed version preflight: the request got past the lane check."""


@pytest.fixture
def box(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv(SWITCH, raising=False)
    launches: list[Any] = []

    def no_popen(*args: Any, **kwargs: Any):
        launches.append(("Popen", args))
        raise AssertionError("provider process started")

    def version_run(*args: Any, **kwargs: Any):
        launches.append(("run", args))
        raise _VersionReached("version preflight reached")

    def no_signal(*args: Any, **kwargs: Any):
        raise AssertionError("signal sent")

    monkeypatch.setattr(subprocess, "Popen", no_popen)
    monkeypatch.setattr(subprocess, "run", version_run)
    monkeypatch.setattr(os, "kill", no_signal)
    monkeypatch.setattr(os, "killpg", no_signal)
    monkeypatch.setattr(signal, "signal", no_signal)
    cline = tmp_path / "bin" / "cline"
    cline.parent.mkdir()
    cline.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cline.chmod(0o755)
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(cline))
    monkeypatch.setattr(
        gateway_module, "resolve_registered_provider_executable", lambda provider, **_: str(cline)
    )
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    state = tmp_path / "state"
    gateway = UnifiedMCPGateway(service=_Service(state))
    return gateway, state, launches


def _call(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _error(gateway: UnifiedMCPGateway, name: str, arguments: dict[str, Any]) -> str:
    result = _call(gateway, name, arguments)
    assert result.get("isError") is True, result
    return str(result["structuredContent"].get("error"))


def _assist(task_id: str, **extra: Any) -> dict[str, Any]:
    return {"task_id": task_id, "what": "x", "why": "y", "allowed_files": ["README.md"], **extra}


def _probe(task_id: str, **extra: Any) -> dict[str, Any]:
    return {"task_id": task_id, "prompt": "probe", "output_schema": {"type": "object"}, **extra}


def _no_job_written(state: Path) -> bool:
    jobs = state / "assisted_provider_jobs"
    return not jobs.exists() or not any(jobs.iterdir())


def test_implicit_assist_submit_is_refused_before_any_effect(box) -> None:
    gateway, state, launches = box
    message = _error(gateway, "nexus_assist_submit", _assist("lane-assist-1"))
    assert message.startswith(ASSIST_BLOCKER)
    assert "authorisation has expired" in message and f"{SWITCH}=1" in message
    assert launches == []
    assert gateway._assist_read("lane-assist-1") is None
    assert _no_job_written(state)


def test_implicit_model_probe_is_refused_before_the_version_preflight(box) -> None:
    gateway, state, launches = box
    message = _error(gateway, "nexus_model_probe", _probe("lane-probe-1"))
    assert message.startswith(PROBE_BLOCKER)
    assert "authorisation has expired" in message and f"{SWITCH}=1" in message
    assert launches == []
    assert gateway._assist_read("lane-probe-1") is None
    assert _no_job_written(state)


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 1", "1 "])
def test_only_the_exact_switch_value_enables_the_default_lane(box, monkeypatch, value) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv(SWITCH, value)
    assert _error(gateway, "nexus_model_probe", _probe("lane-probe-2")).startswith(PROBE_BLOCKER)
    assert _error(gateway, "nexus_assist_submit", _assist("lane-assist-2")).startswith(
        ASSIST_BLOCKER
    )
    assert launches == []


def test_switch_on_keeps_the_previous_implicit_probe_behaviour(box, monkeypatch) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv(SWITCH, "1")
    assert (
        _error(gateway, "nexus_model_probe", _probe("lane-probe-3"))
        == "ASSIST_PROVIDER_VERSION_FAILED"
    )
    assert [kind for kind, _ in launches] == ["run"]


def test_switch_on_keeps_the_previous_implicit_assist_behaviour(box, monkeypatch, tmp_path) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv(SWITCH, "1")
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(tmp_path / "missing-cline"))
    assert (
        _error(gateway, "nexus_assist_submit", _assist("lane-assist-3"))
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )
    assert launches == []


@pytest.mark.parametrize(
    "named",
    [{"provider": "cline"}, {"model": "glm-5.2"}, {"provider": "cline", "model": "glm-5.2"}],
)
def test_a_probe_that_names_provider_or_model_keeps_its_behaviour(box, named) -> None:
    gateway, _state, launches = box
    assert (
        _error(gateway, "nexus_model_probe", _probe("lane-probe-4", **named))
        == "ASSIST_PROVIDER_VERSION_FAILED"
    )
    assert [kind for kind, _ in launches] == ["run"]


@pytest.mark.parametrize(
    "named",
    [
        {"provider": "cline"},
        {"preferred_worker": "cline"},
        {"model": "glm-5.2"},
        {"preferred_model": "glm-5.2"},
        {"provider": "", "preferred_worker": "cline"},
    ],
)
def test_an_assist_that_names_provider_or_model_keeps_its_behaviour(
    box, monkeypatch, tmp_path, named
) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(tmp_path / "missing-cline"))
    assert (
        _error(gateway, "nexus_assist_submit", _assist("lane-assist-4", **named))
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )
    assert launches == []


def test_an_assist_naming_another_provider_keeps_its_unsupported_blocker(box) -> None:
    gateway, _state, launches = box
    assert (
        _error(gateway, "nexus_assist_submit", _assist("lane-assist-5", provider="agy"))
        == "ASSIST_ASYNC_PROVIDER_UNSUPPORTED"
    )
    assert launches == []


def test_empty_names_fall_through_to_the_default_lane(box) -> None:
    gateway, _state, launches = box
    blank = {"provider": "", "model": None}
    assert _error(gateway, "nexus_model_probe", _probe("lane-probe-6", **blank)).startswith(
        PROBE_BLOCKER
    )
    assert _error(gateway, "nexus_assist_submit", _assist("lane-assist-6", **blank)).startswith(
        ASSIST_BLOCKER
    )
    assert launches == []


def test_hint_names_the_switch_and_no_host_detail() -> None:
    hint = assist_jobs.ASSIST_DEFAULT_LANE_UNAVAILABLE_HINT
    assert assist_jobs.ASSIST_DEFAULT_LANE_ENABLED_ENV == SWITCH
    assert f"{SWITCH}=1" in hint
    assert "/" not in hint.replace("cline, glm-5.2", "")
