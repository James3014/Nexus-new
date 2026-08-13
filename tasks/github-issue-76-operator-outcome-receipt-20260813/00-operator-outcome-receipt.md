---
artifact_authority: current
task_id: github-issue-76-operator-outcome-receipt
campaign_id: github-issue-76-operator-outcome-receipt-20260813
source_issue: "#76"
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

# Task-scoped privacy-bounded operator outcome receipt

## Objective

Implement `nexus.operator_outcome_receipt.v1` inside the existing
`nexus.self_hosted_task_state.v1` and expose it only through the existing task
receipt projection. The receipt is observational and grants no authority.

## Inputs and dependencies

- Current main at the exact baseline above.
- #7 ordered task/attempt event and persistence seam, physically merged.
- Issue #76 live contract; #31 is not a dependency.

## Allowed implementation/test files

- `nexus/contracts/operator_outcome_receipt.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/contracts/test_operator_outcome_receipt.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

This card and campaign INDEX are governance artifacts outside the four-file
implementation ceiling.

## Required behavior

- strict unknown-field rejection and canonical payload hash;
- exact task/attempt/lifecycle and source/runtime receipt identity binding;
- exact idempotency conflict behavior and acyclic same-attempt supersession;
- freshness, stale, tamper, conflict, and privacy-negative validation;
- persistence only in existing task state and projection only via get_receipt;
- no free text, chat, hidden CoT, traits, credentials, personal identity,
  telemetry collection, learning writeback, or global analytics;
- no verifier/Candidate/approval/integration/claim/release mutation.

## Verification

- `python3 -m pytest -q tests/contracts/test_operator_outcome_receipt.py tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'operator_outcome'`
- focused adjacent self-hosted receipt tests
- Ruff on the new contract/test when available
- `git diff --check` and exact four-file implementation scope audit

## Exit and residual debt

Exit with a Candidate PR only. No automatic adaptation, production, release,
or public-readiness claim. Claim ceiling:
`OPERATOR_OUTCOME_RECEIPT_CONTRACT_AND_TASK_STATE_PERSISTENCE_TESTED_ONLY`.

`HARD_BLOCK` for privacy/authority widening or unexpected overlap;
`RECOVERABLE_BLOCK` for bounded verifier or formatting defects.
