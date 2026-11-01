"""#3111: the product canary must not leave NEXUS_ARMOR_ALLOW_EPHEMERAL set after it runs."""

from __future__ import annotations

import os

import pytest

from nexus.services import product_capability_canary_helper as helper
from nexus.services.capability_registry import PLANNER_EXECUTION_CONTRACTS

ENV = "NEXUS_ARMOR_ALLOW_EPHEMERAL"


@pytest.fixture
def seen(monkeypatch, tmp_path):
    """Stub the heavy pipeline; record the env value the canary sees while it runs."""
    helper._run_canary_mainchain_cached.cache_clear()
    calls: list[str | None] = []

    def fake_run_mainchain(*args, **kwargs):
        calls.append(os.environ.get(ENV))
        return {"terminal_status": "SUCCEEDED"}

    monkeypatch.setattr(helper, "run_mainchain", fake_run_mainchain)
    yield calls
    helper._run_canary_mainchain_cached.cache_clear()


def _run(task_id: str):
    name = next(iter(PLANNER_EXECUTION_CONTRACTS))
    return helper.run_canary_mainchain(name, positive=False, task_id_override=task_id)


def test_unset_stays_unset_after_canary(monkeypatch, seen):
    monkeypatch.delenv(ENV, raising=False)
    _run("scope-3111-unset")
    assert seen == ["1"]  # the canary itself still runs with the allowance on
    assert ENV not in os.environ


@pytest.mark.parametrize("previous", ["0", "", "custom"])
def test_previous_value_restored_after_canary(monkeypatch, seen, previous):
    monkeypatch.setenv(ENV, previous)
    _run(f"scope-3111-set-{previous or 'empty'}")
    assert seen == ["1"]
    assert os.environ[ENV] == previous


def test_restored_when_canary_raises(monkeypatch, seen):
    monkeypatch.delenv(ENV, raising=False)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(helper, "run_mainchain", boom)
    with pytest.raises(RuntimeError):
        _run("scope-3111-raises")
    assert ENV not in os.environ
