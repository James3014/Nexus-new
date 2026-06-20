import pytest
from nexus.services.local_heal.strategy_differentiator import (
    StrategyID,
    ProbeScore,
    score_strategy,
    rank_strategies,
)


def test_probe_score_positive_when_narrows_span():
    score = ProbeScore(
        narrows_target_span=True,
        avoids_no_op=False,
        reduces_retry=False,
        improves_syntax_valid=False,
        is_default_tie_break=False,
    )
    assert score.positive
    assert score.score == 1


def test_probe_score_positive_when_avoids_noop():
    score = ProbeScore(
        narrows_target_span=False,
        avoids_no_op=True,
        reduces_retry=False,
        improves_syntax_valid=False,
        is_default_tie_break=False,
    )
    assert score.positive
    assert score.score == 1


def test_probe_score_not_positive_when_tie_break():
    score = ProbeScore(
        narrows_target_span=True,
        avoids_no_op=True,
        reduces_retry=True,
        improves_syntax_valid=True,
        is_default_tie_break=True,
    )
    assert not score.positive
    assert score.score == 4


def test_probe_score_not_positive_when_all_false():
    score = ProbeScore(
        narrows_target_span=False,
        avoids_no_op=False,
        reduces_retry=False,
        improves_syntax_valid=False,
        is_default_tie_break=False,
    )
    assert not score.positive
    assert score.score == 0


def test_score_strategy_narrows_span():
    baseline = {"target_span_lines": 50}
    candidate = {"target_span_lines": 20}
    probe = score_strategy("c1", "traceback_first", baseline, candidate)
    assert probe.narrows_target_span
    assert probe.positive


def test_score_strategy_avoids_noop():
    baseline = {"no_op_patch": True}
    candidate = {"no_op_patch": False}
    probe = score_strategy("c1", "source_anchor_first", baseline, candidate)
    assert probe.avoids_no_op
    assert probe.positive


def test_score_strategy_reduces_retry():
    baseline = {"retry_count": 3}
    candidate = {"retry_count": 1}
    probe = score_strategy("c1", "semantic_invariant_first", baseline, candidate)
    assert probe.reduces_retry
    assert probe.positive


def test_score_strategy_improves_syntax():
    baseline = {"syntax_pass": False}
    candidate = {"syntax_pass": True}
    probe = score_strategy("c1", "traceback_first", baseline, candidate)
    assert probe.improves_syntax_valid
    assert probe.positive


def test_rank_strategies_non_tie_break():
    strategies = [
        {"strategy_id": "traceback_first", "target_span_lines": 20, "retry_count": 1},
        {"strategy_id": "source_anchor_first", "target_span_lines": 40, "retry_count": 3},
        {"strategy_id": "semantic_invariant_first", "target_span_lines": 30, "retry_count": 2},
    ]
    baseline = {"target_span_lines": 50, "retry_count": 3}
    ranking = rank_strategies("astropy__astropy-13236", strategies, baseline)
    assert ranking.has_non_tie_break
    assert ranking.rankings[0]["strategy_id"] == "traceback_first"
    assert ranking.rankings[0]["positive"]


def test_rank_strategies_tie_break():
    strategies = [
        {"strategy_id": "traceback_first", "target_span_lines": 30},
        {"strategy_id": "source_anchor_first", "target_span_lines": 30},
        {"strategy_id": "semantic_invariant_first", "target_span_lines": 30},
    ]
    baseline = {"target_span_lines": 50}
    ranking = rank_strategies("astropy__astropy-13236", strategies, baseline)
    assert not ranking.has_non_tie_break
    for r in ranking.rankings:
        assert r["is_default_tie_break"]
        assert not r["positive"]


def test_strategy_id_enum_values():
    assert StrategyID.TRACEBACK_FIRST.value == "traceback_first"
    assert StrategyID.SOURCE_ANCHOR_FIRST.value == "source_anchor_first"
    assert StrategyID.SEMANTIC_INVARIANT_FIRST.value == "semantic_invariant_first"


def test_score_all_dimensions():
    baseline = {"target_span_lines": 100, "no_op_patch": True, "retry_count": 5, "syntax_pass": False}
    candidate = {"target_span_lines": 10, "no_op_patch": False, "retry_count": 0, "syntax_pass": True}
    probe = score_strategy("c1", "traceback_first", baseline, candidate)
    assert probe.narrows_target_span
    assert probe.avoids_no_op
    assert probe.reduces_retry
    assert probe.improves_syntax_valid
    assert probe.score == 4
    assert probe.positive
