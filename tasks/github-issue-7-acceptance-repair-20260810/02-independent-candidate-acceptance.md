---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-7-m3-b-independent-acceptance
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
owner_gate: M3_B_CAMPAIGN_REBIND_AND_OWNER_GATE
owner_gate_status: GRANTED
owner_gate_granted_at: 2026-08-11
baseline_main: 9dddd018ad2761face3d2f3ce29dff8d8feae72d
completion_main: 89ed130ac5d3ad58106e7d9ba8f0d3a65066fdc2
completed_via_pr: 161
pr_head: d2a3bfa8b6ed3fd28015565680a84cdf7c826768
merge_commit: 9121cd2cf83e959db763bbb578a60f861b0855fb
merge_date: 2026-08-11
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# M3-B Independent Exact-Candidate Acceptance

Completed frontier. The Owner granted the M3-B autonomy-conditional acceptance
receipt/approval gate (`M3_B_CAMPAIGN_REBIND_AND_OWNER_GATE`) in the active
Codex thread on 2026-08-11. This grant authorizes only this card's bounded
Candidate implementation; it does not authorize approval, integration, merge,
activation, or public claims.

The historical ACTIVE card permitted its scoped Candidate commit and branch
push. This COMPLETED reconciliation closes those worker permissions; it grants
no authority to M3-C or any successor card.

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
