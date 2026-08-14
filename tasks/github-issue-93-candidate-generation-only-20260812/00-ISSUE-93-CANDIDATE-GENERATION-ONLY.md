---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-93-candidate-generation-only
campaign_id: github-issue-93-candidate-generation-only-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/93
baseline_main: ea8c15293455575b4312b92eeeebc69daa4abbcf
historical_baseline: ea8c15293455575b4312b92eeeebc69daa4abbcf
merge_base: 34fc70af1cd57f7499bf92ecec4926a9716c8de2
reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
current_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: CANDIDATE_GENERATION_ONLY_SEMANTIC_PROVEN
claim_ceiling: CANDIDATE_GENERATION_ONLY_SEMANTIC_PROVEN_ONLY
AUTO_CHAIN: false
commit_required: true
candidate_required: false
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
---

# Candidate-generation-only planner semantic

## Objective

Add a strict Boolean `candidate_generation_only` canonical task fact. When it
is true, `mutation_requested` must be explicitly false and CapabilityPlanner
must project a bounded candidate-generation Workforce demand without selecting
a provider, model, or worker. Malformed or contradictory facts fail closed
before execution.

## Dependencies and inputs

- Issue #93 current contract
- PR #81 physically merged at `41e5ee06eeecb4abd7df7c15c36af13142a1da56`
- fresh collaboration main `ea8c15293455575b4312b92eeeebc69daa4abbcf`
- no open PR ownership overlap at card creation

## Allowed files

- `nexus/contracts/canonical_execution.py`
- `nexus/engine/capability_planner.py`
- `tests/contracts/test_canonical_execution.py`
- `tests/engine/test_capability_planner.py`
- this card and its `INDEX.md`

## Forbidden scope

- PR #81 orchestration or canonical task seam changes
- runtime, gateway, adapter, provider, model, or worker identity selection
- a second Planner, Router, Workforce, Candidate, approval, or integration authority
- default-route or Workforce policy promotion
- Candidate acceptance, repair execution, runtime activation, merge, release,
  production, or public-readiness claims
- Issue #143 or its files
- unrelated cleanup or compatibility shims

## RED evidence

- `CanonicalTaskContext` currently rejects `candidate_generation_only` as an
  unknown task fact.
- CapabilityPlanner currently has no explicit contradiction check and projects
  an ordinary implementation demand instead of bounded candidate generation.

## GREEN acceptance

- the new fact is accepted only as a strict Boolean;
- true requires an explicitly present `mutation_requested=false`;
- true plus mutation, missing explicit non-mutation, or malformed values fail
  closed before topology or Workforce execution;
- CapabilityPlanner remains the sole topology/route authority and projects the
  existing `bounded_candidate_generation` role with non-mutation intent,
  bounded context, and external verification;
- no provider/model/worker identity enters the planner output;
- existing `candidate_required`, ordinary mutation, review, and complex-task
  semantics do not regress.

## Verification

- `uv run pytest -q tests/contracts/test_canonical_execution.py tests/engine/test_capability_planner.py`
- `uv run ruff check nexus/contracts/canonical_execution.py nexus/engine/capability_planner.py tests/contracts/test_canonical_execution.py tests/engine/test_capability_planner.py`
- `uv run ruff format --check --preview nexus/contracts/canonical_execution.py nexus/engine/capability_planner.py tests/contracts/test_canonical_execution.py tests/engine/test_capability_planner.py`
- `uv run python -m compileall -q nexus/contracts/canonical_execution.py nexus/engine/capability_planner.py`
- `git diff --check`
- complete allowed-file and staged-diff audit
- independent exact-head hostile review

## Physical evidence and terminal boundary

- Historical card baseline: `ea8c15293455575b4312b92eeeebc69daa4abbcf`.
- Exact merge base: `34fc70af1cd57f7499bf92ecec4926a9716c8de2`.
- PR #185 head: `024f51bd0e7e9b0e8995d18a62212647bf050a42`.
- PR #185 merge: `0e4c325bbca2304658cea4e0c23f4584d9440dff`.
- Exact changed scope: the four source/test paths above plus this card and INDEX.
- Head workflows: Pyright, Wiki governance, Ruff, Policy lane, Bandit, and Pytest
  completed successfully.
- Reconciled current main: `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`.

`CANDIDATE_GENERATION_ONLY_SEMANTIC_PROVEN` is limited to the strict canonical
fact and existing CapabilityPlanner demand projection. It grants no provider/model/
worker identity selection, second route or authority, Candidate acceptance, runtime,
approval, integration, merge, release, production, or public-readiness truth.
`AUTO_CHAIN=false`.
