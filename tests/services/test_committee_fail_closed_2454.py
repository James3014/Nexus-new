"""#2454 regression: the committee never passes on an indeterminate round.

All-abstain, all-failed verdicts and all ``not_executed`` verdicts must each give
``gate_passed is False`` (the #2069 escape fixed by #2077, now routed through
``nexus.contracts.fail_closed.decide``). A verified winner still passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from nexus.committee import controller as committee_controller
from nexus.core import capability_executor_registry as reg
from nexus.core.belief_contracts import CapabilityExecutionPlan


@dataclass
class _Candidate:
    candidate_id: str
    source_model: str


@dataclass
class _Verdict:
    candidate_id: str
    passed: bool
    verifier_name: str = "fake_verifier"
    score: float = 0.0


@dataclass
class _Result:
    candidates: list[_Candidate]
    verdicts: list[_Verdict]
    winner_id: str = ""
    abstained: bool = False
    failure_bucket: str = ""
    task_id: str = "t-2454"
    confidence: float = 0.0
    verifier_gap: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


_CANDIDATES = [_Candidate("c-a", "proposer-a"), _Candidate("c-b", "proposer-b")]

_ROUNDS: dict[str, _Result] = {
    "all_abstain": _Result(
        candidates=_CANDIDATES,
        verdicts=[_Verdict("c-a", False), _Verdict("c-b", False)],
        winner_id="",
        abstained=True,
        failure_bucket="ABSTAIN",
    ),
    "all_failed_verdicts": _Result(
        candidates=_CANDIDATES,
        verdicts=[_Verdict("c-a", False, score=0.4), _Verdict("c-b", False, score=0.2)],
        winner_id="c-a",
    ),
    "all_not_executed": _Result(
        candidates=_CANDIDATES,
        verdicts=[
            _Verdict("c-a", False, verifier_name="not_executed:no_os_barrier"),
            _Verdict("c-b", False, verifier_name="not_executed:no_os_barrier"),
        ],
        winner_id="c-b",
        failure_bucket="not_executed:no_os_barrier",
    ),
}


def _install_fake_controller(monkeypatch: pytest.MonkeyPatch, result: _Result) -> None:
    class _FakeController:
        enabled = True

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def process_proposals(self, proposals: list[dict[str, Any]]) -> _Result:
            return result

    monkeypatch.setattr(committee_controller, "CommitteeControllerV263", _FakeController)


def _run(monkeypatch: pytest.MonkeyPatch, result: _Result):
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    _install_fake_controller(monkeypatch, result)
    proposals = [
        {"proposer_id": name, "model": name, "raw_label": f"label-{name}", "artifacts": ["diff"]}
        for name in ("proposer-a", "proposer-b")
    ]
    plan = CapabilityExecutionPlan(
        task_id="t-2454", plan_id="p-2454", constraints={"committee_proposals": proposals}
    )
    return reg._exec_committee(plan, "pick a candidate")


@pytest.mark.parametrize("round_name", sorted(_ROUNDS))
def test_indeterminate_committee_round_never_passes(
    monkeypatch: pytest.MonkeyPatch, round_name: str
) -> None:
    receipt = _run(monkeypatch, _ROUNDS[round_name])
    assert receipt.gate_passed is False, round_name
    assert receipt.outcome["semantic_status"] == "FAILED"
    assert receipt.outcome["error"] == "COMMITTEE_NO_VERIFIED_CANDIDATE"


def test_verified_winner_still_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _Result(
        candidates=_CANDIDATES,
        verdicts=[_Verdict("c-a", True, score=1.0), _Verdict("c-b", False)],
        winner_id="c-a",
    )
    receipt = _run(monkeypatch, result)
    assert receipt.gate_passed is True
    assert receipt.outcome["semantic_status"] == "SUCCEEDED"
    assert receipt.outcome["error"] == ""
