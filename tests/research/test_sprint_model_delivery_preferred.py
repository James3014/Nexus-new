"""R2 (online A/B 2026-10-14, gov-002): a verified model answer is the delivered one.

In the bounded hyper rescue, Autoreason picked ``local_hidden_shadow`` over a model candidate
with the same verified score, so the row's delivery became a local rescue.
"""

from __future__ import annotations

from nexus.research.sprint_service import CandidateEval, _select_candidate_with_routing_layers


def _candidates() -> list[CandidateEval]:
    return [
        CandidateEval(seed=0, score=1.0, source="llm", hint="verified patch"),
        CandidateEval(
            seed=1000,
            score=1.0,
            source="local_hidden_shadow",
            hint="very specific shadow verifier evidence " * 8,
            stdout="pytest evidence\n" * 20,
        ),
    ]


def test_autoreason_does_not_replace_verified_model_candidate_with_equal_local_shadow(monkeypatch):
    monkeypatch.delenv("NEXUS_DDTREE_EXECUTOR", raising=False)
    learning_trace: dict = {}

    best, active = _select_candidate_with_routing_layers(
        _candidates(),
        task="Refactor an authorization decision helper: deny by default for unknown roles and missing scopes.",
        learning_trace=learning_trace,
        enable_autoreason_executor=True,
        enable_ddtree_executor=False,
    )

    assert [item.source for item in active] == ["llm", "local_hidden_shadow"]
    assert learning_trace["autoreason"]["winner"] == "local_hidden_shadow:1000"
    assert best.source == "llm"
    assert learning_trace["autoreason"]["winner_overridden_by_model_delivery_guard"] is True


def test_local_candidate_still_wins_when_model_candidate_fails(monkeypatch):
    monkeypatch.delenv("NEXUS_DDTREE_EXECUTOR", raising=False)
    candidates = _candidates()
    candidates[0].score = 0.0
    best, _ = _select_candidate_with_routing_layers(
        candidates,
        task="Refactor an authorization decision helper.",
        learning_trace={},
        enable_autoreason_executor=True,
        enable_ddtree_executor=False,
    )
    assert best.source == "local_hidden_shadow"
