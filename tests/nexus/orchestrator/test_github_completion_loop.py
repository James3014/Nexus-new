import inspect
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.contracts.github_orchestration import (
    CandidateBlobEquivalence,
    CheckResult,
    GitHubOrchestrationEvidence,
    IntegrationBinding,
    MainMovementEvidence,
    ReviewResult,
    canonical_hash,
    compute_candidate_equivalence_proof_hash,
)
from nexus.orchestrator.github_completion_loop import (
    DEFAULT_MAX_INTEGRATION_GENERATIONS,
    MAX_COMPLETION_ELAPSED_SECONDS,
    MAX_INTEGRATION_GENERATIONS,
    CasMergeResult,
    CasMergeStatus,
    CompletionLoopOutcome,
    DimensionRevalidationReceipt,
    FinalMergeFields,
    IntegrationMaterializationResult,
    PostMergeReconciliationResult,
    _validate_reconciliation_facts,
    make_dimension_revalidation_receipt,
    run_github_completion_loop,
)
from nexus.orchestrator.github_orchestration import evaluate_action
from tests.contracts.test_github_orchestration import evidence
from tests.nexus.orchestrator.test_github_orchestration import (
    _make_requalify_git_repo,
    context,
    request,
)


class SpyGitHubCompletionPort:
    """Deterministic fake and spy for testing GitHub completion loop with full physical observations."""

    def __init__(
        self,
        *,
        main_states: list[tuple[str, str]],
        pr_heads: list[str] | None = None,
        default_pr_head: str = "b" * 40,
        tree_shas: dict[str, str] | None = None,
        blob_shas: dict[tuple[str, str], str] | None = None,
        default_blob_sha: str = "1" * 40,
        changed_main_paths_map: dict[tuple[str, str], tuple[str, ...]] | None = None,
        default_changed_paths: tuple[str, ...] = ("docs/unrelated.md",),
        revalidation_receipts: dict[str, DimensionRevalidationReceipt | Any] | None = None,
        materialization_results: list[IntegrationMaterializationResult] | None = None,
        check_results_map: dict[tuple[str, int], Sequence[CheckResult]] | None = None,
        reviews: Sequence[ReviewResult] = (ReviewResult(reviewer="reviewer", state="APPROVED"),),
        is_platform_approval: bool = False,
        cas_merge_results: list[CasMergeResult] | None = None,
        post_merge_results: list[PostMergeReconciliationResult] | None = None,
        final_merge_fields: FinalMergeFields | list[FinalMergeFields] | Any = None,
        issue_states: Mapping[int, str] | None = None,
    ):
        self.main_states = list(main_states)
        self.pr_heads = list(pr_heads) if pr_heads is not None else None
        self.current_pr_head = default_pr_head
        self.tree_shas = tree_shas or {}
        self.blob_shas = blob_shas or {}
        self.default_blob_sha = default_blob_sha
        self.changed_main_paths_map = changed_main_paths_map or {}
        self.default_changed_paths = default_changed_paths
        self.revalidation_receipts = revalidation_receipts or {}
        self.materialization_results = (
            list(materialization_results) if materialization_results is not None else []
        )
        self.check_results_map = check_results_map or {}
        self.reviews = tuple(reviews)
        self.is_platform_approval = is_platform_approval
        self.cas_merge_results = (
            list(cas_merge_results)
            if cas_merge_results is not None
            else [CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40)]
        )
        self.post_merge_results = list(post_merge_results) if post_merge_results is not None else []
        self.final_merge_fields = final_merge_fields
        self.issue_states = (
            dict(issue_states)
            if (issue_states is not None and not callable(issue_states))
            else issue_states
        )

        # Spies
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.read_blob_calls: list[tuple[str, str]] = []
        self.revalidation_calls: list[str] = []
        self.materialize_calls: list[dict[str, Any]] = []
        self.checks_calls: list[dict[str, Any]] = []
        self.cas_merge_calls: list[dict[str, Any]] = []
        self.reconcile_calls: list[dict[str, Any]] = []
        self.read_final_merge_fields_calls: list[dict[str, Any]] = []
        self.read_issue_states_calls: list[dict[str, Any]] = []

    def read_main_state(self) -> tuple[str, str]:
        state = self.main_states[0] if len(self.main_states) == 1 else self.main_states.pop(0)
        self.calls.append(("read_main_state", {"result": state}))
        return state

    def get_tree_sha(self, commit_sha: str) -> str:
        if commit_sha in self.tree_shas:
            res = self.tree_shas[commit_sha]
        elif commit_sha.startswith("0"):
            res = commit_sha
        elif commit_sha.startswith("d"):
            res = "1" * 40
        elif commit_sha.startswith("e"):
            res = "2" * 40
        elif commit_sha.startswith("f"):
            res = "3" * 40
        elif commit_sha.startswith("8"):
            res = "4" * 40
        elif commit_sha.startswith("9"):
            res = "5" * 40
        else:
            res = "1" * 40
        self.calls.append(("get_tree_sha", {"commit_sha": commit_sha, "result": res}))
        return res

    def read_pr_head_sha(self) -> str:
        if self.pr_heads:
            res = self.pr_heads[0] if len(self.pr_heads) == 1 else self.pr_heads.pop(0)
        else:
            res = self.current_pr_head
        self.calls.append(("read_pr_head_sha", {"result": res}))
        return res

    def read_blob_sha(self, commit_or_tree_sha: str, path: str) -> str:
        self.read_blob_calls.append((commit_or_tree_sha, path))
        res = self.blob_shas.get((commit_or_tree_sha, path), self.default_blob_sha)
        self.calls.append(
            (
                "read_blob_sha",
                {"commit_or_tree": commit_or_tree_sha, "path": path, "result": res},
            )
        )
        return res

    def get_changed_main_paths(self, old_main_sha: str, new_main_sha: str) -> tuple[str, ...]:
        res = self.changed_main_paths_map.get(
            (old_main_sha, new_main_sha), self.default_changed_paths
        )
        self.calls.append(
            (
                "get_changed_main_paths",
                {"old": old_main_sha, "new": new_main_sha, "result": res},
            )
        )
        return res

    def revalidate_affected_dimension(
        self,
        dimension: str,
        *,
        evidence: GitHubOrchestrationEvidence,
        movement: MainMovementEvidence,
        generation: int,
    ) -> DimensionRevalidationReceipt:
        self.revalidation_calls.append(dimension)
        if dimension in self.revalidation_receipts:
            res = self.revalidation_receipts[dimension]
        else:
            res = make_dimension_revalidation_receipt(
                dimension=dimension,
                generation=generation,
                old_main_sha=movement.old_main_sha,
                new_main_sha=movement.new_main_sha,
                source_candidate_commit_sha=movement.candidate_head_sha,
                source_candidate_tree_sha=movement.candidate_tree_sha,
                passed=True,
            )
        self.calls.append(
            (
                "revalidate_affected_dimension",
                {"dimension": dimension, "generation": generation, "result": res},
            )
        )
        return res

    def materialize_integration_head(
        self,
        *,
        base_sha: str,
        base_tree_sha: str,
        expected_pr_head_sha: str,
        candidate_tree_sha: str,
        generation: int,
    ) -> IntegrationMaterializationResult:
        call_info = {
            "base_sha": base_sha,
            "base_tree_sha": base_tree_sha,
            "expected_pr_head_sha": expected_pr_head_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "generation": generation,
        }
        self.materialize_calls.append(call_info)
        if self.materialization_results:
            res = self.materialization_results.pop(0)
        else:
            int_head = f"{generation:02x}" * 20
            int_tree = f"{generation:02x}" * 20
            res = IntegrationMaterializationResult(
                success=True,
                integration_head_sha=int_head,
                integration_tree_sha=int_tree,
            )
        if res.success and res.integration_head_sha:
            self.current_pr_head = res.integration_head_sha
        self.calls.append(("materialize_integration_head", {"result": res}))
        return res

    def read_required_checks(
        self,
        *,
        head_sha: str,
        generation: int,
        timeout_seconds: float | None = None,
    ) -> Sequence[CheckResult]:
        call_info = {
            "head_sha": head_sha,
            "generation": generation,
            "timeout_seconds": timeout_seconds,
        }
        self.checks_calls.append(call_info)
        if (head_sha, generation) in self.check_results_map:
            res = self.check_results_map[(head_sha, generation)]
        else:
            res = (
                CheckResult(
                    name="ci",
                    status="completed",
                    conclusion="success",
                    head_sha=head_sha,
                    generation=generation,
                ),
            )
        self.calls.append(("read_required_checks", {"result": res}))
        return res

    def read_reviews(self) -> Sequence[ReviewResult]:
        self.calls.append(("read_reviews", {"result": self.reviews}))
        return self.reviews

    def is_platform_approval_required(
        self,
        *,
        repository: str,
        pull_request_number: int,
    ) -> bool:
        self.calls.append(
            (
                "is_platform_approval_required",
                {"repository": repository, "pr": pull_request_number},
            )
        )
        return self.is_platform_approval

    def cas_merge(
        self,
        *,
        repository: str,
        pull_request_number: int,
        expected_base_sha: str,
        expected_head_sha: str,
    ) -> CasMergeResult:
        call_info = {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "expected_base_sha": expected_base_sha,
            "expected_head_sha": expected_head_sha,
        }
        self.cas_merge_calls.append(call_info)
        res = (
            self.cas_merge_results.pop(0)
            if self.cas_merge_results
            else CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40)
        )
        self.calls.append(("cas_merge", {"input": call_info, "result": res}))
        return res

    def reconcile_post_merge(
        self,
        *,
        repository: str,
        pull_request_number: int,
        expected_base_sha: str,
        expected_head_sha: str,
    ) -> PostMergeReconciliationResult:
        call_info = {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "expected_base_sha": expected_base_sha,
            "expected_head_sha": expected_head_sha,
        }
        self.reconcile_calls.append(call_info)
        if self.post_merge_results:
            res = self.post_merge_results.pop(0)
        else:
            if "observed_main_tree" in self.tree_shas:
                def_tree_sha = self.tree_shas["observed_main_tree"]
            elif self.materialize_calls:
                gen = self.materialize_calls[-1]["generation"]
                def_tree_sha = f"{gen:02x}" * 20
            else:
                def_tree_sha = "c" * 40
            res = PostMergeReconciliationResult(
                observed_main_commit_sha="a" * 40,
                observed_main_tree_sha=def_tree_sha,
                observed_parent_shas=(expected_base_sha, expected_head_sha),
            )
        self.calls.append(("reconcile_post_merge", {"input": call_info, "result": res}))
        return res

    def read_final_merge_fields(
        self,
        *,
        repository: str,
        pull_request_number: int,
    ) -> FinalMergeFields:
        call_info = {"repository": repository, "pull_request_number": pull_request_number}
        self.read_final_merge_fields_calls.append(call_info)
        if callable(self.final_merge_fields):
            res = self.final_merge_fields(
                repository=repository, pull_request_number=pull_request_number
            )
        elif isinstance(self.final_merge_fields, list):
            res = self.final_merge_fields.pop(0)
        elif self.final_merge_fields is not None:
            res = self.final_merge_fields
        else:
            res = FinalMergeFields(
                pr_number=pull_request_number,
                head_sha=self.current_pr_head,
                base_sha=None,
                merge_method="squash",
                pr_body="<!-- NEXUS_ISSUE_INTENT_V1\n[]\nNEXUS_ISSUE_INTENT_V1 -->",
                commit_title=None,
                commit_message=None,
            )
        self.calls.append(("read_final_merge_fields", {"input": call_info, "result": res}))
        return res

    def read_issue_states(
        self,
        *,
        repository: str,
        issue_numbers: tuple[int, ...],
    ) -> Mapping[int, str]:
        call_info = {"repository": repository, "issue_numbers": issue_numbers}
        self.read_issue_states_calls.append(call_info)
        if callable(self.issue_states):
            res = self.issue_states(repository=repository, issue_numbers=issue_numbers)
        elif self.issue_states is not None:
            res = {num: self.issue_states.get(num, "") for num in issue_numbers}
        else:
            res = {num: "open" for num in issue_numbers}
        self.calls.append(("read_issue_states", {"input": call_info, "result": res}))
        return res


def _base_evidence(**overrides):
    return evidence(**overrides)


def _base_request(ctx=None):
    c = ctx or context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    return request(c, action=AutonomyActionClass.GITHUB_MERGE)


# ==============================================================================
# Residual Defect 1: Hostile Reconciliation Tree Verification
# ==============================================================================


def test_residual1_direct_reconciliation_validator_rejects_wrong_tree():
    """Residual 1: _validate_reconciliation_facts MUST reject wrong tree SHA."""
    expected_base = "e" * 40
    expected_head = "01" * 20
    expected_tree = "01" * 20
    wrong_tree = "09" * 20
    merged_sha = "a" * 40

    recon_wrong_tree = PostMergeReconciliationResult(
        observed_main_commit_sha=merged_sha,
        observed_main_tree_sha=wrong_tree,
        observed_parent_shas=(expected_base, expected_head),
    )

    valid, err = _validate_reconciliation_facts(
        recon_wrong_tree,
        expected_base_sha=expected_base,
        expected_head_sha=expected_head,
        expected_integration_tree_sha=expected_tree,
        cas_merged_sha=merged_sha,
    )
    assert not valid
    assert "RECONCILIATION_TREE_SHA_MISMATCH" in str(err)

    # Valid tree passes
    recon_valid = PostMergeReconciliationResult(
        observed_main_commit_sha=merged_sha,
        observed_main_tree_sha=expected_tree,
        observed_parent_shas=(expected_base, expected_head),
    )
    valid_ok, err_ok = _validate_reconciliation_facts(
        recon_valid,
        expected_base_sha=expected_base,
        expected_head_sha=expected_head,
        expected_integration_tree_sha=expected_tree,
        cas_merged_sha=merged_sha,
    )
    assert valid_ok
    assert err_ok is None


def test_residual1_cas_success_with_wrong_tree_blocks(monkeypatch):
    """Residual 1: Hostile probe where CAS SUCCESS has wrong reconciliation tree -> BLOCKED."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40)],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="a" * 40,
                observed_main_tree_sha="09" * 20,  # Wrong tree!
                observed_parent_shas=(new_main_sha, "01" * 20),
            )
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "POST_MERGE_RECONCILIATION_FAILED:RECONCILIATION_TREE_SHA_MISMATCH" in result.reason


def test_residual1_ambiguous_ack_with_wrong_tree_blocks(monkeypatch):
    """Residual 1: Hostile probe where AMBIGUOUS_ACK has wrong reconciliation tree -> BLOCKED."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="a" * 40,
                observed_main_tree_sha="09" * 20,  # Wrong tree!
                observed_parent_shas=(new_main_sha, "01" * 20),
            )
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "AMBIGUOUS_MERGE_RECONCILIATION_FAILED:RECONCILIATION_TREE_SHA_MISMATCH" in result.reason


# ==============================================================================
# Residual Defect 2: Hard Maxima on Budgets
# ==============================================================================


def test_residual2_budget_exceeding_hard_maxima_fails_closed_before_port_calls():
    """Residual 2: Budget widening (max_generations > 10 or max_elapsed > 2700) fails closed before any port calls."""
    assert MAX_INTEGRATION_GENERATIONS == 10
    assert DEFAULT_MAX_INTEGRATION_GENERATIONS == 5
    assert MAX_COMPLETION_ELAPSED_SECONDS == 2700.0

    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    req = _base_request()
    port = SpyGitHubCompletionPort(main_states=[("e" * 40, "2" * 40)])

    # Widened generations budget (e.g. 11, 999)
    res_gen11 = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=11,
    )
    assert res_gen11.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_GENERATION_BUDGET:11" in res_gen11.reason
    assert len(port.calls) == 0  # Zero port calls!

    res_gen999 = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=999,
    )
    assert res_gen999.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_GENERATION_BUDGET:999" in res_gen999.reason
    assert len(port.calls) == 0

    # Invalid generations budget <= 0
    res_gen0 = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=0,
    )
    assert res_gen0.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_GENERATION_BUDGET:0" in res_gen0.reason
    assert len(port.calls) == 0

    # Widened elapsed seconds budget (> 2700)
    res_time_wide = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_elapsed_seconds=2701.0,
    )
    assert res_time_wide.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_TIME_BUDGET:2701.0" in res_time_wide.reason
    assert len(port.calls) == 0

    # Invalid elapsed seconds <= 0
    res_time_zero = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_elapsed_seconds=0.0,
    )
    assert res_time_zero.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_TIME_BUDGET:0.0" in res_time_zero.reason
    assert len(port.calls) == 0


def test_residual2_stricter_budgets_are_accepted_and_honored(monkeypatch):
    """Residual 2: Stricter / smaller budgets (e.g. max_generations=1, max_elapsed=60.0) are allowed."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    req = _base_request()

    # Budget of 1 generation on main movement when main moves twice -> DEFERRED_CONCURRENCY at gen 1
    m1_sha = "e" * 40
    m2_sha = "f" * 40
    tree = "1" * 40
    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, tree),
            (m2_sha, tree),
            (m2_sha, tree),
        ],
        default_pr_head="b" * 40,
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    res = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=1,
        max_elapsed_seconds=60.0,
    )
    assert res.outcome is CompletionLoopOutcome.DEFERRED_CONCURRENCY
    assert "GENERATION_BUDGET_EXHAUSTED" in res.reason
    assert res.generation == 1


# ==============================================================================
# Residual Defect 3: Exact Lowercase 40-hex Git Identity vs 64-hex Receipt Hash
# ==============================================================================


def test_residual3_git_identity_rejects_uppercase_and_64hex():
    """Residual 3: Models reject uppercase or 64-hex where a Git SHA belongs; receipt_hash accepts lowercase 64-hex."""
    # 1. PostMergeReconciliationResult
    with pytest.raises(ValueError):
        # Uppercase in commit sha
        PostMergeReconciliationResult(
            observed_main_commit_sha="A" * 40,
            observed_main_tree_sha="0" * 40,
            observed_parent_shas=("e" * 40, "01" * 20),
        )

    with pytest.raises(ValueError):
        # 64-hex in commit sha
        PostMergeReconciliationResult(
            observed_main_commit_sha="a" * 64,
            observed_main_tree_sha="0" * 40,
            observed_parent_shas=("e" * 40, "01" * 20),
        )

    with pytest.raises(ValueError):
        # Uppercase in parent sha
        PostMergeReconciliationResult(
            observed_main_commit_sha="a" * 40,
            observed_main_tree_sha="0" * 40,
            observed_parent_shas=("E" * 40, "01" * 20),
        )

    # 2. IntegrationMaterializationResult
    with pytest.raises(ValueError):
        IntegrationMaterializationResult(
            success=True,
            integration_head_sha="A" * 40,
            integration_tree_sha="0" * 40,
        )

    with pytest.raises(ValueError):
        IntegrationMaterializationResult(
            success=True,
            integration_head_sha="a" * 64,
            integration_tree_sha="0" * 40,
        )

    # 3. DimensionRevalidationReceipt: Git SHAs must be 40-hex lowercase; receipt_hash must be 64-hex lowercase
    with pytest.raises(ValueError):
        # Uppercase old_main_sha
        make_dimension_revalidation_receipt(
            dimension="TEST",
            generation=1,
            old_main_sha="D" * 40,
            new_main_sha="e" * 40,
            source_candidate_commit_sha="b" * 40,
            source_candidate_tree_sha="c" * 40,
            passed=True,
        )

    with pytest.raises(ValueError):
        # 64-hex old_main_sha
        make_dimension_revalidation_receipt(
            dimension="TEST",
            generation=1,
            old_main_sha="d" * 64,
            new_main_sha="e" * 40,
            source_candidate_commit_sha="b" * 40,
            source_candidate_tree_sha="c" * 40,
            passed=True,
        )

    # Valid receipt has 64-hex receipt_hash and 40-hex Git fields
    receipt = make_dimension_revalidation_receipt(
        dimension="TEST",
        generation=1,
        old_main_sha="d" * 40,
        new_main_sha="e" * 40,
        source_candidate_commit_sha="b" * 40,
        source_candidate_tree_sha="c" * 40,
        passed=True,
    )
    assert len(receipt.receipt_hash) == 64
    assert len(receipt.old_main_sha) == 40
    assert receipt.receipt_hash.islower()


def test_residual3_caller_rejects_uppercase_or_64hex_blob_shas(monkeypatch):
    """Residual 3: read_blob_sha returning uppercase 40 or lowercase 64 blocks before merge."""
    initial_ev = _base_evidence(
        base_sha="d" * 40, current_main_sha="d" * 40, changed_paths=("nexus/a.py",)
    )
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    req = _base_request()

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    # Sub-case 1: Uppercase 40-hex blob SHA from port -> BLOCKED
    port_upper_blob = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        blob_shas={
            ("b" * 40, "nexus/a.py"): "A" * 40,  # Uppercase!
            ("01" * 20, "nexus/a.py"): "A" * 40,
        },
    )
    res_upper = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_upper_blob
    )
    assert res_upper.outcome is CompletionLoopOutcome.BLOCKED
    assert "BLOB_SHA_MALFORMED:nexus/a.py" in res_upper.reason

    # Sub-case 2: 64-hex blob SHA from port -> BLOCKED
    port_64_blob = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        blob_shas={
            ("b" * 40, "nexus/a.py"): "1" * 64,  # 64-hex!
            ("01" * 20, "nexus/a.py"): "1" * 64,
        },
    )
    res_64 = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_64_blob)
    assert res_64.outcome is CompletionLoopOutcome.BLOCKED
    assert "BLOB_SHA_MALFORMED:nexus/a.py" in res_64.reason


# ==============================================================================
# Preserved Core & Adversarial Test Matrix (A through T)
# ==============================================================================


def test_api_surface_has_no_auth_resolver_parameter():
    """Defect 5: Public run_github_completion_loop must NOT accept auth_resolver parameter."""
    sig = inspect.signature(run_github_completion_loop)
    assert "auth_resolver" not in sig.parameters


def test_a_unrelated_docs_drift_reuses_unaffected_and_merges_without_owner(monkeypatch):
    """A. unrelated docs drift -> requalifier used; unaffected semantic evidence not rerun; fresh integration generation/checks required; zero Owner gate."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 1
    assert "SEMANTIC_OVERLAP" not in port.revalidation_calls
    assert len(port.cas_merge_calls) == 1
    assert port.cas_merge_calls[0]["expected_base_sha"] == new_main_sha
    assert port.cas_merge_calls[0]["expected_head_sha"] == "01" * 20


def test_b_test_dependency_drift_calls_only_test_impact_hook(monkeypatch):
    """B. test/dependency drift -> only TEST_IMPACT revalidation hook called with typed receipt."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("tests/unit/test_unrelated.py",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "TEST_ONLY",
                "unmatched_paths": [],
                "changed_paths": ["tests/unit/test_unrelated.py"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert port.revalidation_calls == ["TEST_IMPACT"]


def test_c_transport_drift_calls_only_transport_hook(monkeypatch):
    """C. workflow/provider/MCP drift -> only affected transport/authority dimensions revalidated."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("nexus/providers/transport_example.py",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "CORE_RUNTIME",
                "unmatched_paths": [],
                "changed_paths": ["nexus/providers/transport_example.py"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert port.revalidation_calls == ["TRANSPORT_DRIFT"]


def test_d_semantic_overlap_revalidation_receipt_and_blob_proof(monkeypatch):
    """D & Defect 3: Semantic overlap requires typed receipt and caller blob proof; bare True or fresh acceptance need fails closed."""
    initial_ev = _base_evidence(
        base_sha="d" * 40, current_main_sha="d" * 40, changed_paths=("nexus/a.py",)
    )
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "CORE_RUNTIME",
                "unmatched_paths": [],
                "changed_paths": ["nexus/a.py"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    # Sub-case 1: Bare bool / invalid receipt returned -> BLOCKED
    port_bare_bool = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        default_changed_paths=("nexus/a.py",),
        revalidation_receipts={"SEMANTIC_OVERLAP": True},  # type: ignore
    )
    res_bare = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_bare_bool
    )
    assert res_bare.outcome is CompletionLoopOutcome.BLOCKED
    assert "INVALID_REVALIDATION_RECEIPT:SEMANTIC_OVERLAP" in res_bare.reason

    # Sub-case 2: Receipt demands fresh candidate acceptance -> BLOCKED
    fresh_req_receipt = make_dimension_revalidation_receipt(
        dimension="SEMANTIC_OVERLAP",
        generation=1,
        old_main_sha="d" * 40,
        new_main_sha=new_main_sha,
        source_candidate_commit_sha="b" * 40,
        source_candidate_tree_sha="c" * 40,
        passed=True,
        requires_fresh_candidate_acceptance=True,
    )
    port_fresh_req = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        default_changed_paths=("nexus/a.py",),
        revalidation_receipts={"SEMANTIC_OVERLAP": fresh_req_receipt},
    )
    res_fresh = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_fresh_req
    )
    assert res_fresh.outcome is CompletionLoopOutcome.BLOCKED
    assert "FRESH_CANDIDATE_ACCEPTANCE_REQUIRED:SEMANTIC_OVERLAP" in res_fresh.reason

    # Sub-case 3: Valid passed receipt + caller verified blob proof -> COMPLETED
    valid_receipt = make_dimension_revalidation_receipt(
        dimension="SEMANTIC_OVERLAP",
        generation=1,
        old_main_sha="d" * 40,
        new_main_sha=new_main_sha,
        source_candidate_commit_sha="b" * 40,
        source_candidate_tree_sha="c" * 40,
        passed=True,
        requires_fresh_candidate_acceptance=False,
    )
    port_ok = SpyGitHubCompletionPort(
        main_states=[
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
            (new_main_sha, new_main_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("nexus/a.py",),
        revalidation_receipts={"SEMANTIC_OVERLAP": valid_receipt},
    )
    res_ok = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_ok)
    assert res_ok.outcome is CompletionLoopOutcome.COMPLETED


def test_e_merge_conflict_blocks_without_checks_or_merge(monkeypatch):
    """E. merge conflict from integration materialization -> BLOCK; no check wait, no merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        materialization_results=[
            IntegrationMaterializationResult(
                success=False,
                conflict=True,
                error="merge conflict in nexus/a.py",
            )
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "INTEGRATION_MATERIALIZATION_FAILED" in result.reason
    assert len(port.checks_calls) == 0
    assert len(port.cas_merge_calls) == 0


def test_f_authority_drift_blocks_immediately(monkeypatch):
    """F. authority/AGENTS/merge-policy drift -> BLOCK/rebind requirement; no merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        default_changed_paths=("AGENTS.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["AGENTS.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUALIFICATION_BLOCKED" in result.reason
    assert len(port.materialize_calls) == 0
    assert len(port.cas_merge_calls) == 0


def test_g_unknown_impact_universe_blocks_before_mutation(monkeypatch):
    """G. malformed/unknown impact -> BLOCK before mutation."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "IMPACT_UNKNOWN",
                "unmatched_paths": ["unknown.txt"],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUALIFICATION_BLOCKED" in result.reason or "IMPACT_UNKNOWN" in result.reason
    assert len(port.materialize_calls) == 0


def test_h_foreign_pr_head_mutation_blocks_without_writing():
    """H. external PR-head mutation / second controller / foreign push -> stale actor does not write or merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40, head_sha="b" * 40)
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[("d" * 40, "1" * 40)],
        pr_heads=["9" * 40],
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "FOREIGN_PR_HEAD_MUTATION" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_i_caller_observes_blob_equivalences_and_rejects_mismatch(monkeypatch):
    """I & Defect 4: Caller directly queries read_blob_sha for source and integration; blob mismatch fails closed."""
    initial_ev = _base_evidence(
        base_sha="d" * 40, current_main_sha="d" * 40, changed_paths=("nexus/a.py",)
    )
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    # Integration alters candidate blob
    port_mismatch = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        blob_shas={
            ("b" * 40, "nexus/a.py"): "1" * 40,
            ("01" * 20, "nexus/a.py"): "2" * 40,  # Changed blob!
        },
    )

    res = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port_mismatch,
    )

    assert res.outcome is CompletionLoopOutcome.BLOCKED
    assert "CANDIDATE_BLOB_SHA_MISMATCH:nexus/a.py" in res.reason
    # Prove exact read_blob_sha calls were made for source and integration
    assert ("b" * 40, "nexus/a.py") in port_mismatch.read_blob_calls
    assert ("01" * 20, "nexus/a.py") in port_mismatch.read_blob_calls
    assert len(port_mismatch.cas_merge_calls) == 0


def test_j_defect1_i2_materializes_from_current_pr_head_i1(monkeypatch):
    """J & Defect 1: I1 materializes with expected_pr_head_sha=C; I2 materializes with expected_pr_head_sha=I1."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    cand_c = "b" * 40
    m1_sha = "e" * 40
    m1_tree = "2" * 40
    m2_sha = "f" * 40
    m2_tree = "3" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head=cand_c,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 2
    assert len(port.materialize_calls) == 2

    # Verify DEFECT 1 fix: I1 received C, I2 received I1!
    i1_sha = "01" * 20
    assert port.materialize_calls[0]["expected_pr_head_sha"] == cand_c
    assert port.materialize_calls[0]["generation"] == 1
    assert port.materialize_calls[1]["expected_pr_head_sha"] == i1_sha
    assert port.materialize_calls[1]["generation"] == 2

    # Verify source Candidate C remains immutable in final evidence
    assert result.evidence.candidate.candidate_commit_sha == cand_c
    assert result.evidence.integration.source_candidate_commit_sha == cand_c
    assert result.evidence.integration.integration_head_sha == "02" * 20


def test_k_stale_i1_check_offered_to_i2_fails_closed(monkeypatch):
    """K. stale I1 check offered to I2 -> BLOCK/fail-closed."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    m1_sha = "e" * 40
    m1_tree = "2" * 40
    m2_sha = "f" * 40
    m2_tree = "3" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    i2_head = "02" * 20
    stale_check = CheckResult(
        name="ci",
        status="completed",
        conclusion="success",
        head_sha=i2_head,
        generation=1,
    )

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
        check_results_map={(i2_head, 2): (stale_check,)},
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "CHECK_GENERATION_MISMATCH" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_l_cas_base_moved_signal_reenters_loop_and_merges_next_generation(monkeypatch):
    """L. main moves immediately before CAS merge -> CAS base-moved signal causes I2/I3 re-entry, not Owner interruption."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    m1_sha = "e" * 40
    m1_tree = "2" * 40
    m2_sha = "f" * 40
    m2_tree = "3" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.BASE_MOVED, reason="main moved to m2"),
            CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40),
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 2
    assert len(port.cas_merge_calls) == 2
    assert port.cas_merge_calls[0]["expected_base_sha"] == m1_sha
    assert port.cas_merge_calls[1]["expected_base_sha"] == m2_sha


def test_m_check_failure_blocks_merge(monkeypatch):
    """M. required check failure/nonterminal -> BLOCK; no merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    class FailingCheckPort(SpyGitHubCompletionPort):
        def read_required_checks(self, *, head_sha, generation, timeout_seconds=None):
            self.checks_calls.append({"head_sha": head_sha, "generation": generation})
            raise ValueError("CHECK_NONTERMINAL_OR_FAILED")

    port = FailingCheckPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUIRED_CHECKS_READ_FAILED" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_n_standing_grant_denial_blocks_merge(monkeypatch):
    """N. standing grant expired/revoked/out-of-scope -> existing durable authorization result blocks; no merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context()  # lacks GITHUB_MERGE
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "MERGE_AUTHORIZATION_DENIED:OUT_OF_SCOPE" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_o_generation_budget_exhausted_returns_deferred_concurrency(monkeypatch):
    """O. generation budget 3 exhausted only by benign churn -> DEFERRED_CONCURRENCY/RETRY_LATER."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    m1_sha = "e" * 40
    m2_sha = "f" * 40
    m3_sha = "8" * 40
    m4_sha = "9" * 40
    tree = "1" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, tree),
            (m2_sha, tree),
            (m2_sha, tree),
            (m3_sha, tree),
            (m3_sha, tree),
            (m4_sha, tree),
            (m4_sha, tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=3,
    )

    assert result.outcome is CompletionLoopOutcome.DEFERRED_CONCURRENCY
    assert "GENERATION_BUDGET_EXHAUSTED" in result.reason
    assert result.generation == 3
    assert len(port.cas_merge_calls) == 0


def test_p_hostile_reconciliation_checks_on_ambiguous_ack(monkeypatch):
    """P & Defect 2: Hostile checks on ambiguous ACK for merged SHA mismatch, missing parents, non-typed output."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    # Sub-case 1: Ambiguous ACK, CAS returned merged_sha="a"*40, reconciliation observed "9"*40 -> BLOCKED
    port_sha_mismatch = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="9" * 40,
                observed_main_tree_sha="01" * 20,
                observed_parent_shas=(new_main_sha, "01" * 20),
            )
        ],
    )
    res1 = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_sha_mismatch
    )
    assert res1.outcome is CompletionLoopOutcome.BLOCKED
    assert "RECONCILIATION_MERGED_SHA_MISMATCH" in res1.reason

    # Sub-case 2: Ambiguous ACK, missing integration parent in observed_parent_shas -> BLOCKED
    port_parent_missing = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="a" * 40,
                observed_main_tree_sha="01" * 20,
                observed_parent_shas=(new_main_sha, "3" * 40),
            )
        ],
    )
    res2 = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_parent_missing
    )
    assert res2.outcome is CompletionLoopOutcome.BLOCKED
    assert "RECONCILIATION_MISSING_INTEGRATION_PARENT" in res2.reason

    # Sub-case 3: Ambiguous ACK, valid physical observation -> COMPLETED
    port_ok = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="a" * 40,
                observed_main_tree_sha="01" * 20,
                observed_parent_shas=(new_main_sha, "01" * 20),
            )
        ],
    )
    res3 = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_ok)
    assert res3.outcome is CompletionLoopOutcome.COMPLETED
    assert res3.merged_commit_sha == "a" * 40


def test_q_hostile_reconciliation_checks_on_cas_success(monkeypatch):
    """Q & Defect 2: Hostile check that CAS SUCCESS cannot complete if reconciliation reports different merged SHA."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    # CAS reported "a"*40, but reconciliation reports "9"*40 -> BLOCKED (Defect 2 proved)
    port_mismatch = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        cas_merge_results=[CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40)],
        post_merge_results=[
            PostMergeReconciliationResult(
                observed_main_commit_sha="9" * 40,
                observed_main_tree_sha="01" * 20,
                observed_parent_shas=(new_main_sha, "01" * 20),
            )
        ],
    )

    res = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port_mismatch,
    )

    assert res.outcome is CompletionLoopOutcome.BLOCKED
    assert "RECONCILIATION_MERGED_SHA_MISMATCH" in res.reason


def test_r_source_candidate_identity_immutable_across_generations(monkeypatch):
    """R. source Candidate commit/tree/acceptance identity remains unchanged through I1/I2."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    m1_sha = "e" * 40
    m1_tree = "2" * 40
    m2_sha = "f" * 40
    m2_tree = "3" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head="b" * 40,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 2
    assert result.evidence.candidate.candidate_commit_sha == "b" * 40
    assert result.evidence.candidate.candidate_tree_sha == "c" * 40
    assert result.evidence.candidate.contract_hash == "2" * 64
    assert result.evidence.candidate.independent_acceptance_hash == "5" * 64
    assert result.evidence.integration.source_candidate_commit_sha == "b" * 40
    assert result.evidence.integration.source_candidate_tree_sha == "c" * 40


def test_s_port_cannot_mint_authorization_or_bypass_evaluator(monkeypatch):
    """S. no port method can approve Candidate, mint grant, waive checks, or bypass evaluator."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context()  # lacks GITHUB_MERGE
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        is_platform_approval=True,
    )

    # Notice: resolve_durable_merge_authorization is called naturally without auth_resolver bypass
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert len(port.cas_merge_calls) == 0


def test_t_timeout_passed_to_checks_and_elapsed_monotonic_bounded(monkeypatch):
    """T & Bounded Elapsed Budget: Monotonic deadline/timeout passed to checks and triggers DEFERRED_CONCURRENCY."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    times = [0.0, 100.0, 2800.0]  # Monotonic clock ticks past 2700s

    def clock():
        return times.pop(0) if times else 3000.0

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        monotonic_clock=clock,
    )

    assert result.outcome is CompletionLoopOutcome.DEFERRED_CONCURRENCY
    assert "TIME_BUDGET_EXHAUSTED" in result.reason


# ==============================================================================
# Real Git Oracle Integration Test (Wiring to physical #441 requalify)
# ==============================================================================


def test_real_git_oracle_requalifies_unrelated_docs_drift(tmp_path: Path, monkeypatch):
    """Test completion loop against REAL requalify_main_movement and a real temporary git repo."""
    fixture = _make_requalify_git_repo(tmp_path, include_agents_change=False)
    initial_ev = _base_evidence(
        base_sha=fixture["old_main_sha"],
        current_main_sha=fixture["old_main_sha"],
    )
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (fixture["new_main_sha"], fixture["new_main_tree_sha"]),
            (fixture["new_main_sha"], fixture["new_main_tree_sha"]),
        ],
        default_pr_head="b" * 40,
        tree_shas={
            fixture["old_main_sha"]: fixture["old_main_tree_sha"],
            fixture["new_main_sha"]: fixture["new_main_tree_sha"],
        },
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        git_root=fixture["repo"],
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 1
    assert len(port.cas_merge_calls) == 1
    assert port.cas_merge_calls[0]["expected_base_sha"] == fixture["new_main_sha"]


def test_real_git_oracle_blocks_authority_agents_drift(tmp_path: Path, monkeypatch):
    """Test completion loop against REAL requalify_main_movement with AGENTS.md drift in real git repo."""
    fixture = _make_requalify_git_repo(tmp_path, include_agents_change=True)
    initial_ev = _base_evidence(
        base_sha=fixture["old_main_sha"],
        current_main_sha=fixture["old_main_sha"],
    )
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (fixture["new_main_sha"], fixture["new_main_tree_sha"]),
        ],
        default_pr_head="b" * 40,
        tree_shas={
            fixture["old_main_sha"]: fixture["old_main_tree_sha"],
            fixture["new_main_sha"]: fixture["new_main_tree_sha"],
        },
        default_changed_paths=("AGENTS.md", "docs/unrelated.md"),
    )

    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        git_root=fixture["repo"],
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUALIFICATION_BLOCKED" in result.reason
    assert len(port.cas_merge_calls) == 0


# ==============================================================================
# Hostile Tests: Materialized Integration Tree Readback & Mismatch Verification
# ==============================================================================


def test_hostile_materialized_tree_mismatch_blocks_without_checks_or_merge(monkeypatch):
    """Hostile test: Materialization claims one tree, but physical get_tree_sha returns another -> BLOCKED, 0 checks, 0 merge, 0 blob reads."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    req = _base_request()

    int_head = "01" * 20
    reported_tree = "01" * 20
    actual_different_tree = "99" * 20

    port = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree), (new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        tree_shas={int_head: actual_different_tree},  # Physical git repo returns different tree!
        materialization_results=[
            IntegrationMaterializationResult(
                success=True,
                integration_head_sha=int_head,
                integration_tree_sha=reported_tree,
            )
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(
            context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,)), req
        ),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "MATERIALIZED_TREE_SHA_MISMATCH" in result.reason
    assert reported_tree in result.reason
    assert actual_different_tree in result.reason
    assert len(port.read_blob_calls) == 0  # Zero blob reads
    assert len(port.checks_calls) == 0  # Zero check calls
    assert len(port.cas_merge_calls) == 0  # Zero CAS merge calls


def test_hostile_materialized_tree_malformed_readback_blocks(monkeypatch):
    """Hostile test: Malformed (uppercase/64-hex/exception) tree readback from get_tree_sha blocks without checks or merge."""
    initial_ev = _base_evidence(base_sha="d" * 40, current_main_sha="d" * 40)
    new_main_sha = "e" * 40
    new_main_tree = "2" * 40
    req = _base_request()
    int_head = "01" * 20

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    # Subcase 1: Uppercase 40-hex tree readback
    port_upper = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        tree_shas={int_head: "A" * 40},
    )
    res_upper = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_upper
    )
    assert res_upper.outcome is CompletionLoopOutcome.BLOCKED
    assert "OBSERVED_INTEGRATION_TREE_MALFORMED" in res_upper.reason
    assert len(port_upper.checks_calls) == 0
    assert len(port_upper.cas_merge_calls) == 0

    # Subcase 2: 64-hex tree readback
    port_64 = SpyGitHubCompletionPort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
        tree_shas={int_head: "1" * 64},
    )
    res_64 = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_64)
    assert res_64.outcome is CompletionLoopOutcome.BLOCKED
    assert "OBSERVED_INTEGRATION_TREE_MALFORMED" in res_64.reason
    assert len(port_64.checks_calls) == 0
    assert len(port_64.cas_merge_calls) == 0

    # Subcase 3: Exception on get_tree_sha
    class ErrorTreePort(SpyGitHubCompletionPort):
        def get_tree_sha(self, commit_sha: str) -> str:
            if commit_sha.startswith("0"):
                raise IOError("disk read error on git tree object")
            return super().get_tree_sha(commit_sha)

    port_err = ErrorTreePort(
        main_states=[(new_main_sha, new_main_tree)],
        default_pr_head="b" * 40,
    )
    res_err = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_err)
    assert res_err.outcome is CompletionLoopOutcome.BLOCKED
    assert "GET_TREE_SHA_FAILED" in res_err.reason
    assert len(port_err.checks_calls) == 0
    assert len(port_err.cas_merge_calls) == 0


# ==============================================================================
# Issue #1247 G07 regression test matrix (Tests A through O)
# ==============================================================================


def _setup_g07_test(monkeypatch, **evidence_kwargs):
    ev = _base_evidence(**evidence_kwargs)
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )
    return ev, req


def _make_g07_pr_body(intents: list[tuple[int, str]], extra_prose: str = "") -> str:
    items = [{"issue": num, "on_merge": action} for num, action in intents]
    payload = json.dumps(items, indent=2)
    return f"{extra_prose}\n\n<!-- NEXUS_ISSUE_INTENT_V1\n{payload}\nNEXUS_ISSUE_INTENT_V1 -->\n"


def test_g07_test_a_keep_open_neutral_fields_pass(monkeypatch):
    """Test A: KEEP_OPEN + neutral final fields -> PASS, cas_merge called exactly once."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="feat: neutral commit title",
        commit_message="Detailed description (#1232 remains open)",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.reason == "MERGE_SUCCESS_AND_RECONCILED"
    assert len(port.cas_merge_calls) == 1


def test_g07_test_b_keep_open_with_closes_keyword_blocked(monkeypatch):
    """Test B: KEEP_OPEN + 'Closes #N' in final fields -> BLOCKED, 0 cas_merge calls."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="feat: something",
        commit_message="Closes #1232",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "FINAL_MERGE_INTENT_BINDING_REJECTED" in result.reason
    assert "REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_g07_test_c_keep_open_with_fixes_keyword_blocked(monkeypatch):
    """Test C: KEEP_OPEN + 'Fixes #N' in final fields -> BLOCKED, 0 cas_merge calls."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="Fixes #1232",
        commit_message="neutral details",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "FINAL_MERGE_INTENT_BINDING_REJECTED" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_g07_test_d_closing_keyword_targeting_undeclared_issue_blocked(monkeypatch):
    """Test D: closing keyword targeting undeclared Issue in final fields -> BLOCKED, 0 merges."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="feat: update",
        commit_message="Closes #999",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_g07_test_e_authorized_close_with_matching_final_field(monkeypatch):
    """Test E: authorized CLOSE + matching closing final field -> merge allowed and completed."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "CLOSE")], extra_prose="Closes #1232.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="fix(#1232): resolve defect",
        commit_message="Closes #1232",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "closed"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert len(port.cas_merge_calls) == 1


def test_g07_test_f_stale_identity_fields_fail_closed(monkeypatch):
    """Test F: stale PR number, head SHA, or base SHA fail closed before cas_merge."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")

    # F1: Wrong PR number
    f1 = FinalMergeFields(
        pr_number=99999,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port1 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=f1,
    )
    res1 = run_github_completion_loop(initial_evidence=ev, request=req, port=port1)
    assert res1.outcome is CompletionLoopOutcome.BLOCKED
    assert "PR_NUMBER_MISMATCH" in res1.reason
    assert len(port1.cas_merge_calls) == 0

    # F2: Stale head SHA
    f2 = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha="0" * 40,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port2 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=f2,
    )
    res2 = run_github_completion_loop(initial_evidence=ev, request=req, port=port2)
    assert res2.outcome is CompletionLoopOutcome.BLOCKED
    assert "HEAD_SHA_MISMATCH" in res2.reason
    assert len(port2.cas_merge_calls) == 0

    # F3: Stale base SHA
    f3 = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha="0" * 40,
        merge_method="squash",
        pr_body=pr_body,
    )
    port3 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=f3,
    )
    res3 = run_github_completion_loop(initial_evidence=ev, request=req, port=port3)
    assert res3.outcome is CompletionLoopOutcome.BLOCKED
    assert "BASE_SHA_MISMATCH" in res3.reason
    assert len(port3.cas_merge_calls) == 0


def test_g07_test_g_merge_methods_closure_semantics_invariance(monkeypatch):
    """Test G: merge methods (merge, squash, rebase) enforce identical G07 semantics, unsupported fails."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")

    for method in ("merge", "squash", "rebase"):
        # Neutral fields -> Pass
        pass_fields = FinalMergeFields(
            pr_number=ev.pull_request_number,
            head_sha=ev.head_sha,
            base_sha=ev.base_sha,
            merge_method=method,
            pr_body=pr_body,
            commit_title="neutral title",
        )
        port_pass = SpyGitHubCompletionPort(
            main_states=[(ev.base_sha, ev.tree_sha)],
            default_pr_head=ev.head_sha,
            final_merge_fields=pass_fields,
            issue_states={1232: "open"},
        )
        res_pass = run_github_completion_loop(initial_evidence=ev, request=req, port=port_pass)
        assert res_pass.outcome is CompletionLoopOutcome.COMPLETED
        assert len(port_pass.cas_merge_calls) == 1

        # Closes keyword -> Blocked
        block_fields = FinalMergeFields(
            pr_number=ev.pull_request_number,
            head_sha=ev.head_sha,
            base_sha=ev.base_sha,
            merge_method=method,
            pr_body=pr_body,
            commit_title="Closes #1232",
        )
        port_block = SpyGitHubCompletionPort(
            main_states=[(ev.base_sha, ev.tree_sha)],
            default_pr_head=ev.head_sha,
            final_merge_fields=block_fields,
            issue_states={1232: "open"},
        )
        res_block = run_github_completion_loop(initial_evidence=ev, request=req, port=port_block)
        assert res_block.outcome is CompletionLoopOutcome.BLOCKED
        assert len(port_block.cas_merge_calls) == 0

    # Unsupported method
    bad_method_fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="cherry-pick",
        pr_body=pr_body,
    )
    port_bad = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=bad_method_fields,
    )
    res_bad = run_github_completion_loop(initial_evidence=ev, request=req, port=port_bad)
    assert res_bad.outcome is CompletionLoopOutcome.BLOCKED
    assert "UNSUPPORTED_MERGE_METHOD" in res_bad.reason
    assert len(port_bad.cas_merge_calls) == 0


def test_g07_test_h_drift_generation_revalidates_g07(monkeypatch):
    """Test H: generation N drift re-validates fresh merge fields; stale validation is not reused."""
    old_main = "d" * 40
    new_main = "e" * 40
    int_head = "01" * 20

    ev, req = _setup_g07_test(monkeypatch, current_main_sha=old_main, base_sha=old_main)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )

    # Generation 1 dynamic fields provider that provides fresh base and head
    def dynamic_fields(*, repository, pull_request_number):
        return FinalMergeFields(
            pr_number=pull_request_number,
            head_sha=int_head,
            base_sha=new_main,
            merge_method="squash",
            pr_body=pr_body,
            commit_title="neutral generation 1",
        )

    port = SpyGitHubCompletionPort(
        main_states=[(new_main, "2" * 40)],
        default_pr_head="b" * 40,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.BASE_MOVED),  # Gen 0 drifts
            CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="a" * 40),
        ],
        final_merge_fields=dynamic_fields,
        issue_states={1232: "open"},
    )
    res = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert res.outcome is CompletionLoopOutcome.COMPLETED
    assert res.generation == 1
    # Verify read_final_merge_fields was called on both generation attempts
    assert len(port.read_final_merge_fields_calls) >= 2


def test_g07_test_i_post_effect_keep_open_actual_open_completed(monkeypatch):
    """Test I: KEEP_OPEN + merged + actual Issue=open -> COMPLETED."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.reason == "MERGE_SUCCESS_AND_RECONCILED"


def test_g07_test_j_post_effect_keep_open_actual_closed_mismatch_blocks(monkeypatch):
    """Test J: KEEP_OPEN + merged + actual Issue=closed -> BLOCKED, no second merge."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "closed"},  # Unexpected closed state!
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "POST_MERGE_ISSUE_STATE_MISMATCH" in result.reason
    assert "STATE_MISMATCH expected 'open' (KEEP_OPEN), observed 'closed'" in result.reason
    assert result.details["post_merge_verification"]["allow_second_merge"] is False
    assert len(port.cas_merge_calls) == 1  # Exactly 1 merge, NO second merge!


def test_g07_test_k_post_effect_close_actual_open_mismatch_blocks(monkeypatch):
    """Test K: CLOSE + merged + actual Issue=open -> BLOCKED, no second merge."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "CLOSE")], extra_prose="Closes #1232.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="fix(#1232): fix defect",
        commit_message="Closes #1232",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={1232: "open"},  # Unexpected open state!
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "POST_MERGE_ISSUE_STATE_MISMATCH" in result.reason
    assert "STATE_MISMATCH expected 'closed' (CLOSE), observed 'open'" in result.reason
    assert result.details["post_merge_verification"]["allow_second_merge"] is False
    assert len(port.cas_merge_calls) == 1


def test_g07_test_l_post_effect_issue_state_unknown_blocks(monkeypatch):
    """Test L: Issue state readback unavailable/unknown -> BLOCKED, fails closed."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={},  # Missing state -> will be UNKNOWN
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "ACTUAL_STATE_UNKNOWN" in result.reason
    assert len(port.cas_merge_calls) == 1


def test_g07_test_m_multi_issue_intent_independent_verification(monkeypatch):
    """Test M: multi-Issue intent verifies each issue independently without cross-authorization."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body(
        [(101, "KEEP_OPEN"), (102, "CLOSE")],
        extra_prose="#101 remains open. Closes #102.",
    )
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="feat: update",
        commit_message="Closes #102",
    )

    # M1: Both match
    p1 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={101: "open", 102: "closed"},
    )
    r1 = run_github_completion_loop(initial_evidence=ev, request=req, port=p1)
    assert r1.outcome is CompletionLoopOutcome.COMPLETED

    # M2: 101 closed unexpectedly
    p2 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={101: "closed", 102: "closed"},
    )
    r2 = run_github_completion_loop(initial_evidence=ev, request=req, port=p2)
    assert r2.outcome is CompletionLoopOutcome.BLOCKED
    assert "#101" in r2.reason

    # M3: 102 remained open unexpectedly
    p3 = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states={101: "open", 102: "open"},
    )
    r3 = run_github_completion_loop(initial_evidence=ev, request=req, port=p3)
    assert r3.outcome is CompletionLoopOutcome.BLOCKED
    assert "#102" in r3.reason


def test_g07_test_n_ambiguous_ack_physical_merge_confirmed_issue_state_matches(monkeypatch):
    """Test N: ambiguous ACK + physical merge confirmed + Issue state matches -> COMPLETED."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        final_merge_fields=fields,
        issue_states={1232: "open"},
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.reason == "AMBIGUOUS_ACK_RECONCILED_SUCCESS"


def test_g07_test_o_ambiguous_ack_physical_merge_confirmed_issue_mismatch_blocks(monkeypatch):
    """Test O: ambiguous ACK + physical merge confirmed + Issue mismatch -> BLOCKED, 0 second merge."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        cas_merge_results=[
            CasMergeResult(status=CasMergeStatus.AMBIGUOUS_ACK, merged_sha="a" * 40)
        ],
        final_merge_fields=fields,
        issue_states={1232: "closed"},  # Mismatch under KEEP_OPEN!
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "AMBIGUOUS_MERGE_POST_VERIFICATION_FAILED" in result.reason
    assert "STATE_MISMATCH" in result.reason
    assert result.details["post_merge_verification"]["allow_second_merge"] is False
    assert len(port.cas_merge_calls) == 1  # Exactly 1 merge call, zero retry/second merge


class _PortWithMissingMethods:
    def __init__(self, inner, missing_methods: tuple[str, ...]):
        self._inner = inner
        self._missing = set(missing_methods)

    def __getattr__(self, name: str):
        if name in self._missing:
            raise AttributeError(f"Port has no attribute {name!r}")
        return getattr(self._inner, name)


def test_g07_production_regression_1_missing_read_final_merge_fields_blocks(monkeypatch):
    """Test 1: Host adapter port lacks read_final_merge_fields -> BLOCKED, 0 merges (FINAL_MERGE_FIELDS_PORT_UNAVAILABLE)."""
    ev, req = _setup_g07_test(monkeypatch)
    inner_port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
    )
    port = _PortWithMissingMethods(inner_port, ("read_final_merge_fields",))

    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert result.reason == "FINAL_MERGE_FIELDS_PORT_UNAVAILABLE"
    assert len(inner_port.cas_merge_calls) == 0


def test_g07_production_regression_2_missing_or_failed_pr_body_blocks(monkeypatch):
    """Test 2: Host adapter read failure or pr_body=None/empty -> BLOCKED, 0 merges."""
    ev, req = _setup_g07_test(monkeypatch)

    # 2a: port read_final_merge_fields raises exception
    def failing_read(*a, **k):
        raise RuntimeError("GitHub API connection timeout")

    port_err = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=failing_read,
    )
    r_err = run_github_completion_loop(initial_evidence=ev, request=req, port=port_err)
    assert r_err.outcome is CompletionLoopOutcome.BLOCKED
    assert "READ_FINAL_MERGE_FIELDS_FAILED:GitHub API connection timeout" in r_err.reason
    assert len(port_err.cas_merge_calls) == 0

    # 2b: port returns pr_body=None
    fields_none = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=None,
    )
    port_none = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields_none,
    )
    r_none = run_github_completion_loop(initial_evidence=ev, request=req, port=port_none)
    assert r_none.outcome is CompletionLoopOutcome.BLOCKED
    assert r_none.reason == "FINAL_MERGE_INTENT_PR_BODY_MISSING"
    assert len(port_none.cas_merge_calls) == 0

    # 2c: port returns empty / whitespace pr_body
    fields_empty = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body="   \n\t  ",
    )
    port_empty = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields_empty,
    )
    r_empty = run_github_completion_loop(initial_evidence=ev, request=req, port=port_empty)
    assert r_empty.outcome is CompletionLoopOutcome.BLOCKED
    assert r_empty.reason == "FINAL_MERGE_INTENT_PR_BODY_MISSING"
    assert len(port_empty.cas_merge_calls) == 0


def test_g07_production_regression_4_governed_keep_open_contradictory_message_blocks(monkeypatch):
    """Test 4: GOVERNED KEEP_OPEN + contradictory final message (Closes #1232) -> Loop blocks, 0 merges."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
        commit_title="fix(#1232): separate expired predecessor",
        commit_message="Closes #1232\n\nFull description.",
    )
    port = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
    )
    result = run_github_completion_loop(initial_evidence=ev, request=req, port=port)
    assert result.outcome is CompletionLoopOutcome.BLOCKED
    assert "FINAL_MERGE_INTENT_BINDING_REJECTED" in result.reason
    assert "REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS" in result.reason
    assert len(port.cas_merge_calls) == 0


def test_g07_production_regression_5_post_merge_issue_readback_missing_or_failing(monkeypatch):
    """Test 5: Post-merge issue readback missing or failing -> Reconciliation fails closed, allow_second_merge: False, 0 second merge."""
    ev, req = _setup_g07_test(monkeypatch)
    pr_body = _make_g07_pr_body([(1232, "KEEP_OPEN")], extra_prose="#1232 remains open.")
    fields = FinalMergeFields(
        pr_number=ev.pull_request_number,
        head_sha=ev.head_sha,
        base_sha=ev.base_sha,
        merge_method="squash",
        pr_body=pr_body,
    )

    # 5a: port lacks read_issue_states
    inner_no_states = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
    )
    port_no_states = _PortWithMissingMethods(inner_no_states, ("read_issue_states",))

    r_no_states = run_github_completion_loop(initial_evidence=ev, request=req, port=port_no_states)
    assert r_no_states.outcome is CompletionLoopOutcome.BLOCKED
    assert "POST_MERGE_ISSUE_STATE_MISMATCH" in r_no_states.reason
    assert "READ_ISSUE_STATES_PORT_UNAVAILABLE" in r_no_states.reason
    assert r_no_states.details["post_merge_verification"]["allow_second_merge"] is False
    assert len(inner_no_states.cas_merge_calls) == 1  # Exactly 1 merge occurred, 0 second merge

    # 5b: port read_issue_states raises exception
    def failing_issue_states(*a, **k):
        raise RuntimeError("GitHub GraphQL rate limit exceeded")

    port_failing_states = SpyGitHubCompletionPort(
        main_states=[(ev.base_sha, ev.tree_sha)],
        default_pr_head=ev.head_sha,
        final_merge_fields=fields,
        issue_states=failing_issue_states,
    )
    r_failing = run_github_completion_loop(
        initial_evidence=ev, request=req, port=port_failing_states
    )
    assert r_failing.outcome is CompletionLoopOutcome.BLOCKED
    assert "POST_MERGE_ISSUE_STATE_MISMATCH" in r_failing.reason
    assert "READ_ISSUE_STATES_FAILED" in r_failing.reason
    assert r_failing.details["post_merge_verification"]["allow_second_merge"] is False
    assert len(port_failing_states.cas_merge_calls) == 1  # 0 second merge


# ==============================================================================
# Issue 1384 Acceptance Criteria Tests: Completion Liveness Under Main Churn
# ==============================================================================


def test_issue1384_criterion1_four_consecutive_unrelated_main_movements_during_ci(monkeypatch):
    """AC 1, 2, 3, 5, 6: Four consecutive unrelated main movements during exact-head CI

    converge to CAS merge without Owner interruption, zero fresh Candidate re-acceptance,
    fresh exact-head required checks per generation, candidate blob equivalence verified
    each generation, and immutable source Candidate identity.
    """
    m0_sha = "00" * 20
    m0_tree = "00" * 20
    cand_c = "b" * 40
    m1_sha = "11" * 20
    m1_tree = "11" * 20
    m2_sha = "22" * 20
    m2_tree = "22" * 20
    m3_sha = "33" * 20
    m3_tree = "33" * 20
    m4_sha = "44" * 20
    m4_tree = "44" * 20

    initial_ev = _base_evidence(base_sha=m0_sha, current_main_sha=m0_sha)

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),  # gen 1 start
            (m2_sha, m2_tree),  # main moves while gen 1 checks run
            (m2_sha, m2_tree),  # gen 2 start
            (m3_sha, m3_tree),  # main moves while gen 2 checks run
            (m3_sha, m3_tree),  # gen 3 start
            (m4_sha, m4_tree),  # main moves while gen 3 checks run
            (m4_sha, m4_tree),  # gen 4 start
            (m4_sha, m4_tree),  # gen 4 post-check confirms main unchanged
            (m4_sha, m4_tree),
        ],
        default_pr_head=cand_c,
        tree_shas={
            m0_sha: m0_tree,
            m1_sha: m1_tree,
            m2_sha: m2_tree,
            m3_sha: m3_tree,
            m4_sha: m4_tree,
        },
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    # 1. Converged to completed CAS merge
    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 4

    # 2. Materialized 4 consecutive generations chaining heads correctly
    assert len(port.materialize_calls) == 4
    assert port.materialize_calls[0]["expected_pr_head_sha"] == cand_c
    assert port.materialize_calls[0]["generation"] == 1
    assert port.materialize_calls[1]["expected_pr_head_sha"] == "01" * 20
    assert port.materialize_calls[1]["generation"] == 2
    assert port.materialize_calls[2]["expected_pr_head_sha"] == "02" * 20
    assert port.materialize_calls[2]["generation"] == 3
    assert port.materialize_calls[3]["expected_pr_head_sha"] == "03" * 20
    assert port.materialize_calls[3]["generation"] == 4

    # 3. Exact-head required checks were run for every generation
    assert len(port.checks_calls) == 4
    for i, gen in enumerate([1, 2, 3, 4]):
        assert port.checks_calls[i]["head_sha"] == f"{gen:02x}" * 20
        assert port.checks_calls[i]["generation"] == gen

    # 4. Blob equivalence mechanically verified on every generation
    assert len(port.read_blob_calls) == 8  # 4 generations * 2 (source + integration)

    # 5. CAS merge executed at generation 4 on base M4 and head I4
    assert len(port.cas_merge_calls) == 1
    assert port.cas_merge_calls[0]["expected_base_sha"] == m4_sha
    assert port.cas_merge_calls[0]["expected_head_sha"] == "04" * 20

    # 6. Source candidate identity remained completely immutable
    assert result.evidence.candidate.candidate_commit_sha == cand_c
    assert result.evidence.candidate.candidate_tree_sha == "c" * 40
    assert result.evidence.candidate.contract_hash == "2" * 64
    assert result.evidence.candidate.independent_acceptance_hash == "5" * 64
    assert result.evidence.integration.source_candidate_commit_sha == cand_c
    assert result.evidence.integration.source_candidate_tree_sha == "c" * 40
    assert result.evidence.integration.generation == 4
    assert result.evidence.integration.integration_head_sha == "04" * 20
    assert result.evidence.integration.integration_base_sha == m4_sha


def test_issue1384_criterion4_test_impact_revalidates_only_affected_tests(monkeypatch):
    """AC 4: TEST_IMPACT reruns only the affected test evidence without fresh candidate acceptance."""
    m0_sha = "00" * 20
    m0_tree = "00" * 20
    cand_c = "b" * 40
    m1_sha = "11" * 20
    m1_tree = "11" * 20
    m2_sha = "22" * 20
    m2_tree = "22" * 20

    initial_ev = _base_evidence(base_sha=m0_sha, current_main_sha=m0_sha)

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head=cand_c,
        tree_shas={
            m0_sha: m0_tree,
            m1_sha: m1_tree,
            m2_sha: m2_tree,
        },
        default_changed_paths=("tests/unit/test_runner.py",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "TEST_ONLY",
                "unmatched_paths": [],
                "changed_paths": ["tests/unit/test_runner.py"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 2
    # TEST_IMPACT was revalidated on each movement, NO fresh candidate acceptance was performed
    assert port.revalidation_calls == ["TEST_IMPACT", "TEST_IMPACT"]
    assert result.evidence.candidate.independent_acceptance_hash == "5" * 64
    assert len(port.cas_merge_calls) == 1
    assert port.cas_merge_calls[0]["expected_base_sha"] == m2_sha


def test_issue1384_criterion7_cas_base_moved_reenters_without_owner(monkeypatch):
    """AC 7: Main movement immediately at CAS merge re-enters bounded requalification without Owner interruption."""
    m0_sha = "00" * 20
    m0_tree = "00" * 20
    cand_c = "b" * 40
    m1_sha = "11" * 20
    m1_tree = "11" * 20
    m2_sha = "22" * 20
    m2_tree = "22" * 20

    initial_ev = _base_evidence(base_sha=m0_sha, current_main_sha=m0_sha)

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m1_sha, m1_tree),
            (m1_sha, m1_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
            (m2_sha, m2_tree),
        ],
        default_pr_head=cand_c,
        tree_shas={
            m0_sha: m0_tree,
            m1_sha: m1_tree,
            m2_sha: m2_tree,
        },
        default_changed_paths=("docs/unrelated.md",),
        cas_merge_results=[
            CasMergeResult(
                status=CasMergeStatus.BASE_MOVED,
                reason="main moved right at merge time",
            ),
            CasMergeResult(status=CasMergeStatus.SUCCESS, merged_sha="aa" * 20),
        ],
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 2
    assert len(port.cas_merge_calls) == 2
    assert port.cas_merge_calls[0]["expected_base_sha"] == m1_sha
    assert port.cas_merge_calls[1]["expected_base_sha"] == m2_sha
    assert result.evidence.integration.generation == 2


def test_issue1384_criterion8_resume_from_existing_generation(monkeypatch):
    """AC 8, 11: An evidence already at generation 8 (#1209 R8) can resume and absorb 3 drift steps

    (R8 -> R9 -> R10 -> R11) without tripping GENERATION_BUDGET_EXHAUSTED or requiring fresh
    Candidate acceptance or manual branch reconstruction.
    """
    cand_c = "b" * 40
    m8_sha = "88" * 20
    m8_tree = "88" * 20
    i8_head = "08" * 20
    i8_tree = "08" * 20

    blob_eq = CandidateBlobEquivalence(
        path="nexus/a.py",
        source_blob_sha="1" * 40,
        integration_blob_sha="1" * 40,
    )
    proof_hash = compute_candidate_equivalence_proof_hash(
        source_candidate_commit_sha=cand_c,
        source_candidate_tree_sha="c" * 40,
        source_candidate_diff_hash="e" * 64,
        integration_base_sha=m8_sha,
        integration_head_sha=i8_head,
        integration_tree_sha=i8_tree,
        generation=8,
        blob_equivalences=(blob_eq,),
    )
    gen8_binding = IntegrationBinding(
        source_candidate_commit_sha=cand_c,
        source_candidate_tree_sha="c" * 40,
        source_contract_hash="2" * 64,
        source_candidate_state_hash="3" * 64,
        source_verified_receipt_hash="4" * 64,
        source_independent_acceptance_hash="5" * 64,
        source_candidate_diff_hash="e" * 64,
        integration_base_sha=m8_sha,
        integration_head_sha=i8_head,
        integration_tree_sha=i8_tree,
        generation=8,
        requalification_hash="1" * 64,
        check_subject_kind="INTEGRATION_HEAD",
        check_subject_sha=i8_head,
        check_subject_tree_sha=i8_tree,
        blob_equivalences=(blob_eq,),
        candidate_equivalence_proof_hash=proof_hash,
    )

    checks_r8 = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha=i8_head,
            generation=8,
        ),
    )
    ev_r8 = _base_evidence(
        base_sha=m8_sha,
        head_sha=i8_head,
        tree_sha=i8_tree,
        current_main_sha=m8_sha,
        integration=gen8_binding,
        required_checks=checks_r8,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks_r8]}),
    )

    m9_sha = "99" * 20
    m9_tree = "99" * 20
    m10_sha = "aa" * 20
    m10_tree = "aa" * 20
    m11_sha = "bb" * 20
    m11_tree = "bb" * 20

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=[
            (m9_sha, m9_tree),  # gen 9 start
            (m10_sha, m10_tree),  # moves during gen 9
            (m10_sha, m10_tree),  # gen 10 start
            (m11_sha, m11_tree),  # moves during gen 10
            (m11_sha, m11_tree),  # gen 11 start
            (m11_sha, m11_tree),  # gen 11 post-check unchanged
            (m11_sha, m11_tree),
        ],
        default_pr_head=i8_head,
        tree_shas={
            m8_sha: m8_tree,
            m9_sha: m9_tree,
            m10_sha: m10_tree,
            m11_sha: m11_tree,
        },
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=ev_r8,
        request=req,
        port=port,
        max_generations=5,
    )

    assert result.outcome is CompletionLoopOutcome.COMPLETED
    assert result.generation == 11
    assert len(port.materialize_calls) == 3
    # First materialization (gen 9) chained from i8_head
    assert port.materialize_calls[0]["expected_pr_head_sha"] == i8_head
    assert port.materialize_calls[0]["generation"] == 9
    assert port.materialize_calls[1]["expected_pr_head_sha"] == "09" * 20
    assert port.materialize_calls[1]["generation"] == 10
    assert port.materialize_calls[2]["expected_pr_head_sha"] == "0a" * 20
    assert port.materialize_calls[2]["generation"] == 11

    # Final CAS merge occurred at generation 11
    assert len(port.cas_merge_calls) == 1
    assert port.cas_merge_calls[0]["expected_base_sha"] == m11_sha
    assert port.cas_merge_calls[0]["expected_head_sha"] == "0b" * 20


def test_issue1384_criterion9_generation_budget_exhaustion_truthful_disposition(monkeypatch):
    """AC 9: Exhaustion of relative generation budget returns truthful DEFERRED_CONCURRENCY

    with GENERATION_BUDGET_EXHAUSTED, not FRESH_CANDIDATE_ACCEPTANCE_REQUIRED.
    """
    m0_sha = "00" * 20
    cand_c = "b" * 40
    shas = [f"{i:02x}" * 20 for i in range(1, 10)]
    trees = [f"{i:02x}" * 20 for i in range(1, 10)]

    tree_shas = {m0_sha: "00" * 20}
    for s, t in zip(shas, trees):
        tree_shas[s] = t

    initial_ev = _base_evidence(base_sha=m0_sha, current_main_sha=m0_sha)

    # 5 movements absorb gen 1..5. Movement 6 trips the relative budget of 5.
    # Each generation consumes two reads: top read_main_state() and post-check read_main_state().
    main_states = [
        (shas[0], trees[0]),  # Gen 1 entry (shas[0] != m0) -> materializes I1
        (shas[1], trees[1]),  # Gen 1 post-check -> detects drift to shas[1], loops to gen 2
        (shas[1], trees[1]),  # Gen 2 entry -> materializes I2
        (shas[2], trees[2]),  # Gen 2 post-check -> detects drift to shas[2], loops to gen 3
        (shas[2], trees[2]),  # Gen 3 entry -> materializes I3
        (shas[3], trees[3]),  # Gen 3 post-check -> detects drift to shas[3], loops to gen 4
        (shas[3], trees[3]),  # Gen 4 entry -> materializes I4
        (shas[4], trees[4]),  # Gen 4 post-check -> detects drift to shas[4], loops to gen 5
        (shas[4], trees[4]),  # Gen 5 entry -> materializes I5
        (shas[5], trees[5]),  # Gen 5 post-check -> detects drift to shas[5], loops to next
        (
            shas[5],
            trees[5],
        ),  # Gen 6 entry: current_generation (5) - start_generation (0) >= max_generations (5) -> EXHAUSTED!
        (shas[6], trees[6]),
        (shas[6], trees[6]),
    ]

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=main_states,
        default_pr_head=cand_c,
        tree_shas=tree_shas,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=initial_ev,
        request=req,
        port=port,
        max_generations=5,
    )

    assert result.outcome is CompletionLoopOutcome.DEFERRED_CONCURRENCY
    assert result.reason == "GENERATION_BUDGET_EXHAUSTED"
    assert result.generation == 5
    assert len(port.cas_merge_calls) == 0


def test_issue1384_criterion9_resume_and_exhaust_relative_budget(monkeypatch):
    """AC 8, 9: An already-integrated evidence (start_generation=8) that encounters 5 drift steps

    (reaching gen 13) exhausts its relative budget of 5 truthfully with GENERATION_BUDGET_EXHAUSTED.
    """
    cand_c = "b" * 40
    m8_sha = "88" * 20
    m8_tree = "88" * 20
    i8_head = "08" * 20
    i8_tree = "08" * 20

    blob_eq = CandidateBlobEquivalence(
        path="nexus/a.py",
        source_blob_sha="1" * 40,
        integration_blob_sha="1" * 40,
    )
    proof_hash = compute_candidate_equivalence_proof_hash(
        source_candidate_commit_sha=cand_c,
        source_candidate_tree_sha="c" * 40,
        source_candidate_diff_hash="e" * 64,
        integration_base_sha=m8_sha,
        integration_head_sha=i8_head,
        integration_tree_sha=i8_tree,
        generation=8,
        blob_equivalences=(blob_eq,),
    )
    gen8_binding = IntegrationBinding(
        source_candidate_commit_sha=cand_c,
        source_candidate_tree_sha="c" * 40,
        source_contract_hash="2" * 64,
        source_candidate_state_hash="3" * 64,
        source_verified_receipt_hash="4" * 64,
        source_independent_acceptance_hash="5" * 64,
        source_candidate_diff_hash="e" * 64,
        integration_base_sha=m8_sha,
        integration_head_sha=i8_head,
        integration_tree_sha=i8_tree,
        generation=8,
        requalification_hash="1" * 64,
        check_subject_kind="INTEGRATION_HEAD",
        check_subject_sha=i8_head,
        check_subject_tree_sha=i8_tree,
        blob_equivalences=(blob_eq,),
        candidate_equivalence_proof_hash=proof_hash,
    )

    checks_r8 = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha=i8_head,
            generation=8,
        ),
    )
    ev_r8 = _base_evidence(
        base_sha=m8_sha,
        head_sha=i8_head,
        tree_sha=i8_tree,
        current_main_sha=m8_sha,
        integration=gen8_binding,
        required_checks=checks_r8,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks_r8]}),
    )

    shas = [f"{i:02x}" * 20 for i in range(9, 16)]
    trees = [f"{i:02x}" * 20 for i in range(9, 16)]
    tree_shas = {m8_sha: m8_tree}
    for s, t in zip(shas, trees):
        tree_shas[s] = t

    # Relative budget is 5.
    # Absorbs 5 generations: gen 9 (shas[0]), gen 10 (shas[1]), gen 11 (shas[2]), gen 12 (shas[3]), gen 13 (shas[4]).
    # When main moves to shas[5], current_generation (13) - start_generation (8) == 5 >= max_generations (5) -> EXHAUSTS!
    main_states = [
        (shas[0], trees[0]),  # Gen 9 entry
        (shas[1], trees[1]),  # Gen 9 post-check -> drift to shas[1]
        (shas[1], trees[1]),  # Gen 10 entry
        (shas[2], trees[2]),  # Gen 10 post-check -> drift to shas[2]
        (shas[2], trees[2]),  # Gen 11 entry
        (shas[3], trees[3]),  # Gen 11 post-check -> drift to shas[3]
        (shas[3], trees[3]),  # Gen 12 entry
        (shas[4], trees[4]),  # Gen 12 post-check -> drift to shas[4]
        (shas[4], trees[4]),  # Gen 13 entry
        (shas[5], trees[5]),  # Gen 13 post-check -> drift to shas[5]
        (shas[5], trees[5]),  # Gen 14 entry: 13 - 8 = 5 >= 5 -> GENERATION_BUDGET_EXHAUSTED!
        (shas[6], trees[6]),
    ]

    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    port = SpyGitHubCompletionPort(
        main_states=main_states,
        default_pr_head=i8_head,
        tree_shas=tree_shas,
        default_changed_paths=("docs/unrelated.md",),
    )

    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.github_completion_loop.resolve_durable_merge_authorization",
        lambda *a, **k: evaluate_action(ctx, req),
    )

    result = run_github_completion_loop(
        initial_evidence=ev_r8,
        request=req,
        port=port,
        max_generations=5,
    )

    assert result.outcome is CompletionLoopOutcome.DEFERRED_CONCURRENCY
    assert result.reason == "GENERATION_BUDGET_EXHAUSTED"
    assert result.generation == 13
    assert len(port.materialize_calls) == 5
    assert len(port.cas_merge_calls) == 0


def test_issue1384_criterion10_hostile_drift_fails_closed(monkeypatch):
    """AC 10: Authority drift, candidate blob mismatch, and unknown impact fail closed without merge."""
    m0_sha = "00" * 20
    m0_tree = "00" * 20
    cand_c = "b" * 40
    m1_sha = "11" * 20
    m1_tree = "11" * 20
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    # 10a: Authority drift
    initial_ev = _base_evidence(base_sha=m0_sha, current_main_sha=m0_sha)
    port_auth = SpyGitHubCompletionPort(
        main_states=[(m1_sha, m1_tree)],
        default_pr_head=cand_c,
        tree_shas={m0_sha: m0_tree, m1_sha: m1_tree},
        default_changed_paths=("AGENTS.md",),
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.verify_exact_git_main_movement_paths",
        lambda **k: {"valid": True, "proven_paths": tuple(k["changed_main_paths"])},
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "AUTHORITY_DRIFT",
                "unmatched_paths": [],
                "changed_paths": ["AGENTS.md"],
            },
        )(),
    )
    res_auth = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_auth)
    assert res_auth.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUALIFICATION_BLOCKED" in res_auth.reason
    assert len(port_auth.cas_merge_calls) == 0

    # 10b: Candidate blob SHA mismatch
    port_blob = SpyGitHubCompletionPort(
        main_states=[(m1_sha, m1_tree), (m1_sha, m1_tree)],
        default_pr_head=cand_c,
        tree_shas={m0_sha: m0_tree, m1_sha: m1_tree},
        default_changed_paths=("docs/unrelated.md",),
        blob_shas={
            ("c" * 40, "nexus/a.py"): "1" * 40,
            ("01" * 20, "nexus/a.py"): "9"
            * 40,  # Corrupted / hostile candidate blob in integration tree
        },
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    res_blob = run_github_completion_loop(initial_evidence=initial_ev, request=req, port=port_blob)
    assert res_blob.outcome is CompletionLoopOutcome.BLOCKED
    assert "CANDIDATE_BLOB_SHA_MISMATCH:nexus/a.py" in res_blob.reason
    assert len(port_blob.cas_merge_calls) == 0

    # 10c: Unknown impact
    port_unknown = SpyGitHubCompletionPort(
        main_states=[(m1_sha, m1_tree)],
        default_pr_head=cand_c,
        tree_shas={m0_sha: m0_tree, m1_sha: m1_tree},
        default_changed_paths=("unclassified/file.dat",),
    )
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "IMPACT_UNKNOWN",
                "unmatched_paths": ["unclassified/file.dat"],
                "changed_paths": ["unclassified/file.dat"],
            },
        )(),
    )
    res_unknown = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_unknown
    )
    assert res_unknown.outcome is CompletionLoopOutcome.BLOCKED
    assert "REQUALIFICATION_BLOCKED" in res_unknown.reason or "IMPACT_UNKNOWN" in res_unknown.reason
    assert len(port_unknown.cas_merge_calls) == 0

    # 10d: Integration materialization merge conflict
    monkeypatch.setattr(
        "scripts.ops.pr_impact_gate.build_impact_plan",
        lambda *a, **k: type(
            "Plan",
            (),
            {
                "impact_class": "DOCS_GOVERNANCE",
                "unmatched_paths": [],
                "changed_paths": ["docs/unrelated.md"],
            },
        )(),
    )
    port_conflict = SpyGitHubCompletionPort(
        main_states=[(m1_sha, m1_tree)],
        default_pr_head=cand_c,
        tree_shas={m0_sha: m0_tree, m1_sha: m1_tree},
        default_changed_paths=("docs/unrelated.md",),
        materialization_results=[
            IntegrationMaterializationResult(
                success=False,
                conflict=True,
                error="CONFLICT_IN_TREE_MERGE",
            )
        ],
    )
    res_conflict = run_github_completion_loop(
        initial_evidence=initial_ev, request=req, port=port_conflict
    )
    assert res_conflict.outcome is CompletionLoopOutcome.BLOCKED
    assert "INTEGRATION_MATERIALIZATION_FAILED:CONFLICT_IN_TREE_MERGE" in res_conflict.reason
    assert len(port_conflict.cas_merge_calls) == 0
