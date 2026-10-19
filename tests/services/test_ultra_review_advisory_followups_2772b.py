"""#2772 follow-ups (second round) for the host invoker's ``outcome_contributed``.

1. A non-advisory capability contributes exactly when its gate passed, even when its
   receipt carries advisory-looking keys (``advisory_only=True``, ``review_status="FAIL"``).
2. A record-only review contributes only when the executor's own ``review_passed`` is True,
   not merely when ``review_status == "PASS"``.
3. A PASS review that carries ``advisory_contract_violations`` (a lane could not run) is an
   incomplete review, not a pass, so it does not contribute.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus.core import capability_executor_registry as reg
from nexus.services import capability_registry
from tests.services import test_ultra_review_advisory_2732 as base

_FAKE_CAPABILITY = "fake_non_advisory_capability_2772"


def _context(tmp_path) -> dict[str, Any]:
    return {"task_id": "t-2772b", "task_statement": "review", "workspace_root": str(tmp_path)}


def _invoke_fake(monkeypatch, tmp_path, name: str, gate_passed: bool, outcome: dict[str, Any]):
    receipt = SimpleNamespace(
        invoked=True,
        gate_passed=gate_passed,
        evidence_id=f"ev_{name}",
        telemetries={},
        outcome=dict(outcome),
    )
    real_get_executor = reg.get_executor

    def _get_executor(key: str):
        if key == name:
            return lambda _plan, _desc: receipt
        return real_get_executor(key)

    monkeypatch.setattr(reg, "get_executor", _get_executor)
    invoker = capability_registry.build_real_executor_invoker(name)
    assert invoker is not None
    return invoker(_context(tmp_path))


@pytest.mark.parametrize("gate_passed", [True, False])
@pytest.mark.parametrize(
    "extra",
    [
        {},
        # Advisory-looking keys on a non-advisory capability must not change anything.
        {"advisory_only": True, "review_status": "FAIL", "review_passed": False},
    ],
    ids=["plain", "advisory_looking_fail"],
)
def test_non_advisory_capability_contributes_iff_gate_passed(
    tmp_path, monkeypatch, gate_passed, extra
) -> None:
    assert _FAKE_CAPABILITY not in reg.ADVISORY_ONLY_CAPABILITIES
    outcome = {"semantic_status": "SUCCEEDED", **extra}
    out = _invoke_fake(monkeypatch, tmp_path, _FAKE_CAPABILITY, gate_passed, outcome)
    assert out["gate_passed"] is gate_passed
    assert out["status"] == ("SUCCEEDED" if gate_passed else "FAILED")
    assert out["outcome_contributed"] is gate_passed


def _invoke_review(tmp_path, monkeypatch, payload: dict[str, Any]) -> Any:
    base._bind(monkeypatch, base._fake_service(payload))
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    return invoker(base._context(tmp_path))


def _pass_payload(**overrides: Any) -> dict[str, Any]:
    return {
        **base._fail_payload(),
        "status": "PASS",
        "gate_passed": True,
        "findings": [],
        **overrides,
    }


def test_pass_status_without_review_passed_does_not_contribute(tmp_path, monkeypatch) -> None:
    # The service says PASS but its own gate did not pass: the executor's review_passed is False.
    out = _invoke_review(tmp_path, monkeypatch, _pass_payload(gate_passed=False))
    outcome = out["response"]["outcome"]
    assert outcome["review_status"] == "PASS"
    assert outcome["review_passed"] is False
    assert out["gate_passed"] is True  # still record-only, never blocking
    assert out["outcome_contributed"] is False


@pytest.mark.parametrize("review_passed", [None, False, "true", 1])
def test_advisory_pass_requires_review_passed_to_be_true(
    tmp_path, monkeypatch, review_passed
) -> None:
    # Start from a real, complete PASS receipt and only vary the executor's review_passed.
    base._bind(monkeypatch, base._fake_service(_pass_payload()))
    real = reg._exec_ultra_review(base._plan(tmp_path), "review")
    assert real.outcome["review_passed"] is True
    outcome = dict(real.outcome)
    if review_passed is None:
        outcome.pop("review_passed")
    else:
        outcome["review_passed"] = review_passed
    out = _invoke_fake(monkeypatch, tmp_path, "ultra_review", True, outcome)
    assert "advisory_contract_violations" not in out["response"]
    assert out["response"]["outcome"]["review_status"] == "PASS"
    assert out["outcome_contributed"] is False
    out_true = _invoke_fake(
        monkeypatch, tmp_path, "ultra_review", True, {**outcome, "review_passed": True}
    )
    assert out_true["outcome_contributed"] is True


def test_pass_review_with_advisory_contract_violations_does_not_contribute(
    tmp_path, monkeypatch
) -> None:
    fleet = [
        {"lane": "security_sentry", "status": "PASS", "executed_checks": ["bandit"]},
        # The logic lane could not run any check: the review is incomplete.
        {"lane": "logic_breaker", "status": "PASS", "executed_checks": []},
        {"lane": "ghost_regression", "status": "PASS", "executed_checks": ["tests/test_app.py"]},
    ]
    out = _invoke_review(tmp_path, monkeypatch, _pass_payload(fleet=fleet))
    outcome = out["response"]["outcome"]
    assert outcome["review_status"] == "PASS"
    assert outcome["review_passed"] is True
    assert (
        "ultra_review_logic_breaker_no_executed_checks"
        in out["response"]["advisory_contract_violations"]
    )
    assert out["gate_passed"] is True  # the shortfall is recorded, never blocking
    assert out["status"] == "SUCCEEDED"
    assert out["outcome_contributed"] is False


def test_complete_pass_review_still_contributes(tmp_path, monkeypatch) -> None:
    out = _invoke_review(tmp_path, monkeypatch, _pass_payload())
    assert "advisory_contract_violations" not in out["response"]
    assert out["response"]["outcome"]["review_passed"] is True
    assert out["outcome_contributed"] is True


@pytest.mark.parametrize("flag", ["missing", False])
def test_ultra_review_without_advisory_flag_is_still_record_only(
    tmp_path, monkeypatch, flag
) -> None:
    """A record-only capability's receipt that omits/clears advisory_only cannot contribute
    a failed review (Gemini r1 on #2782)."""
    base._bind(monkeypatch, base._fake_service(base._fail_payload()))
    real = reg._exec_ultra_review(base._plan(tmp_path), "review")
    outcome = dict(real.outcome)
    assert outcome["review_status"] == "FAIL"
    if flag == "missing":
        outcome.pop("advisory_only")
    else:
        outcome["advisory_only"] = flag
    out = _invoke_fake(monkeypatch, tmp_path, "ultra_review", True, outcome)
    assert out["gate_passed"] is True
    assert out["outcome_contributed"] is False


@pytest.mark.parametrize(
    ("capability", "registry_key"),
    [
        ("ultra_review", "ultra_review_impl"),  # the capability name is record-only
        ("review_alias_2772", "ultra_review"),  # the registry key is record-only
    ],
)
def test_record_only_name_or_registry_key_decides(
    tmp_path, monkeypatch, capability, registry_key
) -> None:
    monkeypatch.setitem(capability_registry.EXECUTOR_REGISTRY_ALIASES, capability, registry_key)
    # A real FAIL review receipt (it satisfies the execution contract) without the flag.
    base._bind(monkeypatch, base._fake_service(base._fail_payload()))
    outcome = dict(reg._exec_ultra_review(base._plan(tmp_path), "review").outcome)
    outcome.pop("advisory_only")
    receipt = SimpleNamespace(
        invoked=True, gate_passed=True, evidence_id="ev", telemetries={}, outcome=outcome
    )
    real_get_executor = reg.get_executor
    monkeypatch.setattr(
        reg,
        "get_executor",
        lambda key: (lambda _p, _d: receipt) if key == registry_key else real_get_executor(key),
    )
    invoker = capability_registry.build_real_executor_invoker(capability)
    assert invoker is not None
    out = invoker(_context(tmp_path))
    assert out["gate_passed"] is True
    assert out["outcome_contributed"] is False
