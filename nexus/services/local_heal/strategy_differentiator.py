"""Strategy Differentiator: shadow replay scoring for strategy ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class StrategyID(str, Enum):
    TRACEBACK_FIRST = "traceback_first"
    SOURCE_ANCHOR_FIRST = "source_anchor_first"
    SEMANTIC_INVARIANT_FIRST = "semantic_invariant_first"


@dataclass(frozen=True)
class ProbeScore:
    narrows_target_span: bool
    avoids_no_op: bool
    reduces_retry: bool
    improves_syntax_valid: bool
    is_default_tie_break: bool

    @property
    def positive(self) -> bool:
        if self.is_default_tie_break:
            return False
        return any([
            self.narrows_target_span,
            self.avoids_no_op,
            self.reduces_retry,
            self.improves_syntax_valid,
        ])

    @property
    def score(self) -> int:
        return sum([
            self.narrows_target_span,
            self.avoids_no_op,
            self.reduces_retry,
            self.improves_syntax_valid,
        ])


def score_strategy(
    candidate_id: str,
    strategy_id: str,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    default_tie_break: bool = False,
) -> ProbeScore:
    """Score a strategy candidate against a baseline run."""
    baseline_span = int(baseline.get("target_span_lines", 0))
    candidate_span = int(candidate.get("target_span_lines", 0))
    narrows = candidate_span < baseline_span if baseline_span > 0 else False

    baseline_noop = bool(baseline.get("no_op_patch", False))
    candidate_noop = bool(candidate.get("no_op_patch", False))
    avoids_noop = not candidate_noop and baseline_noop

    baseline_retries = int(baseline.get("retry_count", 0))
    candidate_retries = int(candidate.get("retry_count", 0))
    reduces = candidate_retries < baseline_retries

    baseline_syntax = bool(baseline.get("syntax_pass", False))
    candidate_syntax = bool(candidate.get("syntax_pass", False))
    improves_syntax = candidate_syntax and not baseline_syntax

    return ProbeScore(
        narrows_target_span=narrows,
        avoids_no_op=avoids_noop,
        reduces_retry=reduces,
        improves_syntax_valid=improves_syntax,
        is_default_tie_break=default_tie_break,
    )


@dataclass(frozen=True)
class StrategyRanking:
    candidate_id: str
    rankings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_non_tie_break(self) -> bool:
        return any(r["positive"] for r in self.rankings)


def rank_strategies(
    candidate_id: str,
    strategies: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, Any],
) -> StrategyRanking:
    """Rank multiple strategies for a candidate, flagging default tie-breaks."""
    scores = []
    for s in strategies:
        sid = s.get("strategy_id", "")
        probe = score_strategy(
            candidate_id=candidate_id,
            strategy_id=sid,
            baseline=baseline,
            candidate=s,
        )
        scores.append({
            "strategy_id": sid,
            "score": probe.score,
            "positive": probe.positive,
            "is_default_tie_break": probe.is_default_tie_break,
            "details": {
                "narrows_target_span": probe.narrows_target_span,
                "avoids_no_op": probe.avoids_no_op,
                "reduces_retry": probe.reduces_retry,
                "improves_syntax_valid": probe.improves_syntax_valid,
            },
        })

    scores.sort(key=lambda x: x["score"], reverse=True)

    if scores and scores[0]["score"] == scores[-1]["score"] and len(scores) > 1:
        for s in scores:
            s["is_default_tie_break"] = True
            s["positive"] = False

    return StrategyRanking(candidate_id=candidate_id, rankings=scores)
