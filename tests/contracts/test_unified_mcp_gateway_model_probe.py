"""Characterization tests for the gateway's provider-probe and Agy lease helpers (Issue #2481).

Big-file split G7a: pins ``_provider_executable``, ``_provider_preflight`` (through the
public ``nexus_provider_preflight`` tool), ``_agy_probe_model_family``,
``_acquire_agy_probe_claim``, ``_release_assist_account_claim`` and
``_abandon_assist_account_claim`` before they move out of ``UnifiedMCPGateway`` into a
mixin.  Every collaborator is patched on the gateway facade module
(``resolve_registered_provider_executable``, ``get_account_pool_manager``,
``CrossProcessLeaseCoordinator``, ``Path.home``), so the tests also prove that those facade
patches keep reaching the moved code.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

import pytest

from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway
from nexus.services.agy_account_pool import AgyAccountPoolBusyError, AgyAccountPoolExhaustedError
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY


class _Service(SelfHostedTaskService):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir


@pytest.fixture
def gateway(tmp_path: Path) -> UnifiedMCPGateway:
    return UnifiedMCPGateway(service=_Service(tmp_path / "state"))


def _script(tmp_path: Path, name: str, body: str, *, mode: int = 0o755) -> Path:
    path = tmp_path / "bin" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(mode)
    return path


def _resolve_to(monkeypatch: pytest.MonkeyPatch, value: Any) -> list[dict]:
    calls: list[dict] = []

    def resolve(provider: str, **kwargs: Any) -> str:
        calls.append({"provider": provider, **kwargs})
        if isinstance(value, BaseException):
            raise value
        return str(value)

    monkeypatch.setattr(gateway_module, "resolve_registered_provider_executable", resolve)
    return calls


def _preflight(gateway: UnifiedMCPGateway, **arguments: Any) -> dict[str, Any]:
    response = gateway.handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "nexus_provider_preflight", "arguments": arguments},
    })
    assert response is not None
    result = response["result"]
    assert not result.get("isError"), result
    return result["structuredContent"]


# --- _provider_executable ----------------------------------------------------------


def test_provider_executable_unknown_provider_has_no_metadata(gateway) -> None:
    assert gateway._provider_executable("no-such-provider") == ({}, None)


def test_provider_executable_resolves_registered_binary(gateway, monkeypatch, tmp_path) -> None:
    binary = _script(tmp_path, "cline", "exit 0\n")
    calls = _resolve_to(monkeypatch, binary)
    assert gateway._provider_executable("cline") == (
        ONLINE_CLI_SPEC_REGISTRY["cline"],
        str(binary.resolve()),
    )
    assert calls == [{"provider": "cline"}]


@pytest.mark.parametrize(
    ("provider", "error"),
    [("cline", ValueError("provider_binary_not_found")), ("agy", ValueError("other"))],
)
def test_provider_executable_resolution_failure_keeps_metadata(
    gateway, monkeypatch, provider, error
) -> None:
    _resolve_to(monkeypatch, error)
    assert gateway._provider_executable(provider) == (ONLINE_CLI_SPEC_REGISTRY[provider], None)


def test_agy_falls_back_to_home_local_bin(gateway, monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    agy = _script(home, "agy", "exit 0\n")
    (home / ".local").mkdir()
    (home / ".local" / "bin").symlink_to(agy.parent)
    monkeypatch.setattr(gateway_module.Path, "home", classmethod(lambda cls: home))
    calls: list[dict] = []

    def resolve(provider: str, **kwargs: Any) -> str:
        calls.append(kwargs)
        if not kwargs:
            raise ValueError("provider_binary_not_found")
        return kwargs["environ"]["NEXUS_AGY_BIN"]

    monkeypatch.setattr(gateway_module, "resolve_registered_provider_executable", resolve)
    metadata, executable = gateway._provider_executable("agy")
    assert metadata == ONLINE_CLI_SPEC_REGISTRY["agy"]
    assert executable == str(agy.resolve())
    assert len(calls) == 2
    environ = calls[1]["environ"]
    assert (
        environ["NEXUS_AGY_BIN"] == environ["NEXUS_AGY_EXECUTABLE"] == str(home / ".local/bin/agy")
    )


@pytest.mark.parametrize("case", ["missing", "not_executable", "second_resolution_fails"])
def test_agy_fallback_failures_return_no_executable(gateway, monkeypatch, tmp_path, case) -> None:
    home = tmp_path / "home"
    if case != "missing":
        _script(
            home / ".local", "agy", "exit 0\n", mode=0o644 if case == "not_executable" else 0o755
        )
    monkeypatch.setattr(gateway_module.Path, "home", classmethod(lambda cls: home))

    def resolve(provider: str, **kwargs: Any) -> str:
        raise ValueError("provider_binary_not_found")

    monkeypatch.setattr(gateway_module, "resolve_registered_provider_executable", resolve)
    assert gateway._provider_executable("agy") == (ONLINE_CLI_SPEC_REGISTRY["agy"], None)


# --- _provider_preflight via nexus_provider_preflight ------------------------------


def test_preflight_unregistered_provider(gateway) -> None:
    result = _preflight(gateway, provider="no-such-provider", model="m")
    assert (result["status"], result["blocker"], result["binary_found"]) == (
        "BLOCKED",
        "ASSIST_PROVIDER_NOT_REGISTERED",
        False,
    )
    assert result["schema"] == "nexus.provider_preflight.v1"


def test_preflight_unavailable_binary(gateway, monkeypatch) -> None:
    _resolve_to(monkeypatch, ValueError("provider_binary_not_found"))
    result = _preflight(gateway, provider="cline")
    assert (result["status"], result["blocker"]) == ("BLOCKED", "ASSIST_PROVIDER_UNAVAILABLE")
    assert (result["requested_model"], result["resolved_model"]) == (
        "glm-5.2",
        "cline-pass/glm-5.2",
    )
    assert result["authentication_required"] is True


def test_preflight_unreadable_binary(gateway, monkeypatch, tmp_path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    _resolve_to(monkeypatch, directory)
    result = _preflight(gateway, provider="cline", model="m1")
    assert result["blocker"] == "ASSIST_PROVIDER_BINARY_UNREADABLE"
    assert result["binary_path"] == str(directory.resolve())


def test_preflight_version_launch_failure(gateway, monkeypatch, tmp_path) -> None:
    binary = _script(tmp_path, "cline", "exit 0\n", mode=0o644)
    _resolve_to(monkeypatch, binary)
    result = _preflight(gateway, provider="cline", model="m1")
    assert result["blocker"] == "ASSIST_PROVIDER_VERSION_FAILED"
    assert result["provider_error"]
    assert result["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()


def test_preflight_version_nonzero_exit(gateway, monkeypatch, tmp_path) -> None:
    binary = _script(tmp_path, "cline", "echo 'cline 1.2.3 broken' >&2\nexit 3\n")
    _resolve_to(monkeypatch, binary)
    result = _preflight(gateway, provider="cline", model="m1")
    assert (result["blocker"], result["exit_code"]) == ("ASSIST_PROVIDER_VERSION_FAILED", 3)
    assert result["cli_version"] == "cline 1.2.3 broken"
    assert result["cli_version_sha256"] == hashlib.sha256(b"cline 1.2.3 broken").hexdigest()


@pytest.mark.parametrize(
    ("probe", "blocker", "extra"),
    [
        (False, "MODEL_PROBE_REQUIRED", {}),
        (True, "MODEL_PROBE_ASYNC_REQUIRED", {"probe_mode": "deferred_async_isolated"}),
    ],
)
def test_preflight_without_probe_evidence_requires_async_probe(
    gateway, monkeypatch, tmp_path, probe, blocker, extra
) -> None:
    binary = _script(tmp_path, "cline", "echo 'cline 9.9.9'\n")
    _resolve_to(monkeypatch, binary)
    result = _preflight(gateway, provider="cline", model="vendor/m1", probe=probe)
    assert (result["status"], result["blocker"], result["next_action"]) == (
        "VERSION_VERIFIED",
        blocker,
        "nexus_model_probe",
    )
    assert (result["readiness_status"], result["execution_ready"]) == ("VERSION_VERIFIED", False)
    assert (result["requested_model"], result["resolved_model"]) == ("vendor/m1", "vendor/m1")
    assert result["probe_requested"] is probe
    assert result["cli_version"] == "cline 9.9.9" and result["exit_code"] is None
    assert result["version_latency_ms"] >= 0
    for key, value in extra.items():
        assert result[key] == value


@pytest.mark.parametrize(("authenticated", "ready"), [(True, True), (False, False)])
def test_preflight_with_probe_evidence(
    gateway, monkeypatch, tmp_path, authenticated, ready
) -> None:
    binary = _script(tmp_path, "cline", "echo 'cline 9.9.9'\n")
    _resolve_to(monkeypatch, binary)
    seen: list[dict] = []
    evidence = {
        "authenticated": authenticated,
        "authentication_evidence": "successful_exact_model_probe",
        "evidence_hash": "e" * 64,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }

    def read(**kwargs: Any):
        seen.append(kwargs)
        return evidence

    monkeypatch.setattr(gateway, "_read_probe_evidence", read)
    result = _preflight(gateway, provider="cline", model="m1")
    assert seen == [
        {
            "provider": "cline",
            "requested_model": "m1",
            "resolved_model": "cline-pass/m1",
            "executable": str(binary.resolve()),
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "cli_version": "cline 9.9.9",
        }
    ]
    if ready:
        assert (result["readiness_status"], result["execution_ready"], result["blocker"]) == (
            "MODEL_VERIFIED",
            True,
            None,
        )
        assert (
            result["model_reachable"],
            result["requested_model_verified"],
            result["authenticated"],
        ) == (True, True, True)
        assert (result["probe_evidence_hash"], result["probe_expires_at"]) == (
            "e" * 64,
            "2099-01-01T00:00:00+00:00",
        )
    else:
        assert (result["blocker"], result["execution_ready"]) == ("MODEL_PROBE_REQUIRED", False)


# --- _agy_probe_model_family / _acquire_agy_probe_claim ----------------------------


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("gemini-3.8-flash", "gemini"),
        ("  Gemini-x ", "gemini"),
        ("claude-sonnet", "claude_gpt"),
        ("GPT-5", "claude_gpt"),
    ],
)
def test_agy_probe_model_family(model, family) -> None:
    assert UnifiedMCPGateway._agy_probe_model_family(model) == family


@pytest.mark.parametrize("model", ["", "llama-3", None])
def test_agy_probe_model_family_rejects_unknown(model) -> None:
    with pytest.raises(GatewayInputError, match="^AGY_MODEL_FAMILY_UNSUPPORTED$"):
        UnifiedMCPGateway._agy_probe_model_family(model)


class _Coordinator:
    instances: list["_Coordinator"] = []
    outcome: Any = "claim"

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.calls: list[dict] = []
        _Coordinator.instances.append(self)

    def acquire_claim(self, **kwargs: Any):
        self.calls.append(kwargs)
        if isinstance(_Coordinator.outcome, BaseException):
            raise _Coordinator.outcome
        return _Coordinator.outcome


@pytest.fixture
def pool(monkeypatch):
    manager = object()
    _Coordinator.instances = []
    _Coordinator.outcome = "claim"
    monkeypatch.setattr(gateway_module, "get_account_pool_manager", lambda: manager)
    monkeypatch.setattr(gateway_module, "CrossProcessLeaseCoordinator", _Coordinator)
    return manager


def test_acquire_agy_probe_claim_uses_pool_manager_and_family(gateway, pool) -> None:
    assert gateway._acquire_agy_probe_claim(task_id="t1", model="gemini-3.8") == "claim"
    (coordinator,) = _Coordinator.instances
    assert coordinator.manager is pool
    assert coordinator.calls == [
        {"consumer_id": "model-probe:t1", "wait_timeout": 0.0, "model_family": "gemini"}
    ]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (AgyAccountPoolBusyError("busy"), "AGY_ACCOUNT_POOL_BUSY"),
        (AgyAccountPoolExhaustedError("none"), "AGY_ACCOUNT_POOL_EXHAUSTED"),
    ],
)
def test_acquire_agy_probe_claim_maps_pool_errors(gateway, pool, error, message) -> None:
    _Coordinator.outcome = error
    with pytest.raises(GatewayInputError, match=f"^{message}$") as raised:
        gateway._acquire_agy_probe_claim(task_id="t1", model="claude-x")
    assert raised.value.__cause__ is error


def test_acquire_agy_probe_claim_rejects_unknown_family_before_acquire(gateway, pool) -> None:
    with pytest.raises(GatewayInputError, match="^AGY_MODEL_FAMILY_UNSUPPORTED$"):
        gateway._acquire_agy_probe_claim(task_id="t1", model="llama")
    (coordinator,) = _Coordinator.instances
    assert coordinator.calls == []


# --- lease release / abandon -------------------------------------------------------


class _Claim:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.released = 0
        self.abandoned = 0

    def release(self) -> None:
        self.released += 1
        if self.fail:
            raise RuntimeError("release failed")

    def abandon_parent_reference(self) -> None:
        self.abandoned += 1


def test_release_without_claim_or_lease_is_clean(gateway) -> None:
    job: dict[str, Any] = {}
    assert gateway._release_assist_account_claim("t1", job) is True
    assert job == {}


def test_release_without_claim_but_with_lease_requires_reconciliation(gateway) -> None:
    job: dict[str, Any] = {"account_lease_id_hash": "h"}
    assert gateway._release_assist_account_claim("t1", job) is False
    assert (job["account_lease_released"], job["account_lease_cleanup_status"]) == (
        False,
        "RECONCILIATION_REQUIRED",
    )


@pytest.mark.parametrize(
    ("fail", "ok", "status"), [(False, True, "RELEASED"), (True, False, "RELEASE_FAILED")]
)
def test_release_of_held_claim(gateway, fail, ok, status) -> None:
    claim = _Claim(fail=fail)
    gateway._assist_account_claims["t1"] = claim
    job: dict[str, Any] = {}
    assert gateway._release_assist_account_claim("t1", job) is ok
    assert claim.released == 1 and "t1" not in gateway._assist_account_claims
    assert (job["account_lease_released"], job["account_lease_cleanup_status"]) == (ok, status)


@pytest.mark.parametrize("held", [True, False])
def test_abandon_marks_reconciliation_and_drops_parent_reference(gateway, held) -> None:
    claim = _Claim()
    if held:
        gateway._assist_account_claims["t1"] = claim
    job: dict[str, Any] = {}
    assert gateway._abandon_assist_account_claim("t1", job) is None
    assert claim.abandoned == (1 if held else 0) and claim.released == 0
    assert "t1" not in gateway._assist_account_claims
    assert job == {
        "account_lease_released": False,
        "account_lease_cleanup_status": "RECONCILIATION_REQUIRED",
        "reconciliation_required": True,
    }


def test_lease_helpers_take_the_instance_lock(gateway) -> None:
    gateway._assist_account_claims["t1"] = _Claim()
    acquired = threading.Event()
    done = threading.Event()

    def other() -> None:
        acquired.wait(5)
        gateway._release_assist_account_claim("t1", {})
        done.set()

    worker = threading.Thread(target=other)
    with gateway._assist_lock:
        worker.start()
        acquired.set()
        assert not done.wait(0.2)  # blocked on the same RLock
    assert done.wait(5)
    worker.join(5)
