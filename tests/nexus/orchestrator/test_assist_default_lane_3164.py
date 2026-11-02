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
    # #3171: naming exactly (cline, glm-5.2) is now the default lane, so the third case
    # names another cline model.
    [{"provider": "cline"}, {"model": "glm-5.2"}, {"provider": "cline", "model": "glm-5.3"}],
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


@pytest.mark.parametrize(
    "blank",
    [{"model": "  "}, {"model": "\t"}, {"provider": "", "model": " \n "}],
)
def test_a_blank_probe_model_is_the_default_lane(box, blank) -> None:
    gateway, state, launches = box
    assert _error(gateway, "nexus_model_probe", _probe("lane-probe-7", **blank)).startswith(
        PROBE_BLOCKER
    )
    assert launches == []
    assert _no_job_written(state)


@pytest.mark.parametrize(
    "blank",
    [
        {"model": "  "},
        {"preferred_model": "\t"},
        {"provider": "  "},
        {"preferred_worker": " ", "preferred_model": " "},
        {"provider": "", "model": " \n "},
    ],
)
def test_a_blank_assist_provider_and_model_is_the_default_lane(box, blank) -> None:
    gateway, state, launches = box
    assert _error(gateway, "nexus_assist_submit", _assist("lane-assist-7", **blank)).startswith(
        ASSIST_BLOCKER
    )
    assert launches == []
    assert _no_job_written(state)


def test_switch_off_still_replays_a_stored_assist_job(box, monkeypatch) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv(SWITCH, "1")
    first = _call(gateway, "nexus_assist_submit", _assist("lane-assist-8"))
    assert not first.get("isError"), first
    stored = gateway._assist_read("lane-assist-8")
    assert stored is not None and stored["status"] == "FAILED"
    assert [kind for kind, _ in launches] == ["Popen"]
    monkeypatch.delenv(SWITCH)
    replay = _call(gateway, "nexus_assist_submit", _assist("lane-assist-8"))
    assert not replay.get("isError"), replay
    assert replay["structuredContent"]["task_id"] == "lane-assist-8"
    assert replay["structuredContent"]["status"] == "FAILED"
    assert gateway._assist_read("lane-assist-8")["job_id"] == stored["job_id"]
    assert [kind for kind, _ in launches] == ["Popen"]


def test_switch_off_still_replays_a_stored_model_probe(box, monkeypatch) -> None:
    gateway, _state, launches = box
    versions: list[str] = []

    def version_run(argv: Any, *args: Any, **kwargs: Any):
        versions.append(f"cline {len(versions) + 1}")
        return subprocess.CompletedProcess(argv, 0, stdout=versions[-1], stderr="")

    monkeypatch.setattr(subprocess, "run", version_run)
    monkeypatch.setenv(SWITCH, "1")
    first = _call(gateway, "nexus_model_probe", _probe("lane-probe-8"))
    assert not first.get("isError"), first
    stored = gateway._assist_read("lane-probe-8")
    assert stored is not None
    assert (stored["status"], stored["blocker"]) == ("FAILED", "ASSIST_PROVIDER_IDENTITY_DRIFT")
    assert len(versions) == 2
    monkeypatch.delenv(SWITCH)
    replay = _call(gateway, "nexus_model_probe", _probe("lane-probe-8"))
    assert not replay.get("isError"), replay
    assert replay["structuredContent"]["task_id"] == "lane-probe-8"
    assert replay["structuredContent"]["status"] == "FAILED"
    assert gateway._assist_read("lane-probe-8")["job_id"] == stored["job_id"]
    assert len(versions) == 2 and launches == []


@pytest.mark.parametrize("blank", [{"provider": "  "}, {"provider": "\t", "model": " "}])
def test_a_blank_probe_provider_without_model_is_the_default_lane(box, blank) -> None:
    gateway, state, launches = box
    assert _error(gateway, "nexus_model_probe", _probe("lane-probe-9", **blank)).startswith(
        PROBE_BLOCKER
    )
    assert launches == []
    assert _no_job_written(state)


def test_a_blank_probe_provider_with_a_model_keeps_not_registered(box) -> None:
    gateway, state, launches = box
    assert (
        _error(gateway, "nexus_model_probe", _probe("lane-probe-10", provider="  ", model="m1"))
        == "ASSIST_PROVIDER_NOT_REGISTERED"
    )
    assert launches == []
    assert _no_job_written(state)


def _no_cline_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(provider: str, **_: Any) -> str:
        raise ValueError("provider_binary_not_found")

    monkeypatch.setattr(gateway_module, "resolve_registered_provider_executable", resolve)


def test_an_implicit_probe_without_executable_reports_the_default_lane(box, monkeypatch) -> None:
    gateway, state, launches = box
    _no_cline_executable(monkeypatch)
    assert _error(gateway, "nexus_model_probe", _probe("lane-probe-11")).startswith(PROBE_BLOCKER)
    assert launches == []
    assert _no_job_written(state)


def test_switch_on_an_implicit_probe_without_executable_stays_unavailable(box, monkeypatch) -> None:
    gateway, _state, launches = box
    _no_cline_executable(monkeypatch)
    monkeypatch.setenv(SWITCH, "1")
    assert (
        _error(gateway, "nexus_model_probe", _probe("lane-probe-12"))
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )
    assert launches == []


# --- #3171: an explicit request for exactly the default lane, the schema, and retry ---

EXPLICIT_DEFAULT_LANE = [
    {"provider": "cline", "model": "glm-5.2"},
    {"provider": " CLINE ", "model": " glm-5.2\n"},
    {"provider": "cline", "model": "cline-pass/glm-5.2"},
]


@pytest.mark.parametrize("named", EXPLICIT_DEFAULT_LANE)
def test_an_assist_naming_exactly_the_default_lane_is_refused(box, named) -> None:
    gateway, state, launches = box
    message = _error(gateway, "nexus_assist_submit", _assist("lane-assist-31", **named))
    assert message.startswith(ASSIST_BLOCKER)
    assert launches == []
    assert gateway._assist_read("lane-assist-31") is None
    assert _no_job_written(state)


def test_an_assist_naming_the_default_lane_through_preferred_fields_is_refused(box) -> None:
    gateway, state, launches = box
    named = {"preferred_worker": "cline", "preferred_model": "glm-5.2"}
    message = _error(gateway, "nexus_assist_submit", _assist("lane-assist-32", **named))
    assert message.startswith(ASSIST_BLOCKER)
    assert launches == []
    assert _no_job_written(state)


@pytest.mark.parametrize("named", EXPLICIT_DEFAULT_LANE)
def test_a_probe_naming_exactly_the_default_lane_is_refused(box, named) -> None:
    gateway, state, launches = box
    message = _error(gateway, "nexus_model_probe", _probe("lane-probe-31", **named))
    assert message.startswith(PROBE_BLOCKER)
    assert launches == []
    assert gateway._assist_read("lane-probe-31") is None
    assert _no_job_written(state)


def test_switch_on_an_explicit_default_lane_keeps_its_behaviour(box, monkeypatch, tmp_path) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv(SWITCH, "1")
    named = {"provider": "cline", "model": "glm-5.2"}
    assert (
        _error(gateway, "nexus_model_probe", _probe("lane-probe-33", **named))
        == "ASSIST_PROVIDER_VERSION_FAILED"
    )
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(tmp_path / "missing-cline"))
    assert (
        _error(gateway, "nexus_assist_submit", _assist("lane-assist-33", **named))
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )
    assert [kind for kind, _ in launches] == ["run"]


def test_an_assist_naming_another_cline_model_keeps_its_behaviour(
    box, monkeypatch, tmp_path
) -> None:
    gateway, _state, launches = box
    monkeypatch.setenv("NEXUS_CLINE_BIN", str(tmp_path / "missing-cline"))
    named = {"provider": "cline", "model": "glm-5.3"}
    assert (
        _error(gateway, "nexus_assist_submit", _assist("lane-assist-34", **named))
        == "ASSIST_PROVIDER_UNAVAILABLE"
    )
    assert launches == []


@pytest.mark.parametrize("tool", ["nexus_assist_submit", "nexus_model_probe"])
def test_the_schema_advertises_no_default_lane(tool) -> None:
    specs = {spec["name"]: spec for spec in UnifiedMCPGateway.tool_specs()}
    properties = specs[tool]["inputSchema"]["properties"]
    for field in ("provider", "model"):
        assert "default" not in properties[field], (tool, field)
    assert "glm-5.2" not in str(specs[tool])


def _stored_failed_assist(gateway, monkeypatch, task_id: str, **named: Any) -> dict[str, Any]:
    monkeypatch.setenv(SWITCH, "1")
    first = _call(gateway, "nexus_assist_submit", _assist(task_id, **named))
    assert not first.get("isError"), first
    stored = gateway._assist_read(task_id)
    assert stored is not None and stored["status"] == "FAILED"
    monkeypatch.delenv(SWITCH)
    return stored


@pytest.mark.parametrize("named", [{}, {"provider": "cline", "model": "glm-5.2"}])
def test_switch_off_refuses_a_retry_on_the_default_lane(box, monkeypatch, named) -> None:
    gateway, _state, launches = box
    stored = _stored_failed_assist(gateway, monkeypatch, "lane-assist-35", **named)
    assert [kind for kind, _ in launches] == ["Popen"]
    with pytest.raises(gateway_module.GatewayInputError) as refused:
        gateway._assist_retry("lane-assist-35")
    assert str(refused.value).startswith(ASSIST_BLOCKER)
    assert [kind for kind, _ in launches] == ["Popen"]
    assert gateway._assist_read("lane-assist-35") == stored


def test_switch_on_a_retry_on_the_default_lane_launches_again(box, monkeypatch) -> None:
    gateway, _state, launches = box
    _stored_failed_assist(gateway, monkeypatch, "lane-assist-36")
    monkeypatch.setenv(SWITCH, "1")
    retried = gateway._assist_retry("lane-assist-36")
    assert retried["status"] == "FAILED"
    assert [kind for kind, _ in launches] == ["Popen", "Popen"]


def test_switch_off_a_retry_on_another_cline_model_launches_again(box, monkeypatch) -> None:
    gateway, _state, launches = box
    _stored_failed_assist(gateway, monkeypatch, "lane-assist-37", provider="cline", model="glm-5.3")
    retried = gateway._assist_retry("lane-assist-37")
    assert retried["status"] == "FAILED"
    assert [kind for kind, _ in launches] == ["Popen", "Popen"]
