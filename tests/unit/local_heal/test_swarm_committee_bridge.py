"""C6AI: SwarmCommitteeBridge tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.swarm_committee_bridge import (
    SwarmCommitteeBridge,
    WorktreeResult,
    SwarmCommitteeResult,
)


def test_worktree_result_patch_hash():
    """WorktreeResult computes patch_hash from patch_text."""
    result = WorktreeResult(worktree_id="w1", model="qwen", patch_text="def fix(): pass")
    assert len(result.patch_hash) == 16


def test_worktree_result_succeeded():
    """WorktreeResult.succeeded is True when patch present and no error."""
    result = WorktreeResult(worktree_id="w1", model="qwen", patch_text="def fix(): pass")
    assert result.succeeded is True


def test_worktree_result_failed_on_error():
    """WorktreeResult.succeeded is False when error present."""
    result = WorktreeResult(worktree_id="w1", model="qwen", patch_text="def fix(): pass", error="timeout")
    assert result.succeeded is False


def test_worktree_result_failed_on_empty_patch():
    """WorktreeResult.succeeded is False when patch is empty."""
    result = WorktreeResult(worktree_id="w1", model="qwen", patch_text="")
    assert result.succeeded is False


def test_swarm_committee_bridge_borda_vote():
    """SwarmCommitteeBridge.borda_vote computes scores correctly."""
    bridge = SwarmCommitteeBridge()
    r1 = WorktreeResult(worktree_id="w1", model="qwen", patch_text="patch1", verifier_result="pass", confidence=0.9)
    r2 = WorktreeResult(worktree_id="w2", model="deepseek", patch_text="patch2", verifier_result="fail", confidence=0.7)
    bridge.add_worktree_result(r1)
    bridge.add_worktree_result(r2)

    scores = bridge.borda_vote()
    assert scores["w1"] > scores["w2"]  # pass wins over fail


def test_swarm_committee_bridge_select_winner():
    """SwarmCommitteeBridge.select_winner returns highest-scored result."""
    bridge = SwarmCommitteeBridge()
    r1 = WorktreeResult(worktree_id="w1", model="qwen", patch_text="patch1", verifier_result="pass")
    r2 = WorktreeResult(worktree_id="w2", model="deepseek", patch_text="patch2", verifier_result="fail")
    bridge.add_worktree_result(r1)
    bridge.add_worktree_result(r2)

    winner = bridge.select_winner()
    assert winner is not None
    assert winner.worktree_id == "w1"


def test_swarm_committee_bridge_empty():
    """SwarmCommitteeBridge returns None when no results."""
    bridge = SwarmCommitteeBridge()
    assert bridge.select_winner() is None
    assert bridge.borda_vote() == {}


def test_swarm_committee_bridge_clear():
    """SwarmCommitteeBridge.clear removes all results."""
    bridge = SwarmCommitteeBridge()
    bridge.add_worktree_result(WorktreeResult(worktree_id="w1", model="qwen", patch_text="patch"))
    assert len(bridge._worktree_results) == 1
    bridge.clear()
    assert len(bridge._worktree_results) == 0


def test_swarm_committee_result():
    """SwarmCommitteeResult builds from worktree results."""
    bridge = SwarmCommitteeBridge()
    r1 = WorktreeResult(worktree_id="w1", model="qwen", patch_text="patch1", verifier_result="pass")
    r2 = WorktreeResult(worktree_id="w2", model="deepseek", patch_text="patch2", verifier_result="fail")
    bridge.add_worktree_result(r1)
    bridge.add_worktree_result(r2)

    result = bridge.build_swarm_committee_result()
    assert result.total_worktrees == 2
    assert result.successful_worktrees == 2
    assert result.winner is not None
    assert result.winner.worktree_id == "w1"


def test_borda_vote_verifier_pass_wins():
    """Borda vote: verifier_result=pass always wins."""
    bridge = SwarmCommitteeBridge()
    r1 = WorktreeResult(worktree_id="w1", model="qwen", patch_text="patch1", verifier_result="pass", confidence=0.5)
    r2 = WorktreeResult(worktree_id="w2", model="deepseek", patch_text="patch2", verifier_result="fail", confidence=0.99)
    bridge.add_worktree_result(r1)
    bridge.add_worktree_result(r2)

    winner = bridge.select_winner()
    assert winner.worktree_id == "w1"  # pass wins even with lower confidence
