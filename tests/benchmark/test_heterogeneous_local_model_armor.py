from __future__ import annotations

from nexus.services.local_heal.heterogeneous_candidate_provider import (
    HeterogeneousCandidateProvider,
)
from nexus.services.local_heal.judge_selector import JudgeSelector
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)


def test_local_portfolio_diagnostic_deterministic():
    """Deterministic test: local portfolio with heterogeneous candidates."""
    # Generate candidates
    provider = HeterogeneousCandidateProvider(
        primary_model="qwen2.5-coder:7b-instruct",
        secondary_model="deepseek-coder:6.7b-instruct",
        judge_model="qwen2.5-s2t-advisor:3b",
    )
    candidates = provider.generate_candidates(
        task_id="local-portfolio-1",
        problem_statement="fix code",
        target_file="a.py",
        target_symbol="f",
        locked_search="def f(): pass",
        evidence_refs=("ref1",),
        disagreement_detected=False,
    )

    # Judge selects
    selector = JudgeSelector(judge_model="qwen2.5-s2t-advisor:3b")
    receipt = selector.select(candidates)
    assert receipt.judge_invoked is True
    assert receipt.judge_cannot_verify is True
    assert receipt.selected_candidate_id != ""

    # Run through executor in dry_run
    req = LocalModelExecutorRequest(
        task_id="local-portfolio-1",
        problem_statement="fix code",
        repo_root="/ws",
        target_file="a.py",
        selected_capabilities=("local_model_executor", "repair_loop", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"),
        evidence_refs=("ref1",),
        dry_run=True,
        execution_topology="local_committee_only",
        route_context={"signal_snapshot": {"execution_topology": "local_committee_only"}},
    )
    resp = LocalModelExecutor.run(req)
    assert resp.invoked is False  # dry_run


def test_local_portfolio_disagreement_triggers_secondary():
    """Disagreement triggers secondary proposer."""
    provider = HeterogeneousCandidateProvider(
        primary_model="qwen2.5-coder:7b-instruct",
        secondary_model="deepseek-coder:6.7b-instruct",
        judge_model="qwen2.5-s2t-advisor:3b",
    )
    candidates = provider.generate_candidates(
        task_id="local-portfolio-2",
        problem_statement="fix code",
        target_file="a.py",
        target_symbol="f",
        locked_search="def f(): pass",
        evidence_refs=("ref1",),
        disagreement_detected=True,
    )
    assert len(candidates) == 2
    roles = [c.role for c in candidates]
    assert "primary_proposer" in roles
    assert "secondary_proposer" in roles


def test_local_portfolio_no_secondary_without_trigger():
    """No secondary without disagreement/uncertainty."""
    provider = HeterogeneousCandidateProvider(
        primary_model="qwen2.5-coder:7b-instruct",
        secondary_model="deepseek-coder:6.7b-instruct",
        judge_model="qwen2.5-s2t-advisor:3b",
    )
    candidates = provider.generate_candidates(
        task_id="local-portfolio-3",
        problem_statement="fix code",
        target_file="a.py",
        target_symbol="f",
        locked_search="def f(): pass",
        evidence_refs=("ref1",),
    )
    assert len(candidates) == 1
    assert candidates[0].role == "primary_proposer"


def test_judge_cannot_verify():
    """Judge selection receipt has judge_cannot_verify=True."""
    selector = JudgeSelector(judge_model="qwen2.5-s2t-advisor:3b")
    from nexus.services.local_heal.heterogeneous_candidate_provider import HeterogeneousCandidate
    candidates = [HeterogeneousCandidate(
        candidate_id="c1", model_name="qwen2.5-coder:7b", role="primary_proposer",
        candidate_patch_hash="h", source_anchor_hash="s", evidence_refs=("r",),
    )]
    receipt = selector.select(candidates)
    assert receipt.judge_cannot_verify is True
    assert receipt.selected_candidate_id == "c1"
