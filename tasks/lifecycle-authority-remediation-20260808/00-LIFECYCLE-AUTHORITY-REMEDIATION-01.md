# Task Card: LIFECYCLE-AUTHORITY-REMEDIATION-01

artifact_authority: current
task_id: `LIFECYCLE-AUTHORITY-REMEDIATION-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Fix one bounded lifecycle remediation defect without changing route authority. When a terminal governed attempt has already failed with repository-contract evidence kind effective_route_authority_change because repository-authority-change.v1 was absent, the task action/status must not recommend blind retry_same_task. It must emit a deterministic contract-update-required remediation that names required_protected_contracts=[repository-authority-change.v1], states that unchanged retry is unsafe/not authorized, preserves the same semantic task_id, and surfaces any salvage_commit_sha/salvage_ref as recoverable evidence only. nexus_task_retry/retry_task must fail fast before Target creation or provider execution for this known predecessor condition instead of replaying the unchanged request. Preserve RETRY_SEMANTIC_TASK_MISMATCH for actual semantic/scope changes; do not weaken the repository contract gate, do not auto-authorize authority changes, do not auto-consume architecture approval, do not create a new router/planner/lifecycle, do not alter CapabilityPlanner/HybridRouteDecision authority, and do not touch Gateway public dispatch in this card. Add focused regression tests proving: authority-block predecessor => no runner/provider call on retry and exact remediation; ordinary retryable FINAL_BLOCK behavior remains unchanged; semantic-change retry remains rejected; salvage identity is reported but not promoted to Candidate. Stop at a scoped Candidate pending independent/owner review; no approval, integration, push, cleanup, successor, or production/public claim.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification commands

```bash
python3 -m pytest tests/nexus/orchestrator/test_self_hosted_task_service.py -q
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
