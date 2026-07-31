# Task Card 02: Verify Task Target Integrity

## Identity

- task_id: `verify-task-target-integrity`
- campaign_id: `lifecycle-hardening-followup`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `startup-report-path-portability` integrated
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make `SelfHostedTaskService.verify_task()` fail closed if any verifier command creates, deletes, or changes a file in the Target. Verification must remain read-only with respect to lifecycle state, commits, cleanup, approval, integration, and push.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope

No change to worker routing, Candidate promotion, cleanup authorization, Task Card schema, canonical root, branch/ref deletion, or GitNexus instructions. Do not transplant the obsolete `verify_task_state()` implementation wholesale.

## Required behavior

1. Snapshot Target content before verifier execution, including unreadable/missing entries as fail-closed errors.
2. Execute existing verifier commands under the existing deterministic environment.
3. Snapshot Target content after execution and fail if the digest or integrity status changed.
4. Return explicit failure reasons and preserve provider call count and lifecycle state invariants.
5. Add a regression test whose verifier creates a file and demonstrate RED before the fix and GREEN after it.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Evidence required

- Current-base RED reproduction: verifier creates a Target file while result incorrectly reports `VERIFIED`.
- GREEN regression test and focused lifecycle suite.
- Exact commit SHA and scoped diff.

## Exit criteria

No verifier-created Target mutation can produce a verified result, existing valid verification remains green, and a scoped commit is created.

## Residual debt

Authorized-deletion contract remains separate. Cleanup apply cannot infer promotion from this verification card.

## Block classification

- `RECOVERABLE_BLOCK`: isolated Target cannot be created or test runtime is unavailable.
- `HARD_BLOCK`: implementation would require trusting verifier commands or weakening fail-closed evidence semantics.
