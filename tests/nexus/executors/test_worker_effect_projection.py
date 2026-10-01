from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerAdapter,
    WorkerExecutionReceipt,
    WorkerPreflight,
    WorkerProviderUnavailable,
)
from nexus.executors.worker_registry import WorkerRegistry


class FakeAdapter:
    def __init__(self, provider: str, *, supports_effect_projection: bool = False):
        self.provider = provider
        self.supports_effect_projection = supports_effect_projection
        self.calls = 0
        self.options: dict[str, Any] = {}

    def preflight(self) -> WorkerPreflight:
        return WorkerPreflight(
            provider=self.provider,
            executable=f"/fake/{self.provider}",
            executable_available=True,
            authorized=True,
            implementation_status="IMPLEMENTED",
            ready=True,
            reason="ready",
        )

    def invoke(self, contract, lease, *, prompt: str, **options: Any) -> WorkerExecutionReceipt:
        self.calls += 1
        self.options = dict(options)
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=lease.target_worktree,
            worker_status="completed",
            outcome="EXECUTION_COMPLETED",
            exit_code=0,
            executable_identity=f"/fake/{self.provider}",
            argv=("fake",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=1,
            process_group_id=1,
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )


def _registry(*, provider: str = "codex", supports_effect_projection: bool = False):
    adapters: dict[str, WorkerAdapter] = {}
    selected: FakeAdapter | None = None
    for name in SUPPORTED_WORKER_PROVIDERS:
        adapter = FakeAdapter(
            name,
            supports_effect_projection=(supports_effect_projection if name == provider else False),
        )
        adapters[name] = adapter
        if name == provider:
            selected = adapter
    assert selected is not None
    return WorkerRegistry(adapters), selected


def _subject():
    return SimpleNamespace(task_id="wave4-task"), SimpleNamespace(
        target_worktree="/tmp/wave4-target"
    )


def test_legacy_none_pair_is_removed_before_adapter_invoke():
    registry, adapter = _registry()
    contract, lease = _subject()

    registry.invoke(
        "codex",
        contract,
        lease,
        prompt="bounded task",
        effect_authorization=None,
        tool_projection_manifest=None,
        model="gpt-test",
    )

    assert adapter.calls == 1
    assert "effect_authorization" not in adapter.options
    assert "tool_projection_manifest" not in adapter.options
    assert adapter.options["model"] == "gpt-test"


def test_effect_bound_execution_blocks_legacy_adapter_before_provider_call():
    registry, adapter = _registry()
    contract, lease = _subject()

    with pytest.raises(
        WorkerProviderUnavailable,
        match="projection-aware backend",
    ):
        registry.invoke(
            "codex",
            contract,
            lease,
            prompt="bounded task",
            effect_authorization={"authorization_hash": "a" * 64},
            tool_projection_manifest={"projection_hash": "b" * 64},
        )

    assert adapter.calls == 0


def test_effect_bound_execution_requires_authorization_projection_pair():
    registry, adapter = _registry()
    contract, lease = _subject()

    with pytest.raises(
        WorkerProviderUnavailable,
        match="must be supplied together",
    ):
        registry.invoke(
            "codex",
            contract,
            lease,
            prompt="bounded task",
            effect_authorization={"authorization_hash": "a" * 64},
            tool_projection_manifest=None,
        )

    assert adapter.calls == 0


def test_projection_aware_adapter_receives_exact_pair():
    registry, adapter = _registry(supports_effect_projection=True)
    contract, lease = _subject()
    authorization = {"authorization_hash": "a" * 64}
    projection = {"projection_hash": "b" * 64}

    registry.invoke(
        "codex",
        contract,
        lease,
        prompt="bounded task",
        effect_authorization=authorization,
        tool_projection_manifest=projection,
    )

    assert adapter.calls == 1
    assert adapter.options["effect_authorization"] is authorization
    assert adapter.options["tool_projection_manifest"] is projection
