---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-7-m3-a-canonical-dispatch
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# M3-A Canonical Planner to Admission to Dispatch Binding

## Objective

Make the production gateway derive one canonical typed dispatch envelope from
the actual CapabilityPlanner decision and current Workforce Admission, then
bind that identity through `WorkerRegistry.invoke`. Caller-supplied
worker/provider/model fields are evidence inputs only and never selection
authority.

## Dependencies

- #6 / M2 physically merged
- #16 / PR #41 physically merged at
  `599227f0efbe1e9a4ca8cd6bff56824f0a6d9965`

## Allowed files

- `nexus/engine/canonical_task_seam.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/engine/test_canonical_task_seam.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/executors/test_worker_contract.py`

Maximum changed files: 7.

## Required behavior

- CapabilityPlanner remains the sole route/capability-selection authority.
- Workforce Admission only admits or rejects the requested role/autonomy and
  resolves an eligible worker binding.
- The envelope binds planner decision/plan hash, demand id, worker/provider/
  model, policy hash, binding hash, aggregate binding hash, task id, and attempt
  id.
- Missing or mismatched planner/admission/binding identity fails before worker
  provider invocation with zero calls.
- Persisted dispatch identity must equal the identity used by WorkerRegistry.

## RED controls

- caller swaps worker/provider/model
- missing planner decision/hash
- admission record for another demand/task/attempt
- policy/binding/aggregate hash mismatch
- persisted envelope differs from invocation envelope

## Verification

- focused tests for all allowed test files
- changed-file Ruff check and preview-format check
- changed-file Pyright
- `git diff --check`

## Exit

Exact commit, independent review, zero-call negatives, and one deterministic
Planner-to-Registry positive pass. This proves structural dispatch binding, not
real provider solve truth.

## Forbidden scope

No second router, policy rewrite, runtime activation, model promotion, Issue
#29 files, Candidate acceptance, repair loop, merge, or public claim.

## Block classification

`RECOVERABLE_BLOCK` for bounded implementation defects; `HARD_BLOCK` for a
request to trust caller-selected identity or duplicate route authority.
