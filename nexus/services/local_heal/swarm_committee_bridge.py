"""C6AI: SwarmCommitteeBridge — multi-worktree committee execution.

Combines Swarm (multi-worktree parallelism) with Committee (multi-model Borda voting).
Each worktree runs a different model, results are combined via Borda voting.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorktreeResult:
    """Result from a single worktree execution."""
    worktree_id: str
    model: str
    patch_text: str
    verifier_result: str = ""
    confidence: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def patch_hash(self) -> str:
        return hashlib.sha256(self.patch_text.encode()).hexdigest()[:16] if self.patch_text else ""

    @property
    def succeeded(self) -> bool:
        return bool(self.patch_text and not self.error)


@dataclass
class SwarmCommitteeResult:
    """Result from swarm committee execution."""
    winner: WorktreeResult | None
    all_results: list[WorktreeResult]
    borda_scores: dict[str, float]
    total_worktrees: int
    successful_worktrees: int


class SwarmCommitteeBridge:
    """Bridge between Swarm multi-worktree execution and Committee Borda voting.
    
    Usage:
        bridge = SwarmCommitteeBridge()
        results = bridge.execute(worktrees, proposer_specs)
        winner = bridge.select_winner(results)
    """

    def __init__(self):
        self._worktree_results: list[WorktreeResult] = []

    def add_worktree_result(self, result: WorktreeResult) -> None:
        """Add a worktree result."""
        self._worktree_results.append(result)

    def clear(self) -> None:
        """Clear all worktree results."""
        self._worktree_results.clear()

    def borda_vote(self, results: list[WorktreeResult] | None = None) -> dict[str, float]:
        """Compute Borda scores from worktree results.
        
        Scoring:
        - verifier_result=pass: 3 points
        - patch present + no error: 2 points
        - confidence score: 0-1 points
        """
        if results is None:
            results = self._worktree_results
        
        scores: dict[str, float] = {}
        n = len(results)
        if n == 0:
            return scores

        for result in results:
            score = 0.0
            if result.verifier_result == "pass":
                score += 3.0
            elif result.succeeded:
                score += 2.0
            score += result.confidence
            scores[result.worktree_id] = score

        return scores

    def select_winner(self, results: list[WorktreeResult] | None = None) -> WorktreeResult | None:
        """Select winner using Borda voting."""
        if results is None:
            results = self._worktree_results
        
        if not results:
            return None

        scores = self.borda_vote(results)
        if not scores:
            return None

        winner_id = max(scores, key=scores.get)
        for result in results:
            if result.worktree_id == winner_id:
                return result
        return None

    def build_swarm_committee_result(self, results: list[WorktreeResult] | None = None) -> SwarmCommitteeResult:
        """Build a SwarmCommitteeResult from worktree results."""
        if results is None:
            results = self._worktree_results
        
        scores = self.borda_vote(results)
        winner = self.select_winner(results)
        successful = sum(1 for r in results if r.succeeded)

        return SwarmCommitteeResult(
            winner=winner,
            all_results=results,
            borda_scores=scores,
            total_worktrees=len(results),
            successful_worktrees=successful,
        )
