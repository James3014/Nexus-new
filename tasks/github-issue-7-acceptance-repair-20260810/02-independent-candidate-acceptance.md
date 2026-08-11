---
artifact_authority: current
owner: James Chen
status: BLOCKED_OWNER_GATE
task_id: github-issue-7-m3-b-independent-acceptance
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
owner_gate: M3_B_CAMPAIGN_REBIND_AND_OWNER_GATE
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# M3-B Independent Exact-Candidate Acceptance

Current frontier, blocked on the Owner gate: implementation starts only after
Owner approval of the M3-B autonomy-conditional acceptance receipt/approval
gate (`M3_B_CAMPAIGN_REBIND_AND_OWNER_GATE`).

## Objective

Add one typed ACCEPT / REPAIRABLE / BLOCK reducer that binds the exact Candidate
commit, tree, state hash, diff identity, verified receipt, task/attempt, worker
identity, and applicable #16 verified-repair adequacy evidence. Consume existing
#16 semantics; do not reconstruct them.

## Dependency

M3-A completed and exact-reviewed.

## Allowed files

- `nexus/orchestrator/acceptance_loop.py`
- `nexus/orchestrator/candidate_commit.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_acceptance_loop.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

Maximum changed files: 5.

## Required behavior

- implementer identity cannot equal independent acceptance identity
- acceptance binds exact Candidate commit/tree/state/diff and verifier receipt
- VERIFIED_REPAIR class requires current matching #16 adequacy/mutation receipts
- drift, missing/stale/tampered proof, bare zero-exit, or descriptive
  reproduction evidence returns BLOCK
- verifier/review defect may return REPAIRABLE with bounded structured reasons
- acceptance never approves merge, integration, activation, or public claim

## Verification and exit

Focused positive, separation-of-duties, tamper, stale, wrong-Candidate,
wrong-attempt, and false-green tests; Ruff, Pyright, `git diff --check`; exact
commit and independent review.

## Block classification

`RECOVERABLE_BLOCK` for reducer/test defects; `HARD_BLOCK` for weaker evidence
semantics or self-acceptance.
