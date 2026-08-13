---
artifact_authority: current
task_id: github-issue-65-gate-a-false-witnesses
campaign_id: github-issue-65-golden-witness-gate-a-20260813
source_issue: "#65"
owner: James Chen
status: ACTIVE
baseline_revision: f3dc8d28a0f90d5c5fd2f31dbeb0ab2f29f7ca04
commit_required: true
candidate_required: true
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
---

# Gate A semantic Golden witnesses

## Objective

Replace GB-019 and GB-042 false/insufficient witnesses with behavioral positive
and negative evidence only. Do not change production or corpus claims.

## Inputs and dependencies

- #7 M3-B/M3-D physically merged and #7 closed.
- corpus blob `88a236e3e440052e193aed08f19e996ddab7ed5a`.
- GB-019 witness blob `4d417fe6c1de4c9fb976b55db7c7c1eec4ff991e`.
- GB-042 witness blob `f88dba4950cfb606414a83b841ff6a43b4b1a59d`.

## Allowed implementation/test files

- `tests/contracts/test_hybrid_route_contract.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

This card and INDEX are governance artifacts outside the two-file ceiling.

## Required behavior

- GB-019 exercises the public delivery seam: advisory guard plus failing
  verifier cannot block delivery or create retry/block/claim transition;
  blocking/non-advisory override fails closed.
- GB-042 uses a fully valid external-acceptance and approval/integration
  binding; calling approved integration twice produces one physical side
  effect, stable receipt/commit identity, and idempotent duplicate result.
- If either test exposes a production defect, stop that slice and report a
  separate bounded product Issue; never weaken the witness.

## Forbidden scope

No production, corpus, evaluator, workflow, route/Workforce/lifecycle authority,
Candidate approval semantics, #143, or #191 work.

## Verification

- run the exact GB-019/GB-042 nodes and adjacent focused tests
- canonical Golden evaluator for affected cases if selectable
- Ruff on changed tests and `git diff --check`
- independent hostile review

## Exit

Gate A Candidate PR only. Gates B/C remain residual Issue #65 scope.
Claim ceiling: `GOLDEN_WITNESS_GATE_A_SEMANTIC_TESTS_CANDIDATE_ONLY`.
