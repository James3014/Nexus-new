"""Deterministic strategy tournament / ranking."""

from typing import List


class StrategyTournament:
    """Deterministic ranking of strategy candidates."""

    def rank(self, candidates: List[dict], probes: List[dict]) -> dict:
        """Rank candidates by probe score. Return winner."""
        scored = []
        for c, p in zip(candidates, probes):
            scored.append({
                "strategy_type": c["strategy_type"],
                "strategy_id": c["envelope"].strategy_id,
                "probe_score": p["probe"]["probe_score"],
            })

        scored.sort(key=lambda x: -x["probe_score"])

        winner = scored[0]
        return {
            "selected_strategy_id": winner["strategy_id"],
            "selected_strategy_type": winner["strategy_type"],
            "selected_probe_score": winner["probe_score"],
            "ranking_method": "deterministic_borda",
            "candidate_rankings": scored,
            "non_winner_ids": [s["strategy_id"] for s in scored[1:]],
        }
