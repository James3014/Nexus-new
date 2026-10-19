"""#2772: follow-ups to the record-only ultra_review (#2732).

1. A record-only review contributes to the outcome only when the review itself passed.
2. The advisory/review observation keys are persisted only for ADVISORY_ONLY_CAPABILITIES.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus.orchestrator.self_hosted_task_service_parts import worker_dispatch
from nexus.services import capability_registry
from tests.services import test_ultra_review_advisory_2732 as base


def _invoke(tmp_path, monkeypatch, service) -> Any:
    base._bind(monkeypatch, service)
    invoker = capability_registry.build_real_executor_invoker("ultra_review")
    assert invoker is not None
    return invoker(base._context(tmp_path))


def test_pass_review_contributes(tmp_path, monkeypatch) -> None:
    payload = {**base._fail_payload(), "status": "PASS", "gate_passed": True, "findings": []}
    out = _invoke(tmp_path, monkeypatch, base._fake_service(payload))
    assert out["gate_passed"] is True
    assert out["outcome_contributed"] is True


@pytest.mark.parametrize("kind", ["FAIL", "BLOCKED", "ERROR", "UNAVAILABLE"])
def test_non_pass_review_never_contributes(tmp_path, monkeypatch, kind) -> None:
    if kind == "FAIL":
        service = base._fake_service(base._fail_payload())
    elif kind == "BLOCKED":
        service = base._fake_service({
            **base._fail_payload(),
            "status": "BLOCKED",
            "blocked_reason": "no_diff_to_review",
        })
    elif kind == "ERROR":
        service = base._fake_service(exc=RuntimeError("boom"))
    else:
        service = None
    out = _invoke(tmp_path, monkeypatch, service)
    assert out["gate_passed"] is True  # still record-only, never blocking
    assert out["response"]["outcome"]["review_status"] == kind
    assert out["outcome_contributed"] is False


def _stage(outcome: dict[str, Any]) -> dict[str, Any]:
    return {"status": "SUCCEEDED", "response": {"response": {"outcome": outcome}}}


def test_advisory_keys_are_not_accepted_from_other_capabilities() -> None:
    spoof = {
        "semantic_status": "SUCCEEDED",
        "advisory_only": True,
        "review_status": "PASS",
        "review_passed": True,
        "review_error": "x",
        "findings": [{"rule_id": "r"}],
    }
    observed = worker_dispatch._capability_observations({
        "codeintel": _stage(spoof),
        "ultra_review": _stage(spoof),
    })
    other = observed["codeintel"]
    for key in (
        "advisory_only",
        "review_status",
        "review_passed",
        "review_error_present",
        "review_findings_count",
    ):
        assert key not in other, key
    assert other["semantic_status"] == "SUCCEEDED"
    review = observed["ultra_review"]
    assert review["advisory_only"] is True
    assert review["review_status"] == "PASS"
    assert review["review_passed"] is True
    assert review["review_error_present"] is True
    assert review["review_findings_count"] == 1
